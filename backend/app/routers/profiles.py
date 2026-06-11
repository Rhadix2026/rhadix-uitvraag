"""profiles.py — Uitwisselprofielen en hun indicatoren (live uit de bibliotheek)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_user, require_role
from app.models.auth_models import User, UserRole
from app.services import profiles as profiles_svc

router = APIRouter(tags=["profielen"])
_platform_admin = require_role(UserRole.PLATFORM_ADMIN)


@router.get("/profielen")
def list_profielen(current: User = Depends(get_current_user)):
    return profiles_svc.list_profiles()


@router.post("/profielen/refresh")
def refresh_profielen(current: User = Depends(_platform_admin)):
    """Leeg de profielcache zodat de bibliotheek opnieuw wordt opgehaald (beheerder)."""
    profiles_svc.clear_cache()
    return {"status": "ok", "bron": profiles_svc.source_info(),
            "profielen": len(profiles_svc.list_profiles())}


@router.get("/profielen/{key}")
def get_profiel(key: str, current: User = Depends(get_current_user)):
    prof = profiles_svc.get_profile(key)
    if not prof:
        raise HTTPException(404, f"Onbekend uitwisselprofiel: {key!r}")
    return prof
