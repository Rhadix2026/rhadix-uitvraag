# Rhadix Uitvraag

De afnemer-applicatie binnen het KIK-V-stelsel (opvolger van de ZIN KIK-V Starter), in de **Rhadix-stack**
(React/Vite · FastAPI · PostgreSQL · Fuseki · Docker), met de Rhadix huisstijl.

> Status: **mijlpaal 7 — live profielenbibliotheek**. De uitwisselprofielen + indicatoren
> komen nu live uit de gedeelde Rhadix-validation bibliotheek (`VALIDATION_API_URL`),
> met lokale cache en ingebouwde fallback — één bron om te onderhouden. Daarvoor:
> profieldekking-registry (m6), Analyse/Monitor (m5), Rhadix Uitvraag (m4),
> opvraag-flow (m3), gebruikersbeheer (m2), shell (m1). Zie [ARCHITECTUUR.md](ARCHITECTUUR.md).

## Stack
| Laag | Technologie |
|------|-------------|
| Frontend | React 18 + Vite, React Router, Oxanium-font, Rhadix-palet |
| Backend | FastAPI (Python 3.12) |
| Database | PostgreSQL 16 |
| Triple store | Apache Jena Fuseki 5.1 |
| Deploy | Docker / docker-compose |

## Lokaal draaien
```bash
# volledige stack (frontend, backend, db, fuseki)
docker compose up -d --build
# frontend: http://localhost:5173   ·   backend: http://localhost:8000/api/health
```

Of los, voor ontwikkeling:
```bash
# backend
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload
# frontend
cd frontend && npm install && npm run dev
```

## Structuur
```
rhadix-uitvraag/
├─ frontend/         React/Vite app (Rhadix UI-shell)
│  └─ src/
│     ├─ components/ Brand (KIK-logo), UI (Nav, Card, Button…)
│     ├─ pages/      Login, Home, QueryFlow, Registration, Results
│     └─ services/   api.js
├─ backend/          FastAPI (health, meta + toekomstige KIK-routers)
└─ docker-compose.yml
```

## Modules (gepland)
- **Opvragen** — dataset → zorgaanbieders → uitwisselprofiel → SPARQL → resultaten
- **Beheer / Registratie** — organisaties, endpoints, DID
- **Resultaten** — inzien, vergelijken, exporteren

Gebaseerd op de ZIN KIK-V Starter (`nl.kik.starter`) en de KIK-V Beheermodule.

## Deployment (DTAP)

De app gebruikt een DTAP-flow met branches `develop → staging → main`, GitHub
Actions voor tests en deploy, en gescheiden staging/productie-omgevingen
(eigen poorten zodat KIK naast de Rhadix-validation-app draait). Zie
[DEPLOYMENT.md](DEPLOYMENT.md) voor het volledige proces en de vereiste secrets.
