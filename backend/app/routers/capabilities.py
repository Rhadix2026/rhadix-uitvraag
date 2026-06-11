"""
capabilities.py — Registry van geïmplementeerde uitwisselprofielen per aanbieder.

- Import (CSV, full refresh) door de platformbeheerder.
- Overzicht (per profiel / per aanbieder) voor ketenpartijen.
- Per-profiel aanbieders, voor filtering in de Opvragen-flow.
"""
from __future__ import annotations

import uuid
from collections import Counter, defaultdict

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_role
from app.database import get_db
from app.models.auth_models import User, UserRole
from app.models.kik_models import AanbiederCapability, CapabilityStatus, Zorgaanbieder
from app.services import capabilities as caps_svc
from app.services import profiles as profiles_svc

router = APIRouter(tags=["capabilities"])
_platform_admin = require_role(UserRole.PLATFORM_ADMIN)


def _profiel_label(key: str) -> str:
    p = profiles_svc.get_profile(key)
    return p["label"] if p else key


def apply_import(db: Session, records: list) -> int:
    """Full refresh: bestaande registry vervangen door de nieuwe records."""
    db.query(AanbiederCapability).delete()
    for r in records:
        db.add(AanbiederCapability(
            id=uuid.uuid4(), aanbieder_id_type=r["aanbieder_id_type"],
            aanbieder_id=r["aanbieder_id"], aanbieder_naam=r["aanbieder_naam"],
            software_leverancier=r["software_leverancier"], uitwisselprofiel=r["uitwisselprofiel"],
            versie=r["versie"], status=CapabilityStatus(r["status"]),
            laatst_bijgewerkt=r["laatst_bijgewerkt"]))
    db.commit()
    return len(records)


@router.post("/capabilities/import")
async def import_csv(file: UploadFile = File(...), db: Session = Depends(get_db),
                     current: User = Depends(_platform_admin)):
    """Lees een CSV in (full refresh). Alleen platformbeheerder."""
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "Bestand is geen geldige UTF-8 CSV")
    try:
        records, samenvatting = caps_svc.parse_csv(text)
    except caps_svc.CsvFormatError as exc:
        raise HTTPException(422, f"Formaatfout — bestand afgekeurd: {exc}")
    apply_import(db, records)
    samenvatting["actief"] = len(records)
    return samenvatting


def _za_index(db: Session) -> dict:
    """naam → zorgaanbieder-id, voor het koppelen van capabilities aan registratie."""
    return {z.naam: str(z.id) for z in db.query(Zorgaanbieder).all()}


@router.get("/capabilities/profiel/{key}")
def aanbieders_voor_profiel(key: str, inclusief_niet_productie: bool = False,
                            db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """Aanbieders die dit uitwisselprofiel ondersteunen (standaard alleen productie)."""
    q = db.query(AanbiederCapability).filter(AanbiederCapability.uitwisselprofiel == key)
    if not inclusief_niet_productie:
        q = q.filter(AanbiederCapability.status == CapabilityStatus.PRODUCTIE)
    idx = _za_index(db)
    rows = q.order_by(AanbiederCapability.aanbieder_naam).all()
    return {
        "profiel_key": key, "profiel_label": _profiel_label(key),
        "aanbieders": [{
            "zorgaanbieder_id": idx.get(c.aanbieder_naam),
            "aanbieder_naam": c.aanbieder_naam, "versie": c.versie,
            "status": c.status.value, "software_leverancier": c.software_leverancier,
            "geregistreerd": c.aanbieder_naam in idx,
        } for c in rows],
    }


@router.get("/capabilities/overzicht")
def overzicht(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """Inzichtsscherm: per profiel en per aanbieder, plus statustelling."""
    caps = db.query(AanbiederCapability).all()
    idx = _za_index(db)

    per_profiel = defaultdict(list)
    per_aanbieder = defaultdict(lambda: {"software_leverancier": None, "profielen": []})
    status_telling = Counter()
    for c in caps:
        status_telling[c.status.value] += 1
        per_profiel[c.uitwisselprofiel].append(
            {"aanbieder_naam": c.aanbieder_naam, "versie": c.versie, "status": c.status.value,
             "geregistreerd": c.aanbieder_naam in idx})
        d = per_aanbieder[c.aanbieder_naam]
        d["software_leverancier"] = c.software_leverancier
        d["profielen"].append({"profiel_key": c.uitwisselprofiel, "profiel_label": _profiel_label(c.uitwisselprofiel),
                               "versie": c.versie, "status": c.status.value})

    return {
        "totaal": len(caps),
        "status_telling": dict(status_telling),
        "per_profiel": sorted(
            [{"profiel_key": k, "profiel_label": _profiel_label(k),
              "aanbieders": sorted(v, key=lambda x: x["aanbieder_naam"])}
             for k, v in per_profiel.items()],
            key=lambda x: x["profiel_label"]),
        "per_aanbieder": sorted(
            [{"aanbieder_naam": k, "software_leverancier": v["software_leverancier"],
              "geregistreerd": k in idx, "profielen": sorted(v["profielen"], key=lambda x: x["profiel_label"])}
             for k, v in per_aanbieder.items()],
            key=lambda x: x["aanbieder_naam"]),
    }
