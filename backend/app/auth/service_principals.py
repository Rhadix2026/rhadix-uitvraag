"""service_principals.py — het account waarop een machine-client handelt.

De externe API autoriseert op tenant (`Uitvraag.tenant_id == current.tenant_id`).
Een clienttoken heeft dus een principal met een tenant nodig. Die principal is
bewust minimaal:

  * `password_hash = None` — er is geen wachtwoord, dus lokale login is onmogelijk,
    ook als LOCAL_LOGIN_ENABLED ooit weer aan zou gaan;
  * rol `ORG_USER` — de laagste rol; de externe routes filteren op tenant, niet op
    rol, dus een clienttoken draagt geen beheerdersrechten mee;
  * de tenant komt uit de serverzijdige clientregistratie, nooit uit het verzoek.

Idempotent: bij herhaald aanroepen wordt niets gedupliceerd en worden bestaande
records niet overschreven, afgezien van het terugzetten van de minimale rechten.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.auth.api_clients import ApiClient
from app.models.auth_models import Tenant, User, UserRole

log = logging.getLogger("rhadix.api_clients")


def ensure_service_principal(db: Session, client: ApiClient) -> User:
    """Borg tenant + service-principal voor een geregistreerde client."""
    tenant = db.query(Tenant).filter(Tenant.slug == client.tenant_slug).first()
    if not tenant:
        tenant = Tenant(id=uuid.uuid4(), slug=client.tenant_slug,
                        name=client.tenant_naam, is_active=True)
        db.add(tenant)
        db.flush()
        log.info("Tenant %s aangemaakt voor API-client %s", client.tenant_slug, client.client_id)

    email = client.service_principal_email
    principal = db.query(User).filter(User.email == email).first()
    if not principal:
        principal = User(id=uuid.uuid4(), tenant_id=tenant.id, email=email,
                         full_name=f"API-client {client.naam or client.client_id}",
                         password_hash=None, role=UserRole.ORG_USER, is_active=True)
        db.add(principal)
        log.info("Service-principal aangemaakt voor API-client %s", client.client_id)
    else:
        # Minimale rechten afdwingen en de tenantbinding volgen uit de registratie.
        principal.password_hash = None
        principal.role = UserRole.ORG_USER
        principal.is_active = True
        principal.tenant_id = tenant.id
    db.commit()
    db.refresh(principal)
    return principal
