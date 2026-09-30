"""Daily incremental update (twin/incremental.py) on a tiny generated database in tmp_path (no real DB needed).

  * replay: twins built as of 2026-09-26, four nightly updates, equal to a full rebuild as of 2026-09-30
  * the ledger's as-of view at AS_OF reproduces `twin.engine.build_twins` byte for byte (engine default unchanged)
  * tier classification, Tier 0 salary / large-debit events, idempotent persist that leaves overlays alone
"""
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from twin import incremental as inc
from twin.engine import AS_OF, build_twins
from twin.feedback import apply_feedback

ROOT = Path(__file__).resolve().parent.parent
START = pd.Timestamp("2026-09-26")


@pytest.fixture(scope="module")
def tiny_db(tmp_path_factory):
    out = tmp_path_factory.mktemp("incremental") / "tiny.db"
    subprocess.run([sys.executable, str(ROOT / "data" / "generate_db.py"), "--customers", "30", "--out", str(out)],
                   check=True, capture_output=True)
    return out


@pytest.fixture(scope="module")
def ledger(tiny_db):
    con = sqlite3.connect(f"file:{tiny_db}?mode=ro", uri=True)
    try:
        return inc.Ledger.from_db(con)
    finally:
        con.close()


@pytest.fixture(scope="module")
def replayed(ledger):
    twins, expiry, reasons = inc.initial_build(ledger, START)
    stats = [inc.nightly(ledger, twins, expiry, START + k * inc.DAY, reasons=reasons) for k in range(1, 5)]
    return twins, expiry, stats


def tx(**kw):
    base = dict(tx_id=1, customer_id=1, booked_at=pd.Timestamp("2026-09-25"), amount=-50.0, counterparty="Colruyt",
                description="", category="groceries", subcategory="supermarket", channel="card", balance_after=1000.0,
                acc_type="current")
    return SimpleNamespace(**{**base, **kw})


def test_ledger_as_of_today_matches_engine(tiny_db, ledger):
    con = sqlite3.connect(f"file:{tiny_db}?mode=ro", uri=True)
    engine = {t["customer_id"]: t for t in build_twins(con)}
    con.close()
    for cid, twin in engine.items():
        mine, _ = inc.rebuild(ledger, cid, AS_OF)
        assert json.dumps(mine, default=str) == json.dumps(twin, default=str), cid


def test_replay_equals_full_rebuild(ledger, replayed):
    twins, _, stats = replayed
    for cid in ledger.customer_ids:
        truth, _ = inc.rebuild(ledger, cid, AS_OF)
        assert inc.same_twin(twins[cid], truth), (cid, inc.twin_diff(twins[cid], truth))
    # the replay exercised both Tier 1 paths and the calendar tier, so the equality is not vacuous
    assert sum(s["tier1_rebuild"] for s in stats) and sum(s["tier1_money"] for s in stats)
    assert sum(s["tier2_money"] + s["tier2_rebuild"] for s in stats)


def test_classification():
    assert not inc.tx_is_signal("current", -40, "groceries", "supermarket", "card")
    assert not inc.tx_is_signal("current", -30, "health", "pharmacy", "card")
    assert not inc.tx_is_signal("savings", 200, "savings", "transfer_to_savings", "internal_transfer")
    for sub, cat, amount, channel in (("salary", "income", 2850, "incoming_transfer"), ("rent", "housing", -900, "sepa_transfer"),
                                      ("fuel", "transport", -60, "card"), ("child_benefit", "income", 180, "incoming_transfer"),
                                      ("water", "utilities", -40, "direct_debit")):  # water: a possible recurring bill
        assert inc.tx_is_signal("current", amount, cat, sub, channel), sub
    rows = [tx(), tx(subcategory="restaurant_takeaway", category="dining")]
    assert inc.classify_day(rows) == "balance_only"
    assert inc.classify_day(rows, product_change=True) == "signal"
    assert inc.classify_day(rows + [tx(subcategory="salary", category="income", amount=2850.0)]) == "signal"


def _state(twin, balance=1500.0, **kw):
    return inc.StreamState(customer_id=twin["customer_id"], twin=twin, balance=balance, daily_discretionary=20.0,
                           daily_essentials=5.0, big_debit=500.0, **kw)


def test_tier0_salary_produces_payday_moment(ledger, replayed):
    twins, _, _ = replayed
    twin = twins[1]  # Lotte: salary on the 25th
    state, events = inc.on_transaction(_state(twin), tx(amount=2850.0, subcategory="salary", category="income",
                                                         channel="incoming_transfer", counterparty="Employer", balance_after=4350.0))
    push = [e for e in events if e["kind"] == "salary_plan"]
    assert len(push) == 1 and push[0]["sales"] is False and "€2,850 just arrived" in push[0]["body"]
    assert f"€{twin['plan']['free_per_week']}/week" in push[0]["body"]
    assert state.balance == 4350.0 and any(e["kind"] == "forecast" for e in events)


def test_tier0_large_debit_and_overdraft(ledger, replayed):
    twin = replayed[0][1]
    _, events = inc.on_transaction(_state(twin), tx(amount=-2400.0, subcategory="general", category="shopping",
                                                    counterparty="Bol.com", balance_after=-900.0))
    kinds = {e["kind"] for e in events}
    assert {"large_debit", "overdraft_warning", "forecast"} <= kinds
    assert not any(e.get("sales") for e in events)
    _, events = inc.on_transaction(_state(twin), tx())  # a small grocery run: forecast only
    assert [e["kind"] for e in events] == ["forecast"]


def test_persist_is_idempotent_and_leaves_overlays(tmp_path, ledger, replayed):
    twins, expiry, _ = replayed
    con = sqlite3.connect(tmp_path / "twins.db")
    con.execute("CREATE TABLE twin_feedback (customer_id INTEGER, fact TEXT, correct INTEGER, note TEXT, created_at REAL)")
    con.execute("INSERT INTO twin_feedback VALUES (1, 'has_car', 0, 'sold it', 1.0)")
    con.execute("CREATE TABLE twin_memory (customer_id INTEGER, note TEXT)")  # any read-time overlay table
    con.execute("INSERT INTO twin_memory VALUES (1, 'prefers email')")
    con.commit()
    before = (con.execute("SELECT * FROM twin_feedback").fetchall(), con.execute("SELECT * FROM twin_memory").fetchall())
    inc.persist(con, twins, expiry, "2026-09-30T23:00:00")
    snap = con.execute("SELECT * FROM twin_profile ORDER BY customer_id").fetchall()
    inc.persist(con, twins, expiry, "2026-09-30T23:00:00")  # a re-run of the same night
    assert con.execute("SELECT * FROM twin_profile ORDER BY customer_id").fetchall() == snap
    assert con.execute("SELECT COUNT(*) FROM twin_facts").fetchone()[0] == sum(len(t["facts"]) for t in twins.values())
    assert (con.execute("SELECT * FROM twin_feedback").fetchall(), con.execute("SELECT * FROM twin_memory").fetchall()) == before
    stored = json.loads(con.execute("SELECT profile_json FROM twin_profile WHERE customer_id = 1").fetchone()[0])
    rows = con.execute("SELECT fact, correct, note FROM twin_feedback WHERE customer_id = 1").fetchall()
    shown = apply_feedback(stored, rows)  # the correction still applies on read after the update
    assert shown["facts"]["has_car"]["rejected_by_customer"] is True
    assert "has_car" in shown["plan"].get("adjusted_for_feedback", [])
    con.close()
