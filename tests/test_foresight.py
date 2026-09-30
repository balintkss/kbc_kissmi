"""Money foresight: forecast / safe-to-spend, approve-to-act payday sorter, self-employed envelope, foresight moments.

The pure math runs on synthetic twins and an in-memory database (no generated DB needed). Everything else uses
the generated DB (`needs_db`) and the public API with demo logins from conftest (headers are redacted). The
foresight router is mounted onto api.main.app by a fixture when api/main.py doesn't include it yet.
Mandate rows written here are deleted afterwards; nothing else in the DB is changed.

Run:  .venv/bin/python -m pytest tests/test_foresight.py -q
"""
import copy
import json
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from twin import selfemployed, sorter
from twin.feedback import apply_feedback
from twin.forecast import FLOOR, bill_events, forecast, foresight_moments, project
from twin.recommender import moments

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "kbc_twin.db"
LOTTE, JULIEN, EMMA, MARC = 1, 2, 3, 4
AS_OF = date(2026, 9, 30)
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
needs_db = pytest.mark.needs_db

ENDPOINTS = [
    ("GET", "/api/me/forecast", None),
    ("GET", "/api/me/payday-sorter", None),
    ("POST", "/api/me/payday-sorter/approve", {"pots": ["bills"]}),
    ("POST", "/api/me/payday-sorter/revoke", None),
    ("GET", "/api/me/self-employed", None),
    ("GET", "/api/me/moments-plus", None),
]
ENDPOINT_IDS = [f"{m} {p}" for m, p, _ in ENDPOINTS]


# ---------------------------------------------------------------------- fixtures

def _stress_personas():
    """Demo personas (is_demo_persona = 1) whose stored twin has money_stress. Empty on a fresh clone."""
    if not DB_PATH.exists():
        return []
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        rows = con.execute("""SELECT c.customer_id, p.profile_json FROM customers c JOIN twin_profile p USING(customer_id)
                              WHERE c.is_demo_persona = 1 ORDER BY c.customer_id""").fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()
    return [cid for cid, js in rows if "money_stress" in (json.loads(js).get("facts") or {})]


STRESS = _stress_personas()
TEST_CUSTOMERS = {LOTTE, JULIEN, EMMA, MARC, *STRESS}


@pytest.fixture
def app(client, api_main):
    """The shared TestClient with the foresight router mounted (once), whether or not api/main.py includes it."""
    from api.routes_foresight import router
    # FastAPI >= 0.13x keeps included routers as _IncludedRouter entries (no .path), so look for both shapes
    if not any(getattr(r, "original_router", None) is router or getattr(r, "path", "") == "/api/me/forecast"
               for r in api_main.app.routes):
        api_main.app.include_router(router)
    return client


@pytest.fixture(autouse=True)
def _mandate_cleanup():
    """Delete every sorter_mandates row a test adds for the customers this module uses."""
    if not DB_PATH.exists():
        yield
        return
    con = sqlite3.connect(DB_PATH, timeout=30)
    try:
        base = con.execute("SELECT COALESCE(MAX(id), 0) FROM sorter_mandates").fetchone()[0]
    except sqlite3.OperationalError:
        base = 0
    finally:
        con.close()
    yield
    con = sqlite3.connect(DB_PATH, timeout=30)
    try:
        ids = sorted(TEST_CUSTOMERS)
        con.execute(f"DELETE FROM sorter_mandates WHERE id > ? AND customer_id IN ({','.join('?' * len(ids))})", (base, *ids))
        con.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        con.close()


def _mandates(customer_id):
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        return con.execute("SELECT id, customer_id, pots_json, status FROM sorter_mandates WHERE customer_id = ? ORDER BY id",
                           (customer_id,)).fetchall()
    finally:
        con.close()


@pytest.fixture
def twin_of(ro_con):
    """The twin as the API sees it: stored profile + the customer's own feedback (normally none in tests)."""
    def _load(cid):
        row = ro_con.execute("SELECT profile_json FROM twin_profile WHERE customer_id = ?", (cid,)).fetchone()
        if not row:
            pytest.skip(f"no twin built for customer {cid}")
        fb = ro_con.execute("SELECT fact, correct, note FROM twin_feedback WHERE customer_id = ? ORDER BY created_at",
                            (cid,)).fetchall()
        return apply_feedback(json.loads(row[0]), fb)
    return _load


class Recorder:
    """A connection stand-in that records every SQL statement and its parameters."""

    def __init__(self, con):
        self.con, self.calls = con, []

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))
        return self.con.execute(sql, params)


def _check_scoped(calls, cid):
    assert calls
    for sql, params in calls:
        if re.search(r"\b(transactions|accounts)\b", sql):
            assert "customer_id = ?" in sql, sql
            ints = {p for p in params if isinstance(p, int) and not isinstance(p, bool)}
            assert ints == {cid}, f"query bound to {ints}: {sql}"


def _no_iso(text):
    assert not ISO_DATE.search(text), f"ISO date in customer-facing text: {text}"


# ---------------------------------------------------------------------- synthetic: projection math + scoping

SYN, OTHER = 7, 8


def _synthetic_db():
    """Two customers. Customer 8 has a huge balance and huge spending that must never reach customer 7's forecast."""
    con = sqlite3.connect(":memory:")
    con.executescript("""
        CREATE TABLE accounts (account_id INTEGER PRIMARY KEY, customer_id INTEGER, type TEXT, balance REAL);
        CREATE TABLE transactions (tx_id INTEGER PRIMARY KEY, account_id INTEGER, customer_id INTEGER, booked_at DATE,
            amount REAL, counterparty TEXT, description TEXT, category TEXT, subcategory TEXT, channel TEXT, balance_after REAL);
        INSERT INTO accounts VALUES (1, 7, 'current', 1200), (2, 7, 'savings', 5000), (3, 8, 'current', 99999), (4, 8, 'savings', 1);
    """)
    rows = []
    for i in range(9):  # 9 x EUR 300 groceries in the window -> EUR 30/day
        rows.append((1, SYN, (AS_OF - timedelta(days=5 + 9 * i)).isoformat(), -300, "Lidl", "", "groceries", "supermarket", "card"))
    rows += [
        (1, SYN, "2026-09-02", -30, "Gym", "", "leisure", "gym", "direct_debit"),               # a recurring bill: not twice
        (1, SYN, "2026-09-03", -500, "Eigen rekening", "", "shopping", "general", "internal_transfer"),  # internal
        (2, SYN, "2026-09-04", -1000, "Lidl", "", "groceries", "supermarket", "card"),          # savings account
        (1, SYN, "2026-06-01", -900, "Lidl", "", "groceries", "supermarket", "card"),           # before the 90 days
        (3, SYN, "2026-09-05", -700, "Lidl", "", "groceries", "supermarket", "card"),           # someone else's account
        (3, OTHER, "2026-09-06", -9000, "Lidl", "", "groceries", "supermarket", "card"),        # someone else
        (3, OTHER, "2026-07-20", -2000, "Xerius", "", "taxes", "social_contributions", "direct_debit"),
    ]
    con.executemany("""INSERT INTO transactions (account_id, customer_id, booked_at, amount, counterparty, description,
                       category, subcategory, channel) VALUES (?,?,?,?,?,?,?,?,?)""", rows)
    return con


def _synthetic_twin():
    return dict(
        facts={"employment": dict(key="employment", value="employee", confidence=0.97)},
        recurring=[dict(name="Landlord", subcategory="rent", category="housing", frequency="monthly", amount=900.0,
                        day_of_month=4, next_date="2026-10-04", monthly_equivalent=900.0),
                   dict(name="Phone", subcategory="telecom", category="utilities", frequency="monthly", amount=50.0,
                        day_of_month=8, next_date="2026-10-08", monthly_equivalent=50.0),
                   dict(name="Gym", subcategory="gym", category="leisure", frequency="monthly", amount=30.0,
                        day_of_month=2, next_date="2026-10-02", monthly_equivalent=30.0),
                   dict(name="Insurer", subcategory="home", category="insurance", frequency="yearly", amount=400.0,
                        next_date="2027-03-01", monthly_equivalent=33.33)],
        plan=dict(payday="2026-10-10", income=2000, income_kind="salary", planned_savings=200, variable_essentials=[],
                  bills_until_next_payday=980, reserves=[], reserve_total=0, free_to_spend=820))


def test_lowest_point_math_on_a_synthetic_twin():
    con = _synthetic_db()
    f = forecast(con, SYN, _synthetic_twin())
    assert f["start_balance"] == 1200 and f["typical_daily_spend"] == 30.0 and f["daily_essentials"] == 0
    assert f["payday"] == "2026-10-10" and f["horizon_end"] == "2026-10-11"
    days = [p["date"] for p in f["series"]]
    assert days == [(AS_OF + timedelta(days=i)).isoformat() for i in range(12)]  # every day, today .. payday + 1
    bal = {p["date"][5:]: p["balance"] for p in f["series"]}
    # -30/day everyday, gym 30 on the 2nd, rent 900 on the 4th, phone 50 on the 8th, +2000 on payday, -200 savings after
    assert bal == {"09-30": 1200, "10-01": 1170, "10-02": 1110, "10-03": 1080, "10-04": 150, "10-05": 120, "10-06": 90,
                   "10-07": 60, "10-08": -20, "10-09": -50, "10-10": 1920, "10-11": 1690}
    assert f["lowest"] == dict(date="2026-10-09", balance=-50,
                               cause=dict(name="Phone", amount=50.0, date="2026-10-08", subcategory="telecom"), days_ahead=9)
    assert f["first_below_zero"] == "2026-10-08" and f["warning"] is True
    # without everyday spending the tightest day is payday itself (before the salary): (1200-980-50)/10 = 17
    assert f["safe_to_spend_per_day"] == 17
    assert f["top_up"] == 100 and f["top_up_from_savings"] is True  # brings the low (-50) back up to the EUR 50 floor
    assert [b["name"] for b in f["bills"]] == ["Gym", "Landlord", "Phone"]  # the yearly bill falls outside the horizon
    assert f["message"] == ("Heads-up: you'd go below zero on Thu 8 Oct and reach −€50 on Fri 9 Oct, the day before payday. "
                            "Move €100 from savings, or keep everyday spending under €17/day until payday on Sat 10 Oct "
                            "(you usually spend ≈ €30).")


def test_synthetic_forecast_queries_are_scoped_to_the_customer():
    rec = Recorder(_synthetic_db())
    forecast(rec, SYN, _synthetic_twin())
    _check_scoped(rec.calls, SYN)
    # customer 8's own forecast sees only customer 8's money
    other = forecast(_synthetic_db(), OTHER, _synthetic_twin())
    assert other["start_balance"] == 99999 and other["typical_daily_spend"] == 100.0  # 9000 / 90


def test_safe_to_spend_keeps_the_floor_every_day_until_payday():
    twin = _synthetic_twin()
    bills = bill_events(twin["recurring"], AS_OF, date(2026, 10, 11))
    p = project(1200, bills, date(2026, 10, 11), daily_discretionary=17, payday=date(2026, 10, 10), income=2000, savings=200)
    before_pay = [q["balance"] for q in p["series"] if q["date"] < "2026-10-10"]
    assert min(before_pay) >= FLOOR  # spending exactly the safe amount never breaks the floor ...
    p = project(1200, bills, date(2026, 10, 11), daily_discretionary=18, payday=date(2026, 10, 10), income=2000, savings=200)
    assert p["series"][-2]["balance"] - 2000 < FLOOR  # ... one euro more a day does (on payday, before the salary)


def test_no_fixed_payday_spreads_a_quiet_month_over_35_days():
    twin = _synthetic_twin()
    twin["plan"].update(payday=None, income_kind="irregular", income=3040, planned_savings=0)
    f = forecast(_synthetic_db(), SYN, twin)
    assert f["payday"] is None and f["horizon_end"] == (AS_OF + timedelta(days=35)).isoformat()
    assert len(f["series"]) == 36 and "quiet month" in f["income_assumption"]
    # day 1: +3040/30.4 = +100 income, -30 everyday
    assert f["series"][1]["balance"] == pytest.approx(1200 + 100 - 30, abs=0.01)


def test_bill_events_repeat_inside_the_horizon():
    rec = [dict(name="Rent", subcategory="rent", frequency="monthly", amount=900, next_date="2026-10-31"),
           dict(name="Water", subcategory="water", frequency="quarterly", amount=120, next_date="2026-09-15"),
           dict(name="Broken", frequency="monthly", amount=None, next_date="2026-10-02")]
    ev = bill_events(rec, AS_OF, date(2027, 1, 5))
    assert [(e["name"], e["date"].isoformat()) for e in ev] == [
        ("Rent", "2026-10-31"), ("Rent", "2026-11-30"), ("Water", "2026-12-15"), ("Rent", "2026-12-30")]


# ---------------------------------------------------------------------- real personas (engine output)

@needs_db
def test_lotte_forecast(app, login, ro_con, twin_of):
    r = app.get("/api/me/forecast", headers=login(LOTTE))
    assert r.status_code == 200
    f = r.json()
    current = ro_con.execute("SELECT SUM(balance) FROM accounts WHERE customer_id = ? AND type = 'current'", (LOTTE,)).fetchone()[0]
    assert f["start_balance"] == pytest.approx(current, abs=0.01)
    plan = twin_of(LOTTE)["plan"]
    assert f["payday"] == plan["payday"] == "2026-10-23" and f["horizon_end"] == "2026-10-24"
    assert f["series"][0] == dict(date="2026-09-30", balance=round(current, 2))
    by_day = {p["date"]: p["balance"] for p in f["series"]}
    # the salary lands on payday: the balance jumps by the plan's income minus one day of spending
    jump = by_day["2026-10-23"] - by_day["2026-10-22"]
    assert jump == pytest.approx(plan["income"] - f["typical_daily_spend"] - f["daily_essentials"], abs=0.02)
    assert ("J. Simon", "2026-10-04") in {(b["name"], b["date"]) for b in f["bills"]}  # rent on its day
    low = f["lowest"]
    assert low["balance"] == min(by_day.values()) and by_day[low["date"]] == low["balance"]
    if low["cause"]:
        assert 0 <= (date.fromisoformat(low["date"]) - date.fromisoformat(low["cause"]["date"])).days <= 3
    assert f["warning"] is (low["balance"] < 0)
    assert isinstance(f["safe_to_spend_per_day"], int) and f["safe_to_spend_per_day"] >= 0
    _no_iso(f["message"])
    assert f["message"].startswith("Heads-up" if f["warning"] else "You're on track")


@needs_db
def test_forecast_respects_feedback(ro_con, twin_of):
    base_twin = twin_of(LOTTE)
    base = forecast(ro_con, LOTTE, base_twin)
    no_car = forecast(ro_con, LOTTE, apply_feedback(base_twin, [("has_car", 0, "Sold it")]))
    fuel = next(v["amount"] for v in base_twin["plan"]["variable_essentials"] if v["name"] == "fuel")
    assert no_car["daily_essentials"] == pytest.approx(base["daily_essentials"] - fuel / 30.4, abs=0.01)
    assert no_car["adjusted_for_feedback"] == ["has_car"]
    no_savings = forecast(ro_con, LOTTE, apply_feedback(base_twin, [("saves_monthly", 0, None)]))
    saved = base_twin["plan"]["planned_savings"]
    assert saved and no_savings["series"][-1]["balance"] == pytest.approx(base["series"][-1]["balance"] + saved, abs=0.01)


@needs_db
def test_marc_forecast_irregular_income(app, login):
    f = app.get("/api/me/forecast", headers=login(MARC)).json()
    assert f["payday"] is None and f["horizon_end"] == "2026-11-04" and len(f["series"]) == 36
    assert "quiet month" in f["income_assumption"]
    # the engine's recurring list misses his quarterly social contributions; the forecast adds the next one
    social = [b for b in f["bills"] if b["subcategory"] == "social_contributions"]
    assert len(social) == 1 and "2026-09-30" < social[0]["date"] <= f["horizon_end"]
    assert f["warning"] is (f["lowest"]["balance"] < 0)
    _no_iso(f["message"])
    if f["warning"]:
        assert "quiet month" in f["message"]


@needs_db
@pytest.mark.parametrize("cid", STRESS or [pytest.param(None, marks=pytest.mark.skip(reason="no money-stress demo persona"))])
def test_money_stress_persona(app, login, cid):
    h = login(cid)
    f = app.get("/api/me/forecast", headers=h)
    assert f.status_code == 200 and f.json()["warning"] is (f.json()["lowest"]["balance"] < 0)
    p = app.get("/api/me/payday-sorter", headers=h).json()
    if p["available"]:
        ids = [x["id"] for x in p["pots"]]
        assert p["support_first"] is True and "savings" not in ids and ids[0] == "bills"
        if p["shortfall"]:
            assert "short" in p["message"]
    m = app.get("/api/me/moments-plus", headers=h).json()
    assert not [x for x in m["push"] + m["feed"] if x["sales"]]  # help, never sales
    assert all(x["sales"] and x.get("held_because") for x in m["held_back"])
    if f.json()["warning"]:
        assert "overdraft_warning" in {x["kind"] for x in m["push"] + m["feed"]}


@needs_db
@pytest.mark.parametrize("cid", [LOTTE, MARC])
def test_real_queries_are_scoped_to_the_customer(ro_con, twin_of, cid):
    rec = Recorder(ro_con)
    twin = twin_of(cid)
    foresight_moments(rec, cid, twin)
    selfemployed.envelope(rec, cid, twin)
    _check_scoped(rec.calls, cid)


@needs_db
def test_forecast_ignores_a_customer_id_in_the_query(app, login, ro_con):
    f = app.get("/api/me/forecast?customer_id=4", headers=login(LOTTE)).json()
    lotte = ro_con.execute("SELECT SUM(balance) FROM accounts WHERE customer_id = ? AND type = 'current'", (LOTTE,)).fetchone()[0]
    assert f["start_balance"] == pytest.approx(lotte, abs=0.01)
    assert app.get("/api/me/self-employed?customer_id=4", headers=login(LOTTE)).json() == {"applicable": False}


# ---------------------------------------------------------------------- payday sorter

LOTTE_POTS = ["bills", "everyday", "yearly_bills", "car_upkeep", "savings", "free_to_spend"]


@needs_db
def test_sorter_proposal_ids_are_stable(app, login, twin_of):
    h = login(LOTTE)
    first, second = (app.get("/api/me/payday-sorter", headers=h).json() for _ in range(2))
    assert [p["id"] for p in first["pots"]] == [p["id"] for p in second["pots"]] == LOTTE_POTS
    assert first["mandate"] is None and first["simulation"] is True and first["shortfall"] == 0
    assert sum(p["amount"] for p in first["pots"]) == pytest.approx(first["income"], abs=3)
    assert {p["id"] for p in first["pots"] if p["approvable"]} == {"bills", "yearly_bills", "car_upkeep", "savings"}
    assert first["message"].startswith("On Fri 23 Oct Kate would move €") and "Simulation" in first["message"]
    _no_iso(first["message"])
    # ids never depend on amounts
    twin = twin_of(LOTTE)
    richer = copy.deepcopy(twin)
    richer["plan"]["income"] += 5000
    for r in richer["plan"]["reserves"]:
        r["monthly"] *= 3
    assert [p["id"] for p in sorter.proposal(richer)["pots"]] == [p["id"] for p in sorter.proposal(twin)["pots"]]
    marc = app.get("/api/me/payday-sorter", headers=login(MARC)).json()
    assert "pet_care" in [p["id"] for p in marc["pots"]] and marc["payday"] is None
    assert marc["message"].startswith("When your next invoice lands")


@needs_db
@pytest.mark.parametrize("body", [
    {"pots": ["bills", "holiday_fund"]},                  # not in the proposal
    {"pots": ["free_to_spend"]},                          # in the proposal, but stays on the current account
    {"pots": []},                                         # nothing approved
    {"pots": [{"id": "bills", "amount": 1}]},             # amounts can't be sent
    {"pots": ["Bills; DROP TABLE sorter_mandates"]},      # not a pot id
    {"amounts": {"bills": 5}},                            # no pots at all
], ids=["unknown", "not-movable", "empty", "objects", "junk", "missing"])
def test_sorter_rejects_anything_but_proposal_pot_ids(app, login, body):
    r = app.post("/api/me/payday-sorter/approve", json=body, headers=login(LOTTE))
    assert r.status_code == 422 and isinstance(r.json()["detail"], list)
    assert _mandates(LOTTE) == []


@needs_db
def test_sorter_amounts_come_from_the_server(app, login):
    h = login(LOTTE)
    prop = {p["id"]: p for p in app.get("/api/me/payday-sorter", headers=h).json()["pots"]}
    body = {"pots": ["car_upkeep", "bills", "bills"], "amounts": {"bills": 1, "car_upkeep": 99999}, "amount": 5}
    r = app.post("/api/me/payday-sorter/approve", json=body, headers=h)
    assert r.status_code == 200
    out = r.json()
    stored = [(p["id"], p["amount"]) for p in out["mandate"]["pots"]]
    assert stored == [("bills", prop["bills"]["amount"]), ("car_upkeep", prop["car_upkeep"]["amount"])]  # proposal order
    assert out["message"] == (f"On Fri 23 Oct Kate will move €{prop['bills']['amount']:,} to Bills and "
                              f"€{prop['car_upkeep']['amount']:,} to Car upkeep. {sorter.SIMULATION}")
    rows = _mandates(LOTTE)
    assert len(rows) == 1 and rows[0][1] == LOTTE and rows[0][3] == "active"
    assert json.loads(rows[0][2]) == out["mandate"]["pots"]
    assert app.get("/api/me/payday-sorter", headers=login(MARC)).json()["mandate"] is None  # Lotte's mandate only


@needs_db
def test_sorter_approve_supersede_and_revoke(app, login):
    h = login(LOTTE)
    assert app.post("/api/me/payday-sorter/approve", json={"pots": ["bills"]}, headers=h).status_code == 200
    assert app.post("/api/me/payday-sorter/approve", json={"pots": ["savings", "yearly_bills"]}, headers=h).status_code == 200
    got = app.get("/api/me/payday-sorter", headers=h).json()["mandate"]
    assert [p["id"] for p in got["pots"]] == ["yearly_bills", "savings"] and got["status"] == "active"
    assert got["next_run"]["message"].startswith("On Fri 23 Oct Kate will move")
    assert [s for *_, s in _mandates(LOTTE)] == ["superseded", "active"]

    r = app.post("/api/me/payday-sorter/revoke", headers=h)
    assert r.status_code == 200 and r.json()["revoked"] == 1 and r.json()["mandate"] is None
    assert app.get("/api/me/payday-sorter", headers=h).json()["mandate"] is None
    assert [s for *_, s in _mandates(LOTTE)] == ["superseded", "revoked"]
    assert app.post("/api/me/payday-sorter/revoke", headers=h).json()["revoked"] == 0


@needs_db
def test_sorter_posts_are_rate_limited(app, login):
    h = login(LOTTE)
    codes = [app.post("/api/me/payday-sorter/revoke", headers=h).status_code for _ in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429


def _with_money_stress(twin):
    twin = copy.deepcopy(twin)
    twin["facts"]["money_stress"] = dict(key="money_stress", value=True, confidence=0.9, since=None, evidence=[],
                                         summary="7 days in the red in the last 90 days", implies=[])
    return twin


@needs_db
def test_sorter_under_money_stress_puts_bills_first_and_shows_the_shortfall(twin_of):
    calm = sorter.proposal(twin_of(LOTTE))
    stressed = sorter.proposal(_with_money_stress(twin_of(LOTTE)))
    assert "savings" in [p["id"] for p in calm["pots"]] and calm["support_first"] is False
    assert "savings" not in [p["id"] for p in stressed["pots"]] and stressed["support_first"] is True
    assert "No savings pot for now" in stressed["message"]

    tight = _with_money_stress(twin_of(LOTTE))
    tight["plan"]["income"] = 1500  # less than bills (1458) + groceries & fuel (413)
    prop = sorter.proposal(tight)
    pots = {p["id"]: p for p in prop["pots"]}
    assert pots["bills"]["amount"] == pots["bills"]["planned"]  # bills first, in full
    assert pots["everyday"]["amount"] == 1500 - pots["bills"]["amount"] and pots["everyday"]["short"] > 0
    assert pots["car_upkeep"]["amount"] == 0 and pots["free_to_spend"]["amount"] == 0
    needed = sum(p["planned"] for p in prop["pots"] if p["id"] != "free_to_spend")
    assert prop["shortfall"] == pytest.approx(needed - 1500, abs=2) and f"€{prop['shortfall']:,} short" in prop["message"]


def test_sorter_without_income_has_nothing_to_sort():
    prop = sorter.proposal(dict(facts={}, plan=None))
    assert prop["available"] is False and prop["pots"] == []
    with pytest.raises(sorter.NoPlan):
        sorter.approve(None, 1, dict(facts={}, plan=None), ["bills"])


# ---------------------------------------------------------------------- self-employed envelope

def test_belgian_rates():
    assert selfemployed.social_contribution(50_000) == pytest.approx(10_250)
    assert selfemployed.social_contribution(100_000) == pytest.approx(75_024.54 * 0.205 + (100_000 - 75_024.54) * 0.1416)
    assert selfemployed.social_contribution(500_000) == selfemployed.social_contribution(110_562.42)  # capped
    assert selfemployed.income_tax(0) == 0 and selfemployed.income_tax(11_550) == 0  # the tax-free amount
    assert selfemployed.income_tax(20_000) == pytest.approx((16_720 * 0.25 + 3_280 * 0.40 - 11_550 * 0.25) * 1.07)
    assert [d.isoformat() for d in selfemployed.PREPAYMENT_DEADLINES] == ["2026-04-10", "2026-07-10", "2026-10-12", "2026-12-21"]


@needs_db
def test_marc_self_employed_envelope(app, login):
    r = app.get("/api/me/self-employed", headers=login(MARC))
    assert r.status_code == 200
    e = r.json()
    assert e["applicable"] is True and e["basis"]["invoice_count"] > 0
    sa = e["set_aside"]
    if e["basis"]["annualised_income"] < 75_024:
        assert sa["social_contributions_pct"] == 20.5
    assert sa["total_pct"] == pytest.approx(sa["social_contributions_pct"] + sa["income_tax_pct"], abs=0.11)
    assert 0 < sa["income_tax_pct"] < 50
    assert e["tax_prepayments"]["next_deadline"] == "2026-10-12"
    assert e["tax_prepayments"]["remaining_deadlines"] == ["2026-10-12", "2026-12-21"]
    social = e["social_contributions"]
    assert social["observed_quarterly"] > 0 and social["next_expected"] > "2026-09-30"
    assert social["legal_deadline"] == "2026-12-31"  # due by the last day of the quarter
    assert e["vat"]["known"] is False  # never guessed
    last = e["last_invoice"]
    assert last["total"] == last["social_contributions"] + last["income_tax"]
    assert "not tax advice" in e["message"] and "not tax advice" in e["disclaimer"] and e["sources"]
    _no_iso(e["message"])


@needs_db
@pytest.mark.parametrize("cid", [LOTTE, JULIEN, EMMA])
def test_employees_get_no_envelope(app, login, cid):
    assert app.get("/api/me/self-employed", headers=login(cid)).json() == {"applicable": False}


@needs_db
def test_rejected_self_employment_drops_the_envelope(ro_con, twin_of):
    twin = apply_feedback(twin_of(MARC), [("employment", 0, None)])
    assert selfemployed.envelope(ro_con, MARC, twin) == {"applicable": False}
    assert "self_employed_reserve" not in {m["kind"] for m in foresight_moments(ro_con, MARC, twin)}


# ---------------------------------------------------------------------- moments

@needs_db
@pytest.mark.parametrize("cid", [LOTTE, JULIEN, EMMA, MARC, *STRESS])
def test_moments_without_extra_are_unchanged(twin_of, cid):
    twin = twin_of(cid)
    before = moments(twin)
    assert moments(twin, extra=None) == before and moments(twin, extra=[]) == before
    assert moments(_with_money_stress(twin), extra=None) == moments(_with_money_stress(twin))


@needs_db
def test_moments_with_foresight_extras(app, login, ro_con, twin_of):
    lotte, marc = twin_of(LOTTE), twin_of(MARC)
    extra = foresight_moments(ro_con, LOTTE, lotte)
    assert all(m["sales"] is False and m["topic"] is None for m in extra)
    assert "self_employed_reserve" not in {m["kind"] for m in extra}
    plain, plus = moments(lotte), moments(lotte, extra=extra)
    kinds = lambda m: [x["kind"] for part in ("push", "feed", "held_back") for x in m[part]]  # noqa: E731
    assert set(kinds(plain)) <= set(kinds(plus)) and len(plus["push"]) <= 2
    prios = [x["priority"] for x in plus["push"] + plus["feed"]]
    assert prios == sorted(prios, reverse=True)
    if extra:
        assert plus["push"][0]["kind"] == "overdraft_warning" and plus["push"][0]["priority"] == 94

    marc_extra = {m["kind"]: m for m in foresight_moments(ro_con, MARC, marc)}
    assert marc_extra["self_employed_reserve"]["priority"] == 88
    for m in marc_extra.values():
        _no_iso(m["body"])

    # the API: moments-plus = moments + extras; the existing /api/me/moments is untouched
    h = login(LOTTE)
    assert app.get("/api/me/moments-plus", headers=h).json() == plus
    assert app.get("/api/me/moments", headers=h).json() == plain


def test_extra_sales_moments_are_held_back_under_money_stress():
    twin = dict(facts={"money_stress": dict(key="money_stress", value=True)}, plan=None)
    offer = dict(kind="promo", priority=99, title="t", body="b", topic="savings", sales=True)
    warn = dict(kind="overdraft_warning", priority=94, title="t", body="b", topic=None, sales=False)
    m = moments(twin, extra=[offer, warn])
    assert [x["kind"] for x in m["push"]] == ["support", "overdraft_warning"]
    assert [x["kind"] for x in m["held_back"]] == ["promo"] and m["held_back"][0]["held_because"]


# ---------------------------------------------------------------------- auth

@needs_db
@pytest.mark.parametrize("method,path,body", ENDPOINTS, ids=ENDPOINT_IDS)
def test_foresight_endpoints_require_a_customer_token(app, redacted, method, path, body):
    from api.security import issue_token
    r = app.request(method, path, json=body)
    assert r.status_code == 401 and r.headers.get("www-authenticate", "").lower().startswith("bearer")
    ops = redacted(Authorization=f"Bearer {issue_token('advisor', role='ops')}")  # an ops token is not a customer token
    assert app.request(method, path, json=body, headers=ops).status_code == 401
    assert app.request(method, path, json=body, headers=redacted(Authorization="Bearer not-a-token")).status_code == 401
    assert _mandates(LOTTE) == []


@needs_db
def test_foresight_routes_take_no_customer_identifier(app, api_main):
    spec = api_main.app.openapi()
    paths = {p: ops for p, ops in spec["paths"].items() if p.startswith("/api/me/") and
             any(k in p for k in ("forecast", "payday-sorter", "self-employed", "moments-plus"))}
    assert len(paths) == 6
    for path, ops in paths.items():
        assert "{" not in path
        for op in ops.values():
            assert not op.get("parameters") or {p["name"] for p in op["parameters"]} <= {"authorization"}
    body = spec["components"]["schemas"]["Approval"]
    assert set(body["properties"]) == {"pots"}
