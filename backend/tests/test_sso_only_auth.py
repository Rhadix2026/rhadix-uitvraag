"""SSO is de enige authenticatieweg voor gebruikers (Uitvraag).

Bewijst twee dingen end-to-end:
  1. toegang met een geldig centraal RS256-token werkt, inclusief JIT-provisioning,
     zónder dat er ergens een wachtwoord aan te pas komt;
  2. de lokale wachtwoord-routes voor gebruikers zijn dicht.

Buiten scope van deze tests: de OAuth2 password-grant in routers/external.py.
Die bedient externe afnemers volgens de KIK-Starter-aansluitspecificatie en wordt
apart behandeld; test_flow.py dekt die route.
"""
import pytest

from tests._testkeys import central_token
from tests.conftest import SSO_ADMIN_EMAIL, SSO_TENANT_NAME


# ── 1. SSO / JIT werkt zonder lokale wachtwoord-authenticatie ────────────────
def test_sso_token_geeft_toegang(client, auth):
    r = client.get("/api/auth/me", headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["email"] == SSO_ADMIN_EMAIL


def test_jit_provisioning_maakt_gebruiker_zonder_wachtwoord(client, auth):
    """De JIT-gebruiker bestaat, is platformbeheerder en heeft géén wachtwoord-hash."""
    client.get("/api/auth/me", headers=auth)  # triggert provisioning

    from app.database import SessionLocal
    from app.models.auth_models import User, UserRole

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == SSO_ADMIN_EMAIL).first()
        assert user is not None, "JIT-provisioning heeft geen gebruiker aangemaakt"
        assert user.password_hash is None, "SSO-gebruiker hoort geen wachtwoord te hebben"
        assert user.role == UserRole.PLATFORM_ADMIN
        assert user.is_active is True
    finally:
        db.close()


def test_sso_token_werkt_ook_via_cookie(client):
    """Cross-app SSO loopt via het rhadix_sso-cookie i.p.v. de Authorization-header."""
    token = central_token({
        "sub": "22222222-2222-2222-2222-222222222222",
        "email": "cookie-gebruiker@test.rhadix.nl",
        "role": "ORG_USER",
        "tenant_name": SSO_TENANT_NAME,
    })
    r = client.get("/api/auth/me", cookies={"rhadix_sso": token})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "cookie-gebruiker@test.rhadix.nl"


def test_beschermd_endpoint_werkt_met_sso(client, auth):
    """Een echte, beschermde route werkt met SSO — niet alleen /auth/me."""
    assert client.get("/api/profielen", headers=auth).status_code == 200


def test_bestaande_bootstrap_gebruiker_blijft_bestaan(client, auth):
    """Het afsluiten van login verwijdert geen accounts: de beheerder staat er nog."""
    from app.database import SessionLocal
    from app.models.auth_models import User

    db = SessionLocal()
    try:
        assert db.query(User).filter(User.email == "admin@rhadix.nl").first() is not None
    finally:
        db.close()


def test_zonder_token_geen_toegang(client):
    assert client.get("/api/auth/me").status_code == 401


# ── 2. Lokale wachtwoord-login is afgesloten ─────────────────────────────────
def test_login_endpoint_geblokkeerd_met_juiste_gegevens(client):
    """Zelfs met de bootstrap-gegevens geeft /auth/login geen token meer."""
    r = client.post("/api/auth/login",
                    json={"email": "admin@rhadix.nl", "password": "Rhadixvoordezorg26!"})
    assert r.status_code == 403, r.text
    assert "access_token" not in r.json()


def test_login_endpoint_geblokkeerd_bij_onjuiste_gegevens(client):
    r = client.post("/api/auth/login", json={"email": "admin@rhadix.nl", "password": "fout"})
    assert r.status_code == 403


def test_wachtwoord_wijzigen_geblokkeerd(client, auth):
    r = client.patch("/api/auth/me/password", headers=auth,
                     json={"current_password": "Rhadixvoordezorg26!",
                           "new_password": "NieuwWachtwoord1!"})
    assert r.status_code == 403, r.text


def test_vlag_kan_lokale_login_heropenen(client, monkeypatch):
    """Omkeerbaarheid: met LOCAL_LOGIN_ENABLED=1 werkt de route weer.

    Bewijst dat de afsluiting een schakelaar is en geen eenrichtingsverwijdering,
    zodat herstel geen release vereist.
    """
    monkeypatch.setenv("LOCAL_LOGIN_ENABLED", "1")
    r = client.post("/api/auth/login", json={"email": "admin@rhadix.nl", "password": "fout"})
    assert r.status_code == 401, "route hoort weer bereikbaar te zijn (401 = wachtwoord fout)"


@pytest.mark.parametrize("waarde", ["0", "false", "no", "", "onzin"])
def test_vlag_staat_standaard_en_bij_onbekende_waarden_uit(client, monkeypatch, waarde):
    monkeypatch.setenv("LOCAL_LOGIN_ENABLED", waarde)
    assert client.post("/api/auth/login",
                       json={"email": "admin@rhadix.nl", "password": "x"}).status_code == 403


# ── 3. Vastleggen dat de externe API bewust nog openstaat ────────────────────
def test_externe_password_grant_is_bewust_nog_open(client):
    """Regressiebescherming: legt het huidige gedrag vast, inclusief de opening.

    /external/token accepteert nog steeds een wachtwoord. Dat is een bewuste keuze
    (externe afnemers), geen vergissing — maar het betekent dat de SSO-keten via
    deze route nog te omzeilen is. Zodra dat wordt aangepakt hoort deze test mee
    te veranderen.
    """
    r = client.post("/api/external/token", data={
        "grant_type": "password", "username": "admin@rhadix.nl",
        "password": "Rhadixvoordezorg26!", "client_id": "ksapi"})
    assert r.status_code == 200, "externe password-grant is (nog) bewust open"
