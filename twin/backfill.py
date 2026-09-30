"""Partitioned, parallel backfill: the one-off INITIAL BUILD of every customer's digital twin.

Scalability study, part 1 (method and measurements: docs/scalability/backfill.md). Part 2, the daily
update, is separate.

`python -m twin.engine` loads *all* transactions into one pandas frame (≈ 1.9 GB for 5,000
customers), which cannot reach KBC's 2.3M customers. This runner keeps memory per worker constant:

  1. plan   stream the customers primary key once and cut it into partitions of
            `--partition-size` consecutive customer_ids (memory: one (lo, hi) pair per partition);
  2. build  each of `--workers` processes takes one partition at a time, loads ONLY that
            partition's rows (the same columns and order as `twin.engine.load`, plus a customer_id
            range and a history cut-off), and builds every twin with `twin.engine.Twin(...).build()`;
  3. write  twin_profile / twin_facts rows go to the TARGET database in one transaction per
            partition, together with a `backfill_partitions` row. A partition is therefore written
            completely or not at all, and `--resume` continues a crashed run without gaps or
            duplicates. Per-customer failures go to `backfill_errors` instead of killing the run.

The source is opened read-only and the target must be a different file. twin_profile / twin_facts
use `twin.engine.TWIN_SCHEMA`, so the API can read the target like the demo database. Indexes are
created after the bulk load.

History cut-off (`--history-months`, default 12 → only rows booked on/after 2025-10-01 are read).
The engine is written for exactly one year of data, [WINDOW_START, AS_OF]:
  * 90-day windows (spending, days in the red, groceries) need 3 months, monthly bills 2-3 months,
    quarterly bills (interval > 80 days) about 6 months;
  * yearly bills (YEARLY_SUBS, "annual premium") are seen once a year, so they need 12 months;
  * `_since` treats "first seen within 45 days of WINDOW_START" as "before 2025-10-01", and yearly
    totals (maintenance, vet, road tax, "flight bookings this year", fuel per month normalised from
    max(first, WINDOW_START)) assume the data starts at WINDOW_START.
Reading MORE than 12 months is not a free safety margin with this engine: a yearly bill paid twice
inside the window is kept at its OLDEST date (next_date in the past), a yearly insurance premium paid
in two different months passes the 2-month test and is filed as "quarterly", and yearly sums double.
So 12 months is both the minimum and the maximum; 0 reads all history (what `build_one` does).

Usage:
    python -m twin.backfill --db SOURCE.db --out TARGET.db                      # all cores, 2,000 per partition
    python -m twin.backfill --db SOURCE.db --out TARGET.db --workers 4 --partition-size 500
    python -m twin.backfill --db SOURCE.db --out TARGET.db --resume             # continue a crashed run
    python -m twin.backfill --db SOURCE.db --out TARGET.db --verify 200         # + compare 200 twins with build_one
    python -m twin.backfill --db SOURCE.db --out TARGET.db --limit 5000 --report metrics.json
"""
import argparse
import json
import multiprocessing as mp
import os
import random
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd

try:
    import resource  # Unix only; peak RSS per worker
except ImportError:  # pragma: no cover
    resource = None

from twin.engine import AS_OF, DB, TWIN_SCHEMA, Twin, build_one

DEFAULT_HISTORY_MONTHS = 12
DEFAULT_PARTITION_SIZE = 2000

# twin.engine.load's transaction query, restricted to one customer_id range and a history cut-off.
# idx_tx_customer_date(customer_id, booked_at) serves both the range and the ORDER BY.
TX_SQL = """SELECT t.tx_id, t.customer_id, t.booked_at, t.amount, t.counterparty, t.description, t.category,
       t.subcategory, t.channel, t.balance_after, a.type AS acc_type
FROM transactions t JOIN accounts a USING(account_id)
WHERE t.customer_id BETWEEN ? AND ?{cut}
ORDER BY t.customer_id, t.booked_at, t.tx_id"""

BACKFILL_SCHEMA = """
DROP TABLE IF EXISTS backfill_meta;
DROP TABLE IF EXISTS backfill_partitions;
DROP TABLE IF EXISTS backfill_errors;
CREATE TABLE backfill_meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE backfill_partitions (part INTEGER PRIMARY KEY, lo INTEGER, hi INTEGER, customers INTEGER, twins INTEGER,
                                  errors INTEGER, tx_rows INTEGER, load_s REAL, build_s REAL, serialize_s REAL,
                                  rss_mb REAL, pid INTEGER, finished_at TEXT);
CREATE TABLE backfill_errors (customer_id INTEGER, part INTEGER, error TEXT);
"""
# Resuming requires the same plan and cut-off, otherwise partition numbers would mean something else.
RESUME_KEYS = ("partition_size", "history_months", "limit")
INDEX_SQL = [s.strip() for s in TWIN_SCHEMA.split(";") if s.strip().upper().startswith("CREATE INDEX")]


# ---------------------------------------------------------------------- helpers

def history_cutoff(months):
    """First booking date to read: AS_OF minus `months` months plus one day (12 -> WINDOW_START). 0/None = all."""
    if not months:
        return None
    return (AS_OF - pd.DateOffset(months=int(months)) + pd.Timedelta(days=1)).date().isoformat()


def connect_ro(path):
    con = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    con.execute("PRAGMA query_only = 1")
    return con


def _peak_rss_mb():
    if resource is None:  # pragma: no cover
        return float("nan")
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / 1e6 if sys.platform == "darwin" else rss * 1024 / 1e6  # bytes on macOS, KiB on Linux


def fact_rows(cid, twin):
    """twin_facts rows exactly as `twin.engine.main` writes them."""
    return [(cid, f["key"], json.dumps(f["value"], default=str), f["confidence"], f["since"], f["summary"],
             json.dumps(f["evidence"])) for f in twin["facts"].values()]


def profile_json(twin):
    """twin_profile.profile_json exactly as `twin.engine.main` writes it."""
    return json.dumps(twin, ensure_ascii=False, default=str)


def has_index_on(con, table, column):
    """True when `table` has an index whose first column is `column` (or it is the INTEGER PRIMARY KEY)."""
    for _, name, *_ in con.execute(f"PRAGMA index_list({table})"):
        if con.execute(f"PRAGMA index_info({name})").fetchone()[2] == column:
            return True
    return any(r[1] == column and r[5] == 1 and r[2].upper() == "INTEGER" for r in con.execute(f"PRAGMA table_info({table})"))


def plan_partitions(con, size, limit=None):
    """[(part, lo, hi, n)] with exactly `size` customers each (the last one may be smaller).

    Ranges are cut on the actual ids, so sparse ids are fine and every customer lands in exactly one
    partition. Streams the primary key: memory is one tuple per partition, not per customer."""
    if size < 1:
        raise ValueError("partition size must be at least 1")
    sql, args = "SELECT customer_id FROM customers ORDER BY customer_id", ()
    if limit:
        sql, args = sql + " LIMIT ?", (int(limit),)
    parts, lo, prev, n = [], None, None, 0
    for (cid,) in con.execute(sql, args):
        lo = cid if lo is None else lo
        prev, n = cid, n + 1
        if n == size:
            parts.append((len(parts), lo, cid, n))
            lo, n = None, 0
    if n:
        parts.append((len(parts), lo, prev, n))
    return parts


def load_partition(con, lo, hi, cutoff=None):
    """`twin.engine.load` for one customer_id range: only this partition's rows ever reach pandas."""
    cut, args = (" AND t.booked_at >= ?", (lo, hi, cutoff)) if cutoff else ("", (lo, hi))
    tx = pd.read_sql(TX_SQL.format(cut=cut), con, params=args, parse_dates=["booked_at"])
    rng = (lo, hi)
    cust = pd.read_sql("SELECT * FROM customers WHERE customer_id BETWEEN ? AND ? ORDER BY customer_id", con, params=rng)
    prods = pd.read_sql("SELECT customer_id, product_code FROM products WHERE customer_id BETWEEN ? AND ?", con, params=rng)
    accs = pd.read_sql("SELECT customer_id, type, balance FROM accounts WHERE customer_id BETWEEN ? AND ?", con, params=rng)
    return tx, cust, prods, accs


def group_partition(tx, prods, accs):
    """Per-customer lookups, exactly like `twin.engine.build_twins`."""
    prods_by = prods.groupby("customer_id").product_code.apply(list).to_dict()
    accs_by = {cid: dict(zip(g.type, g.balance)) for cid, g in accs.groupby("customer_id")}
    tx_by = dict(tuple(tx.groupby("customer_id")))
    return tx_by, prods_by, accs_by, tx.iloc[0:0]


def build_customer(c, tx_by, prods_by, accs_by, empty):
    """(customer_id, twin, None), or (customer_id, None, error): one odd customer must not stop a 2.3M run."""
    try:
        return int(c.customer_id), Twin(c, tx_by.get(c.customer_id, empty), prods_by.get(c.customer_id, []),
                                        accs_by.get(c.customer_id, {})).build(), None
    except Exception as exc:
        return int(c.customer_id), None, f"{type(exc).__name__}: {exc}"[:500]


# ---------------------------------------------------------------------- worker

_W = {}


def _init_worker(source, out, cutoff, built_at):
    _W.update(src=connect_ro(source), cutoff=cutoff, built_at=built_at)
    dst = sqlite3.connect(out, timeout=600, isolation_level=None)  # explicit BEGIN/COMMIT below
    dst.execute("PRAGMA synchronous = NORMAL")  # WAL + NORMAL: safe; a lost last partition is redone by --resume
    _W["dst"] = dst


def _close_worker():
    for key in ("src", "dst"):
        con = _W.pop(key, None)
        if con is not None:
            con.close()


def run_partition(part):
    """Load, build, serialise and write one partition. Returns timings (small: nothing big crosses processes)."""
    idx, lo, hi, n = part
    src, dst, cutoff, built_at = _W["src"], _W["dst"], _W["cutoff"], _W["built_at"]
    t0, cpu0 = time.perf_counter(), time.process_time()
    tx, cust, prods, accs = load_partition(src, lo, hi, cutoff)
    groups = group_partition(tx, prods, accs)
    n_tx = len(tx)
    t_load = time.perf_counter() - t0  # SQL -> pandas + per-customer grouping ("load + prepare")

    profiles, facts, errors, t_build, t_ser, json_bytes = [], [], [], 0.0, 0.0, 0
    for c in cust.itertuples():
        a = time.perf_counter()
        cid, twin, err = build_customer(c, *groups)
        b = time.perf_counter()
        t_build += b - a
        if err:
            errors.append((cid, idx, err))
            continue
        doc = profile_json(twin)
        profiles.append((cid, doc, built_at))
        facts.extend(fact_rows(cid, twin))
        json_bytes += len(doc.encode())
        t_ser += time.perf_counter() - b
    del tx, cust, prods, accs, groups  # free the partition's frames before writing
    rss = _peak_rss_mb()

    t2 = time.perf_counter()
    dst.execute("BEGIN IMMEDIATE")  # waits here while another worker holds the single SQLite write lock
    t3 = time.perf_counter()
    try:
        dst.executemany("INSERT INTO twin_profile VALUES (?,?,?)", profiles)
        dst.executemany("INSERT INTO twin_facts VALUES (?,?,?,?,?,?,?)", facts)
        dst.executemany("INSERT INTO backfill_errors VALUES (?,?,?)", errors)
        dst.execute("INSERT INTO backfill_partitions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (idx, lo, hi, n, len(profiles), len(errors), n_tx, t_load, t_build, t_ser, rss, os.getpid(),
                     pd.Timestamp.now().isoformat(timespec="seconds")))
        dst.execute("COMMIT")
    except BaseException:
        dst.execute("ROLLBACK")
        raise
    t4 = time.perf_counter()
    return dict(part=idx, lo=lo, hi=hi, customers=n, twins=len(profiles), errors=len(errors), tx_rows=n_tx,
                facts=len(facts), json_bytes=json_bytes, load_s=t_load, build_s=t_build, serialize_s=t_ser,
                lock_wait_s=t3 - t2, write_s=t4 - t3, busy_s=t4 - t0, cpu_s=time.process_time() - cpu0,
                rss_mb=rss, pid=os.getpid())


# ---------------------------------------------------------------------- orchestration

def _prepare_target(out, config, resume):
    """Create (or, with resume, reopen) the target twin store. Returns (done partition ids, built_at)."""
    con = sqlite3.connect(out, timeout=600)
    try:
        con.execute("PRAGMA journal_mode = WAL")  # readers never block the writer; workers queue on BEGIN IMMEDIATE
        has_meta = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='backfill_meta'").fetchone()
        if resume and has_meta:
            stored = dict(con.execute("SELECT key, value FROM backfill_meta"))
            for key in RESUME_KEYS:
                if stored.get(key) != str(config[key]):
                    raise SystemExit(f"--resume: {key} was {stored.get(key)} in the stored run, now {config[key]}; "
                                     "rerun without --resume to start over")
            done = {r[0] for r in con.execute("SELECT part FROM backfill_partitions")}
            return done, stored["built_at"]
        con.executescript(TWIN_SCHEMA)                   # the engine's own twin tables (drop + create)
        for stmt in INDEX_SQL:                           # bulk load first, index once at the end
            con.execute("DROP INDEX IF EXISTS " + stmt.split()[2])
        con.executescript(BACKFILL_SCHEMA)
        con.executemany("INSERT INTO backfill_meta VALUES (?,?)", [(k, str(v)) for k, v in config.items()])
        con.commit()
        return set(), config["built_at"]
    finally:
        con.close()


def _finalize_target(out):
    con = sqlite3.connect(out, timeout=600)
    try:
        for stmt in INDEX_SQL:
            con.execute(stmt.replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS", 1))
        con.commit()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        con.close()


def backfill(source, out, workers=None, partition_size=DEFAULT_PARTITION_SIZE, history_months=DEFAULT_HISTORY_MONTHS,
             limit=None, resume=False, progress=None):
    """Build every twin of `source` into `out`. Returns a metrics dict (see `summarize`)."""
    source, out = Path(source).resolve(), Path(out).resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    if out == source or (out.exists() and os.path.samefile(out, source)):
        raise ValueError("the target must be a different file than the source (use `python -m twin.engine` to build in place)")
    workers = max(1, int(workers or os.cpu_count() or 1))
    cutoff = history_cutoff(history_months)
    t_start = time.perf_counter()

    con = connect_ro(source)
    try:
        parts = plan_partitions(con, partition_size, limit)
        # Without it the per-partition accounts query is a full scan: O(customers) per partition, O(N^2 / P) in
        # total. Small here (≈ 6 ms per partition at 100K customers), but production reads must be clustered.
        accounts_index = has_index_on(con, "accounts", "customer_id")
    finally:
        con.close()
    t_plan = time.perf_counter() - t_start
    config = dict(source=str(source), partition_size=partition_size, history_months=history_months or 0,
                  cutoff=cutoff or "", limit=limit or 0, as_of=AS_OF.date().isoformat(),
                  built_at=pd.Timestamp.now().isoformat(timespec="seconds"))
    done, built_at = _prepare_target(out, config, resume)
    todo = [p for p in parts if p[0] not in done]

    results, t_pool = [], time.perf_counter()
    init = (str(source), str(out), cutoff, built_at)
    processes = 1 if workers == 1 else max(1, min(workers, len(todo)))
    if workers == 1:  # in-process: the purest single-core measurement, no spawn / IPC
        _init_worker(*init)
        try:
            for p in todo:
                results.append(run_partition(p))
                if progress:
                    progress(results, len(todo), time.perf_counter() - t_pool)
        finally:
            _close_worker()
    elif todo:
        # spawn (not fork): no inherited SQLite handles or pandas thread state, identical on macOS and Linux
        with mp.get_context("spawn").Pool(processes, initializer=_init_worker, initargs=init) as pool:
            for r in pool.imap_unordered(run_partition, todo):
                results.append(r)
                if progress:
                    progress(results, len(todo), time.perf_counter() - t_pool)
    t_pool = time.perf_counter() - t_pool

    t0 = time.perf_counter()
    _finalize_target(out)
    t_final = time.perf_counter() - t0
    wall = time.perf_counter() - t_start
    return summarize(results, dict(source=str(source), out=str(out), workers=processes, workers_requested=workers,
                                   partition_size=partition_size,
                                   history_months=history_months or 0, cutoff=cutoff, limit=limit or 0,
                                   partitions=len(parts), skipped_partitions=len(parts) - len(todo),
                                   accounts_index=accounts_index,
                                   plan_s=t_plan, pool_s=t_pool, finalize_s=t_final, wall_s=wall,
                                   target_bytes=out.stat().st_size))


def summarize(results, run):
    """Aggregate per-partition timings into one report (worker-seconds per phase, per-twin costs, memory)."""
    tot = {k: sum(r[k] for r in results) for k in ("customers", "twins", "errors", "tx_rows", "facts", "json_bytes",
                                                   "load_s", "build_s", "serialize_s", "lock_wait_s", "write_s",
                                                   "busy_s", "cpu_s")}
    n = max(tot["twins"], 1)
    per_pid, per_worker = {}, {}
    for r in sorted(results, key=lambda r: r["part"]):
        per_pid.setdefault(r["pid"], []).append(r["rss_mb"])
        w = per_worker.setdefault(r["pid"], dict(partitions=0, twins=0, busy_s=0.0, cpu_s=0.0))
        w.update(partitions=w["partitions"] + 1, twins=w["twins"] + r["twins"], busy_s=w["busy_s"] + r["busy_s"],
                 cpu_s=w["cpu_s"] + r["cpu_s"])
    speeds = sorted(1000 * w["busy_s"] / w["twins"] for w in per_worker.values() if w["twins"])
    return dict(run, **tot,
                # worker time (wall clock inside the worker) per twin, by phase; total includes the lock wait
                ms_per_twin=dict(load=1000 * tot["load_s"] / n, build=1000 * tot["build_s"] / n,
                                 serialize=1000 * tot["serialize_s"] / n, write=1000 * tot["write_s"] / n,
                                 lock_wait=1000 * tot["lock_wait_s"] / n, total=1000 * tot["busy_s"] / n,
                                 cpu=1000 * tot["cpu_s"] / n),
                wall_s_per_twin=run["pool_s"] / n,
                twins_per_s=tot["twins"] / run["pool_s"] if run["pool_s"] else 0.0,
                twins_per_s_per_worker=tot["twins"] / run["pool_s"] / run["workers"] if run["pool_s"] else 0.0,
                tx_rows_per_s_load=tot["tx_rows"] / tot["load_s"] if tot["load_s"] else 0.0,
                avg_json_bytes=tot["json_bytes"] / n, facts_per_twin=tot["facts"] / n,
                rss_mb_peak=max((r["rss_mb"] for r in results), default=0.0),
                rss_mb_first_partition=max((v[0] for v in per_pid.values()), default=0.0),
                rss_mb_last_partition=max((v[-1] for v in per_pid.values()), default=0.0),
                worker_processes=len(per_pid),
                # cpu / busy < 1 means the workers waited for a core (other load, more workers than cores)
                cpu_per_busy=tot["cpu_s"] / tot["busy_s"] if tot["busy_s"] else 0.0,
                worker_ms_per_twin=dict(fastest=speeds[0], slowest=speeds[-1]) if speeds else {},
                per_worker=list(per_worker.values()))


# ---------------------------------------------------------------------- verification

def verify(source, out, sample=100, seed=0):
    """Compare stored twins with `twin.engine.build_one` on the source, byte for byte.

    twin_profile.built_at is the only volatile value and is not compared. build_one reads ALL history,
    so on a source with rows older than the backfill's cut-off a mismatch is expected (see module doc)."""
    src, dst = connect_ro(source), connect_ro(out)
    try:
        ids = [r[0] for r in dst.execute("SELECT customer_id FROM twin_profile ORDER BY customer_id")]
        pick = sorted(random.Random(seed).sample(ids, min(sample, len(ids)))) if sample else ids
        marks = ",".join("?" * len(pick))
        stored = dict(dst.execute(f"SELECT customer_id, profile_json FROM twin_profile WHERE customer_id IN ({marks})", pick))
        stored_facts = {}
        for row in dst.execute(f"SELECT * FROM twin_facts WHERE customer_id IN ({marks})", pick):
            stored_facts.setdefault(row[0], []).append(tuple(row))
        bad = []
        for cid in pick:
            twin = build_one(src, cid)
            if profile_json(twin) != stored.get(cid) or sorted(fact_rows(cid, twin)) != sorted(stored_facts.get(cid, [])):
                bad.append(cid)
        return dict(checked=len(pick), mismatches=bad)
    finally:
        src.close()
        dst.close()


# ---------------------------------------------------------------------- CLI

def _progress(results, total, elapsed):
    done = len(results)
    if done == total or done % max(1, total // 20) == 0:
        twins = sum(r["twins"] for r in results)
        eta = elapsed / done * (total - done)
        print(f"  {done:>5}/{total} partitions · {twins:,} twins · {twins / elapsed:,.0f} twins/s · ETA {eta:,.0f} s",
              file=sys.stderr, flush=True)


def print_report(m):
    ms = m["ms_per_twin"]
    print(f"Backfill {m['source']} -> {m['out']}")
    print(f"  {m['twins']:,} twins ({m['errors']} errors) from {m['tx_rows']:,} transactions"
          f" · cut-off {m['cutoff'] or 'none'} · {m['partitions']} partitions of {m['partition_size']:,}"
          + (f" ({m['skipped_partitions']} already done)" if m["skipped_partitions"] else "")
          + f" · {m['workers']} worker(s)")
    print(f"  wall {m['wall_s']:.1f} s (plan {m['plan_s']:.2f} · build {m['pool_s']:.1f} · index {m['finalize_s']:.2f})"
          f" → {m['twins_per_s']:,.0f} twins/s · {m['twins_per_s_per_worker']:,.1f} twins/s per worker"
          f" · {1000 * m['wall_s_per_twin']:.2f} ms wall per twin")
    print(f"  worker time per twin: load {ms['load']:.2f} · build {ms['build']:.2f} · serialise {ms['serialize']:.2f}"
          f" · write {ms['write']:.2f} (lock wait {ms['lock_wait']:.2f}) = {ms['total']:.2f} ms"
          f" · CPU {ms['cpu']:.2f} ms (CPU/busy {m['cpu_per_busy']:.2f})"
          + (f" · per worker {m['worker_ms_per_twin']['fastest']:.1f}-{m['worker_ms_per_twin']['slowest']:.1f} ms/twin"
             if m["worker_ms_per_twin"] else ""))
    if not m["accounts_index"]:
        print("  note: source has no index on accounts(customer_id): each partition scans the accounts table")
    print(f"  peak RSS per worker {m['rss_mb_peak']:,.0f} MB (after 1st partition {m['rss_mb_first_partition']:,.0f},"
          f" after last {m['rss_mb_last_partition']:,.0f}) · {m['avg_json_bytes'] / 1024:.1f} KB JSON and"
          f" {m['facts_per_twin']:.1f} facts per twin · target {m['target_bytes'] / 1e6:,.0f} MB")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(DB), help="source bank database, opened read-only (default: %(default)s)")
    ap.add_argument("--out", required=True, help="target twin store (must differ from --db); recreated unless --resume")
    ap.add_argument("--workers", type=int, default=os.cpu_count(), help="worker processes (default: all cores, %(default)s)")
    ap.add_argument("--partition-size", type=int, default=DEFAULT_PARTITION_SIZE, help="customers per partition")
    ap.add_argument("--history-months", type=int, default=DEFAULT_HISTORY_MONTHS,
                    help="read only the last N months up to AS_OF (default 12 = WINDOW_START; 0 = all history)")
    ap.add_argument("--limit", type=int, help="only the first N customers (benchmarks)")
    ap.add_argument("--resume", action="store_true", help="skip partitions a previous run already committed")
    ap.add_argument("--verify", type=int, default=0, metavar="N", help="then compare N random twins with twin.engine.build_one")
    ap.add_argument("--report", help="also write the metrics as JSON to this file")
    ap.add_argument("--quiet", action="store_true", help="no progress lines")
    a = ap.parse_args(argv)
    if a.partition_size < 1 or a.workers < 1 or a.history_months < 0:
        ap.error("--partition-size and --workers must be >= 1, --history-months >= 0")
    try:
        m = backfill(a.db, a.out, a.workers, a.partition_size, a.history_months, a.limit, a.resume,
                     None if a.quiet else _progress)
    except (ValueError, FileNotFoundError) as exc:
        ap.error(str(exc))
    print_report(m)
    if a.verify:
        t0 = time.perf_counter()
        m["verify"] = verify(a.db, a.out, a.verify)
        v = m["verify"]
        print(f"  verify: {v['checked'] - len(v['mismatches'])}/{v['checked']} twins identical to twin.engine.build_one"
              f" ({time.perf_counter() - t0:.1f} s)" + (f" · MISMATCH {v['mismatches'][:10]}" if v["mismatches"] else ""))
    if a.report:
        Path(a.report).write_text(json.dumps(m, indent=2))
    return 1 if m.get("verify", {}).get("mismatches") else 0


if __name__ == "__main__":
    sys.exit(main())
