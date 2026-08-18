"""Externe API: machine-to-machine authenticatie met client_credentials.

Externe afnemers werken niet via Rhadix SSO. Ze authenticeren met een eigen
client_id + client_secret, volledig los van gebruikersaccounts en van het
platform-adminwachtwoord. De tenant volgt uit de serverzijdige registratie.

Gedekt: ontbrekende registratie (503), onbekende client en fout secret (401),
correcte client (token), tenantisolatie, gebruik van het token op de externe
routes, rotatie via secret_hash_next, en de standaard geblokkeerde password-grant.
"""
import base64
import json

import pytest

from app.auth.api_clients import hash_secret, load_clients

# Vaste testsecrets: deze bestaan alleen binnen de testsuite.
SECRET_A = "test-secret-client-a-0123456789"
SECRET_B = "test-secret-client-b-9876543210"
SECRET_A_NIEUW = "test-secret-client-a-na-rotatie"

CLIENT_A = "test-afnemer-a"
CLIENT_B = "test-afnemer-b"
TENANT_A = "platform"          # dezelfde tenant als de uitvragen uit test_flow
TENANT_B = "andere-afnemer"    # aparte tenant: mag niets van A zien


def _registry(rotatie: bool = False) -> str:
    """Bouw een KSAPI_CLIENTS-registratie, base64 zoals in staging/productie."""
    entries = [
        {"client_id": CLIENT_A, "naam": "Test Afnemer A", "tenant": TENANT_A,
         "secret_hash": hash_secret(SECRET_A),
         "secret_hash_next": hash_secret(SECRET_A_NIEUW) if rotatie else None},
        {"client_id": CLIENT_B, "naam": "Test Afnemer B", "tenant": TENANT_B,
         "secret_hash": hash_secret(SECRET_B)},
    ]
    return base64.b64encode(json.dumps(entries).encode()).decode()


@pytest.fixture
def registry(monkeypatch):
    monkeypatch.setenv("KSAPI_CLIENTS", _registry())


def _token(client, client_id, secret, grant="client_credentials", **extra):
    data = {"grant_type": grant, "client_id": client_id, "client_secret": secret}
    data.update(extra)
    return client.post("/api/external/token", data=data)


# ── Fail-closed bij ontbrekende of onbruikbare configuratie ──────────────────
def test_zonder_registratie_503(client, monkeypatch):
    monkeypatch.delenv("KSAPI_CLIENTS", raising=False)
    r = _token(client, CLIENT_A, SECRET_A)
    assert r.status_code == 503, r.text


def test_lege_registratie_503(client, monkeypatch):
    monkeypatch.setenv("KSAPI_CLIENTS", "   ")
    assert _token(client, CLIENT_A, SECRET_A).status_code == 503


def test_onbruikbare_registratie_503(client, monkeypatch):
    """Kapotte JSON mag geen 500 geven en zeker geen toegang."""
    monkeypatch.setenv("KSAPI_CLIENTS", "dit-is-geen-json")
    assert _token(client, CLIENT_A, SECRET_A).status_code == 503


def test_onvolledige_registratie_wordt_genegeerd(monkeypatch):
    """Een registratie zonder tenant of secret_hash telt niet mee."""
    monkeypatch.setenv("KSAPI_CLIENTS", json.dumps([{"client_id": "kaal"}]))
    assert load_clients() == {}


# ── Onjuiste credentials ─────────────────────────────────────────────────────
def test_onbekende_client_401(client, registry):
    assert _token(client, "bestaat-niet", SECRET_A).status_code == 401


def test_fout_secret_401(client, registry):
    assert _token(client, CLIENT_A, "verkeerd-secret").status_code == 401


def test_leeg_secret_401(client, registry):
    assert _token(client, CLIENT_A, "").status_code == 401


def test_secret_van_andere_client_401(client, registry):
    """Het secret van B mag niet werken voor A."""
    assert _token(client, CLIENT_A, SECRET_B).status_code == 401


def test_onbekende_grant_400(client, registry):
    assert _token(client, CLIENT_A, SECRET_A, grant="iets-anders").status_code == 400


# ── Correcte client krijgt een bruikbaar token ───────────────────────────────
def test_correcte_client_krijgt_token(client, registry):
    r = _token(client, CLIENT_A, SECRET_A)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "Bearer"
    assert body["access_token"]
    assert body["expires_in"] == 60 * 60, "clienttoken hoort 60 minuten te leven"


def test_token_draagt_client_en_minimale_rechten(client, registry):
    from jose import jwt

    from app.auth.security import ALGORITHM, SECRET_KEY

    tok = _token(client, CLIENT_A, SECRET_A).json()["access_token"]
    claims = jwt.decode(tok, SECRET_KEY, algorithms=[ALGORITHM])
    assert claims["client_id"] == CLIENT_A
    assert claims["typ"] == "client"
    assert claims["role"] == "ORG_USER", "clienttoken mag geen beheerdersrechten dragen"


def test_service_principal_heeft_geen_wachtwoord(client, registry):
    """De principal kan nergens inloggen: geen wachtwoord, laagste rol."""
    _token(client, CLIENT_A, SECRET_A)

    from app.auth.api_clients import load_clients as _load
    from app.database import SessionLocal
    from app.models.auth_models import User, UserRole

    email = _load()[CLIENT_A].service_principal_email
    db = SessionLocal()
    try:
        p = db.query(User).filter(User.email == email).first()
        assert p is not None
        assert p.password_hash is None
        assert p.role == UserRole.ORG_USER
    finally:
        db.close()


# ── Token werkt op de bedoelde externe routes ────────────────────────────────
def test_token_werkt_op_externe_routes(client, registry, auth):
    """Client A hoort de uitvragen van zijn eigen tenant te zien."""
    # maak via SSO een uitvraag in tenant 'platform' (dezelfde tenant als client A)
    profs = client.get("/api/profielen", headers=auth).json()
    key = profs[0]["key"]
    codes = [i["code"] for i in client.get(f"/api/profielen/{key}", headers=auth).json()["indicatoren"][:2]]
    za = client.get("/api/zorgaanbieders", headers=auth).json()
    linden = [z["id"] for z in za if z["naam"] == "Zorggroep De Linden"][0]
    client.post("/api/uitvragen", headers=auth,
                json={"profiel_key": key, "indicator_codes": codes, "zorgaanbieder_ids": [linden]})

    tok = _token(client, CLIENT_A, SECRET_A).json()["access_token"]
    XH = {"Authorization": f"Bearer {tok}"}

    v = client.get("/api/external/vragen?aanbiederIdType=kvk&aanbiederId=30112233", headers=XH)
    assert v.status_code == 200, v.text
    assert v.json()["aantal"] >= 1
    qid = v.json()["vragen"][0]["query_id"]

    r = client.get(f"/api/external/vraag/{qid}/resultaten", headers=XH)
    assert r.status_code == 200, r.text
    assert r.json()["aantal"] >= 1 and "waarde" in r.json()["resultaten"][0]


def test_tenantisolatie_client_b_ziet_niets_van_a(client, registry, auth):
    """Kern van de autorisatie: een client ziet uitsluitend zijn eigen tenant."""
    profs = client.get("/api/profielen", headers=auth).json()
    key = profs[0]["key"]
    codes = [i["code"] for i in client.get(f"/api/profielen/{key}", headers=auth).json()["indicatoren"][:1]]
    za = client.get("/api/zorgaanbieders", headers=auth).json()
    linden = [z["id"] for z in za if z["naam"] == "Zorggroep De Linden"][0]
    u = client.post("/api/uitvragen", headers=auth,
                    json={"profiel_key": key, "indicator_codes": codes,
                          "zorgaanbieder_ids": [linden]}).json()

    tok_b = _token(client, CLIENT_B, SECRET_B).json()["access_token"]
    XB = {"Authorization": f"Bearer {tok_b}"}

    v = client.get("/api/external/vragen?aanbiederIdType=kvk&aanbiederId=30112233", headers=XB)
    assert v.status_code == 200
    assert v.json()["aantal"] == 0, "client B ziet uitvragen van een andere tenant"

    r = client.get(f"/api/external/vraag/{u['id']}/resultaten", headers=XB)
    assert r.status_code == 404, "client B mag een vraag van tenant A niet kunnen opvragen"


def test_client_kan_tenant_niet_zelf_kiezen(client, registry):
    """Meegestuurde tenant-velden mogen de serverzijdige binding niet beïnvloeden."""
    from jose import jwt

    from app.auth.security import ALGORITHM, SECRET_KEY

    schoon = _token(client, CLIENT_B, SECRET_B).json()["access_token"]
    gepoogd = _token(client, CLIENT_B, SECRET_B,
                     tenant="platform", tenant_id="platform", scope="admin").json()["access_token"]
    a = jwt.decode(schoon, SECRET_KEY, algorithms=[ALGORITHM])
    b = jwt.decode(gepoogd, SECRET_KEY, algorithms=[ALGORITHM])
    assert a["tenant_id"] == b["tenant_id"]
    assert b["scope"] == "external"


# ── Rotatie met overlap ──────────────────────────────────────────────────────
def test_rotatie_beide_secrets_werken(client, monkeypatch):
    """Tijdens de overlap accepteert de server het oude én het nieuwe secret."""
    monkeypatch.setenv("KSAPI_CLIENTS", _registry(rotatie=True))
    assert _token(client, CLIENT_A, SECRET_A).status_code == 200
    assert _token(client, CLIENT_A, SECRET_A_NIEUW).status_code == 200


def test_na_rotatie_werkt_alleen_het_nieuwe_secret(client, monkeypatch):
    """Zodra 'next' is doorgeschoven, vervalt het oude secret."""
    entries = [{"client_id": CLIENT_A, "tenant": TENANT_A,
                "secret_hash": hash_secret(SECRET_A_NIEUW)}]
    monkeypatch.setenv("KSAPI_CLIENTS", base64.b64encode(json.dumps(entries).encode()).decode())
    assert _token(client, CLIENT_A, SECRET_A_NIEUW).status_code == 200
    assert _token(client, CLIENT_A, SECRET_A).status_code == 401


# ── Password-grant staat standaard uit ───────────────────────────────────────
def test_password_grant_standaard_geblokkeerd(client, registry):
    r = client.post("/api/external/token", data={
        "grant_type": "password", "username": "admin@rhadix.nl",
        "password": "Rhadixvoordezorg26!", "client_id": CLIENT_A, "client_secret": SECRET_A})
    assert r.status_code == 401, r.text
    assert "client_credentials" in r.json()["detail"]


def test_password_grant_vereist_ook_client_secret_indien_ingeschakeld(client, registry, monkeypatch):
    """Zelfs bewust ingeschakeld is de oude weg strenger dan voorheen."""
    monkeypatch.setenv("KSAPI_ALLOW_PASSWORD_GRANT", "1")
    r = client.post("/api/external/token", data={
        "grant_type": "password", "username": "admin@rhadix.nl",
        "password": "Rhadixvoordezorg26!", "client_id": CLIENT_A, "client_secret": "fout"})
    assert r.status_code == 401


def test_password_grant_werkt_alleen_bewust_ingeschakeld(client, registry, monkeypatch):
    monkeypatch.setenv("KSAPI_ALLOW_PASSWORD_GRANT", "1")
    r = client.post("/api/external/token", data={
        "grant_type": "password", "username": "admin@rhadix.nl",
        "password": "Rhadixvoordezorg26!", "client_id": CLIENT_A, "client_secret": SECRET_A})
    assert r.status_code == 200, r.text
