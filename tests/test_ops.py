"""Ops & advisor channel: role-bound tokens, ops login, authorization, audit trail, validation, dashboard.

Needs the generated DB, `python -m api.seed_credentials` and `python -m api.seed_ops` (DB tests are marked
`needs_db` and skipped on a fresh clone; api.main is only imported through conftest's `api_main` fixture, so
collecting this file never creates an empty database). Passwords are read from data/*_credentials.txt only
to log in, and every login body and Authorization header is `redacted`, so no password or token can show up
in assertion output. Audit rows written by these tests are deleted afterwards.

Run:  .venv/bin/python -m pytest tests/test_ops.py -q
"""
import base64
import json
import re
import sqlite3
from pathlib import Path

import pytest

from api.security import issue_token, read_token  # stdlib only, no database access

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "kbc_twin.db"
OPS_CREDS = ROOT / "data" / "ops_credentials.txt"
CUSTOMER = 1  # Lotte: the customer side of the "advisor sees the same twin" checks

needs_db = pytest.mark.needs_db
FORBIDDEN = re.compile(r"truth|password|credential|chat_messages", re.I)


class _OpsSecret:
    """The ops login from the git-ignored data/ops_credentials.txt. repr is redacted, bodies are Redacted."""

    def __init__(self, path, redacted):
        m = re.search(r"username=(\S+)\s+password=(\S+)", path.read_text())
        if not m:
            pytest.skip("data/ops_credentials.txt has no login line: run `python -m api.seed_ops`")
        self.username, self._pw, self._redacted = m.group(1), m.group(2), redacted

    def __repr__(self):
        return "<ops credentials redacted>"

    def ops_body(self, wrong=False):
        return self._redacted(username=self.username, password=("x" + self._pw) if wrong else self._pw)


@pytest.fixture(scope="module")
def creds(api_main, redacted):
    if not OPS_CREDS.exists():
        pytest.skip("data/ops_credentials.txt not found: run `python -m api.seed_ops`")
    return _OpsSecret(OPS_CREDS, redacted)


@pytest.fixture(scope="module")
def app_client(api_main):
    from fastapi.testclient import TestClient
    return TestClient(api_main.app)


def _bearer(redacted, token):
    return redacted(Authorization=f"Bearer {token}")


def _audit_max():
    con = sqlite3.connect(DB_PATH, timeout=30)
    try:
        return con.execute("SELECT COALESCE(MAX(rowid), 0) FROM ops_audit").fetchone()[0]
    finally:
        con.close()


def _audit_rows(since):
    con = sqlite3.connect(DB_PATH, timeout=30)
    try:
        return con.execute("SELECT username, customer_id, action FROM ops_audit WHERE rowid > ? ORDER BY rowid",
                           (since,)).fetchall()
    finally:
        con.close()


@pytest.fixture(scope="module", autouse=True)
def audit_cleanup():
    """Delete every audit row this module writes (logins, lists, views) for the usernames it uses."""
    if not DB_PATH.exists():  # fresh clone: DB tests are skipped, and never create an empty DB file here
        yield None
        return
    import api.main  # noqa: F401  (creates ops_audit on the existing DB)
    from api.seed_ops import USERNAME
    start = _audit_max()
    yield start
    con = sqlite3.connect(DB_PATH, timeout=30)
    try:
        con.execute("DELETE FROM ops_audit WHERE rowid > ? AND username IN (?, 'nobody', 'ghost')", (start, USERNAME))
        con.commit()
    finally:
        con.close()


@pytest.fixture(scope="module")
def ops_headers(app_client, creds, redacted):
    r = app_client.post("/api/ops/login", json=creds.ops_body())
    assert r.status_code == 200, f"ops login failed with HTTP {r.status_code}"
    return _bearer(redacted, r.json()["token"])


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


# ---------------------------------------------------------------------- tokens carry a role

def test_token_role_claim_is_exact():
    customer = issue_token(1)
    assert read_token(customer) == 1
    assert read_token(customer, role="customer") == 1
    assert read_token(customer, role="ops") is None

    ops = issue_token("advisor", role="ops")
    assert read_token(ops, role="ops") == "advisor"
    assert read_token(ops) is None
    # colliding subjects: an ops user called "1" is still not customer 1
    assert read_token(issue_token("1", role="ops")) is None

    with pytest.raises(ValueError):
        issue_token(1, role="admin")
    assert read_token(customer, role="admin") is None


def test_forged_role_is_rejected():
    payload, sig = issue_token(1).split(".")
    data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    data["role"] = "ops"
    forged = base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode() + "." + sig
    assert read_token(forged, role="ops") is None
    assert read_token(forged) is None
    assert read_token("not-a-token") is None
    assert read_token("") is None


# ---------------------------------------------------------------------- ops login

@needs_db
def test_ops_login_ok(app_client, creds):
    since = _audit_max()
    r = app_client.post("/api/ops/login", json=creds.ops_body())
    assert r.status_code == 200
    body = r.json()
    token = body.pop("token")  # keep the token out of any assertion output
    assert body["token_type"] == "bearer" and body["expires_in"] > 0 and body["username"] == creds.username
    assert read_token(token, role="ops") == creds.username, "token does not carry the ops role"
    assert read_token(token) is None, "ops token accepted as a customer token"
    assert (creds.username, None, "login") in _audit_rows(since)


@needs_db
def test_ops_login_bad(app_client, creds):
    since = _audit_max()
    assert app_client.post("/api/ops/login", json=creds.ops_body(wrong=True)).status_code == 401
    assert app_client.post("/api/ops/login", json={"username": "nobody", "password": "whatever"}).status_code == 401
    assert app_client.post("/api/ops/login", json={"username": "Robert'); DROP TABLE ops_users;--",
                                                   "password": "x"}).status_code == 422
    assert app_client.post("/api/ops/login", json={"username": "advisor"}).status_code == 422
    assert app_client.post("/api/ops/login", json={"username": "advisor", "password": "x" * 129}).status_code == 422
    rows = _audit_rows(since)
    assert (creds.username, None, "login_failed") in rows and ("nobody", None, "login_failed") in rows


@needs_db
def test_ops_login_rate_limited_per_username(make_client, creds):
    """Spreading guesses over many IPs doesn't help: the username bucket fills up too."""
    codes = [make_client(ip=f"10.0.0.{i}").post("/api/ops/login", json=creds.ops_body(wrong=True)).status_code
             for i in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429
    # even the right password is refused while the limit holds
    assert make_client(ip="10.0.1.1").post("/api/ops/login", json=creds.ops_body()).status_code == 429


@needs_db
def test_ops_login_rate_limited_per_ip(make_client):
    c = make_client(ip="10.0.2.1")
    codes = [c.post("/api/ops/login", json={"username": "nobody", "password": f"guess{i}"}).status_code for i in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429


@needs_db
def test_ops_successful_logins_do_not_use_up_the_budget(make_client, creds):
    """Only failed attempts count: an advisor can log in and out all day from one IP, guessing still locks out."""
    c = make_client(ip="10.0.3.1")
    assert [c.post("/api/ops/login", json=creds.ops_body()).status_code for _ in range(8)] == [200] * 8
    assert [c.post("/api/ops/login", json=creds.ops_body(wrong=True)).status_code for _ in range(5)] == [401] * 5
    assert c.post("/api/ops/login", json=creds.ops_body()).status_code == 429


# ---------------------------------------------------------------------- authorization

OPS_ENDPOINTS = ["/api/ops/overview", "/api/ops/customers", "/api/ops/customers/1"]


@needs_db
def test_ops_endpoints_require_ops_token(app_client):
    for path in OPS_ENDPOINTS:
        assert app_client.get(path).status_code == 401
        assert app_client.get(path, headers={"Authorization": "Bearer garbage"}).status_code == 401
        assert app_client.get(path, headers={"Authorization": "Basic YWR2aXNvcjp4"}).status_code == 401


@needs_db
def test_customer_token_rejected_on_ops(app_client, login, redacted):
    customer_headers = login(CUSTOMER)
    for path in OPS_ENDPOINTS:
        assert app_client.get(path, headers=customer_headers).status_code in (401, 403)
    forged = _bearer(redacted, issue_token(CUSTOMER))
    assert app_client.get("/api/ops/overview", headers=forged).status_code == 401


@needs_db
def test_ops_token_rejected_on_customer_endpoints(app_client, ops_headers, redacted):
    for path in ("/api/me", "/api/me/twin", "/api/me/plan", "/api/me/moments", "/api/experience/car_insurance"):
        assert app_client.get(path, headers=ops_headers).status_code == 401
    collide = _bearer(redacted, issue_token("1", role="ops"))
    assert app_client.get("/api/me", headers=collide).status_code == 401


@needs_db
def test_ops_token_for_unknown_user_is_rejected(app_client, redacted):
    """A validly signed ops token only works while the user exists in ops_users (revocation)."""
    ghost = _bearer(redacted, issue_token("ghost", role="ops"))
    assert app_client.get("/api/ops/overview", headers=ghost).status_code == 401


# ---------------------------------------------------------------------- overview

@needs_db
def test_overview(app_client, ops_headers):
    r = app_client.get("/api/ops/overview", headers=ops_headers)
    assert r.status_code == 200
    o = r.json()
    p = o["population"]
    assert p["customers"] == p["twins_built"] > 0 and p["facts_inferred"] > p["customers"]
    assert 0 < p["avg_confidence"] <= 1
    assert {c["fact"] for c in o["coverage"]} >= {"has_car", "pet", "children", "commutes_by_train", "saves_monthly", "money_stress"}
    car = next(c for c in o["coverage"] if c["fact"] == "has_car")
    assert {b["value"] for b in car["breakdown"]} <= {"combustion", "electric"}
    assert o["life_events"]["window_days"] == 90 and o["life_events"]["total"] > 0
    m = o["moments"]
    assert m["push_total"] <= 2 * p["twins_built"] and m["held_back_total"] > 0
    assert m["customers_held_back"] <= m["customers_money_stress"]
    assert {h["topic"] for h in o["highlights"]} == {"car_loan", "car_insurance", "savings", "home", "family"}
    s = o["scale"]
    assert s["target_customers"] == 2_300_000 and s["llm_calls_for_inference"] == 0
    assert s["build_one_core_hours"] > s["build_cluster_minutes"] / 60 > 0


@needs_db
def test_overview_never_exposes_private_tables(app_client, ops_headers):
    o = app_client.get("/api/ops/overview", headers=ops_headers).json()
    assert not [k for k in _keys(o) if "truth" in k.lower()]
    assert not FORBIDDEN.search(json.dumps(o))
    # counts only: no individual customers in the population view
    assert not [k for k in _keys(o) if k in ("customer_id", "customer_ids", "first_name", "last_name", "iban")]


# ---------------------------------------------------------------------- drill-down + audit

@needs_db
def test_customer_list_and_audit(app_client, ops_headers, creds):
    since = _audit_max()
    r = app_client.get("/api/ops/customers", params={"has": "has_car", "limit": 5}, headers=ops_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= len(body["customers"]) > 0 and len(body["customers"]) <= 5
    assert set(body["customers"][0]) == {"customer_id", "name", "city", "headline"}
    rows = _audit_rows(since)
    listed = {c["customer_id"] for c in body["customers"]}
    assert {cid for user, cid, action in rows if user == creds.username and action.startswith("list")} == listed

    r = app_client.get("/api/ops/customers", params={"event": "new_baby", "has": "children", "limit": 50}, headers=ops_headers)
    assert r.status_code == 200 and all(any("New baby" in h for h in c["headline"]) for c in r.json()["customers"])


@needs_db
@pytest.mark.parametrize("params", [
    {"has": "Has-Car"}, {"has": "has_car; DROP TABLE"}, {"has": "x" * 41}, {"has": "unknown_fact"},
    {"event": "life_event_new_baby'--"}, {"event": "promotion"}, {"limit": 0}, {"limit": 51}, {"limit": "abc"},
])
def test_customer_list_validation(app_client, ops_headers, params):
    assert app_client.get("/api/ops/customers", params=params, headers=ops_headers).status_code == 422


@needs_db
@pytest.mark.parametrize("path", ["/api/ops/customers/0", "/api/ops/customers/-1", "/api/ops/customers/abc",
                                  "/api/ops/customers/1.5", "/api/ops/customers/99999999999"])
def test_customer_id_validation(app_client, ops_headers, path):
    assert app_client.get(path, headers=ops_headers).status_code == 422


@needs_db
def test_drilldown_unknown_customer_404_is_audited(app_client, ops_headers, creds):
    since = _audit_max()
    r = app_client.get("/api/ops/customers/999999", headers=ops_headers)
    assert r.status_code == 404 and r.json() == {"detail": "Unknown customer"}
    assert (creds.username, 999999, "view_not_found") in _audit_rows(since)


@needs_db
def test_drilldown_is_audited_and_private(app_client, ops_headers, creds):
    since = _audit_max()
    r = app_client.get("/api/ops/customers/2", headers=ops_headers)
    assert r.status_code == 200
    v = r.json()
    assert v["customer_id"] == 2 and v["name"] and v["facts"] and set(v["moments"]) == {"push", "feed", "held_back"}
    assert {h["topic"] for h in v["highlights"]} == {"car_loan", "car_insurance", "savings", "home", "family"}
    assert all(0 < f["confidence"] <= 1 and "evidence" not in f for f in v["facts"])
    assert not FORBIDDEN.search(json.dumps(v))
    assert (creds.username, 2, "view") in _audit_rows(since)


@needs_db
def test_advisor_sees_the_same_twin_as_the_customer(app_client, ops_headers, login):
    cid, customer_headers = CUSTOMER, login(CUSTOMER)
    view = app_client.get(f"/api/ops/customers/{cid}", headers=ops_headers).json()
    for topic in ("car_insurance", "car_loan", "savings"):
        mine = app_client.get(f"/api/experience/{topic}", headers=customer_headers).json()
        ops = next(h for h in view["highlights"] if h["topic"] == topic)
        assert ops["personalized"] == mine["personalized"]
        if mine["personalized"]:
            assert ops["highlight"]["id"] == mine["highlight"]["id"]
    assert view["moments"] == app_client.get("/api/me/moments", headers=customer_headers).json()


# ---------------------------------------------------------------------- customer flow unchanged

@needs_db
def test_customer_flow_still_works(app_client, login):
    customer_headers = login(CUSTOMER)
    me = app_client.get("/api/me", headers=customer_headers)
    assert me.status_code == 200 and me.json()["customer_id"] == CUSTOMER
    exp = app_client.get("/api/experience/car_insurance", headers=customer_headers)
    assert exp.status_code == 200 and exp.json()["topic"] == "car_insurance"
    anon = app_client.get("/api/experience/car_insurance")
    assert anon.status_code == 200 and anon.json()["personalized"] is False
    assert app_client.get("/api/me").status_code == 401


# ---------------------------------------------------------------------- dashboard

@needs_db
def test_dashboard_is_served_with_csp(app_client):
    r = app_client.get("/ops")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp and "unsafe-inline" not in csp
    assert r.headers["x-frame-options"] == "DENY"
    for asset, kind in (("/ops/dashboard.js", "javascript"), ("/ops/dashboard.css", "css")):
        a = app_client.get(asset)
        assert a.status_code == 200 and kind in a.headers["content-type"]
    assert app_client.get("/ops/../api/security.py").status_code == 404
    assert app_client.get("/ops/index.html").status_code == 404  # only the three whitelisted files


def test_dashboard_code_rules():
    js = (ROOT / "dashboard" / "dashboard.js").read_text()
    html = (ROOT / "dashboard" / "index.html").read_text()
    for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "localStorage",
                   "sessionStorage", "document.cookie", "eval(", "new Function"):
        assert banned not in js
    assert not re.search(r"\son[a-z]+\s*=", html)          # no inline event handlers
    assert not re.search(r"<script(?![^>]*src=\"/ops/)", html)  # no inline or external scripts
    assert "http://" not in html and "https://" not in html


def test_population_filters_are_whitelisted():
    from twin import population  # lazy: the other tests in this file don't need pandas at import time
    with pytest.raises(ValueError):
        population.search(None, has="credentials")
    with pytest.raises(ValueError):
        population.search(None, event="truth")
