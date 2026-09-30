"""Benchmark the twin engine without touching the database.

Times the same work as `twin.engine.build_twins` (load -> group per customer -> Twin(...).build()),
plus JSON serialisation and the recommender (`moments` + `page` for every topic), and projects the
result to KBC's 2.3M customers.

The DB is opened read-only: nothing is written, so it is safe to run next to the API.

Usage:  python -m twin.benchmark            # 1,000 twins
        python -m twin.benchmark --n 5000   # the whole synthetic population
"""
import argparse
import json
import os
import platform
import sqlite3
import statistics
import sys
import time

import pandas as pd

try:
    import resource  # Unix only; used for peak memory
except ImportError:  # pragma: no cover
    resource = None

from twin.catalog import CATALOG
from twin.engine import DB, Twin, load
from twin.recommender import moments, page

KBC_CUSTOMERS = 2_300_000
CORES = (1, 8, 32)


def _fmt_duration(seconds):
    if seconds < 120:
        return f"{seconds:,.1f} s"
    if seconds < 7200:
        return f"{seconds / 60:,.1f} min"
    return f"{seconds / 3600:,.1f} h"


def _pct(values, q):
    return statistics.quantiles(values, n=100)[q - 1] if len(values) >= 2 else values[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=1000, help="number of twins to build (default 1000)")
    ap.add_argument("--db", default=str(DB))
    a = ap.parse_args()
    if a.n < 1:
        ap.error("--n must be at least 1")

    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)  # read-only: never writes twin tables

    # 1. load: the same query as build_twins (all customers, all transactions)
    t0 = time.perf_counter()
    tx, cust, prods, accs = load(con)
    t_load = time.perf_counter() - t0

    # 2. prepare: the same per-customer grouping as build_twins
    t0 = time.perf_counter()
    prods_by = prods.groupby("customer_id").product_code.apply(list).to_dict()
    accs_by = {cid: dict(zip(g.type, g.balance)) for cid, g in accs.groupby("customer_id")}
    tx_by = dict(tuple(tx.groupby("customer_id")))
    t_prep = time.perf_counter() - t0
    n_loaded = len(cust)

    # 3. build n twins through the same Twin(...).build() path, plus serialisation and the recommender
    rows = list(cust.itertuples())[: a.n]
    build_s, json_s, reco_s, twins = [], [], [], 0
    n_facts = 0
    for c in rows:
        t0 = time.perf_counter()
        twin = Twin(c, tx_by.get(c.customer_id, tx.iloc[0:0]), prods_by.get(c.customer_id, []),
                    accs_by.get(c.customer_id, {})).build()
        t1 = time.perf_counter()
        json.dumps(twin, ensure_ascii=False, default=str)  # what engine.main stores in twin_profile
        t2 = time.perf_counter()
        moments(twin)
        for topic in CATALOG:
            page(twin, topic)
        t3 = time.perf_counter()
        build_s.append(t1 - t0)
        json_s.append(t2 - t1)
        reco_s.append(t3 - t2)
        n_facts += len(twin["facts"])
        twins += 1
    con.close()

    t_build, t_json, t_reco = sum(build_s), sum(json_s), sum(reco_s)
    load_per_cust = (t_load + t_prep) / n_loaded
    build_per_twin = t_build / twins
    total_per_cust = load_per_cust + build_per_twin + t_json / twins
    # ru_maxrss is bytes on macOS, kilobytes on Linux
    peak_mb = (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024) / 1e6
               if resource else float("nan"))

    print("Twin engine benchmark (read-only)")
    print(f"  machine   {platform.machine()} · {os.cpu_count()} logical cores · Python {platform.python_version()} · pandas {pd.__version__}")
    print(f"  data      {n_loaded:,} customers · {len(tx):,} transactions (12 months)")
    print()
    print(f"  load      {t_load:6.2f} s   SQLite -> pandas, all {n_loaded:,} customers ({len(tx) / t_load:,.0f} tx/s)")
    print(f"  prepare   {t_prep:6.2f} s   group transactions / products / accounts per customer")
    print(f"  => load+prepare per customer: {load_per_cust * 1000:.2f} ms")
    print()
    print(f"  build     {t_build:6.2f} s   {twins:,} twins via Twin(...).build(), {n_facts / twins:.1f} facts/twin")
    print(f"            per twin: mean {build_per_twin * 1000:.1f} ms · median {statistics.median(build_s) * 1000:.1f} ms"
          f" · p95 {_pct(build_s, 95) * 1000:.1f} ms · max {max(build_s) * 1000:.1f} ms")
    print(f"  serialise {t_json:6.2f} s   json.dumps per twin: {t_json / twins * 1000:.2f} ms")
    print(f"  recommend {t_reco:6.2f} s   moments + page x {len(CATALOG)} topics per twin: {t_reco / twins * 1000:.2f} ms"
          f" ({twins / t_reco:,.0f} twins/s)")
    print(f"  peak RSS  ≈ {peak_mb:,.0f} MB (whole population held in memory)")
    print()
    print(f"  THROUGHPUT, one core: {1 / build_per_twin:,.0f} twins/s (build only) · {1 / total_per_cust:,.0f} twins/s end-to-end"
          f" (load + prepare + build + serialise = {total_per_cust * 1000:.1f} ms/customer)")
    print()
    print(f"  PROJECTION for {KBC_CUSTOMERS:,} customers — LINEAR extrapolation from this laptop, pandas, one process per core,")
    print("  assuming customers are independent (they are: one twin never reads another) and I/O keeps up:")
    for cores in CORES:
        print(f"    {cores:>2} core{'s' if cores > 1 else ' '}   {_fmt_duration(KBC_CUSTOMERS * total_per_cust / cores):>9}")
    print(f"  Recommender for {KBC_CUSTOMERS:,} customers on 1 core: {_fmt_duration(KBC_CUSTOMERS * t_reco / twins)}"
          " (and it runs per request anyway, in well under a millisecond per page)")
    print("  LLM calls needed to build a twin: 0.")


if __name__ == "__main__":
    main()
