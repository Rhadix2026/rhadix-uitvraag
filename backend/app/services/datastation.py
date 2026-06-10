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

    # ~12% van de combinaties levert geen data (aanbieder heeft de bron niet)
    if n % 100 < 12:
        return DatastationAntwoord("GEEN_DATA", None,
                                   "Bron niet beschikbaar in datastation van deze aanbieder")

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
    return DatastationAntwoord("OK", waarde)


def vraag_indicator(zorgaanbieder, indicator: dict) -> DatastationAntwoord:
    """Stuur de indicatorvraag naar het datastation (echt of gesimuleerd)."""
    url = getattr(zorgaanbieder, "datastation_url", None)
    naam = getattr(zorgaanbieder, "naam", "onbekend")
    if url:
        try:
            sparql = build_sparql(indicator["code"])
            resp = httpx.post(url, data={"query": sparql},
                              headers={"Accept": "application/sparql-results+json"}, timeout=10.0)
            resp.raise_for_status()
            rows = resp.json().get("results", {}).get("bindings", [])
            if not rows or "waarde" not in rows[0]:
                return DatastationAntwoord("GEEN_DATA", None, "Datastation gaf geen waarde terug")
            return DatastationAntwoord("OK", float(rows[0]["waarde"]["value"]))
        except Exception as exc:
            return DatastationAntwoord("FOUT", None, f"Datastation onbereikbaar: {exc}")
    return _simuleer(naam, indicator)
