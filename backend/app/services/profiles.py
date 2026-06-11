"""
profiles.py — Uitwisselprofielen, live uit de Rhadix-validation profielenbibliotheek.

Eén bron: staat VALIDATION_API_URL gezet, dan worden de profielen + indicatoren
opgehaald uit de validation-app (`GET /api/profiles/` en `/api/profiles/{bestand}`),
getransformeerd naar de shape van Rhadix Uitvraag, en lokaal gecachet. Bij een
storing valt de service terug op de cache en daarna op een ingebouwde set, zodat
de app altijd blijft draaien (ook in dev/CI zonder validation-API).
"""
from __future__ import annotations

import copy
import json
import os
import pathlib
import re
from typing import Optional

import httpx

VALIDATION_API_URL = os.getenv("VALIDATION_API_URL", "").rstrip("/")
CACHE_DIR = pathlib.Path(os.getenv("PROFILES_CACHE_DIR", "/tmp/uitvraag_profiles_cache"))
_TIMEOUT = float(os.getenv("PROFILES_HTTP_TIMEOUT", "8"))

_AUTORISATIE = ("Gevalideerde vraag, ondertekend door KIK-V Beheer als Verifiable "
                "Credential; geverifieerd door het datastation van de aanbieder.")

# Context per afnemer (best-effort; de bibliotheek levert dit niet mee).
_AFNEMER = {
    "ActiZ":      ("ActiZ", "ActiZ", "#7c3aed"),
    "IGJ":        ("Inspectie Gezondheidszorg en Jeugd", "IGJ", "#4338ca"),
    "VWS":        ("Ministerie van VWS", "VWS", "#1d4ed8"),
    "NZa":        ("Nederlandse Zorgautoriteit", "NZa", "#047857"),
    "Zorgkantoren": ("Zorgkantoren", "ZK", "#0e7490"),
}
_CONTEXT = {
    "ActiZ": ("Brancherapportage op basis van deelname.", "Branchebrede analyse.", "Benchmark voor leden."),
    "IGJ": ("Wet kwaliteit, klachten en geschillen zorg (Wkkgz).", "Risicogestuurd toezicht.", "Gedeeld in het toezichtgesprek."),
    "VWS": ("Beleidsinformatie t.b.v. stelselverantwoordelijkheid.", "Macro-beleid en capaciteit.", "Landelijke monitorrapportages."),
    "NZa": ("Wet marktordening gezondheidszorg (Wmg).", "Bekostiging en tariefonderzoek.", "Tariefbesluiten en monitors."),
    "Zorgkantoren": ("Wlz-zorginkoop.", "Contractering en zorginkoop.", "Benchmark aan de aanbieder."),
}


def _afnemer_info(name: str):
    n = re.sub(r"^uitwisselprofiel\s+", "", name.strip(), flags=re.I)
    low = n.lower()
    if low.startswith("actiz"):        key = "ActiZ"
    elif low.startswith("igj"):        key = "IGJ"
    elif low.startswith("ministerie van vws") or low.startswith("vws"): key = "VWS"
    elif low.startswith("nza"):        key = "NZa"
    elif low.startswith("zorgkantor"): key = "Zorgkantoren"
    else:                              key = None
    if key:
        afnemer, badge, kleur = _AFNEMER[key]
        return n, afnemer, badge, kleur, key
    return n, (n.split()[0] if n else "?"), (n[:3].upper() if n else "?"), "#334155", None


def _natural(idstr: str):
    return [int(p) if p.isdigit() else p for p in re.split(r"[.\-]", idstr)]


# ── Cache helpers ────────────────────────────────────────────────────────────
def _cache_write(name: str, data) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (CACHE_DIR / name).write_text(json.dumps(data, ensure_ascii=False))
    except Exception:
        pass


def _cache_read(name: str):
    try:
        return json.loads((CACHE_DIR / name).read_text())
    except Exception:
        return None


# ── Transformaties validation → onze shape ───────────────────────────────────
def _summary_from_validation(item: dict) -> dict:
    name = item.get("name") or item.get("filename", "")
    label, afnemer, badge, kleur, _ = _afnemer_info(name)
    key = (item.get("filename") or name).removesuffix(".json")
    return {"key": key, "label": label, "afnemer": afnemer, "badge": badge, "kleur": kleur,
            "versie": item.get("version"), "aantal_indicatoren": item.get("indicator_count", 0)}


def _detail_from_validation(data: dict) -> dict:
    name = data.get("name", "")
    label, afnemer, badge, kleur, akey = _afnemer_info(name)
    grondslag, doelbinding, terugkoppeling = _CONTEXT.get(akey, ("", "", ""))
    inds = []
    for iid, ind in (data.get("indicators") or {}).items():
        if str(iid).startswith("-"):   # bv. -INDEX
            continue
        meta = ind.get("metadata", {})
        files = ind.get("files", {})
        sparql = ((files.get("sparql") or {}).get("content") or "").strip()
        inds.append({
            "code": iid, "label": meta.get("title") or iid, "eenheid": "",
            "definitie": (meta.get("description") or "").strip(),
            "sparql": sparql,
        })
    inds.sort(key=lambda x: _natural(x["code"]))
    return {
        "key": (data.get("filename") or name).removesuffix(".json"),
        "label": label, "afnemer": afnemer, "badge": badge, "kleur": kleur,
        "versie": data.get("version"), "bron": data.get("source"),
        "analyse_vraag": None, "grondslag": grondslag, "doelbinding": doelbinding,
        "terugkoppeling": terugkoppeling, "autorisatie": _AUTORISATIE,
        "indicatoren": inds,
    }


# ── Publieke API ─────────────────────────────────────────────────────────────
def _live_list() -> Optional[list]:
    if not VALIDATION_API_URL:
        return None
    try:
        r = httpx.get(f"{VALIDATION_API_URL}/api/profiles/", timeout=_TIMEOUT)
        r.raise_for_status()
        items = r.json()
        summaries = [_summary_from_validation(it) for it in items]
        _cache_write("_list.json", summaries)
        return summaries
    except Exception:
        return _cache_read("_list.json")


def _live_detail(key: str) -> Optional[dict]:
    if not VALIDATION_API_URL:
        return None
    try:
        r = httpx.get(f"{VALIDATION_API_URL}/api/profiles/{key}.json", timeout=_TIMEOUT)
        r.raise_for_status()
        prof = _detail_from_validation(r.json())
        _cache_write(f"{key}.json", prof)
        return prof
    except Exception:
        return _cache_read(f"{key}.json")


def list_profiles() -> list:
    live = _live_list()
    if live:
        return live
    return [{"key": p["key"], "label": p["label"], "afnemer": p.get("afnemer"),
             "badge": p.get("badge"), "kleur": p.get("kleur"), "versie": p.get("versie"),
             "aantal_indicatoren": len(p["indicatoren"])} for p in _BUILTIN]


def get_profile(key: str) -> Optional[dict]:
    live = _live_detail(key)
    if live:
        return live
    prof = next((p for p in _BUILTIN if p["key"] == key), None)
    if not prof:
        return None
    prof = copy.deepcopy(prof)
    prof.setdefault("autorisatie", _AUTORISATIE)
    for ind in prof["indicatoren"]:
        ind.setdefault("sparql", _builtin_sparql(ind["code"]))
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


# ── Ingebouwde fallback (dev/CI/offline) ─────────────────────────────────────
def _builtin_sparql(code: str) -> str:
    return ("PREFIX kik: <https://kik-v.nl/ns#>\n"
            "SELECT (AVG(?w) AS ?waarde) WHERE {\n"
            f"  ?o a kik:Observatie ; kik:indicator \"{code}\" ; kik:waarde ?w .\n" "}")


_BUILTIN = [
    {"key": "zorgkantoren-inkoop", "label": "Zorgkantoren — Inkoop & contractering",
     "afnemer": "Zorgkantoren", "badge": "ZK", "kleur": "#0e7490", "versie": "1.0",
     "analyse_vraag": "Personeelsinzet, verzuim en cliënttevredenheid per aanbieder.",
     "grondslag": "Wlz-zorginkoop.", "doelbinding": "Contractering Wlz.", "terugkoppeling": "Benchmark aan de aanbieder.",
     "indicatoren": [
         {"code": "PERS_RATIO", "label": "Personeel/cliënt-ratio", "eenheid": "fte/cliënt", "definitie": "Fte zorgpersoneel per cliënt."},
         {"code": "ZIEKTEVERZUIM", "label": "Ziekteverzuimpercentage", "eenheid": "%", "definitie": "Verzuimde dagen als percentage."},
         {"code": "CLIENT_TEVREDENHEID", "label": "Cliënttevredenheid (NPS)", "eenheid": "score", "definitie": "NPS uit cliëntervaringsonderzoek."}]},
    {"key": "igj-toezicht", "label": "IGJ — Toezicht & kwaliteit",
     "afnemer": "Inspectie Gezondheidszorg en Jeugd", "badge": "IGJ", "kleur": "#4338ca", "versie": "1.0",
     "analyse_vraag": "Incidenten, BIG-registratie en medicatieveiligheid.",
     "grondslag": "Wkkgz.", "doelbinding": "Risicogestuurd toezicht.", "terugkoppeling": "Toezichtgesprek.",
     "indicatoren": [
         {"code": "MELDINGEN_INCIDENT", "label": "Gemelde incidenten (per kwartaal)", "eenheid": "aantal", "definitie": "Interne incidentmeldingen."},
         {"code": "BIG_REGISTRATIE", "label": "BIG-geregistreerd personeel", "eenheid": "%", "definitie": "Aandeel met geldige BIG-registratie."},
         {"code": "MEDICATIE_VEILIGHEID", "label": "Medicatieveiligheidsscore", "eenheid": "score", "definitie": "Score medicatiereviews."}]},
    {"key": "vws-beleid", "label": "VWS — Beleid & capaciteit",
     "afnemer": "Ministerie van VWS", "badge": "VWS", "kleur": "#1d4ed8", "versie": "1.0",
     "analyse_vraag": "Wachtlijsten en bezettingsgraad.",
     "grondslag": "Beleidsinformatie VWS.", "doelbinding": "Capaciteitsplanning.", "terugkoppeling": "Monitorrapportages.",
     "indicatoren": [
         {"code": "WACHTLIJST", "label": "Cliënten op wachtlijst", "eenheid": "aantal", "definitie": "Cliënten wachtend op plaatsing."},
         {"code": "CAPACITEIT_BEZETTING", "label": "Bezettingsgraad", "eenheid": "%", "definitie": "Bezette plaatsen percentage."}]},
    {"key": "nza-bekostiging", "label": "NZa — Bekostiging & tarieven",
     "afnemer": "Nederlandse Zorgautoriteit", "badge": "NZa", "kleur": "#047857", "versie": "1.0",
     "analyse_vraag": "Wlz-omzet en tariefbenutting.",
     "grondslag": "Wmg.", "doelbinding": "Bekostiging.", "terugkoppeling": "Tariefbesluiten.",
     "indicatoren": [
         {"code": "OMZET_WLZ", "label": "Omzet Wlz-zorg", "eenheid": "k€", "definitie": "Omzet uit Wlz-zorg."},
         {"code": "TARIEF_BENUTTING", "label": "Tariefbenutting", "eenheid": "%", "definitie": "Opbrengst t.o.v. max tarief."}]},
    {"key": "actiz-branche", "label": "ActiZ — Branche-informatie",
     "afnemer": "ActiZ", "badge": "ActiZ", "kleur": "#7c3aed", "versie": "1.0",
     "analyse_vraag": "Personeelsomvang, verloop en stageplaatsen.",
     "grondslag": "Brancherapportage.", "doelbinding": "Arbeidsmarktanalyse.", "terugkoppeling": "Benchmark voor leden.",
     "indicatoren": [
         {"code": "MEDEWERKERS", "label": "Aantal medewerkers", "eenheid": "aantal", "definitie": "Medewerkers met dienstverband."},
         {"code": "PERSONEELSVERLOOP", "label": "Personeelsverloop", "eenheid": "%", "definitie": "Uitstroom percentage."},
         {"code": "STAGEPLAATSEN", "label": "Stageplaatsen", "eenheid": "aantal", "definitie": "Beschikbare stageplaatsen."}]},
    {"key": "kwaliteitskader", "label": "Kwaliteitskader Verpleeghuiszorg",
     "afnemer": "Zorginstituut Nederland", "badge": "KK", "kleur": "#b45309", "versie": "2.1",
     "analyse_vraag": "Decubitus, valincidenten en vrijheidsbeperking.",
     "grondslag": "Kwaliteitskader Verpleeghuiszorg.", "doelbinding": "Kwaliteitsverbetering.", "terugkoppeling": "Openbaar kwaliteitsbeeld.",
     "indicatoren": [
         {"code": "DECUBITUS", "label": "Decubitus prevalentie", "eenheid": "%", "definitie": "Cliënten met decubitus ≥cat.2."},
         {"code": "VALINCIDENTEN", "label": "Valincidenten met letsel", "eenheid": "aantal", "definitie": "Valincidenten met letsel."},
         {"code": "VRIJHEIDSBEPERKING", "label": "Vrijheidsbeperkende maatregelen", "eenheid": "%", "definitie": "Cliënten met onvrijwillige zorg (Wzd)."}]},
    {"key": "personeelssamenstelling", "label": "Personeelssamenstelling",
     "afnemer": "Zorginstituut Nederland", "badge": "PS", "kleur": "#be185d", "versie": "1.2",
     "analyse_vraag": "Niveaumix en externe inhuur.",
     "grondslag": "Kwaliteitskader — personeel.", "doelbinding": "Inzicht personeelssamenstelling.", "terugkoppeling": "Spiegelinformatie.",
     "indicatoren": [
         {"code": "ZORGNIVEAU_MIX", "label": "Aandeel niveau 3+ zorgverleners", "eenheid": "%", "definitie": "Personeel niveau 3 of hoger."},
         {"code": "INHUUR_EXTERN", "label": "Externe inhuur", "eenheid": "%", "definitie": "Ingehuurde uren percentage."}]},
    {"key": "wlz-jaarverantwoording", "label": "Wlz-jaarverantwoording",
     "afnemer": "CIBG / DigiMV", "badge": "Wlz", "kleur": "#334155", "versie": "1.0",
     "analyse_vraag": "Resultaat, solvabiliteit en weerstandsvermogen.",
     "grondslag": "Regeling jaarverantwoording WMG.", "doelbinding": "Financiële verantwoording.", "terugkoppeling": "Openbaar via jaarverantwoording.",
     "indicatoren": [
         {"code": "RESULTAAT_BOEKJAAR", "label": "Resultaat boekjaar", "eenheid": "k€", "definitie": "Netto resultaat boekjaar."},
         {"code": "SOLVABILITEIT", "label": "Solvabiliteit", "eenheid": "%", "definitie": "Eigen vermogen / balanstotaal."},
         {"code": "WEERSTANDSVERMOGEN", "label": "Weerstandsvermogen", "eenheid": "%", "definitie": "Eigen vermogen / opbrengsten."}]},
]


def clear_cache() -> None:
    """Verwijder de lokale profielcache (forceert verse fetch bij de volgende call)."""
    import shutil
    try:
        shutil.rmtree(CACHE_DIR)
    except FileNotFoundError:
        pass
    except Exception:
        pass


def source_info() -> dict:
    return {"live": bool(VALIDATION_API_URL), "url": VALIDATION_API_URL or None}
