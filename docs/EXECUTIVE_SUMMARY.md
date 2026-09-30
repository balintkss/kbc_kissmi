# KBC Digital Twin: executive summary

*30 Sep 2026 · synthetic-data prototype · KBC figures from public sources, untested in the live app · (U) = unverified · detail: [service map](KBC_SERVICE_MAP.md) · [value matrix](KBC_VALUE_MATRIX.md) · [business case](PRIVATE_BANKER_AT_SCALE.md).*

> **Promise:** "KBC helps me without making me repeat myself — and I stay in control."

## 1. Bottom line

KBC already has the products, the reach and the conversation (Kate serves 5.8M digital customers and raises 140+ proactive situations [1]), but we found no public sign of one memory that every channel shares and that the customer can see and correct (U) [2]. The KBC Digital Twin is that **customer-governed financial memory for Kate**: it productises the parts of a great private-banking relationship that can be safely scaled (a shared understanding of the customer's financial reality, regular meaningful dialogue, a clear goal and a relevant next step) through Kate, KBC Mobile and kbc.be, with a human adviser for consequential choices [3]. Our prototype already covers 19 of 55 KBC service families, 30 more are small or medium extensions, and we ask KBC for a consented pilot to prove that customer benefit, trust and qualified growth rise together.

## 2. Where KBC stands today

Maturity: ① catalogue or human-led · ② digital self-service · ③ rule-based proactive · ④ context-aware. Leverage is the service map's heatmap score out of 25: High ≥ 20, Med 17–19, Low ≤ 14.

| Segment | KBC today | Gap the twin fills | Leverage |
|---|---|---|---|
| Daily banking & PFA | ②③ Best mobile banking app, Sia 2021/24/25 [4]. Guardian Angel for >4M customers [5]. Budgets are descriptive [6] | No forward payday plan or bill forecast. No public hardship mode (U) | High (PFA 21, payments 17) |
| Lending | ②④ MyMobility: ~390k users, ~40% more car-loan share [7][8]. 20% of mortgage applications start digitally [9] | Mortgage hand-off re-asks facts KBC already has | Med (18) |
| Insurance | ② Digital quotes and claims. Digital sales: 30% of insurance vs 57% of banking products (2025) [10] | No customer check for gaps or overlaps found | High (20) |
| Saving & investing | ④ 270k+ digital MiFID profiles. Proactive proposals in the app [11] | Twin may only trigger a review, never recommend | Low (14) |
| Youth | ② Free account for ages 10–24 [12] | No documented journey for the switch at 25 (U) | Med (19) |
| Private banking | ① Dedicated banker, periodic Private Plan [3][13] | Life events missing from the banker's brief. This is the model we scale | Low (13) |
| Self-employed | ②③ Business PRO, Billit/Peppol, Kate invoice reminders [14] | No automatic VAT or social-contribution set-asides (U) | Med (19) |
| SME & agri | ①③ Business Dashboard insights for 150k companies [15] | Needs a company twin | Low (14) |
| Beyond banking | ④ MyHome: 60k users [8]. Kate Coins: 257k users [16], criticised as too commercial [17] | Ecosystem data not used as evidence | Med (17) |
| Channels | ③→④ Kate on GPT-4.1. Staff picked up 656k Kate leads in Q3 2025 [1] | No public "what Kate knows" view (U) [2] | High (22) |

## 3. What the twin adds

- **One context layer, governed by the customer.** Kate, KBC Mobile, kbc.be and advisers all read the same twin, so a fact learned once drives the pages, the plan, the pushes and Kate. It follows the Financial Understanding Contract: non-sensitive pattern → hypothesis (confidence, expiry) → the customer confirms, edits or rejects it → memory → goal and affordability check → one next step, with explicit approval for any action.
- **One explained next step, not a catalogue.** The customer sees one option, the reason and the facts behind it. The alternatives stay one tap away.
- **Help first under money stress.** Sales are held back, and every channel switches to support.
- **The customer confirms, edits or forgets.** A glass box shows each fact's evidence, confidence and date. "That's not me" re-plans at once.
- **Built for 2.3M customers.** The twin runs on rules, with zero LLM calls. The LLM only writes Kate's replies.

## 4. Top 5 use cases

| Use case | Customer value | KBC value | PoC status | Guardrail |
|---|---|---|---|---|
| **Kate grounded in the twin + "Kate remembered"** | No repeating. "Can I afford €1,200 in August?" is answered from the plan | Sharper answers on a channel behind 400k+ sales a year [1] | Built: 4 tools, nl/fr/en. Next: memory chip | AI disclosure [18]; memory is opt-in |
| **Payday plan with implied reserves** | "After bills, reserves and savings: €151 a week free" | Daily relevance; deeper primary relationship | Built, incl. a quiet-month plan | Money moves only with approval |
| **Money-stress care mode** | Help before offers | Fewer harmful sales and complaints | Built on every channel | Protective use only [18] |
| **Household insurance check-up** | One screen: covered, missing, insured elsewhere | Least digital segment [10]. In our synthetic data, 2,118 of 3,350 car owners insure elsewhere | Rules built. Next: customer screen | IDD [21]; confirmed changes only |
| **Adviser and KBC Live brief** | The adviser doesn't re-ask | Less preparation; context on every Kate lead | Built and audited. Next: Kate leads | Need-to-know access; a human decides |

## 5. Kate as personal financial assistant and signal source

- **Assistant:** payday plan with approve-to-act transfers, safe-to-spend with overdraft warning, care mode, "Can I afford it?" (built), life-moment checklists, bill watch, and tax envelopes for the self-employed.
- **Signal source:** Kate proposes a memory and the customer commits it: **"Kate remembered: buying a house in 2027 [Edit] [Forget]"**. Memory is opt-in, and commercial use also needs *Personalised* [19]. When Lotte says "I sold my car", her free money goes from €151 to €213 a week.
- **Source priority:** confirmed > stated to Kate > ecosystem (e.g. a MyMobility VIN) > inferred. Only confirmed or stated facts drive commercial journeys. "No offers" is a hard rule [20].
- **Firewall:** no health, pregnancy/birth or other special-category data is inferred or stored, from payments or chat, and a server-side block enforces this. At most, Kate stores a neutral household change the customer confirms. Each session opens with "I'm Kate, KBC's AI assistant", as the AI Act has required since 2 Aug 2026 [18].

## 6. Proof points from the prototype

*Synthetic data: 5,000 customers, 2.16M transactions.*

- **Accuracy against hidden ground truth:** 94.8–100% per fact, recall 84.5–100%. *Caveat:* we generated the data ourselves, so this proves the pipeline and is an upper bound; real data will be noisier.
- **Speed:** 15.9 ms per twin, so 5,000 twins take ≈ 80–85 s on one laptop core. Linear projection for 2.3M customers: ≈ 10.9 h on 1 core, 80 min on 8, 20 min on 32.
- **Kate cost:** ≈ $0.008 per GPT-4.1 turn [22]. If 10% of 2.3M customers chat 3 turns a month, that is ≈ $5.7k a month.
- **Help before sales:** 597 synthetic customers under money stress get support, not offers, and 102 sales messages are held back (95 customers).
- **Engineering:** 5 bank and insurance topics with 15 variants, and 424 tests passing. Signed tokens, Kate tools bound to the session, audited adviser views.

## 7. What we deliberately don't claim

- **KBC's own tools.** Kate's proactivity (140+ situations) and MyMobility's TCO check belong to KBC [1][7]. We add one shared memory.
- **Investment advice.** Under MiFID, a personal nudge can count as a recommendation [23]. The twin only triggers a review or an adviser handover.
- **Full visibility.** Cash was still 39% of Belgian point-of-sale payments in 2024 [24], and other banks and joint accounts are outside the picture.
- **Health inference.** Never in production. The newborn rule is a synthetic pipeline test, and the confirmation gate is still to be built.
- **A fraud engine or an ROI figure.** Fraud prevention stays a separate, purpose-limited workstream. It shares the audit pattern, never the commercial profile, and security signals never feed marketing [25][26]. Revenue is measured against a control group.

## 8. Roadmap and ask

**Now (prototype)**
- 20+ fact types with evidence; payday and quiet-month plans.
- One highlight per topic for app, web and Kate; care mode; glass box.
- Kate with 4 grounded tools; an audited adviser view.

**3 months**
- Confirmation gate. The newborn and hospital rules stay out of production.
- Kate memory chip and Forget; insurance check-up; self-employed envelopes.
- Shadow run on a pseudonymised sample, then an opt-in pilot with no commercial push.

**12 months**
- Facts from MyMobility and MyHome; households, under a consent model.
- A cross-channel arbiter with a holdout group; a company twin for SMEs.
- Governed product journeys after the pilot gates, with CCD2 and AI Act high-risk readiness [27][18].

**What we need from KBC**
1. Consented, pseudonymised data for one opt-in pilot segment, and a DPO and compliance review: legal basis, AI disclosure, MiFID/IDD, LLM zero-retention terms.
2. One Kate integration point and a KBC Live team for handovers, with agreed gates: plan adoption first, then qualified completions against a control group.

## Sources

Local numbering. "SM" = the entry in [KBC_SERVICE_MAP.md](KBC_SERVICE_MAP.md) §9. [P] primary, [S] secondary. PoC figures come from this repo on synthetic data: the README results table, `docs/PITCH.md` §5, `python -m twin.evaluate`, `python -m twin.benchmark` and the `twin_facts` counts.

1. [P] KBC, "Kate: five years and five milestones", 24 Nov 2025: https://newsroom.kbc.com/kate-five-years-and-five-milestones (SM 1)
2. [P] KBC, Kate page and FAQ: https://www.kbc.be/retail/en/campaign/bespaar-tijd-met-kate.html (SM 21)
3. [P] KBC Private Banking, "Your private banker": https://www.kbc.be/private-banking/en/about-us/uw-private-banker.html
4. [P] KBC, Sia Awards 2025: https://www.kbc.com/content/dam/kbccom/doc/newsroom/pressreleases/2025/Sia%20Awards%202025_EN.pdf (SM 13)
5. [P] KBC, Guardian Angel, 15 Sep 2026: https://newsroom.kbc.com/kbc-brings-guardian-angel-to-more-than-4-million-customers-in-belgium (SM 10)
6. [P] KBC Mobile, PFM and savings goals: https://www.kbc.be/particulieren/nl/product/betalen/zelf-bankieren/met-je-smartphone/mobile/sparen-voor-je-dromen.html (SM 28)
7. [P] KBC, MyMobility, 25 Nov 2025: https://newsroom.kbc.com/discover-mymobility-kbcs-digital-mobility-dashboard (SM 7)
8. [P] KBC Group 2Q2026 results: https://newsroom.kbc.com/kbc-group-second-quarter-result-of-1-152-million-euros (SM 5)
9. [P] KBC Economics, MyHome, 29 Jan 2026: https://www.kbc.com/content/dam/kbccom/doc/newsroom/pressreleases/2026/20260129%20MyHome_EN.pdf (SM 8)
10. [P] KBC Group Annual Report 2025 (read in excerpts, U): https://www.kbc.com/content/dam/kbccom/doc/investor-relations/Results/jvs-2025/jvs-2025-grp-en.pdf (SM 3)
11. [P] KBC, investor profile: https://www.kbc.be/particulieren/nl/beleggen/beleggersprofiel.html (SM 46)
12. [P] KBC, Young Person's Account: https://www.kbc.be/retail/en/products/payments/current-accounts/young-person-s-account.html (SM 41)
13. [P] KBC Private Plan: https://www.kbc.be/private-banking/nl/private-plan.html (SM 54)
14. [P] KBC, Business PRO and freelancers: https://www.kbc.be/ondernemen/nl/product/betalen-en-betaald-worden/zakelijke-rekeningen/business-pro.html · https://www.kbc.be/ondernemen/nl/specifieke-sectoren/freelancers-consultants.html (SM 57, 60)
15. [P] KBC Business Dashboard: https://www.kbc.be/commercial-banking/nl/betalingsverkeer/kbc-business-dashboard.html (SM 58)
16. [P] KBC, Kate Coins, 9 Sep 2025: https://newsroom.kbc.com/you-can-now-do-more-with-kate-coinsmore-benefit-more-experience (SM 11)
17. [S] KBC Mobile App Store reviews: https://apps.apple.com/be/app/kbc-mobile/id458066754?see-all=reviews&platform=ipad (SM 69)
18. [P] EU AI Act, Reg. 2024/1689 (Art. 5(1)(b), 50): https://eur-lex.europa.eu/eli/reg/2024/1689/oj (SM 86)
19. [P] KBC, Extra convenience and commercial settings: https://www.kbc.be/particulieren/nl/product/betalen/zelf-bankieren/met-je-smartphone/mobile/kbc-mobile-faqs/communicatie-contact-acties.html (SM 22)
20. [P] GDPR, Reg. 2016/679 (Art. 9, 21): https://eur-lex.europa.eu/eli/reg/2016/679/oj (SM 83)
21. [P] IDD, Dir. 2016/97: https://eur-lex.europa.eu/eli/dir/2016/97/oj (SM 82)
22. [P] OpenAI API pricing, seen 30 Sep 2026: https://developers.openai.com/api/docs/pricing
23. [P] MiFID II, Dir. 2014/65: https://eur-lex.europa.eu/eli/dir/2014/65/oj (SM 81)
24. [P] ECB, SPACE 2024: https://www.ecb.europa.eu/stats/ecb_surveys/space/html/ecb.space2024~19d46f0f17.en.html
25. [P] EBA Q&A 2020_5621 (transaction monitoring): https://www.eba.europa.eu/single-rule-book-qa/qna/view/publicId/2020_5621
26. [P] EDPB guidelines on legitimate interest: https://www.edpb.europa.eu/system/files/2024-10/edpb_guidelines_202401_legitimateinterest_en.pdf (SM 89)
27. [P] CCD2, Dir. 2023/2225: https://eur-lex.europa.eu/eli/dir/2023/2225/oj/eng (SM 84)
