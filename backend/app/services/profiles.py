"""
profiles.py — Uitwisselprofielen (KIK-V) met volledige metadata en indicatoren.

Pluggable bron: staat RHADIX_PROFILES_URL gezet, dan worden de profielen uit die
API gehaald (zoals Rhadix-validatie ze aanbiedt). Anders valt de service terug op
een ingebouwde set. Elk profiel bevat — conform de KIK-V Architectuur Explainer —
de analyse-vraag, juridische grondslag, doelbinding, autorisatie en terugkoppeling,
en per indicator een definitie en de (gevalideerde) SPARQL-query.
"""
from __future__ import annotations

import copy
import os
from functools import lru_cache
from typing import Optional

import httpx

_AUTORISATIE = ("Gevalideerde vraag, ondertekend door KIK-V Beheer als Verifiable "
                "Credential; geverifieerd door het datastation van de aanbieder.")


def _sparql(code: str) -> str:
    """De (vereenvoudigde) gevalideerde SPARQL-query bij een indicator."""
    return (
        "PREFIX kik: <https://kik-v.nl/ns#>\n"
        "SELECT (AVG(?w) AS ?waarde) WHERE {\n"
        f"  ?o a kik:Observatie ;\n"
        f"     kik:indicator \"{code}\" ;\n"
        "     kik:waarde ?w .\n"
        "}"
    )


_STATIC_PROFILES = [
    {
        "key": "zorgkantoren-inkoop", "label": "Zorgkantoren — Inkoop & contractering",
        "afnemer": "Zorgkantoren", "badge": "ZK", "kleur": "#0e7490", "versie": "1.0",
        "analyse_vraag": "Hoe verhouden personeelsinzet, verzuim en cliënttevredenheid zich per zorgaanbieder, ten behoeve van de zorginkoop?",
        "grondslag": "Wlz-zorginkoop (Wet langdurige zorg, art. 4.2.1).",
        "doelbinding": "Uitsluitend voor contractering en doorontwikkeling van de Wlz-zorginkoop.",
        "terugkoppeling": "Geaggregeerde benchmark wordt teruggekoppeld aan de zorgaanbieder.",
        "indicatoren": [
            {"code": "PERS_RATIO", "label": "Personeel/cliënt-ratio", "eenheid": "fte/cliënt",
             "definitie": "Aantal fte zorgverlenend personeel gedeeld door het aantal cliënten in zorg."},
            {"code": "ZIEKTEVERZUIM", "label": "Ziekteverzuimpercentage", "eenheid": "%",
             "definitie": "Verzuimde kalenderdagen als percentage van het totaal aantal beschikbare dagen."},
            {"code": "CLIENT_TEVREDENHEID", "label": "Cliënttevredenheid (NPS)", "eenheid": "score",
             "definitie": "Net Promoter Score uit het meest recente cliëntervaringsonderzoek."},
        ],
    },
    {
        "key": "igj-toezicht", "label": "IGJ — Toezicht & kwaliteit",
        "afnemer": "Inspectie Gezondheidszorg en Jeugd", "badge": "IGJ", "kleur": "#4338ca", "versie": "1.0",
        "analyse_vraag": "Wat is het beeld van incidenten, BIG-registratie en medicatieveiligheid per aanbieder?",
        "grondslag": "Wet kwaliteit, klachten en geschillen zorg (Wkkgz); Gezondheidswet.",
        "doelbinding": "Risicogestuurd toezicht op de kwaliteit en veiligheid van zorg.",
        "terugkoppeling": "Bevindingen worden gedeeld in het toezichtgesprek met de aanbieder.",
        "indicatoren": [
            {"code": "MELDINGEN_INCIDENT", "label": "Gemelde incidenten (per kwartaal)", "eenheid": "aantal",
             "definitie": "Aantal interne incidentmeldingen (MIC/VIM) over het kwartaal."},
            {"code": "BIG_REGISTRATIE", "label": "BIG-geregistreerd personeel", "eenheid": "%",
             "definitie": "Aandeel zorgverleners met een geldige BIG-registratie."},
            {"code": "MEDICATIE_VEILIGHEID", "label": "Medicatieveiligheidsscore", "eenheid": "score",
             "definitie": "Samengestelde score op basis van medicatiereviews en dubbele controles."},
        ],
    },
    {
        "key": "vws-beleid", "label": "VWS — Beleid & capaciteit",
        "afnemer": "Ministerie van VWS", "badge": "VWS", "kleur": "#1d4ed8", "versie": "1.0",
        "analyse_vraag": "Hoe ontwikkelen wachtlijsten en bezettingsgraad zich, ten behoeve van capaciteitsbeleid?",
        "grondslag": "Beleidsinformatie t.b.v. de stelselverantwoordelijkheid van VWS.",
        "doelbinding": "Macro-beleidsanalyse en capaciteitsplanning langdurige zorg.",
        "terugkoppeling": "Verwerkt in landelijke monitorrapportages.",
        "indicatoren": [
            {"code": "WACHTLIJST", "label": "Cliënten op wachtlijst", "eenheid": "aantal",
             "definitie": "Aantal cliënten met een actieve indicatie dat wacht op plaatsing."},
            {"code": "CAPACITEIT_BEZETTING", "label": "Bezettingsgraad", "eenheid": "%",
             "definitie": "Bezette plaatsen als percentage van de totale beschikbare capaciteit."},
        ],
    },
    {
        "key": "nza-bekostiging", "label": "NZa — Bekostiging & tarieven",
        "afnemer": "Nederlandse Zorgautoriteit", "badge": "NZa", "kleur": "#047857", "versie": "1.0",
        "analyse_vraag": "Hoe verhouden Wlz-omzet en tariefbenutting zich per aanbieder?",
        "grondslag": "Wet marktordening gezondheidszorg (Wmg).",
        "doelbinding": "Bekostiging, tariefonderzoek en doelmatigheidstoezicht.",
        "terugkoppeling": "Verwerkt in tariefbesluiten en monitors.",
        "indicatoren": [
            {"code": "OMZET_WLZ", "label": "Omzet Wlz-zorg", "eenheid": "k€",
             "definitie": "Gerealiseerde omzet uit Wlz-gefinancierde zorg in het boekjaar."},
            {"code": "TARIEF_BENUTTING", "label": "Tariefbenutting", "eenheid": "%",
             "definitie": "Gerealiseerde opbrengst als percentage van het maximaal toegestane tarief."},
        ],
    },
    {
        "key": "actiz-branche", "label": "ActiZ — Branche-informatie",
        "afnemer": "ActiZ", "badge": "ActiZ", "kleur": "#7c3aed", "versie": "1.0",
        "analyse_vraag": "Hoe ontwikkelen personeelsomvang, verloop en stageplaatsen zich in de branche?",
        "grondslag": "Brancherapportage op basis van vrijwillige deelname.",
        "doelbinding": "Branchebrede arbeidsmarkt- en opleidingsanalyse.",
        "terugkoppeling": "Benchmark beschikbaar voor deelnemende leden.",
        "indicatoren": [
            {"code": "MEDEWERKERS", "label": "Aantal medewerkers", "eenheid": "aantal",
             "definitie": "Aantal unieke medewerkers met een actief dienstverband (peildatum einde periode)."},
            {"code": "PERSONEELSVERLOOP", "label": "Personeelsverloop", "eenheid": "%",
             "definitie": "Uitstroom van medewerkers als percentage van het gemiddelde personeelsbestand."},
            {"code": "STAGEPLAATSEN", "label": "Stageplaatsen", "eenheid": "aantal",
             "definitie": "Aantal beschikbaar gestelde stageplaatsen in de periode."},
        ],
    },
    {
        "key": "kwaliteitskader", "label": "Kwaliteitskader Verpleeghuiszorg",
        "afnemer": "Zorginstituut Nederland", "badge": "KK", "kleur": "#b45309", "versie": "2.1",
        "analyse_vraag": "Hoe scoren aanbieders op decubitus, valincidenten en vrijheidsbeperking?",
        "grondslag": "Kwaliteitskader Verpleeghuiszorg (Zorginstituut Nederland).",
        "doelbinding": "Kwaliteitsverbetering en openbare kwaliteitsinformatie.",
        "terugkoppeling": "Opgenomen in het openbaar kwaliteitsbeeld; spiegelinformatie voor de aanbieder.",
        "indicatoren": [
            {"code": "DECUBITUS", "label": "Decubitus prevalentie", "eenheid": "%",
             "definitie": "Aandeel cliënten met decubitus categorie 2 of hoger op de meetdag."},
            {"code": "VALINCIDENTEN", "label": "Valincidenten met letsel", "eenheid": "aantal",
             "definitie": "Aantal geregistreerde valincidenten met letsel in de periode."},
            {"code": "VRIJHEIDSBEPERKING", "label": "Vrijheidsbeperkende maatregelen", "eenheid": "%",
             "definitie": "Aandeel cliënten met een geregistreerde onvrijwillige zorgmaatregel (Wzd)."},
        ],
    },
    {
        "key": "personeelssamenstelling", "label": "Personeelssamenstelling",
        "afnemer": "Zorginstituut Nederland", "badge": "PS", "kleur": "#be185d", "versie": "1.2",
        "analyse_vraag": "Wat is de personeelssamenstelling (niveaumix en externe inhuur) per aanbieder?",
        "grondslag": "Kwaliteitskader Verpleeghuiszorg — onderdeel personeelssamenstelling.",
        "doelbinding": "Inzicht in personeelssamenstelling ten behoeve van kwaliteit.",
        "terugkoppeling": "Spiegelinformatie aan de aanbieder.",
        "indicatoren": [
            {"code": "ZORGNIVEAU_MIX", "label": "Aandeel niveau 3+ zorgverleners", "eenheid": "%",
             "definitie": "Aandeel zorgverlenend personeel op kwalificatieniveau 3 of hoger."},
            {"code": "INHUUR_EXTERN", "label": "Externe inhuur", "eenheid": "%",
             "definitie": "Ingehuurde (niet in loondienst) zorg-uren als percentage van het totaal."},
        ],
    },
    {
        "key": "wlz-jaarverantwoording", "label": "Wlz-jaarverantwoording",
        "afnemer": "CIBG / DigiMV", "badge": "Wlz", "kleur": "#334155", "versie": "1.0",
        "analyse_vraag": "Wat zijn resultaat, solvabiliteit en weerstandsvermogen per aanbieder?",
        "grondslag": "Regeling jaarverantwoording WMG / DigiMV.",
        "doelbinding": "Financiële verantwoording en toezicht.",
        "terugkoppeling": "Openbaar via de jaarverantwoording; geen aparte terugkoppeling.",
        "indicatoren": [
            {"code": "RESULTAAT_BOEKJAAR", "label": "Resultaat boekjaar", "eenheid": "k€",
             "definitie": "Netto resultaat over het boekjaar (baten minus lasten)."},
            {"code": "SOLVABILITEIT", "label": "Solvabiliteit", "eenheid": "%",
             "definitie": "Eigen vermogen als percentage van het balanstotaal."},
            {"code": "WEERSTANDSVERMOGEN", "label": "Weerstandsvermogen", "eenheid": "%",
             "definitie": "Eigen vermogen als percentage van de totale opbrengsten."},
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
        return None


@lru_cache(maxsize=1)
def _load() -> list:
    url = os.getenv("RHADIX_PROFILES_URL")
    if url:
        remote = _fetch_remote(url)
        if remote:
            return remote
    return _STATIC_PROFILES


def list_profiles() -> list:
    """Lichtgewicht overzicht voor de tegels."""
    return [{"key": p["key"], "label": p["label"], "afnemer": p.get("afnemer"),
             "badge": p.get("badge"), "kleur": p.get("kleur"),
             "aantal_indicatoren": len(p["indicatoren"])} for p in _load()]


def get_profile(key: str) -> Optional[dict]:
    """Volledig uitwisselprofiel, met per indicator de SPARQL en de autorisatie."""
    prof = next((p for p in _load() if p["key"] == key), None)
    if not prof:
        return None
    prof = copy.deepcopy(prof)
    prof.setdefault("autorisatie", _AUTORISATIE)
    for ind in prof["indicatoren"]:
        ind.setdefault("sparql", _sparql(ind["code"]))
    return prof


def get_indicators(key: str, codes: Optional[list] = None) -> list:
    prof = get_profile(key)
    if not prof:
        return []
    inds = prof["indicatoren"]
    if codes:
        wanted = set(codes)
        inds = [i for i in inds if i["code"] in wanted]
    return inds
