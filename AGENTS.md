# AGENTS.md: KBC Digital Twin (Tectonic Hackathon)

> The single source of truth for humans and AI coding assistants (Cursor, Claude, Copilot...) working in this repo.
> Read it fully before you change anything. When code and this file disagree, the code wins. Tell the team so this file gets fixed.

## 1. Project in 5 lines

1. **Challenge (KBC):** *"a scalable personalization approach that fundamentally strengthens the relationship between KBC and its customers"*, for 2.3M customers.
2. **Idea:** every customer gets a living **digital twin**, a picture of their life inferred from their transactions (car, baby, move, new job, payday, bills...), where each fact has a confidence score and the transactions that prove it.
3. **Promise to the customer:** *"KBC already knows me. I don't have to explain anything."*
4. **Push + pull:** proactive moments (payday plan, life events; sales are held back under money stress) plus **Kate**, a GPT-4.1 chat that uses the twin as memory and tools for every number.
5. **Glass box:** the customer sees what KBC believes and can correct it ("That's right" / "That's not me").

**One engine, every channel.** The API returns channel-agnostic JSON that the app view and the website view both render:

- **Anonymous visitor**: a generic page with **all variants** (e.g. all 3 car-insurance options).
- **Logged-in customer**: **ONE highlighted variant + the reason + the facts behind it**, with the alternatives collapsed.

Team: **A** = backend (data, twin, recommender, API, Kate; built with Claude). **B** = frontend (phone-style app view + website view).

## 2. Repo map

| Path | What it is | Owner / rule |
|---|---|---|
| `README.md` | Pitch, results, run instructions, status | Both. B adds the frontend run command and status |
| `SUBMISSION_CHECKLIST.md` | Pre-submit checklist (repo public, secrets, Aikido, video) | Both |
| `docs/DATABASE_HANDOFF.md` | Database and API connection contract for humans and coding agents | Read before any database or frontend integration |
| `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/project.mdc` | This guide and its pointers | Both |
| `data/generate_db.py` | Seeded synthetic Belgian bank: 5K customers, ~2.16M transactions, demo personas 1–4 | **A: do not edit** |
| `data/kbc_twin.db` | Generated SQLite DB (~300 MB) | git-ignored, regenerate it, never commit |
| `data/demo_credentials.txt` | Demo persona logins (plain text) | git-ignored. **Never commit, paste, screenshot or hard-code** |
| `twin/engine.py` | Transactions → facts → implications → recurring bills → payday plan (`AS_OF = 2026-09-30`) | **A: do not edit** |
| `twin/recommender.py` | `page(twin, topic)` (highlight-one) and `moments(twin)` (push/feed/held_back) | **A: do not edit** |
| `twin/catalog.py` | Product variants per topic (KBC product families, illustrative text) | **A: do not edit** |
| `twin/assistant.py` | Kate: system prompt, language detection, 4 tools bound to the logged-in customer | **A: do not edit** |
| `twin/evaluate.py` | Accuracy against the hidden `truth_*` tables | A |
| `api/main.py` | FastAPI app: all endpoints, CORS, security headers, rate limits | **A: do not edit** |
| `api/security.py` | PBKDF2 passwords, HMAC-SHA256 bearer tokens (1 h) | **A: do not edit** |
| `api/env.py` | Loads `.env` into the environment (real env vars win) | A |
| `api/seed_credentials.py` | Creates logins, writes demo passwords to `data/demo_credentials.txt` | A |
| `requirements.txt`, `.env.example` | Python deps, env placeholders (no real values) | A (coordinate) |
| `.env` | Local secrets | git-ignored. **Never commit or print** |
| `web/` *(to create)* | The frontend | **B owns it** |
| `hello_world.txt`, `kbc_kissmi/` | Leftovers. `kbc_kissmi/` is an untracked stray copy, so don't commit it | Decide together |

**Need a backend change?** Don't edit `twin/*`, `api/*` or `data/generate_db.py`. Send A a short change request instead, e.g.
`GET /api/me/moments: add "cta_label" to each moment, so the push card button text comes from the engine.`

## 3. Run the backend locally

```bash
cd KBC_hackathon
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # Python 3.10+ (venv uses 3.13)
.venv/bin/python data/generate_db.py          # ~10 s → data/kbc_twin.db (git-ignored, ~300 MB)
.venv/bin/python -m twin.engine               # ~80 s → builds all 5K twins
.venv/bin/python -m twin.evaluate             # optional: accuracy vs hidden truth
.venv/bin/python -m twin.engine --customer 1  # optional: print Lotte's twin as JSON
.venv/bin/python -m api.seed_credentials      # logins; demo passwords → data/demo_credentials.txt (git-ignored)
cp .env.example .env                          # then fill in OPENAI_API_KEY and a random TWIN_SECRET
.venv/bin/uvicorn api.main:app --reload       # http://localhost:8000, docs at http://localhost:8000/api/docs
```

- **The DB is deterministic** (seed 42), so everyone gets the same customers and transactions. **Passwords are not**: each run of `seed_credentials` makes new random ones. Read yours locally from `data/demo_credentials.txt`. Never commit them, paste them in chat or put them in code.
- Re-running `generate_db.py` wipes everything (credentials, feedback, chat history). After that, run `twin.engine` and `seed_credentials` again.
- **`OPENAI_API_KEY`**: get it privately from A and put it only in `.env`. It never goes in code, the frontend, commits or screenshots. Without it everything works except Kate: `GET /api/me/chat` returns 500 and `POST /api/me/chat` returns 503.
- **`TWIN_SECRET`**: set one (`openssl rand -hex 32`). Without it, every `--reload` restart invalidates all tokens.
- **`ALLOWED_ORIGINS`**: comma-separated, **no spaces**. The code default is `http://localhost:5173,http://localhost:3000,http://localhost:8000`, and `.env.example` sets `5173` and `3000`. A Vite dev server on 5173 works out of the box. The easiest setup is a Vite proxy, which avoids CORS entirely:
  ```js
  // web/vite.config.js
  export default { server: { port: 5173, proxy: { "/api": "http://localhost:8000" } } }
  ```
- Smoke test: `curl http://localhost:8000/api/topics`

## 4. API contract for the frontend

Base: `http://localhost:8000`. JSON in and out. Auth: header `Authorization: Bearer <token>`.
**Identity comes only from the token.** No endpoint takes a customer id except login. Never send `customer_id` to `/api/me/*`.

| Code | Meaning | Frontend reaction |
|---|---|---|
| 401 | `"Login required"` / `"Invalid or expired session"` (on login: `"Invalid customer id or password"`) | Drop the token and go to login (on the login screen, show "wrong id or password") |
| 404 | `"Unknown topic"`, `"Unknown fact"`, `"No twin built for this customer yet"` | Friendly empty state |
| 422 | Validation error. `detail` is an **array** of `{loc, msg, ...}` | Show a generic message |
| 429 | Login: `"Too many attempts, try again in a few minutes"`. Chat: `"Slow down a little"` | Show the message and wait |
| 503 | `"Kate is unavailable right now"` | Show it inside the chat and let the user retry |

Errors are `{"detail": "..."}`. **Rate limits** are in memory and reset on API restart. Login allows **5 attempts per 5 min per IP and per customer id, successful logins included**, so don't re-login on every page reload. Chat allows 20 messages/min per customer.

### POST /api/auth/login (no auth)
```json
// request                                  // 200
{"customer_id": 1, "password": "<local>"}   {"token": "<opaque>", "token_type": "bearer", "expires_in": 3600}
```
There's no refresh and no logout endpoint. Logout = forget the token. After 1 h you get 401 and go back to login.

### GET /api/topics (no auth)
```json
[{"id": "car_loan", "title": "Car loans"}, {"id": "car_insurance", "title": "Car insurance"},
 {"id": "savings", "title": "Saving & investing"}, {"id": "home", "title": "Home"}, {"id": "family", "title": "Family"}]
```

### GET /api/experience/{topic}?channel=app|web (auth optional)
**Anonymous** (send no `Authorization` header):
```json
{"topic": "car_insurance", "title": "Car insurance", "personalized": false, "highlight": null,
 "variants": [
   {"id": "liability", "name": "Third-party liability (BA)", "summary": "The legal minimum: damage you cause to others.",
    "features": ["Mandatory cover", "Lowest premium", "Legal assistance optional"]},
   {"id": "mini_omnium", "name": "Mini-omnium", "summary": "Liability plus theft, fire, glass and natural events.", "features": ["..."]},
   {"id": "omnium", "name": "Full omnium", "summary": "Everything, including damage to your own car.", "features": ["..."]}],
 "channel": "web"}
```
**Logged in** (Lotte, id 1):
```json
{"topic": "car_insurance", "title": "Car insurance", "personalized": true,
 "highlight": {"id": "mini_omnium", "name": "Mini-omnium", "summary": "Liability plus theft, fire, glass and natural events.",
   "features": ["Theft & fire", "Glass breakage", "Storm, hail and flooding"],
   "reason": "For a €11,500 second-hand car, mini-omnium covers theft, glass and storm without paying for own-damage you'd rarely claim. You currently insure it at Ethias: we can quote in 2 minutes using what we already know.",
   "because": [{"key": "has_car", "summary": "10 fuel payments, car bought 2026-06-13 for €11,500, insured at Ethias", "confidence": 0.9}]},
 "alternatives": [{"id": "liability", "name": "Third-party liability (BA)", "summary": "The legal minimum: damage you cause to others."},
                  {"id": "omnium", "name": "Full omnium", "summary": "Everything, including damage to your own car."}],
 "channel": "app"}
```
Gotchas:
- Personalized responses have `alternatives` (no `features`) **instead of** `variants`.
- `because` can be `[]` (Lotte / family). Hide the "because" block when it's empty.
- A logged-in customer can still get `personalized: false`, e.g. Emma / car_insurance (she has no car). Render the generic page then.
- An invalid or expired token here gives **401, not an anonymous fallback**. Clear the token, or retry without the header.
- `channel` is only echoed back. The content is identical for app and web.
- `topic` must match `^[a-z_]{1,40}$` (else 422) and exist (else 404).

### GET /api/me (auth)
```json
{"customer_id": 1, "name": "Lotte Peeters", "first_name": "Lotte", "language": "nl", "city": "Gent", "age": 29,
 "kbc_products": ["credit_card", "current_account", "investment_plan", "savings_account"]}
```

### GET /api/me/twin?with_evidence=true (auth): the glass box
```json
{"name": "Lotte Peeters", "as_of": "2026-09-30",
 "facts": [
  {"key": "has_car", "value": true, "confidence": 0.9, "since": "2026-06-13",
   "summary": "10 fuel payments, car bought 2026-06-13 for €11,500, insured at Ethias",
   "implies": [{"cost": "maintenance & tyres", "yearly": 650, "why": "typical for a combustion car"},
               {"cost": "fuel", "monthly": 187, "why": "10 fuel payments"}],
   "powertrain": "combustion", "insured_at": "Ethias", "bought_recently": true, "purchase_price": 11500, "monthly_reserve": 80,
   "evidence": [{"tx_id": 397, "date": "2026-09-21", "amount": -81.65, "counterparty": "...", "description": "..."}]},
  {"key": "financial_buffer", "value": 6.4, "confidence": 0.9, "since": null,
   "summary": "Savings + current account cover 6.4 months of spending", "implies": [], "evidence": []}],
 "recurring": [{"name": "J. Simon", "subcategory": "rent", "category": "housing", "frequency": "monthly", "amount": 963.93,
                "day_of_month": 4, "next_date": "2026-10-04", "monthly_equivalent": 963.93}]}
```
- `value` can be a bool, number, string or list. `since` is an ISO date, `"before 2025-10-01"` or `null`. `implies[]` has either `yearly` or `monthly`. `evidence` has at most ~5 transactions and can be `[]`. Other fields vary per fact, so render the common ones.
- Without `with_evidence=true`, `evidence` is omitted.
- After feedback, a fact also carries `rejected_by_customer`, `confirmed_by_customer` and optionally `customer_note`.
- Fact keys: `employment income has_car pet children childcare housing commutes_by_train gym_member subscriptions travels saves_monthly financial_buffer money_stress life_event_new_car life_event_new_baby life_event_moved life_event_first_job life_event_new_job life_event_new_pet`.

### GET /api/me/plan (auth): payday plan (can be `null` if no income is detected)
```json
{"payday": "2026-10-23", "income": 2850, "income_kind": "salary", "income_note": null, "bills_until_next_payday": 1458,
 "bills": [{"name": "J. Simon", "amount": 963.93, "day_of_month": 4}, {"name": "Ethias", "amount": 58.66, "day_of_month": 8}],
 "reserves": [{"for_": "yearly bills", "monthly": 51, "items": ["Ethias (home) €518 due 2027-06-14"]},
              {"for_": "car upkeep", "monthly": 80, "items": ["maintenance & tyres ≈ €650/yr", "road tax ≈ €250/yr"]}],
 "reserve_total": 131, "planned_savings": 200,
 "variable_essentials": [{"name": "fuel", "amount": 187, "estimated": true}, {"name": "groceries", "amount": 226, "estimated": true}],
 "free_to_spend": 648, "free_per_week": 151, "heads_up": []}
```
For Marc (irregular income): `payday: null`, `income_kind: "irregular"`, `income_note` is set, and **`free_to_spend` / `free_per_week` are negative** (-388 / -90). Note the key is `for_` (with the underscore).

### GET /api/me/moments (auth)
```json
{"push": [
   {"kind": "salary_plan", "priority": 90, "title": "Your payday plan is ready",
    "body": "€2,850 arrives on 2026-10-23. Bills €1,458, set aside €131, save €200 — that leaves €151/week to spend freely.",
    "topic": null, "sales": false},
   {"kind": "new_car", "priority": 80, "title": "Congrats on the car!",
    "body": "Beyond fuel it will cost ≈ €960/year (maintenance, tax, inspection). Shall we set aside €80/month from payday?",
    "topic": "car_insurance", "sales": true}],
 "feed": [],
 "held_back": []}
```
- `push` has at most 2 items. The rest go to `feed`. Items are sorted by priority.
- `kind` is one of `salary_plan | support | new_car | new_baby | moved | new_job`.
- If `topic` isn't null, it links to `/api/experience/{topic}`.
- `held_back` items also have `held_because`. These are sales messages suppressed under money stress, useful for an "ops/why not" view.

### GET /api/me/chat (auth)
```json
{"opener": {"kind": "salary_plan", "title": "Your payday plan is ready", "body": "...", "topic": null, "sales": false, "priority": 90},
 "history": [{"role": "user", "content": "Can I afford a €1,200 holiday in August?"}, {"role": "assistant", "content": "..."}]}
```
`opener` is the top push moment, or `null`. `history` holds the last 30 messages, oldest first.

### POST /api/me/chat (auth): costs OpenAI credits
```json
// request                                         // 200 (takes a few seconds)
{"message": "Welke autoverzekering past bij mij?"}  {"answer": "Een mini-omnium past het best bij je tweedehandswagen ...",
                                                     "tools_used": [{"tool": "recommend_product", "arguments": {"topic": "car_insurance"}}]}
```
- `message` must be 1–1000 characters.
- Tools: `check_affordability {amount, by_date, purpose?}`, `spending_summary {months, category?, merchant?}`, `recommend_product {topic}`, `payday_plan {}`. `tools_used` can be `[]`.
- Errors: 429, 503.
- **Mock it during UI development.** Never call it in loops, tests or on hot reload.

### POST /api/me/facts/{fact}/feedback (auth)
```json
// request                                   // 200
{"correct": false, "note": "Sold it"}        {"fact": "has_car", "correct": false}
```
- `note` is optional, max 280 characters. An unknown fact for this customer gives 404.
- **The latest feedback wins**: "That's right" after "That's not me" undoes it.
- A rejected fact immediately stops driving highlights, moments and Kate. Refetch `/twin`, `/moments` and `/experience/*` afterwards.
- Feedback persists in the local DB. To reset a persona locally: `sqlite3 data/kbc_twin.db "DELETE FROM twin_feedback WHERE customer_id=1"`.

## 5. Screens to build (priority order for the demo)

| Persona (id) | Story | What the UI shows |
|---|---|---|
| **Lotte** (1), 29, Gent, nl | Bought an €11,500 used petrol car on 13 Jun 2026 with savings. Insured at Ethias, no car reserve. Salary €2,850 (the 25th falls on a Sunday, so payday is 23 Oct) | Push: payday plan + "Congrats on the car!" → car_insurance highlights **Mini-omnium**. car_loan → second-hand loan. **Main demo persona** |
| **Julien** (2), 34, Namur, fr | Baby born July 2026, diesel car, dog, KBC mortgage | Push: payday plan + "Welcome to your little one" → family highlights **Hospitalisation insurance**. Kate answers in French |
| **Emma** (3), 23, Leuven, nl | Moved out of her student room in August, first salary at Deloitte in September | Push: payday plan + "Settled in?" → home highlights **Home insurance**. Feed: "New job, new plan". car_insurance stays generic (no car) |
| **Marc** (4), 47, Antwerpen, nl | Self-employed, irregular income, EV, two kids | Push: **"A quiet month would be tight"** (negative free_to_spend). car_loan highlights **Green car loan**. The glass box says "dog", but the data planted a cat: a real live **"That's not me"** demo |

a. **Login + persona picker.** Four cards (name, city, one-line story) plus a password field. The user types the password, read locally from `data/demo_credentials.txt`, which must never be bundled or pre-filled. Then `POST /api/auth/login` and `GET /api/me` for the greeting.
b. **App home (phone frame, ~390 px wide).** A big payday push card (`push[0]`, and `push[1]` if present), then the moments feed. Cards with a `topic` open screen (e).
c. **Kate chat.** Load `GET /api/me/chat`, show `opener` as Kate's first bubble, then `history`. On send: an optimistic user bubble, a typing indicator and a disabled input until the answer arrives. Under the answer, show a small hint from `tools_used`: `payday_plan` → "Kate checked: your payday plan", `check_affordability` → "Kate checked: affordability", `spending_summary` → "Kate checked: your spending", `recommend_product` → "Kate checked: best fit for {topic}".
d. **"What KBC knows about me" (glass box).** `GET /api/me/twin?with_evidence=true`. One card per fact: summary, a confidence bar, since, implications and expandable evidence transactions (date, counterparty, amount). Add **"That's right" / "That's not me"** buttons (feedback endpoint, optional note), then refetch. Style rejected facts as struck-through.
e. **Product topic page (highlight-one).** `GET /api/experience/{topic}`: a highlight card with the reason and "Because we know: {because[].summary} ({confidence})", plus the alternatives collapsed. **Key demo moment:** a **website view side by side, anonymous (no header) vs logged-in (with token)** for the same topic.
f. **Ops / advisor dashboard: do NOT build it.** Person A is building it (`/ops`, `dashboard/`, `api/ops.py`, `twin/population.py`) with its own advisor login. It will be documented here when it lands. Just link to `/ops` from your UI if you want.

Topics bar: `GET /api/topics`. Keep one API client module shared by the app view and the web view.

## 6. Frontend security rules (Aikido scans the frontend too)

1. **Token storage:** keep the bearer token in memory (a JS module variable). `sessionStorage` is the maximum. **Never `localStorage`**, never cookies set from JS.
2. **No raw HTML:** never `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `dangerouslySetInnerHTML` or `v-html`. Kate's answers, transaction descriptions, counterparties, reasons and notes are all **untrusted**. Render them as text (`textContent` / JSX `{text}`) with `white-space: pre-line`. If you want bullets, split lines yourself. No markdown-to-HTML library.
3. **No identifiers in URLs:** never put customer ids, tokens, passwords or personal data in URLs, query strings, route params or `console.log`. Topic ids in routes are fine.
4. **No keys in the frontend:** never hard-code or embed any API key or secret in frontend code or `.env` files that get bundled (`VITE_*` vars are public!). The OpenAI key is backend-only.
5. **Identity only from the token:** never send `customer_id` to `/api/me/*`. The server ignores it anyway, and Aikido flags it as an IDOR smell. The persona id is used only in the login body.
6. **Handle 401 globally:** clear the token, reset the user state and return to login. Show a generic message, never raw error dumps.
7. **Dependencies:** only well-known packages from the npm registry (React/Vite or plain JS is fine). No CDN scripts from random hosts, no analytics, trackers, fonts from unknown CDNs, or session-replay tools.

Minimal client:
```js
let token = null;                                    // memory only (sessionStorage at most)
export const setToken = (t) => { token = t; };
export async function api(path, { method = "GET", body, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && token) headers.Authorization = `Bearer ${token}`;
  const r = await fetch(`/api${path}`, { method, headers, body: body && JSON.stringify(body) });
  if (r.status === 401 && path !== "/auth/login") { token = null; window.dispatchEvent(new Event("logout")); }
  if (!r.ok) throw Object.assign(new Error(`HTTP ${r.status}`), { status: r.status });
  return r.json();
}
```

## 7. Working rules

- **Commit small and often.** Always `git pull --rebase` before `git push`. Never force-push `main`.
- **Database boundary:** frontend and design agents call `/api/*`; they never connect to SQLite or Cloud SQL directly. Read `docs/DATABASE_HANDOFF.md` before database, deployment, or frontend integration work.
- **Put the frontend in `web/`.** Add its run command to the README "Run it" section, e.g. `cd web && npm install && npm run dev  # http://localhost:5173`.
- **Update `.gitignore` for the frontend:** `node_modules/`, `web/dist/`, `web/.vite/`, `*.local`, `.env.*` plus `!.env.example` (so the example stays tracked).
- **Never commit:** `.env`, `data/*.db`, `data/*.txt` (demo credentials), build output or screenshots with passwords or tokens. Run `git status` before every commit.
- **Label the UI clearly:** show **"Concept prototype · synthetic data"** in the footer or header. Product names follow KBC families, but the rates and descriptions in `twin/catalog.py` are illustrative.
- **Branding:** don't use real KBC logos, fonts or brand assets (impersonation risk). A neutral style is fine, e.g. "Twin bank" in a neutral blue.
- **Language:** English UI copy is fine. API texts (reasons, moments) are English. Kate replies in the customer's language (nl/fr/en, detected per message).
- **Before submitting,** go through `SUBMISSION_CHECKLIST.md` (B owns: fresh-clone test, frontend Aikido scan, anonymous vs logged-in demo, correction in the UI, README run command).

## 8. Known limitations (design around them)

- **The plan is precomputed.** Rejecting a fact (e.g. the car) removes it from highlights and moments immediately, but `/api/me/plan` and the payday push body still include its reserve. Currently `twin.engine` doesn't read feedback, so rebuilding doesn't fix it either.
- **Kate is slow.** Replies take a few seconds: show a typing indicator and block double-send. Watch the rate limit of 20 messages/min.
- **Today is 2026-09-30** in the data (`AS_OF`). All dates are ISO strings (`2026-10-23`), so format them in the UI. The text inside moment bodies and reasons is pre-formatted English with ISO dates.
- **Amounts** are EUR numbers, where negative means money out. The plan's `free_*` values can be negative (Marc).
- **Logins are rate-limited:** 5 per 5 min per IP, successful ones included. Keep the token across screen changes. Restarting the API resets the limiter.
- **Tokens last 1 h**, with no refresh. Without `TWIN_SECRET` in `.env`, every API restart logs everyone out.
- **No money-stress demo:** none of the 4 personas has `money_stress`, so `held_back` and the `support` moment are empty in the demo (only non-demo customers have them).
- **`channel` has no effect** on the content. Chat without `OPENAI_API_KEY` fails: GET 500, POST 503.
