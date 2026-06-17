"""
zorgaanbieders.py — Zelfregistratie, import en overzicht van zorgaanbieders.

Registratie is *publiek* (een zorgaanbieder meldt zich aan om uitvragen te kunnen
ontvangen). Het overzicht is voor ingelogde ketenpartijen, die hieruit kiezen.
Beheerders kunnen een KIK-V zorgaanbieders-export (CSV) importeren.
"""
from __future__ import annotations

import csv
import io
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.auth_models import User
from app.models.kik_models import Zorgaanbieder

router = APIRouter(tags=["zorgaanbieders"])


def _dict(z: Zorgaanbieder, vol: bool = False) -> dict:
    d = {
        "id": str(z.id), "naam": z.naam, "kvk": z.kvk, "plaats": z.plaats,
        "gemeente": z.gemeente, "contact_email": z.contact_email,
        "huidige_fase": z.huidige_fase, "sectoren": z.sectoren,
        "daas_leverancier": z.daas_leverancier,
        "heeft_credential": z.heeft_credential,
        "aantal_profielen": len([p for p in (z.uitwisselprofielen or "").split(",") if p.strip()]),
        "heeft_datastation": bool(z.datastation_url),
        "created_at": z.created_at.isoformat() if z.created_at else None,
    }
    if vol:
        d.update({
            "straatnaam": z.straatnaam, "huisnummer": z.huisnummer, "postcode": z.postcode,
            "samenwerkingsverband": z.samenwerkingsverband, "doelgroepen": z.doelgroepen,
            "zorgkantoren": z.zorgkantoren, "concessiehouders": z.concessiehouders,
            "contact_voornaam": z.contact_voornaam, "contact_achternaam": z.contact_achternaam,
            "contact_telefoon": z.contact_telefoon, "contact_functie": z.contact_functie,
            "fte": z.fte, "locaties": z.locaties, "bedden": z.bedden,
            "implementatie_consultant": z.implementatie_consultant,
            "zelfscan_retour": z.zelfscan_retour, "intentieverklaring": z.intentieverklaring,
            "contract_datastation": z.contract_datastation,
            "aangesloten_test": z.aangesloten_test, "aangesloten_productie": z.aangesloten_productie,
            "vestigingen": z.vestigingen, "implementatiepartner": z.implementatiepartner,
            "uitwisselprofielen": z.uitwisselprofielen, "datastation_url": z.datastation_url,
        })
    return d


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


@router.get("/zorgaanbieders/{za_id}")
def get_zorgaanbieder(za_id: str, db: Session = Depends(get_db),
                      current: User = Depends(get_current_user)):
    z = db.query(Zorgaanbieder).filter(Zorgaanbieder.id == za_id).first()
    if not z:
        raise HTTPException(404, "Zorgaanbieder niet gevonden")
    return _dict(z, vol=True)


# ── CSV-import (KIK-V zorgaanbieders-export) ──────────────────────────────────
def _num(val: str):
    s = (val or "").strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _int(val: str):
    s = (val or "").strip()
    try:
        return int(float(s.replace(",", ".")))
    except ValueError:
        return None


def _s(val: str):
    s = (val or "").strip()
    return s or None


@router.post("/zorgaanbieders/import")
async def import_zorgaanbieders(file: UploadFile = File(...),
                                db: Session = Depends(get_db),
                                current: User = Depends(get_current_user)):
    """Importeer een KIK-V zorgaanbieders-export (CSV). Dedupliceert op KVK;
    bij meerdere rijen per aanbieder (verschillende contactpersonen) wordt de
    eerste rij mét contact-e-mail als hoofdcontact gebruikt. Bestaande aanbieders
    (zelfde KVK of naam) worden bijgewerkt."""
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "Algemeen_naam" not in reader.fieldnames:
        raise HTTPException(422, "Onverwacht CSV-formaat: kolom 'Algemeen_naam' ontbreekt")

    # groepeer rijen per aanbieder (KVK, anders naam)
    groepen: dict[str, list[dict]] = {}
    for r in reader:
        key = (_s(r.get("Algemeen_kvknummer")) or _s(r.get("Algemeen_naam")) or "").strip()
        if not key:
            continue
        groepen.setdefault(key, []).append(r)

    nieuw = bijgewerkt = 0
    for key, rijen in groepen.items():
        basis = rijen[0]
        # hoofdcontact: eerste rij met e-mail, anders eerste rij
        contact = next((x for x in rijen if _s(x.get("Contact_person_email"))), basis)

        kvk = _s(basis.get("Algemeen_kvknummer"))
        naam = _s(basis.get("Algemeen_naam"))
        z = None
        if kvk:
            z = db.query(Zorgaanbieder).filter(Zorgaanbieder.kvk == kvk).first()
        if not z and naam:
            z = db.query(Zorgaanbieder).filter(Zorgaanbieder.naam == naam).first()
        if z is None:
            z = Zorgaanbieder(id=uuid.uuid4(), naam=naam or "Onbekend"); db.add(z); nieuw += 1
        else:
            bijgewerkt += 1

        z.naam = naam or z.naam
        z.kvk = kvk
        z.plaats = _s(basis.get("Algemeen_adres_stad"))
        z.gemeente = _s(basis.get("Algemeen_adres_gemeente"))
        z.straatnaam = _s(basis.get("Algemeen_adres_straatnaam"))
        z.huisnummer = _s(basis.get("Algemeen_adres_huisnummer"))
        z.postcode = _s(basis.get("Algemeen_adres_postcode"))
        z.heeft_credential = _s(basis.get("Algemeen_heeft_credential"))
        z.samenwerkingsverband = _s(basis.get("Algemeen_samenwerkingsverband"))
        z.doelgroepen = _s(basis.get("Algemeen_doelgroepen"))
        z.sectoren = _s(basis.get("Algemeen_sectoren"))
        z.zorgkantoren = _s(basis.get("Algemeen_zorgkantoren"))
        z.concessiehouders = _s(basis.get("Algemeen_consessiehouders"))
        z.contact_voornaam = _s(contact.get("Contact_person_voornaam"))
        z.contact_achternaam = _s(contact.get("Contact_person_achternaam"))
        z.contact_email = _s(contact.get("Contact_person_email"))
        z.contact_telefoon = _s(contact.get("Contact_person_telefoon"))
        z.contact_functie = _s(contact.get("Contact_person_functie"))
        z.fte = _num(basis.get("Capaciteit_totaal_aantal_FTE"))
        z.locaties = _int(basis.get("Capaciteit_totaal_aantal_locaties"))
        z.bedden = _int(basis.get("Capaciteit_totaal_aantal_bedden"))
        z.daas_leverancier = _s(basis.get("Software_DAAS-leverancier"))
        z.implementatie_consultant = _s(basis.get("Implementatie_implementatie-consultant"))
        z.zelfscan_retour = _s(basis.get("Implementatie_Zelfscan_retour_ontvangen"))
        z.intentieverklaring = _s(basis.get("Implementatie_Intentieverklaring_ondertekend"))
        z.contract_datastation = _s(basis.get("Implementatie_Contract_datastation_ondertekend"))
        z.aangesloten_test = _s(basis.get("Implementatie_Aangesloten_op_KIK-starter_test"))
        z.aangesloten_productie = _s(basis.get("Implementatie_Aangesloten_op_KIK-Starter_productie"))
        z.huidige_fase = _s(basis.get("Fases_huidige_fase"))
        z.vestigingen = _s(basis.get("Vestigingen_naam_verstiging"))
        z.implementatiepartner = _s(basis.get("Implementatiepartners_naam"))
        z.uitwisselprofielen = _s(basis.get("Uitwisselprofielen_naam"))

    db.commit()
    totaal = db.query(Zorgaanbieder).count()
    return {"status": "ok", "rijen": sum(len(v) for v in groepen.values()),
            "aanbieders": len(groepen), "nieuw": nieuw, "bijgewerkt": bijgewerkt,
            "totaal_in_db": totaal}
