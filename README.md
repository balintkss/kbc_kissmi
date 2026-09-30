# KBC Digital Twin — "It already knows. I don't have to explain."

> Tectonic Hackathon · KBC challenge: *a scalable personalization approach that fundamentally strengthens the relationship between KBC and its customers.*

## The idea in one line

Every customer gets a **living digital twin** — a picture of their life inferred from what they already do with their bank — so that every channel (app, website, advisor, notifications) knows the context and **never makes the customer explain themselves again**.

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
api/                     FastAPI, one API for all channels: login, experience blocks, twin, plan, moments, feedback
        │
        ▼
app + website            render the same experience blocks (to do)
```

### What the twin infers today

employment & employer · net income & payday · job change / first job · car (combustion/electric, older car, recently bought, price, insurer) · pet (dog/cat) · children & newborn · childcare · housing (rent / mortgage / owner / student room / parents) · recent move · train commuter · gym · subscriptions · travel · monthly savings · financial buffer (months) · money stress · recurring monthly, quarterly and yearly bills.

### Demo personas (customer IDs 1–4)

| ID | Who | Story |
|---|---|---|
| 1 | **Lotte**, 29, Gent (nl) | Bought an €11,500 used petrol car on 13 Jun 2026 with savings; insured at Ethias; no car reserve. Salary €2,850 on the 25th. |
| 2 | **Julien**, 34, Namur (fr) | Baby born July 2026; diesel car; dog; KBC mortgage. |
| 3 | **Emma**, 23, Leuven (nl) | Moved out of her student room in August; first salary at Deloitte in September. |
| 4 | **Marc**, 47, Antwerpen (nl) | Self-employed, irregular income, EV, two kids — a quiet month would be tight. |

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python data/generate_db.py          # ~10 s, creates data/kbc_twin.db (git-ignored, 300 MB)
.venv/bin/python -m twin.engine               # ~80 s, builds all 5K twins
.venv/bin/python -m twin.evaluate             # accuracy vs. hidden truth
.venv/bin/python -m twin.engine --customer 1  # print Lotte's twin as JSON
.venv/bin/python -m api.seed_credentials      # logins; demo persona passwords -> data/demo_credentials.txt (git-ignored)
cp .env.example .env                          # then fill in OPENAI_API_KEY and a random TWIN_SECRET
.venv/bin/uvicorn api.main:app --reload       # API docs at http://localhost:8000/api/docs
```

### API (same JSON for app and website)

| Endpoint | Auth | What it returns |
|---|---|---|
| `POST /api/auth/login` | – | `{customer_id, password}` → bearer token (1 h). Rate-limited. |
| `GET /api/experience/{topic}?channel=app\|web` | optional | Anonymous: all variants. Logged in: **one highlight + reason + facts**, alternatives collapsed. Topics: `car_loan`, `car_insurance`, `savings`, `home`, `family` |
| `GET /api/me/twin?with_evidence=true` | required | Glass box: every fact, confidence, since, implications and the proving transactions |
| `GET /api/me/plan` | required | Payday plan: bills, reserves, savings, free to spend per week |
| `GET /api/me/moments` | required | `push` (max 2), `feed`, and `held_back` (sales suppressed under money stress) |
| `GET /api/me/chat` | required | Kate's opener (top proactive moment) + chat history |
| `POST /api/me/chat` | required | `{message}` → Kate's answer + which tools she used. Rate-limited. |
| `POST /api/me/facts/{fact}/feedback` | required | `{correct, note}` — the customer corrects their twin; rejected facts stop driving recommendations |

The generator is seeded, so everyone gets the same database.

## Security (Aikido audit = 10% of the score)

- The customer id always comes from the signed session token (HMAC-SHA256, 1 h expiry), never from the URL or body → no IDOR. Evidence queries are also scoped by `customer_id`.
- Passwords PBKDF2-SHA256 with a per-user salt; login rate-limited per IP and per customer; strict CORS; security headers.
- `TWIN_SECRET` comes from the environment (see `.env.example`); without it a random per-process secret is used. No real customer data anywhere.
- `truth_*` tables are for evaluation only and never exposed through the API.

## Status / unfinished

- [x] Synthetic data generator (5K customers, Belgian specifics, planted life events, demo personas)
- [x] Twin engine: facts, implications, recurring bills, payday plan
- [x] Evaluation against ground truth
- [x] Recommender: highlight-one pages + push moments with silence rules
- [x] API with login, experience blocks, glass-box twin, plan, moments
- [x] Customer correction of facts ("that's not right") — corrections immediately adjust the payday plan (car/pet reserves, fuel, savings) without rebuilding the twin (`twin/feedback.py`)
- [x] Kate chat over the twin ("pull") with grounded tools, in the customer's language (nl/fr/en)
- [ ] App + website frontends, ops dashboard for the 5K population
- [ ] Aikido scan before/after, demo video

Product names follow KBC's product families, but descriptions and rates in `twin/catalog.py` are illustrative placeholders, not real KBC terms.
