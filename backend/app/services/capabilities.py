"""
capabilities.py — Inlezen/valideren van de uitwisselprofiel-registry (CSV).

Conform de RFC "Inzichtelijk maken van geïmplementeerde uitwisselprofielen":
de CSV is leidend (single source of truth, beheerd door KIK-V Beheer), wordt als
full refresh verwerkt, en kent per record validatie met logging van afkeur.
"""
from __future__ import annotations

import csv
import datetime
import io
from typing import Tuple

REQUIRED_COLS = ["aanbieder_id_type", "aanbieder_id", "aanbieder_naam",
                 "uitwisselprofiel", "versie", "status", "laatst_bijgewerkt"]
OPTIONELE_COLS = ["software_leverancier"]
ALLOWED_STATUS = {"productie", "test", "implementatie", "uitgefaseerd"}
ALLOWED_IDTYPE = {"kvk", "agb"}


class CsvFormatError(Exception):
    """Formaatfout in de CSV — het gehele bestand wordt afgekeurd."""


def _valid_date(s: str) -> bool:
    try:
        datetime.date.fromisoformat(s)
        return True
    except (ValueError, TypeError):
        return False


def parse_csv(text: str) -> Tuple[list, dict]:
    """Parse + valideer. Retourneert (geldige_records, samenvatting).

    Bij een formaatfout (ontbrekende/onleesbare header) wordt het hele bestand
    afgekeurd via CsvFormatError. Fouten per record → record overslaan + loggen.
    """
    try:
        reader = csv.DictReader(io.StringIO(text))
        header = reader.fieldnames or []
    except Exception as exc:
        raise CsvFormatError(f"CSV niet leesbaar: {exc}")

    ontbrekend = [c for c in REQUIRED_COLS if c not in header]
    if ontbrekend:
        raise CsvFormatError(f"Ontbrekende verplichte kolommen: {', '.join(ontbrekend)}")

    geldig, redenen = [], []
    n_total = 0
    for i, row in enumerate(reader, start=2):  # regel 1 = header
        n_total += 1
        fouten = []
        idtype = (row.get("aanbieder_id_type") or "").strip().lower()
        status = (row.get("status") or "").strip().lower()
        for col in REQUIRED_COLS:
            if not (row.get(col) or "").strip():
                fouten.append(f"verplicht veld leeg: {col}")
        if idtype and idtype not in ALLOWED_IDTYPE:
            fouten.append(f"ongeldig aanbieder_id_type: {idtype!r}")
        if status and status not in ALLOWED_STATUS:
            fouten.append(f"onbekende status: {status!r}")
        datum = (row.get("laatst_bijgewerkt") or "").strip()
        if datum and not _valid_date(datum):
            fouten.append(f"ongeldige datum: {datum!r} (verwacht YYYY-MM-DD)")

        if fouten:
            redenen.append({"regel": i, "redenen": fouten})
            continue
        geldig.append({
            "aanbieder_id_type": idtype,
            "aanbieder_id": row["aanbieder_id"].strip(),
            "aanbieder_naam": row["aanbieder_naam"].strip(),
            "software_leverancier": (row.get("software_leverancier") or "").strip() or None,
            "uitwisselprofiel": row["uitwisselprofiel"].strip(),
            "versie": row["versie"].strip(),
            "status": status,
            "laatst_bijgewerkt": datum or None,
        })

    samenvatting = {
        "totaal": n_total,
        "verwerkt": len(geldig),
        "afgekeurd": len(redenen),
        "redenen": redenen[:50],   # cap logging
    }
    return geldig, samenvatting


# Seed-demodata (CSV) voor de gedemonstreerde aanbieders ─ profiel-keys + versies
# moeten matchen met services/profiles.py. Gemengde statussen tonen de filtering.
SEED_CSV = """aanbieder_id_type,aanbieder_id,aanbieder_naam,software_leverancier,uitwisselprofiel,versie,status,laatst_bijgewerkt
kvk,30112233,Zorggroep De Linden,Nedap,igj-toezicht,1.0,productie,2026-02-01
kvk,30112233,Zorggroep De Linden,Nedap,zorgkantoren-inkoop,1.0,productie,2026-02-01
kvk,30112233,Zorggroep De Linden,Nedap,kwaliteitskader,2.1,productie,2026-02-10
kvk,30112233,Zorggroep De Linden,Nedap,nza-bekostiging,1.0,test,2026-02-10
kvk,44556677,Stichting Thuiszorg West,PinkRoccade,zorgkantoren-inkoop,1.0,productie,2026-01-20
kvk,44556677,Stichting Thuiszorg West,PinkRoccade,actiz-branche,1.0,productie,2026-01-20
kvk,44556677,Stichting Thuiszorg West,PinkRoccade,igj-toezicht,1.0,implementatie,2026-03-01
kvk,55667788,Verpleeghuis Avondrood,Ecare,kwaliteitskader,2.1,productie,2026-02-15
kvk,55667788,Verpleeghuis Avondrood,Ecare,personeelssamenstelling,1.2,productie,2026-02-15
kvk,55667788,Verpleeghuis Avondrood,Ecare,wlz-jaarverantwoording,1.0,productie,2026-02-18
kvk,55667788,Verpleeghuis Avondrood,Ecare,vws-beleid,1.0,uitgefaseerd,2025-11-30
"""
