# Database and API Handoff

This is the database connection contract for humans and AI coding agents working on KBC Digital Twin.

## The one rule

**Frontend, design, and demo agents connect to the API, never directly to the database.**

The database contains synthetic banking transactions, inferred life facts, and demo credentials. Direct browser/database access would expose data and create an IDOR risk. The FastAPI backend owns authentication, customer scoping, rate limits, and the glass-box evidence rules.

| Role | Connect to | Must not do |
|---|---|---|
| Frontend agent | FastAPI API (`/api/*`) | Use SQLite/PostgreSQL drivers or handle database credentials |
| Backend owner (A) | Local SQLite today; Cloud SQL after the approved migration | Put secrets in the repository or expose the database to the browser |
| Ops/deployment owner | Cloud Run and Cloud SQL service configuration | Share connection strings, passwords, tokens, or the database file |

## Current supported setup: local SQLite

The repository deliberately does **not** contain a database file. `data/kbc_twin.db` is generated locally, is deterministic, and is git-ignored because it is about 300 MB.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python data/generate_db.py
.venv/bin/python -m twin.engine
.venv/bin/python -m api.seed_credentials
cp .env.example .env
.venv/bin/uvicorn api.main:app --reload
```

The API is then available at `http://localhost:8000` and its interactive contract is at `http://localhost:8000/api/docs`.

Smoke test:

```bash
curl http://localhost:8000/api/topics
```

Each developer or coding agent gets the same generated customers and transactions because the generator seed is fixed. Demo passwords are intentionally random on every run and remain in `data/demo_credentials.txt`; never commit, paste, screenshot, or bundle that file.

Re-running `data/generate_db.py` replaces the local database. Run `twin.engine` and `api.seed_credentials` again afterwards.

## How application agents should connect

For local development, use the existing Vite proxy and request relative API paths:

```js
fetch("/api/topics")
```

The frontend is responsible for the bearer token returned by `POST /api/auth/login`, but it must keep that token in memory (or, at most, `sessionStorage`). Never put a token, customer ID, password, or personal data in a URL, log, or `localStorage`.

The complete endpoint, authentication, error-handling, and frontend-security contract is in [`AGENTS.md`](../AGENTS.md#4-api-contract-for-the-frontend). Agents should build against that contract instead of reading database tables.

## Shared cloud demo: target architecture

Cloud SQL for PostgreSQL is the planned shared database. It is **not provisioned or connected in the codebase yet**.

```text
Web/mobile frontend
        |
        | HTTPS, bearer token
        v
Cloud Run: FastAPI API
        |
        | Cloud SQL connector / service identity
        v
Cloud SQL for PostgreSQL
```

When the deployment is ready, frontend agents receive only the public API base URL (or keep using `/api` through the deployed frontend proxy). They do not receive a `DATABASE_URL`, Cloud SQL password, service-account key, or a copy of the database.

## Cloud migration checklist — backend/deployment owner only

The current backend uses `sqlite3` directly. Before moving production/demo traffic to Cloud SQL, the backend owner must complete and verify all of these steps:

1. Add a database adapter that keeps SQLite as the local default and supports a server-only PostgreSQL `DATABASE_URL`.
2. Create an explicit PostgreSQL schema and indexes for the API query paths, especially `customer_id`, `transactions(customer_id, tx_id)`, `twin_profile(customer_id)`, and feedback history.
3. Import generated synthetic data through a one-off migration script or controlled seed job. Do not upload `kbc_twin.db` to GitHub.
4. Run `twin.engine`, credential seeding, and API smoke tests against the target database.
5. Deploy FastAPI to Cloud Run with a dedicated service account and Cloud SQL connector; do not grant public database access.
6. Store `DATABASE_URL`, `TWIN_SECRET`, and `OPENAI_API_KEY` only in server-side secret management. No `VITE_*` variable may contain a secret.
7. Confirm that one customer cannot retrieve another customer's data, then run the Aikido audit.

Until those steps are complete, `data/kbc_twin.db` is the only supported database runtime.

## Copyable task prompt for a colleague agent

> Read `AGENTS.md` and `docs/DATABASE_HANDOFF.md` before changing anything. Build only against the FastAPI API contract. Do not connect directly to SQLite or Cloud SQL, do not request credentials, and do not add keys, tokens, passwords, customer IDs, or database files to the repository.
