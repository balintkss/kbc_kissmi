# Pitch kit: Kate+ powered by the KBC Digital Twin

> *"KBC helps me without making me repeat myself — and I stay in control."*

Concept prototype on synthetic data (5,000 customers, 2.16M transactions). Figures come from the repo (`python -m twin.evaluate`, `python -m twin.benchmark`) or from the sources at the bottom.

---

## 1. Builderbase short description

**≈ 50 words**

> Kate+ gives every customer a living, explainable picture of their financial life (car, move, new job, payday, bills), inferred from non-sensitive transaction patterns KBC already has. Its Digital Twin memory gives every channel one highlighted next step with the reason, a payday plan, answers in context and no sales under money stress.

**≈ 100 words**

> Customers keep explaining their financial context to their bank. Our digital twin reduces that burden. From transactions KBC already categorises, it identifies explainable, non-sensitive facts such as "bought a used car in June, insured at Ethias" or "moved home". Each comes with a confidence score, its supporting transactions and a financial implication such as road tax. One API feeds the app, website, advisors and Kate. A logged-in customer sees one relevant next step with the reason, gets a payday plan and can ask Kate in Dutch or French in context. Sales are held back under money stress. Customers can see, correct or remove every fact.

**≈ 150 words**

> Customers keep explaining their financial context to their bank. Our digital twin reduces that burden. Deterministic rules identify explainable, non-sensitive facts such as "bought a used €11,500 car in June, insured at Ethias", "moved home" or "self-employed, income swings 47%". Each carries a confidence score, supporting transactions and financial implications such as maintenance and road tax. One shared context feeds every channel. Product pages highlight one relevant next step with the reason. Payday brings a plan, not an offer. Kate (GPT-4.1, like KBC's Kate) answers "can I afford this trip?" in the customer's language, with tools computing every number. Under money stress, sales are held back and only help gets through. A glass box lets customers correct or remove facts instantly. 5,000 twins build in under 90 seconds on one laptop core with zero LLM calls. Linear projection: 2.3M in about 80 minutes on 8 cores.

## 2. 30-second elevator pitch (≈ 80 words, about 30 s spoken)

> Kate already talks to millions of KBC customers, yet every channel still starts from zero. **Kate+** is the product layer that changes that, powered by a digital twin per customer inferred from permitted transaction patterns. It knows Lotte bought a used car in June and insures it elsewhere. So the website shows her one insurance with the reason, payday brings a plan, not an offer, and Kate+ answers “can I afford this trip?” without a single question. And Lotte can see and correct all of it.

## 3. The challenge's five questions

**1. Which signals?** Only data KBC already holds and already categorises: transactions (category, subcategory, counterparty, channel, balance after), products held and account balances. `twin/engine.py` reads non-sensitive patterns such as fuel vs. EV charging, a car purchase plus registration tax, an insurer's direct debit, rent to a new landlord after a moving company, a new salary payer after student jobs, invoice variance for the self-employed, and days in the red. Every fact stores `confidence`, `since` and `evidence` (transaction ids), so every signal can be traced. A real rollout excludes special-category inferences; household or family changes are voluntary customer confirmations, not deductions from payments.

**2. Recognising situation, behaviour and intent.** *Situation* = state facts: employment, income and payday, housing, car (powertrain, age, price, insurer). *Behaviour* = patterns: monthly saving, train commuting, subscriptions, travel, financial buffer and money stress. *Intent* = a customer-confirmed objective or a non-sensitive life moment detected as a change with a date (`life_event_new_car`, `_moved`, `_first_job`, `_new_job`). Facts become future financial costs through **implications** (a car → €650/yr maintenance and €250/yr road tax). In chat, Kate reads that customer-controlled context and routes it to a tool or topic (`twin/assistant.py`).

**3. Automatic adaptation.** Nothing is configured per customer. Pickers in `twin/recommender.py` choose one variant per topic from the facts: a car bought with savings → second-hand loan, sized to 35% of free money over 60 months; an EV → green loan; a €11,500 used car → mini-omnium. `moments()` ranks messages, sends at most 2 as pushes and **moves every sales message to `held_back`** when money stress is detected. Irregular income gets a plan built on a quiet month. Kate mirrors the language of each message (nl/fr/en). A customer correction immediately removes a fact from every decision and recomputes the payday plan (`twin/feedback.py`), with no retraining. The nightly rebuild picks up new life events on its own.

**4. Across products, services and channels.** One API (`api/main.py`) returns channel-agnostic experience blocks: the app and the website render the same JSON, and Kate's `recommend_product` tool calls the very same `page()` function. The advisor dashboard (`/ops`, `api/ops.py`) reads the same twin, and every advisor view of a customer is written to an audit log. Five topics span bank *and* insurer: car loan, car insurance, saving & investing, home (loan, renovation, insurance) and family (child savings, hospitalisation, family liability). One fact learned once (Lotte's car) drives the loan page, the insurance page, the payday reserve, the push message and Kate's answers.

**5. Impact for millions.** *Cost:* the twin is plain rules at about 16 ms per customer, 60 twins/s per core and zero LLM calls. Linear projection for 2.3M customers: about 80 minutes on 8 cores, about 20 on 32 (§5). The LLM is only used for chat language, at about $0.008 per turn. *Relationship:* no questions ("don't make me explain"), one relevant option instead of a catalogue, help before sales (597 of 5,000 synthetic customers get a support message and no offers), and a glass box that earns trust. *Business:* relevance on top of Kate's 400,000+ yearly sales. In our data 2,118 of 3,350 car owners insure elsewhere, and the twin can say "we can quote in 2 minutes, we already know your car". *Measurable:* confirmation rate of facts, highlight acceptance, held-back volume.

## 4. Why this isn't "another feature": vs. what KBC already has

KBC is ahead of the market. Kate is a strong conversational and proactive assistant. We don't replace her. We give her, and every other channel, a shared memory.

| | KBC today (public sources) | What the twin adds |
|---|---|---|
| **Assistant** | Kate: 5.8M digital customers in 5 countries, solves 70% of queries on her own, 80M conversations, runs on GPT-4.1 since Oct 2025 | The twin as Kate's memory: a compact profile (≈ 300–560 tokens) in the prompt plus 4 tools that compute on it. She never asks what's already known |
| **Proactive** | 140+ situations in Belgium (duplicate payments, service vouchers running low, card activated abroad…) | Each situation reads **one shared context**. Ranked, max 2 pushes, and **sales held back under money stress** |
| **Budgeting** | Budgets and a subscription overview in KBC Mobile | A payday plan that includes *implied* future costs (car upkeep, yearly bills) and a quiet-month plan for irregular income |
| **Product pages** | Typical bank sites show the same product range to everyone | **One highlighted variant + the reason + the facts behind it**, alternatives collapsed. Same JSON on the app, web and for the advisor |
| **Transparency** | We found no public customer-facing view of what is inferred about them | **Glass box:** every fact with confidence, date and proving transactions, plus "That's right" / "That's not me" |
| **Sales** | Kate contributes to 400,000+ products and services sold per year | Makes those moments more relevant (life events, insurer elsewhere) and safer (silence under stress) |
| **Market** | Belfius builds a conversational assistant ("Hey Belfius") with Mistral AI | Chat is becoming a commodity. **Shared, correctable context** is the differentiator |

## 5. Scale & cost

### Twin engine benchmark (`python -m twin.benchmark --n 5000`, read-only on the DB)

Apple-silicon laptop (arm64, 8 cores), Python 3.13, pandas 3.0, **one process**, 2026-09-30:

| Step | Result |
|---|---|
| Load 5,000 customers / 2.16M transactions (SQLite → pandas) | 4.8 s (≈ 1.0 ms per customer, incl. grouping) |
| Build twins via `Twin(...).build()` | **15.9 ms per twin** (median 15.8, p95 19.7) · 8.1 facts per twin |
| Serialise (JSON) | 0.06 ms per twin |
| Recommender: `moments` + `page` × 5 topics | 0.03 ms per twin (≈ 30,000 twins/s) |
| **Throughput, one core** | **63 twins/s** build-only · **59 twins/s** end-to-end (17.0 ms/customer) |
| 5,000 twins, end to end | ≈ 85 s |

**Linear projection for 2,300,000 customers** (extrapolated from the laptop: pandas, one process per core, customers are independent, I/O assumed to keep up): **1 core ≈ 10.9 h · 8 cores ≈ 80 min · 32 cores ≈ 20 min.** A 1,000-twin run gives the same result (15.3 ms/twin, 10.6 h / 80 min / 20 min). Peak memory was ≈ 1.9 GB with the whole population loaded at once. In production you would stream customers in partitions, on Spark, BigQuery or a job queue.

### LLM cost (Kate only; the twin needs **zero** LLM calls)

OpenAI standard pricing per 1M tokens, [developers.openai.com/api/docs/pricing](https://developers.openai.com/api/docs/pricing), seen **2026-09-30**:

| Model | Input | Cached input | Output |
|---|---|---|---|
| GPT-4.1 | $2.00 | $0.50 | $8.00 |
| GPT-4.1-mini | $0.40 | $0.10 | $1.60 |

**Tokens per Kate turn**, measured offline on the demo personas with `SYSTEM` + `compact_twin()` + `TOOLS` from `twin/assistant.py`, using characters ÷ 4 (no API call made):

- System prompt with compact twin: avg 3,644 chars ≈ **910 tokens** (Lotte: 3,695 chars, of which the compact twin is 1,913 chars ≈ 480 tokens)
- Tool schemas: 1,801 chars ≈ 450 tokens (sent on every call)
- A typical turn is **2 calls**: call 1 (prompt + ~175 tokens of history + question) → tool call. Call 2 adds the tool result (avg 726 chars ≈ 180 tokens) → answer of about 150 tokens
- ≈ **3,400 input + 185 output tokens per turn**

| Per chat turn | GPT-4.1 | GPT-4.1-mini |
|---|---|---|
| chars ÷ 4 | **$0.0082** | **$0.0016** |
| with prompt caching on call 2 | $0.0062 | $0.0012 |
| pessimistic (chars ÷ 3) | $0.0102 | $0.0020 |

| Scenario (2.3M customers) | Turns/month | GPT-4.1 / month | GPT-4.1-mini / month | GPT-4.1 per customer per year |
|---|---|---|---|---|
| A: 10% chat, 3 turns/month | 0.69M | **≈ $5,700** | ≈ $1,100 | $0.03 |
| B: 30% chat, 5 turns/month | 3.45M | ≈ $28,400 | ≈ $5,700 | $0.15 |
| C: everyone, 10 turns/month | 23M | ≈ $189,500 | ≈ $37,900 | $0.99 |

Push messages, product pages, the payday plan, Kate's opener and the glass box are all generated without an LLM. Cost grows with *conversations*, not with the number of customers.

## 6. Likely judge questions

**Where is the business value?** KBC already delivers high-touch private-banking relationships through a dedicated contact, regular dialogue and specialist coordination. The Digital Twin scales the *preparation layer* of that relationship to retail: a customer-governed financial memory, one stated goal, an explainable next step and an adviser handover when judgement matters. We do not invent an ROI figure. In a controlled pilot we measure plan adoption and customer effort first, then incremental qualified journey completion against a control group, alongside suitability, complaints, opt-outs and fairness. See [`PRIVATE_BANKER_AT_SCALE.md`](PRIVATE_BANKER_AT_SCALE.md) for the metric tree and pilot gates.

**Can the same idea help prevent fraud?** Yes — as a separate, purpose-limited security workstream. PSD2 requires payment providers to have monitoring mechanisms for unauthorised or fraudulent payments; a security baseline can use approved payment, device, payee and session signals to route an anomalous payment to allow, step-up authentication or review. It shares the Twin's evidence and audit discipline, **not** its commercial life profile: fraud signals never become marketing inputs, and security-derived risk never determines credit, insurance or pricing. [EBA Q&A 2020_5621](https://www.eba.europa.eu/single-rule-book-qa/qna/view/publicId/2020_5621) · [EDPB legitimate-interest guidance](https://www.edpb.europa.eu/system/files/2024-10/edpb_guidelines_202401_legitimateinterest_en.pdf)

**Privacy / GDPR / consent?** This prototype uses synthetic data. A real rollout uses a **Financial Understanding Contract**: separate, revocable choices for KBC account data, connected external data, proactive help and commercial offers. The customer sees why, can confirm, correct or delete facts, and controls what becomes durable memory. Special-category data — including health, mental health, pregnancy, religion, politics and union membership — is never inferred from transactions or used for marketing, pricing, eligibility or automated decisions. Any external-account data requires the customer’s explicit PSD2 consent. The glass box provides transparency and access; evidence is always scoped to the logged-in customer. Product purchase, credit, insurance acceptance or price always requires an explicit customer step and the applicable KBC process.

**What if the twin is wrong?** Every fact has a confidence score and its proving transactions. Messages are phrased as help, not accusations. The customer corrects in one tap, and the fact stops driving highlights, pushes and Kate immediately, while the plan recomputes. Our own demo contains a real mistake: Marc's cat is inferred as a dog. Accuracy on synthetic data is 94.8–100% per fact (recall 84.5–100%). Corrections double as free labels for improving the rules.

**Why rules and not ML for inference?** Banks may have well-categorised transactions but not reliable labels for many customer needs. Rules are explainable fact by fact (evidence ids), deterministic, auditable for regulators, cheap (16 ms, no GPU, no LLM) and easy to correct. The fact contract (`value`, `confidence`, `since`, `evidence`, `implies`) is model-agnostic, so any single rule can later be swapped for a validated model without touching a channel.

**Real data is noisier.** Yes. Our data is synthetic and generated by us, so our accuracy is an upper bound. Expect joint and household accounts, customers who bank at two banks (salary elsewhere → lower confidence), cash, and mis-categorised merchants. The plan: run in shadow mode on real data, show only facts above a confidence threshold, and use customer confirmations as ground truth.

**Regulation: investment advice, insurance, credit?** Kate's prompt forbids personalised investment advice and hands investments or binding offers to a KBC advisor (MiFID II). The savings page's "investment plan" highlight would need a suitability/appropriateness check first in production. For insurance (IDD), the twin can pre-fill the demands-and-needs test. For credit, loan suggestions are sized to the payday plan (35% of free money) and are never shown under money stress. The standard creditworthiness check still applies.

**How does it plug into Kate?** Kate already runs on GPT-4.1 with function calling. Add the compact twin (≈ 300–560 tokens of facts, plan and bills) to her context and expose 4 tools (`check_affordability`, `spending_summary`, `recommend_product`, `payday_plan`) backed by the twin API. Her 140+ proactive situations become consumers of the same facts. The twin is built nightly in KBC's data platform and served by one API to Kate, KBC Mobile, kbc.be and advisor tools.

**Security?** Identity only comes from a signed token (HMAC-SHA256, 1 h). No customer id ever appears in a URL or body, so there's no IDOR. Passwords use PBKDF2-SHA256 with a per-user salt. Login and chat are rate-limited, CORS is strict and security headers are set. Kate's tools are bound to the session server-side, so the model *cannot* choose a customer, and transaction texts are treated as data, never instructions (prompt-injection guard). Advisors use separate ops identities (a customer token is rejected there and vice versa), and every advisor look-up of a customer is audited (`ops_audit`). Secrets live only in `.env`. Aikido scans before and after are in the submission.

## 7. Honest limitations

- **Synthetic data we generated ourselves.** The accuracy numbers prove the pipeline works end to end, not real-world accuracy.
- **Hand-tuned thresholds.** Example: dog vs. cat is decided by the average pet-food ticket (> €42), which is exactly why Marc's cat becomes a dog. Money stress is a crude heuristic: it can fire on one big purchase with 0 days in the red.
- **None of the 4 demo personas is under money stress.** The held-back behaviour is shown on other synthetic customers (95 of them have sales held back).
- **Batch, not real time.** Twins are rebuilt nightly. Corrections apply instantly, but a new life event waits for the next build.
- **Single-customer view.** No households or joint accounts, and no data from other banks.
- **The benchmark is a linear extrapolation** from one laptop, with all customers loaded in memory (≈ 1.9 GB). Production needs partitioned batches.
- **Kate's wording isn't deterministic.** The numbers come from tools, but phrasing varies and replies take a few seconds. Language detection is a simple word list (nl/fr/en).
- **Illustrative catalogue.** Product names follow KBC families, but the descriptions and rates are placeholders. No A/B test or business-impact measurement yet.

## Sources

- OpenAI API pricing, [developers.openai.com/api/docs/pricing](https://developers.openai.com/api/docs/pricing), plus the model pages [gpt-4.1](https://developers.openai.com/api/docs/models/gpt-4.1) and [gpt-4.1-mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini). Seen 2026-09-30.
- KBC, "Kate: five years and five milestones" (Nov 2025), [newsroom.kbc.com/kate-five-years-and-five-milestones](https://newsroom.kbc.com/kate-five-years-and-five-milestones), for 5.8M users, 70% of queries solved, 140+ proactive situations, 400,000+ products/yr, GPT-4.1 since Oct 2025. Seen 2026-09-30.
- Belfius, "BAM! Avec Alan et Mistral AI…", [belfius.be/retail/fr/bam](https://www.belfius.be/retail/fr/bam/index.aspx), for "Hey Belfius" (announced for end 2025) and Mistral AI. Seen 2026-09-30.
- KBC Mobile budgets, subscription overview and duplicate-payment alerts: team market research, plus the KBC newsroom for duplicate payments.
- Repo: `python -m twin.evaluate` (accuracy), `python -m twin.benchmark` (speed), population counts from `twin_profile` (5,000 synthetic twins).
