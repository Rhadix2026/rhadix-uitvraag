"""De startup-bootstrap raakt de users-tabel niet meer aan.

Tot de opruiming borgde `_seed_platform_admin` bij elke start een adminaccount en
herschreef het diens wachtwoord met een in de code gebakken waarde. Nu SSO/JIT de
enige authenticatieweg voor gebruikers is, en externe clients een eigen
service-principal hebben, heeft dat geen functie meer.

`init_db()` is precies wat bij startup draait; die opnieuw aanroepen simuleert een
herstart of deployment op dezelfde database.
"""
from app.bootstrap import _ensure_platform_tenant, init_db
from app.database import SessionLocal
from app.models.auth_models import Tenant, User, UserRole

from tests.conftest import SSO_ADMIN_EMAIL


def _users_count() -> int:
    db = SessionLocal()
    try:
        return db.query(User).count()
    finally:
        db.close()


def _get_user(email: str):
    db = SessionLocal()
    try:
        return db.query(User).filter(User.email == email).first()
    finally:
        db.close()


# ── Bootstrap maakt, wijzigt en verwijdert geen gebruikers ───────────────────
def test_bootstrap_maakt_geen_gebruikers_aan(client, auth):
    client.get("/api/auth/me", headers=auth)          # JIT-gebruiker aanmaken
    voor = _users_count()

    init_db()

    assert _users_count() == voor, "de bootstrap heeft accounts toegevoegd of verwijderd"


def test_bootstrap_seedt_geen_adminaccount():
    """Op een verse database ontstaat er geen adminaccount meer uit de code."""
    init_db()
    assert _get_user("admin@rhadix.nl") is None, \
        "de bootstrap seedt nog steeds een lokaal adminaccount"


def test_bootstrap_reset_geen_wachtwoorden(client, auth):
    """Een bestaande wachtwoord-hash blijft na een herstart ongewijzigd."""
    from app.auth.security import hash_password

    db = SessionLocal()
    try:
        u = User(email="met-wachtwoord@test.rhadix.nl", full_name="Met wachtwoord",
                 password_hash=hash_password("EenEigenWachtwoord1!"),
                 role=UserRole.ORG_ADMIN, is_active=True,
                 tenant_id=_ensure_platform_tenant())
        db.add(u)
        db.commit()
        hash_voor, rol_voor = u.password_hash, u.role
    finally:
        db.close()

    init_db()

    na = _get_user("met-wachtwoord@test.rhadix.nl")
    assert na is not None, "een bestaand account is verdwenen"
    assert na.password_hash == hash_voor, "de bootstrap heeft een wachtwoord gereset"
    assert na.role == rol_voor, "de bootstrap heeft een rol gewijzigd"


def test_jit_gebruiker_overleeft_herstart(client, auth):
    client.get("/api/auth/me", headers=auth)
    voor = _get_user(SSO_ADMIN_EMAIL)
    assert voor is not None
    user_id, tenant_id = voor.id, voor.tenant_id

    init_db()

    na = _get_user(SSO_ADMIN_EMAIL)
    assert na is not None, "JIT-gebruiker is bij de herstart verdwenen"
    assert na.id == user_id, "gebruiker is opnieuw aangemaakt i.p.v. behouden"
    assert na.tenant_id == tenant_id


def test_service_principal_overleeft_herstart(client):
    """Ook de machine-client houdt zijn principal over een herstart heen."""
    import base64
    import json

    import pytest as _pytest  # noqa: F401  (alleen voor duidelijkheid bij falen)
    from app.auth.api_clients import hash_secret, load_clients

    import os
    secret = "test-secret-herstart-0123456789"
    os.environ["KSAPI_CLIENTS"] = base64.b64encode(json.dumps([
        {"client_id": "herstart-client", "tenant": "herstart-tenant",
         "secret_hash": hash_secret(secret)}]).encode()).decode()
    try:
        r = client.post("/api/external/token", data={
            "grant_type": "client_credentials",
            "client_id": "herstart-client", "client_secret": secret})
        assert r.status_code == 200, r.text
        email = load_clients()["herstart-client"].service_principal_email
        voor = _get_user(email)
        assert voor is not None

        init_db()

        na = _get_user(email)
        assert na is not None, "service-principal is bij de herstart verdwenen"
        assert na.id == voor.id
        assert na.password_hash is None
    finally:
        os.environ.pop("KSAPI_CLIENTS", None)


# ── Tenant-bootstrap blijft wel werken ───────────────────────────────────────
def test_platform_tenant_wordt_geborgd_en_hergebruikt():
    tenant_id = _ensure_platform_tenant()
    assert tenant_id is not None

    init_db()

    db = SessionLocal()
    try:
        t = db.query(Tenant).filter(Tenant.slug == "platform").first()
        assert t is not None, "platform-tenant ontbreekt na de bootstrap"
        assert t.id == tenant_id, "platform-tenant is opnieuw aangemaakt i.p.v. hergebruikt"
    finally:
        db.close()


def test_demo_seed_blijft_werken(client, auth):
    """De demo-zorgaanbieders en capabilities blijven geladen worden."""
    za = client.get("/api/zorgaanbieders", headers=auth).json()
    assert len(za) > 0, "demo-zorgaanbieders zijn niet geladen"


# ── Broncodecontrole ─────────────────────────────────────────────────────────
def test_bootstrap_bevat_geen_wachtwoordlogica():
    import inspect as _inspect

    import app.bootstrap as bootstrap

    bron = _inspect.getsource(bootstrap)
    for term in ("hash_password", "KIK_ADMIN_PASSWORD", "RHADIX_ADMIN_PASSWORD", "AUTH_RESET"):
        regels = [r.strip() for r in bron.splitlines()
                  if term in r and not r.strip().startswith("#") and '"""' not in r]
        assert regels == [], f"{term} nog aanwezig in bootstrap: {regels}"
