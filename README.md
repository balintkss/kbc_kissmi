# Kate+ — KBC’s customer-controlled financial co-pilot

> Tectonic Hackathon · KBC challenge: *a scalable personalization approach that fundamentally strengthens the relationship between KBC and its customers.*

## The idea in one line

**Kate+** is the customer-facing co-pilot. Its **Digital Twin** is the explainable memory layer underneath: a customer-controlled picture of financial context that lets every channel (app, website, adviser, notifications) help without making the customer explain themselves again.

> **Production boundary:** this repository is a synthetic proof of the pipeline. A real KBC rollout would infer only non-sensitive financial context, let the customer confirm a neutral household change, and never infer health, mental-health, pregnancy or other special-category data from transactions. No inferred fact can drive marketing, pricing, eligibility or an automated financial decision without the customer’s explicit step and the applicable KBC process.

## Why this, and not "another feature"

KBC is already far ahead: Kate has 6M users, proactive nudges in 140+ situations, budgets, subscription overviews and duplicate-payment alerts. Everyone will build "categorize transactions → recommend a product". We don't compete with that — we build the layer underneath it:

| Today (typical bank) | The digital twin |
|---|---|
| Knows *transactions* | Knows *facts about your life* — with confidence and proof |
| Each trigger stands alone | One shared context, reused by every channel |
| Shows every product variant | **Highlights the one that fits you** and says why |
| Pushes offers | Pushes **help** first; holds back sales when you're under money stress |
| Hidden profiling | Glass box: you see what KBC thinks and can correct it |

### The chain: signal → fact → implication → plan

```
Fuel purchase ─► FACT  owns a car (petrol, since 13 Jun 2026, 90% confident, 7 transactions as evidence)
                 └► IMPLIES  maintenance ≈ €650/yr · road tax ≈ €250/yr · inspection · insurance at Ethias (not KBC)
                      └► PLAN  reserve €80/month on payday
                           └► EXPERIENCE  car-insurance page highlights Mini-omnium: "for your €11,500 second-hand car…"
```

### Two-way communication

- **Push (the system attracts the user)** — on salary day: *"€2,850 arrives on 23 Oct. Bills €1,458, set aside €131, save €200 — that leaves €151/week to spend freely."* Plus life-moment messages (new car, baby, move, new job) — ranked, max 2 pushes, and sales messages are **held back** if the customer shows money stress.
- **Pull (the user asks the system)** — the customer asks *"Can I afford a €1,200 holiday in August?"* and the answer uses the twin's context: salary day, bills, reserves, buffer. No forms, no follow-up questions.

### Kate, with the twin as her memory (`twin/assistant.py`)

KBC's Kate runs on GPT-4.1, so we mimic her on the same model — but she now *knows* the customer:

- The system prompt carries a compact twin (facts, implications, payday plan, recurring bills).
- **The LLM never does the maths.** It calls tools that compute on the twin: `check_affordability`, `spending_summary`, `recommend_product` (the same one-highlight logic as the web/app pages) and `payday_plan`.
- Tools are bound to the logged-in customer on the server; the model cannot pick a customer id → prompt injection can't reach other customers' data.
- Rules: never ask what the twin already knows, recommend ONE option with the reason, no selling under money stress, reply in the customer's language (detected per message: nl/fr/en), general guidance only — an advisor for binding advice.

Example (Lotte, in Dutch): *"Welke autoverzekering past bij mij?"* → *"Een mini-omnium past het best bij je tweedehandswagen van €11.500 … Je bent nu verzekerd bij Ethias, maar ik kan snel een KBC-offerte maken."*

### One engine, every channel

The API returns **channel-agnostic experience blocks**. The app and the website render the same JSON:

- **Anonymous visitor** → generic page with all variants (e.g. all 3 car loans).
- **Logged-in customer** → **one highlighted variant + the reason + the facts behind it**; the alternatives are collapsed.

### Why it scales to 2.3M customers

- The twin is built with cheap, deterministic rules over transactions: **5,000 twins in ~80 s on a laptop** → 2.3M overnight on a small cluster (or BigQuery).
- LLMs are only needed for *language* (chat answers, message phrasing), never for the inference itself → low, predictable cost per customer.
- Every fact carries evidence (transaction ids) → explainable, auditable, correctable (GDPR-friendly).

## Results on synthetic data

The generator hides life facts in transaction patterns; ground truth sits in `truth_*` tables the twin never reads. `python -m twin.evaluate`:

| Fact | Accuracy | Recall |
|---|---|---|
| Owns a car | 99.8% | 99.7% |
| Electric car | 99.9% | 99.4% |
| Has a pet | 100% | 100% |
| Dog vs cat | 94.8% | 84.5% |
| Commutes by train | 100% | 100% |
| Has children | 99.9% | 99.7% |
| Just bought a car | 99.8% | 93.7% |
| New baby | 99.7% | 88.8% |
| Moved house | 100% | 100% |
| New job / first job | 99.7% / 100% | 93.4% / 97.9% |

*Honest caveat: the data is synthetic and made by us, so these numbers show the pipeline works end-to-end — real data will be noisier.*

## Architecture

```
data/generate_db.py      synthetic Belgian bank: 5K customers, ~2.16M transactions (Oct 2025 – Sep 2026)
        │
        ▼  SQLite: customers, accounts, transactions, products, truth_* (evaluation only)
twin/engine.py           transactions → facts (+confidence, since, evidence) → implications → recurring bills → payday plan
        │                writes twin_profile (JSON per customer) + twin_facts (queryable)
        ▼
twin/recommender.py      page(twin, topic)  → one highlighted variant + reason   (twin=None → generic page)
twin/catalog.py          moments(twin)      → push / feed / held-back messages
        │
        ▼
api/                     FastAPI, one API for all channels: login, experience blocks, twin, plan, moments, feedback, Kate
        │                api/ops.py + twin/population.py → /api/ops/*: population aggregates & advisor drill-down (ops role, audited)
        │                api/routes_foresight.py + twin/forecast.py, sorter.py, selfemployed.py → money foresight (forecast, payday sorter, self-employed reserve)
        │
        ▼
web/                     Kate+ customer app + website view, rendering the same experience blocks
dashboard/               ops / advisor view, served by the API at /ops (static, same origin, strict CSP)
```

### What the twin infers today

employment & employer · net income & payday · job change / first job · car (combustion/electric, older car, recently bought, price, insurer) · pet (dog/cat) · children & newborn · childcare · housing (rent / mortgage / owner / student room / parents) · recent move · train commuter · gym · subscriptions · travel · monthly savings · financial buffer (months) · money stress · recurring monthly, quarterly and yearly bills.

### Demo personas (customer IDs 1–4 and 113)

| ID | Who | Story |
|---|---|---|
| 1 | **Lotte**, 29, Gent (nl) | Bought an €11,500 used petrol car on 13 Jun 2026 with savings; insured at Ethias; no car reserve. Salary €2,850 on the 25th. |
| 2 | **Julien**, 34, Namur (fr) | Baby born July 2026; diesel car; dog; KBC mortgage. |
| 3 | **Emma**, 23, Leuven (nl) | Moved out of her student room in August; first salary at Deloitte in September. |
| 4 | **Marc**, 47, Antwerpen (nl) | Self-employed, irregular income, EV, two kids — a quiet month would be tight. |
| 113 | **Jens**, 21, Gent (nl) | Persona 5, **money stress**: student (≈ €782/month from student jobs and parents), moved into a rental in July 2026, in the red on 46 of the last 90 days, no buffer. The "Settled in?" home-insurance message is **held back**; he gets the support push instead, and every product page is support-first. |

Personas 1–4 are hand-written in `data/generate_db.py`; persona 5 is an ordinary seeded customer flagged via `EXTRA_DEMO_IDS`.

## Team & tools

- **Team:** Mihály Németh (backend: data, twin engine, API, Kate, tests) · [@balintkss](https://github.com/balintkss) (frontend `web/`, positioning docs)
- **Partner tech:** ElevenLabs (demo video voice-over) · Aikido (security audit)
- **Also used:** OpenAI GPT-4.1 (Kate's language only; the twin itself uses no LLM) · Claude Code (development)
- **Demo video:** link in the Builderbase submission
- All customer data in this repository is **synthetic**; product names and rates are illustrative.

## Run it

`requirements.txt` is a pinned lockfile (every transitive dependency; `pip-audit`: no known vulnerabilities). The loose top-level ranges live in `requirements.in`; the frontend is locked by `web/package-lock.json` (`npm audit`: 0 vulnerabilities).

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python data/generate_db.py          # ~10 s, creates data/kbc_twin.db (git-ignored, 300 MB)
.venv/bin/python -m twin.engine               # ~80 s, builds all 5K twins
.venv/bin/python -m twin.evaluate             # accuracy vs. hidden truth
.venv/bin/python -m twin.engine --customer 1  # print Lotte's twin as JSON
.venv/bin/python -m api.seed_credentials      # logins; demo persona passwords -> data/demo_credentials.txt (git-ignored)
                                              #   re-running keeps existing passwords; --rotate issues new ones for everyone
.venv/bin/python -m api.seed_ops              # ops/advisor login 'advisor' -> data/ops_credentials.txt (git-ignored); dashboard at /ops
cp .env.example .env                          # then fill in OPENAI_API_KEY and a random TWIN_SECRET
.venv/bin/uvicorn api.main:app --reload       # API docs at http://localhost:8000/api/docs

# in a second terminal — customer app + public product view
cd web && npm install && npm run dev           # Node 20.19+ / 22.12+ · http://localhost:5173 (proxies /api to :8000)

# tests (no real OpenAI calls; DB tests are skipped until the steps above have run)
.venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest -q
```

### API (same JSON for app and website)

| Endpoint | Auth | What it returns |
|---|---|---|
| `POST /api/auth/login` | – | `{customer_id, password}` → bearer token (1 h). Rate-limited: 5 **failed** attempts per 5 min per IP and per customer (successful logins don't count) |
| `POST /api/auth/demo-login` | – | `{customer_id}` → bearer token **without a password, only for the 5 synthetic demo personas** (1, 2, 3, 4, 113; others 403). The app's persona cards use it. Disable with `TWIN_DEMO_LOGIN=0` |
| `GET /api/topics` | – | The product topics: `[{id, title}]` |
| `GET /api/experience/{topic}?channel=app\|web\|advisor` | optional | Anonymous: all variants. Logged in: **one highlight + reason + facts**, alternatives collapsed. Topics: `car_loan`, `car_insurance`, `savings`, `home`, `family` |
| `GET /api/me` | required | Who is logged in: `{customer_id, name, first_name, language, city, age, kbc_products}` |
| `GET /api/me/twin?with_evidence=true` | required | Glass box: every fact, confidence, since, implications and the proving transactions |
| `GET /api/me/plan` | required | Payday plan: bills, reserves, savings, free to spend per week |
| `GET /api/me/moments` | required | `push` (max 2), `feed`, and `held_back` (sales suppressed under money stress) |
| `GET /api/me/chat` | required | Kate's opener (top proactive moment) + chat history |
| `POST /api/me/chat` | required | `{message}` → Kate's answer + which tools she used. Rate-limited. |
| `POST /api/me/facts/{fact}/feedback` | required | `{correct, note}` — the customer corrects their twin; rejected facts stop driving recommendations |
| `GET /api/me/forecast` | required | Money foresight: day-by-day balance projection until payday (35 days without a fixed payday), safe to spend per day, lowest point, **early overdraft warning** + top-up suggestion |
| `GET /api/me/payday-sorter` | required | Kate's proposed split of the next payday into pots (bills, reserves, savings, free to spend) + the active mandate. Simulation: nothing moves |
| `POST /api/me/payday-sorter/approve` | required | `{pots: [ids]}` — **approve-to-act**: pot ids only, amounts are always recomputed server-side; unknown / non-movable ids → 422. Rate-limited |
| `POST /api/me/payday-sorter/revoke` | required | Stop the active payday-sorter mandate |
| `GET /api/me/self-employed` | required | Self-employed reserve: % of every invoice to set aside for social contributions and tax prepayments (indicative, Belgian 2026 rates), or `{applicable: false}` |
| `GET /api/me/moments-plus` | required | `/api/me/moments` plus the foresight moments (`overdraft_warning`, `self_employed_reserve`) — the app home feed |
| `GET /ops` | – (login in page) | Ops & advisor dashboard (static, same origin, strict CSP; token kept in memory only) |
| `POST /api/ops/login` | – | `{username, password}` → **ops-role** token (1 h). Rate-limited per IP and per username. Customer tokens never work on `/api/ops/*`, ops tokens never work on `/api/me/*` |
| `GET /api/ops/overview` | ops | Population aggregates, counts only: coverage, life events (90 d), pushes / held back, opportunities, highlight mix, 2.3M scale projection |
| `GET /api/ops/customers?has=<fact>&event=<type>&limit=1-50` | ops | Advisor picker (demo personas first). Every customer listed is written to `ops_audit` |
| `GET /api/ops/customers/{id}` | ops | Advisor drill-down: the same twin the customer sees (facts, plan, one highlight per topic, moments incl. held back). **Every access is logged** in `ops_audit(at, username, customer_id, action)` |

The generator is seeded, so everyone gets the same customers and transactions. Passwords are not part of it: `seed_credentials` and `seed_ops` generate them on each machine, so read yours from the git-ignored `data/*_credentials.txt`.

## Security (Aikido audit = 10% of the score)

- The customer id always comes from the signed session token (HMAC-SHA256, 1 h expiry), never from the URL or body → no IDOR. Evidence queries are also scoped by `customer_id`.
- Passwords PBKDF2-SHA256 with a per-user salt; login rate-limited per IP and per customer (failed attempts only, checked before the password); strict CORS; security headers.
- `TWIN_SECRET` comes from the environment (see `.env.example`); without it a random per-process secret is used. No real customer data anywhere.
- `truth_*` tables are for evaluation only and never exposed through the API.

## Docs

- [`AGENTS.md`](AGENTS.md) — repo map, full API contract and screens for the frontend (read first)
- [`docs/EXECUTIVE_SUMMARY.md`](docs/EXECUTIVE_SUMMARY.md) — one-page summary
- [`docs/SCALABILITY.md`](docs/SCALABILITY.md) — scalability for 2.3M customers: initial build, daily update, cost (details in `docs/scalability/`)
- [`docs/KBC_SERVICE_MAP.md`](docs/KBC_SERVICE_MAP.md) — where the twin fits in KBC's services, with sources
- [`docs/KBC_VALUE_MATRIX.md`](docs/KBC_VALUE_MATRIX.md) — product-value matrix, guardrails, proof points
- [`docs/PRIVATE_BANKER_AT_SCALE.md`](docs/PRIVATE_BANKER_AT_SCALE.md) — business case: private-banker quality at retail scale
- [`docs/PITCH.md`](docs/PITCH.md), [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md), [`docs/DATABASE_HANDOFF.md`](docs/DATABASE_HANDOFF.md) — pitch kit, demo video script, database/API handoff

## Status / unfinished

- [x] Synthetic data generator (5K customers, Belgian specifics, planted life events, demo personas)
- [x] Twin engine: facts, implications, recurring bills, payday plan
- [x] Evaluation against ground truth
- [x] Recommender: highlight-one pages + push moments with silence rules
- [x] API with login, experience blocks, glass-box twin, plan, moments
- [x] Customer correction of facts ("that's not right") — corrections immediately adjust the payday plan (car/pet reserves, fuel, savings) without rebuilding the twin (`twin/feedback.py`)
- [x] Kate chat over the twin ("pull") with grounded tools, in the customer's language (nl/fr/en)
- [x] Ops & advisor dashboard for the 5K population (`/ops`, separate ops login, every customer access audited)
- [x] Money-stress demo persona (5, Jens): sales held back, support first
- [x] Money foresight: overdraft early warning, payday sorter (approve-to-act, simulated), self-employed reserve
- [x] Test suite: 513 tests, all passing (`python -m pytest -q`)
- [x] App + website frontends (`web/`): customer login, payday plan, safe-to-spend forecast, approval-only payday sorter, product comparison, glass box with fact correction, Kate and support-first state
- [x] Life moments & gaps: checklists auto-ticked from the twin, coverage-gap finder, benefits hints with official sources (`/api/me/life-checklists`, `/coverage-gaps`, `/benefits`)
- [x] Confirmation gate: highlights built only on inferred facts ask "Is that right?" before any sales CTA; family content only after the customer confirms a household change
- [x] Scalability study for 2.3M customers (`docs/SCALABILITY.md`): partitioned backfill, incremental daily update (verified equal to a full rebuild), cost model
- [x] Fresh clone from public GitHub → README steps → 513 tests passing in ~2.5 min (verified 30 Sep 2026)
- [ ] Aikido scan before/after, demo video
- [ ] Not built: "Kate remembered" (facts stated in chat, confirmed by the customer, with Edit/Forget) — designed in `docs/KBC_SERVICE_MAP.md` §6, not implemented
- [ ] Known, accepted for the demo: one-click `POST /api/auth/demo-login` has no password by design. It only issues ordinary customer-scoped tokens for the 5 flagged **synthetic** demo personas, is rate-limited, and switches off with `TWIN_DEMO_LOGIN=0`; a real deployment would not ship it
- [ ] Production hardening not done: Kate's prompt still includes the customer's first name, age and city (drop name/city before real use); SQLite only (Cloud SQL migration in `docs/DATABASE_HANDOFF.md`)

Product names follow KBC's product families, but descriptions and rates in `twin/catalog.py` are illustrative placeholders, not real KBC terms.
