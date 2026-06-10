"""bootstrap.py — tabellen aanmaken en een platform-admin seeden."""
from __future__ import annotations

import os
import uuid

from app.database import Base, SessionLocal, engine
from app.models.auth_models import Tenant, User, UserRole
from app.models import kik_models  # noqa: F401  (registreert KIK-tabellen)
from app.models.kik_models import Zorgaanbieder
from app.auth.security import hash_password


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _seed_platform_admin()
    _seed_demo_zorgaanbieders()


def _seed_platform_admin() -> None:
    """Maak (eenmalig) een platform-organisatie + platform-admin uit env-variabelen."""
    email = os.getenv("KIK_ADMIN_EMAIL", "admin@kik-starter.nl").lower().strip()
    password = os.getenv("KIK_ADMIN_PASSWORD", "KikStarter2026!")

    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == email).first():
            return  # al geseed

        tenant = db.query(Tenant).filter(Tenant.slug == "platform").first()
        if not tenant:
            tenant = Tenant(id=uuid.uuid4(), slug="platform", name="KIK-Starter Platform", is_active=True)
            db.add(tenant)
            db.flush()

        admin = User(
            id=uuid.uuid4(), tenant_id=tenant.id, email=email,
            full_name="Platformbeheerder", password_hash=hash_password(password),
            role=UserRole.PLATFORM_ADMIN, is_active=True,
        )
        db.add(admin)
        db.commit()
    finally:
        db.close()


def _seed_demo_zorgaanbieders() -> None:
    """Seed een paar demo-zorgaanbieders zodat de opvraag-flow direct te proberen is."""
    demo = [
        ("Zorggroep De Linden", "Utrecht", "info@delinden.nl"),
        ("Stichting Thuiszorg West", "Rotterdam", "contact@thuiszorgwest.nl"),
        ("Verpleeghuis Avondrood", "Groningen", "info@avondrood.nl"),
    ]
    db = SessionLocal()
    try:
        if db.query(Zorgaanbieder).count() > 0:
            return
        for naam, plaats, email in demo:
            db.add(Zorgaanbieder(id=uuid.uuid4(), naam=naam, plaats=plaats, contact_email=email))
        db.commit()
    finally:
        db.close()
