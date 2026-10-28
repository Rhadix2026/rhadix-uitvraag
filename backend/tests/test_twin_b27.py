"""B-27 — de twin-aanbieder bestaat alleen bij een expliciete TWIN_DATASTATION_URL.

Tot nu toe viel een ontbrekende variabele stil terug op
`http://host.docker.internal:8017`, de staging-Datastation. Daardoor zette
productie-Uitvraag vragen uit bij staging. Nu:

- geen (of een lege) TWIN_DATASTATION_URL → geen twin, en een bestaande twin wordt
  losgekoppeld; de rij, zijn capabilities en de antwoorden blijven staan;
- `ophalen` benadert alleen het datastation waar de aanbieder nu op aangesloten is,
  zodat bestaande uitgezette antwoorden ongewijzigd blijven uitstaan.

`init_db()` is precies wat bij startup draait; opnieuw aanroepen simuleert een
herstart of deployment op dezelfde database.
"""
import uuid

import pytest

from app.bootstrap import TWIN_NAAM, init_db
from app.database import SessionLocal
from app.models.kik_models import (AanbiederCapability, Antwoord, AntwoordStatus, Uitvraag,
                                   UitvraagStatus, Zorgaanbieder)

TWIN_URL = "http://twin-staging-datastation:8000"


def _twin():
    db = SessionLocal()
    try:
        return db.query(Zorgaanbieder).filter(Zorgaanbieder.naam == TWIN_NAAM).first()
    finally:
        db.close()


def _twin_capabilities() -> int:
    db = SessionLocal()
    try:
        return db.query(AanbiederCapability).filter(AanbiederCapability.aanbieder_naam == TWIN_NAAM).count()
    finally:
        db.close()


@pytest.fixture
def geen_twin(client):
    """Begin zonder twin; ruim hem na de test weer op (gedeelde testdatabase)."""
    def opruimen():
        db = SessionLocal()
        try:
            db.query(AanbiederCapability).filter(AanbiederCapability.aanbieder_naam == TWIN_NAAM).delete()
            twin = db.query(Zorgaanbieder).filter(Zorgaanbieder.naam == TWIN_NAAM).first()
            if twin:
                db.query(Antwoord).filter(Antwoord.zorgaanbieder_id == twin.id).delete()
                db.delete(twin)
            db.commit()
        finally:
            db.close()
    opruimen()
    yield
    opruimen()


# ── Seeding ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("waarde", [None, "", "   "])
def test_zonder_configuratie_geen_twin(geen_twin, monkeypatch, waarde):
    if waarde is None:
        monkeypatch.delenv("TWIN_DATASTATION_URL", raising=False)
    else:
        monkeypatch.setenv("TWIN_DATASTATION_URL", waarde)
    init_db()
    assert _twin() is None, "zonder configuratie mag er geen twin ontstaan"
    assert _twin_capabilities() == 0


def test_geen_stille_standaard_naar_8017(geen_twin, monkeypatch):
    monkeypatch.delenv("TWIN_DATASTATION_URL", raising=False)
    init_db()
    db = SessionLocal()
    try:
        urls = {z.datastation_url for z in db.query(Zorgaanbieder).all()}
    finally:
        db.close()
    assert not any(u and "host.docker.internal" in u for u in urls)


def test_met_configuratie_twin_en_capabilities(geen_twin, monkeypatch):
    monkeypatch.setenv("TWIN_DATASTATION_URL", f"  {TWIN_URL} ")
    init_db()
    twin = _twin()
    assert twin is not None and twin.datastation_url == TWIN_URL
    n = _twin_capabilities()
    assert n > 0
    init_db()                                   # idempotent
    assert _twin_capabilities() == n and _twin().id == twin.id


def test_url_wijzigen_werkt_door(geen_twin, monkeypatch):
    monkeypatch.setenv("TWIN_DATASTATION_URL", TWIN_URL)
    init_db()
    monkeypatch.setenv("TWIN_DATASTATION_URL", "http://ander-datastation")
    init_db()
    assert _twin().datastation_url == "http://ander-datastation"


def test_configuratie_weg_koppelt_los_en_behoudt_alles(geen_twin, monkeypatch):
    monkeypatch.setenv("TWIN_DATASTATION_URL", TWIN_URL)
    init_db()
    twin_id, caps = _twin().id, _twin_capabilities()

    monkeypatch.delenv("TWIN_DATASTATION_URL")
    init_db()
    twin = _twin()
    assert twin is not None and twin.id == twin_id, "de twin-rij moet blijven bestaan"
    assert twin.datastation_url is None
    assert _twin_capabilities() == caps, "bestaande capabilities blijven staan"


# ── Ophalen ──────────────────────────────────────────────────────────────────
def _uitgezette_uitvraag(client, auth, monkeypatch, url):
    """Een uitvraag met één uitgezet antwoord bij de twin (dien_in gemockt)."""
    import app.routers.uitvragen as uv
    profs = client.get("/api/profielen", headers=auth).json()
    key = profs[0]["key"]
    code = client.get(f"/api/profielen/{key}", headers=auth).json()["indicatoren"][0]["code"]
    monkeypatch.setattr(uv, "dien_in", lambda z, ind, afnemer=None: {
        "modus": "async", "query_id": "Q-B27", "status": "UITGEZET",
        "duur_ms": 3, "url": url, "toelichting": "uitgezet"})
    u = client.post("/api/uitvragen", headers=auth, json={
        "profiel_key": key, "indicator_codes": [code], "zorgaanbieder_ids": [str(_twin().id)]}).json()
    assert u["status"] == "LOPEND" and u["antwoorden"][0]["status"] == "UITGEZET", u
    return u


def _antwoord(uitvraag_id):
    db = SessionLocal()
    try:
        a = db.query(Antwoord).filter(Antwoord.uitvraag_id == uuid.UUID(uitvraag_id)).one()
        u = db.get(Uitvraag, uuid.UUID(uitvraag_id))
        return ({k: getattr(a, k) for k in ("status", "waarde", "query_id", "datastation_url",
                                            "toelichting", "duur_ms", "computed_at")}, u.status)
    finally:
        db.close()


def test_losgekoppelde_twin_wordt_niet_benaderd(geen_twin, client, auth, monkeypatch):
    """Het productiescenario: uitgezette antwoorden blijven ongewijzigd en de oude
    URL wordt niet aangeroepen, ook niet door de auto-poll van de frontend."""
    import app.routers.uitvragen as uv
    monkeypatch.setenv("TWIN_DATASTATION_URL", TWIN_URL)
    init_db()
    u = _uitgezette_uitvraag(client, auth, monkeypatch, TWIN_URL)
    voor = _antwoord(u["id"])

    monkeypatch.delenv("TWIN_DATASTATION_URL")
    init_db()                                   # deploy zonder twin-configuratie

    aangeroepen = []
    monkeypatch.setattr(uv, "haal_resultaat", lambda url, qid: aangeroepen.append(url) or
                        {"status": "GEREED", "waarde": 1.0})
    for _ in range(3):                          # zoals de 4-secondenpoll
        d = client.post(f"/api/uitvragen/{u['id']}/ophalen", headers=auth)
        assert d.status_code == 200 and d.json()["bijgewerkt"] == 0
    assert aangeroepen == []
    assert _antwoord(u["id"]) == voor, "het uitgezette antwoord moet ongewijzigd blijven"
    assert voor[1] == UitvraagStatus.LOPEND and voor[0]["status"] == AntwoordStatus.UITGEZET


def test_omgezette_twin_haalt_niet_bij_oude_url(geen_twin, client, auth, monkeypatch):
    import app.routers.uitvragen as uv
    monkeypatch.setenv("TWIN_DATASTATION_URL", TWIN_URL)
    init_db()
    u = _uitgezette_uitvraag(client, auth, monkeypatch, TWIN_URL)
    monkeypatch.setenv("TWIN_DATASTATION_URL", "http://ander-datastation")
    init_db()
    aangeroepen = []
    monkeypatch.setattr(uv, "haal_resultaat", lambda url, qid: aangeroepen.append(url) or {"status": "GEREED"})
    assert client.post(f"/api/uitvragen/{u['id']}/ophalen", headers=auth).json()["bijgewerkt"] == 0
    assert aangeroepen == []


def test_actuele_twin_haalt_gewoon_op(geen_twin, client, auth, monkeypatch):
    """Op staging (twin geconfigureerd) werkt de federatieve flow ongewijzigd,
    ook als de URL met of zonder afsluitende slash is opgegeven."""
    import app.routers.uitvragen as uv
    monkeypatch.setenv("TWIN_DATASTATION_URL", TWIN_URL + "/")
    init_db()
    u = _uitgezette_uitvraag(client, auth, monkeypatch, TWIN_URL)
    aangeroepen = []
    monkeypatch.setattr(uv, "haal_resultaat", lambda url, qid: aangeroepen.append((url, qid)) or
                        {"status": "GEREED", "waarde": 42.0, "handmatig": False})
    d = client.post(f"/api/uitvragen/{u['id']}/ophalen", headers=auth).json()
    assert aangeroepen == [(TWIN_URL, "Q-B27")]
    assert d["bijgewerkt"] == 1 and d["status"] == "VOLTOOID"
    assert d["antwoorden"][0]["waarde"] == 42.0
