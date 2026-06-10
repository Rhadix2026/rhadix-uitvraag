"""
uitvragen.py — Het hart van de KIK-Starter.

Een ketenpartij stelt een uitvraag samen (uitwisselprofiel + indicatoren) en
richt die op één of meer zorgaanbieders. Per (aanbieder × indicator) wordt het
datastation bevraagd; de berekende antwoorden worden vastgelegd en zijn daarna
in te zien, te downloaden (CSV/Excel) of via de API op te halen.
"""
from __future__ import annotations

import csv
import io
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.auth_models import User
from app.models.kik_models import (Antwoord, AntwoordStatus, Uitvraag, UitvraagStatus, Zorgaanbieder)
from app.services import profiles as profiles_svc
from app.services.datastation import vraag_indicator

router = APIRouter(tags=["uitvragen"])


def _parse_uuid(val: str, label="ID") -> uuid.UUID:
    try:
        return uuid.UUID(str(val))
    except (ValueError, AttributeError):
        raise HTTPException(400, f"Ongeldig {label}: {val!r}")


class CreateUitvraag(BaseModel):
    profiel_key: str
    indicator_codes: list[str]
    zorgaanbieder_ids: list[str]


def _antwoord_dict(a: Antwoord) -> dict:
    return {"id": str(a.id), "zorgaanbieder_id": str(a.zorgaanbieder_id) if a.zorgaanbieder_id else None,
            "zorgaanbieder": a.zorgaanbieder_naam, "indicator_code": a.indicator_code,
            "indicator": a.indicator_label, "eenheid": a.eenheid, "waarde": a.waarde,
            "status": a.status.value, "toelichting": a.toelichting,
            "computed_at": a.computed_at.isoformat() if a.computed_at else None}


def _uitvraag_dict(u: Uitvraag, with_antwoorden=False) -> dict:
    d = {"id": str(u.id), "profiel_key": u.profiel_key, "profiel_label": u.profiel_label,
         "status": u.status.value, "aantal_antwoorden": len(u.antwoorden),
         "created_at": u.created_at.isoformat() if u.created_at else None}
    if with_antwoorden:
        d["antwoorden"] = [_antwoord_dict(a) for a in u.antwoorden]
    return d


@router.post("/uitvragen", status_code=201)
def create_uitvraag(body: CreateUitvraag, db: Session = Depends(get_db),
                    current: User = Depends(get_current_user)):
    prof = profiles_svc.get_profile(body.profiel_key)
    if not prof:
        raise HTTPException(404, f"Onbekend uitwisselprofiel: {body.profiel_key!r}")
    indicatoren = profiles_svc.get_indicators(body.profiel_key, body.indicator_codes)
    if not indicatoren:
        raise HTTPException(422, "Selecteer minimaal één geldige indicator")
    if not body.zorgaanbieder_ids:
        raise HTTPException(422, "Selecteer minimaal één zorgaanbieder")

    aanbieders = (db.query(Zorgaanbieder)
                  .filter(Zorgaanbieder.id.in_([_parse_uuid(z, "zorgaanbieder_id") for z in body.zorgaanbieder_ids]))
                  .all())
    if not aanbieders:
        raise HTTPException(404, "Geen geldige zorgaanbieders gevonden")

    uitvraag = Uitvraag(id=uuid.uuid4(), tenant_id=current.tenant_id, created_by=current.id,
                        profiel_key=prof["key"], profiel_label=prof["label"])
    db.add(uitvraag); db.flush()

    n_ok = n_total = 0
    for z in aanbieders:
        for ind in indicatoren:
            res = vraag_indicator(z, ind)
            n_total += 1
            if res.status == "OK":
                n_ok += 1
            db.add(Antwoord(
                id=uuid.uuid4(), uitvraag_id=uitvraag.id, zorgaanbieder_id=z.id,
                zorgaanbieder_naam=z.naam, indicator_code=ind["code"],
                indicator_label=ind["label"], eenheid=ind.get("eenheid"),
                waarde=res.waarde, status=AntwoordStatus(res.status), toelichting=res.toelichting))

    uitvraag.status = (UitvraagStatus.VOLTOOID if n_ok == n_total
                       else UitvraagStatus.MISLUKT if n_ok == 0
                       else UitvraagStatus.GEDEELTELIJK)
    db.commit(); db.refresh(uitvraag)
    return _uitvraag_dict(uitvraag, with_antwoorden=True)


@router.get("/uitvragen")
def list_uitvragen(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    rows = (db.query(Uitvraag).filter(Uitvraag.tenant_id == current.tenant_id)
            .order_by(Uitvraag.created_at.desc()).all())
    return [_uitvraag_dict(u) for u in rows]


def _get_owned(uitvraag_id: str, db: Session, current: User) -> Uitvraag:
    uid = _parse_uuid(uitvraag_id, "uitvraag_id")
    u = db.query(Uitvraag).filter(Uitvraag.id == uid, Uitvraag.tenant_id == current.tenant_id).first()
    if not u:
        raise HTTPException(404, "Uitvraag niet gevonden")
    return u


@router.get("/uitvragen/{uitvraag_id}")
def get_uitvraag(uitvraag_id: str, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return _uitvraag_dict(_get_owned(uitvraag_id, db, current), with_antwoorden=True)


def _rows_for_export(u: Uitvraag):
    yield ("Zorgaanbieder", "Indicator", "Code", "Eenheid", "Waarde", "Status", "Toelichting")
    for a in u.antwoorden:
        yield (a.zorgaanbieder_naam, a.indicator_label, a.indicator_code, a.eenheid or "",
               "" if a.waarde is None else a.waarde, a.status.value, a.toelichting or "")


@router.get("/uitvragen/{uitvraag_id}/export.csv")
def export_csv(uitvraag_id: str, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    u = _get_owned(uitvraag_id, db, current)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    for row in _rows_for_export(u):
        w.writerow(row)
    buf.seek(0)
    fn = f"uitvraag-{str(u.id)[:8]}.csv"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fn}"'})


@router.get("/uitvragen/{uitvraag_id}/export.xlsx")
def export_xlsx(uitvraag_id: str, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    u = _get_owned(uitvraag_id, db, current)
    wb = Workbook(); ws = wb.active; ws.title = "Antwoorden"
    rows = list(_rows_for_export(u))
    ws.append(rows[0])
    for c in ws[1]:
        c.font = Font(bold=True)
    for row in rows[1:]:
        ws.append(row)
    for col in ws.columns:
        width = max((len(str(c.value)) for c in col if c.value is not None), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(width + 4, 50)
    out = io.BytesIO(); wb.save(out); out.seek(0)
    fn = f"uitvraag-{str(u.id)[:8]}.xlsx"
    return StreamingResponse(
        out, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'})
