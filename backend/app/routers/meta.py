import os

from fastapi import APIRouter

router = APIRouter()


@router.get("/meta")
def meta():
    """Applicatie-metadata voor de frontend-shell (omgeving, versie, features)."""
    return {
        "name": "KIK-Starter",
        "edition": "Rhadix",
        "version": "0.1.0",
        "environment": os.getenv("KIK_ENV", "development"),
        "modules": [
            {"key": "query-flow", "label": "Opvragen", "status": "planned"},
            {"key": "registration", "label": "Beheer / Registratie", "status": "planned"},
        ],
    }
