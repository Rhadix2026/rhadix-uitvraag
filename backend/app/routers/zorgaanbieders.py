"""
zorgaanbieders.py — Zelfregistratie en overzicht van zorgaanbieders.

Registratie is *publiek* (een zorgaanbieder meldt zich aan om uitvragen te kunnen
ontvangen). Het overzicht is voor ingelogde ketenpartijen, die hieruit kiezen.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.auth_models import User
from app.models.kik_models import Zorgaanbieder

router = APIRouter(tags=["zorgaanbieders"])


def _dict(z: Zorgaanbieder) -> dict:
    return {"id": str(z.id), "naam": z.naam, "kvk": z.kvk, "plaats": z.plaats,
            "contact_email": z.contact_email,
            "heeft_datastation": bool(z.datastation_url),
            "created_at": z.created_at.isoformat() if z.created_at else None}


class RegisterZorgaanbieder(BaseModel):
    naam: str
    kvk: Optional[str] = None
    plaats: Optional[str] = None
    contact_email: Optional[str] = None
    datastation_url: Optional[str] = None   # leeg = gesimuleerd datastation


@router.post("/zorgaanbieders/register", status_code=201)
def register(body: RegisterZorgaanbieder, db: Session = Depends(get_db)):
    """Publieke zelfregistratie van een zorgaanbieder."""
    naam = body.naam.strip()
    if not naam:
        raise HTTPException(422, "Naam is verplicht")
    if db.query(Zorgaanbieder).filter(Zorgaanbieder.naam == naam).first():
        raise HTTPException(400, f"Zorgaanbieder '{naam}' is al geregistreerd")
    z = Zorgaanbieder(id=uuid.uuid4(), naam=naam, kvk=body.kvk, plaats=body.plaats,
                      contact_email=body.contact_email,
                      datastation_url=(body.datastation_url or None))
    db.add(z); db.commit(); db.refresh(z)
    return _dict(z)


@router.get("/zorgaanbieders")
def list_zorgaanbieders(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    rows = db.query(Zorgaanbieder).order_by(Zorgaanbieder.naam).all()
    return [_dict(z) for z in rows]
