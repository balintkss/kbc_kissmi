"""Backfill runner (twin/backfill.py): the partitioned, parallel initial build equals the engine's own build.

Every test runs on a 200-customer bank generated into tmp_path with a fixed seed; these tests never
open data/kbc_twin.db themselves (and never write to it).
"""
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from twin import backfill as bf
from twin.engine import WINDOW_START, build_one

ROOT = Path(__file__).resolve().parent.parent
N_CUSTOMERS, SEED = 200, 7


@pytest.fixture(scope="module")
def bank(tmp_path_factory):
    path = tmp_path_factory.mktemp("bank") / "bank.db"
    subprocess.run([sys.executable, str(ROOT / "data" / "generate_db.py"), "--customers", str(N_CUSTOMERS),
                    "--seed", str(SEED), "--out", str(path)], check=True, capture_output=True)
    return path


@pytest.fixture(scope="module")
def expected(bank):
    """The reference: twin.engine.build_one for every customer, sequentially, all history."""
    con = bf.connect_ro(bank)
    try:
        return {cid: build_one(con, cid) for (cid,) in con.execute("SELECT customer_id FROM customers").fetchall()}
    finally:
        con.close()


@pytest.fixture(scope="module")
def parallel(bank, tmp_path_factory):
    """Default backfill (12-month cut-off) with 2 worker processes and a partition size that does not divide 200."""
    out = tmp_path_factory.mktemp("twins") / "twins.db"
    return out, bf.backfill(bank, out, workers=2, partition_size=37)


def stored(out):
    con = bf.connect_ro(out)
    try:
        profiles = dict(con.execute("SELECT customer_id, profile_json FROM twin_profile"))
        facts = {}
        for row in con.execute("SELECT * FROM twin_facts"):
            facts.setdefault(row[0], []).append(tuple(row))
        return profiles, facts
    finally:
        con.close()


# ---------------------------------------------------------------------- partitioning

@pytest.mark.parametrize("size", [1, 3, 7, 25, 26, 100])
def test_partitions_cover_sparse_ids_exactly_once(size):
    ids = sorted([3, 4, 9, 10, 11, 50, 51, 52, 700, 701, 1_000_000, 1_000_003] + list(range(2000, 2014)))  # 26 sparse ids
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE customers (customer_id INTEGER PRIMARY KEY)")
    con.executemany("INSERT INTO customers VALUES (?)", [(i,) for i in reversed(ids)])
    parts = bf.plan_partitions(con, size)
    seen = []
    for number, (part, lo, hi, n) in enumerate(parts):
        inside = [i for i in ids if lo <= i <= hi]  # what the worker's BETWEEN lo AND hi will read
        assert part == number and len(inside) == n and inside[0] == lo and inside[-1] == hi
        seen += inside
    assert seen == ids  # every customer once, no overlap, no gap
    assert [p[3] for p in parts[:-1]] == [size] * (len(parts) - 1) and 1 <= parts[-1][3] <= size
    limited = bf.plan_partitions(con, size, limit=10)
    assert sum(p[3] for p in limited) == 10 and limited[-1][2] == ids[9]


def test_partitions_on_generated_bank(bank):
    con = bf.connect_ro(bank)
    try:
        parts = bf.plan_partitions(con, 37)
    finally:
        con.close()
    assert [p[3] for p in parts] == [37] * 5 + [15]
    assert parts[0][1] == 1 and parts[-1][2] == N_CUSTOMERS


# ---------------------------------------------------------------------- correctness

def test_parallel_backfill_equals_sequential_build_one(parallel, expected):
    out, m = parallel
    profiles, facts = stored(out)
    assert m["workers"] == 2 and m["partitions"] == 6 and m["twins"] == N_CUSTOMERS and m["errors"] == 0
    assert set(profiles) == set(expected)
    for cid, twin in expected.items():
        assert profiles[cid] == bf.profile_json(twin), f"twin {cid} differs from build_one"
        assert sorted(facts.get(cid, [])) == sorted(bf.fact_rows(cid, twin)), f"twin_facts of {cid} differ"


def test_every_customer_written_exactly_once(parallel, bank):
    out, m = parallel
    con = bf.connect_ro(out)
    try:
        n, distinct = con.execute("SELECT COUNT(*), COUNT(DISTINCT customer_id) FROM twin_profile").fetchone()
        parts = con.execute("SELECT lo, hi, customers, twins FROM backfill_partitions ORDER BY lo").fetchall()
        assert con.execute("SELECT COUNT(*) FROM backfill_errors").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'idx_twin_facts'").fetchone()[0] == 1
    finally:
        con.close()
    assert n == distinct == N_CUSTOMERS
    assert sum(p[2] for p in parts) == sum(p[3] for p in parts) == N_CUSTOMERS
    assert all(a[1] < b[0] for a, b in zip(parts, parts[1:]))  # ranges are disjoint
    assert m["facts"] == sum(len(v) for v in stored(out)[1].values())


def test_verify_matches_and_catches_a_tampered_twin(parallel, bank, tmp_path):
    out, _ = parallel
    assert bf.verify(bank, out, sample=50) == {"checked": 50, "mismatches": []}
    copy = tmp_path / "tampered.db"
    src = sqlite3.connect(out)
    dst = sqlite3.connect(copy)
    src.backup(dst)
    src.close()
    dst.execute("UPDATE twin_profile SET profile_json = replace(profile_json, '\"as_of\"', '\"as_off\"') WHERE customer_id = 5")
    dst.commit()
    dst.close()
    assert bf.verify(bank, copy, sample=0)["mismatches"] == [5]


# ---------------------------------------------------------------------- history cut-off

def test_twelve_months_is_exactly_the_engine_window(parallel, bank, tmp_path):
    """--history-months 12 reads from WINDOW_START on, i.e. everything the engine's rules are written for."""
    assert bf.history_cutoff(12) == WINDOW_START.date().isoformat()
    assert bf.history_cutoff(0) is None and bf.history_cutoff(None) is None
    out, m12 = parallel
    all_history = bf.backfill(bank, tmp_path / "all.db", workers=1, partition_size=64, history_months=0)
    con = bf.connect_ro(bank)
    try:
        assert m12["tx_rows"] == all_history["tx_rows"] == con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    finally:
        con.close()
    assert stored(out) == stored(tmp_path / "all.db")  # the cut changes no fact, no bill, no plan


def test_a_shorter_history_only_drops_older_rows_and_changes_twins(bank, expected, tmp_path):
    """Documents why the default is 12: with 3 months, yearly bills and 'since' dates are lost."""
    m = bf.backfill(bank, tmp_path / "short.db", workers=1, partition_size=20, history_months=3, limit=40)
    cutoff = bf.history_cutoff(3)
    profiles, facts = stored(tmp_path / "short.db")
    con = bf.connect_ro(bank)
    try:
        booked = dict(con.execute("SELECT tx_id, booked_at FROM transactions WHERE customer_id <= 40"))
    finally:
        con.close()
    assert m["twins"] == 40 and 0 < m["tx_rows"] < len(booked)
    evidence = [tx for rows in facts.values() for row in rows for tx in bf.json.loads(row[6])]
    assert evidence and all(booked[tx] >= cutoff for tx in evidence)
    changed = [cid for cid, doc in profiles.items() if doc != bf.profile_json(expected[cid])]
    assert changed  # so the cut-off is a real knob, not a no-op


# ---------------------------------------------------------------------- resume & safety

def test_resume_skips_committed_partitions_and_redoes_a_lost_one(bank, expected, tmp_path):
    out = tmp_path / "resume.db"
    first = bf.backfill(bank, out, workers=1, partition_size=25, limit=75)
    assert first["partitions"] == 3 and first["twins"] == 75
    again = bf.backfill(bank, out, workers=1, partition_size=25, limit=75, resume=True)
    assert again["skipped_partitions"] == 3 and again["twins"] == 0
    con = sqlite3.connect(out)  # simulate a crash that lost partition 1 (customers 26-50)
    con.execute("DELETE FROM twin_profile WHERE customer_id BETWEEN 26 AND 50")
    con.execute("DELETE FROM twin_facts WHERE customer_id BETWEEN 26 AND 50")
    con.execute("DELETE FROM backfill_partitions WHERE part = 1")
    con.commit()
    con.close()
    redo = bf.backfill(bank, out, workers=2, partition_size=25, limit=75, resume=True)
    assert redo["skipped_partitions"] == 2 and redo["twins"] == 25
    profiles, _ = stored(out)
    assert sorted(profiles) == list(range(1, 76))
    assert all(profiles[cid] == bf.profile_json(expected[cid]) for cid in profiles)
    with pytest.raises(SystemExit, match="partition_size"):
        bf.backfill(bank, out, workers=1, partition_size=30, limit=75, resume=True)


def test_refuses_to_write_into_the_source(bank):
    with pytest.raises(ValueError, match="different file"):
        bf.backfill(bank, bank, workers=1)
    with pytest.raises(ValueError, match="different file"):
        bf.backfill(bank, Path(str(bank).replace("bank.db", "./bank.db")), workers=1)


def test_uses_an_accounts_index_when_the_source_has_one(bank, expected, tmp_path):
    """The generator has no accounts(customer_id) index (each partition then scans accounts); with one, same twins."""
    indexed = tmp_path / "indexed.db"
    src, dst = bf.connect_ro(bank), sqlite3.connect(indexed)
    src.backup(dst)
    src.close()
    assert not bf.has_index_on(dst, "accounts", "customer_id") and bf.has_index_on(dst, "customers", "customer_id")
    dst.execute("CREATE INDEX idx_accounts_customer ON accounts(customer_id)")
    dst.commit()
    plan = dst.execute("EXPLAIN QUERY PLAN SELECT customer_id, type, balance FROM accounts WHERE customer_id BETWEEN ? AND ?",
                       (1, 2)).fetchone()[-1]
    dst.close()
    assert plan.startswith("SEARCH")
    m = bf.backfill(indexed, tmp_path / "twins.db", workers=1, partition_size=20, limit=50)
    profiles, _ = stored(tmp_path / "twins.db")
    assert m["accounts_index"] is True and sorted(profiles) == list(range(1, 51))
    assert all(doc == bf.profile_json(expected[cid]) for cid, doc in profiles.items())
