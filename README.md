# Omni-AI

Starter monorepo for the Omni-AI platform described in `SPEC.md`, `SPEC_SUMMARY.md`, and `ARCHITECTURE.md`.

## What is included

- FastAPI backend scaffold with:
  - typed settings
  - health and metrics endpoints
  - collection and document APIs
  - SQLAlchemy-backed persistence with a local SQLite default
- React + Vite frontend shell with route structure matching the product screens
- Docker Compose starter for local development

## Quick start

### Backend

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ./backend
uvicorn omniai.interfaces.http.app:create_app --factory --reload --app-dir backend
```

Backend runs at `http://localhost:9380`.

The backend uses `DB_URL` and defaults to `sqlite:///./omniai-dev.db`, so
collections and documents now persist across restarts in local development.

## Default Dev Credentials

The backend seeds a local bootstrap admin automatically in development:

- email: `admin@omniai.local`
- password: `Admin12345!`

You can override those with `BOOTSTRAP_ADMIN_EMAIL` and
`BOOTSTRAP_ADMIN_PASSWORD`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`.

## Current status

This is an implementation foundation, not the full product yet. It gives us:

- a clean backend package layout aligned with the architecture doc
- a typed API surface we can extend
- a navigable frontend shell for the planned screens
- local development wiring

Next build steps would be persistence, auth, ingestion workers, retrieval, and the agent runtime.
