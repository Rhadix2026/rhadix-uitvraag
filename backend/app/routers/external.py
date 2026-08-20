"""
external.py — KIK-Starter-compatibele externe API.

Implementeert het aansluitcontract uit de 'Aansluitspecificatie KIK-Starter API'
(v1.0): OAuth2 password-grant token + vragen ophalen per KVK + resultaten per
query_id. Hiermee kan afnemer-tooling op de standaardmanier aansluiten.
"""
from __future__ import annotations

import os
import uuid as _uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.api_clients import load_clients, verify_client_secret
from app.auth.app_access import require_machine_client
from app.auth.security import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token, verify_password
from app.auth.service_principals import ensure_service_principal
from app.database import get_db
from app.models.auth_models import User
from app.models.kik_models import AanbiederCapability, Uitvraag, Zorgaanbieder

router = APIRouter(tags=["external (KIK-Starter-compatibel)"])


def _client_token_minutes() -> int:
    """Clienttokens leven korter dan gebruikerstokens (default 60 i.p.v. 480)."""
    try:
        return int(os.getenv("KSAPI_TOKEN_EXPIRE_MINUTES", "60"))
    except ValueError:
        return 60


def password_grant_enabled() -> bool:
    """De oude password-grant: standaard UIT, alleen bewust per omgeving aan.

    Uitsluitend bedoeld als tijdelijke overgangsmaatregel zolang externe afnemers
    nog niet op client_credentials zijn overgestapt.
    """
    return os.getenv("KSAPI_ALLOW_PASSWORD_GRANT", "0").strip().lower() in ("1", "true", "yes", "on")


@router.post("/external/token")
def token(grant_type: str = Form(...),
          client_id: str = Form(default="ksapi"), client_secret: str = Form(default=""),
          username: str | None = Form(default=None), password: str | None = Form(default=None),
          db: Session = Depends(get_db)):
    """OAuth2-token voor externe afnemers.

    `client_credentials` is de bedoelde weg: authenticatie met een eigen
    client_id + client_secret, los van gebruikersaccounts. De tenant volgt uit de
    serverzijdige registratie en kan niet via het verzoek worden gekozen.

    `password` is de oude weg uit de aansluitspecificatie en staat standaard uit.
    """
    if grant_type == "client_credentials":
        clients = load_clients()
        if not clients:
            # Fail-closed: zonder registratie geeft deze route niets uit.
            raise HTTPException(503, "server_error: geen API-clients geconfigureerd")
        client = clients.get(client_id)
        if client is None or not verify_client_secret(client, client_secret):
            raise HTTPException(401, "invalid_client")

        principal = ensure_service_principal(db, client)
        tok = create_access_token(
            {"sub": str(principal.id), "role": principal.role.value,
             "tenant_id": str(principal.tenant_id), "email": principal.email,
             "client_id": client.client_id, "typ": "client", "scope": "external"},
            expires_delta=timedelta(minutes=_client_token_minutes()),
        )
        return {"access_token": tok, "token_type": "Bearer",
                "expires_in": _client_token_minutes() * 60, "scope": "external"}

    if grant_type == "password":
        if not password_grant_enabled():
            raise HTTPException(
                401,
                "unsupported_grant_type: de password-grant is uitgeschakeld; "
                "gebruik grant_type=client_credentials met uw client_id en client_secret",
            )
        # Ook de oude weg vereist nu een geldig client-credential.
        clients = load_clients()
        if not clients:
            raise HTTPException(503, "server_error: geen API-clients geconfigureerd")
        client = clients.get(client_id)
        if client is None or not verify_client_secret(client, client_secret):
            raise HTTPException(401, "invalid_client")
        user = db.query(User).filter(User.email == (username or "").lower().strip(),
                                     User.is_active == True).first()
        if not user or not user.password_hash or not verify_password(password or "", user.password_hash):
            raise HTTPException(401, "invalid_grant")
        tok = create_access_token({"sub": str(user.id), "role": user.role.value,
                                   "tenant_id": str(user.tenant_id), "email": user.email})
        return {"access_token": tok, "token_type": "Bearer",
                "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60}

    raise HTTPException(400, "unsupported_grant_type")


def _namen_voor_kvk(db: Session, kvk: str) -> set[str]:
    """KVK → aanbiedernamen, via de capabilities-registry en/of het kvk-veld."""
    namen = {c.aanbieder_naam for c in db.query(AanbiederCapability).filter(AanbiederCapability.aanbieder_id == kvk).all()}
    namen |= {z.naam for z in db.query(Zorgaanbieder).filter(Zorgaanbieder.kvk == kvk).all()}
    return namen


@router.get("/external/vragen")
def external_vragen(aanbiederId: str = Query(...), aanbiederIdType: str = Query("kvk"),
                    datumOntvangen: str | None = Query(None), paginanummer: int = Query(1, ge=1),
                    db: Session = Depends(get_db), current: User = Depends(require_machine_client)):
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
                        db: Session = Depends(get_db), current: User = Depends(require_machine_client)):
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
