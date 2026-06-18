# CLAUDE.md — Rhadix Uitvraag (Rhadix-editie) projectgeheugen

Lees dit bestand aan het begin van elke sessie. Werk de sessie-log bij aan het eind.

## Project
Herbouw van de **ZIN KIK-V Starter** in de **Rhadix-stack**, met Rhadix look & feel.
- **Repo:** https://github.com/Rhadix2026/rhadix-uitvraag
- **Stack:** React/Vite (frontend), FastAPI (backend), PostgreSQL, Apache Jena Fuseki, Docker
- **Zusterproject:** Rhadix-datavalidatie (zelfde huisstijl, palet, Oxanium-font)

## Bron-materiaal
Twee officiële ZIN-zips als basis (AES-versleuteld, niet in repo):
- `kik-v-starter` — Java 17 / Spring Boot, modules commons/central/decentral/rest-api,
  Apache Jena/Fuseki, Keycloak, SHACL, LRZa (SOAP), Angular-frontend (query-flow).
- `kik-v-registration` — Angular 8 + Java beheermodule (organisatie/DID-registratie).
Aanpak: **volledig herbouwen** in de Rhadix-stack (geen Java/Angular).

## Huisstijl (overgenomen van Rhadix)
- Palet: `--blue/#1A2847` (navy), `--blue-dark/#0F1A30`, `--accent/#6FA8D0`, `--blue-mid/#B8D4EA`.
- Font: **Oxanium** (lokaal in `frontend/public/fonts`, OFL).
- Logo: **Rhadix boom-logo** (`/rhadix-logo.jpg`) in de nav met home-functie + '← Terug'-knop, gelijk aan Datavalidatie (sinds 2026-06-17, v0.7.0). Boom-decoratie op de login-hero (`/rhadix-boom.jpg`).
- Componenten in `components/UI.jsx`: Nav, Page, PageTitle, Card, BtnPrimary, StatusDot.

## Structuur
- `frontend/src/App.jsx` — React Router shell + demo-auth guard.
- `frontend/src/pages/` — Login, Home, QueryFlow, Registration, Results, Placeholder, NotFound.
- `backend/app/main.py` — FastAPI, CORS, routers health + meta.
- `docker-compose.yml` — db + fuseki + backend + frontend.

## Branch-strategie & deployen
| Branch | Omgeving | Poorten (fe/be) | Deploy |
|--------|----------|-----------------|--------|
| `staging` | Staging | 5177 / 8013 | push = automatisch |
| `v*.*.*` tag op `main` | Productie (`uitvraag.rhadix.nl`) | 5176 / 8012 | GitHub Actions + handmatige goedkeuring |

- Werk in `/tmp`-clone (niet de gemounte map). Na merge naar main ook staging uitlijnen.
- **Huidige versie:** v0.7.0
- Auth: `_seed_platform_admin` borgt `admin@rhadix.nl` **niet-destructief** (geen TRUNCATE); `AUTH_RESET=0` slaat over.

## Roadmap
1. ✅ Applicatie-shell (huisstijl, nav, login-demo, health/meta).
2. Auth (JWT, zoals Rhadix) + Postgres-modellen.
3. Opvragen-flow: dataset → zorgaanbieders → uitwisselprofiel → SPARQL (Fuseki) → resultaten.
4. Beheer/registratiemodule.
5. Resultaten + export.

## Sessie-log
| Datum | Wijziging |
|-------|-----------|
| 2026-06-17 | v0.7.0 RELEASE: Zorgaanbieders + CSV-import en async uitvraag-flow naar productie. Nav in Rhadix-huisstijl (boom-logo + home + '← Terug'). Login-hero boom-decoratie. Destructieve `TRUNCATE`-auth verwijderd → niet-destructieve admin-bootstrap. 16 tests groen. Prod-domein uitvraag.rhadix.nl via nginx (5176/8012). |
| 2026-06-09 | Mijlpaal 2: **gebruikersbeheer** met multi-tenant hiërarchie (PLATFORM_ADMIN → ORG_ADMIN → ORG_USER), zoals Rhadix-validatie. Backend: SQLAlchemy (Tenant/User, portable GUID), bcrypt + JWT + wachtwoordsterkte, seed platform-admin uit env, routers auth/admin/org (organisaties + gebruikers CRUD, rolhandhaving). Frontend: echte login, rol-gebaseerde nav, Gebruikersbeheer-pagina (eigen org) + Organisaties-pagina (platform) met aanmaken/deactiveren/wachtwoord-reset. Backend end-to-end getest (SQLite), frontend bouwt schoon. Compose-env: JWT_SECRET_KEY + KIK_ADMIN_*.
| 2026-06-09 | Repo opgezet. Mijlpaal 1: monorepo-scaffold (React/Vite + FastAPI + Postgres + Fuseki + Docker) en Rhadix UI-shell (palet, Oxanium, KIK-wordmerk, Nav, Home met module-kaarten, demo-login, placeholder-pagina's voor de KIK-flows). Frontend bouwt schoon, backend serveert /api/health + /api/meta. |
