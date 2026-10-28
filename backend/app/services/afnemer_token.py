"""
afnemer_token.py — het centrale token waarmee Uitvraag zich bij een datastation
als afnemer meldt (B-28).

Zelfde patroon als de CRM-koppeling van Rhadix Datavalidatie: een serviceaccount
in het centrale platform (zonder applicaties in de apps-claim) logt in bij de
centrale login en krijgt een gewoon RS256-token. Het datastation herkent de afnemer
aan de `sub` van dat account. Er is dus geen apart geheim of mechanisme; uitgifte,
rotatie (wachtwoord resetten), intrekking (account deactiveren) en audit lopen via
het centrale beheer.

Configuratie (geheimen alleen uit een serverbestand, nooit uit Git):
    DATASTATION_AFNEMER_LOGIN_URL      https-basis van het centrale platform
    Bij voorkeur een machineaccount (B-28 stap 5; client_credentials):
    DATASTATION_AFNEMER_CLIENT_ID      id van het machineaccount
    DATASTATION_AFNEMER_CLIENT_SECRET  geheim (rmx_…)
    DATASTATION_AFNEMER_AUDIENCE       doelgroep, bijv. datastation-staging
    Alleen tijdens de overgang, als er geen machineaccount is ingesteld:
    DATASTATION_AFNEMER_EMAIL / _WACHTWOORD  serviceaccount

Niet geconfigureerd = geen token; de aanroep gaat dan zonder token en een datastation
dat authenticatie vraagt, weigert hem. Het token wordt nooit gelogd, en alleen
meegestuurd naar bestemmingen die door `services/bestemming.py` zijn toegestaan.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
from typing import Optional
from urllib.parse import urlsplit

import httpx

log = logging.getLogger("rhadix.afnemer_token")

TIJDSLIMIET = 8
TOKENMARGE = 60      # seconden vóór het verlopen alvast opnieuw inloggen

_slot = threading.Lock()
_cache: dict = {"waarde": None, "geldig_tot": 0.0}


def _env(naam: str) -> str:
    return (os.getenv(naam) or "").strip()


def _machine() -> bool:
    return bool(_env("DATASTATION_AFNEMER_CLIENT_ID") and _env("DATASTATION_AFNEMER_CLIENT_SECRET"))


def geconfigureerd() -> bool:
    return bool(_env("DATASTATION_AFNEMER_LOGIN_URL") and (
        _machine() or (_env("DATASTATION_AFNEMER_EMAIL") and _env("DATASTATION_AFNEMER_WACHTWOORD"))))


def _vervaltijd(token: str) -> float:
    try:
        deel = token.split(".")[1]
        deel += "=" * (-len(deel) % 4)
        return float(json.loads(base64.urlsafe_b64decode(deel)).get("exp", 0))
    except Exception:
        return 0.0


def vergeet() -> None:
    with _slot:
        _cache.update(waarde=None, geldig_tot=0.0)


def token(vernieuw: bool = False) -> Optional[str]:
    """Een geldig centraal token, of None als dat er niet is (niet geconfigureerd of
    inloggen mislukt). Gooit nooit een uitzondering."""
    if not geconfigureerd():
        return None
    with _slot:
        if not vernieuw and _cache["waarde"] and time.time() < _cache["geldig_tot"]:
            return _cache["waarde"]
    basis = _env("DATASTATION_AFNEMER_LOGIN_URL").rstrip("/")
    if urlsplit(basis).scheme != "https":
        log.error("afnemer-token: DATASTATION_AFNEMER_LOGIN_URL moet https zijn")
        return None
    try:
        with httpx.Client(follow_redirects=False, trust_env=False, timeout=TIJDSLIMIET) as c:
            if _machine():
                soort = "machine"
                r = c.post(f"{basis}/api/auth/machine-token",
                           json={"grant_type": "client_credentials",
                                 "client_id": _env("DATASTATION_AFNEMER_CLIENT_ID"),
                                 "client_secret": _env("DATASTATION_AFNEMER_CLIENT_SECRET"),
                                 "audience": _env("DATASTATION_AFNEMER_AUDIENCE") or None})
            else:
                soort = "serviceaccount"
                r = c.post(f"{basis}/api/auth/login",
                           json={"email": _env("DATASTATION_AFNEMER_EMAIL"),
                                 "password": _env("DATASTATION_AFNEMER_WACHTWOORD")})
        if r.status_code != 200:
            log.error("afnemer-token (%s): centrale uitgifte gaf HTTP %s", soort, r.status_code)
            return None
        waarde = r.json().get("access_token")
    except Exception as exc:
        log.error("afnemer-token: centrale login mislukt (%s)", type(exc).__name__)
        return None
    if not waarde:
        log.error("afnemer-token: centrale login gaf geen token terug")
        return None
    verloopt = _vervaltijd(waarde)
    with _slot:
        _cache["waarde"] = waarde
        _cache["geldig_tot"] = (verloopt - TOKENMARGE) if verloopt else time.time() + 300
    log.info("afnemer-token: nieuw centraal token opgehaald (%s)", soort)
    return waarde
