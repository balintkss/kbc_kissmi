# Daily update of the digital twins: does part 2 scale?

> Part 1 builds each twin from a year of history (`twin/engine.py`, [backfill.md](backfill.md)). Part 2 updates every twin each day from that day's new transactions. If part 2 scales, the project is viable. This page measures it.
>
> Code: `twin/incremental.py`. Tests: `tests/test_incremental.py`. Replay: `python -m twin.incremental --db <copy> --start 2026-09-23 --days 7 --verify daily` (opens the DB read-only). Synthetic data, 5,000 customers, 2026-09-30.

## Verdict

**Viable, with a wide margin.** Replaying 7 days, the incremental update gives **exactly the same twins as a full rebuild**. Projected to KBC's 2.3M customers, it needs **about 7 CPU-hours a night, or 4 laptop-class cores for a 2-hour window**. That drops to about 5.4 CPU-hours (3 cores) once the fuel-average rule is fixed (§6).

The streaming tier costs **about 50 µs per transaction**. One core handles about 20,000 events/s. KBC's peak is on the order of 100–1,100 transactions/s.

The worst night is the 1st of the month. Today it is a full-rebuild night: about 12 CPU-hours, or 6 cores for 2 hours. One small engine change removes that spike (§6).

Even the naive plan, rebuilding everyone every night, is only 10.9 CPU-hours. The tiers mainly cut I/O, not CPU: only customers who were touched (or whose windows expired) are re-read. They also give real-time reactions through Tier 0.

## 1. Method: the replay experiment

1. **As-of view.** `Ledger` reads the bank tables once and answers "as of day D":
   - transactions booked on or before D;
   - end-of-day balances, taken from the last `balance_after` on each account up to D;
   - products with `started_at <= D`.
2. **Part 1 at D₀ = 2026-09-23.** Every twin is built with `Twin(..., as_of=D₀).build()`, using only data up to D₀.
3. **Seven nights, 24–30 Sep.** Each night runs `nightly()`: Tier 1 and Tier 2 on that day's batch. Tier 0 streams the same day's transactions first.
4. **Ground truth.** A full `Twin.build()` as of each day, compared with the incremental twins every night (`--verify daily`).

**Equality definition (strict).** The twin's JSON must be identical, key order included:

- every fact with all of its fields (value, confidence, since, evidence, summary, implications, extras);
- `recurring`;
- `plan`;
- the profile fields (name, age, `kbc_products`, …).

There is **one intended difference: `as_of`**. It is the last day the twin was recomputed. A twin that had nothing to change keeps its older stamp.

A looser "core" check (same fact keys, values and confidence) is also computed. It is implied by the strict check.

**Result:**

- 300 customers × 7 nights, verified every night: **300/300 identical on every night** (strict).
- The tests replay 4 nights on a freshly generated 30-customer database: all identical.
- As a sanity check, the as-of view at 2026-09-30 reproduces `twin.engine.build_twins` byte for byte.

**Engine change.** `twin/engine.py` gets one optional parameter, `Twin(..., as_of=None)`. Every `AS_OF` inside the methods now reads `self.as_of`, and `_is_recent` takes an optional `as_of`.

The default is unchanged. I built all 5,000 twins before and after the change: **identical SHA-256** (`ccd0b0a9…`). The full test suite still passes.

## 2. The tiers

| Tier | When | Who | What runs | Cost per customer |
|---|---|---|---|---|
| **0 · streaming** | Every booking, within seconds | The customer who paid or got paid | `on_transaction(state, tx)`, a pure function (details below). **Never rebuilds the twin.** | **≈ 50 µs** (p50 41–56 µs, p95 49–148 µs) |
| **1a · balance-only day** | Nightly | Touched customers whose day contains only subcategories no rule reads: groceries, dining, shopping, cash, doctor, pharmacy, kids, bonus, refunds, savings-account moves | `refresh_money()`: the engine's own `infer_money()` + `plan()` on the last 90 days. Refreshes `financial_buffer`, `money_stress`, the plan (groceries, free to spend) and the forecast inputs. Keeps everything else. | ≈ 1.5 ms (measured 4.6–6.7 ms under load) |
| **1b · signal-bearing day** | Nightly | Touched customers with a salary, rent/mortgage, fuel/EV, insurance, child benefit, moving/notary, pet, invoice, subscription or other signal subcategory; any debit that could be a recurring bill; or a product opened that day | `rebuild()`: `Twin.build()` on that customer's rolling ~13 months as of today, plus the next calendar expiry | ≈ 19 ms (16 ms build + 3 ms expiry; measured 55–62 ms under load) |
| **2 · calendar** | Nightly | Customers whose twin changes although nothing was booked | (a) a transaction left the 90-day money window → `refresh_money()`; (b) `refresh_on ≤ today` (a known expiry date, listed below) → `rebuild()` | Same as 1a / 1b |

**What Tier 0 does with each booking:**

- updates the balance and re-projects it to payday using `twin.forecast.project`;
- sends an overdraft warning the first time the projection dips below zero;
- sends the payday-plan push when a salary, pension or benefit lands;
- sends a "spread it?" service message for a large unusual debit: at least €500 and at least 2× the customer's 99th-percentile debit, and not a known bill.

**How a day is classified.** The rule is derived from the engine, not tuned by hand. `RULE_SUBS` holds every subcategory an `infer_*` rule reads. On top of that, any current-account debit that `recurring()` could count as a bill is a signal. Everything else only moves balances and the 90-day window, so the cheap path is exact by construction.

**The expiry dates behind Tier 2(b)** (`calendar_expiries()`), each derived from a rule in `engine.py`:

- **Month start.** Monthly `next_date` values and the payday move a month. This also covers age on 1 Jan.
- **A bill stops.** A bill unpaid for 70 days drops out of `recurring`.
- **Housing.** A new home is listed after one payment for 40 days; rent and mortgage count only if paid within the last 45 days.
- **Income.** Pension and benefit count only if paid within the last 45 days.
- **Subscriptions.** A subscription counts only if paid within the last 45 days.
- **New car.** The "new car" flag lasts 200 days.
- **Fuel average.** The monthly fuel estimate divides a fixed total by a month count that grows every day, so its rounded value changes every few days.

**What was measured on 300 customers, first night:** 183 customers had the fuel average as their earliest expiry, 102 the month start, and 15 a stopped bill.

**Why Tier 2 is needed.** Staleness on 30 Sep, out of 300 customers, when a tier is left out:

| Tiers run | Twins that differ from a full rebuild |
|---|---|
| None (twins as of 23 Sep) | 300 (100%) |
| Tier 1 only | 141 (47%) |
| Tier 1 + money window | 106 (35%) |
| Tier 1 + money window + rolling 1/7 rebuild sweep | 87 (29%) |
| **All tiers (expiry triggers)** | **0** |

In a full rebuild, about 91% of twins change in some field every day. Most of those changes are small drifts in the 90-day window and the fuel average.

**Recommendation.** Use the known expiry dates, which are exact and cheap. Keep a rolling 1/30 sweep only as a safety net against logic drift. Do a full rebuild whenever a rule changes.

**Corrections and memories are never overwritten.** Customer corrections (`twin_feedback`) and memories are overlays applied on read (`api.main.load_twin` → `apply_feedback`). `persist()` writes only `twin_profile`, `twin_facts` and `twin_state`. The tests check that a `twin_feedback` row and a memory-style table stay byte-identical across two persists, and that the correction still applies to the updated twin. Tier 0 takes the read-time twin, so a rejected car also drops its fuel from the push and the forecast.

## 3. Measurements (Apple-silicon laptop, 8 cores = 4P + 4E, Python 3.13, pandas 3.0)

**Caveat.** During the runs the machine was shared with other agents' jobs (load average 40–74 on 8 cores). Absolute timings came out about 3.7× slower than the quiet-machine part-1 benchmark: `Twin.build()` took 55–62 ms instead of 15.9 ms. Below, the rebuild path is normalized to the 16 ms part-1 figure and the other paths use the ratio measured in the same run: money path ≈ 0.09 × a rebuild; expiry calculation ≈ 0.18 × a rebuild.

**Volume and class split** (all 5,000 customers, 24–30 Sep, vectorized over the whole population):

| Metric | Value |
|---|---|
| Transactions per day | **5,694** average (4,838–7,207; the whole-year mean is 5,909, the busiest day 9,481 = 1.6× the mean) |
| Transactions per customer per day | **1.14** (1.18 over the year) |
| Customers touched per day | **68.6%** (63.8–78.1%; paydays 25–26 Sep are highest) |
| Signal-bearing share of touched | **51.4%** (40–70%; 35% of all customers) |
| Balance-only share of touched | **48.6%** (33% of all customers) |
| Product opened (forces a rebuild) | 0.4 per day |
| Tier 2(a): untouched, but the 90-day window moved | **21.3%** of all customers |
| Tier 2(b): calendar expiry → rebuild | **18.9%** of all customers (300-customer run, 32–78 per night; mostly the fuel average) |
| Nothing to do | ≈ 12–25% of customers per night |

**Cost per customer and per night** (300-customer run):

- Rebuild path ≈ 19 ms normalized.
- Money path ≈ 1.5 ms normalized.
- One night for 300 customers: 3.1–8.0 CPU-s under load. That is ≈ 0.9–2.2 CPU-s on a quiet machine, or 3–7 ms per customer in the population.

**Tier 0** (every booking of the week, single core, under load): p50 **41–56 µs**, p95 **49–148 µs**, including a full re-projection of the balance to payday.

**Parallelism.** Customers are independent, so the work scales linearly by customer partition (as in the part-1 benchmark; see [backfill.md](backfill.md)). `python -m twin.incremental --workers N` runs one process per customer-id range. The 8-worker 5K run could not finish on the overloaded machine within the deadline, so no N-worker wall time is quoted here.

## 4. Projection to 2.3M customers

**Assumptions:**

- KBC's activity per customer matches the synthetic data: 1.14–1.18 transactions per customer per day, 69% touched.
- The per-path costs are the normalized laptop figures above.
- Linear scaling by partition.

**Daily volume:** 2.3M × 1.14–1.18 ≈ **2.6–2.7M transactions a day**. That matches the **>2.5M payments a day** KBC's fraud engine scans ([kbc_retail_insurance.md](../research/kbc_retail_insurance.md)).

**Nightly CPU:**

| Path | Share of customers | Customers | ms each | CPU-h |
|---|---|---|---|---|
| 1b signal rebuild | 35.3% | 812K | 19 | 4.3 |
| 2b calendar rebuild | 18.9% | 435K | 19 | 2.3 |
| 1a balance-only refresh | 33.3% | 766K | 1.5 | 0.3 |
| 2a window-moved refresh | 21.3% | 490K | 1.5 | 0.2 |
| **Total, a normal night** | | | | **≈ 7.1 CPU-h → 3.6 cores for a 2-hour window (4 cores)** |
| With the fuel fix (§6): fuel expiries become money refreshes | | | | ≈ 5.4 CPU-h → 3 cores |
| 1st of the month (all twins rebuilt today) | ≈ 100% | 2.3M | 19 | ≈ 12 CPU-h → 6 cores for 2 h |
| For comparison: a full rebuild of everyone every night | 100% | 2.3M | 17 | 10.9 CPU-h |
| Raw, as measured on the overloaded laptop (×3.7) | | | | ≈ 26 CPU-h → 13 cores for 2 h (upper bound) |

**I/O per night.** The new batch is about 2.7M rows. The rebuild path reads about 13 months (about 430 rows) for each of 0.8–1.2M customers, so about 350–520M rows in total. The money path reads 90 days. In a warehouse partitioned by customer and date that is a routine nightly scan, and it is the part to optimize first (§6).

**Streaming (Tier 0):**

- Average load: 2.7M a day ≈ **31 transactions/s**.
- **Assumed peak factors:** the busiest day is 1.6× average (measured on synthetic data), and the peak hour carries 10% of that day's volume. That gives ≈ **120 transactions/s**.
- A salary batch of about 1M credits posted within about 15 minutes gives ≈ **1,100 transactions/s** in bursts.
- At ≈ 50 µs per event (p95 ≤ 150 µs), one core handles about 7,000–20,000 events/s. **Design target: 2,000 events/s, which is about 0.3 of one core.** Partition by customer for availability, not for capacity.

## 5. What is streaming and what is batch; failures and replay

- **Streaming (seconds):** balance, forecast, overdraft warning, payday push, large-debit message. These read the latest twin plus a small state per customer. The state holds the balance, daily spend rates, the big-debit threshold and upcoming bills; the nightly job prepares it from the same 90-day slice as the money path.
- **Batch (nightly):** every inferred fact, recurring bills, the payday plan and life events.
  - A new life event (a car purchase, a move) shows up the next morning.
  - A salary reacts immediately through Tier 0.
- **Idempotent and safe to re-run.** A night is a pure function of (yesterday's twins, the ledger, the date).
  - Re-running a night produces the same twins.
  - `persist()` upserts by `customer_id`, so a double run leaves the same rows (tested).
  - A crashed night is re-run per partition.
- **Missed nights.** Call `nightly(..., prev_day=<last run>)`. The batch, product changes and window exits are ranges, and expiries are triggered with `refresh_on ≤ today`, so a gap is caught up in one pass.
- **Late or corrected bookings** (value date in the past, reversals, re-categorization). The customer counts as signal-bearing on the night the change arrives. The rebuild re-reads the ledger, so the twin heals itself; nothing is patched.
- **Rule changes.** Run a full rebuild (part 1), because the nightly tiers assume yesterday's twins came from today's rules.

## 6. Findings and recommended follow-ups (not implemented; engine behaviour left unchanged)

1. **Payday and monthly bill dates always point to *next* month.**
   - Where: `plan()` and `recurring()` use `(as_of + MonthBegin(1)).replace(day=…)`.
   - Effect: correct on the 30th, but as of 23 Sep the plan says Lotte is paid on 23 Oct while the salary actually lands on 25 Sep. It also forces the month-start full rebuild.
   - Fix: take "the next occurrence after as_of". That gives the same output at 30 Sep for every day ≤ 28, and on other days it would ideally be computed on read.
2. **The fuel average drifts every day.**
   - Where: `infer_car` divides total fuel by months since first seen.
   - Effect: the rounded figure changes every 2–3 days without any new transaction, and it causes about 80% of Tier 2 rebuilds.
   - Fix: use a trailing 90-day or 12-month window (then the money window mechanism covers it), or roll it arithmetically in the money path.
3. **`since` uses a fixed `WINDOW_START`.** With a rolling 13-month window, "before <window start>" would change every day. In production, store the first-seen date in `twin_state` instead of recomputing it.
4. **`calendar_expiries()` costs about 0.18 × a rebuild** (pandas filters per bill). A single pass over the customer's rows would make it about 0.5 ms.
5. **Beyond the prototype:** a per-customer daily ring buffer (91 buckets of debits, credits, groceries and red days) would turn the whole money path into a vectorized update. The replay equality test is the guard for any such rewrite.
