# Private-Banker Quality at Retail Scale: Business Case

## The commercial thesis

**Kate+ productises the parts of a great private-banking relationship that can be safely scaled: a shared understanding of the customer’s financial reality, regular meaningful dialogue, a clear goal and a relevant next step. The Digital Twin remains its explainable memory layer.**

This is not a claim that every retail customer receives a human private banker. It is a promise that every customer can receive the *preparation, continuity and clarity* of that relationship through Kate, KBC Mobile and kbc.be — with a human adviser available for consequential choices.

KBC’s own Private Banking proposition makes the comparison concrete: each customer has a dedicated contact who understands their wealth, goals and family expectations, coordinates specialists, and maintains an ongoing dialogue. [KBC Private Banking](https://www.kbc.be/private-banking/en.html) · [Your private banker](https://www.kbc.be/private-banking/en/about-us/uw-private-banker.html)

## What we scale — and what we do not

| High-touch private-banking relationship | Retail-scale Digital Twin | Deliberate boundary |
|---|---|---|
| Dedicated contact learns goals and context over time | Customer-controlled financial memory records only confirmed, non-sensitive context and goals | The Twin does not pretend to be a human adviser or private banker |
| Regular conversations adapt the plan when life changes | A quiet monthly check-in or customer-initiated conversation asks one useful question | No interrogation after every payment; customer can say “not now” or exclude a category |
| Banker prepares relevant options and brings specialists | Kate prepares one explainable next step; an adviser receives a short, audited handover brief | Credit, insurance, investment and legal decisions remain in existing regulated flows |
| Trust comes from continuity and discretion | Evidence, confidence, purpose, correction and deletion are visible to the customer | No hidden sensitive profiling, no irreversible profile, no automatic purchase or price |

The presentation phrase:

> **Private-banker quality should not be reserved for the few. We scale the relationship, not the headcount: one governed financial memory gives every customer continuity across Kate, app, web and an adviser.**

## Why it is a business case, not just a nicer interface

The value is a causal chain to test, not an assumed revenue number:

```text
Consented financial context + stated goal
  -> fewer repeated questions and more useful help
  -> trust, plan completion and a stronger primary relationship
  -> qualified, affordable journeys at genuine life moments
  -> retained relationship, lower avoidable service effort and safer cross-product conversion
```

### Five value levers

| Lever | Product mechanism | Customer outcome | Business measure — validate in experiment |
|---|---|---|---|
| **Relationship depth** | One portable, customer-visible context across channels | “I do not need to start again” | Active use, repeat engagement, customer effort score, retention / primary-relationship proxy |
| **Financial wellbeing** | Payday plan, future-cost reserve and support-before-sales rule | Fewer avoidable surprises; goal stays protected | Plan completion, buffer progress, support uptake, complaints — never use hardship as a sales trigger |
| **Qualified growth** | A customer goal and affordability check precede a product journey | One relevant option, not a catalogue | Opt-in rate, qualified quote/application start, completion and later suitability/complaint outcomes |
| **Service efficiency** | Kate and adviser read the same prepared context and evidence | Fewer repeated questions; faster human handover when needed | Containment where appropriate, handle time, number of repeated questions, adviser preparation time |
| **Trust and control** | Explain, confirm, edit, reject, forget; commercial use needs its own choice | Customer understands and controls personalisation | Fact confirmation/correction/delete rates, opt-out rate, trust/NPS and privacy complaints |

**Do not invent ROI on stage.** Say: *“These are the measurable hypotheses for a controlled pilot. We will release only if customer benefit, fairness and business outcomes improve together.”*

## Pilot design: prove value before scaling

| Phase | Scope | Success gate |
|---|---|---|
| **0. Shadow and quality** | Use synthetic data, then a privacy-approved internal evaluation set; no customer action | Evidence quality, error rate, coverage and data-protection impact assessment approved |
| **1. Customer-controlled utility** | Voluntary early-adopter group: payday plan, savings goal and car-cost reserve; no commercial push | High confirmation / low harmful-error rate; better plan engagement; no material complaint or trust deterioration |
| **2. Governed journeys** | Opted-in, customer-confirmed life changes; one relevant product or adviser journey | Incremental qualified completion and customer value versus a control group; suitability and fairness checks pass |
| **3. Cross-channel scale** | Kate, Mobile, web and adviser handover use the same contract | Higher resolution with no rise in repeat contacts, complaints, opt-outs or adverse-outcome indicators |

Randomise at customer level only where lawful and fair, preregister success criteria, and measure a holdout group. No commercial journey should be activated just because a model produces a high confidence score.

## The right role for fraud prevention

There is a real security opportunity, but it must be a **separate, purpose-limited workstream**, not an excuse to merge a commercial life profile into fraud scoring.

Payment providers already need transaction-monitoring mechanisms to detect unauthorised or fraudulent payments; PSD2 allows transaction-risk analysis in defined circumstances. The EBA describes additional security measures that can use signals such as device, IP address and location, and notes that fraud prevention must be strict, necessary and risk-based. [EBA Q&A 2020_5621](https://www.eba.europa.eu/single-rule-book-qa/qna/view/publicId/2020_5621) · [EBA payment-fraud opinion](https://eba.europa.eu/sites/default/files/2024-04/363649ff-27b4-4210-95a6-0a87c9e21272/Opinion%20on%20new%20types%20of%20payment%20fraud%20and%20possible%20mitigations.pdf)

The EDPB is equally clear that fraud-prevention processing must be strictly necessary, data-minimised and subject to storage limits. [EDPB legitimate-interest guidance](https://www.edpb.europa.eu/system/files/2024-10/edpb_guidelines_202401_legitimateinterest_en.pdf)

### Safe architecture

| Personalisation Twin | Security / fraud baseline |
|---|---|
| Purpose: customer-requested financial help and opted-in commercial relevance | Purpose: prevent unauthorised or fraudulent payments |
| Inputs: confirmed, non-sensitive financial context and stated goals | Inputs: payment, device, payee, session and authorised security signals required for risk analysis |
| Output: explainable help, plan or optional journey | Output: allow, step-up authentication, pause for review or customer verification |
| Customer control: confirm, correct, delete and change personalisation choices | Governance: model-risk validation, fraud-ops oversight, false-positive monitoring, retention limits and appeal/support route |
| Never sets a price, credit eligibility, underwriting or fraud outcome | Never sends fraud risk or security-derived traits to marketing or product recommendation |

The reusable asset is the **governance pattern** — evidence, confidence, monitoring, correction and audit trails — not indiscriminate reuse of profile data. If a payment is anomalous, the best customer experience is a proportionate step-up question such as *“Was this €X payment to Y you?”*, not a silent, opaque decision based on inferred lifestyle.

## Three judge-proof answers

**“Is this a private banker for everyone?”**
“It is the scalable preparation layer of a private-banking relationship: shared context, a regular conversation, goals and relevant specialists. It does not replace advisers; it makes every interaction more prepared and hands consequential cases to them.”

**“Where is the revenue?”**
“We do not count every push as revenue. We first prove plan adoption and trust. Then, for opted-in customers with a confirmed need and affordability, we measure incremental qualified journeys and completion against a control group — while monitoring suitability, complaints and opt-outs.”

**“Can it help prevent fraud?”**
“Yes, through a separate security baseline that detects anomalous payment behaviour and triggers proportionate verification. It shares the explainability and audit pattern, not a hidden commercial life profile. Security data never becomes a marketing signal.”

## Slide-ready close

> **The Digital Twin gives KBC a new retail operating model: give every customer the continuity of a prepared relationship, use humans where judgement matters, and prove that every automated step is useful, permitted and reversible.**
