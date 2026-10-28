"""B-29 — geen SSRF via de datastation-URL van een zorgaanbieder.

Drie lagen, elk apart getest:
1. wie een aanbieder mag aanmaken of een URL mag zetten (autorisatie);
2. welke bestemmingen de server mag aanroepen (allowlist, alleen publieke IP's,
   geen redirects, het gecontroleerde IP-adres vastgepind);
3. wat de gebruiker te zien krijgt (geen netwerkdetails).
"""
import uuid

import httpx
import pytest

import app.services.bestemming as bestemming
from app.auth.app_access import APP_SLUG
from app.database import SessionLocal
from app.models.kik_models import Zorgaanbieder
from app.services import datastation as ds
from app.services.bestemming import NietToegestaan, controleer, is_toegestaan, normaliseer, verzoek

from tests._testkeys import central_token

PUBLIEK = "https://datastation.voorbeeld.nl"
_HTTPX_CLIENT = httpx.Client
INTERN = "http://twin-intern:8000"


@pytest.fixture(autouse=True)
def allowlist(monkeypatch):
    monkeypatch.setenv("DATASTATION_BESTEMMINGEN", PUBLIEK)
    monkeypatch.setenv("DATASTATION_INTERNE_BESTEMMINGEN", INTERN)


def _H(rol: str, naam: str) -> dict:
    return {"Authorization": "Bearer " + central_token({
        "sub": str(uuid.uuid5(uuid.NAMESPACE_DNS, naam)), "email": f"{naam}@test.rhadix.nl",
        "role": rol, "tenant_name": "B29 Tenant", "apps": [APP_SLUG]})}


def _resolve_als(monkeypatch, *adressen):
    monkeypatch.setattr(bestemming, "_resolve", lambda host, poort: list(adressen))


class _Nep:
    """Vervangt de netwerklaag van httpx en legt elk verzoek vast."""

    def __init__(self, monkeypatch, antwoord):
        self.verzoeken = []

        def handler(request):
            self.verzoeken.append(request)
            return antwoord(request) if callable(antwoord) else antwoord

        monkeypatch.setattr(bestemming.httpx, "Client",
                            lambda **kw: _HTTPX_CLIENT(transport=httpx.MockTransport(handler), **kw))


# ── 1. Autorisatie ───────────────────────────────────────────────────────────
def test_registreren_zonder_token_geweigerd(client):
    r = client.post("/api/zorgaanbieders/register", json={"naam": "Anoniem BV", "datastation_url": PUBLIEK})
    assert r.status_code == 401


def test_registreren_als_org_user_geweigerd(client):
    r = client.post("/api/zorgaanbieders/register", headers=_H("ORG_USER", "b29-user"), json={"naam": "User BV"})
    assert r.status_code == 403


def test_org_admin_registreert_zonder_url(client):
    r = client.post("/api/zorgaanbieders/register", headers=_H("ORG_ADMIN", "b29-orgadmin"),
                    json={"naam": "B29 Zorg zonder URL"})
    assert r.status_code == 201 and r.json()["heeft_datastation"] is False


def test_org_admin_mag_geen_url_zetten(client):
    r = client.post("/api/zorgaanbieders/register", headers=_H("ORG_ADMIN", "b29-orgadmin"),
                    json={"naam": "B29 Zorg met URL", "datastation_url": PUBLIEK})
    assert r.status_code == 403


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data", "http://127.0.0.1:8011", "http://kik-db:5432",
    "http://host.docker.internal:8017", "https://evil.voorbeeld.nl", "file:///etc/passwd",
    "https://datastation.voorbeeld.nl/?x=", "https://user@datastation.voorbeeld.nl",
])
def test_platform_admin_niet_toegestane_url(client, auth, url):
    r = client.post("/api/zorgaanbieders/register", headers=auth,
                    json={"naam": f"B29 {uuid.uuid4().hex[:8]}", "datastation_url": url})
    assert r.status_code == 422, (url, r.text)


def test_platform_admin_toegestane_url_wordt_genormaliseerd(client, auth):
    r = client.post("/api/zorgaanbieders/register", headers=auth,
                    json={"naam": "B29 Publiek Datastation", "datastation_url": "HTTPS://Datastation.Voorbeeld.NL:443/"})
    assert r.status_code == 201
    d = client.get(f"/api/zorgaanbieders/{r.json()['id']}", headers=auth).json()
    assert d["datastation_url"] == PUBLIEK


def test_url_alleen_zichtbaar_voor_platform_admin(client, auth):
    zid = client.post("/api/zorgaanbieders/register", headers=auth,
                      json={"naam": "B29 Zichtbaarheid", "datastation_url": INTERN}).json()["id"]
    assert client.get(f"/api/zorgaanbieders/{zid}", headers=auth).json()["datastation_url"] == INTERN
    d = client.get(f"/api/zorgaanbieders/{zid}", headers=_H("ORG_ADMIN", "b29-orgadmin")).json()
    assert "datastation_url" not in d and d["heeft_datastation"] is True


def test_import_alleen_platform_admin(client):
    csv = b"Naam\nB29 Import BV\n"
    r = client.post("/api/zorgaanbieders/import", headers=_H("ORG_ADMIN", "b29-orgadmin"),
                    files={"file": ("a.csv", csv, "text/csv")})
    assert r.status_code == 403


# ── 2. Bestemmingen ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("url", [
    "ftp://datastation.voorbeeld.nl", "gopher://x", "file:///etc/passwd", "http://", "",
    "https://a:b@datastation.voorbeeld.nl", "https://datastation.voorbeeld.nl#x",
    "https://datastation.voorbeeld.nl?x", "https://datastation.voorbeeld.nl:99999",
])
def test_normaliseer_weigert(url):
    with pytest.raises(NietToegestaan):
        normaliseer(url)


def test_normaliseer_vaste_vorm():
    assert normaliseer("HTTPS://Datastation.Voorbeeld.NL:443/") == PUBLIEK
    assert normaliseer("http://[::1]:8000/") == "http://[::1]:8000"


def test_lege_allowlist_is_fail_closed(monkeypatch):
    monkeypatch.delenv("DATASTATION_BESTEMMINGEN")
    monkeypatch.delenv("DATASTATION_INTERNE_BESTEMMINGEN")
    assert not is_toegestaan(PUBLIEK) and not is_toegestaan(INTERN)
    with pytest.raises(NietToegestaan):
        controleer(PUBLIEK)


def test_niet_op_allowlist(monkeypatch):
    _resolve_als(monkeypatch, "93.184.216.34")
    for url in ("https://ander.voorbeeld.nl", PUBLIEK + "/extra", "http://datastation.voorbeeld.nl"):
        with pytest.raises(NietToegestaan):
            controleer(url)


@pytest.mark.parametrize("ip", [
    "127.0.0.1", "10.0.0.5", "172.17.0.1", "172.22.0.4", "192.168.1.1", "169.254.169.254",
    "100.64.0.1", "0.0.0.0", "::1", "fe80::1", "fc00::1", "::ffff:127.0.0.1", "224.0.0.1",
])
def test_publieke_bestemming_naar_intern_adres_geweigerd(monkeypatch, ip):
    """DNS die een toegestane naam naar een intern adres laat wijzen (rebinding)."""
    _resolve_als(monkeypatch, ip)
    with pytest.raises(NietToegestaan):
        controleer(PUBLIEK)


def test_gemengde_dns_geweigerd(monkeypatch):
    _resolve_als(monkeypatch, "93.184.216.34", "10.0.0.5")
    with pytest.raises(NietToegestaan):
        controleer(PUBLIEK)


def test_interne_bestemming_alleen_expliciet(monkeypatch):
    _resolve_als(monkeypatch, "10.0.0.5")
    assert controleer(INTERN).intern is True
    with pytest.raises(NietToegestaan):
        controleer("http://twin-intern:8001")


def test_verbinding_gaat_naar_gecontroleerd_adres(monkeypatch):
    """Na de controle verbindt de client met het gecontroleerde IP; Host en SNI
    blijven de naam. Een tweede DNS-antwoord kan daar niet meer tussenkomen."""
    _resolve_als(monkeypatch, "93.184.216.34")
    nep = _Nep(monkeypatch, httpx.Response(200, json={"status": "IN_BEHANDELING"}))
    assert verzoek("GET", PUBLIEK, "/api/datastation/vragen/abc/resultaat")["status"] == "IN_BEHANDELING"
    rq = nep.verzoeken[0]
    assert str(rq.url) == "https://93.184.216.34/api/datastation/vragen/abc/resultaat"
    assert rq.headers["host"] == "datastation.voorbeeld.nl"
    assert rq.extensions.get("sni_hostname") == "datastation.voorbeeld.nl"


@pytest.mark.parametrize("code", [301, 302, 303, 307, 308])
def test_redirect_wordt_niet_gevolgd(monkeypatch, code):
    _resolve_als(monkeypatch, "93.184.216.34")
    nep = _Nep(monkeypatch, httpx.Response(code, headers={"Location": "http://169.254.169.254/"}))
    with pytest.raises(NietToegestaan):
        verzoek("GET", PUBLIEK, "/x")
    assert len(nep.verzoeken) == 1


def test_te_groot_of_geen_json(monkeypatch):
    _resolve_als(monkeypatch, "93.184.216.34")
    _Nep(monkeypatch, httpx.Response(200, content=b"x" * (bestemming.MAX_ANTWOORD + 1)))
    with pytest.raises(NietToegestaan):
        verzoek("GET", PUBLIEK, "/x")
    _Nep(monkeypatch, httpx.Response(200, content=b"<html>metadata</html>"))
    with pytest.raises(NietToegestaan):
        verzoek("GET", PUBLIEK, "/x")


def test_geen_proxy_uit_de_omgeving(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    _resolve_als(monkeypatch, "93.184.216.34")
    nep = _Nep(monkeypatch, httpx.Response(200, json={"status": "OK"}))
    verzoek("GET", PUBLIEK, "/x")
    assert nep.verzoeken[0].url.host == "93.184.216.34"


# ── 3. Wat de gebruiker ziet ─────────────────────────────────────────────────
class _Za:
    def __init__(self, url):
        self.datastation_url, self.naam = url, "B29 Testzorg"


IND = {"code": "1.1", "label": "Test", "profiel": "Test"}


def test_niet_toegestane_bestemming_wordt_niet_aangeroepen(monkeypatch):
    nep = _Nep(monkeypatch, httpx.Response(200, json={"query_id": "q1"}))
    r = ds.dien_in(_Za("http://169.254.169.254"), IND)
    assert r["status"] == "FOUT" and r["toelichting"] == ds.MELDING_NIET_TOEGESTAAN
    assert nep.verzoeken == []
    a = ds.vraag_indicator(_Za("http://kik-db:5432"), IND)
    assert a.status == "FOUT" and a.toelichting == ds.MELDING_NIET_TOEGESTAAN


def test_foutmelding_zonder_netwerkdetails(monkeypatch):
    def weigert(request):
        raise httpx.ConnectError("[Errno 111] Connection refused to 10.1.2.3:8000")
    _Nep(monkeypatch, weigert)
    r = ds.dien_in(_Za(INTERN), IND)
    assert r["toelichting"] == ds.MELDING_ONBEREIKBAAR
    for geheim in ("10.1.2.3", "twin-intern", "Errno", "refused"):
        assert geheim not in r["toelichting"]
    assert ds.haal_resultaat(INTERN, "q1")["toelichting"] == ds.MELDING_ONBEREIKBAAR


@pytest.mark.parametrize("qid", ["../../admin", "q1/../x", "q1?x=1", "", None, "a" * 65])
def test_ongeldig_zaaknummer(monkeypatch, qid):
    nep = _Nep(monkeypatch, httpx.Response(200, json={"query_id": qid}))
    assert ds.dien_in(_Za(INTERN), IND)["status"] == "FOUT"
    n = len(nep.verzoeken)
    assert ds.haal_resultaat(INTERN, qid)["status"] == "FOUT"
    assert len(nep.verzoeken) == n, "met een ongeldig zaaknummer wordt niets opgehaald"


def test_toegestane_bestemming_werkt(monkeypatch):
    nep = _Nep(monkeypatch, lambda rq: httpx.Response(201, json={"query_id": "3f2c-0a"}) if rq.method == "POST"
               else httpx.Response(200, json={"status": "GEREED", "waarde": 7.5}))
    r = ds.dien_in(_Za(INTERN + "/"), IND)
    assert r["status"] == "UITGEZET" and r["query_id"] == "3f2c-0a"
    assert ds.haal_resultaat(INTERN, "3f2c-0a") == {"status": "GEREED", "waarde": 7.5}
    assert [str(v.url) for v in nep.verzoeken] == [
        f"{INTERN}/api/datastation/vragen", f"{INTERN}/api/datastation/vragen/3f2c-0a/resultaat"]


def test_ophalen_bij_geblokkeerde_bestemming_laat_antwoord_staan(client, auth, monkeypatch):
    """Komt een bestaande URL niet (meer) door de controle, dan blijft een
    uitgezet antwoord ongewijzigd uitstaan (zoals de 96 in productie, B-27)."""
    import app.routers.uitvragen as uv
    zid = client.post("/api/zorgaanbieders/register", headers=auth,
                      json={"naam": "B29 Ophalen", "datastation_url": INTERN}).json()["id"]
    profs = client.get("/api/profielen", headers=auth).json()
    key = profs[0]["key"]
    code = client.get(f"/api/profielen/{key}", headers=auth).json()["indicatoren"][0]["code"]
    monkeypatch.setattr(uv, "dien_in", lambda z, ind, afnemer=None: {
        "modus": "async", "query_id": "q-b29", "status": "UITGEZET", "duur_ms": 1, "url": INTERN})
    u = client.post("/api/uitvragen", headers=auth, json={
        "profiel_key": key, "indicator_codes": [code], "zorgaanbieder_ids": [zid]}).json()

    monkeypatch.setenv("DATASTATION_INTERNE_BESTEMMINGEN", "")      # bestemming ingetrokken
    nep = _Nep(monkeypatch, httpx.Response(200, json={"status": "GEREED", "waarde": 1.0}))
    d = client.post(f"/api/uitvragen/{u['id']}/ophalen", headers=auth).json()
    assert nep.verzoeken == []
    assert d["status"] == "LOPEND" and d["antwoorden"][0]["status"] == "UITGEZET" and d["bijgewerkt"] == 0
    db = SessionLocal()
    try:
        assert db.get(Zorgaanbieder, uuid.UUID(zid)).datastation_url == INTERN
    finally:
        db.close()
