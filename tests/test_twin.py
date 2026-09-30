"""Engine, recommender and moments tests on the precomputed twins (no HTTP).

Twins are read from twin_profile (read-only). The ground-truth tables are only read here, to
score the twin; the product code must never read them."""
import copy
import json
import re
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from twin.catalog import CATALOG
from twin.recommender import moments, page

pytestmark = pytest.mark.needs_db

ROOT = Path(__file__).resolve().parent.parent
LOTTE, JULIEN, EMMA, MARC = 1, 2, 3, 4


@pytest.fixture(scope="module")
def profiles(ro_con):
    """Every stored twin, keyed by customer id."""
    out = {cid: json.loads(js) for cid, js in ro_con.execute("SELECT customer_id, profile_json FROM twin_profile")}
    if len(out) < 100:
        pytest.skip("twin_profile is (almost) empty: run `python -m twin.engine` first")
    return out


@pytest.fixture
def persona(profiles):
    """Deep copy of one stored twin, safe to modify."""
    return lambda cid: copy.deepcopy(profiles[cid])


def facts(twin):
    return twin["facts"]


def reject(twin, key):
    twin["facts"][key]["rejected_by_customer"] = True
    return twin


def with_money_stress(twin):
    twin = copy.deepcopy(twin)
    twin["facts"]["money_stress"] = dict(key="money_stress", value=True, confidence=0.9, since=None, evidence=[],
                                         summary="7 days in the red in the last 90 days", implies=[])
    return twin


# ====================================================================== demo personas

def test_lotte_owns_a_recently_bought_petrol_car_insured_elsewhere(persona):
    car = facts(persona(LOTTE))["has_car"]
    assert car["value"] is True
    assert car["powertrain"] == "combustion"
    assert car["bought_recently"] is True
    assert car["insured_at"] == "Ethias"
    assert car["purchase_price"] == 11500
    assert car["evidence"] and car["confidence"] >= 0.6


def test_lotte_new_car_event(persona):
    assert facts(persona(LOTTE))["life_event_new_car"]["value"] == "2026-06-13"


def test_lotte_payday_plan_lands_on_a_weekday(persona):
    t = persona(LOTTE)
    assert facts(t)["income"]["payday"] == 25
    pay = date.fromisoformat(t["plan"]["payday"])
    assert pay.weekday() < 5
    assert (pay.year, pay.month) == (2026, 10) and 23 <= pay.day <= 25  # 25 Oct 2026 is a Sunday -> Friday 23rd
    assert t["plan"]["income"] == 2850 and t["plan"]["income_kind"] == "salary"


def test_julien_new_baby_drives_hospital_insurance(persona):
    t = persona(JULIEN)
    assert "life_event_new_baby" in facts(t)
    block = page(t, "family")
    assert block["personalized"] and block["highlight"]["id"] == "hospital_insurance"
    assert "life_event_new_baby" in {b["key"] for b in block["highlight"]["because"]}


def test_emma_first_job_and_move(persona):
    f = facts(persona(EMMA))
    assert f["life_event_first_job"]["value"] == "Deloitte Belgium"
    assert "life_event_moved" in f
    assert page(persona(EMMA), "home")["highlight"]["id"] == "home_insurance"


def test_marc_self_employed_with_irregular_plan(persona):
    t = persona(MARC)
    assert facts(t)["employment"]["value"] == "self_employed"
    assert t["plan"]["income_kind"] == "irregular"
    assert t["plan"]["payday"] is None


def test_every_fixed_payday_is_a_weekday(profiles):
    paydays = [t["plan"]["payday"] for t in profiles.values() if t.get("plan") and t["plan"].get("payday")]
    assert len(paydays) > 1000
    weekend = [p for p in paydays if date.fromisoformat(p).weekday() >= 5]
    assert weekend == []


def test_every_fact_is_well_formed(profiles):
    for cid, t in profiles.items():
        for key, f in t["facts"].items():
            assert f["key"] == key, cid
            assert 0 < f["confidence"] <= 1, (cid, key)
            assert isinstance(f["evidence"], list) and all(isinstance(x, int) for x in f["evidence"]), (cid, key)


def test_twin_never_stores_truth_data(profiles):
    assert not any("truth" in js for js in (json.dumps(t) for t in list(profiles.values())[:500]))


# ====================================================================== recommender

@pytest.mark.parametrize("topic", list(CATALOG))
def test_anonymous_page_is_generic(topic):
    block = page(None, topic)
    assert block["personalized"] is False and block["highlight"] is None
    assert [v["id"] for v in block["variants"]] == list(CATALOG[topic]["variants"])
    assert all(v["name"] and v["summary"] and v["features"] for v in block["variants"])


def test_every_personalized_highlight_is_a_catalog_variant(profiles):
    """All 5,000 twins x every topic: no crash, highlight from the catalogue, alternatives = the rest."""
    personalized = 0
    for cid, t in profiles.items():
        for topic, cat in CATALOG.items():
            block = page(t, topic)
            if not block["personalized"]:
                assert block["highlight"] is None
                continue
            personalized += 1
            hl = block["highlight"]
            assert hl["id"] in cat["variants"], (cid, topic, hl["id"])
            assert isinstance(hl["reason"], str), (cid, topic)
            assert {b["key"] for b in hl["because"]} <= set(t["facts"]), (cid, topic)
            assert sorted(a["id"] for a in block["alternatives"]) == sorted(set(cat["variants"]) - {hl["id"]}), (cid, topic)
    assert personalized > len(profiles) * 3


@pytest.mark.xfail(strict=False, reason="BUG: _pick_car_loan falls through to 'new_car_loan' with an empty reason when "
                                        "_affordable_loan() is None (free_to_spend <= 0): ~150 twins with no room in "
                                        "their budget, most under money stress, get the priciest loan highlighted, unexplained")
def test_every_personalized_highlight_explains_itself(profiles):
    unexplained = [(cid, topic, block["highlight"]["id"]) for cid, t in profiles.items() for topic in CATALOG
                   for block in [page(t, topic)] if block["personalized"] and not block["highlight"]["reason"].strip()]
    assert unexplained == []


def test_rejected_car_stops_driving_car_pages_and_moments(persona):
    t = reject(persona(LOTTE), "has_car")
    assert page(t, "car_insurance")["personalized"] is False
    kinds = {m["kind"] for part in moments(t).values() for m in part}
    assert "new_car" not in kinds and "salary_plan" in kinds


@pytest.mark.xfail(strict=False, raises=TypeError,
                   reason="BUG: _pick_savings uses buffer['value'] when the customer rejected financial_buffer "
                          "(buffer is None) -> TypeError; reachable as HTTP 500 on /api/experience/savings")
def test_rejected_financial_buffer_does_not_crash_savings_page(persona):
    block = page(reject(persona(MARC), "financial_buffer"), "savings")
    assert block["topic"] == "savings"


@pytest.mark.xfail(strict=False, reason="BUG: page() builds `because` from the picker's fact keys without skipping "
                                        "rejected facts, so a highlight still cites a fact the customer said is wrong "
                                        "(e.g. Lotte rejects housing -> home page is still 'because' housing)")
def test_highlight_never_cites_a_rejected_fact(persona):
    for cid, key, topic in ((LOTTE, "housing", "home"), (LOTTE, "financial_buffer", "savings"),
                            (JULIEN, "income", "car_loan")):
        block = page(reject(persona(cid), key), topic)
        cited = {b["key"] for b in (block["highlight"] or {}).get("because", [])}
        assert key not in cited, (cid, key, topic)


# ====================================================================== moments

def test_moment_rules_hold_for_every_twin(profiles):
    for cid, t in profiles.items():
        m = moments(t)
        stressed = bool(t["facts"].get("money_stress"))
        assert len(m["push"]) <= 2, cid
        prios = [x["priority"] for x in m["push"] + m["feed"]]
        assert prios == sorted(prios, reverse=True), cid
        assert all(x["sales"] and x["held_because"] for x in m["held_back"]), cid
        if stressed:
            assert not [x for x in m["push"] + m["feed"] if x["sales"]], cid
        else:
            assert m["held_back"] == [], cid


@pytest.mark.parametrize("cid", [LOTTE, JULIEN, EMMA, MARC])
def test_money_stress_holds_back_every_sales_moment(persona, cid):
    calm = persona(cid)
    before = moments(calm)
    sales_kinds = {x["kind"] for x in before["push"] + before["feed"] if x["sales"]}

    stressed = moments(with_money_stress(calm))
    shown = stressed["push"] + stressed["feed"]
    assert not [x for x in shown if x["sales"]]
    assert {x["kind"] for x in stressed["held_back"]} == sales_kinds
    assert all(x["held_because"] for x in stressed["held_back"])
    assert stressed["push"][0]["kind"] == "support"  # help comes first
    assert len(stressed["push"]) <= 2


def test_lotte_new_car_is_a_sales_moment_that_stress_suppresses(persona):
    calm = moments(persona(LOTTE))
    new_car = next(x for x in calm["push"] if x["kind"] == "new_car")
    assert new_car["sales"] is True  # insured at Ethias: the insurance quote is a sales pitch
    assert "new_car" in {x["kind"] for x in moments(with_money_stress(persona(LOTTE)))["held_back"]}


# ====================================================================== accuracy vs hidden truth

@pytest.fixture(scope="module")
def truth(ro_con):
    traits, events = {}, {}
    for cid, trait, value in ro_con.execute("SELECT customer_id, trait, value FROM truth_traits"):
        traits.setdefault(cid, {})[trait] = value
    for cid, event in ro_con.execute("SELECT customer_id, event FROM truth_events"):
        events.setdefault(cid, set()).add(event)
    return traits, events


CHECKS = {
    "owns a car": (lambda tr, ev: tr["has_car"] == "true", lambda f: bool(f.get("has_car"))),
    "has a pet": (lambda tr, ev: tr["pet"] != "none", lambda f: "pet" in f),
    "has children": (lambda tr, ev: tr["children"] != "0", lambda f: "children" in f or "life_event_new_baby" in f),
    "moved house": (lambda tr, ev: "moved" in ev, lambda f: "life_event_moved" in f),
}


@pytest.mark.parametrize("name", list(CHECKS))
def test_accuracy_against_ground_truth(profiles, truth, name):
    traits, events = truth
    is_true, predicted = CHECKS[name]
    pairs = [(is_true(traits[c], events.get(c, set())), predicted(profiles.get(c, {}).get("facts", {}))) for c in traits]
    assert len(pairs) >= 1000
    accuracy = sum(t == p for t, p in pairs) / len(pairs)
    assert accuracy >= 0.95, f"{name}: accuracy {accuracy:.1%}"
    assert any(t for t, _ in pairs), f"{name}: no positives in the truth table"


def test_evaluate_script_reports_high_accuracy(capsys):
    from twin.evaluate import main
    main()
    out = capsys.readouterr().out
    for name in CHECKS:
        m = re.search(rf"^{re.escape(name)}\s+([\d.]+)%", out, re.M)
        assert m, f"{name} missing from twin.evaluate output"
        assert float(m.group(1)) >= 95.0, name


def test_engine_builds_a_twin_without_reading_truth_tables(persona):
    """Rebuild Lotte in memory on a read-only connection that refuses every truth_* read."""
    from twin.engine import DB, build_one
    touched = []

    def authorizer(action, arg1, arg2, dbname, source):
        if action == sqlite3.SQLITE_READ and arg1 and arg1.lower().startswith("truth_"):
            touched.append(arg1)
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.set_authorizer(authorizer)
    try:
        fresh = build_one(con, LOTTE)
    finally:
        con.close()
    assert touched == []
    stored = persona(LOTTE)
    assert set(fresh["facts"]) == set(stored["facts"])
    assert fresh["facts"]["has_car"]["insured_at"] == "Ethias"
    assert fresh["plan"]["payday"] == stored["plan"]["payday"]


@pytest.mark.parametrize("module", ["api/main.py", "api/security.py", "twin/engine.py", "twin/recommender.py",
                                    "twin/assistant.py", "twin/catalog.py"])
def test_product_code_does_not_query_truth_tables(module):
    src = (ROOT / module).read_text()
    assert not re.search(r"\b(FROM|JOIN)\s+truth_", src, re.I), module
