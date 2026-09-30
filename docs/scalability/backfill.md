# Scalability study, part 1: the initial build (backfill) of 2.3M digital twins

Part 1 is the one-off job that builds every customer's twin from stored history: transactions, accounts,
products and customer data. It is slow and runs once. Part 2, the daily update, is covered separately.
This page covers the runner (`twin/backfill.py`), how we measured it, what we measured on synthetic
banks of 5K to 100K customers, and what that means for KBC's ~2.3M Belgian retail customers.

<!-- TLDR -->

## 1. The runner: `python -m twin.backfill`

`python -m twin.engine` loads **all** transactions into one pandas frame, then builds twins one by one.
That needs about 1.9 GB for 5,000 customers, and memory grows linearly with the bank. At 2.3M customers
it would need about 880 GB. The backfill keeps the engine's rules (`twin.engine.Twin(...).build()`) exactly
as they are and changes only how data gets to them:

| Step | What happens | Cost |
|---|---|---|
| **plan** | Stream `SELECT customer_id FROM customers ORDER BY customer_id` once and cut it into partitions of `--partition-size` consecutive ids. Ranges are cut on the actual ids, so sparse ids work and every customer is in exactly one partition. | One primary-key scan. Memory holds one `(lo, hi)` pair per partition (1,150 pairs for 2.3M at P = 2,000). |
| **load** | Each worker takes one partition at a time and runs the engine's own query shape (same columns, same `ORDER BY`), restricted to `customer_id BETWEEN lo AND hi AND booked_at >= cut-off`. It also reads the partition's customers, products and accounts, then groups rows per customer exactly as `build_twins` does. | Served by `idx_tx_customer_date`. Only the partition ever reaches pandas. |
| **build** | `Twin(customer, tx, products, accounts).build()` for each customer: the unchanged engine. | About 16 ms per twin (see §4). |
| **write** | One `BEGIN IMMEDIATE … COMMIT` per partition into the **target** database: `twin_profile` and `twin_facts` rows (byte-identical to `twin.engine.main`), plus a `backfill_partitions` row. | About 0.03 ms per twin. |

Design choices that matter at 2.3M:

* **Constant memory per worker.** A worker holds one partition (P customers × ~430 rows) and nothing
  else, so peak RSS depends on P, not on the size of the bank (§4.4).
* **Exactly-once and resumable.** A partition's twins and its `backfill_partitions` row are committed in
  the same transaction, so a partition is written completely or not at all. `--resume` skips committed
  partitions, and the stored plan (partition size, cut-off, limit) must match. A crash 9 hours into a
  12-hour run then costs only the partitions that were in flight.
* **One bad customer does not stop the run.** An exception in `build()` goes to `backfill_errors` with the
  customer id. The rest of the partition is still written.
* **The source is read-only.** It is opened with `mode=ro` and `PRAGMA query_only`. The target must be a
  different file, and the backfill refuses to write into its source. The target uses
  `twin.engine.TWIN_SCHEMA`, so the API and `twin.population` can read it like the demo database. Indexes
  are built once, after the bulk load. SQLite runs in WAL mode with `synchronous=NORMAL`: the last partition
  can be lost on power loss, but `--resume` redoes it.
* **Nothing big crosses processes.** Workers read and write SQLite themselves and return only a small
  timing dict. `spawn` (not `fork`) behaves the same on macOS and Linux and inherits no SQLite handles.
* **Built-in verification.** `--verify N` rebuilds N random customers with `twin.engine.build_one`
  (the engine's own single-customer path) on the source and compares them byte for byte with what the
  backfill stored: `profile_json` and every `twin_facts` row. `built_at` is the only volatile column
  and is not compared.

```bash
python -m twin.backfill --db SOURCE.db --out TARGET.db --workers 8 --partition-size 2000   # defaults: all cores, 2,000, 12 months
python -m twin.backfill --db SOURCE.db --out TARGET.db --resume                            # after a crash
python -m twin.backfill --db SOURCE.db --out TARGET.db --verify 200 --report metrics.json  # check + machine-readable metrics
```

## 2. How much history to read: exactly 12 months (`--history-months 12`)

`--history-months N` reads rows booked on or after `AS_OF − N months + 1 day`. For N = 12 that is
2025-10-01, which is exactly the engine's `WINDOW_START`. This is a test in `tests/test_backfill.py`.
We read the engine to decide how much history it needs:

| Engine rule (twin/engine.py) | History it needs |
|---|---|
| `infer_money`, `plan` (groceries), `money_stress`: `AS_OF − 90 days` windows | 3 months |
| `recurring()` monthly bills: at least 2 (housing, utilities, insurance) or 3 distinct months, last seen within 70 days | 2–3 months |
| `recurring()` quarterly bills: median interval > 80 days, at least 2–3 occurrences | ~6 months |
| **Yearly bills** (`YEARLY_SUBS`, "jaarpremie / prime annuelle / annual premium"): paid once a year | **12 months** |
| `_since`: first seen within 45 days of `WINDOW_START` ⇒ "before 2025-10-01" | data starts at `WINDOW_START` |
| Yearly totals: maintenance, vet, road tax, "N flight bookings this year", fuel per month (normalised by months since `max(first, WINDOW_START)`) | exactly 12 months: more history inflates them |

So 12 months is the **minimum**, because yearly bills must be seen once. With this engine it is also the
**maximum**. A 13th month is not a free safety margin for late yearly bills. We tested this: we gave 1,000
customers a synthetic 13th month (their September-2026 rows copied one year back, without one-off events)
and rebuilt them. Results in §4.7:

* a yearly bill paid in both Septembers is kept at its **oldest** date, because the first matching row
  wins in `recurring()`, so `next_date` falls in the past;
* a yearly insurance premium seen in two different months passes the 2-month test for insurance and is
  filed as **quarterly**, with a monthly equivalent 4× too high;
* yearly totals such as fuel per month and vet costs per year go up by about 1/12.

If production wants a margin for yearly bills that are paid late, the engine first needs three small fixes.
(1) Keep the latest occurrence of each yearly bill. (2) Treat an interval above ~300 days as yearly. (3) Cap
yearly sums to the last 365 days. After that, `--history-months 13` is safe. The I/O projection in §5 shows
both 12 and 13 months. `--history-months 0` reads all history, which is what `build_one` does. On the
generator's data, 0 and 12 give identical twins because the data starts on `WINDOW_START`.

<!-- MEASUREMENTS -->
