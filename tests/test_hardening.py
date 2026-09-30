"""Second hardening pass: the login throttle counts only failures, oversized ids are rejected cleanly,
`channel` is validated, the money-stress demo persona (5) tells its story, and seed_credentials is
idempotent. Passwords and tokens never appear in test output (redacted helpers from conftest).
"""
import importlib.util
import re
import sqlite3
from pathlib import Path

import pytest

from twin.catalog import CATALOG

ROOT = Path(__file__).resolve().parent.parent
WRONG_PASSWORD = "definitely-not-the-password"
PERSONA_5 = 113  # Jens: money stress, see EXTRA_DEMO_IDS in data/generate_db.py
needs_db = pytest.mark.needs_db


def _login(client, body):
    return client.post("/api/auth/login", json=body).status_code


def _wrong(customer_id):
    return {"customer_id": customer_id, "password": WRONG_PASSWORD}


# ====================================================================== login throttle: only failures count

@needs_db
def test_ten_successful_logins_in_a_row_are_all_200(make_client, demo_secrets):
    c = make_client(ip="192.0.2.10")  # one IP, like a room of judges behind one NAT
    codes = [_login(c, demo_secrets.login_body(1)) for _ in range(10)]
    assert codes == [200] * 10


@needs_db
def test_judges_can_switch_personas_from_one_ip(make_client, demo_secrets):
    c = make_client(ip="192.0.2.11")
    codes = [_login(c, demo_secrets.login_body(cid)) for _ in range(2) for cid in (1, 2, 3, 4)]
    assert codes == [200] * 8


@needs_db
def test_five_failures_then_429_even_after_earlier_successes(make_client, demo_secrets):
    c = make_client(ip="192.0.2.12")
    assert [_login(c, demo_secrets.login_body(1)) for _ in range(3)] == [200] * 3
    assert [_login(c, _wrong(1)) for _ in range(5)] == [401] * 5
    assert _login(c, _wrong(1)) == 429
    assert _login(c, demo_secrets.login_body(1)) == 429  # locked out: the right password waits too


@needs_db
def test_success_after_the_lockout_window(make_client, demo_secrets, api_main, advance_clock):
    c = make_client(ip="192.0.2.13")
    assert [_login(c, _wrong(3)) for _ in range(5)] == [401] * 5
    assert _login(c, demo_secrets.login_body(3)) == 429
    advance_clock(api_main.WINDOW + 5)
    assert _login(c, demo_secrets.login_body(3)) == 200


@needs_db
def test_success_clears_the_account_counter_but_not_the_ip_counter(make_client, demo_secrets):
    a, b = make_client(ip="192.0.2.14"), make_client(ip="192.0.2.15")
    assert [_login(a, _wrong(1)) for _ in range(4)] == [401] * 4
    assert _login(a, demo_secrets.login_body(1)) == 200
    # the account starts from zero again (the owner proved the password) ...
    assert [_login(b, _wrong(1)) for _ in range(5)] == [401] * 5
    assert _login(b, _wrong(1)) == 429
    # ... but IP a keeps its 4 failures: one more and it is locked out, whichever account it tries
    assert _login(a, _wrong(2)) == 401
    assert _login(a, _wrong(3)) == 429


@needs_db
def test_in_flight_attempts_hold_a_slot(api_main):
    """Parallel guesses can't all pass the check before any failure is recorded."""
    keys = ("ip:unit-test", "cid:424242")
    tickets = [api_main.begin_login_attempt(keys) for _ in range(api_main.MAX_ATTEMPTS)]
    assert None not in tickets
    assert api_main.begin_login_attempt(keys) is None
    api_main.end_login_attempt(keys, tickets[0], ok=False)  # a failure keeps its slot
    assert api_main.begin_login_attempt(keys) is None
    api_main.end_login_attempt(keys, tickets[1], ok=True)   # a success gives it back
    assert api_main.begin_login_attempt(keys) is not None


# ====================================================================== oversized customer id

@needs_db
@pytest.mark.parametrize("customer_id", [2 ** 31, 2 ** 63, 10 ** 30])
def test_oversized_customer_id_is_422(make_client, customer_id):
    c = make_client(raise_server_exceptions=False)
    r = c.post("/api/auth/login", json=_wrong(customer_id))
    assert r.status_code == 422
    assert "Traceback" not in r.text


@needs_db
def test_largest_valid_customer_id_is_a_plain_401(make_client):
    c = make_client(raise_server_exceptions=False)
    assert c.post("/api/auth/login", json=_wrong(2 ** 31 - 1)).status_code == 401


# ====================================================================== channel

@needs_db
@pytest.mark.parametrize("channel", ["app", "web", "advisor"])
def test_known_channels_are_echoed(client, login, channel):
    for headers in ({}, login(1)):
        r = client.get("/api/experience/savings", params={"channel": channel}, headers=headers)
        assert r.status_code == 200 and r.json()["channel"] == channel


@needs_db
def test_channel_defaults_to_web(client):
    assert client.get("/api/experience/home").json()["channel"] == "web"


@needs_db
@pytest.mark.parametrize("channel", ["APP", "Web", "mobile", "", " app", "app ", "app,web", "web%00",
                                     "advisor'--", "<script>", "a" * 50])
def test_unknown_channel_is_422(client, login, channel):
    for headers in ({}, login(1)):
        r = client.get("/api/experience/savings", params={"channel": channel}, headers=headers)
        assert r.status_code == 422, channel
        assert "Traceback" not in r.text


@needs_db
def test_channel_enum_is_in_the_openapi_spec(api_main):
    params = api_main.app.openapi()["paths"]["/api/experience/{topic}"]["get"]["parameters"]
    schema = next(p["schema"] for p in params if p["name"] == "channel")
    assert sorted(schema.get("enum", [])) == ["advisor", "app", "web"] and schema.get("default") == "web"


# ====================================================================== persona 5: money stress, help first

def _generator():
    spec = importlib.util.spec_from_file_location("generate_db", ROOT / "data" / "generate_db.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # module level only defines data and functions (build() is behind __main__)
    return mod


def test_generator_declares_persona_5():
    gen = _generator()
    assert gen.EXTRA_DEMO_IDS == {PERSONA_5}
    assert PERSONA_5 > len(gen.DEMO_PERSONAS)  # a seeded customer, not a hand-written override


@needs_db
def test_db_demo_flags_match_the_generator(ro_con):
    gen = _generator()
    flagged = {r[0] for r in ro_con.execute("SELECT customer_id FROM customers WHERE is_demo_persona = 1")}
    assert flagged == set(range(1, len(gen.DEMO_PERSONAS) + 1)) | gen.EXTRA_DEMO_IDS


@needs_db
def test_persona_5_logs_in_and_gets_help_not_sales(client, login):
    h = login(PERSONA_5)
    me = client.get("/api/me", headers=h)
    assert me.status_code == 200 and me.json()["customer_id"] == PERSONA_5 and me.json()["first_name"] == "Jens"

    facts = {f["key"]: f for f in client.get("/api/me/twin", headers=h).json()["facts"]}
    assert facts["money_stress"]["value"] is True and not facts["money_stress"].get("rejected_by_customer")

    m = client.get("/api/me/moments", headers=h).json()
    assert m["held_back"], "expected at least one sales moment held back"
    assert all(x["sales"] and x.get("held_because") for x in m["held_back"])
    assert "support" in {x["kind"] for x in m["push"]}
    assert not [x["kind"] for x in m["push"] + m["feed"] if x["sales"]]  # nothing sold to him

    # Experience pages: once page() is support-first under money stress it says so with `support_first`.
    # Until that lands (recommender is being changed separately) the key is absent and this check is skipped.
    for topic in CATALOG:
        block = client.get(f"/api/experience/{topic}", headers=h).json()
        if "support_first" in block:
            assert block["support_first"] is True, topic


# ====================================================================== seed_credentials is idempotent

def _tmp_bank(path, customers):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, first_name TEXT NOT NULL, "
                "is_demo_persona INTEGER DEFAULT 0)")
    con.executemany("INSERT INTO customers VALUES (?,?,?)", customers)
    con.commit()
    con.close()


def _hashes(path):
    con = sqlite3.connect(path)
    try:
        return dict(con.execute("SELECT customer_id, password_hash FROM credentials"))
    finally:
        con.close()


_LINE = re.compile(r"^customer_id=(\d+)\s+\([^)]*\)\s+password=(\S+)$")


def _file_ids(creds):
    return [int(_LINE.match(line).group(1)) for line in creds.read_text().splitlines()]


def _file_logins_work(creds, db):
    """True when every line in the file verifies against the DB (passwords never leave this function)."""
    from api.security import verify_password
    stored = _hashes(db)
    for line in creds.read_text().splitlines():
        cid, password = _LINE.match(line).groups()
        if not verify_password(password, stored[int(cid)]):
            return False
    return True


def _line_for(creds, cid):
    return next(line for line in creds.read_text().splitlines() if line.startswith(f"customer_id={cid} "))


def test_seed_credentials_is_idempotent_and_only_adds_what_is_missing(tmp_path, monkeypatch, capsys):
    import api.seed_credentials as seed
    db = tmp_path / "bank.db"
    creds = tmp_path / "demo_credentials.txt"
    _tmp_bank(db, [(1, "Ann", 1), (2, "Bert", 0), (3, "Cas", 0)])
    monkeypatch.setattr(seed, "DB", db)

    seed.main([])
    assert set(_hashes(db)) == {1, 2, 3} and _file_ids(creds) == [1]
    assert creds.stat().st_mode & 0o777 == 0o600 and _file_logins_work(creds, db)
    first_hashes, first_file = _hashes(db), creds.read_bytes()

    seed.main([])  # nothing to do: same hashes, same file
    assert _hashes(db) == first_hashes and creds.read_bytes() == first_file

    # A newly flagged demo persona (its password was never written down) gets one, appended to the file.
    con = sqlite3.connect(db)
    con.execute("UPDATE customers SET is_demo_persona = 1 WHERE customer_id = 3")
    con.execute("INSERT INTO customers VALUES (4, 'Dirk', 0)")
    con.commit()
    con.close()
    line_1 = _line_for(creds, 1)
    result = seed.main([])
    assert result["created"] == 1 and [cid for cid, _ in result["issued_for"]] == [3]
    after = _hashes(db)
    assert after[1] == first_hashes[1] and after[2] == first_hashes[2] and after[3] != first_hashes[3] and 4 in after
    assert _file_ids(creds) == [1, 3] and _line_for(creds, 1) == line_1 and _file_logins_work(creds, db)

    # A stale line (e.g. the DB was rebuilt) is detected and that one persona is re-issued.
    creds.write_text(creds.read_text().replace(line_1, "customer_id=1  (Ann)  password=stale-password"))
    seed.main([])
    assert _hashes(db)[1] != first_hashes[1] and _hashes(db)[3] == after[3] and _file_logins_work(creds, db)

    # --rotate keeps the old behaviour: everyone gets a new password.
    before_rotate = _hashes(db)
    seed.main(["--rotate"])
    rotated = _hashes(db)
    assert set(rotated) == {1, 2, 3, 4} and all(rotated[c] != before_rotate[c] for c in rotated)
    assert _file_ids(creds) == [1, 3] and _file_logins_work(creds, db) and creds.stat().st_mode & 0o777 == 0o600

    out = capsys.readouterr().out
    assert "password=" not in out and not any(line.split("password=")[1] in out for line in creds.read_text().splitlines())
