# Scalability study, part 3: production architecture and cost model for ~2.3M twins

> **Status: PROVISIONAL (2026-09-30).** The architecture holds. The cost numbers are formulas with inputs marked **[P]**.
> These inputs are placeholders until part 1 ([`backfill.md`](backfill.md), the initial build) and part 2 (the daily incremental
> update: Tier 0 / 1 / 2) publish measured values. §3.7 lists every input to replace. All prices are **USD list prices**
> for **europe-west1 (Belgium)** unless stated. They exclude VAT, free tiers, committed-use discounts and any negotiated
> KBC discount. We read them from Google's region-specific price tables on 2026-09-30.
> **(U)** marks a price we could not confirm for europe-west1.

## TL;DR

- **The twin is small data.** It averages **5.8 KB of JSON per customer**, measured on the local DB. That is **≈ 13 GB for 2.3M twins**, or
  ≈ 18 GB including the queryable fact rows. **30 days of versions add 170–370 GiB** in the analytical store, which costs **< $10/month**.
- **Twin compute is a rounding error.** A full backfill of 2.3M twins is **≈ 22 vCPU-hours**, which costs **≈ $5 per run** and takes ≈ 20 min on 64 vCPUs.
  The nightly Tier 1 recompute costs **≈ $60/month** including data reads and writes.
- **Base-case infrastructure** is **≈ $1,100/month for production** and **≈ $1,700/month with non-production environments**.
  That is **≈ $0.009 per customer per year**. The largest infrastructure line is the serving API, not the twin build.
- **The only material variable cost is the LLM behind Kate.** It depends on conversations, not on the number of customers.
  - Full turn cost on GPT-4.1 (the PITCH scenarios): **$5.7k / $28.4k / $190k per month** (low / base / high).
  - Base case, all-in: **≈ $30k/month ≈ $0.16 per customer per year**.
  - Counting only the tokens the twin adds to Kate: **≈ $0.08 per customer per year**.
- **Rules instead of an LLM for inference** is the decisive design choice. Inferring the twin with GPT-4.1 would cost ≈ $0.027 per build
  against ≈ $0.00000075 with rules, about 36,000× more. At base nightly volume that is **≈ $600k/month instead of ≈ $17**.

---

## 1. Reference architecture

### 1.1 Design principles

1. **The derived twin and customer memory are separate stores.**
   - The *derived twin* (facts, implications, plan) is a **rebuildable cache**. It can be recomputed from source in minutes.
     So its RPO can be "last night", and a disaster-recovery rebuild is just a batch job.
   - *Customer memory* holds consent flags, confirmations, rejections, goals and forget requests. It is **primary data**
     that nothing can rebuild, so it lives in a transactional, backed-up system of record.
   - Every rebuild reads customer memory, so a rejected or forgotten fact is **never silently re-inferred**.
2. **Rules do the inference and the LLM only does language.** This is how the prototype already works (`twin/engine.py` vs `twin/assistant.py`).
3. **One stateless engine for every path.** Backfill, Tier 1 and Tier 2 run the same `Twin(...).build()` code. They differ only in *which* customers
   they process and *when*. Tier 0 is a thin per-transaction rule function that reads the precomputed twin. It does not rebuild it.
4. **Purpose-gated reads.** Every read through the API passes a consent/purpose gate (the Financial Understanding Contract).
5. **Fail open to generic, never to wrong personalisation.** If the twin store is unavailable, channels render the anonymous page.
   That path already exists: `page(twin=None)`.
6. **Fraud firewall.** The security/fraud baseline is a separate, purpose-limited system ([`PRIVATE_BANKER_AT_SCALE.md`](../PRIVATE_BANKER_AT_SCALE.md)).
   It has no data path into or out of the commercial twin.

### 1.2 Logical diagram (cloud-agnostic)

```text
 SOURCES (KBC systems of record, EU)
 +----------------------+  +------------------------+  +----------------------+  +------------------------+
 | Core-banking booking |  | Warehouse: 13 months   |  | Kate conversations   |  | Customer actions:      |
 | feed (per tx,        |  | of tx, products,       |  | (memory only with    |  | confirm / correct /    |
 | ~2.7M tx/day)        |  | accounts, balances     |  | kate_memory consent) |  | forget, goals, consent |
 +----------+-----------+  +-----------+------------+  +----------+-----------+  +-----------+------------+
            | CDC / events             | batch extract            | memory events           | API writes
            v                          v                          v                         v
 +----------------------+  +------------------------+  +---------------------------------------------------+
 | EVENT BUS  tx.booked |  | BATCH (stateless jobs, |  | CUSTOMER MEMORY  (system of record, backed up)    |
 | key = pseudonymous   |  | partitioned by hash)   |  | consent flags = Financial Understanding Contract  |
 | customer key; 2nd    |  |  * Backfill (once)     |<-+ confirmed facts, rejections + suppressions,      |
 | sub -> raw archive   |  |  * Tier 1 nightly      |  | goals, forget journal                             |
 +----------+-----------+  |  * Tier 2 calendar     |  +-----------------------+---------------------------+
            |              +-----------+------------+                          | read at request time
            |                          | twin vN (rules_version)               | (purpose gate)
            v                          v                                       v
 +----------------------+  +------------------------+  +---------------------------------------------------+
 | TIER 0  stateless    |  | TWIN STORE             |  | TWIN API  (existing FastAPI, stateless,           |
 | rule fn per tx:      +->| serving key-value:     +->| N replicas): auth, consent/purpose gate,          |
 | salary landed? big   |  | twin_profile,          |  | glass box, corrections, audit, fail-open to       |
 | purchase? -> push    |  | tier-0 state           |  | the generic (anonymous) page                      |
 +----------+-----------+  +-----------+------------+  +-----+-----------+-----------+-----------+--------+
            |                          | copy                |           |           |           |
            v                          v                     v           v           v           v
 +----------------------+  +------------------------+      Kate      KBC Mobile    kbc.be    Advisor / ops
 | KBC push service     |  | ANALYTICAL COPY        |   (EU LLM     (push,       (web)     (role-based,
 | (rate-limited,       |  | facts, 30-day versions,|    endpoint,   pages,                every view
 |  quiet hours)        |  | aggregates, audit      |    tools)      plan)                 audited)
 +----------------------+  +------------------------+

 CROSS-CUTTING   Secret Manager + KMS (CMEK) | one least-privilege service account per box | append-only audit log
                 | consent flags + kill-switch feature flags (per fact type, topic, channel) | EU-only resource locations

 ======================================== FRAUD FIREWALL ========================================
 Security / fraud baseline = separate project and perimeter: own subscription to the booking feed,
 own service accounts, NO read path to twin store or customer memory, NO write path into commercial use.
```

### 1.3 The data paths

| Path | Trigger | What runs | Reads | Writes |
|---|---|---|---|---|
| **Backfill** (part 1) | Once at launch, then on every rules-version change (full rebuild) | `Twin.build()` in parallel tasks, one partition per task (part 1's runner defaults to 2,000 customers per partition) | 13 months of transactions, products, accounts and customer memory (suppressions, confirmations) | Twin store (serving), analytical copy (facts, version 0) |
| **Tier 0 streaming** (part 2) | Every booked transaction, ≈ 2.7M/day at 2.3M customers | Stateless rule function: "is this the expected salary / a big purchase / a new insurer?" It reads the twin's payday fact and the tier-0 state | Twin store (one small document per customer) | Tier-0 state. Push request to KBC's push service (template text, no LLM). A "dirty" flag for Tier 1 |
| **Tier 1 nightly** (part 2) | After the warehouse end-of-day load | `Twin.build()` only for customers flagged as having signal-bearing transactions | That customer's 13-month history plus customer memory | New twin version `vN` (with `rules_version`). Diffs go to the analytical copy |
| **Tier 2 calendar** (part 2) | Date-driven: payday tomorrow, a yearly bill due, a fact expiring | Plan/moments refresh only. No fact inference (≈ 0.4 ms per twin measured for `json.loads` + 5 pages + moments) | Current twin | Updated plan/moments |
| **Correction / forget** | Customer taps "That's not me", edits a fact or asks to forget it | Customer memory is written at once. `twin/feedback.py` already applies corrections at read time without a rebuild | – | Customer memory. Forget journal → propagation job (see §5) |
| **Kate turn** | A customer message | `twin/assistant.py`: compact twin (≈ 480 tokens) plus 4 tools bound server-side to the session | Twin store via the API | Chat history (only with consent) |

### 1.4 GCP instantiation (europe-west1 = Belgium) and equivalents

This is **one possible instantiation**. We have not sourced which cloud or on-prem stack KBC runs, so the design keeps the engine portable.
The engine is pure Python/pandas with no GCP-specific code. That also supports a DORA-style exit plan.

| Logical component | GCP instantiation | Why | Azure | AWS | On-prem / open source |
|---|---|---|---|---|---|
| Event bus | **Pub/Sub** (ordering key = pseudonymous customer key). Use Managed Service for Apache Kafka instead if the core feed is already Kafka | Serverless, $40/TiB, independent subscriptions (Tier 0, archive, and a separate one for fraud) | Event Hubs | Kinesis / MSK | Kafka |
| Tier 0 function | **Cloud Run** service (Pub/Sub push) or a Cloud Run worker pool (pull), min instances ≥ 1 | Stateless, millisecond rules, autoscaling | Functions / Container Apps | Lambda / Fargate | Kafka Streams / Flink |
| Backfill, Tier 1, Tier 2 | **Cloud Run jobs** (parallel tasks). **Dataflow** if managed shuffle/grouping is wanted. **BigQuery** for the extract | The engine runs unchanged in a container | Batch / Databricks | Batch / Glue / EMR | Spark on Kubernetes |
| Twin store (serving) | **Firestore** (Native mode, regional europe-west1; `eur3` for multi-region). **Bigtable** if Tier-0 write rates or per-customer history move into the store | ≈ 14 GiB total. Firestore is pay-per-operation. Documents max ≈ 9 KB, far below the 1 MiB limit | Cosmos DB | DynamoDB | Cassandra / ScyllaDB / Redis / PostgreSQL |
| Analytical copy | **BigQuery** dataset in europe-west1 | Facts, 30-day versions, `/ops` aggregates, audit | Fabric / Synapse / Databricks SQL | Redshift / Athena | Existing warehouse |
| Customer memory (system of record) | **Cloud SQL for PostgreSQL** HA (the teammate's target in [`DATABASE_HANDOFF.md`](../DATABASE_HANDOFF.md)), or AlloyDB | Relational and transactional, with PITR. Consent and feedback need ACID | Azure Database for PostgreSQL | RDS / Aurora | PostgreSQL |
| Twin API | **Cloud Run** (the existing FastAPI container), behind an HTTPS load balancer with Cloud Armor, or behind KBC's API gateway | Already built. Stateless and horizontally scaled | Container Apps / AKS | ECS / EKS | OpenShift / Kubernetes |
| Secrets and keys | **Secret Manager** (`TWIN_SECRET`, LLM key), **Cloud KMS** (CMEK) | No secrets in the image or environment files | Key Vault | Secrets Manager / KMS | Vault / HSM |
| Logs and audit | **Cloud Logging** plus Cloud Audit Logs. Business audit (the `ops_audit` equivalent) goes append-only into BigQuery | – | Monitor / Log Analytics | CloudWatch / CloudTrail | ELK / Splunk |
| Consent and feature flags | Consent flags in customer memory, plus an OpenFeature-compatible flag service for kill switches per fact type, topic and channel | Separates "is it allowed?" from "is it switched on?" | same | same | same |
| LLM | An EU-resident GPT-4.1 deployment under KBC's data processing agreement. KBC's Kate already runs on GPT-4.1 ([KBC newsroom](https://newsroom.kbc.com/kate-five-years-and-five-milestones)) | – | – | – | – |

---

## 2. Measured locally: what a twin weighs

These were read-only queries (`sqlite3 "file:data/kbc_twin.db?mode=ro"`) on the synthetic DB: 5,000 customers and 2,156,874 transactions
(Oct 2025 – Sep 2026), 2026-09-30.

| Metric | Value |
|---|---|
| `twin_profile.profile_json`, UTF-8 bytes | **mean 5,765 B**, median 5,933, p95 7,453, p99 8,027, max 8,928 |
| same, minified JSON / zlib-compressed | 5,344 B / **1,702 B** (3.4× compression) |
| `twin_profile` on disk, including SQLite page overhead | 32.9 MB / 5,000 = **6.59 KB per twin** |
| Composition (Lotte, 6.2 KB) | facts 2.7 KB · recurring bills 2.0 KB · plan 1.2 KB · rest 0.2 KB. Evidence tx ids ≈ 240 chars per twin |
| `twin_facts` rows per customer | **8.12** (40,604 rows), ≈ 102 B payload per row. On disk 4.96 MB table + 1.24 MB index = **1.24 KB per customer** |
| Transactions per customer | 431 per 12 months = **1.18 per day** (matches the ~1.2 assumption). 98.6 B per row on disk (+56 B for two indexes) |
| Transaction row, estimated BigQuery logical size | ≈ **108 B** (3 × INT64, DATE, 2 × FLOAT64, 6 short strings) |

### Projection to 2.3M customers

| Item | Per customer | 2.3M customers | Monthly storage cost |
|---|---|---|---|
| Current twin (raw JSON) | 5.77 KB | **13.3 GB (12.4 GiB)** | – |
| Twin + fact projection, SQLite-equivalent on disk | 7.83 KB | **18.0 GB (16.8 GiB)** | – |
| Compressed twin (zlib) | 1.70 KB | 3.9 GB | – |
| **Serving store** (Firestore: twin + ≈ 0.1 KB overhead + ≈ 0.5 KB tier-0 state) | ≈ 6.4 KB | **13.6 GiB** | $2.25 (+ $6.30 for 14 daily backups) |
| **30 days of versions**: full daily snapshot | – | 30 × 13.3 GB = 398 GB (371 GiB) | $7.40 (BigQuery active logical $0.02/GiB) |
| **30 days of versions**: only changed twins (base: 42% per day, Tier 1 + Tier 2) | – | 168 GiB (low 75, high 383) | $3.40 (low $1.50, high $7.70) |
| Fact rows (analytical) | 8.12 rows × ~150 B | 2.6 GiB | $0.05 |
| 13-month source history, *if* mirrored (normally already in KBC's warehouse) | 467 tx × 108 B = 50 KB | 1.07 billion rows, **116 GB (108 GiB)** | $2.20 |

> History length: this model uses **13 months** as a conservative I/O assumption. Part 1 ([`backfill.md`](backfill.md) §2) found
> that the current engine needs **exactly 12 months**: 13 would first need three small engine fixes for yearly bills.
> With 12 months, the history is 0.99 billion rows and ≈ 107 GB. Every history-dependent line below drops by ≈ 8%.

On real data a twin could be 2–3× larger: more recurring bills, households, other-bank flows. Even then storage stays below $30/month.

---

## 3. Cost model

### 3.1 List prices used (seen 2026-09-30)

| Service | Price (europe-west1 unless noted) | Source |
|---|---|---|
| **Cloud Run jobs** | $0.000018 per vCPU-s, $0.000002 per GiB-s (≈ $0.079 per vCPU-hour with 2 GiB) | [cloud.google.com/run/pricing](https://cloud.google.com/run/pricing). europe-west1 is a Tier 1 region |
| **Cloud Run services**, request-based | $0.000024 per vCPU-s active, $0.0000025 per GiB-s, **$0.40 per 1M requests**. Idle min-instance $0.0000025 per vCPU-s | same |
| Cloud Run services, instance-based / worker pools | $0.000018 / $0.000002 · worker pools $0.000011244 / $0.000001235 per vCPU-s / GiB-s. 1-year Cloud Run CUD ≈ −17% | same |
| **Dataflow** batch · FlexRS · streaming | vCPU $0.059/h · $0.0354/h · $0.072/h. Memory $0.004172 per GiB-h. Shuffle $0.011/GiB. Streaming Engine $0.098 per compute unit | [cloud.google.com/dataflow/pricing](https://cloud.google.com/dataflow/pricing) |
| **Compute Engine** | n2-standard-8 $0.427336/h (≈ $0.053 per vCPU-h), e2-standard-8 $0.29486/h. Spot n2-standard-8 ≈ $0.1075/h **(U)** (third-party tracker, volatile) | [Google general-purpose VM pricing](https://cloud.google.com/products/compute/pricing/general-purpose) · [gcloud-compute.com](https://gcloud-compute.com/n2-standard-8.html) |
| **Pub/Sub** | **$40 per TiB** throughput (publish + subscribe), "in all Google Cloud regions". First 10 GiB/month free. **Minimum 1 KB per request**. BigQuery subscriptions $50/TiB. Import topics $50–80/TiB. Retained-message storage $0.27 per GiB-month | [cloud.google.com/pubsub/pricing](https://cloud.google.com/pubsub/pricing) |
| **BigQuery** | On-demand **$7.50/TiB** (EU multi-region $6.25). Active logical storage **$0.02 per GiB-month**, long-term $0.01. Standard edition $0.044 per slot-hour. Storage Write API $0.03/GiB (2 TiB/month free). Storage Read API $1.32/TiB (300 TiB/month free). Batch loads free | [cloud.google.com/bigquery/pricing](https://cloud.google.com/bigquery/pricing) |
| **Firestore** | Reads **$0.033 per 100k**, writes **$0.099 per 100k**, deletes $0.011 per 100k. Storage $0.165 per GiB-month, backups $0.033. **eur3** multi-region: $0.06 / $0.18 / $0.02, storage $0.18 | [cloud.google.com/firestore/pricing](https://cloud.google.com/firestore/pricing) |
| **Bigtable** | $0.65 per node-hour ($474.50/month). SSD $0.17 per GiB-month, HDD $0.026, standard backup $0.026. 1-year CUD −20% | [cloud.google.com/bigtable/pricing](https://cloud.google.com/bigtable/pricing) |
| **Cloud SQL** (Enterprise) | $0.0413 per vCPU-h, $0.007 per GiB-h. HA doubles both ($0.0826 / $0.014) | [cloud.google.com/sql/pricing](https://cloud.google.com/sql/pricing) |
| **Cloud Logging** | $0.50/GiB ingested (first 50 GiB per project per month free), includes 30 days of storage. $0.01 per GiB-month beyond 30 days | [cloud.google.com/stackdriver/pricing](https://cloud.google.com/stackdriver/pricing) |
| Secret Manager · Cloud KMS | $0.06 per active secret version per month, $0.03 per 10k accesses · $0.06 per key version per month, $0.03 per 10k crypto operations | [secret-manager/pricing](https://cloud.google.com/secret-manager/pricing) · [kms/pricing](https://cloud.google.com/kms/pricing) |
| Internet egress (Premium tier, to Europe) | $0.12/GiB (1 GiB–1 TiB), $0.11 (1–10 TiB), $0.085 (> 10 TiB). Default table as displayed; europe-west1 source not confirmed **(U)** | [cloud.google.com/vpc/network-pricing](https://cloud.google.com/vpc/network-pricing) |
| **LLM** (reused from [`PITCH.md`](../PITCH.md) §5) | GPT-4.1 $2.00 / $0.50 cached / $8.00 per 1M tokens. GPT-4.1-mini $0.40 / $0.10 / $1.60. **≈ $0.0082 per Kate turn** on GPT-4.1, ≈ $0.0016 on mini | [developers.openai.com/api/docs/pricing](https://developers.openai.com/api/docs/pricing), as recorded in PITCH (seen 2026-09-30) |

### 3.2 Inputs and formulas

`C` = 2,300,000 customers, 30 days per month. Inputs marked **[P]** are provisional (see §3.7).

| Input | Low | Base | High | Basis |
|---|---|---|---|---|
| `t_build`: ms per full twin rebuild, end to end (load + build + serialise) | 16 | 17 | 17 | **[P]** PITCH benchmark: 15.9 ms build + 1.0 ms load + 0.06 ms serialise |
| `k`: platform overhead factor (I/O wait, skew, retries, start-up) | 1.5 | 2 | 4 | **[P]** guess |
| `tx_day`: transactions per customer per day | 1.18 | 1.18 | 1.18 | measured on synthetic data (431 per year). KBC's fraud engine scans > 2.5M payments/day ([research](../research/kbc_retail_insurance.md)), the same order as C × 1.18 = 2.72M |
| `s`: share of customers recomputed nightly (Tier 1) | 14% | 32% | 70% | **[P]** proxies on synthetic data: customer-days with a narrow signal tx 13.6%, a broad signal tx 31.8%, any tx 70.3% |
| `t2`: share refreshed per day (Tier 2), at 0.5 ms × `k` | 3% | 10% | 100% | **[P]** guess |
| `cpu_t0`: billed CPU per Tier-0 event | 5 ms | 10 ms | 20 ms | **[P]** guess |
| App opens per customer per day × API calls per open | 0.5 × 2 | 1.5 × 3 | 4 × 5 | **[P]** guess. KBC Mobile has ~2.1M Belgian app users ([research](../research/kbc_retail_insurance.md)) |
| `cpu_api`: CPU per API call (utilisation 50%) | 5 ms | 10 ms | 20 ms | **[P]** Twin logic measured at 0.4 ms. The rest is FastAPI, auth and the store client |
| Response size on the wire | 2 KB | 2 KB | 3 KB | page JSON ≈ 1.0 KB and moments ≈ 0.4 KB raw, measured. The glass box with evidence is larger |
| Log ingestion per month | 50 GiB | 300 GiB | 1,000 GiB | **[P]** depends on request-log sampling |
| Kate usage (PITCH scenarios) | A: 10% chat, 3 turns/month | B: 30%, 5 turns | C: 100%, 10 turns | [`PITCH.md`](../PITCH.md) §5 |
| Non-production environments | +50% of infrastructure | +50% | +50% | **[P]** dev/test/acceptance |

```text
H_bytes (13-month history) = C × tx_day × 395 days × 108 B               ≈ 116 GB = 0.1055 TiB
E  (Tier-0 events/month)   = C × tx_day × 30                              ≈ 81.6M
R  (API requests/month)    = C × opens × calls × 30                       (base 310.5M)

Backfill $ (one run)       = C × t_build × k × (p_job_cpu + 2 GiB × p_job_mem)       compute
                           + H_bytes × $7.50/TiB                                     read (≈ $0 via Storage Read API)
                           + C × p_write                                             initial twin documents
Tier 0  $/month            = E × cpu_t0 / 0.5 × (p_cpu + 1 GiB × p_mem) + E × $0.40/1M + min-instance idle
                           + [(2 × E × 1 KB − 10 GiB) × $40 + E × 1 KB × $50] / TiB  Pub/Sub + BigQuery archive subscription
                           + E × p_read + E × s × p_write                            tier-0 state
Tier 1  $/month            = C × s × 30 × t_build × k × p_job + 30 × scan × H_bytes × $7.50/TiB + C × s × 30 × p_write
Tier 2  $/month            = C × t2 × 30 × (0.5 ms × k × p_job + p_write)
Storage $/month            = G_serving × ($0.165 + 14 × $0.033) + (G_versions + G_facts + G_audit) × $0.02
Serving $/month            = R × cpu_api / 0.5 × (p_cpu + p_mem) + R × $0.40/1M + 2 min instances
                           + R × $0.033/100k (twin read) + egress(R × response size)
Customer memory $/month    = Cloud SQL HA, 2 vCPU / 8 GiB (high: 4 / 16) × 730 h
LLM     $/month            = Kate turns × $/turn
Per customer per year      = 12 × (infrastructure × 1.5 + LLM) / C
```

The script that evaluates these formulas is small and deterministic. Rerun it with measured inputs and replace the tables below.

### 3.3 One-off backfill (part 1 will replace these numbers)

| | Low | Base | High |
|---|---|---|---|
| CPU: C × `t_build` × `k` | 15.3 vCPU-h | **21.7 vCPU-h** | 43.4 vCPU-h |
| Compute (Cloud Run jobs, 2 GiB per vCPU) | $1.2 | $1.7 | $3.4 |
| Read 13 months of history (BigQuery on-demand scan of 0.1055 TiB) | $0.8 | $0.8 | $0.8 |
| 2.3M initial twin writes (Firestore) | $2.3 | $2.3 | $2.3 |
| **Total per full run** | **$4.3** | **$4.8** | **$6.5** |
| Wall clock on 64 parallel vCPUs (CPU only) | 14 min | 20 min | 41 min |

- **Ten rehearsal runs cost < $70.**
- **The practical floor is the store's write ramp, not CPU.** Following Firestore's 500/50/5 rule (500 ops/s, then +50% every 5 minutes),
  2.3M initial writes take **≈ 30 min**.
- **Optional replay** ("twin as of every day for the last 13 months", for back-testing rules against later outcomes)
  multiplies CPU by 395 days: **≈ $480 / $680 / $1,360**. Spot VMs would cut that by ~4×.

### 3.4 Monthly run cost (production, list price, USD)

| Line | Low | Base | High | Base detail |
|---|---:|---:|---:|---|
| Tier 0 streaming | 115 | **151** | 225 | Cloud Run $89 (81.6M events) · Pub/Sub $9 · tier-0 state reads and writes $53 |
| Tier 1 nightly | 15 | **62** | 168 | compute $17 (736k twins/night) · BigQuery scan $24 · twin writes $22 |
| Tier 2 calendar | 2 | **7** | 71 | almost all store writes |
| Storage (Firestore + backups + BigQuery versions, facts, audit) | 13 | **26** | 64 | see §2 |
| Serving API | 110 | **487** | 2,931 | Cloud Run $315 (310.5M requests) · twin reads $102 · egress $69 |
| Logging + Secret Manager, KMS, scheduler, monitoring | 50 | **175** | 525 | logging $125 · misc $50 |
| Customer memory (Cloud SQL HA) | 202 | **202** | 405 | 2 vCPU / 8 GiB HA (high: 4 / 16) |
| **Infrastructure, production** | **507** | **1,111** | **4,388** | |
| Non-production (+50%) | 253 | 555 | 2,194 | |
| **Infrastructure, all environments** | **760** | **1,666** | **6,583** | |
| Kate LLM on GPT-4.1, full turn cost (PITCH A / B / C) | 5,686 | **28,428** | 189,520 | ≈ PITCH §5: $5.7k / $28.4k / $189.5k |
| **Total, all-in** | **6,446** | **30,094** | **196,103** | |

### 3.5 Cost per customer per year (provisional)

| View | Low | Base | High |
|---|---:|---:|---:|
| Infrastructure only (all environments) | $0.004 | **$0.009** | $0.034 |
| Infrastructure + Kate on GPT-4.1, **full** turn cost | $0.034 | **$0.157** | $1.02 |
| Infrastructure + Kate on GPT-4.1, **incremental** (only the tokens the twin adds: compact twin + 4 tool schemas on 2 calls + tool result ≈ 2,040 input tokens ≈ $0.004 per turn) | $0.019 | **$0.083** | $0.53 |
| Infrastructure + Kate on GPT-4.1-mini, full turn cost | $0.010 | $0.038 | $0.23 |

**Reading the numbers:**
- The twin itself (build, store, serve) costs **less than one cent per customer per year**.
- What moves the total is **how much customers talk to Kate**, and KBC already pays for most of those tokens today.
- Engineering, model governance and operations staff are **not** in this model. At this scale they dominate the cloud bill.

### 3.6 Sensitivities (base case)

| Change | Effect |
|---|---|
| **Bigtable** (2 × 1-node clusters for HA) instead of Firestore | ≈ **+$760/month**: nodes $949 + SSD $5 − Firestore operations and storage ≈ $192. Worth it only if Tier-0 state writes or per-customer history move into the store |
| Firestore **eur3** multi-region instead of regional | Operations cost 1.82× → ≈ **+$150/month** |
| **Full nightly rebuild** of all 2.3M (no incremental Tier 1) | Tier 1 rises from $62 to ≈ **$144/month**. Incremental Tier 1 buys *freshness*, not savings |
| Tier 1 on **Dataflow** batch ($0.059/vCPU-h + 3.75 GiB × $0.004172 ≈ $0.075/vCPU-h) instead of Cloud Run jobs ($0.079) | ≈ same, plus shuffle ($0.011/GiB) |
| Tier 1 / backfill on **spot VMs** (≈ $0.013/vCPU-h) | ≈ −80% on a line that is ~1.5% of infrastructure |
| 1-year commitments (Cloud Run −17%, Firestore −20%, Bigtable −20%) | ≈ −15% of infrastructure |
| API called only from KBC's own backend over Interconnect instead of the internet | Most of the $69 egress disappears. Interconnect is priced separately and not modelled |
| Request logs at 100% instead of sampled | Logging moves from the base to the high column (+$350/month) |
| **LLM for inference instead of rules** | ≈ 467 tx × ~25 tokens ≈ 11.7k input + 500 output tokens per build ≈ **$0.027 per build on GPT-4.1** ($0.0055 on mini) vs **$0.00000075** with rules. At base nightly volume: **≈ $604k/month** (mini $121k) vs **$17** |

### 3.7 Inputs to replace with measured values

| # | Input | Provisional value | Measured by | Where it enters |
|---|---|---|---|---|
| 1 | `t_build`: ms per full rebuild (p50 and p95, target platform) | 17 ms (laptop, 1 core) | **Part 1** ([`backfill.md`](backfill.md)) | Backfill, Tier 1 |
| 2 | `k`: overhead factor (wall-clock vCPU-s ÷ pure build CPU) | 2 | **Part 1** | Backfill, Tier 1 |
| 3 | Backfill read volume, rows and bytes per customer | 467 tx, 50 KB | **Part 1** | Backfill read cost, I/O plan |
| 4 | Memory per task / customers per partition | 2 GiB per vCPU, 2,000 customers (part 1 default) | **Part 1** | Job sizing |
| 5 | `s`: share of customers with signal-bearing transactions per night | 32% (proxy) | **Part 2** | Tier 1 |
| 6 | `cpu_t0` and state reads/writes per Tier-0 event | 10 ms, 1 read + `s` writes | **Part 2** | Tier 0 |
| 7 | `t2` and cost per Tier-2 refresh | 10%/day, 0.5 ms | **Part 2** | Tier 2 |
| 8 | Tier-0 end-to-end latency (booking → push request) | target p95 ≤ 10 s | **Part 2**, then pilot | SLOs |
| 9 | `tx_day` on real KBC data (households, SMEs, joint accounts) | 1.18 | Pilot | Everything |
| 10 | Twin size on real data | 5.8 KB | Pilot | Storage |
| 11 | App opens/day, API calls/open, CPU/call, response size | 1.5, 3, 10 ms, 2 KB | KBC analytics + load test | Serving |
| 12 | Kate adoption and turns; real tokens per turn | PITCH scenario B, ≈ 3,400 input / 185 output tokens | KBC Kate analytics | LLM |
| 13 | Log volume after sampling/exclusions | 300 GiB/month | Pilot | Logging |

---

## 4. Latency and SLOs (proposed targets to validate)

| Path | Target | Budget and reasoning |
|---|---|---|
| **Tier 0**: salary booked → payday push request queued | **p95 ≤ 10 s, p99 ≤ 60 s** on a normal day. **p95 ≤ 2 min** at the payday burst | Core-banking feed latency (KBC-dependent, unknown) + Pub/Sub delivery (measure; no published guarantee) + rule function (≤ 20 ms) + state read/write (tens of ms) + push service. A synthetic "canary salary" every 5 min measures this end to end |
| **Tier 1**: nightly recompute | Done inside a **3-hour window** after the warehouse end-of-day load, e.g. 02:00–05:00 CET | Base needs ≈ 13 min on 32 vCPUs (736k twins × 34 ms), about 14× headroom. The high case needs ≈ 57 min on 32 vCPUs, so run 64 |
| **Full rebuild** (rules change, disaster recovery) | ≤ 1 h for 2.3M | ≈ 20 min of CPU on 64 vCPUs. The ≈ 30 min store write ramp dominates |
| **Tier 2**: calendar refresh | Before 06:00 local on the relevant day | Seconds of CPU |
| **Twin API** reads (`/me/twin`, `/me/plan`, `/me/moments`, `/experience/*`) | **p95 ≤ 150 ms, p99 ≤ 400 ms** server-side. **99.9% monthly** availability | 1 key-value read (tens of ms regionally) + 0.4 ms twin logic (measured). If the store is unavailable, serve the generic page and never a stale page for another purpose |
| Customer correction | Effective on the next read (< 1 s) | Already implemented (`twin/feedback.py`) |
| **Forget** | Serving store ≤ 1 h. Analytical copies ≤ 24 h. Backups ≤ their retention (see §5) | Forget journal plus propagation job, with an audited completion record |
| **Kate turn** | p95 ≤ 6 s. Each tool call ≤ 100 ms | 2 LLM calls dominate. Tools compute on the twin |
| Freshness | Facts ≤ 24 h old. Salary-dependent plan ≤ 1 min after the salary lands | Tier 1 / Tier 0 |

---

## 5. Scaling risks and mitigations

### 5.1 Payday hot spot: modelled from the synthetic data

| Observation (5,000 synthetic customers, 12 months) | Value |
|---|---|
| Customers with a salary | 60% (3,006 salary credits per month) |
| Income credits (salary + pension + benefit) by day of month | Day 1: 21% (pensions) · days 24–28: 58% · days 30–31: 12% |
| Largest single-day share of a month's salaries | **61%** (1,846 of ~3,006 on 2026-02-27) |
| Busiest day, all transactions | 9,481 vs 5,909 average = **1.60×** (the 2nd of the month) |

| At 2.3M customers | Value |
|---|---|
| Average Tier-0 load | 2.72M tx/day ≈ **31 events/s** |
| Peak day | ≈ 4.35M transactions. If 30% post in one batch hour, **≈ 360 events/s** |
| Salary credits on the peak payday | ≈ 842k. Posted over 2 h, that is **≈ 117/s**, with as many payday-push candidates |
| API: average / normal diurnal peak (3×) | ≈ 120 / 360 requests/s (base) |
| API on payday morning | 30% of pushed customers open within 30 min × 3 calls ≈ **+420 requests/s** on top of the diurnal peak |
| **Design point** | **1,000 requests/s API** and **1,000 events/s Tier 0** sustained. Bursts up to ~5,000 events/s are absorbed by the event-bus backlog |

At 10 ms CPU per request, 1,000 requests/s is ≈ 10 busy vCPUs, or ≈ 20 at 50% utilisation. That is small.
For the store, one Bigtable SSD node is documented at up to 17,000 reads/s or 14,000 writes/s for 1 KB rows ([Bigtable performance](https://docs.cloud.google.com/bigtable/docs/performance)).
Firestore scales automatically but recommends ramping new traffic by the 500/50/5 rule ([Firestore best practices](https://firebase.google.com/docs/firestore/best-practices)).

| Risk | Mitigation |
|---|---|
| **Payday spike** (25th to last working day, plus the 1st for pensions) | The event bus buffers bursts, so Tier 0 degrades to "minutes late", never "lost". Autoscaling runs with a max-instance cap, and min instances are **pre-warmed on known paydays**: the twin knows every customer's payday, so the platform can forecast its own peak. Push fan-out is rate-limited with jitter over 30–60 min and respects quiet hours |
| **Hot keys / hot partitions** | Key everything by a **pseudonymous hashed customer key**, never by sequential ids or dates. Firestore explicitly warns against monotonically increasing document ids, and Bigtable needs evenly spread row keys. This also pseudonymises the store. Per-customer ordering comes from the Pub/Sub ordering key |
| **Backfill I/O** (1.07B rows, 116 GB) | Don't load the whole population into one frame: `twin.engine.load()` needs ≈ 1.9 GB for 5k customers, which projects to ≈ 880 GB at 2.3M. Part 1's runner (`twin/backfill.py`) already builds partition by partition with constant memory per worker, exactly-once and resumable. In the cloud: read partitions in parallel via the BigQuery Storage Read API or a Parquet export. Key the *store* by a hashed customer key even if partitions are id ranges. Writes are idempotent (key = customer + `rules_version`), checkpointed per partition and throttled to the store ramp |
| **Reprocessing** (new rules, bug fix, late or reversed transactions) | Version every twin with `rules_version`. Rebuild into a new version (blue/green), shadow-diff it against the current one (facts gained/lost per rule) and switch with a flag. **Never overwrite customer-confirmed facts or suppressions**, which live in customer memory. Tier 0 is idempotent on `tx_id`. A full rebuild costs ≈ $5 and ≈ 30 min, so rebuilding from scratch is cheap |
| **Schema evolution of facts** | Keep the fact contract (`value, confidence, since, evidence, implies`) plus `schema_version` in a registry with compatibility checks in CI. Changes are additive only and consumers ignore unknown fields. A renamed fact gets a new key plus a deprecation window. One contract test suite covers every channel, since app, web, advisor and Kate read the same JSON. Evidence needs **stable core-banking transaction ids** |
| **Multi-region / DR** | Start regional (europe-west1, multi-zone). The derived twin is rebuildable, so DR = redeploy in a second EU region (e.g. europe-west4) and rebuild in ≈ 1 h from the warehouse replica. **Customer memory needs a cross-region replica** (RPO minutes). Firestore `eur3` is an option at ~1.8× the operation price. Active-active is not needed for a help-first, fail-open service |
| **Tail customers** (self-employed, very long or large histories) | Cap per-customer build time and history. Alert on p99 build time. Hash buckets avoid skew |
| **Noisy neighbour** (the Tier 1 write burst vs serving reads) | Throttle batch writes. Write the new version, then flip a pointer. Schedule outside peak app hours |
| **Cost of LLM vs rules** | Keep inference in rules (§3.6: ~36,000× cheaper). The LLM does language only. Cap the compact twin at ~500 tokens. Use prompt caching, a smaller model for simple intents, and per-customer rate limits (already in the API). Budget alerts are labelled per tier |

---

## 6. Security and compliance at scale

| Area | Control |
|---|---|
| **Data residency (EU)** | All resources in europe-west1, or EU multi-regions (BigQuery `EU`, Firestore `eur3`), enforced by the organisation-policy resource-location constraint (optionally Assured Workloads for an EU boundary). The LLM endpoint must be EU-resident under KBC's data processing agreement. Send the compact twin only: no raw transactions, and **drop the name and city from the prompt** (today `compact_twin()` includes first name, age and city) |
| **Encryption** | TLS in transit. At rest: Google default encryption, plus **CMEK via Cloud KMS** (optionally HSM or external key management) where the service supports it (Firestore, BigQuery, Pub/Sub, Bigtable, Cloud SQL, Cloud Run). Evidence holds transaction *ids*, not merchant text. Logs never contain twin content or transaction descriptions |
| **Least privilege** | One service account per component, using workload identity (no exported keys):<br>• `ingest`: publish only<br>• `tier0`: subscribe + read/write tier-0 state<br>• `batch`: read the transactions dataset + write twins<br>• `api`: read twins + append to feedback, consent and audit<br>• `ops`: aggregates plus audited drill-down<br>No human write access to production data. A **VPC Service Controls** perimeter around the twin projects. IAM deny policies block the fraud project |
| **Audit** | Cloud Audit Logs: admin activity always on, data-access logs on for BigQuery, Firestore and Cloud SQL. **Business audit log**, append-only (the production form of `ops_audit`), records who saw which customer, for which purpose, under which consent state. It also records consent changes, fact corrections, pushes sent and Kate tool calls. Retention follows KBC policy, with restricted access |
| **Retention and deletion ("forget")** | Two semantics:<br>(a) **Forget this fact** → a suppression entry in customer memory (so the nightly rules cannot re-infer it), removal from the serving twin at once, and DML delete from versions and facts within 24 h.<br>(b) **Delete my twin / withdraw consent** → Tier 0 filters the customer out at ingress, and the twin, versions, facts and chat memory are deleted. Only the consent-withdrawal record is kept as proof.<br>**Backups:** Firestore backups expire after their retention (e.g. 14 days). BigQuery keeps deleted data for a time-travel window (2–7 days, configurable) plus **7 days of fail-safe** that cannot be queried ([BigQuery time travel](https://docs.cloud.google.com/bigquery/docs/time-travel)). The privacy notice must state this maximum. **After any restore, replay the forget journal** before serving traffic. Rolling 13-month evidence window. Snapshots kept 30 days. Facts carry an expiry |
| **Purpose limitation per consent flag** | The Financial Understanding Contract is enforced **in code at three points**: ingestion (don't process), batch (don't compute commercial ranking) and API (the policy gate filters blocks by purpose). The flags, mapped to KBC's existing consents ([research](../research/kbc_retail_insurance.md)):<br>• `financial_context`<br>• `proactive_help` ↔ "Extra convenience" / *Extra gebruiksgemak*, which proactive Kate requires today<br>• `commercial_personalisation` ↔ "Personalised" / *Op jouw maat*, which offers require today<br>• `external_accounts` (PSD2)<br>• `kate_memory`<br>• `advisor_view`<br>Ops aggregates are counts with a minimum cell size. Kill-switch feature flags per fact type, topic and channel |
| **No special-category inference** | A **deny-list at ingestion** masks health/medical, pharmacy, religious, political, trade-union and similar merchant categories to "other" *before* the twin sees them. The synthetic data has a `health` category (8% of transactions); the prototype engine does not read it, and production should drop it at the edge. The **fact allow-list** is enforced in CI (no fact key outside the registry). Household changes are customer-confirmed, not inferred. Kate memory stores only customer-confirmed goals. Keep the twin out of creditworthiness and life/health-insurance pricing, which are high-risk uses under the EU AI Act, and out of GDPR Art. 22 automated decisions |
| **Fraud firewall** | The security baseline runs in a **separate project and perimeter**. It has its own subscription to the raw booking feed and its own service accounts. There is **no IAM path** between it and the twin store or customer memory, in either direction. Fraud or risk outputs never become twin facts or marketing inputs. KBC already runs a fraud engine that scans > 2.5M payments a day against 150+ signals ([research](../research/kbc_retail_insurance.md)); the twin neither replaces nor feeds it |
| **Secrets** | `TWIN_SECRET`, the LLM key and database credentials live only in Secret Manager, injected at runtime. No `VITE_*` secrets, as already required by [`DATABASE_HANDOFF.md`](../DATABASE_HANDOFF.md) |

---

## 7. Verdict

Serving the digital twin to KBC's ~2.3M customers is an **integration and governance problem, not a scale or cost problem**.

- **The workload is small.** The whole population's twins fit in ≈ 14 GiB. A complete rebuild is ≈ 22 vCPU-hours, ≈ $5 and ≈ 30 minutes.
- **Infrastructure is cheap.** Streaming, nightly updates, storage and a horizontally scaled API cost ≈ $1.7k/month in the base case,
  including non-production environments. That is < $0.01 per customer per year.
- **The one cost that matters is Kate's LLM.** It grows with conversations, not with customers. The twin adds only ≈ $0.004 of tokens per turn.
  The rules-not-LLM design keeps inference ~36,000× cheaper than an LLM approach.
- **The real risks are elsewhere:** end-to-end latency from the core-banking feed, the payday burst, correct propagation of consent and forget,
  and rule quality on real, noisy data.

**Recommendation: proceed to a pilot.** The provisional numbers could be 10× worse and would not change this conclusion.

### What we'd validate in a pilot

1. **Real data shape:** transactions per customer per day, history length, twin size, and households/joint accounts (inputs 9–10).
2. **Build performance on the target platform:** p50/p95/p99 `t_build`, the overhead factor `k`, and memory per task, measured by part 1.
3. **Incremental ratios:** the real signal-bearing share `s`, Tier-0 CPU per event, and the Tier-2 refresh share, measured by part 2 on real feeds.
4. **Tier-0 end-to-end latency** from the core-banking booking to the push request, including the feed's own latency, with a canary salary every 5 min.
5. **Payday burst profile** at per-minute resolution from KBC's actual posting batches, plus a load test at **1,000 requests/s** and 1,000 events/s. Compare Firestore and Bigtable p95/p99.
6. **Forget drill:** end to end across the serving store, analytical copies, logs and backups, with the DPO, as part of the DPIA.
7. **Consent-gate and firewall tests:** automated proof that no read path exists without the flag, and no IAM path exists between the fraud and twin projects.
8. **Kate economics:** real tokens per turn, the incremental cost of the twin context, answer quality on GPT-4.1 vs mini, and an EU-resident endpoint.
9. **Cost telemetry:** resource labels per tier, then compare actual $ per customer per month against this model every month.
10. **Customer value gates** from [`PRIVATE_BANKER_AT_SCALE.md`](../PRIVATE_BANKER_AT_SCALE.md): confirmation/correction rates, opt-outs and complaints, before any commercial journey scales.

---

### Sources

- Google Cloud pricing pages, europe-west1 tables unless noted, seen **2026-09-30**:
  - [Cloud Run](https://cloud.google.com/run/pricing) · [Dataflow](https://cloud.google.com/dataflow/pricing) · [Pub/Sub](https://cloud.google.com/pubsub/pricing) · [BigQuery](https://cloud.google.com/bigquery/pricing)
  - [Firestore](https://cloud.google.com/firestore/pricing) · [Bigtable](https://cloud.google.com/bigtable/pricing) · [Cloud SQL](https://cloud.google.com/sql/pricing) · [Compute Engine general-purpose](https://cloud.google.com/products/compute/pricing/general-purpose)
  - [Cloud Logging](https://cloud.google.com/stackdriver/pricing) · [Secret Manager](https://cloud.google.com/secret-manager/pricing) · [Cloud KMS](https://cloud.google.com/kms/pricing) · [Network](https://cloud.google.com/vpc/network-pricing)
  - Spot price (third party): [gcloud-compute.com n2-standard-8](https://gcloud-compute.com/n2-standard-8.html)
- Google Cloud docs, seen 2026-09-30: [Bigtable performance](https://docs.cloud.google.com/bigtable/docs/performance) · [Firestore best practices (500/50/5, hotspots)](https://firebase.google.com/docs/firestore/best-practices) · [BigQuery time travel and fail-safe](https://docs.cloud.google.com/bigquery/docs/time-travel)
- LLM prices and tokens per Kate turn: [`PITCH.md`](../PITCH.md) §5 (OpenAI pricing seen 2026-09-30).
- KBC facts (Kate on GPT-4.1, consent gates, KBC Mobile users, > 2.5M payments/day fraud-screened): [`KBC_VALUE_MATRIX.md`](../KBC_VALUE_MATRIX.md), [`research/kbc_retail_insurance.md`](../research/kbc_retail_insurance.md) and the sources cited there.
- Local measurements: read-only queries on `data/kbc_twin.db` (synthetic, 5,000 customers), 2026-09-30.
