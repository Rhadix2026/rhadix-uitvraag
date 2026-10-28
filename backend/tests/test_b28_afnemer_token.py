"""B-28 — Uitvraag meldt zich bij een datastation met het centrale serviceaccount.

Het token komt van de centrale login (zoals de CRM-koppeling van Datavalidatie),
wordt hergebruikt tot kort voor het verlopen, gaat alleen naar toegestane
bestemmingen en komt nooit in een melding of de log.
"""
import base64
import json
import logging
import time

import httpx
import pytest

import app.services.afnemer_token as at
import app.services.bestemming as bestemming
from app.services import datastation as ds

INTERN = "http://twin-intern:8000"
LOGIN = "https://login.voorbeeld.nl"
_HTTPX_CLIENT = httpx.Client
IND = {"code": "2.1", "label": "Test", "profiel": "Test"}


def _jwt(exp, n=1):
    kop = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    lijf = base64.urlsafe_b64encode(json.dumps({"exp": exp, "n": n}).encode()).rstrip(b"=").decode()
    return f"{kop}.{lijf}.handtekening{n}"


class _Za:
    def __init__(self, url):
        self.datastation_url, self.naam = url, "B28 Testzorg"


@pytest.fixture
def net(monkeypatch):
    """Nep-netwerk voor zowel de centrale login als het datastation."""
    monkeypatch.setenv("DATASTATION_INTERNE_BESTEMMINGEN", INTERN)
    monkeypatch.setenv("DATASTATION_AFNEMER_LOGIN_URL", LOGIN)
    monkeypatch.setenv("DATASTATION_AFNEMER_EMAIL", "svc@test.rhadix.nl")
    monkeypatch.setenv("DATASTATION_AFNEMER_WACHTWOORD", "Geheim-wachtwoord-123!")
    at.vergeet()
    staat = {"logins": 0, "verzoeken": [], "ds": lambda rq: httpx.Response(201, json={"query_id": "q-1"}),
             "exp": int(time.time()) + 3600}

    def handler(rq):
        if rq.url.host == "login.voorbeeld.nl":
            staat["logins"] += 1
            return httpx.Response(200, json={"access_token": _jwt(staat["exp"], staat["logins"])})
        staat["verzoeken"].append(rq)
        return staat["ds"](rq)

    for mod in (at.httpx, bestemming.httpx):
        monkeypatch.setattr(mod, "Client", lambda **kw: _HTTPX_CLIENT(transport=httpx.MockTransport(handler), **kw))
    yield staat
    at.vergeet()


def test_token_mee_naar_toegestane_bestemming(net):
    r = ds.dien_in(_Za(INTERN), IND)
    assert r["status"] == "UITGEZET"
    assert net["verzoeken"][0].headers["authorization"] == f"Bearer {_jwt(net['exp'], 1)}"


def test_token_hergebruikt_tot_kort_voor_verlopen(net):
    ds.dien_in(_Za(INTERN), IND); ds.dien_in(_Za(INTERN), IND)
    assert net["logins"] == 1
    at.vergeet(); net["exp"] = int(time.time()) + 30          # binnen de marge van 60 s
    ds.dien_in(_Za(INTERN), IND); ds.dien_in(_Za(INTERN), IND)
    assert net["logins"] == 3, "een bijna verlopen token wordt niet hergebruikt"


def test_geen_token_naar_niet_toegestane_bestemming(net):
    r = ds.dien_in(_Za("http://169.254.169.254"), IND)
    assert r["status"] == "FOUT" and net["verzoeken"] == [] and net["logins"] == 0


def test_na_401_eenmaal_opnieuw_met_vers_token(net):
    antwoorden = iter([httpx.Response(401), httpx.Response(201, json={"query_id": "q-2"})])
    net["ds"] = lambda rq: next(antwoorden)
    r = ds.dien_in(_Za(INTERN), IND)
    assert r["status"] == "UITGEZET" and r["query_id"] == "q-2"
    tokens = [rq.headers["authorization"] for rq in net["verzoeken"]]
    assert len(tokens) == 2 and tokens[0] != tokens[1] and net["logins"] == 2


def test_aanhoudende_401_geeft_generieke_fout(net):
    net["ds"] = lambda rq: httpx.Response(401)
    r = ds.dien_in(_Za(INTERN), IND)
    assert r["status"] == "FOUT" and r["toelichting"] == ds.MELDING_ONBEREIKBAAR
    assert len(net["verzoeken"]) == 2, "maximaal één herhaalpoging"


def test_resultaat_van_ander_of_onbekend_blijft_uitstaan(net):
    net["ds"] = lambda rq: httpx.Response(404, json={"detail": "Vraag niet gevonden"})
    assert ds.haal_resultaat(INTERN, "q-1")["status"] == "FOUT"


def test_niet_geconfigureerd_geen_token(net, monkeypatch):
    monkeypatch.delenv("DATASTATION_AFNEMER_WACHTWOORD")
    ds.dien_in(_Za(INTERN), IND)
    assert "authorization" not in net["verzoeken"][0].headers and net["logins"] == 0


def test_login_alleen_over_https(net, monkeypatch):
    monkeypatch.setenv("DATASTATION_AFNEMER_LOGIN_URL", "http://login.voorbeeld.nl")
    assert at.token() is None and net["logins"] == 0


def test_mislukte_login_geen_token_en_geen_geheim_in_log(net, monkeypatch, caplog):
    monkeypatch.setattr(at.httpx, "Client", lambda **kw: _HTTPX_CLIENT(
        transport=httpx.MockTransport(lambda rq: httpx.Response(401)), **kw))
    with caplog.at_level(logging.INFO):
        assert at.token() is None
    assert "Geheim-wachtwoord-123!" not in caplog.text and "svc@test.rhadix.nl" not in caplog.text


def test_token_nooit_in_log_of_melding(net, caplog):
    net["ds"] = lambda rq: httpx.Response(500)
    with caplog.at_level(logging.INFO):
        r = ds.dien_in(_Za(INTERN), IND)
    t = _jwt(net["exp"], 1)
    assert t not in caplog.text and "handtekening" not in caplog.text
    assert "Geheim-wachtwoord-123!" not in caplog.text
    assert t not in r["toelichting"]


def test_token_nooit_over_http_naar_publieke_bestemming(net, monkeypatch):
    monkeypatch.setenv("DATASTATION_BESTEMMINGEN", "http://datastation.voorbeeld.nl,https://datastation.voorbeeld.nl")
    monkeypatch.setattr(bestemming, "_resolve", lambda host, poort: ["93.184.216.34"])
    r = ds.dien_in(_Za("http://datastation.voorbeeld.nl"), IND)
    assert r["status"] == "FOUT" and r["toelichting"] == ds.MELDING_NIET_TOEGESTAAN
    assert net["verzoeken"] == [], "geen verzoek, dus ook geen token over http"
    r = ds.dien_in(_Za("https://datastation.voorbeeld.nl"), IND)
    assert r["status"] == "UITGEZET" and net["verzoeken"][-1].url.scheme == "https"
    assert net["verzoeken"][-1].headers["authorization"].startswith("Bearer ")
