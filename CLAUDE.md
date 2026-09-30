# CLAUDE.md

Read `AGENTS.md`. It is the single source of truth for this repo (project, repo map, run commands, API contract, screens, security and working rules).

The three hardest rules:

1. **Never commit secrets or private data.** `.env`, `data/*.db`, `data/demo_credentials.txt` and any API key, password or token stay local. Never print or paste them either.
2. **Identity comes only from the bearer token.** Never send or accept a `customer_id` on `/api/me/*`, and never put ids, tokens or personal data in URLs.
3. **Don't edit `twin/`, `api/` or `data/generate_db.py` without coordinating with their owner (person A).** Propose API changes instead.
