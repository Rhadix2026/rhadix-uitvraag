"""
KIK-Starter (Rhadix-editie) — FastAPI backend
=============================================
Herbouw van de ZIN KIK-V Starter in de Rhadix-stack (React/Vite + FastAPI +
PostgreSQL + Fuseki + Docker), met de Rhadix huisstijl.

Deze eerste mijlpaal levert de applicatie-shell: health, meta-info en
placeholder-routers voor de KIK-flows (query-flow + beheermodule).
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health, meta

APP_VERSION = "0.1.0"

app = FastAPI(
    title="KIK-Starter API (Rhadix-editie)",
    version=APP_VERSION,
    description="Herbouw van de ZIN KIK-V Starter in de Rhadix-stack.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(meta.router, prefix="/api", tags=["meta"])


@app.get("/api")
def root():
    return {"app": "KIK-Starter", "edition": "Rhadix", "version": APP_VERSION}
