"""Life moments & gaps: life-moment checklists, coverage gaps, benefits hints, turning 25 and the moment feed.

Covers twin/checklists.py, twin/gaps.py, twin/benefits.py and api/routes_life.py. The /api/me/* routes are
mounted onto api.main.app by the `life_api` fixture only when api/main.py doesn't include them yet.

Safety: DB tests are `needs_db` (skipped on a fresh clone); logins and the ops login go through conftest's redacted
helpers, so no password or token can show up in assertion output; feedback and ops-audit rows written here are
deleted afterwards. The whole-population test reads twin_profile as built (no customer feedback).

Run:  .venv/bin/python -m pytest tests/test_life.py -q
"""
import copy
import inspect
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from api.security import issue_token  # stdlib only, no database access
from twin.benefits import benefits, benefits_review, turning_25
from twin.checklists import (HOUSEHOLD_PROMPT, checklists, household_prompt, life_checklists, life_moments,
                             load_life_tx, support_first)
from twin.feedback import apply_feedback
from twin.gaps import coverage_gaps, coverage_review

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "kbc_twin.db"
OPS_CREDS = ROOT / "data" / "ops_credentials.txt"
LOTTE, JULIEN, EMMA, MARC, JENS = 1, 2, 3, 4, 113
PERSONAS = (LOTTE, JULIEN, EMMA, MARC, JENS)
PATHS = ("/api/me/life-checklists", "/api/me/coverage-gaps", "/api/me/benefits")
CHECKLISTS, GAPS, BENEFITS = PATHS
MOMENT_KEYS = {"kind", "priority", "title", "body", "topic", "sales"}
LIFE_KINDS = {"life_checklist", "coverage_gap", "benefit_hint", "turning_25", "household_change_prompt"}
STATUSES = {"done", "todo", "unknown"}
SEVERITIES = {"essential", "recommended", "nice-to-have"}
PROMISE = "without making you repeat yourself"

# Special-category wording that must never appear, even after the customer confirmed a household change.
HEALTH_WORDS = re.compile(r"pregnan|zwanger|enceinte|grossesse|expecting|matern|pr[ée]natal|bevalling|accouchement|"
                          r"deliver|obstetr|gyn[ae]|medic|health|ziekenhuis|h[oô]pital|hospital(?!isation)", re.I)
# Before confirmation not even the household change itself may show (production-safe path).
FAMILY_WORDS = re.compile(r"bab(y|ies)|birth(?!day)|naissance|geboorte|newborn|little one|\bchild|pregnan|hospital", re.I)

needs_db = pytest.mark.needs_db


# ---------------------------------------------------------------------- fixtures & helpers

@pytest.fixture(scope="module")
def life_api(api_main):
    """api.main.app with the life routes mounted (a no-op once api/main.py includes the router itself)."""
    from api.routes_life import router
    if not set(PATHS) <= {getattr(r, "path", "") for r in api_main.app.routes}:
        api_main.app.include_router(router)
    return api_main


@pytest.fixture
def baby_feedback_cleanup():
    """Delete the life_event_new_baby confirmation a test writes for Julien (conftest's guard does too)."""
    con = sqlite3.connect(DB_PATH, timeout=30)
    start = con.execute("SELECT COALESCE(MAX(rowid), 0) FROM twin_feedback").fetchone()[0]
    con.close()
    yield
    con = sqlite3.connect(DB_PATH, timeout=30)
    try:
        con.execute("DELETE FROM twin_feedback WHERE rowid > ? AND customer_id = ? AND fact = 'life_event_new_baby'",
                    (start, JULIEN))
        con.commit()
    finally:
        con.close()


def _get(client, path, headers):
    r = client.get(path, headers=headers)
    assert r.status_code == 200, f"GET {path}: HTTP {r.status_code}"
    return r.json()


def _events(body):
    return {c["event"]: c for c in body["checklists"]}


def _statuses(checklist):
    return {i["id"]: i["status"] for i in checklist["items"]}


def _raw_twin(con, cid):
    return json.loads(con.execute("SELECT profile_json FROM twin_profile WHERE customer_id = ?", (cid,)).fetchone()[0])


def _evidence_ids(checklist_list):
    return {t for c in checklist_list for i in c["items"] for t in i["evidence"]["tx_ids"]}


def _own(con, cid, tx_ids):
    """How many of tx_ids really are this customer's transactions."""
    if not tx_ids:
        return 0
    marks = ",".join("?" * len(tx_ids))
    return con.execute(f"SELECT COUNT(*) FROM transactions WHERE customer_id = ? AND tx_id IN ({marks})",
                       (cid, *tx_ids)).fetchone()[0]


def _ops_login_body(redacted):
    m = re.search(r"username=(\S+)\s+password=(\S+)", OPS_CREDS.read_text())
    return (m.group(1), redacted(username=m.group(1), password=m.group(2))) if m else (None, None)


# ---------------------------------------------------------------------- pure rules (no database)

BASE = dict(customer_id=0, region="Flanders", language="nl", age=30, kbc_products=["current_account"], plan=None,
            recurring=[])


def _twin(**facts):
    return dict(BASE, facts={k: dict(key=k, **v) for k, v in facts.items()})


def test_household_prompt_is_neutral():
    assert HOUSEHOLD_PROMPT["kind"] == "household_change_prompt" and HOUSEHOLD_PROMPT["sales"] is False
    assert HOUSEHOLD_PROMPT["title"] == "Has your household changed?"
    assert "Tell us only if you want KBC to take it into account" in HOUSEHOLD_PROMPT["body"]
    assert not FAMILY_WORDS.search(json.dumps(HOUSEHOLD_PROMPT))


def test_household_checklist_only_after_confirmation():
    event = dict(value="2026-08-01", since="2026-08-01", confidence=0.9, summary="", evidence=[], implies=[])
    unconfirmed = _twin(life_event_new_baby=event)
    assert checklists(None, 0, unconfirmed, tx=[]) == []
    assert household_prompt(unconfirmed)["kind"] == "household_change_prompt"
    moments = life_moments(None, 0, unconfirmed, tx=[])
    assert [m["kind"] for m in moments] == ["household_change_prompt"] and not moments[0]["sales"]
    assert not FAMILY_WORDS.search(json.dumps([moments, coverage_review(None, 0, unconfirmed, tx=[]),
                                               benefits_review(None, 0, unconfirmed, tx=[])]))

    confirmed = apply_feedback(unconfirmed, [("life_event_new_baby", 1, None)])
    [baby] = checklists(None, 0, confirmed, tx=[])
    assert baby["event"] == "new_baby" and household_prompt(confirmed) is None
    assert not HEALTH_WORDS.search(json.dumps(baby))

    rejected = apply_feedback(unconfirmed, [("life_event_new_baby", 0, None)])
    assert checklists(None, 0, rejected, tx=[]) == [] and household_prompt(rejected) is None


def test_old_life_events_are_left_alone():
    old = _twin(life_event_moved=dict(value="2025-11-02", since="2025-11-02", bought_home=False))
    assert checklists(None, 0, old, tx=[]) == []


def test_money_stress_keeps_only_essential_gaps():
    facts = dict(has_car=dict(value=True, summary="12 fuel payments", insured_at=None),
                 housing=dict(value="renting", monthly=700), pet=dict(value="dog"),
                 travels=dict(value=3))
    calm = {g["id"]: g for g in coverage_gaps(None, 0, _twin(**facts), tx=[])}
    assert {"car_uninsured", "home_uninsured_tenant", "family_liability", "travel_cover"} <= set(calm)
    assert calm["car_uninsured"]["severity"] == calm["home_uninsured_tenant"]["severity"] == "essential"
    assert not calm["car_uninsured"]["sales"] and calm["home_uninsured_tenant"]["source"].startswith("https://")

    stressed = _twin(**facts, money_stress=dict(value=True))
    review = coverage_review(None, 0, stressed, tx=[])
    assert review["support_first"] is True
    assert {g["id"] for g in review["gaps"]} == {"car_uninsured", "home_uninsured_tenant"}
    assert all(g["severity"] == "essential" and g["support_first"] and not g["sales"] for g in review["gaps"])
    assert not [m for m in life_moments(None, 0, stressed, tx=[]) if m["sales"]]
    # the customer said the stress fact is wrong: back to the normal rules
    unstressed = apply_feedback(stressed, [("money_stress", 0, None)])
    assert "family_liability" in {g["id"] for g in coverage_gaps(None, 0, unstressed, tx=[])}


def test_car_insured_elsewhere_is_a_compare_item_not_a_gap():
    t = _twin(has_car=dict(value=True, summary="10 fuel payments", insured_at="Ethias"))
    [item] = coverage_gaps(None, 0, t, tx=[])
    assert (item["id"], item["kind"], item["severity"]) == ("car_insured_elsewhere", "compare", "nice-to-have")
    assert PROMISE in item["why"]
    assert coverage_gaps(None, 0, dict(t, kbc_products=["car_insurance"]), tx=[]) == []


def test_travel_cover_says_not_in_our_catalogue():
    [gap] = coverage_gaps(None, 0, _twin(travels=dict(value=3)), tx=[])
    assert gap["id"] == "travel_cover" and "not in our catalogue" in gap["why"] and gap["topic"] is None


def test_turning_25_highlights_one_option():
    t = turning_25(dict(BASE, age=24, facts={}))
    assert t["turns_25_in"] == 2027 and t["sales"] is False and t["source"].startswith("https://www.kbc.be/")
    assert t["highlight"]["id"] == "basic_account" and len(t["alternatives"]) == 1
    assert "4.25" in t["body"] and "2.50" in t["highlight"]["reason"]
    traveller = _twin(travels=dict(value=2))
    assert turning_25(dict(traveller, age=25))["highlight"]["id"] == "plus_account"
    assert turning_25(dict(traveller, age=25))["turns_25_in"] == 2026
    stressed = _twin(travels=dict(value=2), money_stress=dict(value=True))
    assert turning_25(dict(stressed, age=24))["highlight"]["id"] == "basic_account"  # cheapest when money is tight
    assert turning_25(dict(BASE, age=23, facts={})) is None and turning_25(dict(BASE, age=26, facts={})) is None
    assert turning_25(dict(BASE, age=24, kbc_products=[], facts={})) is None


def test_benefit_hints_region_and_sources():
    student = _twin(employment=dict(value="student"), income=dict(value=700, kind="student"))
    for region, lang, host in (("Flanders", "nl", "vlaanderen.be"), ("Wallonia", "fr", "cfwb.be"),
                               ("Brussels", "fr", "cfwb.be"), ("Brussels", "nl", "vlaanderen.be")):
        [hint] = benefits(None, 0, dict(student, region=region, language=lang), tx=[])
        assert hint["id"] == "study_grant" and host in hint["source"] and hint["region"] == region
    owner = _twin(employment=dict(value="employee"), housing=dict(value="owner_with_mortgage"))
    ids = {h["id"] for h in benefits(None, 0, owner, tx=[])}
    assert ids == {"pension_tax", "renovation_premium"}
    assert {h["id"] for h in benefits(None, 0, dict(owner, region="Wallonia"), tx=[])} == {"pension_tax"}
    stressed = _twin(employment=dict(value="employee"), housing=dict(value="owner"), money_stress=dict(value=True))
    assert benefits(None, 0, stressed, tx=[]) == []  # nothing that asks for new spending
    short = dict(owner, plan=dict(free_to_spend=-388, free_per_week=-90))  # a plan that is already short (Marc)
    assert benefits(None, 0, short, tx=[]) == []


def test_functions_tolerate_empty_twins():
    for twin in (None, {}, dict(BASE, facts={}), dict(BASE, facts={"life_event_moved": {"key": "x", "value": 3}})):
        assert isinstance(life_checklists(None, 0, twin, tx=[])["checklists"], list)
        assert isinstance(coverage_review(None, 0, twin, tx=[])["gaps"], list)
        assert isinstance(benefits_review(None, 0, twin, tx=[])["benefits"], list)
        assert isinstance(life_moments(None, 0, twin, tx=[]), list)


def test_router_module_does_not_import_api_main():
    """api.main will `include_router` this module at its end: importing it first must not import api.main."""
    code = "import sys, api.routes_life; assert 'api.main' not in sys.modules"
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]


# ---------------------------------------------------------------------- API: personas

@needs_db
def test_emma_gets_move_and_first_job_checklists(client, login, life_api):
    body = _get(client, CHECKLISTS, login(EMMA))
    assert PROMISE in body["intro"] and body["household_prompt"] is None
    events = _events(body)
    assert {"moved", "first_job"} <= set(events)
    moved = _statuses(events["moved"])
    assert moved["movers"] == moved["mail_forwarding"] == moved["energy"] == "done"
    assert moved["home_insurance"] == "todo" and moved["municipality"] == "unknown"
    assert events["moved"]["summary"] == "3 of 5 things done for your move — 2 left"
    job = _statuses(events["first_job"])
    assert job["first_salary"] == job["payday_plan"] == job["buffer"] == "done"
    for c in body["checklists"]:
        assert set(_statuses(c).values()) <= STATUSES and c["done"] + c["left"] == c["total"]
        for i in c["items"]:
            if i["id"] in ("movers", "mail_forwarding", "energy", "first_salary"):
                assert i["evidence"]["tx_ids"], i["id"]
            if i["topic"]:
                assert client.get(f"/api/experience/{i['topic']}").status_code == 200


@needs_db
def test_julien_unconfirmed_gets_only_the_neutral_prompt(client, login, life_api, api_main, ro_con):
    h = login(JULIEN)
    bodies = {p: _get(client, p, h) for p in PATHS}
    assert "new_baby" not in _events(bodies[CHECKLISTS])
    for p in PATHS:
        prompt = bodies[p]["household_prompt"]
        assert prompt and prompt["kind"] == "household_change_prompt" and prompt["sales"] is False, p
    assert not [g for g in bodies[GAPS]["gaps"] if g["id"].startswith("newborn")]
    assert {g["id"] for g in bodies[GAPS]["gaps"]} >= {"family_liability"}  # his dog: not a household fact
    moments = life_moments(ro_con, JULIEN, api_main.load_twin(ro_con, JULIEN))
    assert "household_change_prompt" in {m["kind"] for m in moments}
    assert not FAMILY_WORDS.search(json.dumps([bodies, moments], ensure_ascii=False))


@needs_db
def test_julien_confirmed_gets_the_household_checklist(client, login, life_api, api_main, ro_con, baby_feedback_cleanup):
    h = login(JULIEN)
    r = client.post("/api/me/facts/life_event_new_baby/feedback", headers=h, json={"correct": True})
    assert r.status_code == 200
    body = _get(client, CHECKLISTS, h)
    assert body["household_prompt"] is None
    baby = _events(body)["new_baby"]
    status = _statuses(baby)
    assert status["birth_allowance"] == status["child_benefit"] == "done"
    assert status["family_liability"] == "todo" and baby["items"][0]["evidence"]["tx_ids"]
    gaps = _get(client, GAPS, h)
    ids = {g["id"]: g for g in gaps["gaps"]}
    assert "newborn_hospitalisation_cover" in ids and "your children" in ids["family_liability"]["why"]
    moments = life_moments(ro_con, JULIEN, api_main.load_twin(ro_con, JULIEN))
    assert "household_change_prompt" not in {m["kind"] for m in moments}
    blob = json.dumps([body, gaps, _get(client, BENEFITS, h), moments], ensure_ascii=False)
    assert not HEALTH_WORDS.search(blob), HEALTH_WORDS.search(blob).group(0)
    cited = sorted(_evidence_ids(body["checklists"]))
    assert _own(ro_con, JULIEN, cited) == len(cited)
    marks = ",".join("?" * len(cited))
    subs = {s for (s,) in ro_con.execute(f"SELECT DISTINCT subcategory FROM transactions WHERE customer_id = ? "
                                         f"AND tx_id IN ({marks})", (JULIEN, *cited))}
    assert not subs & {"hospital", "pharmacy", "doctor", "baby", "mutuality"}  # never a health-related payment


@needs_db
def test_lotte_new_car_checklist_and_compare_not_gap(client, login, life_api):
    h = login(LOTTE)
    car = _events(_get(client, CHECKLISTS, h))["new_car"]
    insured = next(i for i in car["items"] if i["id"] == "insured")
    assert insured["status"] == "done" and "Ethias" in insured["evidence"]["text"] and insured["evidence"]["tx_ids"]
    assert _statuses(car)["registration_tax"] == "done" and _statuses(car)["upkeep_reserve"] == "done"
    gaps = {g["id"]: g for g in _get(client, GAPS, h)["gaps"]}
    assert "car_uninsured" not in gaps
    compare = gaps["car_insured_elsewhere"]
    assert compare["kind"] == "compare" and compare["severity"] == "nice-to-have" and "Not a gap" in compare["why"]
    assert not [g for g in gaps.values() if g["kind"] == "gap" and "has_car" in g["because"]]


@needs_db
def test_jens_money_stress_support_first_and_no_sales(client, login, life_api, api_main, ro_con):
    h = login(JENS)
    gaps = _get(client, GAPS, h)
    assert gaps["support_first"] is True
    assert all(g["severity"] == "essential" and g["support_first"] and not g["sales"] for g in gaps["gaps"])
    assert "car_insured_elsewhere" not in {g["id"] for g in gaps["gaps"]}  # no "compare" pitch under money stress
    hints = _get(client, BENEFITS, h)["benefits"]
    assert hints and not {x["id"] for x in hints} & {"pension_tax", "first_home_duty", "renovation_premium"}
    assert all(x["sales"] is False for x in hints)
    body = _get(client, CHECKLISTS, h)
    assert "moved" in _events(body)
    assert not [i for c in body["checklists"] for i in c["items"] if i["id"] == "pension_savings"]
    moments = life_moments(ro_con, JENS, api_main.load_twin(ro_con, JENS))
    assert moments and not [m for m in moments if m["sales"]]
    assert all(set(m) == MOMENT_KEYS for m in moments)


@needs_db
def test_rejected_life_event_gives_no_checklist(ro_con):
    twin, tx = _raw_twin(ro_con, EMMA), load_life_tx(ro_con, EMMA)
    assert {"moved", "first_job"} <= {c["event"] for c in checklists(ro_con, EMMA, twin, tx=tx)}
    rejected = apply_feedback(twin, [("life_event_moved", 0, "not me")])  # exactly what api.main.load_twin does
    assert {c["event"] for c in checklists(ro_con, EMMA, rejected, tx=tx)} == {"first_job"}
    assert not [g for g in coverage_gaps(ro_con, EMMA, rejected, tx=tx) if "life_event_moved" in g["because"]]
    assert "Your move" not in json.dumps(life_moments(ro_con, EMMA, rejected, tx=tx))
    job_rejected = apply_feedback(twin, [("life_event_first_job", 0, None)])
    assert {c["event"] for c in checklists(ro_con, EMMA, job_rejected, tx=tx)} == {"moved"}


@needs_db
def test_every_benefit_hint_has_an_official_source(client, login, life_api):
    for cid in PERSONAS:
        body = _get(client, BENEFITS, login(cid))
        assert body["note"] and body["region"] in ("Flanders", "Wallonia", "Brussels")
        for hint in body["benefits"]:
            assert hint["source"].startswith("https://") and hint["source_name"], (cid, hint["id"])
            assert hint["check"] == "Check your eligibility" and hint["body"].endswith("Check your eligibility.")
            assert hint["sales"] is False and hint["region"]


@needs_db
def test_life_endpoints_require_a_customer_token(client, life_api, redacted):
    for path in PATHS:
        r = client.get(path)
        assert r.status_code == 401 and r.headers.get("www-authenticate", "").lower().startswith("bearer")
        assert client.get(path, headers=redacted(Authorization="Bearer garbage")).status_code == 401
        for ops_token in (issue_token("advisor", role="ops"), issue_token("1", role="ops")):
            assert client.get(path, headers=redacted(Authorization=f"Bearer {ops_token}")).status_code == 401


@needs_db
def test_real_ops_login_token_is_rejected(client, life_api, redacted):
    if not OPS_CREDS.exists():
        pytest.skip("data/ops_credentials.txt not found: run `python -m api.seed_ops`")
    username, body = _ops_login_body(redacted)
    if body is None:
        pytest.skip("data/ops_credentials.txt has no login line")
    con = sqlite3.connect(DB_PATH, timeout=30)
    start = con.execute("SELECT COALESCE(MAX(rowid), 0) FROM ops_audit").fetchone()[0]
    con.close()
    try:
        r = client.post("/api/ops/login", json=body)
        assert r.status_code == 200, f"ops login failed with HTTP {r.status_code}"
        ops = redacted(Authorization=f"Bearer {r.json()['token']}")
        for path in PATHS:
            assert client.get(path, headers=ops).status_code == 401
    finally:
        con = sqlite3.connect(DB_PATH, timeout=30)
        con.execute("DELETE FROM ops_audit WHERE rowid > ? AND username = ?", (start, username))
        con.commit()
        con.close()


@needs_db
def test_customer_id_in_query_is_ignored(client, login, life_api):
    body = _get(client, f"{CHECKLISTS}?customer_id={LOTTE}", login(EMMA))
    assert "moved" in _events(body) and "new_car" not in _events(body)


@needs_db
def test_evidence_only_cites_the_customers_own_transactions(client, login, life_api, api_main, ro_con):
    for cid in PERSONAS:
        cited = sorted(_evidence_ids(_get(client, CHECKLISTS, login(cid))["checklists"]))
        assert _own(ro_con, cid, cited) == len(cited), cid


@needs_db
def test_life_moments_fit_the_recommender_feed(api_main, ro_con):
    """Once twin.recommender.moments() takes `extra`, life moments slot into push/feed with the same rules."""
    from twin.recommender import moments
    if "extra" not in inspect.signature(moments).parameters:
        pytest.skip("twin.recommender.moments() has no `extra` parameter yet")
    for cid in PERSONAS:
        twin = api_main.load_twin(ro_con, cid)
        m = moments(twin, extra=life_moments(ro_con, cid, twin))
        assert len(m["push"]) <= 2
        prios = [x["priority"] for x in m["push"] + m["feed"]]
        assert prios == sorted(prios, reverse=True)
        if support_first(twin):
            assert not [x for x in m["push"] + m["feed"] if x["sales"]], cid


# ---------------------------------------------------------------------- the whole population

@needs_db
def test_population_life_features_hold_their_rules(ro_con):
    rows = ro_con.execute("SELECT customer_id, profile_json FROM twin_profile ORDER BY customer_id").fetchall()
    assert len(rows) >= 1000
    cited, seen = [], {"checklists": 0, "stressed": 0, "turning_25": 0, "hints": 0}
    for cid, profile in rows:
        twin = json.loads(profile)
        tx = load_life_tx(ro_con, cid)
        cl, gr = life_checklists(ro_con, cid, twin, tx=tx), coverage_review(ro_con, cid, twin, tx=tx)
        br, ms = benefits_review(ro_con, cid, twin, tx=tx), life_moments(ro_con, cid, twin, tx=tx)
        blob = json.dumps([cl, gr, br, ms], ensure_ascii=False)
        # production-safe: nobody confirmed a household change in twin_profile, so nothing family-related shows
        assert not FAMILY_WORDS.search(blob), (cid, FAMILY_WORDS.search(blob).group(0))
        assert all(c["event"] != "new_baby" for c in cl["checklists"])
        for c in cl["checklists"]:
            assert set(_statuses(c).values()) <= STATUSES and c["done"] + c["left"] == c["total"] and c["items"]
            cited += [(cid, t) for i in c["items"] for t in i["evidence"]["tx_ids"]]
        assert all(g["severity"] in SEVERITIES for g in gr["gaps"])
        for m in ms:
            assert set(m) == MOMENT_KEYS and m["kind"] in LIFE_KINDS and isinstance(m["sales"], bool)
        for hint in br["benefits"]:
            assert hint["source"].startswith("https://") and hint["sales"] is False
        if support_first(twin):
            seen["stressed"] += 1
            assert gr["support_first"] is True
            assert not [m for m in ms if m["sales"]], cid
            assert all(g["severity"] == "essential" and g["support_first"] and not g["sales"] for g in gr["gaps"]), cid
        seen["checklists"] += bool(cl["checklists"])
        seen["turning_25"] += bool(br["turning_25"])
        seen["hints"] += bool(br["benefits"])
    assert all(seen.values()), seen  # every rule path is exercised on the population
    # evidence never cites another customer's transaction
    by_tx = {}
    pairs = sorted(set(cited), key=lambda p: p[1])
    for i in range(0, len(pairs), 900):
        chunk = [t for _, t in pairs[i:i + 900]]
        by_tx.update(ro_con.execute(f"SELECT tx_id, customer_id FROM transactions WHERE tx_id IN "
                                    f"({','.join('?' * len(chunk))})", chunk).fetchall())
    assert all(by_tx.get(t) == cid for cid, t in pairs)


@needs_db
def test_population_rejections_are_respected(ro_con):
    """Rejecting every life event (the customer said 'That's not me') leaves no checklist for anyone."""
    rows = ro_con.execute("SELECT customer_id, profile_json FROM twin_profile WHERE profile_json LIKE '%life_event_%' "
                          "ORDER BY customer_id LIMIT 400").fetchall()
    assert rows
    for cid, profile in rows:
        twin = json.loads(profile)
        events = [k for k in twin["facts"] if k.startswith("life_event_")]
        rejected = apply_feedback(copy.deepcopy(twin), [(k, 0, None) for k in events])
        assert checklists(ro_con, cid, rejected) == [], cid
        assert household_prompt(rejected) is None
