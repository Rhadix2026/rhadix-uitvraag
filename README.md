# Rhadix Uitvraag

De afnemer-applicatie binnen het KIK-V-stelsel (opvolger van de ZIN KIK-V Starter), in de **Rhadix-stack**
(React/Vite · FastAPI · PostgreSQL · Fuseki · Docker), met de Rhadix huisstijl.

> Status: **mijlpaal 6 — profieldekking**. Naast de shell (m1), gebruikersbeheer (m2),
> de opvraag-flow (m3), de hernoeming naar **Rhadix Uitvraag** (m4) en het
> **Analyse/Monitor**-dashboard (m5) is er nu een **uitwisselprofiel-registry** (m6):
> per zorgaanbieder welke profielen + versie + status zijn geïmplementeerd
> (CSV-import door beheer), met filtering in Opvragen (alleen 'productie') en een
> doorzoekbaar dekkings-inzichtsscherm. Zie [ARCHITECTUUR.md](ARCHITECTUUR.md).

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
