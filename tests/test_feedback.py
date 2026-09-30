"""Unit tests for twin.feedback.apply_feedback (customer corrections on a precomputed twin).

Real twins of the demo personas are read read-only from data/kbc_twin.db (skipped if the DB
is not built); synthetic twins cover the edge cases. Self-contained: no conftest needed.
"""
import copy
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from twin.feedback import apply_feedback  # noqa: E402

DB = ROOT / "data" / "kbc_twin.db"


def _load_twins(*cids):
    if not DB.exists():
        return {}
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        rows = con.execute(f"SELECT customer_id, profile_json FROM twin_profile WHERE customer_id IN ({','.join('?' * len(cids))})",
                           cids).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        con.close()
    return {cid: json.loads(js) for cid, js in rows}


@pytest.fixture(scope="module")
def twins():
    loaded = _load_twins(1, 2, 4)
    if len(loaded) < 3:
        pytest.skip("data/kbc_twin.db with built twins for customers 1, 2 and 4 is required")
    return loaded


@pytest.fixture
def lotte(twins):
    return copy.deepcopy(twins[1])


@pytest.fixture
def julien(twins):
    return copy.deepcopy(twins[2])


@pytest.fixture
def marc(twins):
    return copy.deepcopy(twins[4])


def reserve(plan, label):
    return next((r for r in plan["reserves"] if r["for_"] == label), None)


def energy(plan):
    return [v for v in plan["variable_essentials"] if v["name"] in ("fuel", "charging")]


def engine_free(twin):
    """free_to_spend before rounding, recomputed independently with the engine's formula."""
    p, rec = twin["plan"], twin["recurring"]
    bills = (sum(r["amount"] for r in rec if r["frequency"] == "monthly")
             + sum(r["monthly_equivalent"] for r in rec if r["frequency"] == "quarterly"))
    return (p["income"] - bills - sum(r["monthly"] for r in p["reserves"]) - p["planned_savings"]
            - sum(v["amount"] for v in p["variable_essentials"]))


# ---------------------------------------------------------------------- real twins

def test_personas_have_the_expected_plan_inputs(lotte, julien, marc):
    assert reserve(lotte["plan"], "car upkeep") and energy(lotte["plan"])[0]["name"] == "fuel"
    assert reserve(julien["plan"], "car upkeep") and reserve(julien["plan"], "dog care")
    assert reserve(marc["plan"], "car upkeep") and energy(marc["plan"])[0]["name"] == "charging"
    # the independent formula reproduces the stored numbers, so it can check the recomputation
    for t in (lotte, julien, marc):
        assert round(engine_free(t)) == t["plan"]["free_to_spend"]
        assert round(engine_free(t) / 4.3) == t["plan"]["free_per_week"]


def test_input_is_not_mutated(lotte):
    before = json.dumps(lotte, sort_keys=True)
    out = apply_feedback(lotte, [("has_car", 0, "sold it"), ("saves_monthly", 0, None)])
    assert json.dumps(lotte, sort_keys=True) == before
    assert out is not lotte and out["plan"] is not lotte["plan"] and out["facts"] is not lotte["facts"]
    assert out["plan"]["reserves"] is not lotte["plan"]["reserves"]


def test_no_feedback_returns_an_equal_copy(lotte):
    out = apply_feedback(lotte, [])
    assert out == lotte and out is not lotte


@pytest.mark.parametrize("persona", ["lotte", "julien", "marc"])
def test_rejecting_car_drops_reserve_and_fuel(persona, request):
    twin = request.getfixturevalue(persona)
    old = twin["plan"]
    car_reserve = reserve(old, "car upkeep")["monthly"]
    fuel = sum(v["amount"] for v in energy(old))
    assert car_reserve > 0 and fuel > 0

    out = apply_feedback(twin, [("has_car", 0, None)])
    new = out["plan"]
    assert out["facts"]["has_car"]["rejected_by_customer"] is True
    assert out["facts"]["has_car"]["confirmed_by_customer"] is False
    assert reserve(new, "car upkeep") is None
    assert energy(new) == []
    assert [v["name"] for v in new["variable_essentials"]] == ["groceries"]
    assert new["reserve_total"] == old["reserve_total"] - car_reserve
    assert new["free_to_spend"] == old["free_to_spend"] + car_reserve + fuel
    assert new["free_per_week"] == round(engine_free(out) / 4.3)
    assert new["adjusted_for_feedback"] == ["has_car"]
    # bills come from observed transactions and are never touched
    for k in ("bills", "bills_until_next_payday", "heads_up", "income", "planned_savings"):
        assert new[k] == old[k]
    assert reserve(new, "yearly bills") == reserve(old, "yearly bills")


def test_lotte_numbers(lotte):
    new = apply_feedback(lotte, [("has_car", 0, None)])["plan"]
    assert (new["reserve_total"], new["free_to_spend"], new["free_per_week"]) == (51, 915, 213)


def test_confirming_changes_nothing_numerically(julien):
    out = apply_feedback(julien, [("has_car", 1, None), ("pet", 1, "Max"), ("saves_monthly", 1, None)])
    assert out["plan"] == julien["plan"]
    assert "adjusted_for_feedback" not in out["plan"]
    assert out["facts"]["has_car"]["confirmed_by_customer"] is True
    assert out["facts"]["has_car"]["rejected_by_customer"] is False
    assert out["facts"]["pet"]["customer_note"] == "Max"


def test_last_row_wins(lotte):
    restored = apply_feedback(lotte, [("has_car", 0, "not mine"), ("has_car", 1, None)])
    assert restored["plan"] == lotte["plan"]
    assert restored["facts"]["has_car"]["rejected_by_customer"] is False
    assert restored["facts"]["has_car"]["confirmed_by_customer"] is True
    assert restored["facts"]["has_car"]["customer_note"] == "not mine"  # a later row without a note keeps it

    rejected = apply_feedback(lotte, [("has_car", 1, None), ("has_car", 0, None)])
    assert reserve(rejected["plan"], "car upkeep") is None
    assert rejected["plan"]["adjusted_for_feedback"] == ["has_car"]


@pytest.mark.parametrize("persona", ["julien", "marc"])
def test_rejecting_pet_drops_pet_reserve(persona, request):
    twin = request.getfixturevalue(persona)
    old = twin["plan"]
    label = f"{twin['facts']['pet']['value']} care"
    pet_reserve = reserve(old, label)["monthly"]

    new = apply_feedback(twin, [("pet", 0, None)])["plan"]
    assert reserve(new, label) is None
    assert reserve(new, "car upkeep") == reserve(old, "car upkeep")
    assert new["variable_essentials"] == old["variable_essentials"]
    assert new["reserve_total"] == old["reserve_total"] - pet_reserve
    assert new["free_to_spend"] == old["free_to_spend"] + pet_reserve
    assert new["adjusted_for_feedback"] == ["pet"]


def test_rejecting_savings_zeroes_planned_savings(lotte):
    old = lotte["plan"]
    new = apply_feedback(lotte, [("saves_monthly", 0, None)])["plan"]
    assert old["planned_savings"] > 0
    assert new["planned_savings"] == 0
    assert new["free_to_spend"] == old["free_to_spend"] + old["planned_savings"]
    assert new["reserves"] == old["reserves"] and new["reserve_total"] == old["reserve_total"]
    assert new["adjusted_for_feedback"] == ["saves_monthly"]


def test_several_rejections_add_up(julien):
    old = julien["plan"]
    freed = (reserve(old, "car upkeep")["monthly"] + reserve(old, "dog care")["monthly"]
             + sum(v["amount"] for v in energy(old)) + old["planned_savings"])
    out = apply_feedback(julien, [("pet", 0, None), ("saves_monthly", 0, None), ("has_car", 0, None)])
    new = out["plan"]
    assert [r["for_"] for r in new["reserves"]] == ["yearly bills"]
    assert new["reserve_total"] == reserve(old, "yearly bills")["monthly"]
    assert new["free_to_spend"] == old["free_to_spend"] + freed
    assert new["free_per_week"] == round(engine_free(out) / 4.3)
    assert new["adjusted_for_feedback"] == ["has_car", "pet", "saves_monthly"]


def test_unknown_fact_is_ignored(lotte):
    out = apply_feedback(lotte, [("has_boat", 0, "no boat"), ("pet", 0, None)])  # Lotte has no pet either
    assert out == lotte


def test_rejecting_a_fact_without_plan_effect_leaves_plan(lotte):
    out = apply_feedback(lotte, [("gym_member", 0, None)])
    assert out["facts"]["gym_member"]["rejected_by_customer"] is True
    assert out["plan"] == lotte["plan"]


# ---------------------------------------------------------------------- synthetic edge cases

def synthetic():
    return {
        "facts": {
            "has_car": {"key": "has_car", "value": True, "powertrain": "combustion", "monthly_reserve": 80},
            "pet": {"key": "pet", "value": "cat", "monthly_reserve": 15},
            "saves_monthly": {"key": "saves_monthly", "value": 100},
        },
        "recurring": [
            {"frequency": "monthly", "amount": 500.0, "monthly_equivalent": 500.0},
            {"frequency": "quarterly", "amount": 90.0, "monthly_equivalent": 30.0},
            {"frequency": "yearly", "amount": 120.0, "monthly_equivalent": 10.0},
        ],
        "plan": {
            "income": 2000, "bills_until_next_payday": 530,
            "reserves": [{"for_": "yearly bills", "monthly": 10}, {"for_": "car upkeep", "monthly": 80},
                         {"for_": "cat care", "monthly": 15}],
            "reserve_total": 105, "planned_savings": 100,
            "variable_essentials": [{"name": "fuel", "amount": 150, "estimated": True},
                                    {"name": "groceries", "amount": 300, "estimated": True}],
            "free_to_spend": 815, "free_per_week": 190,
        },
    }


def test_synthetic_full_recompute():
    t = synthetic()
    new = apply_feedback(t, [("has_car", 0, None), ("pet", 0, None), ("saves_monthly", 0, None)])["plan"]
    assert new["reserves"] == [{"for_": "yearly bills", "monthly": 10}]
    assert new["reserve_total"] == 10
    assert new["planned_savings"] == 0
    assert new["free_to_spend"] == 2000 - 530 - 10 - 0 - 300 == 815 + 80 + 15 + 150 + 100
    assert new["free_per_week"] == round(1160 / 4.3)
    assert new["adjusted_for_feedback"] == ["has_car", "pet", "saves_monthly"]
    assert t == synthetic()  # not mutated


def test_plan_none():
    t = synthetic()
    t["plan"] = None
    out = apply_feedback(t, [("has_car", 0, "no car")])
    assert out["plan"] is None
    assert out["facts"]["has_car"]["rejected_by_customer"] is True
    assert out["facts"]["has_car"]["customer_note"] == "no car"


def test_missing_plan_and_facts_keys():
    assert apply_feedback({}, [("has_car", 0, None)]) == {}
    assert apply_feedback({"facts": None, "plan": None}, [("has_car", 0, None)]) == {"facts": None, "plan": None}
    t = synthetic()
    del t["plan"]
    assert "plan" not in apply_feedback(t, [("has_car", 0, None)])


def test_sparse_plan_shifts_free_money_by_what_was_freed():
    """No income / recurring to recompute from: free_to_spend moves by exactly the dropped amounts."""
    t = {"facts": {"has_car": {"value": True}},
         "plan": {"reserves": [{"for_": "car upkeep", "monthly": 80}], "variable_essentials": [{"name": "charging", "amount": 40}],
                  "free_to_spend": 100}}
    new = apply_feedback(t, [("has_car", 0, None)])["plan"]
    assert new["reserves"] == [] and new["variable_essentials"] == []
    assert new["reserve_total"] == 0
    assert new["free_to_spend"] == 220 and new["free_per_week"] == round(220 / 4.3)
    assert new["adjusted_for_feedback"] == ["has_car"]


def test_plan_without_reserves_or_variable_keys():
    t = {"facts": {"has_car": {"value": True}, "pet": {"value": "dog"}}, "plan": {"income": 1000, "reserve_total": 50}}
    new = apply_feedback(t, [("has_car", 0, None), ("pet", 0, None)])["plan"]
    assert new == {"income": 1000, "reserve_total": 50}  # nothing to drop -> untouched, no marker


def test_bills_fallback_when_recurring_missing():
    t = synthetic()
    del t["recurring"]
    new = apply_feedback(t, [("has_car", 0, None)])["plan"]
    assert new["free_to_spend"] == 2000 - 530 - 25 - 100 - 300
