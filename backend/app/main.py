"""
Rhadix Uitvraag — FastAPI backend
=============================================
Mijlpaal 3: opvraag-flow — uitwisselprofielen, zorgaanbieders,
  uitvragen via (gesimuleerde) datastations en resultaat-export.
"""
from __future__ import annotations

import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.bootstrap import init_db
from app.routers import health, meta, admin, org, profiles, zorgaanbieders, uitvragen, capabilities, external
from app.auth.app_access import require_app_access
from app.auth.router import router as auth_router

APP_VERSION = "0.6.0"

app = FastAPI(title="Rhadix Uitvraag API", version=APP_VERSION)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    init_db()


# Applicatietoegang via de centrale apps-claim (zie auth/app_access.py). Zonder
# token doet de dependency niets, zodat publieke routes ongewijzigd blijven.
#
# /api/auth blijft ongegate, zodat de frontend ook zonder toewijzing /auth/me kan
# ophalen en een verklarende melding kan tonen i.p.v. een blinde 401/403-lus.
#
# external.router is BEWUST niet gekoppeld: die routes bedienen machine-clients
# die met client_credentials authenticeren. Hun autorisatie loopt via de
# serverzijdige clientregistratie en de tenantbinding, niet via de menselijke
# apps-claim.
_app_access = [Depends(require_app_access)]

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(meta.router, prefix="/api", tags=["meta"])
app.include_router(auth_router, prefix="/api/auth")
app.include_router(admin.router, prefix="/api/admin", dependencies=_app_access)
app.include_router(org.router, prefix="/api/org", dependencies=_app_access)
app.include_router(profiles.router, prefix="/api", dependencies=_app_access)
app.include_router(zorgaanbieders.router, prefix="/api", dependencies=_app_access)
app.include_router(uitvragen.router, prefix="/api", dependencies=_app_access)
app.include_router(capabilities.router, prefix="/api", dependencies=_app_access)
app.include_router(external.router, prefix="/api")


@app.get("/api")
def root():
    return {"app": "Rhadix Uitvraag", "edition": "KIK-V", "version": APP_VERSION}
