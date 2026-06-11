"""bootstrap.py — tabellen aanmaken en een platform-admin seeden."""
from __future__ import annotations

import os
import uuid

from sqlalchemy import inspect, text

from app.database import Base, SessionLocal, engine
from app.models.auth_models import Tenant, User, UserRole
from app.models import kik_models  # noqa: F401  (registreert KIK-tabellen)
from app.models.kik_models import Zorgaanbieder, AanbiederCapability
from app.auth.security import hash_password


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    _seed_platform_admin()
    _seed_demo_zorgaanbieders()
    _seed_capabilities()


def _ensure_columns() -> None:
    """Voeg ontbrekende kolommen toe aan bestaande tabellen (lichtgewicht migratie).

    create_all() maakt alleen nieuwe tabellen; bij een reeds bestaande database
    (bijv. staging) ontbreken nieuwe kolommen. Deze helper voegt ze defensief toe.
    """
    wanted = {
        "antwoorden": [("duur_ms", "INTEGER")],
        "uitvragen":  [("doorlooptijd_ms", "INTEGER")],
    }
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in wanted.items():
            if not insp.has_table(table):
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols:
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


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
            tenant = Tenant(id=uuid.uuid4(), slug="platform", name="Rhadix Uitvraag Platform", is_active=True)
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


def _seed_capabilities() -> None:
    """Seed de uitwisselprofiel-registry uit de demo-CSV (eenmalig)."""
    from app.services import capabilities as caps_svc
    from app.routers.capabilities import apply_import
    db = SessionLocal()
    try:
        if db.query(AanbiederCapability).count() > 0:
            return
        records, _ = caps_svc.parse_csv(caps_svc.SEED_CSV)
        apply_import(db, records)
    finally:
        db.close()
