"""
external.py — KIK-Starter-compatibele externe API.

Implementeert het aansluitcontract uit de 'Aansluitspecificatie KIK-Starter API'
(v1.0): OAuth2 password-grant token + vragen ophalen per KVK + resultaten per
query_id. Hiermee kan afnemer-tooling op de standaardmanier aansluiten.
"""
from __future__ import annotations

import os
import uuid as _uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.security import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token, verify_password
from app.database import get_db
from app.models.auth_models import User
from app.models.kik_models import AanbiederCapability, Uitvraag, Zorgaanbieder

router = APIRouter(tags=["external (KIK-Starter-compatibel)"])
_KSAPI_CLIENT_SECRET = os.getenv("KSAPI_CLIENT_SECRET")   # optioneel


@router.post("/external/token")
def token(grant_type: str = Form(...), username: str = Form(...), password: str = Form(...),
          client_id: str = Form(default="ksapi"), client_secret: str = Form(default=""),
          db: Session = Depends(get_db)):
    """OAuth2 password-grant (conform de aansluitspecificatie)."""
    if grant_type != "password":
        raise HTTPException(400, "unsupported_grant_type")
    if _KSAPI_CLIENT_SECRET and client_secret != _KSAPI_CLIENT_SECRET:
        raise HTTPException(401, "invalid_client")
    user = db.query(User).filter(User.email == username.lower().strip(), User.is_active == True).first()
    if not user or not user.password_hash or not verify_password(password, user.password_hash):
        raise HTTPException(401, "invalid_grant")
    tok = create_access_token({"sub": str(user.id), "role": user.role.value,
                               "tenant_id": str(user.tenant_id), "email": user.email})
    return {"access_token": tok, "token_type": "Bearer", "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60}


def _namen_voor_kvk(db: Session, kvk: str) -> set[str]:
    """KVK → aanbiedernamen, via de capabilities-registry en/of het kvk-veld."""
    namen = {c.aanbieder_naam for c in db.query(AanbiederCapability).filter(AanbiederCapability.aanbieder_id == kvk).all()}
    namen |= {z.naam for z in db.query(Zorgaanbieder).filter(Zorgaanbieder.kvk == kvk).all()}
    return namen


@router.get("/external/vragen")
def external_vragen(aanbiederId: str = Query(...), aanbiederIdType: str = Query("kvk"),
                    datumOntvangen: str | None = Query(None), paginanummer: int = Query(1, ge=1),
                    db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """Vragen (uitvragen) ophalen voor een aanbieder, geïdentificeerd via KVK."""
    if aanbiederIdType != "kvk":
        raise HTTPException(400, "Alleen aanbiederIdType=kvk wordt ondersteund")
    namen = _namen_voor_kvk(db, aanbiederId)
    vragen = []
    if namen:
        rows = (db.query(Uitvraag).filter(Uitvraag.tenant_id == current.tenant_id)
                .order_by(Uitvraag.created_at.desc()).all())
        for u in rows:
            a_voor = [a for a in u.antwoorden if a.zorgaanbieder_naam in namen]
            if not a_voor:
                continue
            if datumOntvangen and (not u.created_at or u.created_at.date().isoformat() != datumOntvangen):
                continue
            vragen.append({
                "query_id": str(u.id), "uitwisselprofiel": u.profiel_label,
                "uitwisselprofielKey": u.profiel_key, "status": u.status.value,
                "datumOntvangen": u.created_at.isoformat() if u.created_at else None,
                "aanbieder": a_voor[0].zorgaanbieder_naam,
                "indicatoren": sorted({a.indicator_code for a in a_voor}),
            })
    PAGE = 50
    start = (paginanummer - 1) * PAGE
    return {"aanbiederId": aanbiederId, "aanbiederIdType": aanbiederIdType,
            "aantal": len(vragen), "paginanummer": paginanummer, "vragen": vragen[start:start + PAGE]}


@router.get("/external/vraag/{query_id}/resultaten")
def external_resultaten(query_id: str, aanbiederId: str | None = Query(None),
                        paginanummer: int = Query(1, ge=1),
                        db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """Resultaten (antwoorden) ophalen voor een vraag op basis van query_id."""
    try:
        uid = _uuid.UUID(query_id)
    except (ValueError, AttributeError):
        raise HTTPException(400, "Ongeldig query_id")
    u = db.query(Uitvraag).filter(Uitvraag.id == uid, Uitvraag.tenant_id == current.tenant_id).first()
    if not u:
        raise HTTPException(404, "Vraag niet gevonden")
    namen = _namen_voor_kvk(db, aanbiederId) if aanbiederId else None
    res = []
    for a in u.antwoorden:
        if namen is not None and a.zorgaanbieder_naam not in namen:
            continue
        res.append({"indicatorCode": a.indicator_code, "indicator": a.indicator_label,
                    "waarde": a.waarde, "eenheid": a.eenheid, "status": a.status.value,
                    "aanbieder": a.zorgaanbieder_naam,
                    "datumBerekend": a.computed_at.isoformat() if a.computed_at else None})
    PAGE = 100
    start = (paginanummer - 1) * PAGE
    return {"query_id": query_id, "uitwisselprofiel": u.profiel_label, "status": u.status.value,
            "aantal": len(res), "paginanummer": paginanummer, "resultaten": res[start:start + PAGE]}
