"""profiles.py — Uitwisselprofielen en hun indicatoren (alle ingelogde gebruikers)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.models.auth_models import User
from app.services import profiles as profiles_svc

router = APIRouter(tags=["profielen"])


@router.get("/profielen")
def list_profielen(current: User = Depends(get_current_user)):
    return profiles_svc.list_profiles()


@router.get("/profielen/{key}")
def get_profiel(key: str, current: User = Depends(get_current_user)):
    prof = profiles_svc.get_profile(key)
    if not prof:
        raise HTTPException(404, f"Onbekend uitwisselprofiel: {key!r}")
    return prof
