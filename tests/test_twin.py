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
from twin.recommender import CREDIT_VARIANTS, NO_ROOM, _affordable_loan, _nice_date, moments, page

pytestmark = pytest.mark.needs_db

ROOT = Path(__file__).resolve().parent.parent
LOTTE, JULIEN, EMMA, MARC = 1, 2, 3, 4
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


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
    """Production boundary: an inferred birth never drives family content; the customer's confirmation does."""
    from twin.feedback import apply_feedback
    t = persona(JULIEN)
    assert "life_event_new_baby" in facts(t)
    unconfirmed = page(t, "family")
    assert unconfirmed["highlight"]["id"] != "hospital_insurance"
    assert not any(w in unconfirmed["highlight"]["reason"].lower() for w in ("baby", "born", "birth", "hospital"))
    assert "new_baby" not in {m["kind"] for part in ("push", "feed") for m in moments(t)[part]}
    confirmed = apply_feedback(t, [("life_event_new_baby", 1, None)])
    block = page(confirmed, "family")
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
            if hl["id"] == "support":  # money stress, credit topic: a "payday plan first" card, every loan collapsed
                assert block.get("support_first") is True and topic == "car_loan", (cid, topic)
                assert hl["name"] and hl["summary"] and hl["features"], cid
            else:
                assert hl["id"] in cat["variants"], (cid, topic, hl["id"])
            assert isinstance(hl["reason"], str), (cid, topic)
            assert {b["key"] for b in hl["because"]} <= set(t["facts"]), (cid, topic)
            assert sorted(a["id"] for a in block["alternatives"]) == sorted(set(cat["variants"]) - {hl["id"]}), (cid, topic)
    assert personalized > len(profiles) * 3


def test_every_personalized_highlight_explains_itself(profiles):
    """Regression: with no room in the budget, _pick_car_loan used to fall through to 'new_car_loan' with an empty reason."""
    unexplained = [(cid, topic, block["highlight"]["id"]) for cid, t in profiles.items() for topic in CATALOG
                   for block in [page(t, topic)] if block["personalized"] and not block["highlight"]["reason"].strip()]
    assert unexplained == []


def test_car_loan_with_no_budget_room_highlights_the_cheapest_loan_honestly(profiles):
    """free_to_spend <= 0 and no car-specific reason: the smallest (second-hand) loan, never 'new car', with an honest reason."""
    no_room = {cid: t for cid, t in profiles.items() if _affordable_loan(t) is None and not t["facts"].get("money_stress")}
    assert len(no_room) > 100
    fall_through = 0
    for cid, t in no_room.items():
        hl = page(t, "car_loan")["highlight"]
        assert hl["id"] != "new_car_loan", cid
        assert "comfortably" not in hl["reason"], cid  # no promise the budget can't keep
        if hl["id"] == "used_car_loan" and "has_car" not in t["facts"]:
            fall_through += 1
            assert hl["reason"] == NO_ROOM, cid
    assert fall_through > 50


def test_car_loan_no_room_reason_for_a_single_twin(persona):
    t = persona(EMMA)
    t["facts"].pop("has_car", None)
    t["plan"]["free_to_spend"] = -120
    hl = page(t, "car_loan")["highlight"]
    assert hl["id"] == "used_car_loan" and hl["reason"] == NO_ROOM
    assert "no room" in hl["reason"] and "payday plan" in hl["reason"]


def test_rejected_car_stops_driving_car_pages_and_moments(persona):
    t = reject(persona(LOTTE), "has_car")
    assert page(t, "car_insurance")["personalized"] is False
    kinds = {m["kind"] for part in moments(t).values() for m in part}
    assert "new_car" not in kinds and "salary_plan" in kinds


def test_rejected_financial_buffer_does_not_crash_savings_page(persona):
    """Regression: _pick_savings formatted buffer['value'] after the customer rejected financial_buffer -> TypeError."""
    block = page(reject(persona(MARC), "financial_buffer"), "savings")
    assert block["topic"] == "savings" and block["personalized"]
    hl = block["highlight"]
    assert hl["id"] == "savings_account" and hl["reason"].strip()  # buffer unknown: build the base, no investment pitch
    assert "financial_buffer" not in {b["key"] for b in hl["because"]}


def test_highlight_never_cites_a_rejected_fact(persona):
    """Regression: page() built `because` from the picker's keys without skipping rejected facts."""
    for cid, key, topic in ((LOTTE, "housing", "home"), (LOTTE, "financial_buffer", "savings"),
                            (JULIEN, "income", "car_loan")):
        block = page(reject(persona(cid), key), topic)
        cited = {b["key"] for b in (block["highlight"] or {}).get("because", [])}
        assert key not in cited, (cid, key, topic)
        assert block["highlight"]["reason"].strip(), (cid, key, topic)  # still highlighted, still explained


@pytest.mark.parametrize("cid", [LOTTE, JULIEN, EMMA, MARC])
def test_any_single_rejected_fact_is_tolerated_everywhere(persona, cid):
    """Every fact the twin has, rejected on its own: every picker and moments() keep working, never cite it."""
    for key in list(persona(cid)["facts"]):
        t = reject(persona(cid), key)
        for topic in CATALOG:
            block = page(t, topic)
            if block["personalized"]:
                assert block["highlight"]["reason"].strip(), (cid, key, topic)
                assert key not in {b["key"] for b in block["highlight"]["because"]}, (cid, key, topic)
        m = moments(t)
        assert all(x["body"].strip() for part in m.values() for x in part), (cid, key)


@pytest.mark.parametrize("cid", [LOTTE, JULIEN, EMMA, MARC])
def test_every_fact_rejected_at_once_is_tolerated(persona, cid):
    t = persona(cid)
    for key in list(t["facts"]):
        reject(t, key)
    for topic in CATALOG:
        block = page(t, topic)
        if block["personalized"]:
            assert block["highlight"]["reason"].strip() and block["highlight"]["because"] == [], (cid, topic)
    assert moments(t)["held_back"] == []


def test_bare_twin_without_facts_or_plan_is_tolerated():
    bare = dict(facts={}, plan=None, recurring=[], kbc_products=[], age=None)
    for topic in CATALOG:
        block = page(bare, topic)
        assert block["topic"] == topic
        if block["personalized"]:
            assert block["highlight"]["reason"].strip() and block["highlight"]["because"] == [], topic
    assert moments(bare) == dict(push=[], feed=[], held_back=[])


# ====================================================================== money stress: support first on product pages

def test_money_stress_makes_every_page_support_first(persona):
    for cid in (LOTTE, JULIEN, EMMA, MARC):
        calm, stressed = persona(cid), with_money_stress(persona(cid))
        for topic in CATALOG:
            assert "support_first" not in page(calm, topic), (cid, topic)
            block = page(stressed, topic)
            assert block["support_first"] is True, (cid, topic)
            if block["personalized"]:
                hl = block["highlight"]
                assert hl["id"] not in CREDIT_VARIANTS, (cid, topic, hl["id"])
                assert hl["reason"].strip(), (cid, topic)
                assert "quote in 2 minutes" not in hl["reason"] and "comfortably" not in hl["reason"], (cid, topic)
                assert "money_stress" in {b["key"] for b in hl["because"]}, (cid, topic)


def test_money_stress_car_loan_shows_no_loan(persona):
    block = page(with_money_stress(persona(LOTTE)), "car_loan")
    assert block["personalized"] is True and block["support_first"] is True
    hl = block["highlight"]
    assert hl["id"] == "support" and hl["id"] not in CATALOG["car_loan"]["variants"]
    assert hl["reason"].startswith("Let's first get your payday plan back in balance")
    assert {a["id"] for a in block["alternatives"]} == set(CATALOG["car_loan"]["variants"])  # all loans, collapsed


def test_money_stress_home_and_savings_never_sell_credit_or_investing(persona):
    for cid in (LOTTE, JULIEN, EMMA, MARC):
        t = with_money_stress(persona(cid))
        assert page(t, "home")["highlight"]["id"] == "home_insurance", cid
        assert page(t, "savings")["highlight"]["id"] == "savings_account", cid
        car_ins = page(t, "car_insurance")
        assert not car_ins["personalized"] or car_ins["highlight"]["id"] != "omnium", cid


def test_rejected_money_stress_is_not_support_first(persona):
    t = reject(with_money_stress(persona(LOTTE)), "money_stress")
    assert page(t, "car_loan") == page(persona(LOTTE), "car_loan")
    assert page(None, "car_loan").get("support_first") is None  # anonymous visitors: nothing to flag


def test_no_stressed_twin_is_ever_offered_credit(profiles):
    stressed = 0
    for cid, t in profiles.items():
        is_stressed = bool(t["facts"].get("money_stress")) and not t["facts"]["money_stress"].get("rejected_by_customer")
        stressed += is_stressed
        for topic in CATALOG:
            block = page(t, topic)
            assert block.get("support_first", False) is is_stressed, (cid, topic)
            if is_stressed and block["personalized"]:
                assert block["highlight"]["id"] not in CREDIT_VARIANTS | {"pension_savings", "investment_plan", "omnium"}, (cid, topic)
    assert stressed > 100


# ====================================================================== friendly dates in customer-facing text

@pytest.mark.parametrize("raw,nice", [
    ("2026-10-23", "Fri 23 Oct"),            # upcoming (payday): weekday, no year
    ("2026-09-30", "Wed 30 Sep"),            # today counts as upcoming
    ("2027-01-05", "Tue 5 Jan 2027"),        # upcoming, but next year
    ("2026-06-13", "13 Jun 2026"),           # past: day month year
    ("before 2025-10-01", "before 1 Oct 2025"),
    ("Ethias €518 expected 2026-11-02", "Ethias €518 expected Mon 2 Nov"),
    ("2026-13-45", "2026-13-45"),            # not a real date: left alone
    ("Deloitte Belgium", "Deloitte Belgium"),
    (None, ""),
    (date(2026, 10, 23), "Fri 23 Oct"),
])
def test_nice_date(raw, nice):
    assert _nice_date(raw) == nice


def test_demo_texts_use_friendly_dates(persona):
    lotte = persona(LOTTE)
    push = {m["kind"]: m for m in moments(lotte)["push"]}
    assert push["salary_plan"]["body"].startswith("€2,850 arrives on Fri 23 Oct. Bills €1,458")
    assert lotte["plan"]["payday"] == "2026-10-23"  # the structured field stays ISO
    assert "You bought your car on 13 Jun 2026 with your own savings" in page(lotte, "car_loan")["highlight"]["reason"]
    from twin.feedback import apply_feedback  # family texts only after the customer confirms (production boundary)
    julien = apply_feedback(persona(JULIEN), [("life_event_new_baby", 1, None)])
    assert "(born around 21 Jul 2026)" in page(julien, "family")["highlight"]["reason"]
    assert page(persona(EMMA), "home")["highlight"]["reason"].startswith("You moved on 18 Aug 2026:")


def test_customer_facing_text_never_shows_iso_dates(profiles):
    for cid, t in profiles.items():
        m = moments(t)
        texts = [x[k] for part in m.values() for x in part for k in ("title", "body")]
        for topic in CATALOG:
            hl = page(t, topic)["highlight"]
            if hl:
                texts += [hl["reason"], *(b["summary"] for b in hl["because"])]
        assert not [x for x in texts if ISO_DATE.search(x)], cid


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
