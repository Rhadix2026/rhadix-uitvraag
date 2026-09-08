"""bootstrap.py — tabellen aanmaken, de platform-tenant borgen en demo-data laden.

Gebruikers worden NIET meer geseed. Authenticatie verloopt via SSO: Rhadix
Datavalidatie geeft het centrale token uit en deze app provisioneert gebruikers
just-in-time. Externe machine-clients hebben een eigen service-principal via
client_credentials. Een lokaal adminaccount met een in de code gebakken wachtwoord
heeft daardoor geen functie meer.

Bestaande accounts blijven staan: deze module maakt, wijzigt en verwijdert geen
gebruikers.
"""
from __future__ import annotations

import logging
import os
import uuid

from sqlalchemy import inspect, text

from app.database import Base, SessionLocal, engine
from app.models.auth_models import Tenant
from app.models import kik_models  # noqa: F401  (registreert KIK-tabellen)
from app.models.kik_models import Zorgaanbieder, AanbiederCapability

log = logging.getLogger("rhadix.bootstrap")


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    _ensure_platform_tenant()
    _ensure_api_client_principals()
    _seed_demo_zorgaanbieders()
    _seed_capabilities()
    _seed_twin_capabilities()


def _ensure_api_client_principals() -> None:
    """Borg tenant + service-principal voor elke geregistreerde externe API-client.

    Idempotent en niet-destructief. Ontbreekt de registratie, dan gebeurt er niets:
    de externe tokenroute weigert dan zelf dienst (fail-closed).
    """
    from app.auth.api_clients import load_clients
    from app.auth.service_principals import ensure_service_principal

    clients = load_clients()
    if not clients:
        return
    db = SessionLocal()
    try:
        for client in clients.values():
            ensure_service_principal(db, client)
    except Exception:
        db.rollback()
        log.error("Borgen van API-client-principals mislukt", exc_info=True)
    finally:
        db.close()


def _ensure_columns() -> None:
    """Voeg ontbrekende kolommen toe aan bestaande tabellen (lichtgewicht migratie).

    create_all() maakt alleen nieuwe tabellen; bij een reeds bestaande database
    (bijv. staging) ontbreken nieuwe kolommen. Deze helper voegt ze defensief toe.
    """
    wanted = {
        "antwoorden": [("duur_ms", "INTEGER"), ("query_id", "VARCHAR(64)"), ("datastation_url", "VARCHAR(512)")],
        "uitvragen":  [("doorlooptijd_ms", "INTEGER")],
        "zorgaanbieders": [
            ("heeft_credential", "VARCHAR(8)"), ("straatnaam", "VARCHAR(255)"),
            ("huisnummer", "VARCHAR(32)"), ("postcode", "VARCHAR(16)"),
            ("gemeente", "VARCHAR(128)"), ("samenwerkingsverband", "VARCHAR(255)"),
            ("doelgroepen", "TEXT"), ("sectoren", "TEXT"), ("zorgkantoren", "TEXT"),
            ("concessiehouders", "TEXT"), ("contact_voornaam", "VARCHAR(128)"),
            ("contact_achternaam", "VARCHAR(128)"), ("contact_telefoon", "VARCHAR(64)"),
            ("contact_functie", "VARCHAR(255)"), ("fte", "FLOAT"),
            ("locaties", "INTEGER"), ("bedden", "INTEGER"),
            ("daas_leverancier", "VARCHAR(255)"), ("implementatie_consultant", "VARCHAR(255)"),
            ("zelfscan_retour", "VARCHAR(255)"), ("intentieverklaring", "VARCHAR(255)"),
            ("contract_datastation", "VARCHAR(255)"), ("aangesloten_test", "VARCHAR(255)"),
            ("aangesloten_productie", "VARCHAR(255)"), ("huidige_fase", "VARCHAR(64)"),
            ("vestigingen", "TEXT"), ("implementatiepartner", "VARCHAR(255)"),
            ("uitwisselprofielen", "TEXT"),
        ],
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

    # Nieuwe enum-waarden (Postgres) — async-statussen
    if engine.dialect.name == "postgresql":
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            for typ, val in [("antwoordstatus", "UITGEZET"), ("antwoordstatus", "AFGEWEZEN"),
                             ("uitvraagstatus", "LOPEND")]:
                try:
                    conn.execute(text(f"ALTER TYPE {typ} ADD VALUE IF NOT EXISTS '{val}'"))
                except Exception:
                    pass

    # Verbreed bestaande kolommen (alleen Postgres dwingt lengte af; SQLite negeert dit)
    if engine.dialect.name == "postgresql":
        widen = [
            ("uitvragen", "profiel_key", "VARCHAR(255)"),
            ("uitvragen", "profiel_label", "VARCHAR(512)"),
            ("antwoorden", "indicator_label", "VARCHAR(512)"),
            ("aanbieder_capabilities", "uitwisselprofiel", "VARCHAR(255)"),
        ]
        with engine.begin() as conn:
            for table, col, typ in widen:
                if insp.has_table(table):
                    try:
                        conn.execute(text(f"ALTER TABLE {table} ALTER COLUMN {col} TYPE {typ}"))
                    except Exception:
                        pass


def _ensure_platform_tenant() -> uuid.UUID:
    """Borg de platform-tenant.

    Functioneel nodig als thuisbasis binnen deze applicatie. Volledig losgekoppeld
    van gebruikersaccounts: deze functie raakt de users-tabel niet aan. Gebruikers
    ontstaan uitsluitend via SSO/JIT-provisioning; machine-clients krijgen hun
    eigen service-principal (zie auth/service_principals.py).
    """
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.slug == "platform").first()
        if not tenant:
            tenant = Tenant(id=uuid.uuid4(), slug="platform", name="Rhadix Platform", is_active=True)
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
        return tenant.id
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
        if db.query(Zorgaanbieder).count() == 0:
            for naam, plaats, email in demo:
                db.add(Zorgaanbieder(id=uuid.uuid4(), naam=naam, plaats=plaats, contact_email=email))
        # Twin-aanbieder met echt datastation (idempotent — ook op bestaande DB)
        twin_naam = "Twin Zorgaanbieder (datastation)"
        twin = db.query(Zorgaanbieder).filter(Zorgaanbieder.naam == twin_naam).first()
        twin_url = os.getenv("TWIN_DATASTATION_URL", "http://host.docker.internal:8017")
        if not twin:
            db.add(Zorgaanbieder(id=uuid.uuid4(), naam=twin_naam, plaats="Demo",
                                 contact_email="twin@rhadix.nl", datastation_url=twin_url))
        else:
            twin.datastation_url = twin_url
        db.commit()
    finally:
        db.close()


def _seed_capabilities() -> None:
    """Seed de uitwisselprofiel-registry profiel-bewust (matcht de geladen bron)."""
    from app.services import profiles as profiles_svc
    from app.routers.capabilities import apply_import
    db = SessionLocal()
    try:
        profs = profiles_svc.list_profiles()
        if not profs:
            return
        keys = {p["key"] for p in profs}
        bestaand = db.query(AanbiederCapability).all()
        if bestaand:
            # Laat handmatige/actuele registry staan zolang die matcht met de bron.
            if any(c.uitwisselprofiel in keys for c in bestaand):
                return
            # Bron is gewijzigd (andere sleutels) → demo-registry opnieuw seeden.
            db.query(AanbiederCapability).delete()
            db.commit()
        providers = [("Zorggroep De Linden", "30112233", "Nedap"),
                     ("Stichting Thuiszorg West", "44556677", "PinkRoccade"),
                     ("Verpleeghuis Avondrood", "55667788", "Ecare")]
        statuses = ["productie", "productie", "productie", "test", "implementatie"]
        n = len(profs)
        rows = []
        for pi, (naam, kvk, lev) in enumerate(providers):
            for j in range(min(4, n)):
                prof = profs[(pi * 2 + j) % n]
                rows.append({
                    "aanbieder_id_type": "kvk", "aanbieder_id": kvk, "aanbieder_naam": naam,
                    "software_leverancier": lev, "uitwisselprofiel": prof["key"],
                    "versie": prof.get("versie") or "1.0", "status": statuses[j % len(statuses)],
                    "laatst_bijgewerkt": "2026-02-01"})
        if rows:
            apply_import(db, rows)
    finally:
        db.close()


def _seed_twin_capabilities() -> None:
    """Twin-aanbieder krijgt voor elk geladen profiel een productie-capability (idempotent, altijd)."""
    from app.services import profiles as profiles_svc
    from app.models.kik_models import AanbiederCapability, CapabilityStatus
    profs = profiles_svc.list_profiles()
    if not profs:
        return
    db = SessionLocal()
    try:
        twin = "Twin Zorgaanbieder (datastation)"
        have = {c.uitwisselprofiel for c in db.query(AanbiederCapability).filter(AanbiederCapability.aanbieder_naam == twin).all()}
        added = 0
        for prof in profs:
            if prof["key"] in have:
                continue
            db.add(AanbiederCapability(
                id=uuid.uuid4(), aanbieder_id_type="kvk", aanbieder_id="99887766", aanbieder_naam=twin,
                software_leverancier="Rhadix", uitwisselprofiel=prof["key"], versie=prof.get("versie") or "1.0",
                status=CapabilityStatus.PRODUCTIE, laatst_bijgewerkt="2026-02-01"))
            added += 1
        if added:
            db.commit()
    finally:
        db.close()
