# Demo video script: "Kate+ — financial context, in your control"

**Target 2:45** (hard limit 3:00) · English voice-over at about 150 words/min (≈ 410 words) · real running product, no slides except the first and last card.
Criteria: **C** = Creativity · **T** = Technical ability ("does it work?") · **F** = Fit with the KBC challenge · **S** = Security.

Every number below was checked against the current DB (`AS_OF` = 2026-09-30). If a screen shows a different number, say the one on screen.
Words in *[brackets]* are optional cuts if the take runs long.

## Shot list

| # | Time | On screen (persona · screen · endpoint) | Voice-over | Hits |
|---|---|---|---|---|
| 1 | 0:00–0:11 | **Title card, then a generic bank page** listing all 3 car-insurance options (anonymous `GET /api/experience/car_insurance`). Small caption: *Concept prototype · synthetic data*. | "Your bank sees every payment you make, and still treats you like a stranger. You fill in forms, you explain yourself again, and every page shows you every option." | F |
| 2 | 0:11–0:31 | **Lotte (1) · Kate+ financial picture** (`GET /api/me/twin?with_evidence=true`). Open the `has_car` card: *"10 fuel payments, car bought 2026-06-13 for €11,500, insured at Ethias"*, confidence bar 90%. Expand evidence: Garage Lambert −€11,500 (13 Jun), registration tax −€864.80 (10 Jul), Lukoil fuel, Ethias −€58.66. Implications: maintenance €650/yr, road tax €250/yr. | "Meet Lotte, 29, from Ghent. She never told KBC she bought a car. Kate+ worked it out from a garage payment in June and the fuel after it. Ninety percent confident, with the proof, transaction by transaction. And it knows what a car implies: maintenance, road tax, insurance at Ethias, not KBC." | C, T, S |
| 3 | 0:31–0:46 | **Lotte · app home "Today"** (`GET /api/me/moments-plus`). Card 1 *"Heads-up: you'd go below zero on Fri 9 Oct and reach −€1,118 on Thu 22 Oct … Move €1,170 from savings"*. Card 2 *"€2,850 arrives on Fri 23 Oct. Bills €1,458, set aside €131, save €200 — that leaves €151/week to spend freely."* | "The app doesn't sell her anything. It plans, and warns her early: before payday she'd dip below zero, so move €1,170 from savings. On payday: bills, a car reserve, savings, and €151 a week to spend." | F, C |
| 4 | 0:46–1:05 | **Website view, split screen, same topic `car_insurance`.** Left: anonymous, 3 equal cards. Right: Lotte logged in: **Mini-omnium** highlighted, reason *"For a €11,500 second-hand car … You currently insure it at Ethias: we can quote in 2 minutes using what we already know."*, "Because we know: …(90%)", 2 alternatives collapsed. | "Same page on the website. A stranger gets three options. Lotte gets one: mini-omnium, and the reason. It fits a second-hand car, and we can quote in two minutes because we already know it. App, website, adviser: Kate+ uses one governed memory, through one API, for the same answer." | C, F |
| 5 | 1:05–1:26 | **Lotte · Kate+ chat** (`POST /api/me/chat`). Type: **"Kan ik een reis van 1200 euro betalen in augustus?"** Typing indicator → Dutch answer. Hint under the bubble: *"Kate+ checked: affordability"*. Expected tool result: `verdict: yes_with_savings`, 11 paydays to Aug 2027, 3-month buffer kept. | "Now she asks Kate+, in Dutch: can I afford a €1,200 trip in August? No salary, no rent, no savings typed in. Kate+ runs on GPT-4.1, like KBC's Kate, but never does the maths herself. A tool computes on Lotte's governed financial memory, and only hers. Yes: from savings, with her three-month buffer intact." | T, S, F |
| 6 | 1:26–1:41 | **Julien (2) · synthetic prototype family screen.** Keep the current screen only if it is labelled *"Synthetic scenario — customer confirmation required in production"*. Show the glass-box confirmation control before the family route. Optional 3 s cut: Kate in French, *"Qu'est-ce que je dois faire maintenant pour ma famille ?"* | "This synthetic scenario tests a family journey. In production, KBC never deduces a birth or health information from a payment. Julien first chooses to confirm a household change; then Kate can offer a relevant next step in French. The customer stays in control." | C, F, S |
| 7 | 1:41–1:55 | **Marc (4) · app home** push *"A quiet month would be tight"*: *"Planned on a quiet month (€2,635): bills €1,674, set aside €298. That's €388 short before groceries — keeping ≈ €1,164 aside from your good months covers it."* | "Marc is self-employed. His income swings almost fifty percent month to month. So his plan is built on a quiet month, and it warns him early: a slow month leaves him €388 short. Help first." | F, C |
| 8 | 1:55–2:22 | **Ops / advisor dashboard** (`/ops`, advisor login done off camera; `GET /api/ops/overview`). KPI tiles: 5,000 twins · 597 customers with money stress · **102 sales messages held back** (95 customers) · headline *"5K twins in 80 s → 2.3M in ~10 h on one core / ~19 min on 32 cores"*. Tab **Advisor drill-down** → **Jens (113)** (`GET /api/ops/customers/113`, audited in `ops_audit`): `money_stress` (46 of 90 days in the red), `held_back`: *"Settled in?"* (home insurance), reason *"Customer shows money stress: no product offers, only support."*; `push[0]`: *"Let's get ahead of next month … no fees, no product."* Every product page for him shows *support first*. | "Behind it: 5,000 twins, built in about 80 seconds on one laptop core, zero LLM calls. When money is tight, we stay quiet: 102 sales messages held back. Jens, a student, was in the red 46 of the last 90 days. His insurance offer is held back; he gets help moving a bill instead, and the advisor sees the same context. All 2.3 million customers: about 20 minutes on 32 cores." | T, F, S |
| 9 | 2:22–2:35 | **Marc · glass box**, `pet` card says *"dog"* (95%). Tap **"That's not me"**, note *"It's a cat"* (`POST /api/me/facts/pet/feedback`). Card strikes through; back to home: the gap drops from €388 to €328 (dog-care reserve removed). | "And when the twin is wrong (Marc has a cat, not a dog), he just says: that's not me. The fact stops driving anything, and his plan updates on the spot." | S, T, C |
| 10 | 2:35–2:45 | **Closing card:** *"Kate+ — financial context, in your control."* · one governed memory · every channel · help before sales · glass box · repo URL · *Concept prototype · synthetic data*. | "Kate+ gives every customer one governed financial memory, across every channel: help before sales, and a glass box you control." | F |

**Use persona 5, Jens (customer 113), for the "we stay quiet" beat:** he is money-stressed (46 of 90 days in the red), his "Settled in?" home-insurance offer is held back and he gets "Let's get ahead of next month" instead; every product page shows `support_first`. Click his card on the login screen (id 113), or open him in the /ops advisor drill-down. Older fallback (#190) below. Alternatives if the dashboard lists others first: #429 Pieter (Roeselare, 32 days in the red, family offer held back) or #203 Seppe (Brugge, new-car offer held back). Avoid #464: his stress flag comes from one big car purchase, which reads oddly on screen.

**On-screen caption for shot 8 (small print):** *"Projection = linear extrapolation from a laptop benchmark (pandas, one process per core). `python -m twin.benchmark`."*

## Pre-recording checklist

### 1. Reset the demo state (API stopped or idle)

```bash
cd KBC_hackathon
sqlite3 data/kbc_twin.db <<'SQL'
DELETE FROM twin_feedback WHERE customer_id IN (1, 2, 3, 4, 113);
DELETE FROM chat_messages WHERE customer_id IN (1, 2, 3, 4, 113);
DELETE FROM sorter_mandates WHERE customer_id IN (1, 2, 3, 4, 113);
SQL

# verify: both counts must be 0
sqlite3 data/kbc_twin.db "SELECT 'feedback', COUNT(*) FROM twin_feedback WHERE customer_id IN (1,2,3,4,113)
                          UNION ALL SELECT 'chat', COUNT(*) FROM chat_messages WHERE customer_id IN (1,2,3,4,113);"
```

- [ ] **Don't run `python -m twin.engine` or `data/generate_db.py` right before or during recording.** The engine rewrites `twin_profile`/`twin_facts`; the generator wipes feedback and chat. If you must regenerate, do it well before (then `python -m twin.engine` and `python -m api.seed_ops`).
- [ ] **Restart the API** right before recording (latest code, fresh counters). Customer login is **one click on the persona card** (no password: `POST /api/auth/demo-login`, synthetic demo personas only). Only `/ops` needs the advisor login: do it off camera.
- [ ] `TWIN_SECRET` is set in `.env`, so a `--reload` doesn't log you out mid-take. Tokens last 1 h: log in fresh for each session.

### 2. Log in fresh, rehearse the numbers

- [ ] Click Lotte, Julien, Marc and Jens once and check that the screens show the numbers in the table (e.g. €151/week, Mini-omnium + Ethias, €388 short, 102 held back).
- [ ] The VO says "GPT-4.1": make sure `OPENAI_MODEL` in `.env` is unset or `gpt-4.1` (check it off camera).
- [ ] Kate (costs a few cents per question): ask Lotte's question once. If the answer isn't "yes, from savings, buffer intact", reset `chat_messages` for customer 1 and retake. Record Kate shots as separate takes and cut the wait (her reply takes a few seconds).
- [ ] After rehearsing the correction (shot 9), **run the reset SQL again**, or the `pet` card starts out already struck through.
- [ ] Check the correction updates Marc's plan (€388 → €328). If the feedback fix isn't wired into the API yet, cut "and his plan updates on the spot" and say "and every channel stops using it".

### 3. Screen hygiene (security is judged too)

- [ ] **No passwords on screen:** customers need none (one-click personas). Log in to `/ops` before you start recording that shot, and never open `data/ops_credentials.txt` on camera. Dismiss or disable the browser's "save password" prompt and autofill.
- [ ] **Close every terminal** that shows env vars, `.env`, the OpenAI key, tokens or `curl` headers with `Authorization`. No DevTools Network tab (it shows the bearer token).
- [ ] Use a clean browser profile (guest window): no bookmarks bar, no personal extensions, no other tabs, no personal email in the corner.
- [ ] macOS Do Not Disturb on (no notification pop-ups).
- [ ] The *Concept prototype · synthetic data* label is visible. No real KBC logos or fonts.

### 4. Browser and recording

- [ ] Window 1920×1080 (or 1440×900), **browser zoom 125–150%** so the reason text is readable on a phone.
- [ ] App view in the ~390 px phone frame. Website split screen side by side for shot 4.
- [ ] Quiet room, external mic, one test take and listen back. Export and check the **actual file length is < 3:00**.
- [ ] Add captions (Kate's Dutch/French answers need an English subtitle line).
- [ ] Upload as **unlisted** (not private) and open the link in an incognito window.
