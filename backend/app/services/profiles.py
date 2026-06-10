"""
profiles.py — Uitwisselprofielen (KIK-V) met hun gevalideerde indicatoren.

Pluggable bron: staat de env-variabele RHADIX_PROFILES_URL gezet, dan worden de
profielen uit die API gehaald (zoals Rhadix-validatie ze aanbiedt). Anders valt
de service terug op een ingebouwde set representatieve profielen, zodat deze
versie volledig zelfstandig draait.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

import httpx

# ── Ingebouwde fallback: 8 uitwisselprofielen met gevalideerde indicatoren ──
_STATIC_PROFILES = [
    {
        "key": "zorgkantoren-inkoop", "label": "Zorgkantoren — Inkoop & contractering",
        "afnemer": "Zorgkantoren",
        "indicatoren": [
            {"code": "PERS_RATIO", "label": "Personeel/cliënt-ratio", "eenheid": "fte/cliënt"},
            {"code": "ZIEKTEVERZUIM", "label": "Ziekteverzuimpercentage", "eenheid": "%"},
            {"code": "CLIENT_TEVREDENHEID", "label": "Cliënttevredenheid (NPS)", "eenheid": "score"},
        ],
    },
    {
        "key": "igj-toezicht", "label": "IGJ — Toezicht & kwaliteit",
        "afnemer": "Inspectie Gezondheidszorg en Jeugd",
        "indicatoren": [
            {"code": "MELDINGEN_INCIDENT", "label": "Gemelde incidenten (per kwartaal)", "eenheid": "aantal"},
            {"code": "BIG_REGISTRATIE", "label": "BIG-geregistreerd personeel", "eenheid": "%"},
            {"code": "MEDICATIE_VEILIGHEID", "label": "Medicatieveiligheidsscore", "eenheid": "score"},
        ],
    },
    {
        "key": "vws-beleid", "label": "VWS — Beleid & capaciteit",
        "afnemer": "Ministerie van VWS",
        "indicatoren": [
            {"code": "WACHTLIJST", "label": "Cliënten op wachtlijst", "eenheid": "aantal"},
            {"code": "CAPACITEIT_BEZETTING", "label": "Bezettingsgraad", "eenheid": "%"},
        ],
    },
    {
        "key": "nza-bekostiging", "label": "NZa — Bekostiging & tarieven",
        "afnemer": "Nederlandse Zorgautoriteit",
        "indicatoren": [
            {"code": "OMZET_WLZ", "label": "Omzet Wlz-zorg", "eenheid": "k€"},
            {"code": "TARIEF_BENUTTING", "label": "Tariefbenutting", "eenheid": "%"},
        ],
    },
    {
        "key": "actiz-branche", "label": "ActiZ — Branche-informatie",
        "afnemer": "ActiZ",
        "indicatoren": [
            {"code": "MEDEWERKERS", "label": "Aantal medewerkers", "eenheid": "aantal"},
            {"code": "PERSONEELSVERLOOP", "label": "Personeelsverloop", "eenheid": "%"},
            {"code": "STAGEPLAATSEN", "label": "Stageplaatsen", "eenheid": "aantal"},
        ],
    },
    {
        "key": "kwaliteitskader", "label": "Kwaliteitskader Verpleeghuiszorg",
        "afnemer": "Zorginstituut Nederland",
        "indicatoren": [
            {"code": "DECUBITUS", "label": "Decubitus prevalentie", "eenheid": "%"},
            {"code": "VALINCIDENTEN", "label": "Valincidenten met letsel", "eenheid": "aantal"},
            {"code": "VRIJHEIDSBEPERKING", "label": "Vrijheidsbeperkende maatregelen", "eenheid": "%"},
        ],
    },
    {
        "key": "personeelssamenstelling", "label": "Personeelssamenstelling",
        "afnemer": "Zorginstituut Nederland",
        "indicatoren": [
            {"code": "ZORGNIVEAU_MIX", "label": "Aandeel niveau 3+ zorgverleners", "eenheid": "%"},
            {"code": "INHUUR_EXTERN", "label": "Externe inhuur", "eenheid": "%"},
        ],
    },
    {
        "key": "wlz-jaarverantwoording", "label": "Wlz-jaarverantwoording",
        "afnemer": "CIBG / DigiMV",
        "indicatoren": [
            {"code": "RESULTAAT_BOEKJAAR", "label": "Resultaat boekjaar", "eenheid": "k€"},
            {"code": "SOLVABILITEIT", "label": "Solvabiliteit", "eenheid": "%"},
            {"code": "WEERSTANDSVERMOGEN", "label": "Weerstandsvermogen", "eenheid": "%"},
        ],
    },
]


def _fetch_remote(url: str) -> Optional[list]:
    try:
        resp = httpx.get(url, timeout=8.0)
        resp.raise_for_status()
        data = resp.json()
        return data.get("profielen", data) if isinstance(data, dict) else data
    except Exception:
        return None  # nette terugval op de statische set


@lru_cache(maxsize=1)
def _load() -> list:
    url = os.getenv("RHADIX_PROFILES_URL")
    if url:
        remote = _fetch_remote(url)
        if remote:
            return remote
    return _STATIC_PROFILES


def list_profiles() -> list:
    """Profielen zonder indicator-detail (lichtgewicht overzicht)."""
    return [{"key": p["key"], "label": p["label"], "afnemer": p.get("afnemer"),
             "aantal_indicatoren": len(p["indicatoren"])} for p in _load()]


def get_profile(key: str) -> Optional[dict]:
    return next((p for p in _load() if p["key"] == key), None)


def get_indicators(key: str, codes: Optional[list] = None) -> list:
    prof = get_profile(key)
    if not prof:
        return []
    inds = prof["indicatoren"]
    if codes:
        wanted = set(codes)
        inds = [i for i in inds if i["code"] in wanted]
    return inds
