"""Applicatietoegang op basis van de centrale apps-claim (Uitvraag).

De claim is de enige bron voor menselijke applicatietoegang. Geen rol-bypass:
een PLATFORM_ADMIN komt binnen doordat het platform alle toegewezen slugs in zijn
claim zet, niet doordat deze app de rol interpreteert.

Deze matrix dekt beide wegen waarlangs een slug in de claim belandt — een
organisatiebrede toewijzing (TenantApplication) en een persoonlijke toewijzing
(UserApplication) — plus de standen warn en on, en de scheiding met
machine-to-machine tokens.
"""
import pytest
from jose import jwt

from app.auth.app_access import APP_SLUG, beoordeel_toegang, enforce_mode

from tests._testkeys import PRIV, central_token

# Een menselijke, beschermde route.
BESCHERMD = "/api/profielen"


def _tok(**overrides) -> str:
    claims = {
        "sub": "aaaaaaaa-0000-0000-0000-000000000001",
        "email": "matrix-gebruiker@test.rhadix.nl",
        "role": "ORG_USER",
        "tenant_name": "Matrix Tenant",
        "apps": [APP_SLUG],
    }
    claims.update(overrides)
    # None-waarden betekenen: claim helemaal weglaten
    claims = {k: v for k, v in claims.items() if v is not None}
    return central_token(claims)


def _H(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── 1-2. Gebruiker mét en zonder toewijzing ─────────────────────────────────
def test_1_gebruiker_met_app_toewijzing(client):
    """Toewijzing via de organisatie (TenantApplication) levert de slug in de claim."""
    t = _tok(email="org-toegewezen@test.rhadix.nl", apps=["datavalidatie", APP_SLUG])
    assert client.get(BESCHERMD, headers=_H(t)).status_code == 200


def test_1b_persoonlijke_toewijzing(client):
    """Toewijzing op gebruikersniveau (UserApplication) levert dezelfde claim op.

    Het platform verenigt TenantApplication en UserApplication tot één apps-claim;
    voor deze app is het onderscheid niet zichtbaar en dus ook niet relevant —
    beide wegen leiden tot dezelfde beoordeling. Dat legt deze test vast.
    """
    t = _tok(email="persoonlijk-toegewezen@test.rhadix.nl", apps=[APP_SLUG])
    assert client.get(BESCHERMD, headers=_H(t)).status_code == 200


def test_2_gebruiker_zonder_app_toewijzing_warn(client, monkeypatch):
    """Zonder toewijzing: in warn nog toegang, maar wel als weigering beoordeeld."""
    monkeypatch.setenv("APP_ACCESS_ENFORCE", "warn")
    t = _tok(email="niet-toegewezen@test.rhadix.nl", apps=["datavalidatie", "rhadix-crm"])
    assert client.get(BESCHERMD, headers=_H(t)).status_code == 200


def test_2b_gebruiker_zonder_app_toewijzing_enforce(client, monkeypatch):
    monkeypatch.setenv("APP_ACCESS_ENFORCE", "on")
    t = _tok(email="niet-toegewezen2@test.rhadix.nl", apps=["datavalidatie"])
    r = client.get(BESCHERMD, headers=_H(t))
    assert r.status_code == 403, r.text
    assert APP_SLUG in r.json()["detail"]


# ── 3-4. Ontbrekende, lege en gemanipuleerde claim ──────────────────────────
@pytest.mark.parametrize("apps,omschrijving", [(None, "ontbreekt"), ([], "leeg")])
def test_3_claim_ontbreekt_of_leeg_warn(client, monkeypatch, apps, omschrijving):
    monkeypatch.setenv("APP_ACCESS_ENFORCE", "warn")
    t = _tok(email=f"claim-{omschrijving}@test.rhadix.nl", apps=apps)
    assert client.get(BESCHERMD, headers=_H(t)).status_code == 200


@pytest.mark.parametrize("apps,omschrijving", [(None, "ontbreekt"), ([], "leeg")])
def test_3b_claim_ontbreekt_of_leeg_enforce(client, monkeypatch, apps, omschrijving):
    monkeypatch.setenv("APP_ACCESS_ENFORCE", "on")
    t = _tok(email=f"claim2-{omschrijving}@test.rhadix.nl", apps=apps)
    assert client.get(BESCHERMD, headers=_H(t)).status_code == 403


def test_4_gemanipuleerde_handtekening_blijft_401(client, monkeypatch):
    """Sleutelen aan de claim breekt de handtekening: 401, nog vóór de app-check."""
    monkeypatch.setenv("APP_ACCESS_ENFORCE", "warn")
    geldig = _tok(apps=["datavalidatie"])
    kop, body, sig = geldig.split(".")
    import base64
    import json
    p = body + "=" * (-len(body) % 4)
    claims = json.loads(base64.urlsafe_b64decode(p))
    claims["apps"] = [APP_SLUG]                       # rechten erbij verzinnen
    nieuw_body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    geknoeid = f"{kop}.{nieuw_body}.{sig}"
    assert client.get(BESCHERMD, headers=_H(geknoeid)).status_code == 401


def test_4b_eigen_sleutel_wordt_geweigerd(client):
    """Een token dat met een andere sleutel is ondertekend, wordt niet vertrouwd."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    eigen = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = eigen.private_bytes(serialization.Encoding.PEM,
                              serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption()).decode()
    vals = jwt.encode({"sub": "x", "email": "vals@test.rhadix.nl", "role": "PLATFORM_ADMIN",
                       "apps": [APP_SLUG], "iss": "suresync-id"}, pem, algorithm="RS256")
    assert client.get(BESCHERMD, headers=_H(vals)).status_code == 401


def test_4c_verkeerde_issuer_wordt_geweigerd(client):
    vals = jwt.encode({"sub": "x", "email": "issuer@test.rhadix.nl", "role": "ORG_USER",
                       "apps": [APP_SLUG], "iss": "iemand-anders"}, PRIV, algorithm="RS256")
    assert client.get(BESCHERMD, headers=_H(vals)).status_code == 401


# ── 5. PLATFORM_ADMIN: claim-only, geen rol-bypass ──────────────────────────
def test_5_platform_admin_met_slug(client, monkeypatch):
    monkeypatch.setenv("APP_ACCESS_ENFORCE", "on")
    t = _tok(email="pa-met@test.rhadix.nl", role="RHADIX_ADMIN",
             apps=["datavalidatie", "uitvraag", APP_SLUG, "rhadix-crm"])
    assert client.get(BESCHERMD, headers=_H(t)).status_code == 200


def test_5b_platform_admin_zonder_slug_krijgt_403(client, monkeypatch):
    """Kern van claim-only: de rol geeft géén toegang, de claim wel."""
    monkeypatch.setenv("APP_ACCESS_ENFORCE", "on")
    t = _tok(email="pa-zonder@test.rhadix.nl", role="RHADIX_ADMIN", apps=["datavalidatie"])
    assert client.get(BESCHERMD, headers=_H(t)).status_code == 403


# ── 6. JIT-gebruiker ────────────────────────────────────────────────────────
def test_6_jit_gebruiker_met_toewijzing(client, monkeypatch):
    monkeypatch.setenv("APP_ACCESS_ENFORCE", "on")
    t = _tok(email="jit-nieuw@test.rhadix.nl", apps=[APP_SLUG])
    assert client.get(BESCHERMD, headers=_H(t)).status_code == 200

    from app.database import SessionLocal
    from app.models.auth_models import User
    db = SessionLocal()
    try:
        assert db.query(User).filter(User.email == "jit-nieuw@test.rhadix.nl").first() is not None
    finally:
        db.close()


# ── 7. Machine-to-machine blijft gescheiden ─────────────────────────────────
def test_7_machine_token_op_menselijke_route_geweigerd(client, monkeypatch):
    """Een client_credentials-token hoort niet op menselijke routes."""
    monkeypatch.setenv("APP_ACCESS_ENFORCE", "on")
    t = _tok(email="machine@test.rhadix.nl", typ="client", scope="external", apps=None)
    assert client.get(BESCHERMD, headers=_H(t)).status_code == 403


def test_7b_machine_token_valt_niet_onder_de_apps_claim():
    """Beoordeling gebeurt op typ/scope, niet op de apps-claim."""
    class _P:
        email = "machine@test"
        _token_source = "central"
        _token_typ = "client"
        _token_scope = "external"
        _apps = ["datastation"]           # zou menselijk gezien voldoende zijn
    toegestaan, reden = beoordeel_toegang(_P())
    assert toegestaan is False
    assert "machine-token" in reden


# ── 8. Directe API-aanroep buiten de portal om ──────────────────────────────
def test_8_directe_aanroep_zonder_toewijzing_enforce(client, monkeypatch):
    """Het portaal is geen securitygrens: de app beslist zelf."""
    monkeypatch.setenv("APP_ACCESS_ENFORCE", "on")
    t = _tok(email="direct@test.rhadix.nl", apps=["datavalidatie"])
    for route in (BESCHERMD, "/api/zorgaanbieders", "/api/uitvragen"):
        assert client.get(route, headers=_H(t)).status_code == 403, route


def test_8b_directe_aanroep_via_cookie_ook_gegate(client, monkeypatch):
    monkeypatch.setenv("APP_ACCESS_ENFORCE", "on")
    t = _tok(email="cookie-direct@test.rhadix.nl", apps=["datavalidatie"])
    assert client.get(BESCHERMD, cookies={"rhadix_sso": t}).status_code == 403


# ── 9. Publieke en server-to-server routes blijven ongewijzigd ──────────────
def test_9_publieke_routes_ongewijzigd(client, monkeypatch):
    monkeypatch.setenv("APP_ACCESS_ENFORCE", "on")
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/meta").status_code == 200


def test_9b_beschermde_route_zonder_token_blijft_401(client, monkeypatch):
    monkeypatch.setenv("APP_ACCESS_ENFORCE", "on")
    assert client.get(BESCHERMD).status_code == 401


def test_9c_auth_me_blijft_bereikbaar_zonder_toewijzing(client, monkeypatch):
    """Zo kan de frontend een verklarende melding tonen i.p.v. een blinde lus."""
    monkeypatch.setenv("APP_ACCESS_ENFORCE", "on")
    t = _tok(email="me-zonder@test.rhadix.nl", apps=["datavalidatie"])
    assert client.get("/api/auth/me", headers=_H(t)).status_code == 200


# ── 10. Standen van de schakelaar ───────────────────────────────────────────
def test_10_stand_off_laat_alles_door(client, monkeypatch):
    monkeypatch.setenv("APP_ACCESS_ENFORCE", "off")
    t = _tok(email="uit@test.rhadix.nl", apps=[])
    assert client.get(BESCHERMD, headers=_H(t)).status_code == 200


@pytest.mark.parametrize("waarde,verwacht", [
    ("on", "on"), ("warn", "warn"), ("off", "off"),
    ("", "warn"), ("onzin", "warn"), ("ON", "on"),
])
def test_10b_onbekende_stand_valt_terug_op_warn(monkeypatch, waarde, verwacht):
    monkeypatch.setenv("APP_ACCESS_ENFORCE", waarde)
    assert enforce_mode() == verwacht


def test_10c_default_is_warn(monkeypatch):
    monkeypatch.delenv("APP_ACCESS_ENFORCE", raising=False)
    assert enforce_mode() == "warn"


# ── 11. Machine-to-machine blijft volledig gescheiden ───────────────────────
# De externe API is bewust NIET aan require_app_access gekoppeld. Deze tests
# bewijzen dat de client_credentials-flow ongewijzigd werkt, óók met de
# app-autorisatie op 'on', en dat een machine-token niet op menselijke routes komt.
import base64 as _b64
import json as _json

_M_SECRET = "test-secret-appaccess-machine-01"
_M_CLIENT = "appaccess-machineclient"


def _machine_registry(monkeypatch):
    from app.auth.api_clients import hash_secret
    monkeypatch.setenv("KSAPI_CLIENTS", _b64.b64encode(_json.dumps([{
        "client_id": _M_CLIENT, "naam": "Machineclient", "tenant": "platform",
        "secret_hash": hash_secret(_M_SECRET)}]).encode()).decode())


def test_11_client_credentials_werkt_met_app_access_on(client, monkeypatch):
    """De machinekoppeling blijft werken, ongeacht de stand van de app-check."""
    monkeypatch.setenv("APP_ACCESS_ENFORCE", "on")
    _machine_registry(monkeypatch)
    r = client.post("/api/external/token", data={
        "grant_type": "client_credentials", "client_id": _M_CLIENT,
        "client_secret": _M_SECRET})
    assert r.status_code == 200, r.text
    assert r.json()["scope"] == "external"


def test_11b_machine_token_werkt_op_externe_routes(client, monkeypatch):
    monkeypatch.setenv("APP_ACCESS_ENFORCE", "on")
    _machine_registry(monkeypatch)
    tok = client.post("/api/external/token", data={
        "grant_type": "client_credentials", "client_id": _M_CLIENT,
        "client_secret": _M_SECRET}).json()["access_token"]
    r = client.get("/api/external/vragen?aanbiederIdType=kvk&aanbiederId=30112233",
                   headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text


def test_11c_machine_token_niet_op_menselijke_routes(client, monkeypatch):
    """Het scheidingsvlak: hetzelfde token wordt op /api/profielen geweigerd."""
    monkeypatch.setenv("APP_ACCESS_ENFORCE", "on")
    _machine_registry(monkeypatch)
    tok = client.post("/api/external/token", data={
        "grant_type": "client_credentials", "client_id": _M_CLIENT,
        "client_secret": _M_SECRET}).json()["access_token"]
    r = client.get(BESCHERMD, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403, r.text


def test_11d_externe_routes_zijn_niet_gegate_door_apps_claim(client, monkeypatch):
    """Een machine-token heeft geen apps-claim; dat mag de externe API niet raken."""
    monkeypatch.setenv("APP_ACCESS_ENFORCE", "on")
    _machine_registry(monkeypatch)
    tok = client.post("/api/external/token", data={
        "grant_type": "client_credentials", "client_id": _M_CLIENT,
        "client_secret": _M_SECRET}).json()["access_token"]
    from jose import jwt as _jwt
    from app.auth.security import ALGORITHM, SECRET_KEY
    claims = _jwt.decode(tok, SECRET_KEY, algorithms=[ALGORITHM])
    assert "apps" not in claims
    assert claims["typ"] == "client" and claims["scope"] == "external"
