"""
bestemming.py — welke datastation-URL's de server mag aanroepen (B-29).

Uitvraag roept het datastation van een zorgaanbieder aan. Zonder controle is dat
een SSRF-ingang: wie een URL kan zetten, laat de server elk adres benaderen dat
hij bereikt (Docker-netwerk, host-poorten, metadata). Daarom:

1. Alleen URL's die exact op een allowlist staan (na normalisatie):
   - DATASTATION_BESTEMMINGEN          publieke datastations, komma-gescheiden;
   - DATASTATION_INTERNE_BESTEMMINGEN  bewust toegestane interne adressen
                                        (bijv. de twin op staging).
   Leeg = niets toegestaan (fail-closed): elke aanbieder wordt dan gesimuleerd
   of krijgt een foutmelding.
2. Een publieke bestemming moet bij elke aanroep naar uitsluitend publieke
   IP-adressen resolven. De verbinding gaat naar dat gecontroleerde adres (Host
   en TLS-SNI blijven de hostnaam), zodat DNS tussen controle en verbinding niet
   kan omslaan naar een intern adres.
3. Geen redirects, geen proxy uit de omgeving, beperkte antwoordgrootte.

Fouten bevatten details voor de log; aan de gebruiker gaat alleen een generieke
melding (zie `services/datastation.py`).
"""
from __future__ import annotations

import ipaddress
import json
import os
import socket
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit

import httpx

TIMEOUT = 12.0
MAX_ANTWOORD = 64 * 1024
STANDAARDPOORT = {"http": 80, "https": 443}


class NietToegestaan(Exception):
    """De bestemming of het antwoord voldoet niet aan het beleid."""


@dataclass(frozen=True)
class Bestemming:
    url: str          # genormaliseerde basis-URL
    schema: str
    host: str
    poort: int
    intern: bool
    adres: Optional[str] = None   # gecontroleerd IP voor een publieke bestemming


def normaliseer(url: Optional[str]) -> str:
    """Basis-URL in vaste vorm: schema en host in kleine letters, geen
    standaardpoort, geen afsluitende slash. Weigert userinfo, query en fragment."""
    if not url or not isinstance(url, str):
        raise NietToegestaan("lege URL")
    try:
        d = urlsplit(url.strip())
        poort = d.port
    except ValueError as exc:
        raise NietToegestaan(f"ongeldige URL: {exc}") from None
    schema = d.scheme.lower()
    if schema not in STANDAARDPOORT:
        raise NietToegestaan(f"schema '{schema}' niet toegestaan")
    if d.username is not None or d.password is not None or "@" in d.netloc:
        raise NietToegestaan("userinfo in URL")
    if d.query or d.fragment or "?" in url or "#" in url:
        raise NietToegestaan("query of fragment in URL")
    host = (d.hostname or "").lower().rstrip(".")
    if not host:
        raise NietToegestaan("geen host")
    if poort is None or poort == STANDAARDPOORT[schema]:
        hostdeel = f"[{host}]" if ":" in host else host
    else:
        hostdeel = f"[{host}]:{poort}" if ":" in host else f"{host}:{poort}"
    pad = d.path.rstrip("/")
    return f"{schema}://{hostdeel}{pad}"


def _lijst(naam: str) -> set[str]:
    uit = set()
    for deel in os.getenv(naam, "").split(","):
        if deel.strip():
            try:
                uit.add(normaliseer(deel))
            except NietToegestaan:
                pass
    return uit


def is_toegestaan(url: Optional[str]) -> bool:
    """Staat de URL op een allowlist? (zonder DNS; voor opslaan en tonen)"""
    try:
        n = normaliseer(url)
    except NietToegestaan:
        return False
    return n in _lijst("DATASTATION_BESTEMMINGEN") or n in _lijst("DATASTATION_INTERNE_BESTEMMINGEN")


def _publiek(ip: str) -> bool:
    a = ipaddress.ip_address(ip.split("%", 1)[0])
    if isinstance(a, ipaddress.IPv6Address) and a.ipv4_mapped:
        a = a.ipv4_mapped
    return a.is_global and not a.is_multicast


def _resolve(host: str, poort: int) -> list[str]:
    try:
        info = socket.getaddrinfo(host, poort, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise NietToegestaan(f"host niet te resolven: {exc}") from None
    return list(dict.fromkeys(i[4][0] for i in info))


def controleer(url: Optional[str]) -> Bestemming:
    """Controleer een basis-URL vlak vóór gebruik. Gooit NietToegestaan."""
    n = normaliseer(url)
    d = urlsplit(n)
    host = (d.hostname or "").lower()
    poort = d.port or STANDAARDPOORT[d.scheme]
    if n in _lijst("DATASTATION_INTERNE_BESTEMMINGEN"):
        return Bestemming(n, d.scheme, host, poort, intern=True)
    if n not in _lijst("DATASTATION_BESTEMMINGEN"):
        raise NietToegestaan(f"{n} staat niet op de allowlist")
    adressen = _resolve(host, poort)
    if not adressen:
        raise NietToegestaan("host levert geen adres")
    niet_publiek = [a for a in adressen if not _publiek(a)]
    if niet_publiek:
        raise NietToegestaan(f"{host} resolveert naar niet-publiek adres {niet_publiek[0]}")
    return Bestemming(n, d.scheme, host, poort, intern=False, adres=adressen[0])


def verzoek(methode: str, basis_url: str, pad: str, body: Optional[dict] = None,
            token: Optional[str] = None) -> dict:
    """Doe één verzoek naar een toegestane bestemming en geef de JSON terug.

    `pad` begint met '/' en komt uit de eigen code (gevalideerde onderdelen).
    `token` gaat pas mee nadat de bestemming is goedgekeurd (B-28)."""
    b = controleer(basis_url)
    pad_basis = urlsplit(b.url).path
    headers, extensions = {}, {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if b.intern:
        doel = f"{b.url}{pad}"
    else:
        ip = f"[{b.adres}]" if ":" in b.adres else b.adres
        doel = f"{b.schema}://{ip}:{b.poort}{pad_basis}{pad}"
        headers["Host"] = urlsplit(b.url).netloc
        if b.schema == "https":
            extensions["sni_hostname"] = b.host
    with httpx.Client(follow_redirects=False, trust_env=False, timeout=TIMEOUT) as client:
        with client.stream(methode, doel, json=body, headers=headers, extensions=extensions) as resp:
            if resp.is_redirect:
                raise NietToegestaan(f"redirect ({resp.status_code}) geweigerd")
            resp.raise_for_status()
            inhoud = b""
            for blok in resp.iter_bytes():
                inhoud += blok
                if len(inhoud) > MAX_ANTWOORD:
                    raise NietToegestaan("antwoord te groot")
    try:
        data = json.loads(inhoud)
    except ValueError:
        raise NietToegestaan("antwoord is geen JSON") from None
    if not isinstance(data, dict):
        raise NietToegestaan("antwoord is geen JSON-object")
    return data
