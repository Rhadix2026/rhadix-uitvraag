"""
uitvragen.py — Het hart van de Rhadix Uitvraag.

Een ketenpartij stelt een uitvraag samen (uitwisselprofiel + indicatoren) en
richt die op één of meer zorgaanbieders. Per (aanbieder × indicator) wordt het
datastation bevraagd; de berekende antwoorden worden vastgelegd en zijn daarna
in te zien, te downloaden (CSV/Excel) of via de API op te halen.
"""
from __future__ import annotations

import csv
import io
import statistics
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
from app.services.datastation import vraag_indicator, dien_in, haal_resultaat

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
            "status": a.status.value, "toelichting": a.toelichting, "duur_ms": a.duur_ms,
            "query_id": a.query_id, "wacht": a.status == AntwoordStatus.UITGEZET,
            "async": bool(a.datastation_url),
            "computed_at": a.computed_at.isoformat() if a.computed_at else None}


def _uitvraag_dict(u: Uitvraag, with_antwoorden=False) -> dict:
    open_count = sum(1 for a in u.antwoorden if a.status == AntwoordStatus.UITGEZET)
    d = {"id": str(u.id), "profiel_key": u.profiel_key, "profiel_label": u.profiel_label,
         "status": u.status.value, "aantal_antwoorden": len(u.antwoorden),
         "openstaand": open_count,
         "doorlooptijd_ms": u.doorlooptijd_ms,
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

    n_ok = n_total = n_uit = 0
    duren = []
    afnemer = getattr(current, "email", None)
    for z in aanbieders:
        for ind in indicatoren:
            n_total += 1
            if getattr(z, "datastation_url", None):
                # Federatief async: zet de gevalideerde vraag uit bij het datastation.
                r = dien_in(z, ind, afnemer=afnemer)
                if r.get("duur_ms") is not None:
                    duren.append(r["duur_ms"])
                if r.get("status") == "UITGEZET" and r.get("query_id"):
                    n_uit += 1
                    db.add(Antwoord(
                        id=uuid.uuid4(), uitvraag_id=uitvraag.id, zorgaanbieder_id=z.id,
                        zorgaanbieder_naam=z.naam, indicator_code=ind["code"],
                        indicator_label=ind["label"], eenheid=ind.get("eenheid"),
                        waarde=None, status=AntwoordStatus.UITGEZET,
                        toelichting=r.get("toelichting"), duur_ms=r.get("duur_ms"),
                        query_id=r.get("query_id"), datastation_url=r.get("url")))
                else:
                    db.add(Antwoord(
                        id=uuid.uuid4(), uitvraag_id=uitvraag.id, zorgaanbieder_id=z.id,
                        zorgaanbieder_naam=z.naam, indicator_code=ind["code"],
                        indicator_label=ind["label"], eenheid=ind.get("eenheid"),
                        waarde=None, status=AntwoordStatus.FOUT,
                        toelichting=r.get("toelichting"), duur_ms=r.get("duur_ms"),
                        datastation_url=r.get("url")))
            else:
                res = vraag_indicator(z, ind)
                if res.status == "OK":
                    n_ok += 1
                if res.duur_ms is not None:
                    duren.append(res.duur_ms)
                db.add(Antwoord(
                    id=uuid.uuid4(), uitvraag_id=uitvraag.id, zorgaanbieder_id=z.id,
                    zorgaanbieder_naam=z.naam, indicator_code=ind["code"],
                    indicator_label=ind["label"], eenheid=ind.get("eenheid"),
                    waarde=res.waarde, status=AntwoordStatus(res.status),
                    toelichting=res.toelichting, duur_ms=res.duur_ms))

    uitvraag.doorlooptijd_ms = max(duren) if duren else None
    if n_uit > 0:
        uitvraag.status = UitvraagStatus.LOPEND
    else:
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


@router.get("/uitvragen/stats")
def uitvragen_stats(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """Analyse/Monitor: volumes, response-ratio, doorlooptijd en uitsplitsingen."""
    from collections import Counter, defaultdict

    uitvragen = db.query(Uitvraag).filter(Uitvraag.tenant_id == current.tenant_id).all()
    antwoorden = (db.query(Antwoord).join(Uitvraag, Antwoord.uitvraag_id == Uitvraag.id)
                  .filter(Uitvraag.tenant_id == current.tenant_id).all())

    sc = Counter(a.status.value for a in antwoorden)
    n_ok, n_geen, n_fout = sc.get("OK", 0), sc.get("GEEN_DATA", 0), sc.get("FOUT", 0)
    totaal_antw = len(antwoorden)
    ratio = lambda x: round(x / totaal_antw, 3) if totaal_antw else 0.0

    dts = [u.doorlooptijd_ms for u in uitvragen if u.doorlooptijd_ms is not None]
    doorlooptijd = {
        "gemiddeld_ms": round(statistics.mean(dts)) if dts else None,
        "mediaan_ms":   round(statistics.median(dts)) if dts else None,
        "max_ms":       max(dts) if dts else None,
    }

    prof_label = {u.id: u.profiel_label for u in uitvragen}
    per_prof = defaultdict(lambda: {"uitvragen": 0, "antwoorden": 0, "ok": 0})
    for u in uitvragen:
        per_prof[u.profiel_label]["uitvragen"] += 1
    for a in antwoorden:
        lbl = prof_label.get(a.uitvraag_id, "—")
        per_prof[lbl]["antwoorden"] += 1
        if a.status.value == "OK":
            per_prof[lbl]["ok"] += 1

    per_za = defaultdict(lambda: {"antwoorden": 0, "ok": 0, "duren": []})
    for a in antwoorden:
        d = per_za[a.zorgaanbieder_naam]
        d["antwoorden"] += 1
        if a.status.value == "OK":
            d["ok"] += 1
        if a.duur_ms is not None:
            d["duren"].append(a.duur_ms)

    tijdlijn = defaultdict(int)
    for u in uitvragen:
        if u.created_at:
            tijdlijn[u.created_at.date().isoformat()] += 1

    return {
        "totaal_uitvragen": len(uitvragen),
        "totaal_antwoorden": totaal_antw,
        "antwoord_status": {"OK": n_ok, "GEEN_DATA": n_geen, "FOUT": n_fout},
        "response_ratio": ratio(n_ok),
        "geen_data_ratio": ratio(n_geen),
        "fout_ratio": ratio(n_fout),
        "doorlooptijd": doorlooptijd,
        "per_profiel": sorted(
            [{"profiel": k, "uitvragen": v["uitvragen"], "antwoorden": v["antwoorden"],
              "response_ratio": round(v["ok"] / v["antwoorden"], 3) if v["antwoorden"] else 0.0}
             for k, v in per_prof.items()],
            key=lambda x: x["antwoorden"], reverse=True),
        "per_zorgaanbieder": sorted(
            [{"zorgaanbieder": k, "antwoorden": v["antwoorden"],
              "response_ratio": round(v["ok"] / v["antwoorden"], 3) if v["antwoorden"] else 0.0,
              "gem_duur_ms": round(statistics.mean(v["duren"])) if v["duren"] else None}
             for k, v in per_za.items()],
            key=lambda x: x["antwoorden"], reverse=True),
        "tijdlijn": [{"datum": d, "uitvragen": n} for d, n in sorted(tijdlijn.items())],
    }


def _get_owned(uitvraag_id: str, db: Session, current: User) -> Uitvraag:
    uid = _parse_uuid(uitvraag_id, "uitvraag_id")
    u = db.query(Uitvraag).filter(Uitvraag.id == uid, Uitvraag.tenant_id == current.tenant_id).first()
    if not u:
        raise HTTPException(404, "Uitvraag niet gevonden")
    return u


@router.get("/uitvragen/{uitvraag_id}")
def get_uitvraag(uitvraag_id: str, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return _uitvraag_dict(_get_owned(uitvraag_id, db, current), with_antwoorden=True)


@router.post("/uitvragen/{uitvraag_id}/ophalen")
def ophalen_antwoorden(uitvraag_id: str, db: Session = Depends(get_db),
                       current: User = Depends(get_current_user)):
    """Haal de antwoorden op van uitgezette (async) vragen bij de datastations.
    Een antwoord komt pas binnen nadat de zorgaanbieder het heeft geaccordeerd."""
    u = _get_owned(uitvraag_id, db, current)
    bijgewerkt = 0
    for a in u.antwoorden:
        if a.status != AntwoordStatus.UITGEZET or not a.query_id or not a.datastation_url:
            continue
        r = haal_resultaat(a.datastation_url, a.query_id)
        st = r.get("status")
        if st == "GEREED":
            a.waarde = r.get("waarde")
            a.status = AntwoordStatus.OK
            a.toelichting = (("Handmatig vastgesteld" if r.get("handmatig") else "Geaccordeerd")
                             + " door zorgaanbieder" + (f": {r.get('toelichting')}" if r.get("toelichting") else ""))
            bijgewerkt += 1
        elif st == "AFGEWEZEN":
            a.status = AntwoordStatus.AFGEWEZEN
            a.toelichting = r.get("toelichting") or "Afgewezen door zorgaanbieder"
            bijgewerkt += 1
        # IN_BEHANDELING → blijft UITGEZET

    nog_open = sum(1 for a in u.antwoorden if a.status == AntwoordStatus.UITGEZET)
    n_ok = sum(1 for a in u.antwoorden if a.status == AntwoordStatus.OK)
    n_total = len(u.antwoorden)
    if nog_open:
        u.status = UitvraagStatus.LOPEND
    else:
        u.status = (UitvraagStatus.VOLTOOID if n_ok == n_total
                    else UitvraagStatus.MISLUKT if n_ok == 0
                    else UitvraagStatus.GEDEELTELIJK)
    db.commit(); db.refresh(u)
    d = _uitvraag_dict(u, with_antwoorden=True)
    d["bijgewerkt"] = bijgewerkt
    return d


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
