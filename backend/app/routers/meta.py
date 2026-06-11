import os

from fastapi import APIRouter

router = APIRouter()


@router.get("/meta")
def meta():
    """Applicatie-metadata voor de frontend-shell (omgeving, versie, features)."""
    return {
        "name": "Rhadix Uitvraag",
        "edition": "KIK-V",
        "version": "0.6.0",
        "environment": os.getenv("KIK_ENV", "development"),
        "modules": [
            {"key": "query-flow", "label": "Opvragen", "status": "available"},
            {"key": "zorgaanbieders", "label": "Zorgaanbieders", "status": "available"},
            {"key": "results", "label": "Resultaten", "status": "available"},
            {"key": "analyse", "label": "Analyse & Monitor", "status": "available"},
            {"key": "dekking", "label": "Uitwisselprofiel-dekking", "status": "available"},
            {"key": "user-mgmt", "label": "Gebruikersbeheer", "status": "available"},
        ],
    }
