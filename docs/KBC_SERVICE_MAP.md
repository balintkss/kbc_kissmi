# KBC service map: where the digital twin fits

*Synthesis of `docs/research/*.md` and our PoC code, 30 Sep 2026. Web research only; nothing tested in the live KBC app. Not legal advice.*

> **Promise:** "KBC helps me without making me repeat myself — and I stay in control."
>
> **Positioning:** the twin is the **customer-governed financial memory for Kate**. Kate stays the interface; the twin is the explainable decision layer that Kate, KBC Mobile, kbc.be and advisers all read from.

**How this relates to [`KBC_VALUE_MATRIX.md`](KBC_VALUE_MATRIX.md):** the value matrix sets the positioning, the competitive story and the product guardrails for 7 retail families. This file is the detailed layer underneath it: 55 service families, including the segments the matrix leaves out (youth, private banking, self-employed, SME/agri). Everything here follows the matrix's **Financial Understanding Contract**:

`observed, non-sensitive pattern → hypothesis (confidence + expiry) → customer confirms / edits / rejects → customer-governed memory → goal & affordability check → one next step, explicit approval for any action`

Three rules from the matrix apply to every row. Only **confirmed** facts drive a commercial journey. **Help comes before sales** under money stress. There is a **sensitive-data firewall**: no health, mental-health, pregnancy/birth or other special-category inference from payments or chat; household changes enter only when the customer confirms a neutral change.

## 1. How to read this

- §2 has one row per KBC service family (55 rows, 11 segments). "KBC today" is what public sources show. "Our fit" is what our twin (this repo) already does or could do.
- `[n]` points to §9, where every source is tagged [P] primary or [S] secondary. **(U)** marks an unverified or conflicting claim.
- "Built" means working code in `twin/` and `api/` on our synthetic data (5,000 customers). None of it has run on real KBC data. Our PoC still lets *inferred* facts drive highlights, with a reject path. The contract's confirm-before-commercial-use gate is a roadmap item (§7). The synthetic newborn persona is **a pipeline test only**, not a deployable feature.

| KBC today: maturity | Meaning |
|---|---|
| ① Catalogue | Same page or product for everyone, or human-led with no digital personalisation |
| ② Digital self-service | Customer can simulate, buy and manage it in the app or on the web |
| ③ Rule-based proactive | Kate raises a situation from data (the "140+ situations" [1]) |
| ④ Context-aware | Uses a persistent customer picture across steps (e.g. MyMobility) |

| Our fit | Value-matrix symbol | Meaning |
|---|---|---|
| **Built** | ✓ | Runs today in the PoC (engine, recommender, Kate tools, feedback, ops view) |
| **Small** | ◐ | Reuses existing facts; needs a new rule, message or screen (days) |
| **Medium** | ◐ | Needs a new signal, store or consent flow (weeks) |
| **Large** | ◐ | Needs a new data domain, a company-level twin or a channel integration (months) |
| **Not a fit** | — | Regulation makes it unwise (e.g. MiFID: a personal nudge counts as a recommendation), or the twin adds little |

A "✓/◐" cell means built, but the regulated journey or a human owner still has to take over (the matrix's ◐ meaning).

| Value-matrix family | Rows here |
|---|---|
| Current account, cards and payments | #1–#10 |
| Savings, pension and investment plan | #25–#29, #35 |
| Mortgage, renovation and home loan | #11, #12, #46 |
| Car loan and mobility | #13, #44, #45 |
| Car, home and family insurance | #15–#24 |
| Travel and lifestyle services | #4, #22, #47–#50 |
| Kate and KBC Live advisers | #51–#55 |
| *Not in the matrix* | youth #30–#32, private banking #33–#35, self-employed #36–#39, SME/agri #40–#43, loans #14 |

Twin vocabulary used below (`twin/engine.py`): `employment`, `income` (+payday), `life_event_first_job` / `_new_job`, `has_car` (powertrain, older_car, insured_at, purchase_price, bought_recently), `life_event_new_car`, `pet` (dog/cat), `children`, `childcare`, `life_event_new_baby` (synthetic pipeline test only), `housing`, `life_event_moved`, `commutes_by_train`, `gym_member`, `subscriptions`, `travels`, `saves_monthly`, `financial_buffer`, `money_stress`, plus recurring bills, implications and the payday plan. A signal marked "(new)" is not in the PoC yet.

## 2. Master service map

| Service | KBC today | Twin signals used | What the twin does for it | Example moment | Our fit | Constraint |
|---|---|---|---|---|---|---|
| **Personal daily banking & payments** | | | | | | |
| 1. Current accounts (Plus / Basic pack) | ② Opened with itsme in minutes. 77% choose Plus, €4.25/month from 1 Jan 2026 [15][29] | `income`, `travels`, age | Shows one pack and says why (frequent flyer → Plus for free ATM withdrawals across Europe). Feeds the age-25 switch (#30) | "Plus is worth it for me: I take out cash on every trip." | ◐ Small | Keep every pack one tap away |
| 2. Cards: debit, credit (+ packages), prepaid | ② Card control in the app. Kate checks the card works abroad before a trip. Package prices (U) [29][1] | `travels`, `income`, `money_stress` | Travel package only for frequent travellers. Prepaid framed as a budget tool. No credit card offer under stress | "Six flights this year, so the travel package pays for itself." | ◐ Small | Credit card = consumer credit: CCD2 from 20 Nov 2026 [84] |
| 3. Payments: Wero, instant + Verification of Payee, QR | ② Wero replaced Payconiq on 8 Dec 2025. Automatic VoP warning since 9 Oct 2025 [31] | P2P counterparties (new) | Mainly a signal: regular P2P payments to one person suggest shared rent or a flat-share | n/a | — Not a fit (commodity rail); Small as a signal | Purpose limitation on reusing the P2P graph [83] |
| 4. Multicurrency pockets, eSIM, foreign banknotes | ② Launched Jun 2026: 29 currencies, eSIM for 180+ countries. No trip-triggered prompt found [9][31] | `travels` (flight count only), FX spend, accommodation (new) | Part of **travel mode** (#22): one pre-trip message covering card, currency pocket, eSIM and cover | "Kate suggested a USD pocket a week before New York." | ◐ Medium (we count flights but don't know trip dates) | Extra convenience consent [22] |
| 5. Fraud & security: Secure4u, Guardian Angel, CyberSecure | ③ Strong. 2.5M payments a day checked against 150+ signals. Guardian Angel for >4M customers (15 Sep 2026). CyberSecure €7/€12 a month [10][39] | None shared with fraud (see `docs/PRIVATE_BANKER_AT_SCALE.md`: fraud is a separate, purpose-limited workstream; the commercial twin never feeds fraud scoring and security signals never feed marketing) | Only customer-facing safety help: suggests turning on Guardian Angel at a confirmed life moment, before any CyberSecure sale | "When I retired, KBC suggested making my daughter my Guardian Angel." | ◐ Small (context feed only); not a fit for detection | Help before sales: no insurance pitch right after a fraud case (our rule) |
| **Budgeting & PFA** | | | | | | |
| 6. "In & uit" overview and category budgets | ② Income/expense overview, budgets and the CO2 footprint of spending. Descriptive [28][13] | `income` + payday, recurring bills, `has_car`/`pet` implications, `saves_monthly` | **Payday plan**: bills until the next payday, reserves for implied costs, savings, free money per week. Irregular income is planned on a quiet month | "€2,850 lands on the 23rd. After bills, €131 of reserves and €200 of savings, I have €151 a week." | ✓ **Built** | Legal basis for service profiling to be set with the DPO [83][89] |
| 7. Subscriptions overview | ② Lists 6 months of subscription payments with a link to cancel. No "switch and save" nudge found [28] | `subscriptions`, `gym_member`, recurring bills | A monthly check for price rises and double charges, plus total cost. A full audit on request | "Netflix went up €2. My gym and 2 streaming services cost €71 a month." | ◐ Small | Low |
| 8. Savings goals and boosters ("Sparen voor je dromen") | ② Goals with savings boosters. Doconomy module for 18–25s [28][12] | `saves_monthly`, `financial_buffer`, stated goal (new) | Goal planner with a timeline, shown as its own line in the payday plan | "Wedding fund 40% there. €300 a month gets me there by June." | ◐ Medium (goal store) | Low |
| 9. Kate alerts: duplicate payment, low balance, payment reminders | ③ Part of the 140+ situations. Duplicate-payment and voucher alerts are published [1][21] | recurring bills with next date, payday, `financial_buffer` | Forecasts before it alerts: flags a yearly bill that lands before income arrives (the plan's `heads_up` field exists) | "Heads-up: the €412 mutuality bill is due on the 13th." | ◐ Small (heads-up built for yearly bills) | Extra convenience [22] |
| 10. Money-stress support | ② An overdraft can be requested by typing to Kate [30]. No public hardship or care mode found (U) | `money_stress` (days in the red, spending above income), `financial_buffer` | **Care mode**: every sales message moves to `held_back`. A support message comes first ("move a bill after payday, no fees, no product"). Every page switches to support-first (no credit highlighted; the car-loan page shows a "payday plan first" card). The advisor view flags "support first". Protective use only, so no confirmation is needed | "They saw I was short and offered to move a bill, not a loan." | ✓ **Built** | In the spirit of AI Act Art. 5(1)(b): no exploiting economic vulnerability [86] |
| **Lending** | | | | | | |
| 11. Mortgage (+ bridging loan, loan-balance cover) | ②③ Certainty online in 10–15 min, then a mandatory woonexpert call. Only 20% of applications start digitally. >8/10 also take loan-balance cover. Kate follow-up after a simulation is reported only by a secondary source (U) [16][32][8][3][68] | `housing=renting` + rent, `income`, `financial_buffer`; intent to buy (new) | Highlights the home loan for renters with ≥ 3 months of buffer whose rent is close to a loan payment (built). Pre-fills the woonexpert brief so nothing is asked twice (new) | "I didn't have to repeat my €964 rent or my savings to the woonexpert. We started with the numbers." | ✓/◐ **Built** (highlight); Medium (brief, intent) | KBC's creditworthiness process decides [84]. AI Act high-risk if the twin ever feeds scoring (from 2 Dec 2027) [86] |
| 12. Renovation and energy loans | ② Online simulation. Energy loan at 3.89% from 1 Sep 2026. Setle report accepted. Energy loans +19% in 2025 [33][8] | `housing` (owner), `life_event_moved` (bought_home), energy bills; EPC (new) | Owners see the energy renovation loan (built). Timed after a purchase or a jump in energy bills (new) | "We bought a 1970s house, and the app showed the energy loan, not a car loan." | ✓ **Built** (highlight); Small (timing) | CCD2 advertising rules [84] |
| 13. Car, bike and motorbike loans (incl. Car Loan Plus) | ④ MyMobility: 800+ cars, affordability check, TCO, loan + insurance in a few clicks, Kate follow-up. ~390k users. 95% of new-EV loans are digital. 88% of new-EV borrowers choose Car Loan Plus [7][14][5] | `has_car` (powertrain, older_car, bought_recently, has_car_loan), payday plan | Picks one variant (second-hand, EV rate or new), sized to 35% of free money over 60 months (built). Our catalogue's "green car loan" label should switch to KBC's own EV/PHEV-rate wording [14]. No loan pitch after a cash purchase. E-bike loan for train commuters (new) | "I'd confirmed the car I paid cash for, so it didn't push a loan." | ✓ **Built** | CCD2 creditworthiness and advertising [84]. Guidance, not a credit decision |
| 14. Personal loan and overdraft | ② Personal loan of €1k–€75k in the app. Overdraft up to €750 at 10.09%, requested via Kate [33][30] | `money_stress`, `financial_buffer`, payday plan | Never pushed under stress: sales moments are held back and no credit is highlighted. Kate's rules put cheaper routes first (move a bill, spread a bill) | "Before any overdraft, Kate showed that moving my energy bill fixes the month." | ✓ **Built** (held-back moments, support-first pages) | CCD2 [84]; AI Act Art. 5(1)(b) spirit [86] |
| **Insurance** | | | | | | |
| 15. Car insurance | ② Quote and buy online. Mileage bands only, no pay-as-you-drive. Sold inside MyMobility. Kate suggests moving from omnium to basic cover as the car ages [34][7][22][68] | `has_car` (insured_at, purchase_price, older_car), fuel spend | One cover with the reason (built). "Insured at Ethias: quote in 2 minutes from what you've already shared" (built). Mileage band estimated from fuel spend (new) | "For the €11,500 used car I'd confirmed, it picked mini-omnium and pre-filled the quote." | ✓ **Built** | IDD demands-and-needs test and cross-selling rules (art. 24) [82] |
| 16. Bicycle and two-wheeler insurance | ② Online simulator, cover from the next day. Only 1 in 3 cyclists insured (KBC survey, May 2026) [20] | bike purchase (new), `commutes_by_train` | After an e-bike purchase: one message with bike cover and the bike-loan rate | "I bought a €2,400 e-bike, and the next morning I saw the theft-cover option." | ◐ Medium (new fact) | IDD [82]; Personalised consent for offers [22] |
| 17. Home insurance + home assistance | ② Price in 3 steps online. >9/10 KBC mortgage clients buy it. Cover follows a move for 90 days [35][3] | `life_event_moved`, `housing`; home insurer elsewhere (visible in recurring bills, not a fact yet) | After a move, highlights home insurance (built). Tenant or owner variant. Home insured elsewhere (Lotte pays Ethias €518/yr) (new) | "We moved last month, and the app listed what's left, including contents cover." | ✓ **Built** | IDD [82] |
| 18. Family liability + dog/cat options | ② No personalisation found. Pet options are inside the family policy [36] | `pet` (dog/cat), `children`, `childcare` | Recurring pet spending prompts a question, not a claim: "Add a pet to your plan?" Once the customer confirms: family liability highlighted (built), and for cats the vet/theft option (new) | "I added our dog to my plan, and it showed bites are covered by the family policy." | ✓ **Built** (highlight); Small (ask-first, pet options) | IDD [82]. Ask, don't assert: our dog/cat rule makes mistakes (Marc) |
| 19. Legal assistance | ① Mostly sold by agents. The tax deduction ends from tax year 2026 [36] | weak (life events) | Little. Inferring disputes or a divorce from payments would be intrusive | n/a | — Not a fit | Sensitive inference, weak signal |
| 20. Hospitalisation insurance | ② Quote through an expert or agent. Kate can file a hospital admission [37] | customer-confirmed household change (new), `children` | After the customer confirms a neutral household change, one hospital-cover review. The PoC's newborn trigger (Julien) is a synthetic pipeline test only | "After I told the app our household had grown, it showed how to add someone to our hospital cover." | ◐ Small (confirmed household change); newborn inference is a pipeline test only | Never infer birth or health from payments; hospital bills and birth allowances stay out (GDPR Art. 9, sensitive-data firewall) [83]. Health-insurance pricing is AI Act high-risk (2 Dec 2027) [86] |
| 21. Accident, life (death cover), funeral | ② Simulators in Mobile/Touch, digital signature [37] | confirmed household change (new), `children`, `housing=owner_with_mortgage` | One item on the household-change checklist ("review death cover"). Never priced from inferred data | "The household checklist reminded us to look at life cover." | ◐ Medium | IDD [82]. Life pricing is AI Act high-risk [86] |
| 22. Travel insurance (+ travel mode) | ② The app shows existing cover to avoid duplicates [38]. Kate's card-abroad check [1] | `travels`, KBC products | **Travel mode** (with #4): card, currency pocket, eSIM and cover in one message. One option offered only if the trip isn't covered | "Before my trip Kate said my annual cover already applies." | ◐ Small (fact built, bundle new) | IDD [82] |
| 23. Claims, incl. storm alerts | ② Digital claims, video damage assessment, status tracking. Kate storm-damage alerts since 2021 [40][2] | region/city, `has_car`, `housing`, KBC policies | Pre-fills what is known. Sends storm alerts only to affected policyholders | "After the hail, Kate already had my car and policy. I only added photos." | ◐ Medium | Low (service use) |
| 24. Insurance check-up (gaps and overlaps) | — No public check-up or gap feature found. Group-wide, 30% of insurance products vs 57% of banking products were sold digitally in 2025 [40][3] | all facts, KBC products, insurer elsewhere | One screen: what's covered, what's missing, what's insured elsewhere. `/ops` already counts 5 opportunity rules, 3 of them for insurance (car elsewhere, moved without home cover, newborn without hospital cover; the last is a pipeline test only) | "One screen: car and home are fine, but nothing covers damage my dog causes." | ◐ Small (rules in `twin/population.py`; customer screen new) | IDD demands-and-needs [82]; Personalised consent [22] |
| **Saving & investing** | | | | | | |
| 25. Savings accounts, Start2Save, term accounts | ② Opened in the app. Automatic savings orders. Start2Save max €500/month [44][17] | `financial_buffer`, `saves_monthly`, payday | Buffer under 3 months → savings account with a payday transfer (built) | "1.4 months of buffer is thin, so €150 now moves on payday." | ✓ **Built** | Low |
| 26. Pension savings (fund or insurance) | ② The app shows year-to-date status and "top up to max". The €1,050 cap applies unless the customer picks €1,350. A proactive December reminder is not confirmed (U) [49] | `employment`, age < 64, `financial_buffer`, KBC products | Highlights pension savings when the buffer is healthy and the customer has none (built). Cap reminder in Q4 (new) | "Kate reminded me in November that €310 more gets me the full tax benefit." | ✓/◐ **Built** (highlight); Small (reminder) | The fund falls under MiFID, the insurance under IDD. Nudge the category; suitability before the sale [81][82] |
| 27. Advised investing (Strategie Plus) + MiFID investor profile | ④ 270k+ profiles completed digitally, incl. sustainability preferences. "Regular proactive proposals at appropriate times" in the app. Kate can sell Strategie Plus [46][45][3] | life events, `financial_buffer` | **No fund picks.** Prompts a profile refresh when life changes (KBC already asks clients to do this) and hands over to KBC Live | "After my new job Kate asked if my investor profile still fits." | ◐ Small (trigger only) | MiFID II: a personal nudge presented as suitable is a personal recommendation [81] |
| 28. Investment plan and round-up investing | ② Plan from €25/month. Round-up invests each €10 in a balanced fund (average ≈ €20/month) [47][48] | `financial_buffer` ≥ 3 months, `saves_monthly` | Our savings picker shows "investment plan" once the buffer is healthy (built). In production it must be gated by suitability | "Investing only came up once my buffer was full." | ✓/◐ **Built**, needs gating | MiFID suitability/appropriateness [81] |
| 29. Bolero, ETFs, crypto | ② Execution-only or appropriateness test. ETF Playlist, Invest & Repeat, BTC/ETH since 16 Feb 2026 under MiCA. bluesphere ETFs (retail distribution U) [51][52][53] | none | Nothing product-specific | n/a | — Not a fit | Any push would be a recommendation [81] |
| **Youth & students** | | | | | | |
| 30. Young Person's Account (10–24) + parental dashboard | ② Free for ages 10–24. Parental dashboard for 10–17. No documented journey for the paid switch at 25 (U) [41] | age, `employment` (student → first job), `housing` | Age-25 journey two months ahead: which pack fits now, and the new price | "Before I turned 25 it explained the fee and why Plus still fits me." | ◐ Small | Minors: no marketing profiling under 18 (our rule; DPO to confirm) |
| 31. Baby and child savings ("Mijn baby op komst", Pamper account) | ② In-app entry point for the baby account, with no data trigger [41] | `children` (child-benefit hypothesis, confirmed by the customer) | Child benefit → "Include your children in your plan?" → child savings highlight (built). The new-baby moment is a synthetic pipeline test only | "It suggested putting part of the child benefit aside for both kids." | ✓ **Built** | No birth or pregnancy inference from payments. Household changes enter only when the customer confirms them [83] |
| 32. First salary and moving out (Doconomy, jobstarter, young-adults hub) | ② Goal-based savings module for 18–25s. The jobstarter page is static content [12][41] | `life_event_first_job`, `life_event_moved`, `housing` | Payday plan for the first salary plus a "new job, new plan" moment (built). Move-out checklist (new) | "My first Deloitte salary had a plan waiting before it arrived." | ✓ **Built** | Low |
| **Private banking & wealth** | | | | | | |
| 33. Private Banking, Wealth Management (€5M+) | ① Human-led: dedicated banker, reviews, digital signing, reports in Doccle. PB entry threshold not published (U) [54][55] | life events, `children`; large transfers (new) | Puts life events into the banker's brief through the same audited ops view | "I didn't have to tell my banker about the move again, so we skipped the admin." | ◐ Medium (ops view built; AuM and mandates not in the twin) | MiFID [81]; need-to-know access plus audit log |
| 34. Private Plan, Successiescan, gifting | ① Periodic, human-led reports. No automated refresh or gift-window triggers found [54] | age, `children`, plan date (new) | Refresh prompt for the banker: "plan older than 2 years, and a life event since" | "My banker suggested updating the plan after our second grandchild." | ◐ Medium | Estate data is sensitive: banker-only, never pushed to the customer |
| 35. Retirement planning for mass retail (gap) | — No KBC retirement hub or projection found. Private Plan looks PB-only (U) [49][54] | age, `income`, `saves_monthly`, pension products | A general pace projection plus the cap reminder. Hands over for advice | "It showed my pension-savings pace without selling me a fund." | ◐ Medium | Stay generic, or MiFID applies [81] |
| **Self-employed** | | | | | | |
| 36. Business PRO + Boostpack (starters) | ② Business PRO for €51/year with a free private Plus account. Boostpack of 12 starter benefits (Billit, Dexxter, VAT activation) [57] | switch from salary to invoices (`employment` → self_employed) | Spots the switch on the private account and offers the starter bundle once | "My first invoices came in and KBC offered the starter pack." | ◐ Medium (business-account link) | Personalised consent [22] |
| 37. Invoices, accounting links, Kate reminders | ③ Kate reminds about unpaid customer invoices. Billit is live; Exact, Yuki and Dexxter announced (U). Peppol B2B e-invoicing mandatory since 1 Jan 2026 [60][59][88] | `employment=self_employed`, invoice variance, `income` (quiet month) | **Quiet-month plan** (built: Marc would be €388 short in a quiet month). Invoice ageing from Peppol data later | "My plan assumes a slow month, so August can't catch me out." | ✓ **Built** (quiet month); Medium (Peppol) | Purpose limitation for business data in a personal twin [83] |
| 38. Tax, VAT and social-contribution set-asides + Voorafbetalingsplan | ② Voorafbetalingsplan spreads tax prepayments over 12 months. No automatic set-aside envelopes found (U) [60] | social contributions (in our synthetic data, not reserved yet), VAT (new), `income` | Envelopes in the plan for social contributions, VAT and prepayments. The prepayment plan only when the buffer falls short | "Kate put €820 aside for my Q3 VAT the day the client paid." | ◐ Small | SME Financing Law for the credit part [85] |
| 39. Self-employed pension and protection (VAPZ, POZ, IPT, guaranteed income) | ① Sold by agents and advisers. No digital nudge found. Kate had a VAPZ-optimisation situation in 2021 [61][63][2][67] | `self_employed`, `income`, age, KBC products | A "person + business" gap view for the agent (VAPZ unused, no income cover) | "I didn't have to explain my income swings again. The agent went straight to VAPZ." | ◐ Medium | IDD [82]; advice stays with the agent |
| **SME & agri** | | | | | | |
| 40. Business Dashboard + Kate in BD | ③ Working-capital, CO2 and sector-comparison insights for 150k companies. Kate in BD since 2024 [58][1] | none today (needs a company twin) | Company facts (DSO, payroll peaks, lease ends) on the same fact contract | "BD warned that June holiday pay will squeeze cash." | ◐ Large | Directors' data stays under GDPR [83] |
| 41. Financing, leasing (Autolease), factoring, trade finance | ① Led by relationship managers and specialists; small tickets digital. Autolease: 54k+ vehicles, 95% of 2025 orders EV [60][65][66][3] | company twin (new), lease end dates | Lease-end and seasonal-credit timing in the RM's brief | "My RM called three months before the lease ended." | ◐ Large | SME Financing Law [85] |
| 42. Business insurance, cyber, Better Building tool | ① Agent-led. Cyber cover for 1,500+ SMEs. Better Building shows EPC obligations for non-residential buildings [63][66] | sums insured vs asset growth, building EPC (new) | Renewal review for the agent | "The agent flagged that our new warehouse wasn't in the policy." | ◐ Large | IDD [82] |
| 43. KBC Agro | ① About 70 agri-only staff. Lifecycle offers from start-up to hand-over. Broad weather insurance [64] | seasonal receipts, CAP/VLIF subsidies, farmer age (new) | Seasonal cash plan for farm households (reuses the quiet-month plan). Succession timing for advisers | "My plan follows the harvest, not the calendar." | ◐ Medium | Succession data for advisers only |
| **Beyond banking** | | | | | | |
| 44. MyMobility | ④ Up to 15 vehicles by VIN, TCO, 800+ cars, loan + insurance, Kate follow-up. ~390k users. KBC credits it with ~40% more car-loan market share [7][25][5] | `has_car` + implications; declared VIN, mileage (new) | Two-way: the twin pre-fills the car it detected. A declared VIN upgrades `has_car` to near-stated (≥ 0.9) and sharpens cost estimates | "MyMobility already showed my car and its yearly costs. I just confirmed." | ◐ Small (integration) | Needs Extra convenience [22][25] |
| 45. Mobility services: NMBS/De Lijn tickets, 4411 parking, shared bikes, fuel, VAB, driving lessons | ② 16 services. >2M 4411 sessions, >1M train and >1M De Lijn tickets. Kate adds a teen driver to the policy after driving-school payments (secondary) [5][7][18][24][68] | `commutes_by_train`, `has_car`; routes, parking zones (new) | Commute optimiser (season vs single tickets, employer reimbursement). Learner driver → add them to the car policy | "19 single tickets this month. A season ticket saves €46." | ◐ Medium (new signals) | Partner data only with Extra convenience, under partner terms [24][26] |
| 46. MyHome (Immoscoop, Setle, Impact Us Today, Eliq, Switch Together) | ④ Home search, budget, value, renovation simulation, certificates. 60k users by Q2 2026. Launch dated Mar 2025 or Mar 2026 depending on the source (U) [8][25][5] | `housing`, `life_event_moved`; saved searches, EPC (new) | House-hunting intent with a horizon → deposit goal, plus timing for the mortgage and home cover. EPC → renovation loan | "After I saved a search in Gent, my plan showed a deposit goal." | ◐ Medium | Extra convenience [22]. Intent is not a credit decision [84] |
| 47. Energy: Eliq insights, Mijnenergie switching, group purchase, solar simulator | ②③ Kate already has an energy-saving / supplier-switch situation [27][19][1][68] | energy bills (recurring), `housing`, electric car | Energy-bill watch: direct debit up 22% → compare suppliers or join the group purchase. EV charging at home | "My energy debit rose 22%, and Kate pointed me to the group purchase." | ◐ Small | Digital-meter data comes via a partner and needs consent [27] |
| 48. Kate Coins and Kate Deals | ③ Offers "match the customer's lifestyle". 257k users, €1.7M saved. Needs Personalised (+ Extra convenience for Deals). Criticised as too commercial; coins expired without notice [11][23][69] | `pet`, `has_car`, `commutes_by_train`, `money_stress` | Shows the one deal that matches a *confirmed* fact (pet food for a dog owner, parking for a driver). No deals under stress. Redemptions become weak affinity signals | "I'd added my dog to the plan, and the only deal I saw was dog food." | ◐ Small | Personalised consent. KBC says it doesn't share the data with retailers [23] |
| 49. Kate Wallet | ② Announced 22 Jun 2026 for summer 2026 (live status U): tickets and loyalty cards, meal vouchers later [9] | tickets, meal vouchers (new) | Near-stated evidence: meal vouchers → employee benefits; season ticket → commute | "My plan counted my meal vouchers without me entering them." | ◐ Medium | Extra convenience [22]. Vouchers reveal the employer |
| 50. MyNWS and "important moments" content | ② MyNWS by topic preference. The "important moments" web hub (separation, death, moving) is content only [25][43] | life events, topics read | Surfaces the one relevant article when it matters | "The week we moved, the first article was the moving checklist." | ◐ Small | Sensitive moments (separation, death) only on request |
| **Channels** | | | | | | |
| 51. Kate (chat + 140+ proactive situations) | ③→④ GPT-4.1 since Oct 2025. 140+ situations. 656k leads picked up by staff in Q3 2025, 89k of them sales. KBC's own model tops out at L4 "hyper-personal & contextual". No public memory feature (U) [1][4][21] | all facts, plan, recurring bills | Kate stays the interface; the twin is her memory. Compact twin in the prompt plus 4 tools that do the maths (built). Never re-asks, gives one option with the reason, doesn't sell under stress, replies in nl/fr/en | "Can I afford €1,200 in August? Yes, from your current account." | ✓ **Built** (PoC version of Kate) | AI Act Art. 50(1) disclosure since 2 Aug 2026 [86]. KBC Live can read chats [21] |
| 52. KBC Mobile/Touch, kbc.be and push messages | ② Best mobile banking app (Sia 2021, 2024, 2025). Reviews call the home screen promo-heavy [13][69] | all facts | Same experience blocks on every channel: anonymous → all variants; logged in → one highlight + reason. Max 2 pushes; sales held back under stress (API built, frontends to do) | "The car page showed one option for me, with the reason." | ✓ **Built** (API) | Right to object to marketing, GDPR Art. 21 [83] |
| 53. KBC Live, Expert Vermogensopbouw, Kate leads | ③ Remote advisers who spend about half their time on outbound calls. Kate users get priority handover [45][21][1] | full twin + held-back list | Advisor brief: the customer's own twin, a "support first" flag, every view audited (built in `/ops`). Attach reason + facts to each Kate lead (new) | "The adviser didn't ask anything I'd already answered in the app." | ✓ **Built** (ops view); Small (leads) | Need-to-know access plus audit log. A human decides, so Art. 22 isn't triggered [83] |
| 54. Branch, insurance agents, relationship managers | ① Human-led for mortgages, insurance, PB and SME [32][63][54] | same as #53 | The same brief inside agent and RM tools | "My agent had my car details ready." | ◐ Medium (tool integration) | Same as #53 |
| 55. Privacy settings and "what KBC knows" | ② Extra convenience and Personalised toggles. No customer view of inferred facts found (U) [22][21] | all facts + corrections | Glass box: every fact with confidence, date and evidence. "That's right" and "That's not me" change the plan at once (built). The rest of the contract is new: edit, expiry, "Why am I seeing this?", source badges, Forget | "I said the car is my partner's, and the car reserve disappeared." | ✓ **Built**; Small (badges) | GDPR Art. 13–16: transparency and rectification [83] |

**Tally (55 rows):** ✓ Built 19 (3 of them ✓/◐) · ◐ Small 15 · ◐ Medium 15 · ◐ Large 3 · — Not a fit 3. Rows that are Built with a Small or Medium follow-up count as Built. In production, every "Built" row that makes a commercial highlight or push still needs the confirmation gate (§7).

## 3. Segment scorecards

**3.1 Personal daily banking & payments**
- KBC today: best mobile banking app worldwide (Sia 2021/2024/2025) [13]; Plus pack chosen by 77% [15]. Fraud stack screens 2.5M payments a day, and Guardian Angel reaches >4M customers [10]. FX pockets and eSIM (Jun 2026) have no trip trigger [9].
- Biggest twin opportunity: tie the separate travel tools into one pre-trip moment. Beyond that, daily banking is mainly a *signal source*.
- Top 2 use cases: travel mode (#4, #22); the right pack, incl. the age-25 switch (#1, #30).
- Don't claim as new: fraud detection, the card-abroad check (Kate already does it [1]), instant payments or VoP.

**3.2 Budgeting & PFA**
- KBC today: In & uit, budgets, a subscription list with a cancel link, savings goals with boosters [28]. Kate duplicate-payment and low-balance alerts [1][21]. All descriptive: no payday plan or bill forecast found [28].
- Biggest twin opportunity: turn descriptive PFM into a forward-looking payday plan that includes *implied* costs. This is the twin's most complete area.
- Top 2 use cases: payday plan with safe-to-spend (#6, #9); money-stress care mode (#10).
- Don't claim as new: budgets, the subscription list, duplicate-payment alerts, savings goals.

**3.3 Lending**
- KBC today: MyMobility is already context-aware (affordability, TCO, Kate follow-up, ~390k users, ~40% more car-loan share) [7][5]. Mortgages are hybrid: 10–15 min online certainty, then a woonexpert call; only 20% start digitally [16][32][8].
- Biggest twin opportunity: a mortgage hand-off where nothing is asked twice, with home-loan conversations timed from rent + buffer + stated intent.
- Top 2 use cases: woonexpert brief pre-filled from the twin (#11); loans sized to the payday plan and never pushed after a cash purchase or under stress (#13, #14).
- Don't claim as new: car affordability checks, TCO, instant mortgage certainty (since 2019 [16]).

**3.4 Insurance**
- KBC today: broad catalogue with digital quotes and claims, incl. video damage assessment [34][40]. Insurance sells digitally far less than banking: 30% vs 57% (group, 2025) [3]. Cross-selling is concentrated at the mortgage (>9/10 take home insurance) [3]. No public gap check, no telematics [40][34]. Only 1 in 3 cyclists insured [20].
- Biggest twin opportunity: a fact-driven household check-up. The rules already run in `/ops`. In our synthetic data 2,118 of 3,350 car owners insure elsewhere.
- Top 2 use cases: car insured elsewhere → 2-minute quote from confirmed facts (#15); a cover review after a *confirmed* change (move → home, household change → hospital, pet → liability) (#17, #18, #20, #24).
- Don't claim as new: the travel duplicate-cover check [38], the omnium → basic suggestion [22][68], storm alerts [2].

**3.5 Saving & investing**
- KBC today: 270k+ digital MiFID profiles with sustainability preferences, and proactive proposals in the app [46][3]. RI funds are 51% of direct client money [3][87]. Round-up investing and plans from €25 [48][47]. New 10% capital gains withholding since 1 Jun 2026 [50].
- Biggest twin opportunity: the twin as a *trigger* (buffer full, new job, a household change the customer confirmed) for a profile refresh or advice, never as the recommender.
- Top 2 use cases: buffer → savings on payday (#25); pension-cap reminder (#26).
- Don't claim as new: personalised investment advice, or "AI that picks funds" (MiFID applies, and KBC is already proactive).

**3.6 Youth & students**
- KBC today: free account for ages 10–24 with a parental dashboard [41]. Doconomy module for 18–25s [12]. Jobstarter content is static; K'Ching is probably discontinued (U) [41][42].
- Biggest twin opportunity: predictable transitions (first salary, moving out, turning 25). The twin detects a first job with 97.9% recall on synthetic data.
- Top 2 use cases: first-salary plan (#32); age-25 pack switch (#30).
- Don't claim as new: goal-based saving for young adults, the baby-account entry point.

**3.7 Private banking & wealth**
- KBC today: human-led and award-winning. Digital covers monitoring, alerts and e-signing [54][3]. Private Plan and Successiescan are periodic, with no automated triggers [54]. Mass-affluent planning looks PB-only (U).
- Biggest twin opportunity: life-event triggers in the banker's brief, and a generic retirement-pace view for mass-affluent clients.
- Top 2 use cases: banker brief with life events (#33); plan-refresh trigger (#34).
- Don't claim as new: planning or estate tools. Also, Puilaetco is not KBC (it belongs to Quintet) [56].

**3.8 Self-employed**
- KBC today: an open ecosystem: Business PRO, Boostpack, Billit/Peppol, Kate unpaid-invoice reminders [57][60][59]. No automatic VAT or social-contribution envelopes found (U) [60]. The private + business view exists only as a human service [62].
- Biggest twin opportunity: one "person + business" plan: the quiet-month plan plus tax envelopes.
- Top 2 use cases: quiet-month plan (#37, built for Marc); VAT and social-contribution envelopes with prepayment deadlines (#38).
- Don't claim as new: invoice reminders, accounting integrations, tax-prepayment credit.

**3.9 SME & agri**
- KBC today: Business Dashboard insights for 150k companies; Kate in BD since 2024 [58][1]. Agro specialists [64]. Advice is led by RMs and agents; no public cash-flow forecasting (U).
- Biggest twin opportunity: a company twin on the same fact contract (later).
- Top 2 use cases: seasonal cash plan for farm and sole-trader households (#43); lease-end and renewal triggers for RMs (#41).
- Don't claim as new: working-capital insights, CO2 footprint, sector benchmarks.

**3.10 Beyond banking**
- KBC today: data-rich hubs (MyMobility ~390k users, MyHome 60k) [5]. 16 mobility services with millions of transactions [7]. Kate Coins: 257k users [11]. Criticised as "too commercial" [69].
- Biggest twin opportunity: ecosystem data (VIN, EAN, route) as near-stated evidence that raises twin confidence. In return, the twin gives the hubs implied costs and life events.
- Top 2 use cases: MyMobility ↔ twin (#44); energy-bill watch and commute optimiser (#47, #45).
- Don't claim as new: TCO, affordability checks, energy insights, group purchasing.

**3.11 Channels**
- KBC today: Kate has 140+ situations, runs on GPT-4.1, produced 656k leads in Q3 2025, and follows a maturity model up to L4 [1][4]. Autonomy figures conflict: 82% in Belgium for FY2025 vs 77% in 2Q2026 (secondary, U) [4][6]. Consent gates exist [22]. No public cross-conversation memory or "what Kate knows" view (U) [21].
- Biggest twin opportunity: be the **customer-governed financial memory for Kate**. Kate stays the interface; the twin is the explainable decision layer that Kate, app, web and advisers share, with memory the customer can see, correct and delete.
- Top 2 use cases: twin-grounded Kate with "Kate remembered" (#51, #55); advisor brief (#53).
- Don't claim as new: proactive Kate, an LLM-based Kate, human handover. Don't claim "we know everything": cash and other-bank activity stay outside the picture (see the value matrix).

## 4. Opportunity heatmap

Scores 1–5. For regulatory risk, **5 = low risk**, so a higher total is always better.

| Segment | Customer value | Business value for KBC | Differentiation vs KBC today | Feasibility on KBC data | Reg. risk (5 = low) | Total /25 | Rationale |
|---|---|---|---|---|---|---|---|
| Channels (Kate, app, advisers) | 5 | 5 | 5 | 4 | 3 | **22** | Shared context + visible memory exist nowhere publicly; AI Act Art. 50 and GDPR purpose limits apply |
| Budgeting & PFA | 5 | 3 | 4 | 5 | 4 | **21** | Built; KBC's PFM is descriptive; value is retention and trust more than direct sales |
| Insurance | 4 | 5 | 4 | 4 | 3 | **20** | Weakest digital sales (30%), no gap check; IDD and Art. 9 need care |
| Youth & students | 4 | 4 | 3 | 5 | 3 | **19** | Predictable transitions, lifetime value; minors need extra care |
| Self-employed | 5 | 4 | 4 | 3 | 3 | **19** | Irregular income is a real pain; Peppol data exists but must be linked |
| Lending | 4 | 5 | 3 | 4 | 2 | **18** | High value, but MyMobility is strong; CCD2 and AI Act high-risk |
| Personal daily banking | 3 | 2 | 2 | 5 | 5 | **17** | KBC is best in class; the twin mostly adds travel mode and signals |
| Beyond banking | 4 | 4 | 3 | 3 | 3 | **17** | Rich data; hubs already ④; partner terms and consent limit reach |
| Saving & investing | 3 | 4 | 2 | 4 | 1 | **14** | KBC already proactive under MiFID; the twin can only trigger |
| SME & agri | 3 | 4 | 2 | 2 | 3 | **14** | Needs a company twin; BD already has insights |
| Private banking & wealth | 3 | 3 | 3 | 2 | 2 | **13** | Human-led, data outside the twin; strong existing service |

**Top 10 use cases across segments (ranked)**

1. **Kate grounded in the twin + "Kate remembered"** (Channels; #51, #55): Kate never re-asks, and what the customer tells her updates the twin visibly. *Built / Medium.*
2. **Payday plan with implied reserves and safe-to-spend** (PFA; #6, #9). *Built / Small.*
3. **Money-stress care mode across every channel** (PFA; #10, #14, #48). *Built.*
4. **Household insurance check-up**: insured elsewhere, moved, confirmed household change, confirmed pet (Insurance; #15, #17, #18, #20, #24). *Highlights built / screen Small.*
5. **Advisor and KBC Live brief; reason + facts on every Kate lead** (Channels; #53, #54). *Built / Small.*
6. **Life-moment checklists across bank + insurer** for a car, move, first job or a household change the customer confirms (cross-segment; #13, #17, #21, #31, #32). *Moments built / checklist Medium.*
7. **Self-employed quiet-month plan + tax envelopes** (#37, #38). *Built / Small.*
8. **MyMobility ↔ twin, two-way car facts** (#44, #13, #15). *Small.*
9. **Youth transitions**: first salary, moving out, turning 25 (#30, #32). *Built / Small.*
10. **Travel mode**: card, FX pocket, eSIM and cover in one message (#4, #22). *Medium.*

Runners-up: home-loan timing from renting + stated intent (#11, #46), energy-bill watch (#47), pension-cap reminder (#26), investor-profile refresh trigger (#27).

## 5. Kate as a personal financial assistant

Ranked by fit with the twin. Taken from the 22 research ideas, deduplicated, plus our own "can I afford it?" and the self-employed envelopes.

| # | Feature | What the customer experiences | Twin signals | Mode | Benchmark | PoC status | Effort |
|---|---|---|---|---|---|---|---|
| 1 | Payday plan + approve-to-act sorter | On payday: "Move €131 to reserves and €200 to savings? [Approve]". The same split is one tap next month | `income`, recurring bills, implications, `saves_monthly` | Proactive | Monzo Salary Sorter [70]; KBC "never without explicit approval" [1]; Revolut approval for sensitive actions [71] | Partly (plan built; money movement new) | S |
| 2 | Safe-to-spend and overdraft forecast | "€151 free this week". Five days' warning when a bill would overdraw you before payday | payday, recurring bills, balance, `financial_buffer` | Proactive | ING Kijk Vooruit [73], CBA Bill Sense [79], Emma [76], Erica 7-day [77] | Partly (per-week figure and yearly-bill heads-up built) | S |
| 3 | Money-stress care mode | Offers pause; help comes first (move a bill, spread a bill); a human on call | `money_stress`, `financial_buffer` | Proactive | CBA hardship support [79]; the Klarna walk-back [75] | Built (held-back + support message); call-back new | S |
| 4 | "Can I afford it?" | "€1,200 holiday in August?" → yes, yes with savings, tight, or no, with a per-payday suggestion | plan, buffer, 90-day spending | On request | bunq Finn [72], Revolut AIR [71] | Built (`check_affordability`) | — |
| 5 | "Kate remembered" memory | After a chat: "Kate remembered: buying a house in 2027 [Edit] [Forget]" | chat-stated facts (§6) | Both | ChatGPT memory controls [90] | New | M |
| 6 | Life-moment checklist | After a move or a household change the customer confirms: "5 things", each with a status (child benefit, hospital cover, child savings, death cover, childcare costs) | life events, confirmed household change, KBC products | Proactive | Belfius life moments [74], CBA [79], KBC "important moments" [43] | Partly (moments built) | M |
| 7 | Insurance fit and overlap check | At renewal or after a life event: one screen, one highlighted option ("9-year-old car on full omnium → mini-omnium") | `has_car` + insurer, KBC products, life events | Proactive | Kate's omnium → basic situation [22] | Partly (highlights + ops rules) | M |
| 8 | Bill and subscription watch | "Netflix +€2", "two Spotify charges", "trial turns paid tomorrow", and an audit of what you'd save | `subscriptions`, `gym_member`, recurring bills | Proactive | Capital One Eno [78], Revolut AIR [71], Rocket Money [76] | Partly (facts built) | S (M for trials) |
| 9 | Advisor handover brief | When Kate escalates, the adviser sees the twin and a "don't re-ask" list | full twin, chat context | On request | Kate leads to staff [1]; the Klarna lesson [75] | Partly (`/ops` view built) | S |
| 10 | Next-best-conversation arbiter | The same single top item on every channel, max 2 pushes a week, service before sales, holdout group | all facts, priorities | Proactive | CBA Customer Engagement Engine [79] | Partly (ranking, 2-push cap, held-back) | M |
| 11 | "Save the raise" | "Your salary went up €240. Keep €100 of it in savings automatically?" | `life_event_new_job`, `income`; bonus / holiday pay (in synthetic data) | Proactive | Cleo Autopilot [76] | Partly (new-job fact built) | S |
| 12 | Goal planner with timeline | "House deposit €30k by 2028: 18% there, on track at €420 a month" | stated goal, `saves_monthly`, `housing` | Both | Emma, Cleo [76] | New | M |
| 13 | Travel mode | Trip detected → card active abroad, cover, currency pocket, eSIM | `travels`, FX spend | Proactive | Kate trip check [1], Belfius [74], Revolut AIR [71] | Partly (`travels` built) | S–M |
| 14 | Self-employed tax envelopes | "Set aside €820 for Q3 VAT and €610 for social contributions" when an invoice is paid | `self_employed`, invoices, tax payments | Proactive | KBC Voorafbetalingsplan [60] | Partly (quiet-month plan built) | S |
| 15 | Belgian benefits and premiums finder | "You may be entitled to: service-voucher tax credit, renovation premium, social energy tariff" | `children`, `housing`, `money_stress`, `self_employed` | Proactive | CBA Benefits finder [79] | New | M |

Merged or dropped: the commute optimiser and car TCO coach went to rows #45 and #44 (KBC already has TCO in MyMobility). Energy-bill watch went to #47 (Kate already has an energy situation). The monthly money story and "what's this payment?" are half-covered by Kate's `spending_summary` tool. The weekly nudge merged into #2, sinking funds into #1, and free-trial and audit into #8.

## 6. Kate as a signal source ("collect information from Kate")

What customers tell Kate is the richest twin signal, and also the most regulated. KBC publishes nothing about Kate remembering across conversations. It does say that chats are "not strictly confidential" (KBC Live staff can read them) (U on memory) [21][1]. In the value matrix's Financial Understanding Contract, Kate is where the "customer confirms / edits / rejects" step and the customer-governed memory happen in conversation. The monthly **Financial Understanding Check-in** described in the matrix (§6 there: at most 1–2 non-sensitive questions, each with "Why am I seeing this?", "Not now" and "Don't use this category") is the same step outside the chat.

**6.1 Signal types**

| Type | Example utterance | Twin mapping | Default confidence | Expiry | Allowed use |
|---|---|---|---|---|---|
| Stated fact | "I sold my car", "we have a cat" | existing key (`has_car=false`, `pet=cat`), `source=kate_chat` | 0.95 | none; re-check if transactions contradict for 60 days | service; offers only with Personalised |
| Correction | "That car is my partner's" | same as a glass-box "That's not me" (`rejected_by_customer` + note) | 1.0 | sticky, 12 months | suppress everywhere |
| Intent with horizon | "Buying a house next year", "EV in 6 months" | `intent_*` fact `{what, horizon}` | 0.7 | horizon + 90 days unless reconfirmed | timely guidance; one highlight near the horizon |
| Goal | "€10k for the wedding by June 2027" | `goals[]` `{label, amount, date}` | 1.0 | on the date, or when reached | payday plan line, goal planner |
| Preference / constraint | "Don't call me", "no offers", "answer in English" | preference store (not a fact), mirrored to KBC's commercial settings | 1.0 | until changed | **hard rule** checked before every channel |
| Stress / sentiment | "I'm broke until payday" | transient `stated_stress`; no raw text stored | 0.6 | 30 days | **protective only**: suppress sales, offer help |
| Special category | "I'm pregnant", "I'm in chemo", "seeing a therapist" | **never stored or inferred**; at most a neutral household change the customer confirms | n/a | n/a | never for marketing, pricing, eligibility or credit |
| About third parties | "My mother moved into a care home" | at most a customer-level need ("supports a parent"), and only after opt-in | 0.6 | 12 months | service only |

**6.2 Source priority and conflict rules**

1. **Customer-confirmed** (glass box, check-in or chat correction) > **stated in Kate** (committed through the chip, so it counts as memory) > **ecosystem-declared** (MyMobility VIN, MyHome EPC, NMBS route; ≥ 0.9) > **transaction-inferred** (a *hypothesis* with the rule's confidence and an expiry). Within one source, the newest wins. Only confirmed or stated facts may drive a commercial journey. Inferred hypotheses drive service (the plan) and a question.
2. A statement beats inference when it is made, but it doesn't silence later evidence. If newer transactions contradict it with ≥ 0.8 confidence for 60 days (e.g. "sold my car" but 6 fuel purchases since), set `status=conflict`, stop using it for offers, and ask once in the glass box.
3. Intents decay (confidence × 0.5 after the horizon), then expire. An intent **graduates into a fact** when transactions confirm it (notary fee → `housing=owner`; dealer payment → `life_event_new_car`).
4. Rejections are sticky for 12 months unless a *new kind* of evidence appears.
5. Preferences are never overridden by any source. Stress signals can only ever make the twin more protective.

**6.3 Consent and transparency UX**

- Every session opens with "I'm Kate, KBC's AI assistant" and a link to "What Kate knows about me". AI Act Art. 50(1) applies from 2 Aug 2026 and was not delayed [86].
- A toggle, "Let Kate remember what I tell her", sits under *Extra convenience* and is **off until the customer turns it on**. Commercial use needs *Personalised* too [22][89]. A **private chat** mode neither uses nor creates memories [90].
- A chip appears after each save: **"Kate remembered: buying a house in 2027 [Edit] [Forget]"**. Kate *proposes* and the chip *commits*: nothing is saved if the customer undoes it. For intents and goals Kate first asks "Shall I remember this?"
- Each fact in the glass box carries a source badge: "From your transactions (7 payments)" · "You told Kate on 12 Sep" · "From MyMobility" · "You confirmed".
- **Forget** deletes the memory *and* everything derived from it (reserves, highlights) within 24 h, and logs the deletion. Deleting a chat and deleting a memory are separate, clearly labelled actions [90].
- "Don't contact me" or "no offers" updates KBC's commercial settings immediately, and Kate confirms it. The GDPR right to object to direct marketing (Art. 21(2)–(3)) is absolute [83].

**6.4 Sensitive-data firewall.** Never infer *or retain* health, mental health, pregnancy/birth, religion, politics, sexual orientation, ethnicity or union membership, whether from payments, merchant names or chat. This is the value matrix's rule 4. It covers *inferred* data too: the CJEU (C-252/21, C-184/20) treats data that reveals such traits as special category even when the inference is indirect or wrong [83]. Kate helps in the moment and stores nothing sensitive. The most she can offer is a **neutral household change** the customer confirms ("our household is growing"). Whether it may carry a date needs legal sign-off (U). The block list is enforced server-side in the tool, not in the prompt. Our PoC's `life_event_new_baby` rule (birth allowance, baby spending, hospital bill) is a **synthetic pipeline test only** and is not a production feature. Helena medical data never feeds the twin [24].

**6.5 AI Act and credit.** Art. 50(3) (emotion recognition) covers biometric inference only. Text sentiment falls outside it, but GDPR fairness still applies (U: our reading) [86]. Art. 5(1)(b) is why stress is protective only. The high-risk duties for credit scoring and life/health pricing now start on 2 Dec 2027 [86]. CCD2 (from 20 Nov 2026) keeps special-category data out of creditworthiness assessments [84], so chat-derived facts never enter a credit decision. The LLM vendor should work under zero-retention terms, as Revolut's does [71][89].

**6.6 How it maps onto our fact schema.** Today a fact is `key, value, confidence, since, evidence (transaction ids), summary, implies`, and `twin/feedback.py` overlays `rejected_by_customer`, `confirmed_by_customer` and `customer_note`. We add five fields and allow message ids as evidence:

```json
"has_car": { "key": "has_car", "value": false, "confidence": 0.95, "since": "2026-09-24",
  "source": "kate_chat",              "stated_at": "2026-09-30T10:12:00Z",
  "expires_at": null,                 "status": "active",
  "consent": "extra_convenience",     "evidence": ["msg:8812"],
  "summary": "You told Kate on 30 Sep: sold the car", "implies": [] }
```

- `source` ∈ transactions | ecosystem | kate_chat | customer_feedback. `status` ∈ active | conflict | expired. `evidence` holds a message id and **never raw chat text**.
- A new Kate tool, `remember(kind, key, value, horizon?, quote_span)`, is limited to a whitelist of keys. Like the 4 existing tools in `twin/assistant.py`, it is bound to the session's customer, so the model can't pick a customer id. The server validates the call, blocks special-category keys, writes a *proposed* row and shows the chip.
- The read path reuses the feedback overlay. `apply_feedback()` already turns a correction into plan changes without a rebuild. Stated facts become a second overlay (stated > inferred) on the nightly twin.

**6.7 Five worked examples**

| Customer says | Stored as | What changes in plan / highlight / moments | Guardrail |
|---|---|---|---|
| "I sold my car last week." (Lotte) | Stated fact `has_car=false`, `kate_chat`, 0.95, `msg:` evidence | Same path as "That's not me". The car-upkeep reserve (€80) and fuel estimate (€187) leave the plan, so free money goes from **€151 to €213 a week**. The new-car push and the car-insurance highlight disappear (run through `twin/feedback.py` on Lotte's twin) | Fuel purchases continue for 60 days → `conflict`, and the glass box asks once |
| "We want to buy a house next year." | Intent `intent_buy_home {horizon: 2027}`, 0.7, expires horizon + 90 days, after "Shall I remember this?" | Lotte's home topic already highlights the home loan (€964 rent, 6.4 months of buffer). Now a deposit-goal line joins the payday plan, MyHome is suggested, and a woonexpert moment is scheduled near the horizon | Guidance only, not a credit decision; no loan push under stress [84] |
| "Stop sending me offers." | Preference `no_offers` (hard rule), mirrored into the *Personalised* setting | Every sales moment moves to `held_back` with the reason "customer opted out". The payday plan and support messages continue. Kate confirms the change | Art. 21(2)–(3) objection is absolute [83] |
| "I'm pregnant, due in March." | Special category: **nothing about the pregnancy is stored** | Kate answers in the moment with general info. She offers: "Shall I add an expected household change to your plan, so I can prepare a checklist?" Only after an explicit yes is a neutral `household_change: expected` stored (with or without a month, pending legal sign-off (U)). It unlocks the household checklist (#6 in §5) and a plan line for childcare costs. The twin never learns this from payments: the PoC's birth-allowance rule is a pipeline test only | Firewall: Art. 9 covers inferred data too [83]; never used for marketing, pricing or credit |
| "I'm broke until payday." | `stated_stress`, 0.6, 30 days, no raw text | Treated like `money_stress`: sales held back, the support moment goes to the top, and Kate offers to move a bill until after payday. The overdraft is not pitched | Protective use only (AI Act Art. 5(1)(b) spirit) [86] |

## 7. Roadmap

**Now: in the PoC (synthetic data)**
- Twin engine: 20+ fact types with confidence, date and evidence; implications; recurring bills; payday plan and quiet-month plan (`twin/engine.py`).
- One highlight per topic (5 topics, 15 variants), with the same JSON for app, web and Kate (`twin/recommender.py`, `api/main.py`).
- Moments: max 2 pushes; sales held back and pages switched to support-first under money stress (597 of 5,000 synthetic customers get a support message). The newborn moment is a pipeline test only.
- Glass box with corrections that re-plan instantly (`twin/feedback.py`, `/api/me/twin`).
- Kate on GPT-4.1 with 4 grounded tools, replying in nl/fr/en (`twin/assistant.py`).
- Ops and advisor view with 5 opportunity rules and an audit log of every customer view (`twin/population.py`, `api/ops.py`).

**Next: hackathon + 3 months**
- **Confirmation gate** (the Financial Understanding Contract): inferred facts become hypotheses with an expiry. Commercial highlights and pushes only use confirmed facts. Unconfirmed facts feed the plan and one monthly check-in question. The newborn and hospital evidence rules are removed from any production path.
- Kate as a signal source: the `remember` tool, `source`/`expires_at`/`status` fields, the chip, Forget, private chat (§6).
- A customer-facing insurance check-up built from the ops rules, plus "home insured elsewhere" as a fact (#24, #17).
- Self-employed envelopes (social contributions, VAT) in the quiet-month plan (#38).
- Travel mode, with trip dates from flights plus accommodation (#4, #22).
- Advisor brief attached to Kate leads and KBC Live handovers (#53).
- Shadow run on a pseudonymised real sample, showing only facts above a confidence threshold.
- *Prerequisites:* DPO decision on the legal basis for each use (service vs marketing) and the mapping to *Extra convenience* / *Personalised*; Art. 50 disclosure text; zero-retention terms with the LLM vendor; MiFID/IDD review of the savings and pension highlights.

**Later: 12 months**
- Ecosystem signals as near-stated facts: MyMobility VIN, MyHome EPC and searches, NMBS routes, 4411 parking, Eliq (#44–#47).
- Households and joint accounts (couples, parent–child links).
- A next-best-conversation arbiter across all channels, with weekly caps and a holdout group to measure uplift.
- A company twin for the self-employed and SMEs on the same fact contract (Peppol invoices, VAT, lease ends) (#37, #40, #41).
- MiFID-safe triggers: investor-profile refresh, pension cap, retirement pace (#26, #27, #35).
- Integration into agent and RM tools (#54).
- *Prerequisites:* partner data-sharing terms; a household consent model; AI Act high-risk readiness by 2 Dec 2027 if anything touches credit or insurance pricing; CCD2 compliance (20 Nov 2026) for credit messages; a measurement framework (fact confirmation rate, highlight acceptance, held-back volume).

## 8. What this means for our pitch

- **Promise and position.** "KBC helps me without making me repeat myself — and I stay in control." The twin is the **customer-governed financial memory for Kate**. Kate stays the interface, and the twin is the explainable decision layer behind Kate, the app, the web and advisers. For the positioning, competitor lines and "say this, not that", use [`KBC_VALUE_MATRIX.md`](KBC_VALUE_MATRIX.md); this file is the per-service evidence underneath it.
- **Broadened claim: "one memory, 11 segments".** The same Financial Understanding Contract reaches 55 KBC service families: 19 run in the PoC today, and 30 more are small or medium extensions on the same fact contract. Only 3 are not a fit, and we say why. KBC is already context-aware in MyMobility and MyHome and proactive in 140+ situations [7][8][1]. We don't replace those; we give them one shared, correctable memory, a niche KBC has left open publicly (U) [21].
- **Demo extension 1: "Kate remembered".** Lotte says "I sold my car". The chip appears, her free money jumps from €151 to €213 a week, and the car messages vanish. This reuses the existing feedback overlay.
- **Demo extension 2: insurance check-up.** Lotte's car *and* home are insured at Ethias. One screen, one quote from facts we already hold, sitting on the segment with the weakest digital sales (30%) [3].
- **Demo extension 3: Marc's self-employed plan.** A quiet month would leave him €388 short. Add social-contribution and VAT envelopes, and the plan tells him what to keep aside when a good month comes in.
- **Honest caveats:** synthetic data we generated ourselves; the newborn persona is a pipeline test, not a feature; the PoC lets inferred facts drive highlights, and the confirmation gate is still to build; no ecosystem, household or business data in the PoC; payment data is partial (cash, other banks); reach is limited to customers who opted into *Extra convenience*; the twin only triggers investment conversations and never advises (MiFID); the rules are hand-tuned, but the fact contract lets any rule be swapped for a trained model later (as Nubank does with nuFormer) [80].

## 9. Sources

Tags: **[P]** primary (KBC, a regulator, or the company itself) · **[S]** secondary (press, blog, review, third-party summary). **(U)** = unverified or conflicting. Deduplicated across the three research files.

**KBC group, newsroom and investor documents**
- [1] [P] KBC, "Kate: five years and five milestones", 24 Nov 2025: https://newsroom.kbc.com/kate-five-years-and-five-milestones · https://www.kbc.com/content/dam/kbccom/doc/newsroom/pressreleases/2025/20251124_Vijf%20jaar%20Kate_EN.pdf
- [2] [P] KBC, "Kate, your personal digital assistant" (2021 figures): https://newsroom.kbc.com/kate-your-personal-digital-assistant
- [3] [P] KBC Group Annual Report 2025 (one research note could only read excerpts (U)): https://www.kbc.com/content/dam/kbccom/doc/investor-relations/Results/jvs-2025/jvs-2025-grp-en.pdf
- [4] [P] KBC 4Q/FY2025 company presentation: https://wcmassets.kbc.be/content/dam/kbccom/doc/investor-relations/Results/4q2025/4q2025-company-presentation.pdf
- [5] [P] KBC 2Q2026 results: https://newsroom.kbc.com/kbc-group-second-quarter-result-of-1-152-million-euros · https://wcmassets.kbc.be/content/dam/kbccom/doc/investor-relations/Results/2q2026/2q2026-quarterly-report-en.pdf.cdn.res/last-modified/1785941395577/2q2026-quarterly-report-en.pdf
- [6] [S] Investing.com, Q2 2026 slides and earnings-call transcript (figures U): https://www.investing.com/news/company-news/kbc-group-q2-2026-slides-strong-results-drive-guidance-upgrade-93CH-4840503 · https://www.investing.com/news/transcripts/earnings-call-transcript-kbc-group-lifts-2026-outlook-after-strong-q2-93CH-4840397
- [7] [P] MyMobility, 25 Nov 2025: https://newsroom.kbc.com/discover-mymobility-kbcs-digital-mobility-dashboard · https://www.kbc.com/content/dam/kbccom/doc/newsroom/pressreleases/2025/20251125_MyMobility_EN.pdf
- [8] [P] KBC Economics, renovation pace and MyHome, 29 Jan 2026: https://newsroom.kbc.com/kbc-economics-belgiums-renovation-pace-remains-far-too-low · https://www.kbc.com/content/dam/kbccom/doc/newsroom/pressreleases/2026/20260129%20MyHome_EN.pdf
- [9] [P] Kate Wallet, multicurrency, eSIM, 22 Jun 2026: https://newsroom.kbc.com/kbc-launches-kate-wallet-this-summer-and-makes-payments-in-foreign-currencies-easy · [S] https://www.dvo.be/artikel/kbc-lanceert-eigen-digitale-wallet-en-multicurrency-functie-in-kbc-mobile
- [10] [P] Guardian Angel, 10 Feb and 15 Sep 2026: https://newsroom.kbc.com/a-first-of-its-kind-in-belgium-activate-guardian-angel-for-suspicious-payments · https://newsroom.kbc.com/kbc-brings-guardian-angel-to-more-than-4-million-customers-in-belgium
- [11] [P] Kate Coins, Nov 2023 and 9 Sep 2025: https://newsroom.kbc.com/kbc-enables-customers-to-earn-money-with-kate-and-kate-coins · https://newsroom.kbc.com/you-can-now-do-more-with-kate-coinsmore-benefit-more-experience
- [12] [P] Doconomy partnership, 2 Jan 2025: https://newsroom.kbc.com/doconomy-announces-partnership-with-kbc-providing-younger-generations-access-to-financial-wellbeing-tools
- [13] [P] Sia 2025 award, 24 Sep 2025: https://www.kbc.com/content/dam/kbccom/doc/newsroom/pressreleases/2025/Sia%20Awards%202025_EN.pdf
- [14] [P] Motor Show 2026 offers, 9 Jan 2026: https://www.kbc.com/content/dam/kbccom/doc/newsroom/pressreleases/2026/2026%20persbericht%20autosalon%20ENG.pdf
- [15] [P] Account charges 2026 and 2024 offering update: https://www.kbc.com/content/dam/kbccom/doc/newsroom/pressreleases/2025/20250926%20aanpassing%20tarief%20rekeningen%20ENG.pdf · https://newsroom.kbc.com/kbc-responds-to-changing-customer-behaviour-by-updating-its-account-offerings
- [16] [P] Home-loan certainty in 10 minutes (2019): https://newsroom.kbc.com/kbc-offers-certainty-on-home-loans-in-just-ten-minutes · https://newsroom.kbc.com/ook-niet-klanten-krijgen-nu-binnen-10-minuten-instant-krediet-en-tariefzekerheid
- [17] [P] Start2Save rates from 1 Aug 2026: https://newsroom.kbc.com/kbc-kbc-brussels-and-cbc-will-adapt-interest-rates-on-start2save-and-start2save4-savings-accounts-as-of-1-august-2026 · [S] https://www.test-aankoop.be/invest/sparen/sparen/spaarrekeningen/2026/07/kbc-verhoogt-spaarrente-start2save-315
- [18] [P] "Differently: the Next Level" and mobility solutions (2020): https://newsroom.kbc.com/kbc-shifts-digital-transformation-and-customer-experience-up-a-gear-differently-the-next-level · https://newsroom.kbc.com/new-handy-solutions-in-kbc-mobile-for-those-travelling-by-car-or-public-transport
- [19] [P] Mijnenergie.be: https://newsroom.kbc.com/met-mijnenergiebe-helpt-kbc-u-aan-een-voordelig-energietarief
- [20] [P] Bicycle insurance and cycling survey, 21 May 2026: https://www.kbc.be/retail/en/insurance/vehicle/bicycle-insurance.html · https://newsroom.kbc.com/belgians-cycle-more-often-and-further-but-lag-behind-when-it-comes-to-bicycle-maintenance-and-knowledge-of-insurance-and-other-services

**kbc.be: Kate, app and ecosystem**
- [21] [P] Kate page and FAQ: https://www.kbc.be/retail/en/campaign/bespaar-tijd-met-kate.html · https://www.kbc.be/particulieren/nl/product/betalen/zelf-bankieren/met-je-smartphone/mobile/kbc-mobile-faqs/Kate-FAQ.html
- [22] [P] Extra convenience and commercial settings: https://www.kbc.be/particulieren/nl/product/betalen/zelf-bankieren/met-je-smartphone/mobile/kbc-mobile-faqs/communicatie-contact-acties.html · https://www.kbcbrussels.be/retail/en/products/payments/self-banking/on-your-smartphone/mobile/mobile-faq/communicatie-contact-acties.html
- [23] [P] Kate Deals FAQ: https://www.kbc.be/retail/en/products/payments/self-banking/on-your-smartphone/mobile/mobile-faq/deals.html
- [24] [P] Additional and extra services: https://www.kbc.be/retail/en/products/payments/self-banking/on-your-smartphone/mobile/mobile-faq/additional-services.html · https://www.kbc.be/particulieren/nl/product/betalen/zelf-bankieren/met-je-smartphone/mobile/kbc-mobile-faqs/extra-diensten.html
- [25] [P] MyMobility / MyHome / MyNWS FAQ: https://www.kbc.be/particulieren/nl/product/betalen/zelf-bankieren/met-je-smartphone/mobile/kbc-mobile-faqs/themas.html
- [26] [P] Ecosystem partners: https://www.kbc.be/particulieren/nl/product/betalen/zelf-bankieren/ecosystemen-partners.html
- [27] [P] Energy insights (Eliq): https://www.kbc.be/retail/en/products/payments/self-banking/on-your-smartphone/mobile/energy-insights.html
- [28] [P] PFM and savings goals: https://www.kbc.be/particulieren/nl/product/betalen/zelf-bankieren/met-je-smartphone/mobile/sparen-voor-je-dromen.html · https://www.kbcbrussels.be/retail/en/products/payments/self-banking/on-your-smartphone/new-in-mobile.html

**kbc.be: retail products**
- [29] [P] Accounts and cards: https://www.kbcbrussels.be/retail/en/products/payments/current-accounts/compare-current-accounts.html · https://www.kbc.be/retail/en/products/payments.html · https://www.kbc.be/particulieren/nl/betalen/betaalkaarten/vergelijk-kaarten.html · https://www.kbc.be/retail/en/payments/payment-cards/credit-cards/kbc-credit-card.html
- [30] [P] Overdraft: https://www.kbc.be/retail/en/products/payments/current-accounts/overdraft-facility.html
- [31] [P] Wero, MobilePay, instant payments and VoP, foreign currency: https://www.kbc.be/retail/en/products/payments/self-banking/wero.html · https://www.kbc.be/retail/en/products/payments/self-banking/on-your-smartphone/mobile/mobilepay.html · https://www.kbc.be/content/particulieren/nl/betalen/instantpayments.html · https://www.kbc.be/particulieren/nl/product/betalen/vreemde-valuta-bestellen.html
- [32] [P] Mortgages: https://www.kbc.be/particulieren/nl/lenen/wonen/hypothecaire-lening.html · https://www.kbcbrussels.be/particulieren/nl/lenen/wonen/je-woonproject-in-15-minuten.html · https://www.kbc.be/retail/en/loans/home.html · https://www.kbc.be/particulieren/nl/lenen/wonen/huis-kopen-zonder-zorgen.html
- [33] [P] Energy loan and personal loans: https://www.kbc.be/particulieren/nl/lenen/wonen/groene-energielening.html · https://www.kbc.be/particulieren/nl/lenen/persoonlijke-lening.html · https://www.kbc.be/particulieren/nl/lenen/faq-lening-op-afbetaling.html
- [34] [P] Insurance overview and car insurance: https://www.kbc.be/retail/en/products/insurance.html · https://www.kbc.be/retail/en/insurance/vehicle/car-insurance.html
- [35] [P] Home insurance and moving: https://www.kbc.be/retail/en/insurance/home.html · https://www.kbc.be/particulieren/nl/verzekeren/wonen/wat-doen-bij-verhuis.html
- [36] [P] Family liability, pets, legal assistance: https://www.kbc.be/retail/en/insurance/family/your-family-insurance.html · https://www.kbc.be/particulieren/nl/verzekeren/gezin/hond-verzekeren.html · https://www.kbc.be/particulieren/nl/verzekeren/gezin/rechtsbijstand-familiale-verzekering.html
- [37] [P] Hospitalisation, accident, life, loan-balance: https://www.kbc.be/retail/en/insurance/family/hospitalisation-insurance.html · https://www.kbc.be/retail/en/insurance/family/accident-insurance.html · https://www.kbc.be/retail/en/insurance/family/life-insurance.html · https://www.kbc.be/retail/en/insurance/home/loan-balance-insurance.html
- [38] [P] Travel insurance: https://www.kbc.be/retail/en/insurance/family/travel-insurance.html
- [39] [P] CyberSecure: https://www.kbc.be/retail/en/insurance/family/cybersecure-insurance.html
- [40] [P] Claims and insurance in KBC Mobile: https://www.kbc.be/retail/en/insurance/insurance-claims.html · https://www.kbc.be/retail/en/products/payments/self-banking/on-your-smartphone/mobile/insurance-onthego.html
- [41] [P] Youth, child and baby accounts, jobstarter, young adults: https://www.kbc.be/retail/en/products/payments/current-accounts/young-person-s-account.html · https://www.kbc.be/retail/en/payments/account-for-your-child.html · https://www.kbc.be/particulieren/nl/sparen/spaarrekeningen/pamperrekening.html · https://www.kbc.be/particulieren/nl/jongeren/jobstarter.html · https://www.kbc.be/young-adults/nl/geldbeheer.html
- [42] [P] K'Ching, 2019 (current status U): https://newsroom.kbc.com/nog-een-studentenjob-regelen-rekening-delen-onder-vrienden
- [43] [P] Important moments: https://www.kbc.be/particulieren/nl/belangrijke-momenten.html
- [44] [P] Savings, Start2Save, term account: https://www.kbc.be/particulieren/nl/sparen/spaarrekeningen.html · https://www.kbc.be/particulieren/nl/sparen/spaarrekeningen/start2save.html · https://www.kbc.be/particulieren/nl/sparen/termijnrekening.html
- [45] [P] Advised investing and KBC Live experts: https://www.kbc.be/particulieren/nl/product/beleggen/beleggingsfondsen/easy-invest-service-extra.html · https://www.kbc.be/particulieren/nl/beleggen/slim-beleggen.html · https://www.kbc.be/jobs/nl/expertises/retail/expert-vermogensopbouw-worden.html
- [46] [P] Investor profile: https://www.kbc.be/particulieren/nl/beleggen/beleggersprofiel.html
- [47] [P] Saving and investing in KBC Mobile: https://www.kbc.be/particulieren/nl/product/betalen/zelf-bankieren/met-je-smartphone/mobile/sparen-en-beleggen-in-kbc-mobile.html
- [48] [P] Round-up investing: https://www.kbc.be/particulieren/nl/beleggen/beleggen-met-je-wisselgeld.html
- [49] [P] Pension savings, branch 21/23: https://www.kbc.be/particulieren/nl/pensioensparen.html · https://www.kbc.be/particulieren/nl/pensioensparen/pensioensparen-maximum.html · https://www.kbc.be/particulieren/nl/pensioensparen/pensioenspaarverzekering/home-pension-plan.html · https://www.kbc.be/particulieren/nl/sparen/tak-23/life-long-term-fund-plan.html
- [50] [P] Capital gains tax and SFDR disclosures: https://www.kbc.be/particulieren/nl/nieuws/arizona-regeerakkoord-meerwaardebelasting.html · https://www.kbc.be/particulieren/nl/juridische-info/documentatie-beleggen/Sustainability-related-disclosures.html
- [51] [P] Bolero: https://www.bolero.be/nl · https://www.bolero.be/nl/lp/invest-repeat · [S] https://www.test-aankoop.be/invest/beleggen/etf/artikels/2025/02/bolero-invest-repeat-etf-play-list
- [52] [S] Cointelegraph, crypto on Bolero: https://cointelegraph.com/news/kbc-bank-bitcoin-ether-investment-belgium
- [53] [P] bluesphere ETFs: https://newsroom.kbc.com/kbc-asset-management-enters-europes-rapidly-growing-etf-market-with-unique-czk-hedged-etf · [S] https://etfexpress.com/2026/06/26/kbc-expands-european-etf-range/
- [54] [P] Private banking, wealth management, Private Plan, succession, digital tools: https://www.kbc.be/private-banking/nl.html · https://www.kbc.be/private-banking/nl/wealth-management.html · https://www.kbc.be/private-banking/nl/private-plan.html · https://www.kbc.be/private-banking/nl/successieplanning/successieplanning-voor-particulieren.html · https://www.kbc.be/private-banking/en/portfolio-management/digital-tools.html
- [55] [S] PB thresholds (U): https://www.bankshopper.be/private-banking/kbc-private-banking/ · https://top10privatebanks.com/bank/kbc-private-banking.html
- [56] [S] Quintet (Puilaetco is not KBC): https://en.wikipedia.org/wiki/Quintet_Private_Bank · https://www.quintet.com/en-gb/about-quintet/history

**kbc.be: business**
- [57] [P] Business PRO and starting a business: https://www.kbc.be/ondernemen/nl/product/betalen-en-betaald-worden/zakelijke-rekeningen/business-pro.html · https://www.kbc.be/ondernemen/nl/sleutelmomenten/zaak-starten.html
- [58] [P] Business Dashboard: https://www.kbc.be/ondernemen/nl/product/betalen-en-betaald-worden/online-bankieren/computer/alles-over-business-dashboard/business-dashboard.html · https://www.kbc.be/commercial-banking/nl/betalingsverkeer/kbc-business-dashboard.html
- [59] [S] Accountancy Vandaag, 26 Nov 2025: https://accountancyvandaag.be/kbc-mobile-koppelt-met-boekhoud-en-facturatiepakketten-een-open-strategie-om-cashflow-te-verbeteren/
- [60] [P] Freelancers, business sitemap, Voorafbetalingsplan: https://www.kbc.be/ondernemen/nl/specifieke-sectoren/freelancers-consultants.html · https://www.kbc.be/ondernemen/nl/sitemap.html · https://www.kbc.be/ondernemen/nl/product/kredieten/voorafbetalingsplan.html
- [61] [P] POZ, IPT, VAPZ: https://www.kbc.be/ondernemen/nl/product/verzekeringen/jezelf-en-je-medewerkers/gezin/poz.html · https://www.kbc.be/ondernemen/nl/product/verzekeringen/jezelf-en-je-medewerkers/gezin/ipt-individuele-pensioentoezegging.html · https://www.kbc.be/ondernemen/nl/artikel/einde-ondernemerscarriere/pensioen/vrij-aanvullend-pensioen-zelfstandigen.html
- [62] [P] Investing for entrepreneurs: https://www.kbc.be/ondernemen/nl/product/sparen-beleggen/easy-invest-business.html · https://www.kbc.be/ondernemen/nl/product/sparen-beleggen/vermogensservice-for-business.html
- [63] [P] Business insurance and cyber: https://www.kbc.be/ondernemen/nl/product/verzekeringen.html · https://www.kbc.be/ondernemen/nl/product/verzekeringen/patrimonium/cyberverzekering.html
- [64] [P] KBC Agro: https://www.kbc.be/ondernemen/nl/specifieke-sectoren/landbouw-en-tuinbouw/agro.html · [S] https://vilt.be/nl/nieuws/land-en-tuinbouwers-staan-er-niet-alleen-voor-kbc-agro-als-fiscaal-juridisch-klankbord
- [65] [P] Leasing, Autolease, bike leasing: https://www.kbc.be/commercial-banking/nl/product/financieren/leasing.html · https://www.kbc.be/autolease/nl.html · https://www.kbc.be/autolease/nl/vlootbeheerder/fietsleasing/fietsleasing.html
- [66] [P] Commercial Finance, KBC Reach, Better Building, financing: https://www.kbc.be/corporate/nl/artikel/betalingsverkeer/facturen-goud-waard-comfin.html · https://www.kbc.be/corporate/en/product/payments/tools/kbc-reach.html · https://www.kbc.be/corporate/nl/financieren/vastgoed/better-building-tool.html · https://www.kbc.be/commercial-banking/nl/financieren.html
- [67] [S] kbc.be business news, "Maak kennis met Kate": https://www.kbc.be/ondernemen/nl/nieuws/provibes/algemeen/kate.html

**Commentary and customer criticism**
- [68] [S] Commentary on Kate: https://en.paperjam.lu/article/meet-kate-an-ai-that-does-the-work-of-300-people-at-kbc · https://thebankingscene.com/opinions/meet-digital-assistant-kate-when-digital-transformation-gets-personal/ · https://thebankingscene.com/opinions/kbc-generative-ai-for-customer-centric-banking/ · https://www.linkedin.com/pulse/kate-digital-assistants-banking-kasper-peters
- [69] [S] App Store reviews and a Test-Aankoop complaint: https://apps.apple.com/be/app/kbc-mobile/id458066754?see-all=reviews&platform=ipad · https://www.test-aankoop.be/klagen/publieke-klachten/ongevraagd-verwijderen-van-kat/ea8882b2ffc4662163

**PFA benchmark**
- [70] [S] Monzo: https://monzo.com/blog/2019/09/26/introducing-salary-sorter-and-bills-pots · https://monzo.com/features/monzo-payday
- [71] [S] Revolut AIR: https://www.revolut.com/news/revolut_enters_new_era_of_money_intelligence_with_launch_of_ai_assistant/ · https://www.fintechweekly.com/news/revolut-air-ai-assistant-uk-customers-launch-2026
- [72] [S] bunq Finn: https://aws.amazon.com/blogs/machine-learning/how-bunq-handles-97-of-support-with-amazon-bedrock/
- [73] [S] ING Kijk Vooruit: https://www.ing.nl/particulier/digitaal-bankieren/jouw-app/kijk-vooruit/kijk-vooruit · https://www.ing.be/nl/particulieren/voor-elke-dag/budget-voorspellen-beheren
- [74] [S] Belfius "Hey Belfius": https://www.larevuedudigital.com/la-banque-belge-belfius-developpe-son-assistant-virtuel-en-ia-generative-avec-mistral-ai/ · https://www.lalibre.be/economie/entreprises-startup/2026/04/01/internationalisation-assistant-digital-neobanque-rebel-belfius-devoile-son-plan-2030-3FI6ZNQOYZGGXOBWODVNJYQD3A/
- [75] [S] Klarna: https://openai.com/index/klarna/ · https://www.forbes.com/sites/quickerbettertech/2025/05/18/business-tech-news-klarna-reverses-on-ai-says-customers-like-talking-to-people/
- [76] [S] Cleo, Rocket Money, Emma: https://lendedu.com/blog/cleo-app-review/ · https://www.rocketmoney.com/learn/personal-finance/does-rocket-money-work · https://moneytothemasses.com/banking/emma-review-is-it-the-best-budgeting-app
- [77] [P] BofA Erica (the 60%-proactive figure is from [S] coverage): https://newsroom.bankofamerica.com/content/newsroom/press-releases/2025/08/a-decade-of-ai-innovation--bofa-s-virtual-assistant-erica-surpas.html · https://thefinancialbrand.com/news/banking-technology/bofa-spends-billions-on-erica-and-other-leading-edge-tech-194239
- [78] [P] Capital One Eno: https://www.capitalone.com/learn-grow/money-management/eno-manages-finances/
- [79] [S] CommBank Customer Engagement Engine, Bill Sense, benefits finder: https://www.itnews.com.au/news/cba-system-suggests-20m-customer-conversations-a-day-493688 · https://www.commbank.com.au/digital-banking/bill-sense.html · https://www.cio.inc/commonwealth-bank-australia-builds-ai-native-banking-a-30513
- [80] [S] Nubank nuFormer: https://building.nu.com/how-nubank-uses-transformers-to-model-financial-habits-at-scale/

**Regulation, privacy and memory**
- [81] [P] MiFID II, Del. Reg. 2017/565, ESMA suitability guidelines, FSMA: https://eur-lex.europa.eu/eli/dir/2014/65/oj · https://eur-lex.europa.eu/eli/reg_del/2017/565/oj · https://www.esma.europa.eu/sites/default/files/2023-04/ESMA35-43-3172_Guidelines_on_certain_aspects_of_the_MiFID_II_suitability_requirements.pdf · https://www.fsma.be/en/news/certain-aspects-appropriateness-and-execution-only-requirements
- [82] [P] IDD and Del. Reg. 2017/2359: https://eur-lex.europa.eu/eli/dir/2016/97/oj · https://eur-lex.europa.eu/eli/reg_del/2017/2359/oj
- [83] [P] GDPR: https://eur-lex.europa.eu/eli/reg/2016/679/oj · [S] CJEU C-252/21 and C-184/20: https://privacymatters.dlapiper.com/2023/07/eu-cjeus-landmark-decision-in-meta-vs-bundeskartellamt/
- [84] [P] CCD2, Dir. 2023/2225 (applies 20 Nov 2026): https://eur-lex.europa.eu/eli/dir/2023/2225/oj/eng · [S] https://www.schoenherr.eu/content/consumer-credit-directive-ii-consumer-credit-legislation-for-the-digital-age
- [85] [P] Belgian SME Financing Law: https://economie.fgov.be/nl/themas/ondernemingen/een-onderneming-beheren-en/krediet-aanvragen-voor-uw-kmo/de-wet-over-kmo-financiering
- [86] [P] EU AI Act: https://eur-lex.europa.eu/eli/reg/2024/1689/oj · [S] Jones Walker on Art. 50 and the Digital Omnibus: https://www.joneswalker.com/en/insights/blogs/ai-law-blog/yes-august-2-still-matters-the-eu-approved-a-high-risk-ai-delay-but-most-trans.html?id=102nbon
- [87] [P] SFDR: https://eur-lex.europa.eu/eli/reg/2019/2088/oj
- [88] [S] Belgian Peppol B2B e-invoicing mandate: https://econnect.eu/en/docs/knowledge/regulations/europe/belgium/overview
- [89] [P] EDPB guidelines on legitimate interest, virtual voice assistants, and LLM privacy risks: https://www.edpb.europa.eu/system/files/2024-10/edpb_guidelines_202401_legitimateinterest_en.pdf · https://www.edpb.europa.eu/system/files/2021-03/edpb_guidelines_022021_virtual_voice_assistants_adopted-public-consultation_en.pdf · https://www.edpb.europa.eu/system/files/2025-04/ai-privacy-risks-and-mitigations-in-llms.pdf
- [90] [P] OpenAI memory controls: https://openai.com/index/memory-and-new-controls-for-chatgpt/ · https://help.openai.com/en/articles/8590148-memory-in-chatgpt

*PoC figures (Lotte's plan, Marc's quiet month, 2,118 of 3,350 car owners insured elsewhere, 597 support messages, 97.9% first-job recall) come from this repo on synthetic data: `twin/engine.py`, `twin/feedback.py`, `python -m twin.evaluate`, `docs/PITCH.md`.*
