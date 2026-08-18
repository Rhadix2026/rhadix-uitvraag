"""api_clients.py — registratie van machine-to-machine clients voor de externe API.

Externe afnemers sluiten aan zonder Rhadix SSO. Ze authenticeren met een eigen
client_id + client_secret (OAuth2 client_credentials), volledig los van
gebruikersaccounts en van RHADIX_ADMIN_PASSWORD.

De registratie komt uit de omgevingsvariabele KSAPI_CLIENTS, per omgeving
aangeleverd uit een GitHub Environment secret. Inhoud is JSON, eventueel
base64-gecodeerd (aanbevolen: bcrypt-hashes bevatten `$`, wat in env-files tot
interpolatieproblemen kan leiden). Dezelfde base64-conventie gebruikt security.py
al voor de RSA-sleutels.

    [
      {
        "client_id":        "afnemer-x",
        "naam":             "Afnemer X",
        "tenant":           "platform",
        "secret_hash":      "<bcrypt>",
        "secret_hash_next": "<bcrypt of null>"
      }
    ]

`tenant` bepaalt de autorisatiegrens en wordt UITSLUITEND server-side uit deze
registratie gelezen. Een client kan zijn tenant dus niet via het tokenverzoek
kiezen of wijzigen.

Rotatie zonder downtime: zet het nieuwe secret als `secret_hash_next`. Beide
secrets worden dan geaccepteerd. Zodra de afnemer is overgestapt, schuift `next`
naar `secret_hash` en vervalt het oude.

Fail-closed: ontbreekt de registratie of is die onbruikbaar, dan levert
`load_clients()` een lege dict en weigert de tokenroute dienst (503).
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

from passlib.context import CryptContext

log = logging.getLogger("rhadix.api_clients")

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# E-mailadres van de service-principal per client. Bewust een niet-routeerbaar
# domein: dit is geen postbus en er hoort nooit post naartoe te gaan.
SERVICE_PRINCIPAL_DOMAIN = "clients.rhadix.invalid"


@dataclass(frozen=True)
class ApiClient:
    client_id: str
    tenant_slug: str
    secret_hash: str
    secret_hash_next: Optional[str] = None
    naam: Optional[str] = None

    @property
    def service_principal_email(self) -> str:
        return f"ksapi+{self.client_id}@{SERVICE_PRINCIPAL_DOMAIN}".lower()

    @property
    def tenant_naam(self) -> str:
        return self.naam or self.tenant_slug


def _decode_registry(raw: str) -> list:
    """Accepteer zowel platte JSON als base64-gecodeerde JSON."""
    raw = raw.strip()
    if not raw:
        return []
    if raw.lstrip().startswith("["):
        return json.loads(raw)
    try:
        return json.loads(base64.b64decode(raw).decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("KSAPI_CLIENTS is geen geldige JSON of base64-JSON") from exc


def load_clients() -> dict[str, ApiClient]:
    """Lees de clientregistratie. Bij ontbreken of fouten: lege dict (fail-closed).

    Bewust bij elke aanroep gelezen en niet op moduleniveau gecached, zodat een
    omgeving zonder herbouw te wijzigen is en tests de registratie kunnen zetten.
    """
    raw = os.getenv("KSAPI_CLIENTS", "")
    if not raw.strip():
        return {}
    try:
        entries = _decode_registry(raw)
    except ValueError as exc:
        log.error("KSAPI_CLIENTS onbruikbaar: %s", exc)
        return {}
    if not isinstance(entries, list):
        log.error("KSAPI_CLIENTS moet een lijst zijn")
        return {}

    clients: dict[str, ApiClient] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            log.error("KSAPI_CLIENTS bevat een niet-object; overgeslagen")
            continue
        client_id = str(entry.get("client_id") or "").strip()
        tenant = str(entry.get("tenant") or "").strip()
        secret_hash = str(entry.get("secret_hash") or "").strip()
        if not client_id or not tenant or not secret_hash:
            log.error("KSAPI_CLIENTS: onvolledige registratie voor %r; overgeslagen",
                      client_id or "<zonder client_id>")
            continue
        nxt = entry.get("secret_hash_next")
        clients[client_id] = ApiClient(
            client_id=client_id,
            tenant_slug=tenant,
            secret_hash=secret_hash,
            secret_hash_next=str(nxt).strip() if nxt else None,
            naam=(str(entry["naam"]).strip() if entry.get("naam") else None),
        )
    return clients


def verify_client_secret(client: ApiClient, secret: str) -> bool:
    """Controleer het secret tegen het huidige én het volgende hash (rotatie-overlap)."""
    if not secret:
        return False
    for candidate in (client.secret_hash, client.secret_hash_next):
        if not candidate:
            continue
        try:
            if _pwd_context.verify(secret, candidate):
                return True
        except Exception:  # onbruikbare hash mag geen 500 opleveren
            log.error("Onbruikbare secret-hash voor client %s", client.client_id)
    return False


def hash_secret(secret: str) -> str:
    """Hulpfunctie om een secret te hashen bij het aanmaken/roteren van een client."""
    return _pwd_context.hash(secret)
