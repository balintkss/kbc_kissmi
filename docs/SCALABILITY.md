# Scalability for KBC's 2.3M customers

**Verdict: viable, with a wide margin.** Both parts were measured on synthetic banks of 5K–100K customers
(8-core laptop) and extrapolated linearly. Details: [initial build](scalability/backfill.md) ·
[daily update](scalability/daily.md) · [architecture & cost](scalability/architecture_cost.md).

| Part | What it does | Measured | 2.3M customers |
|---|---|---|---|
| **1. Initial build** (one-off, `twin/backfill.py`) | Build every twin from ~12 months of stored history, partitioned and parallel, resumable | **~17 ms per twin on one core, flat from 5K to 100K customers** (16.8 → 17.5 ms); constant **~350 MB per worker** (vs ~880 GB if everything were loaded at once); 5.7 KB per twin | **~11 CPU-hours** → ~80 min on 8 cores, ~20 min on 32 cores; ~13 GB of twins |
| **2. Daily update** (`twin/incremental.py`) | Tier 0: react per transaction (salary landed → payday plan). Tier 1: nightly recompute only for customers whose day changed a fact. Tier 2: refresh when a fact's time window expires | 7-day replay gives **exactly the same twins as a full rebuild**; Tier 0 ≈ **50 µs per transaction** (~20,000 events/s per core) | **~7 CPU-hours per night → 4 cores for a 2-hour window**; worst night (1st of the month) ~12 CPU-hours; KBC's peak ~100–1,100 tx/s fits on one core |
| **Cost** (europe-west1 list prices, 30 Sep 2026) | Serving API, streaming, nightly batch, storage, consent/corrections store | — | Infrastructure **≈ $1,700/month ≈ $0.009 per customer per year**; with Kate's LLM ≈ $30k/month ≈ $0.16 per customer per year |

**Why it scales:** the twin is built with deterministic rules, not an LLM. That is ~36,000× cheaper per twin than
using GPT-4.1 for inference. The LLM is only used for Kate's language, which dominates the cost.

**Caveats:** synthetic data we generated ourselves; laptop measurements with linear extrapolation; production would
read from KBC's warehouse (column store) instead of SQLite. A pilot should validate I/O, real-data noise and the
payday peak.
