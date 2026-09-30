# Kate, the KBC Mobile ecosystem, PFA benchmark and Kate-as-a-signal-source

Research note for the Digital Twin PoC · compiled 2026-09-30 · web research only, nothing tested in the live app.
Tags: **[P]** = primary source (KBC, a regulator, or the company itself) · **[S]** = secondary (press, blog, review site, earnings-call summary) · **[U]** = unverified, conflicting, or our own inference.

## Summary

- **Kate is big, proactive and increasingly commercial.** As of 2Q2026 she reaches 6.2M customers in 5 countries and solves about 75% of queries without a human [P4]. She has made 140+ kinds of proactive suggestion in Belgium [P1], runs fully on GPT-4.1 since Oct 2025 ("Kate 2.0") [P1][P3], and produces roughly 400–490k converted sales leads a year [P3][S5]. KBC's stated next steps are advice on housing, mobility and energy, plus agentic AI, "but never without explicit customer approval" [P1].
- **Consent comes in two layers.** A privacy setting called *"Extra convenience / Extra gebruiksgemak"* lets Kate analyse your data and act proactively. A commercial setting, *"Personalised"*, turns on tailored offers. Kate Coins, Kate Deals, MyMobility and MyHome all depend on these settings [P11][P16][P24]. KBC does **not** say anything public about Kate remembering things across conversations. What it does say: conversations are "not strictly confidential" (KBC Live staff can read them), they may be analysed automatically, and Kate profiles you from your transaction and product data [P9].
- **The "beyond banking" ecosystem is a large source of signals we don't use yet.** It covers 16 mobility services (more than 2M 4411 parking sessions, more than 1M train tickets and more than 1M De Lijn tickets), MyMobility (about 390k customers), MyHome (60k customers), Eliq energy data, Immoscoop/Setle, eSIM, event tickets and Kate Wallet (summer 2026) [P4][P21][P22][P17]. Each one reveals commuting, car ownership, house-hunting or travel with far more certainty than card transactions alone.
- **The best PFAs share three patterns.** (1) Money is sorted on payday (Monzo). (2) The app looks ahead: bills until payday and safe-to-spend (CBA Bill Sense, ING Kijk Vooruit, Emma). (3) One engine decides the next-best conversation across all channels, with service before sales (CBA's engine makes 35–55M decisions a day [S41]). About 60% of Erica's interactions are proactive [S39]. Klarna's 2025 walk-back of its AI-only support is the cautionary tale.
- **What customers say to Kate is the richest twin signal, but also the most regulated.** Our proposal: separate stated facts, intents with an expiry date, goals, preferences and a short-lived stress signal. Rank them customer-confirmed > stated > inferred. Show a "Kate remembered: … [Edit] [Forget]" chip after each save. Never extract special-category data (pregnancy, health, religion, union membership) automatically. The EU AI Act's chatbot-disclosure rule (Art. 50) has applied since **2 Aug 2026**. The high-risk credit-scoring and insurance-pricing duties moved to **2 Dec 2027** [S43]. CCD2 applies from **20 Nov 2026** [S49].

---

## A. Kate today

### A1. Timeline and headline numbers

| When | Metric | Src |
|---|---|---|
| 24 Nov 2020 | Launch in KBC Mobile (BE) and ČSOB (CZ). 14 use cases in BE, 7 in CZ. Name = "KBC's Assistant To Ease your mind" | [S7][P1] |
| Apr 2021 | 781k unique users. 2.36M conversations, 30% led to an action. 90% of questions understood, 12% handed to KBC Live. 27.8k proactive notifications with 24% acceptance. 41,850 opted in to "advanced Kate" before the campaign; ~60% acceptance after the May 2021 campaign **[U: the denominator isn't defined]** | [P2] |
| Nov 2023 | 30M+ interactions. 283k customers had earned Kate Coins. German added (NL/FR/EN/DE) | [P15] |
| ~2024 (undated) | 5.7M users (+19% YoY). 19k conversations/day. 70% solved autonomously. "More than 125 situations" with proactive proposals. Over 2M of 2.3M KBC Mobile users had chatted with Kate. Workload of 300+ FTE | [S6] |
| Sep 2025 | 73M interactions. Kate Coins: 257k users since Jan 2023, €1.7M saved in total | [P14] |
| Oct 2025 | Kate runs **entirely on GPT-4.1**. Reason given: customers expect more empathy and accuracy since ChatGPT. Result: better at understanding and "remembering" complex questions | [P1] |
| 24 Nov 2025 | 5.8M digital customers (BE, CZ, HU, SK, BG). 70% solved independently. 80M conversations. Work of 356+ FTE. Contributes to 400k+ products sold a year. **140+ proactive situations in BE.** Q3 2025: 656k Kate leads picked up by staff, 89k became sales (~13.6%) | [P1] |
| FY2025 (Feb 2026) | 6.0M users. Autonomy **82% BE / 69% CZ**. 398k converted Kate leads in the last 12 months. "Kate 2.0 using LLM" in BE | [P3] |
| 2Q2026 (Aug 2026) | 6.2M customers. ~75% solved autonomously on average. Workload of 400+ commercial FTE | [P4] |
| 2Q2026 call | 77% BE / 75% CZ (Kate 2.0 now also in CZ). 484k converted leads LTM. "488k sales" in the quarter. ~19% lead-to-contract in BE | [S5] **[U: summary of the earnings call]** |

The autonomy figure depends on the source: 70% group (Nov 2025), 82% BE (FY2025), then 77% BE (2Q2026). The definitions probably differ, or the LLM switch changed the measurement. **[U]**

### A2. What Kate does

- **Questions and information.** Product questions, grounded on kbc.be. Since 2023 the generative part summarises public website content [S8]. Also income and spending questions, transaction search, finding documents (insurance certificates, tax certificates), MyNWS articles [P9].
- **Transactions she can execute** [P9][P10]:
  - domestic and international transfers, cancelling a transfer, QR payments, standing orders, viewing direct debits
  - blocking or replacing a card, PIN reset, card and account limits, activating a card for use abroad
  - ordering foreign currency, filing a damage claim
  - buying funds or topping up existing funds
  - updating personal details
  - applying for a credit card, mortgage or travel insurance
  - buying bus tickets
  - checking, earning and spending Kate Coins
- **Handover.** If Kate can't solve it, she routes you to KBC Live, which gets priority for Kate users [P9].
- **Languages.** NL, FR, DE and EN in Belgium [P9]. Local languages in CZ/HU/SK/BG **[U: implied by the 5-country roll-out]**. Voice exists; early reviews reported speech-recognition problems [S13].

**Concrete proactive situations ("Kate2You") we could find. KBC only publishes examples of the 140+ situations.**

| # | Situation | Likely trigger signal | Src |
|---|---|---|---|
| 1 | Duplicate payment, or payment to the wrong account number | same amount + beneficiary within a short window | [P1][P9] |
| 2 | Service vouchers (Pluxee) almost used up | voucher balance | [P1][P11] |
| 3 | Leaving on a trip: is your card activated for abroad? | travel booking or location | [P1] |
| 4 | Wrong-PIN alert; suspected fraud | card events, fraud model | [P2] |
| 5 | Store the warranty for an electronics purchase | merchant category | [P2] |
| 6 | Optimise the VAPZ/VSPSS pension prepayment (self-employed) | self-employed status, calendar | [P2][S18] |
| 7 | File a storm-damage claim after severe weather in your area (e.g. Namur floods, 25 Jul 2021) | weather feed + home address | [P11][S] |
| 8 | Switch car insurance from full omnium to basic cover as the car ages | car age and policy | [P11][S7] |
| 9 | Save on your energy bill / switch energy supplier | energy direct debits | [P9][S7] |
| 10 | Add a teenage driver to the car policy after payments to a driving school are detected | driving-school transactions | [S7] |
| 11 | Mortgage follow-up after a loan simulation | simulation event | [S7] |
| 12 | AssurCard number and automatic hospital-claim handling | hospital admission | [P12] |
| 13 | Automatic 4411 parking and parking-cost savings | parking usage | [P12][S] |
| 14 | Payment reminders, policy-review nudges, low-balance alerts | balances, policies | [P9] **[U: from a page summary]** |
| 15 | Alerts about chances to earn Kate Coins | partner offers | [P15] |
| 16 | CZ: energy-price comparison, pet insurance, travel insurance | CZ app | [P12] |

**KBC's design principles** (FY2025 deck [P3]):
- Interactions are "triggered by data analysis (approval granted by customer)".
- Kate only makes offers that add real value or that serve "an important moment in the client's life".
- Journeys driven by time or location are left to Kate because those notifications feel highly personal.
- Security and fraud count as service.
- Maturity model: L1 Q&A, L2 reactive end-to-end, L3 proactive end-to-end, L4 "hyper-personal & contextual".
- The **"Kate brain"** is fed by KBC's own data plus third-party services, with feedback loops from every interaction.

### A3. Consent model

| Setting (KBC Mobile › Profile › Privacy / Commercial settings) | What it unlocks | Src |
|---|---|---|
| **Extra convenience ("Extra (gebruiks)gemak")**, formerly "advanced Kate" | Proactive Kate: KBC analyses your data to spot situations (the storm, omnium and voucher examples). Required for MyMobility and for the full MyHome | [P11][P24][P25] |
| **Commercial: "Personalised"** (vs standard) | Tailored commercial messages. Required for Kate Coins, together with a KBC current account | [P1][P14] |
| **Kate Deals** | Needs *both* Personalised and Extra convenience, plus age 18+ and a personal current account | [P16] |

You are always free to accept or refuse a proposal, and if you accept, the solution is fully digital [P2].

### A4. Kate Coins, Kate Deals, Kate Wallet

- **Kate Coins (2023).** You earn coins when you buy KBC products (home loan, insurance, pension saving, round-up investing, a Setle renovation simulation) or partner offers. Coins can be swapped for vouchers, cashback, deals, events, or donated to De Warmste Week. Since Sep 2025 coins earned at one partner can be spent at another. "10 coins = €15" deals exist [P14][P15]. In MyMobility you get 50 coins for a vehicle purchase and 100 each for a loan or insurance [P24].
  - Partners in 2025: Colruyt, Kinepolis, HelloFresh, Telenet, Inno, Amazon, Pizza Hut, Just Russel, Q-Park, Bofrost, KBC, Bolero [P14].
  - Partners in 2023: Brussels Airport, Omnia Travel, Filou & Friends, Poppy, Lucien, Foodmaker [P15].
  - Coin value: the FAQ says ≥ €1 per coin, while a Test-Aankoop complaint mentions 250 coins ≈ €1.25 **[U: conflicting]**.
- **Kate Deals.** Cashback or discount codes from retailers. You activate a deal in the app, pay with KBC, and the cashback is credited on the 1st business day of the next month. KBC picks the deals using your data and "does not share" it with retailers [P16].
- **Kate Wallet (announced Jun 2026, launching summer 2026).** KBC's own NFC wallet, a first for a Belgian bank. It holds:
  - payment cards and loyalty cards
  - De Lijn, NMBS and parking tickets, plus event tickets
  - later: Monizze, Pluxee and Payflip vouchers

  It also adds multi-currency on your existing account: 29 currencies, and €1,500 a month without FX fees [P17].

### A5. Kate for business and for employees

- **Kate4Business.** Available in the Business Dashboard for corporates since 2024: payments, reports, insurance [P1]. Live in BE, CZ and BG, with SK and HU planned [P3]. For the self-employed: VAPZ optimisation, energy savings, appointments [S18].
- **Kate4Commercial Employees (2022).** Automates reports and document reading, and hands out "Kate leads" (656k picked up in Q3 2025, 89k became sales) [P1]. Kate also steers commercial priorities and gives managers coaching tools [P3].
- **MyKate.** Internal HR, IT and facilities assistant [P1].
- **"Kate in a box".** Built once at group level on a shared cloud stack, with one persona in every country [P3].

### A6. Roadmap as stated

- GPT-4.1 is "a first step" towards a personal assistant.
- Agentic AI is being explored, "but Kate will never implement anything without explicit customer approval".
- Kate will become "even more personalised and proactive, combining customer queries with personal data", advising on housing, mobility and energy [P1].
- CIO Erik Luts: advice on "what a customer can do with their savings or what they should look out for when buying a home", and alerting customers "to opportunities as they happen" [P1].
- The 2Q2026 report adds housing, mobility and travel ecospheres "increasingly powered by Kate", and a digital-transformation investor event on **11 Feb 2027** [P4].

### A7. Personal data and memory: what KBC says

- To answer, Kate uses the product pages, MyNWS, and "details needed to answer your question" (e.g. your transaction history for a payment look-up) [P9].
- If you don't ask Kate anything, no personal data is processed *for the digital assistant* **[S: search excerpt of a kbc.be page]**.
- For proactive Kate, KBC analyses historical and new data (transactions, product use, market and behavioural analyses) to predict "behaviour, wishes, risks and needs" (profiling) **[S: search excerpt of the KBC privacy text]**.
- Conversations are "not strictly confidential": KBC Live staff can see your Kate conversation [P9]. KBC may analyse conversations automatically to improve the service **[S]**.
- **Memory across conversations: KBC says nothing about it publicly.** "Remembering more complex questions" after GPT-4.1 [P1] reads as context *within* a conversation. There is no public "what Kate remembers" view and no delete-a-memory control **[U]**. This is an open niche for our glass-box twin.

### A8. Criticism and limitations

- **Too commercial.** App-store reviews (4.6/5 from 274k ratings) complain that Kate Coins and promotions dominate the login and home screens, and that the app is turning into an "advertising platform" [S19].
- **Coins expiring without notice.** Test-Aankoop complaint, Oct 2025 [S20].
- **Early limits.** Few use cases at launch, voice not trained on banking jargon, Flemish accent support lagging [S13]. The first generative-AI step was modest: summarising website content, which the author calls "incremental" [S8].
- **Trust.** A partner revenue model could erode trust in how the bank handles data [S13]. About 25–30% of queries still need a human [P1][P4].

**What this means for our PoC:** KBC already has the triggers, consent flags and GPT-4.1. What it lacks publicly is (a) one explainable profile shared by all 140+ triggers, (b) a customer-visible, correctable memory, and (c) an explicit "service before sales" rule. That gap is exactly our twin's story.

---

## B. KBC Mobile "beyond banking" ecosystem and the signals it produces

Most partner services go through Olympus Mobility or the partner's own privacy terms [P21]. KBC says data from extra services can make offers "more tailored", and "certain partners make your data available to KBC" [P26]. **Any use for the twin needs Extra convenience consent** [U: our reading].

| Domain | Service (what it is) | Signals it generates | Twin fact / use |
|---|---|---|---|
| Mobility | **NMBS/SNCB tickets** (single, 10-ride, season); >1M tickets sold [P22] | origin/destination stations, frequency, weekday peaks, ticket type | `commutes_by_train` with a route. Home and work regions. Season-ticket or employer-reimbursement tips |
| Mobility | **De Lijn** m-ticket / m-card10 (>1M); **STIB** BRUPASS on MoBIB (>3k) [P22] | urban public-transport use, city | no car / car-light household, student, Brussels commuter |
| Mobility | **4411 pay-as-you-park** (>2M sessions); **Q-Park** number-plate parking [P22][P21] | zone, city, duration, weekday 9–17 pattern, number plate(s) | `has_car` (+ how many cars), workplace location, airport parking = travel |
| Mobility | **Shared bikes** Blue-bike / Velo / Mobit (>8k rides); **Cambio** and shared cars (>11k rides; needs ID + driving licence) [P22][P23] | last-mile station bikes, car-sharing | train + bike commuter; car-free household that might buy a car |
| Mobility | **Q8 fuel at the pump** (location-based, Smiles loyalty) [P23][P21] | fuel type, litres, frequency | car type (petrol/diesel), mileage estimate → maintenance and TCO |
| Mobility | **VAB breakdown / VAB stickers**, **driving-theory practice and driving-licence courses (cat. B)** [P21] | breakdown cover, road trips, learner driver | young driver in the household → add to policy (a Kate use case [S7]), car purchase coming |
| Mobility | **MyMobility** (Nov 2025, ~390k customers BE+CZ): up to 15 vehicles by VIN, TCO calculator, 800+ cars for sale, digital loan and insurance [P22][P24][P4] | customer-*declared* vehicles, mileage, fuel type; browsing cars | high-confidence `has_car`/EV; **car-purchase intent** (a car-loan lead). KBC credits it with ~40% more car-loan market share [P4] |
| Travel | **Brussels Airport** lounge/fast lane; **eSIM for travellers** (180+ countries); Kate Wallet multi-currency [P21][P17] | travel dates, destinations | `travels` → card-abroad check, travel insurance, FX |
| Energy | **Energy insights (Eliq)**: Fluvius digital-meter data by EAN, comparison with similar households, savings targets [P27] | kWh profile, peaks, home size, household size | heat pump / EV charging at home / solar; energy-bill stress |
| Energy | **Mijnenergie.be** comparison and switching; **Samen Overstappen (iChoosr)** group purchase [P28][P26] | current supplier, tariff, contract end | energy-switch intent, price sensitivity |
| Energy | **Solar panels + battery** simulator; renovation quotes (heat pump, insulation) via **Impact Us Today** [P26][P21] | concrete home-energy investment intent | green energy-loan lead, timing |
| Housing | **MyHome** (Mar 2025, 60k customers): up to 15 homes, EPC and energy score, value, budget calculator (max 90% LTV), linked loans and insurance, certificates [P24][P25][P4] | owner vs renter, EPC label, heating system, budget searches | `housing`; home-purchase and renovation intent; mandatory EPC renovation timing **[U]** |
| Housing | **Immoscoop** home search; **Setle** renovation simulation (report usable for a loan); valuation [P26][P25] | search region and price band, renovation budget | "planning to buy / move" intent with a horizon → mortgage and home insurance |
| Telecom | **Proximus Pay&Go / Orange / BASE prepaid top-ups**; eSIM [P21] | prepaid use, top-up amounts | young or price-sensitive profile; telecom spend |
| News | **MyNWS** (adults only; favourite topics, fortnightly top 12) [P24] | topics read | weak interest signal (investing, housing, mobility) |
| Tickets / leisure | **Event tickets via Seetickets**, **Kinepolis** film tickets (in Kate Wallet) [P29][P17] | event dates, genres | leisure profile; ticket-cancellation insurance |
| Payments / vouchers | **Pluxee** service vouchers, **Monizze/Pluxee** meal vouchers, **Joyn** loyalty cards, **split group expenses**, PayPal [P21] | household help, employer benefits, shared costs | employed (meal vouchers); household with cleaning help; flat-share or couple |
| Admin | **Helena** medical data, Digital safe, eBox, IPEX [P21] | **health = GDPR Art. 9**: must *not* feed the twin | exclude |
| Rewards | **Kate Coins** partners and **Kate Deals** activations [P14][P16] | which deals are redeemed or activated (pet food via Just Russel, meal kits, cinema, Q-Park) | weak lifestyle affinities; feedback on which offers fit |
| Other | Carbon-footprint calculator; charity (Kom op tegen Kanker, De Warmste Week) [P21][P14] | sustainability or cause affinity | tone and framing of green products (low weight) |

**Why this matters:** transaction data *suggests* a car or a commute. Ecosystem data *shows* the plate, the route, the VIN or the EAN, often because the customer entered it. In our model these should be treated as **near-stated facts** (confidence ≥ 0.9).

---

## C. Personal-financial-assistant benchmark

### C1. What leading apps do

| App | Standout features (P = proactive, R = on request) | Numbers / notes |
|---|---|---|
| **Monzo** (UK) | **Salary Sorter** splits pay into Pots, and the split is remembered each payday (P). **Bills Pot** pays direct debits from a ring-fenced pot. **Get Paid Early**: salary available at 4pm the day before (P). **Trends** spending insights (R). Gambling block | Salary Sorter + Bills Pots since 2019 [S30] |
| **Revolut AIR** (UK, 9 Apr 2026) | Spending summaries and comparisons, unusual-charge detection, subscription tracking with price-rise alerts and cancelling, card freeze or new virtual card, trip budget + eSIM (mostly R) | 13M UK customers. Zero data retention at third-party model providers. **Biometric approval for sensitive actions** [S31]. Reviewers call it mostly reactive [S] |
| **bunq Finn** (NL) | Q&A over your own transactions ("average grocery spend", "that restaurant in London"), payment ETA, travel tips, 38 languages, speech-to-speech (R) | Runs on Claude via Amazon Bedrock; ~97% of support automated [S32] |
| **ING** (BE/NL) | **Kijk Vooruit**: forecasts expected debits and credits, including predicted energy bills, for the coming month (P/R). Category budgets with overspend alerts (P). "Rond af en spaar" round-up saving | Gen-AI support chatbot handles ~80% of queries (NL, 2023–) [S33] |
| **Belfius "Hey Belfius"** (BE, Apr 2026) | Mistral-based conversational assistant for 2.2M customers. Budget help, documents, lost card or fraud help. Guidance around life moments (trip: currency, card limits, travel insurance; buying a home). Voice planned by end 2026 | 255k conversations in the first weeks. Aim: 80% of remote interactions by 2030. Principle: "show the right feature exactly when needed" [S34] |
| **Klarna** | OpenAI-powered assistant handled 2/3 of chats (2.3M) in its first month, the "work of 700 agents". Shopping search app inside ChatGPT (2026) | **Walked back in 2025**: quality and empathy dropped, human agents rehired [S35]. Lesson: design the human handover in |
| **Cleo** (US/UK) | Chat coach with a tone choice ("roast" / "hype"). Cash advance to avoid overdraft (P). **Autopilot**: roadmap + daily plan + actions (auto-save, spending limits at specific merchants) (P) | Autopilot is waitlist-only [S36] |
| **Rocket Money** (US) | Finds subscriptions and cancels them for you. Bill negotiation (~90% success claimed, paid as 35–60% of the savings). Smart Savings (P/R) | "$2.5–3.1B saved" (vendor claim) [S37] |
| **Emma** (UK) | Budgets that run **payday to payday**. Subscription detection. **Warns if an upcoming bill will overdraw you before payday** (P). Net worth, rent reporting | [S38] |
| **BofA Erica** (US) | Balance-trend alerts for the next 7 days. Recurring-charge changes. Cashback deals based on your spending. Preferred Rewards eligibility (P) | 3.2B interactions, 20M active clients, 1.7B proactive insights. **~60% of interactions are proactive** [P39][S] |
| **Capital One Eno** (US) | Duplicate charges, **free-trial-ending reminder** (the day before), recurring charge up, "did you mean a 150% tip?" (P) | [P40] |
| **CommBank CEE** (AU) | **Customer Engagement Engine**: next-best-conversation across 18 channels (app, NetBank, branch, call centre, chatbot, ATM). **Benefits finder** (400+ government benefits). **Bill Sense** forecasts bills up to 12 months ahead. Same-day disaster support from weather data (P) | 2016 on Pega. 20M conversation suggestions/day in <160 ms. 250 digital next-best-conversations. Control groups cut from 10% to ≤1%. **35M decisions/day (2022) → ~55M (2025)**. 400–450 models, now with 100+ LLMs. 157B data points. Benefits finder: $1B+ in unclaimed benefits connected, 2M+ claims started [S41] |
| **Nubank** (BR) | Pix payments by voice, text or image in the app and in WhatsApp (R). **nuFormer**: a transformer trained on transaction sequences that powers credit, income prediction and cross-sell | WhatsApp Pix tested by 2M customers. nuFormer: 4.4% relative churn reduction in production [S42] |

**Patterns worth copying:**
1. **The payday is the moment.** Monzo, Emma and Cleo all plan around it.
2. **Forecast before you alert.** ING, CBA, Emma and Erica warn *before* the problem happens.
3. **One engine arbitrates** (CBA): relevance scoring, contact-fatigue caps, service before sales, and control groups to measure uplift.
4. **Act only with approval** (Revolut biometrics, KBC's own promise).
5. **Human handover is part of the product** (the Klarna lesson).

### C2. PFA feature ideas for Kate on our twin

| # | Idea | What the customer experiences | Signals (twin facts) | Mode | Inspired by | Effort |
|---|---|---|---|---|---|---|
| 1 | **Approve-to-act payday sorter** | Payday push: "Move €131 to reserves and €200 to savings? [Approve]". The next month the same split is one tap | `employment`/`income` (payday), recurring bills, implications, `saves_monthly` | P | Monzo Salary Sorter; KBC agentic-with-approval; Revolut biometric OK | S |
| 2 | **Safe-to-spend until payday** | A daily "€38/day left until payday" figure, plus a warning 5 days ahead if a bill will overdraw the account | payday, recurring bills, balance, `financial_buffer` | P | Emma, ING Kijk Vooruit, CBA Bill Sense, Erica 7-day | S |
| 3 | **Bill and subscription watch** | "Netflix went up €2", "Two Spotify charges", "Price rise at your insurer" | `subscriptions`, recurring bills | P | Eno, Revolut AIR | S |
| 4 | **Free-trial reminder** | "Your Disney+ trial turns paid tomorrow. Keep it?" | new merchant with a €0/€1 charge, then a recurring charge | P | Eno | M |
| 5 | **Subscription audit** | Kate lists the subscriptions you haven't used and what you'd save, with links to cancel | `subscriptions`, `gym_member` (no gym visits) | R/P | Rocket Money, Revolut | S |
| 6 | **Implied-cost reserves ("sinking funds")** | Pots for car upkeep, road tax, vet, back-to-school in August, annual insurance premiums | `has_car`, `pet`, `children`, yearly bills | P (payday) | Monzo Pots/Bills Pot; our implications | S |
| 7 | **Life-moment checklist** | "New baby? 5 things: Groeipakket, add to health insurance, savings for the child, update your will/beneficiary, childcare costs", each with a status | `life_event_new_baby`/`moved`/`new_job`/`new_car`/`new_pet` | P | Belfius life moments, CBA next-best-conversation, KBC "important moments" | M |
| 8 | **Belgian benefits and premiums finder** | "You may be entitled to: service-voucher tax credit, Mijn VerbouwPremie, social energy tariff, VAPZ tax benefit" | `children`, `housing`, renovation intent, `money_stress`, self-employed | P | CBA Benefits finder | M |
| 9 | **Money-stress care mode** | Sales are paused and replaced by help: breathing-room plan, payment deferral options, a budget coach, a human on call | `money_stress`, `financial_buffer` | P | CBA hardship/weather, Monzo money worries, Klarna lesson; AI Act Art. 5(1)(b) spirit | S |
| 10 | **"Save the raise"** | "Your salary went up €240. Keep €100 of it in savings automatically?" | `life_event_new_job`, `income` change | P | Cleo Autopilot, ING round-up | S |
| 11 | **Goal planner with a timeline** | "House deposit of €30k by 2028: you're 18% there. At €420/month you'll make it in Q3 2028" | stated goal (D), `saves_monthly`, `housing` | R/P | Emma goals, Cleo roadmap, Luts's "savings advice" quote | M |
| 12 | **Commute optimiser** | "You bought 19 single Brussels tickets this month. A season ticket saves €46. Does your employer reimburse it?" | `commutes_by_train` (+ NMBS tickets and 4411 parking from B) | P (monthly) | KBC mobility ecosystem | M |
| 13 | **Car TCO and EV switch coach** | "Your car costs €412/month all-in. An EV like X would cost €365, and green car loans are cheaper" | `has_car`, fuel spend, mileage, MyMobility | R/P | KBC MyMobility TCO | M |
| 14 | **Insurance fit and overlap check** | At renewal: "Your 9-year-old car is still on full omnium: switch to mini-omnium and save about €180" (one highlighted option) | `has_car` + insurer, policies, car age | P | Kate's omnium→basic use case; our one-highlight rule | M |
| 15 | **Energy bill watch** | "Your energy direct debit rose 22%. Compare suppliers (Mijnenergie) or join the group purchase?" | energy bills, `housing`, EV charging | P | Kate energy use case, Eliq, iChoosr | S |
| 16 | **Travel mode** | Booking detected → "Card active abroad: yes, travel insurance: yes, add EUR→USD in Kate Wallet?" | `travels`, FX spend | P | Kate trip check, Belfius trip journey, Revolut AIR travel | S |
| 17 | **Monthly money story** | One-screen recap: where it went, which bills changed, the one thing to do next. Tone chosen by the customer | all facts, spending summary | P (monthly) | Monzo Trends, Erica insights, Cleo tone | S |
| 18 | **"What's this payment?"** | Explains an unclear descriptor (merchant, place, whether it's a subscription) and offers a dispute or duplicate check | transactions, merchant enrichment | R | bunq Finn, Eno | S |
| 19 | **Weekly free-to-spend nudge** | Monday: "€151 free this week". Thursday: "€40 left, on track" | payday plan | P | Monzo / Revolut budgets | S |
| 20 | **"Kate remembered" memory** | After a chat: "Kate remembered: planning to buy a house in 2027 [Edit] [Forget]", visible in the glass box | chat-stated facts (D) | P/R | ChatGPT memory controls | M |
| 21 | **Next-best-conversation arbiter** | Every channel shows the same single top item. At most 2 pushes a week. Service beats sales. A holdout group measures uplift | all facts + priorities | P | CBA CEE | M |
| 22 | **Advisor handover brief** | When Kate escalates, the advisor sees a one-screen twin brief and a "don't re-ask" list, so the customer never has to explain again | twin summary, chat context | R | Kate4Commercial leads, Klarna handover lesson | S |

---

## D. "Collect information from Kate": conversations as twin signals

### D1. The legal frame, briefly (not legal advice; KBC Legal/DPO must validate)

- **Purpose limitation and legal basis.** GDPR Art. 5(1)(b). Using chat content *to answer the question* rests on the contract. Reusing it *to personalise later or to market* is a new purpose that needs its own basis. The EDPB's voice-assistant guidelines take this line: executing a request = contract; model improvement and profiling for personalisation or ads = consent [P45]. The EDPB legitimate-interest guidelines add that profiling for marketing rarely passes the balancing test, and that people must be informed for the processing to be expected [P44]. **Practical choice:** tie "remember what I tell Kate" to KBC's existing *Extra convenience* consent, and use it for commercial offers only when *Personalised* is on.
- **Special categories, including inferred ones.** In C-184/20 and C-252/21 (Meta), the CJEU held that data which *reveals* health, religion, sexual orientation or union membership, even indirectly and even if the inference is wrong, falls under Art. 9 [S47]. "We're expecting a baby" is pregnancy, which is health data. Union dues, church donations and pharmacy spend are other examples. So: never auto-extract these. Either store them only on an explicit "remember this" with explicit consent, or store a neutral, non-medical fact ("household expects to grow: Mar 2027") only after legal sign-off **[U]**.
- **Right to object to marketing** (Art. 21(2)–(3)) is absolute. "Don't call me" or "stop the offers" in chat must flow straight into KBC's commercial settings, not just into a twin note.
- **EU AI Act.**
  - Art. 50(1): tell people they are talking to an AI, unless it's obvious. Applies from **2 Aug 2026** and was *not* delayed by the Digital Omnibus [S43].
  - The Digital Omnibus moved the Annex III high-risk obligations (creditworthiness, life and health insurance pricing) to **2 Dec 2027** [S43]. If the twin ever feeds a credit decision, it becomes high-risk.
  - Art. 50(3) (emotion recognition) covers *biometric* inference only. Text sentiment is outside it, but GDPR fairness still applies [U: our reading of Art. 3(39)].
  - Art. 5(1)(b) prohibits exploiting vulnerabilities from a person's social or economic situation. Our "no selling under money stress" rule fits it directly.
- **CCD2 (Directive 2023/2225, applies 20 Nov 2026).** No social-network or special-category data in creditworthiness assessments. Stricter credit advertising [S49]. The affordability tool must stay guidance, not a credit decision.
- **LLM-specific risks.** The EDPB's 2025 LLM report works through a customer-service chatbot case: minimise, set retention, avoid leakage, and use processors under zero-retention terms (as Revolut does) [P46][S31].

### D2. Memory best practice (from ChatGPT and banking assistants)

- **Two layers** (ChatGPT): explicit *saved memories* the user can view, edit and delete, and implicit *chat-history reference*, which can be switched off. A "Memory updated" notice appears when something is saved. **Temporary chat** neither uses nor creates memories. Sensitive details (health) aren't remembered proactively unless the user asks. Deleting a chat does *not* delete a memory saved from it, so the two must be managed separately [P48].
- **Banking additions:** approval for any action (Revolut), zero retention at the model vendor (Revolut) [S31], and conversation visibility for staff made explicit (KBC [P9]).

### D3. Proposal: chat-derived signals in the twin

**Signal types**

| Type | Example utterance | Twin mapping | Default confidence | Expiry | Allowed use |
|---|---|---|---|---|---|
| **Stated fact** (present state) | "I sold my car", "we have a cat", "I work at UZ Leuven now" | an existing fact key (`has_car=false`, `pet=cat`, `employment`) with `source=kate_chat` | 0.95 | none; re-check if transactions contradict for 60 days | service + offers (if Personalised) |
| **Correction** | "That car is my partner's, not mine" | same as glass-box feedback: `rejected_by_customer` + `customer_note` | 1.0 | sticky, 12 months | suppress the fact everywhere |
| **Intent with horizon** | "Planning to buy a house next year", "want an EV in 6 months" | new `intent_*` fact: `{what, horizon}` | 0.7 | horizon + 90 days, unless reconfirmed | timely guidance; one highlighted product near the horizon |
| **Goal** | "Save €10k for the wedding by June 2027" | `goal` object: `{amount, date, label}` | 1.0 (the customer set it) | on the date, or when reached | feeds the payday plan and goal planner (#1, #11) |
| **Preference / constraint** | "Don't call me", "no offers", "answer in English", "keep it short" | preference store (not a fact); mirrored into commercial settings | 1.0 | until changed | **hard rule** checked before every channel |
| **Stress / sentiment** | "I'm broke until payday", "worried about my loan" | transient `stated_stress` flag; no raw text stored | 0.6 | 30 days | **protective use only**: suppress sales, offer help |
| **Special category** | "I'm pregnant", "I'm in chemo" | *not stored* by default. Kate helps in the moment. Saved only on an explicit "remember this" + explicit consent | n/a | n/a | never for marketing or credit |
| **About third parties** | "My mother moved into a care home" | not stored as a fact about the mother; at most a customer-level need ("supports a parent") after an opt-in | 0.6 | 12 months | service only |

**Confidence and merge rules**

1. **Priority:** customer-confirmed or rejected in the glass box > stated in Kate > ecosystem-declared (MyMobility VIN, MyHome EPC) > transaction-inferred. Within the same source, the most recent wins.
2. **Stated beats inferred at the moment of statement.** It doesn't silently overwrite later evidence. If newer transaction evidence contradicts a statement with confidence ≥ 0.8 (e.g. "sold my car" but fuel purchases for 60 days), mark the fact `status=conflict`. Don't use it for offers, and ask once in the glass box: "Still driving? We saw 6 fuel purchases."
3. **Intents decay:** `confidence × 0.5` after the horizon, then expire. An intent **graduates into a fact** when transactions confirm it (notary fees → `housing=owner`, a dealer payment → `life_event_new_car`).
4. **Rejections are sticky:** the engine may not re-infer a rejected fact for 12 months unless a *new kind* of evidence appears.
5. **Provenance on every fact:** `source` (transactions | ecosystem | kate_chat | customer_feedback), `stated_at`, `expires_at`, `evidence` (transaction ids **or** a message id, never raw chat text).

**Pipeline (fits `twin/assistant.py`)**

- Add a GPT-4.1 tool `remember(kind, key, value, horizon?, quote_span)` limited to a **whitelist of keys**. The server validates, blocks special-category keys, and binds the call to the logged-in customer, like the other tools.
- Kate *proposes*; the chip *commits*. Nothing is saved until the customer sees "Kate remembered: … [Edit] [Forget]" and doesn't undo it. For intents and goals, ask: "Shall I remember this?"
- Store facts in the same fact table with the provenance fields above. `twin/feedback.py` already does the "rejected wins" overlay and plan re-computation; chat corrections reuse it.

**Consent and transparency UX**

- The first message in every session: "I'm Kate, KBC's AI assistant" (Art. 50(1)), plus a link to "What Kate knows about me".
- A **settings toggle** "Let Kate remember what I tell her", under Extra convenience, **off until the customer chooses**. A **Private chat** mode that neither uses nor creates memories.
- The **glass box shows a source badge** on every fact: "From your transactions (7 payments)" / "You told Kate on 12 Sep" / "You confirmed". Each fact has Edit and Forget.
- **Forget** (the button, or "forget that" in chat) deletes the memory *and* anything derived from it (plan reserves, highlights) within 24 h, and logs the deletion. Deleting a chat transcript and deleting a memory are separate, clearly labelled actions (the ChatGPT lesson).
- "Don't contact me" / "no offers" updates KBC's commercial settings immediately and replies with a confirmation.

---

## Sources

**KBC (primary)**
- [P1] KBC, "Kate: five years and five milestones", 24 Nov 2025 — https://newsroom.kbc.com/kate-five-years-and-five-milestones (PDF: https://www.kbc.com/content/dam/kbccom/doc/newsroom/pressreleases/2025/20251124_Vijf%20jaar%20Kate_EN.pdf)
- [P2] KBC, "Kate, your personal digital assistant" (2021 figures) — https://newsroom.kbc.com/kate-your-personal-digital-assistant
- [P3] KBC 4Q/FY2025 company presentation (slides 3, 23, 58–63) — https://wcmassets.kbc.be/content/dam/kbccom/doc/investor-relations/Results/4q2025/4q2025-company-presentation.pdf
- [P4] KBC 2Q2026 quarterly report (p. 3) — https://wcmassets.kbc.be/content/dam/kbccom/doc/investor-relations/Results/2q2026/2q2026-quarterly-report-en.pdf.cdn.res/last-modified/1785941395577/2q2026-quarterly-report-en.pdf
- [P9] kbc.be, "Discover KBC's digital assistant. Kate it." — https://www.kbc.be/retail/en/campaign/bespaar-tijd-met-kate.html · NL: https://www.kbc.be/particulieren/nl/campagne/bespaar-tijd-met-kate.html
- [P10] kbc.be Kate FAQ — https://www.kbc.be/particulieren/nl/product/betalen/zelf-bankieren/met-je-smartphone/mobile/kbc-mobile-faqs/Kate-FAQ.html
- [P11] kbc.be "Communicatie, contact en acties" (Extra gemak) — https://www.kbc.be/particulieren/nl/product/betalen/zelf-bankieren/met-je-smartphone/mobile/kbc-mobile-faqs/communicatie-contact-acties.html · https://www.kbcbrussels.be/retail/en/products/payments/self-banking/on-your-smartphone/mobile/mobile-faq/communicatie-contact-acties.html
- [P12] KBC, "Differently: the Next Level" (2020) — https://newsroom.kbc.com/kbc-shifts-digital-transformation-and-customer-experience-up-a-gear-differently-the-next-level
- [P14] KBC, Kate Coins update (Sep 2025) — https://newsroom.kbc.com/you-can-now-do-more-with-kate-coinsmore-benefit-more-experience
- [P15] KBC, "earn money with Kate and Kate Coins" (Nov 2023) — https://newsroom.kbc.com/kbc-enables-customers-to-earn-money-with-kate-and-kate-coins
- [P16] kbc.be Kate Deals FAQ — https://www.kbc.be/retail/en/products/payments/self-banking/on-your-smartphone/mobile/mobile-faq/deals.html
- [P17] KBC, Kate Wallet (Jun 2026) — https://newsroom.kbc.com/kbc-launches-kate-wallet-this-summer-and-makes-payments-in-foreign-currencies-easy · DVO, 24 Jun 2026: https://www.dvo.be/artikel/kbc-lanceert-eigen-digitale-wallet-en-multicurrency-functie-in-kbc-mobile
- [P21] kbc.be additional-services FAQ — https://www.kbc.be/retail/en/products/payments/self-banking/on-your-smartphone/mobile/mobile-faq/additional-services.html
- [P22] KBC, MyMobility (Nov 2025) — https://newsroom.kbc.com/discover-mymobility-kbcs-digital-mobility-dashboard
- [P23] KBC, mobility solutions (2020) — https://newsroom.kbc.com/new-handy-solutions-in-kbc-mobile-for-those-travelling-by-car-or-public-transport
- [P24] kbc.be MyMobility/MyHome/MyNWS FAQ — https://www.kbc.be/particulieren/nl/product/betalen/zelf-bankieren/met-je-smartphone/mobile/kbc-mobile-faqs/themas.html
- [P25] KBC, renovation pace / MyHome (Jan 2026) — https://newsroom.kbc.com/kbc-economics-belgiums-renovation-pace-remains-far-too-low
- [P26] kbc.be ecosystem partners — https://www.kbc.be/particulieren/nl/product/betalen/zelf-bankieren/ecosystemen-partners.html
- [P27] kbc.be Energy insights (Eliq) — https://www.kbc.be/retail/en/products/payments/self-banking/on-your-smartphone/mobile/energy-insights.html
- [P28] KBC, Mijnenergie.be — https://newsroom.kbc.com/met-mijnenergiebe-helpt-kbc-u-aan-een-voordelig-energietarief
- [P29] kbc.be extra services / event tickets (Seetickets) — https://www.kbc.be/particulieren/nl/product/betalen/zelf-bankieren/met-je-smartphone/mobile/kbc-mobile-faqs/extra-diensten.html

**Secondary sources on Kate**
- [S5] Investing.com, KBC Q2 2026 slides and call — https://www.investing.com/news/company-news/kbc-group-q2-2026-slides-strong-results-drive-guidance-upgrade-93CH-4840503 · https://www.investing.com/news/transcripts/earnings-call-transcript-kbc-group-lifts-2026-outlook-after-strong-q2-93CH-4840397
- [S6] Paperjam, "Meet Kate…" — https://en.paperjam.lu/article/meet-kate-an-ai-that-does-the-work-of-300-people-at-kbc
- [S7] The Banking Scene, "Meet Digital Assistant Kate" — https://thebankingscene.com/opinions/meet-digital-assistant-kate-when-digital-transformation-gets-personal/
- [S8] The Banking Scene, "KBC – Generative AI for customer-centric banking" — https://thebankingscene.com/opinions/kbc-generative-ai-for-customer-centric-banking/
- [S13] K. Peters, "Kate and digital assistants in banking" — https://www.linkedin.com/pulse/kate-digital-assistants-banking-kasper-peters
- [S18] kbc.be business, "Maak kennis met Kate" — https://www.kbc.be/ondernemen/nl/nieuws/provibes/algemeen/kate.html
- [S19] App Store reviews, KBC Mobile — https://apps.apple.com/be/app/kbc-mobile/id458066754?see-all=reviews&platform=ipad
- [S20] Test-Aankoop complaint (Oct 2025) — https://www.test-aankoop.be/klagen/publieke-klachten/ongevraagd-verwijderen-van-kat/ea8882b2ffc4662163

**Benchmark apps**
- [S30] Monzo — https://monzo.com/blog/2019/09/26/introducing-salary-sorter-and-bills-pots · https://monzo.com/features/monzo-payday · https://monzo.com/help/monzo-perks/trends-spending-and-balance-web
- [S31] Revolut AIR — https://www.revolut.com/news/revolut_enters_new_era_of_money_intelligence_with_launch_of_ai_assistant/ · https://www.fintechweekly.com/news/revolut-air-ai-assistant-uk-customers-launch-2026 · https://ai2.work/blog/revolut-s-air-assistant-can-freeze-cards-and-decode-your-spending
- [S32] bunq Finn — https://aws.amazon.com/blogs/machine-learning/how-bunq-handles-97-of-support-with-amazon-bedrock/ · https://www.cxtoday.com/ai-automation-in-cx/bunq-finn-financial-ai-assistant/
- [S33] ING — https://www.ing.nl/particulier/digitaal-bankieren/jouw-app/kijk-vooruit/kijk-vooruit · https://www.ing.be/nl/particulieren/voor-elke-dag/budget-voorspellen-beheren · https://www.banken.nl/nieuws/25618/ing-voegt-budget-optie-toe-aan-mobiele-app · https://finainews.com/banking/ings-gen-ai-chatbot-tackles-nearly-80-of-customer-queries/
- [S34] Belfius — https://miro.com/blog/belfius-canvas-26/ · https://www.larevuedudigital.com/la-banque-belge-belfius-developpe-son-assistant-virtuel-en-ia-generative-avec-mistral-ai/ · https://www.lalibre.be/economie/entreprises-startup/2026/04/01/internationalisation-assistant-digital-neobanque-rebel-belfius-devoile-son-plan-2030-3FI6ZNQOYZGGXOBWODVNJYQD3A/
- [S35] Klarna — https://openai.com/index/klarna/ · https://www.forbes.com/sites/quickerbettertech/2025/05/18/business-tech-news-klarna-reverses-on-ai-says-customers-like-talking-to-people/ · https://investors.klarna.com/News--Events/news/news-details/2026/Klarna-launches-AI-powered-Shopping-Search-app-in-ChatGPT/default.aspx
- [S36] Cleo — https://lendedu.com/blog/cleo-app-review/
- [S37] Rocket Money — https://www.rocketmoney.com/learn/personal-finance/does-rocket-money-work
- [S38] Emma — https://moneytothemasses.com/banking/emma-review-is-it-the-best-budgeting-app
- [P39] BofA Erica — https://newsroom.bankofamerica.com/content/newsroom/press-releases/2025/08/a-decade-of-ai-innovation--bofa-s-virtual-assistant-erica-surpas.html · https://newsroom.bankofamerica.com/content/newsroom/press-releases/2025/02/digital-interactions-by-bofa-clients-surge-to-over-26-billion--u.html (the 60%-proactive figure comes from secondary coverage, e.g. https://thefinancialbrand.com/news/banking-technology/bofa-spends-billions-on-erica-and-other-leading-edge-tech-194239)
- [P40] Capital One Eno — https://www.capitalone.com/learn-grow/money-management/eno-manages-finances/
- [S41] CommBank — https://www.itnews.com.au/news/cba-system-suggests-20m-customer-conversations-a-day-493688 · https://www.commbank.com.au/articles/newsroom/2022/06/CBA-artificial-intelligence-usages.html · https://www.cio.inc/commonwealth-bank-australia-builds-ai-native-banking-a-30513 · https://www.commbank.com.au/digital-banking/bill-sense.html · https://www.commbank.com.au/articles/newsroom/2023/05/artificial-intelligence-banking.html
- [S42] Nubank — https://tiinside.com.br/en/11/12/2024/nubank-amplia-servico-de-pix-com-ia-generativa-para-app-e-whastapp/ · https://building.nu.com/how-nubank-uses-transformers-to-model-financial-habits-at-scale/ · https://arxiv.org/html/2507.23267v1

**Law, regulation and memory**
- [S43] Jones Walker, AI Act Art. 50 and Digital Omnibus — https://www.joneswalker.com/en/insights/blogs/ai-law-blog/yes-august-2-still-matters-the-eu-approved-a-high-risk-ai-delay-but-most-trans.html?id=102nbon · AI Act text: https://eur-lex.europa.eu/eli/reg/2024/1689/oj
- [P44] EDPB Guidelines 1/2024 on legitimate interest — https://www.edpb.europa.eu/system/files/2024-10/edpb_guidelines_202401_legitimateinterest_en.pdf
- [P45] EDPB Guidelines 02/2021 on virtual voice assistants — https://www.edpb.europa.eu/system/files/2021-03/edpb_guidelines_022021_virtual_voice_assistants_adopted-public-consultation_en.pdf
- [P46] EDPB, "AI Privacy Risks & Mitigations – LLMs" (Apr 2025) — https://www.edpb.europa.eu/system/files/2025-04/ai-privacy-risks-and-mitigations-in-llms.pdf
- [S47] CJEU C-252/21 and C-184/20 on inferred special-category data — https://privacymatters.dlapiper.com/2023/07/eu-cjeus-landmark-decision-in-meta-vs-bundeskartellamt/ · https://www.osborneclarke.com/insights/2024-privacy-review-most-important-ecj-privacy-rulings · GDPR text: https://eur-lex.europa.eu/eli/reg/2016/679/oj
- [P48] OpenAI, "Memory and new controls for ChatGPT" and Memory FAQ — https://openai.com/index/memory-and-new-controls-for-chatgpt/ · https://help.openai.com/en/articles/8590148-memory-in-chatgpt
- [S49] CCD2 (Directive 2023/2225) — https://www.schoenherr.eu/content/consumer-credit-directive-ii-consumer-credit-legislation-for-the-digital-age · https://www.beshapingthefuture.de/insights/consumer-credit-directive-changes-in-2026-and-action-required-by-20-november-2026/?lang=en

*Not read in full: the KBC Annual Report 2025 PDF (over 10 MB; the fetch failed). Its Kate figures (73M interactions, "14% sales conversion", "400k sales LTM") come only from search excerpts **[U]**. The FY2025 and 2Q2026 figures above come from the investor documents we could read.*
