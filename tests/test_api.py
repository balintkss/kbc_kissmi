"""HTTP-level tests: authentication, authorization (IDOR), rate limiting, experience blocks,
moments, customer feedback and response hardening. Everything goes through the public API
(POST /api/auth/login), never through token internals."""
import base64
import hashlib
import hmac
import json
import sqlite3
import time

import pytest

from twin.catalog import CATALOG

pytestmark = pytest.mark.needs_db

WRONG_PASSWORD = "definitely-not-the-password"

# Every customer endpoint, with a valid body where one is needed.
ME_ENDPOINTS = [
    ("GET", "/api/me", None),
    ("GET", "/api/me/twin", None),
    ("GET", "/api/me/twin?with_evidence=true", None),
    ("GET", "/api/me/plan", None),
    ("GET", "/api/me/moments", None),
    ("GET", "/api/me/chat", None),
    ("POST", "/api/me/chat", {"message": "Hoeveel kan ik uitgeven?"}),
    ("POST", "/api/me/facts/has_car/feedback", {"correct": False}),
]
ME_IDS = [f"{m} {p}" for m, p, _ in ME_ENDPOINTS]


def call(client, method, path, headers=None, body=None):
    return client.request(method, path, headers=headers or {}, json=body)


def all_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from all_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from all_keys(v)


def _b64d(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _b64e(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _edit_claims(token, edit):
    """Re-encode the JSON claims segment of a token with `edit` applied, keeping the original signature."""
    parts = token.split(".")
    for i, part in enumerate(parts):
        try:
            claims = json.loads(_b64d(part))
        except (ValueError, TypeError):
            continue
        if isinstance(claims, dict) and "sub" in claims:
            edit(claims)
            parts[i] = _b64e(json.dumps(claims).encode())
            return ".".join(parts)
    pytest.skip("token has no decodable claims segment to tamper with")


def _flip_signature_char(token):
    i = len(token) - 6  # well inside the signature, so the decoded bytes really change
    return token[:i] + ("A" if token[i] != "A" else "Q") + token[i + 1:]


def _forged(key=None):
    claims = {"sub": 1, "exp": int(time.time()) + 3600, "role": "customer"}
    payload = _b64e(json.dumps(claims).encode())
    sig = _b64e(hmac.new(key or b"not-the-server-secret", payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def _alg_none_jwt():
    head = _b64e(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    body = _b64e(json.dumps({"sub": 1, "exp": int(time.time()) + 3600}).encode())
    return f"{head}.{body}."


BAD_TOKENS = {
    "garbage": lambda tok: "garbage",
    "empty": lambda tok: "",
    "flipped signature": _flip_signature_char,
    "subject swapped to customer 2": lambda tok: _edit_claims(tok, lambda c: c.update(sub=2 if not isinstance(c["sub"], str) else "2")),
    "expiry extended": lambda tok: _edit_claims(tok, lambda c: c.update(exp=int(time.time()) + 10 * 365 * 86400)),
    "role escalated": lambda tok: _edit_claims(tok, lambda c: c.update(role="ops")),
    "signature stripped": lambda tok: tok.rsplit(".", 1)[0] + ".",
    "payload only": lambda tok: tok.split(".")[0],
    "forged with another key": lambda tok: _forged(),
    "alg=none JWT": lambda tok: _alg_none_jwt(),
    "two tokens glued": lambda tok: tok + "." + tok,
}


# ====================================================================== login

def test_login_ok_returns_a_bearer_token_for_that_customer(client, demo_secrets, redacted):
    r = client.post("/api/auth/login", json=demo_secrets.login_body(1))
    assert r.status_code == 200
    body = r.json()
    headers = redacted(Authorization=f"Bearer {body.pop('token')}")  # keep the token out of any assertion output
    assert body["token_type"].lower() == "bearer"
    assert 0 < body["expires_in"] <= 24 * 3600
    assert not [k for k in all_keys(body) if "password" in k.lower() or "hash" in k.lower()]
    me = client.get("/api/me", headers=headers)
    assert me.status_code == 200 and me.json()["customer_id"] == 1


def test_wrong_password_is_401(client):
    r = client.post("/api/auth/login", json={"customer_id": 1, "password": WRONG_PASSWORD})
    assert r.status_code == 401
    assert "token" not in r.json()


def test_unknown_customer_gets_the_same_401_as_a_wrong_password(client, ro_con):
    unknown = ro_con.execute("SELECT MAX(customer_id) + 1000 FROM customers").fetchone()[0]
    assert ro_con.execute("SELECT 1 FROM credentials WHERE customer_id = ?", (unknown,)).fetchone() is None
    wrong_pw = client.post("/api/auth/login", json={"customer_id": 1, "password": WRONG_PASSWORD})
    no_user = client.post("/api/auth/login", json={"customer_id": unknown, "password": WRONG_PASSWORD})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json() == no_user.json()  # no user enumeration through the message


@pytest.mark.parametrize("body", [
    {"customer_id": 1},
    {"password": WRONG_PASSWORD},
    {},
    {"customer_id": "abc", "password": WRONG_PASSWORD},
    {"customer_id": 0, "password": WRONG_PASSWORD},
    {"customer_id": -3, "password": WRONG_PASSWORD},
    {"customer_id": 1.5, "password": WRONG_PASSWORD},
    {"customer_id": 1, "password": ""},
    {"customer_id": 1, "password": "x" * 129},
    {"customer_id": 1, "password": 12345678},
    {"customer_id": 1, "password": None},
    [1, WRONG_PASSWORD],
], ids=["no password", "no id", "empty", "id not int", "id zero", "id negative", "id float", "empty password",
        "password too long", "password not str", "password null", "array body"])
def test_malformed_login_body_is_422(client, body):
    assert client.post("/api/auth/login", json=body).status_code == 422


def test_login_body_that_is_not_json_is_422(client):
    r = client.post("/api/auth/login", content=b"customer_id=1&password=x",
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422


@pytest.mark.parametrize("customer_id", [2 ** 63, 10 ** 30])
def test_huge_customer_id_is_rejected_cleanly(make_client, customer_id):
    c = make_client(raise_server_exceptions=False)
    r = c.post("/api/auth/login", json={"customer_id": customer_id, "password": WRONG_PASSWORD})
    assert r.status_code in (401, 422)


# ====================================================================== token required everywhere

@pytest.mark.parametrize("method,path,body", ME_ENDPOINTS, ids=ME_IDS)
def test_customer_endpoints_require_a_token(client, method, path, body):
    r = call(client, method, path, body=body)
    assert r.status_code == 401
    assert r.headers.get("www-authenticate", "").lower().startswith("bearer")


def test_every_registered_me_route_requires_a_token(client, api_main):
    """Catches new /api/me* routes that forget the auth dependency."""
    checked = 0
    for route in api_main.app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/me"):
            continue
        concrete = path.replace("{fact}", "has_car")
        for method in sorted(getattr(route, "methods", None) or ()):
            if method in ("HEAD", "OPTIONS"):
                continue
            body = {"message": "hi", "correct": False} if method == "POST" else None
            assert call(client, method, concrete, body=body).status_code == 401, f"{method} {path} is open"
            checked += 1
    assert checked >= len({(m, p.split("?")[0]) for m, p, _ in ME_ENDPOINTS})


@pytest.mark.parametrize("kind", list(BAD_TOKENS))
@pytest.mark.parametrize("method,path,body", ME_ENDPOINTS, ids=ME_IDS)
def test_invalid_or_tampered_tokens_are_401(client, login, redacted, method, path, body, kind):
    good = login(1)["Authorization"].split(" ", 1)[1]
    r = call(client, method, path, headers=redacted(Authorization=f"Bearer {BAD_TOKENS[kind](good)}"), body=body)
    assert r.status_code == 401


@pytest.mark.parametrize("method,path,body", ME_ENDPOINTS, ids=ME_IDS)
def test_expired_token_is_401(client, login, advance_clock, method, path, body):
    headers = login(1)
    assert client.get("/api/me", headers=headers).status_code == 200
    advance_clock(login.expires_in(1) + 120)
    assert call(client, method, path, headers=headers, body=body).status_code == 401


@pytest.mark.parametrize("make_header", [
    lambda tok: tok,                          # no scheme at all
    lambda tok: f"Token {tok}",
    lambda tok: f"Basic {tok}",
    lambda tok: f"Bearer{tok}",               # missing separator
    lambda tok: "Basic " + base64.b64encode(b"1:guess").decode(),
    lambda tok: "Bearer",
], ids=["raw token", "Token scheme", "Basic scheme with token", "no space", "basic credentials", "scheme only"])
def test_bearer_scheme_is_required(client, login, redacted, make_header):
    tok = login(1)["Authorization"].split(" ", 1)[1]
    r = client.get("/api/me", headers=redacted(Authorization=make_header(tok)))
    assert r.status_code == 401


def test_bad_token_on_optional_auth_endpoint_is_rejected_not_downgraded(client):
    """A broken session must not silently fall back to the anonymous page."""
    r = client.get("/api/experience/car_insurance", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


# ====================================================================== IDOR / authorization

@pytest.mark.parametrize("cid", [1, 2, 3, 4])
def test_token_only_ever_returns_its_own_customer(client, login, ro_con, cid):
    first, last = ro_con.execute("SELECT first_name, last_name FROM customers WHERE customer_id = ?", (cid,)).fetchone()
    h = login(cid)
    me = client.get("/api/me", headers=h).json()
    assert me["customer_id"] == cid and me["first_name"] == first and me["name"] == f"{first} {last}"
    assert client.get("/api/me/twin", headers=h).json()["name"] == f"{first} {last}"


def test_customer_id_in_query_or_body_is_ignored(client, login):
    h = login(1)
    for path in ("/api/me?customer_id=2", "/api/me?cid=2&id=2", "/api/me/twin?customer_id=2"):
        body = client.get(path, headers=h).json()
        assert body["name"].startswith("Lotte"), path
    plan_1 = client.get("/api/me/plan?customer_id=2", headers=h).json()
    plan_2 = client.get("/api/me/plan", headers=login(2)).json()
    assert plan_1 != plan_2
    kinds = {m["kind"] for m in client.get("/api/me/moments?customer_id=2", headers=h).json()["push"]}
    assert "new_car" in kinds and "new_baby" not in kinds  # Lotte's moments, not Julien's


def test_personas_see_different_twins(client, login):
    twins = {cid: client.get("/api/me/twin", headers=login(cid)).json() for cid in (1, 2)}
    keys = {cid: {f["key"] for f in t["facts"]} for cid, t in twins.items()}
    assert "life_event_new_car" in keys[1] and "life_event_new_car" not in keys[2]
    assert "life_event_new_baby" in keys[2] and "life_event_new_baby" not in keys[1]


def test_customer_routes_take_no_customer_identifier(api_main):
    """Identity comes only from the token: no customer id in any /api/me* or experience path, query or body."""
    spec = api_main.app.openapi()
    schemas = spec.get("components", {}).get("schemas", {})
    suspicious = {"customer_id", "customerid", "cid", "customer", "user_id", "userid", "id", "sub", "subject"}

    def props(schema):
        if "$ref" in schema:
            schema = schemas[schema["$ref"].rsplit("/", 1)[-1]]
        return set(schema.get("properties", {}))

    seen = 0
    for path, ops in spec["paths"].items():
        if not path.startswith(("/api/me", "/api/experience", "/api/topics")):
            continue
        assert "customer" not in path.lower() and "{id}" not in path
        for method, op in ops.items():
            seen += 1
            names = {p["name"].lower() for p in op.get("parameters", [])}
            assert not names & suspicious, f"{method.upper()} {path} takes {names & suspicious}"
            for media in op.get("requestBody", {}).get("content", {}).values():
                body_props = {p.lower() for p in props(media["schema"])}
                assert not body_props & suspicious, f"{method.upper()} {path} body takes {body_props & suspicious}"
    assert seen >= 8


@pytest.mark.parametrize("cid", [1, 2, 3, 4])
def test_evidence_transactions_all_belong_to_the_caller(client, login, ro_con, cid):
    r = client.get("/api/me/twin", params={"with_evidence": "true"}, headers=login(cid))
    assert r.status_code == 200
    tx_ids = [e["tx_id"] for f in r.json()["facts"] for e in f["evidence"]]
    assert tx_ids, "expected at least one proving transaction"
    marks = ",".join("?" * len(tx_ids))
    owners = dict(ro_con.execute(f"SELECT tx_id, customer_id FROM transactions WHERE tx_id IN ({marks})", tx_ids).fetchall())
    assert set(owners) == set(tx_ids)
    assert set(owners.values()) == {cid}


def test_evidence_is_hidden_unless_requested(client, login):
    facts = client.get("/api/me/twin", headers=login(1)).json()["facts"]
    assert facts and all("evidence" not in f for f in facts)


def test_evidence_query_is_scoped_even_if_the_twin_lists_foreign_transactions(client, login, api_main, ro_con, monkeypatch):
    """Defense in depth: even a corrupted twin cannot make the API return another customer's transactions."""
    foreign = [r[0] for r in ro_con.execute("SELECT tx_id FROM transactions WHERE customer_id = 2 ORDER BY tx_id LIMIT 10")]
    original = api_main.load_twin

    def poisoned(con, cid):
        twin = original(con, cid)
        for f in twin["facts"].values():
            f["evidence"] = list(f.get("evidence") or []) + foreign
        return twin

    monkeypatch.setattr(api_main, "load_twin", poisoned)
    r = client.get("/api/me/twin?with_evidence=true", headers=login(1))
    returned = {e["tx_id"] for f in r.json()["facts"] for e in f["evidence"]}
    assert returned and not returned & set(foreign)


def _feedback_rows(ro_con, cid):
    return ro_con.execute("SELECT COUNT(*) FROM twin_feedback WHERE customer_id = ?", (cid,)).fetchone()[0]


def test_feedback_on_a_fact_the_caller_does_not_have_is_404(client, login, ro_con):
    h = login(1)
    lotte = {f["key"] for f in client.get("/api/me/twin", headers=h).json()["facts"]}
    julien = {f["key"] for f in client.get("/api/me/twin", headers=login(2)).json()["facts"]}
    other_customers_fact = sorted(julien - lotte)[0]  # e.g. life_event_new_baby: exists, but not for Lotte
    before = _feedback_rows(ro_con, 1)
    for fact in ("has_unicorn", other_customers_fact):
        r = client.post(f"/api/me/facts/{fact}/feedback", json={"correct": False}, headers=h)
        assert r.status_code == 404, fact
    assert _feedback_rows(ro_con, 1) == before


@pytest.mark.parametrize("path", [
    "/api/experience/..%2F..",
    "/api/experience/..%2F..%2Fapi%2Fme",
    "/api/experience/%2e%2e",
    "/api/experience/CAR_LOAN",
    "/api/experience/Car_Insurance",
    "/api/experience/" + "a" * 41,
    "/api/experience/car-loan",
    "/api/experience/car_loan%00",
    "/api/experience/car_loan'%20OR%201=1--",
])
def test_experience_path_is_validated(client, login, path):
    for headers in ({}, login(1)):
        r = client.get(path, headers=headers)
        assert r.status_code in (404, 422), (path, r.status_code)
        assert "Traceback" not in r.text


@pytest.mark.parametrize("fact", ["HAS_CAR", "has-car", "..%2Fhas_car", "a" * 41, "has_car%27--", "has_car%00"])
def test_feedback_path_is_validated(client, login, ro_con, fact):
    before = _feedback_rows(ro_con, 1)
    r = client.post(f"/api/me/facts/{fact}/feedback", json={"correct": False}, headers=login(1))
    assert r.status_code in (404, 422)
    assert _feedback_rows(ro_con, 1) == before


def test_api_never_reads_truth_tables(api_main, client, demo_secrets, redacted, fake_openai):
    """Runs the read endpoints on a connection whose authorizer denies (and records) any truth_* read."""
    touched = []

    def authorizer(action, arg1, arg2, dbname, source):
        if action == sqlite3.SQLITE_READ and arg1 and arg1.lower().startswith("truth_"):
            touched.append(arg1)
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def guarded_db():
        con = sqlite3.connect(api_main.DB, check_same_thread=False)
        con.set_authorizer(authorizer)
        try:
            yield con
        finally:
            con.close()

    api_main.app.dependency_overrides[api_main.db] = guarded_db
    try:
        login = client.post("/api/auth/login", json=demo_secrets.login_body(1))
        assert login.status_code == 200
        h = redacted(Authorization=f"Bearer {login.json()['token']}")
        paths = ["/api/me", "/api/me/twin?with_evidence=true", "/api/me/plan", "/api/me/moments", "/api/me/chat",
                 "/api/topics"] + [f"/api/experience/{t}" for t in CATALOG]
        for path in paths:
            assert client.get(path, headers=h).status_code == 200, path
    finally:
        api_main.app.dependency_overrides.pop(api_main.db, None)
    assert touched == []


# ====================================================================== rate limiting

def test_sixth_rapid_failed_login_is_429_even_with_the_right_password(client, demo_secrets):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"customer_id": 1, "password": WRONG_PASSWORD}).status_code == 401
    r = client.post("/api/auth/login", json=demo_secrets.login_body(1))
    assert r.status_code == 429
    assert "token" not in r.json()


def test_login_lockout_is_per_customer_across_ips(make_client, demo_secrets):
    """Rotating IPs does not help brute-forcing one customer."""
    for i in range(5):
        c = make_client(ip=f"198.51.100.{i + 1}")
        assert c.post("/api/auth/login", json={"customer_id": 2, "password": WRONG_PASSWORD}).status_code == 401
    r = make_client(ip="198.51.100.200").post("/api/auth/login", json=demo_secrets.login_body(2))
    assert r.status_code == 429


def test_login_lockout_is_per_ip_across_customers(make_client):
    """One IP cannot spray passwords over many customers."""
    c = make_client(ip="203.0.113.7")
    for cid in range(101, 106):
        assert c.post("/api/auth/login", json={"customer_id": cid, "password": WRONG_PASSWORD}).status_code == 401
    assert c.post("/api/auth/login", json={"customer_id": 106, "password": WRONG_PASSWORD}).status_code == 429
    other = make_client(ip="203.0.113.8")
    assert other.post("/api/auth/login", json={"customer_id": 107, "password": WRONG_PASSWORD}).status_code == 401


def test_login_lockout_expires_after_the_window(client, api_main, advance_clock):
    for _ in range(5):
        client.post("/api/auth/login", json={"customer_id": 3, "password": WRONG_PASSWORD})
    assert client.post("/api/auth/login", json={"customer_id": 3, "password": WRONG_PASSWORD}).status_code == 429
    advance_clock(getattr(api_main, "WINDOW", 300) + 5)
    assert client.post("/api/auth/login", json={"customer_id": 3, "password": WRONG_PASSWORD}).status_code == 401


def test_chat_is_rate_limited_per_customer(client, login, fake_openai):
    h = login(1)
    for i in range(20):
        assert client.post("/api/me/chat", json={"message": f"vraag {i}"}, headers=h).status_code == 200, i
    r = client.post("/api/me/chat", json={"message": "nog eentje"}, headers=h)
    assert r.status_code == 429
    assert len(fake_openai.calls) == 20  # the limited request never reached the (paid) LLM
    assert client.post("/api/me/chat", json={"message": "Bonjour"}, headers=login(2)).status_code == 200


# ====================================================================== experience blocks

def test_topics_list_the_catalog(client):
    r = client.get("/api/topics")
    assert r.status_code == 200
    assert [t["id"] for t in r.json()] == list(CATALOG)


def test_anonymous_experience_is_generic_with_all_variants(client):
    topics = [t["id"] for t in client.get("/api/topics").json()]
    assert topics
    for topic in topics:
        r = client.get(f"/api/experience/{topic}")
        assert r.status_code == 200, topic
        block = r.json()
        assert block["personalized"] is False and block["highlight"] is None
        assert [v["id"] for v in block["variants"]] == list(CATALOG[topic]["variants"])
        assert block["channel"] == "web"


def test_lotte_car_insurance_highlights_mini_omnium(client, login):
    r = client.get("/api/experience/car_insurance", params={"channel": "app"}, headers=login(1))
    assert r.status_code == 200
    block = r.json()
    assert block["personalized"] is True and block["channel"] == "app"
    hl = block["highlight"]
    assert hl["id"] == "mini_omnium"
    assert hl["because"] and "has_car" in {b["key"] for b in hl["because"]}
    assert "Ethias" in hl["reason"]  # knows where she is insured today
    alt = [a["id"] for a in block["alternatives"]]
    assert hl["id"] not in alt
    assert set(alt) == set(CATALOG["car_insurance"]["variants"]) - {hl["id"]}


@pytest.mark.parametrize("channel", ["app", "web"])
def test_channel_is_echoed(client, login, channel):
    assert client.get(f"/api/experience/savings?channel={channel}").json()["channel"] == channel
    assert client.get(f"/api/experience/savings?channel={channel}", headers=login(1)).json()["channel"] == channel


def test_same_block_for_every_channel(client, login):
    h = login(2)
    app_block = client.get("/api/experience/family?channel=app", headers=h).json()
    web_block = client.get("/api/experience/family?channel=web", headers=h).json()
    app_block.pop("channel"), web_block.pop("channel")
    assert app_block == web_block


@pytest.mark.parametrize("cid", [1, 2, 3, 4])
def test_personalized_highlights_are_real_catalog_variants(client, login, cid):
    h = login(cid)
    for topic in CATALOG:
        block = client.get(f"/api/experience/{topic}", headers=h).json()
        if block["personalized"]:
            assert block["highlight"]["id"] in CATALOG[topic]["variants"]
            assert block["highlight"]["reason"]


def test_unknown_topic_is_404(client, login):
    assert client.get("/api/experience/mortgage").status_code == 404
    assert client.get("/api/experience/mortgage", headers=login(1)).status_code == 404


# ====================================================================== moments

def test_lotte_moments(client, login):
    m = client.get("/api/me/moments", headers=login(1)).json()
    kinds = [x["kind"] for x in m["push"]]
    assert {"salary_plan", "new_car"} <= set(kinds)
    assert len(m["push"]) <= 2
    assert all(x["sales"] for x in m["held_back"])


@pytest.mark.parametrize("cid", [1, 2, 3, 4])
def test_moment_rules_hold_for_every_persona(client, login, cid):
    m = client.get("/api/me/moments", headers=login(cid)).json()
    assert len(m["push"]) <= 2
    prios = [x["priority"] for x in m["push"] + m["feed"]]
    assert prios == sorted(prios, reverse=True)
    assert all(x["sales"] and x.get("held_because") for x in m["held_back"])


# ====================================================================== feedback (customer corrects the twin)

def _facts(client, h):
    return {f["key"]: f for f in client.get("/api/me/twin", headers=h).json()["facts"]}


def _moment_kinds(client, h):
    m = client.get("/api/me/moments", headers=h).json()
    return {x["kind"] for part in ("push", "feed", "held_back") for x in m[part]}


def test_rejecting_a_fact_stops_it_driving_recommendations(client, login):
    h = login(1)
    assert client.get("/api/experience/car_insurance", headers=h).json()["personalized"] is True
    r = client.post("/api/me/facts/has_car/feedback", json={"correct": False, "note": "Sold it"}, headers=h)
    assert r.status_code == 200 and r.json() == {"fact": "has_car", "correct": False}

    assert _facts(client, h)["has_car"].get("rejected_by_customer") is True
    assert client.get("/api/experience/car_insurance", headers=h).json()["personalized"] is False
    assert "new_car" not in _moment_kinds(client, h)

    # Scoped to the caller: Julien's car is untouched.
    j = login(2)
    assert not _facts(client, j)["has_car"].get("rejected_by_customer")
    assert client.get("/api/experience/car_insurance", headers=j).json()["personalized"] is True


def test_latest_feedback_wins(client, login):
    h = login(1)
    client.post("/api/me/facts/has_car/feedback", json={"correct": False}, headers=h)
    assert client.get("/api/experience/car_insurance", headers=h).json()["personalized"] is False
    time.sleep(0.01)  # distinct created_at
    assert client.post("/api/me/facts/has_car/feedback", json={"correct": True}, headers=h).status_code == 200
    assert not _facts(client, h)["has_car"].get("rejected_by_customer")
    assert client.get("/api/experience/car_insurance", headers=h).json()["highlight"]["id"] == "mini_omnium"


@pytest.mark.parametrize("body", [{}, {"correct": "maybe"}, {"correct": None}, {"correct": False, "note": "x" * 281}])
def test_malformed_feedback_is_422(client, login, ro_con, body):
    before = _feedback_rows(ro_con, 1)
    assert client.post("/api/me/facts/has_car/feedback", json=body, headers=login(1)).status_code == 422
    assert _feedback_rows(ro_con, 1) == before


def test_rejecting_financial_buffer_keeps_savings_page_working(make_client, login):
    """Regression: _pick_savings formatted buffer['value'] after the customer rejected financial_buffer -> HTTP 500."""
    h = login(4)  # Marc: already has pension savings, so the picker used to fall through to the investment_plan branch
    c = make_client(raise_server_exceptions=False)
    assert c.post("/api/me/facts/financial_buffer/feedback", json={"correct": False}, headers=h).status_code == 200
    r = c.get("/api/experience/savings", headers=h)
    assert r.status_code == 200
    hl = r.json()["highlight"]
    assert hl["reason"] and "financial_buffer" not in {b["key"] for b in hl["because"]}


@pytest.mark.parametrize("cid", [1, 2, 3, 4])
def test_rejecting_any_fact_keeps_every_page_working(make_client, login, cid):
    h = login(cid)
    c = make_client(raise_server_exceptions=False)
    for fact in [f["key"] for f in c.get("/api/me/twin", headers=h).json()["facts"]]:
        assert c.post(f"/api/me/facts/{fact}/feedback", json={"correct": False}, headers=h).status_code == 200, fact
    for topic in CATALOG:
        r = c.get(f"/api/experience/{topic}", headers=h)
        assert r.status_code == 200, topic
        if r.json()["personalized"]:
            assert r.json()["highlight"]["reason"] and r.json()["highlight"]["because"] == [], topic
    assert c.get("/api/me/moments", headers=h).status_code == 200


def test_money_stress_experience_is_support_first(client, login, api_main, monkeypatch):
    original = api_main.load_twin

    def stressed(con, cid):
        twin = original(con, cid)
        twin["facts"]["money_stress"] = dict(key="money_stress", value=True, confidence=0.9, since=None, evidence=[],
                                             summary="7 days in the red in the last 90 days", implies=[])
        return twin

    h = login(1)
    assert "support_first" not in client.get("/api/experience/car_loan", headers=h).json()
    monkeypatch.setattr(api_main, "load_twin", stressed)
    loan = client.get("/api/experience/car_loan", headers=h).json()
    assert loan["support_first"] is True and loan["personalized"] is True
    assert loan["highlight"]["id"] not in CATALOG["car_loan"]["variants"] and loan["highlight"]["reason"]
    assert {a["id"] for a in loan["alternatives"]} == set(CATALOG["car_loan"]["variants"])
    home = client.get("/api/experience/home", headers=h).json()
    assert home["support_first"] is True and home["highlight"]["id"] == "home_insurance"
    assert "support_first" not in client.get("/api/experience/car_loan").json()  # anonymous visitors


# ====================================================================== response hardening

@pytest.mark.parametrize("method,path,auth,status", [
    ("GET", "/api/topics", False, 200),
    ("GET", "/api/me/twin", True, 200),
    ("GET", "/api/me", False, 401),
    ("GET", "/api/experience/mortgage", False, 404),
    ("GET", "/api/experience/NOPE", False, 422),
    ("POST", "/api/auth/login", False, 422),
])
def test_security_headers_on_every_response(client, login, method, path, auth, status):
    r = call(client, method, path, headers=login(1) if auth else None, body={} if method == "POST" else None)
    assert r.status_code == status
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["referrer-policy"] == "no-referrer"


def test_cors_rejects_foreign_origins(client):
    evil = "https://evil.example"
    pre = client.options("/api/me/twin", headers={"Origin": evil, "Access-Control-Request-Method": "GET",
                                                   "Access-Control-Request-Headers": "Authorization"})
    assert pre.headers.get("access-control-allow-origin") not in (evil, "*")
    simple = client.get("/api/topics", headers={"Origin": evil})
    assert simple.headers.get("access-control-allow-origin") not in (evil, "*")
    ok = client.get("/api/topics", headers={"Origin": "http://localhost:5173"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_customer_responses_never_expose_truth_or_secrets(client, login, fake_openai):
    h = login(1)
    for path in ("/api/me", "/api/me/twin", "/api/me/twin?with_evidence=true", "/api/me/plan", "/api/me/moments",
                 "/api/me/chat", "/api/experience/car_insurance"):
        r = client.get(path, headers=h)
        assert r.status_code == 200, path
        keys = [k.lower() for k in all_keys(r.json())]
        assert not [k for k in keys if "truth" in k], path
        assert not [k for k in keys if "password" in k or k in ("hash", "password_hash", "token", "secret")], path
        assert "truth_" not in r.text and "pbkdf2" not in r.text.lower(), path
