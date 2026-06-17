"""
datastation.py — Client die een indicatorvraag bij het datastation van een
zorgaanbieder uitzet en het berekende antwoord teruggeeft.

Pluggable: heeft de zorgaanbieder een `datastation_url` (een echt SPARQL-endpoint),
dan wordt de SPARQL-query daarheen gestuurd. Zonder endpoint berekent deze service
een *deterministisch gesimuleerd* antwoord — stabiel per (aanbieder, indicator) —
zodat de volledige flow zonder externe afhankelijkheden werkt en later naadloos
op echte datastations kan worden aangesloten.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

import httpx


@dataclass
class DatastationAntwoord:
    status: str                     # "OK" | "GEEN_DATA" | "FOUT"
    waarde: Optional[float]
    toelichting: Optional[str] = None
    duur_ms: Optional[int] = None   # tijd die het datastation deed over de berekening


def build_sparql(indicator_code: str) -> str:
    """De gevalideerde SPARQL-query die bij een indicator hoort (vereenvoudigd)."""
    return (
        "PREFIX kik: <https://kik-v.nl/ns#>\n"
        "SELECT (COUNT(?o) AS ?teller) (AVG(?w) AS ?waarde) WHERE {\n"
        f"  ?o a kik:Observatie ; kik:indicator \"{indicator_code}\" ; kik:waarde ?w .\n"
        "}"
    )


def _simuleer(zorgaanbieder_key: str, indicator: dict) -> DatastationAntwoord:
    code = indicator["code"]
    eenheid = (indicator.get("eenheid") or "").lower()
    digest = hashlib.sha256(f"{zorgaanbieder_key}:{code}".encode()).digest()
    n = int.from_bytes(digest[:4], "big")

    duur = 150 + (n % 2350)   # gesimuleerde verwerkingstijd: 150–2500 ms

    # ~12% van de combinaties levert geen data (aanbieder heeft de bron niet)
    if n % 100 < 12:
        return DatastationAntwoord("GEEN_DATA", None,
                                   "Bron niet beschikbaar in datastation van deze aanbieder", duur)

    if "%" in eenheid:
        waarde = round(n % 1000 / 10.0, 1)              # 0–100 %
    elif eenheid in ("aantal", "score"):
        waarde = float(n % 500)
    elif "fte" in eenheid:
        waarde = round(0.5 + (n % 100) / 100.0, 2)      # 0.5–1.5
    elif "k€" in eenheid or "€" in eenheid:
        waarde = float(n % 50000)
    else:
        waarde = round(n % 1000 / 10.0, 1)
    return DatastationAntwoord("OK", waarde, duur_ms=duur)


def vraag_indicator(zorgaanbieder, indicator: dict) -> DatastationAntwoord:
    """Stuur de indicatorvraag naar het datastation (echt of gesimuleerd)."""
    url = getattr(zorgaanbieder, "datastation_url", None)
    naam = getattr(zorgaanbieder, "naam", "onbekend")
    if url:
        import time
        t0 = time.monotonic()
        try:
            sparql = build_sparql(indicator["code"])
            resp = httpx.post(f"{url.rstrip('/')}/api/datastation/beantwoord",
                              json={"sparql": sparql}, timeout=12.0)
            resp.raise_for_status()
            dur = int((time.monotonic() - t0) * 1000)
            d = resp.json()
            status = d.get("status")
            if status == "OK" and d.get("waarde") is not None:
                return DatastationAntwoord("OK", float(d["waarde"]), duur_ms=dur)
            if status == "GEEN_DATA":
                return DatastationAntwoord("GEEN_DATA", None, d.get("toelichting") or "Geen data in datastation", dur)
            return DatastationAntwoord("FOUT", None, d.get("toelichting") or "Datastation gaf geen waarde", dur)
        except Exception as exc:
            dur = int((time.monotonic() - t0) * 1000)
            return DatastationAntwoord("FOUT", None, f"Datastation onbereikbaar: {exc}", dur)
    return _simuleer(naam, indicator)


def dien_in(zorgaanbieder, indicator: dict, afnemer: str | None = None) -> dict:
    """Zet de gevalideerde vraag *asynchroon* uit bij het datastation van de
    aanbieder (federatief: de vraag reist naar de bron). Retourneert het
    zaaknummer (query_id); het antwoord wordt later opgehaald na beoordeling."""
    import time
    url = getattr(zorgaanbieder, "datastation_url", None)
    naam = getattr(zorgaanbieder, "naam", "onbekend")
    if not url:
        return {"modus": "sim"}
    t0 = time.monotonic()
    try:
        sparql = build_sparql(indicator["code"])
        resp = httpx.post(
            f"{url.rstrip('/')}/api/datastation/vragen",
            json={"sparql": sparql, "uitwisselprofiel": indicator.get("profiel"),
                  "indicator_code": indicator["code"], "afnemer": afnemer, "zorgaanbieder": naam},
            timeout=12.0)
        resp.raise_for_status()
        dur = int((time.monotonic() - t0) * 1000)
        d = resp.json()
        return {"modus": "async", "query_id": d.get("query_id"), "status": "UITGEZET",
                "duur_ms": dur, "url": url.rstrip('/'),
                "toelichting": f"Uitgezet bij datastation van {naam}; wacht op beoordeling"}
    except Exception as exc:
        dur = int((time.monotonic() - t0) * 1000)
        return {"modus": "async", "query_id": None, "status": "FOUT", "duur_ms": dur,
                "url": url, "toelichting": f"Datastation onbereikbaar: {exc}"}


def haal_resultaat(url: str, query_id: str) -> dict:
    """Haal het resultaat van een uitgezette vraag op bij het datastation."""
    try:
        resp = httpx.get(f"{url.rstrip('/')}/api/datastation/vragen/{query_id}/resultaat", timeout=12.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        return {"status": "FOUT", "toelichting": f"Ophalen mislukt: {exc}"}
