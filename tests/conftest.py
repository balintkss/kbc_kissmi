"""Shared fixtures for the KBC digital-twin test suite.

Safety rules baked in here:
  * No real LLM traffic: a dummy OPENAI_API_KEY and an unroutable base URL are set before any app
    import, and `twin.assistant.OpenAI` is replaced for every test (tests that want Kate to talk use
    the scripted `fake_openai` fixture).
  * No secrets in output: demo passwords are read from data/demo_credentials.txt only to log in and
    are never bound to test locals, printed or put into assertion messages.
  * No lasting DB changes: rows a test adds to twin_feedback / chat_messages are deleted afterwards.
  * Tests that need the generated database are marked `needs_db` and skipped when it is missing.
"""
import itertools
import json
import os
import re
import secrets
import sqlite3
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB_PATH = ROOT / "data" / "kbc_twin.db"
CREDS_PATH = ROOT / "data" / "demo_credentials.txt"
HAS_DB = DB_PATH.exists()
DEMO_IDS = (1, 2, 3, 4)  # Lotte, Julien, Emma, Marc
MISSING_DB = ("data/kbc_twin.db not found: run `python data/generate_db.py && python -m twin.engine "
              "&& python -m api.seed_credentials` first")

# Must happen before api.env / api.security / openai are imported (api.env never overrides real env vars).
os.environ["OPENAI_API_KEY"] = "sk-test-dummy-key-not-real"
os.environ["OPENAI_BASE_URL"] = "http://127.0.0.1:9/v1"  # discard port: nothing can leave the machine
os.environ["TWIN_SECRET"] = secrets.token_hex(32)       # test-only signing key, tokens die with the process
os.environ["ALLOWED_ORIGINS"] = "http://localhost:5173,http://localhost:3000,http://localhost:8000"


def pytest_collection_modifyitems(config, items):
    if HAS_DB:
        return
    skip = pytest.mark.skip(reason=MISSING_DB)
    for item in items:
        if "needs_db" in item.keywords:
            item.add_marker(skip)


# ---------------------------------------------------------------------- app + database

@pytest.fixture(scope="session")
def api_main():
    """The FastAPI module, imported lazily: importing it creates tables, so never without a DB."""
    if not HAS_DB:
        pytest.skip(MISSING_DB)
    import api.main
    return api.main


@pytest.fixture
def client(api_main):
    from fastapi.testclient import TestClient
    return TestClient(api_main.app)


@pytest.fixture
def make_client(api_main):
    """TestClient factory: pick the client IP and whether server exceptions surface as HTTP 500."""
    from fastapi.testclient import TestClient

    def _make(ip="testclient", raise_server_exceptions=True):
        return TestClient(api_main.app, client=(ip, 50000), raise_server_exceptions=raise_server_exceptions)
    return _make


@pytest.fixture(scope="session")
def ro_con():
    """Read-only connection for assertions against the raw tables (tests may read truth_*, the API may not)."""
    if not HAS_DB:
        pytest.skip(MISSING_DB)
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)
    yield con
    con.close()


@pytest.fixture
def rw_con(_db_guard):
    """Writable connection for code under test that persists (Kate saves chat turns). Cleaned up by _db_guard."""
    if not HAS_DB:
        pytest.skip(MISSING_DB)
    con = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    yield con
    con.close()


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """The login/chat rate limiter is in-memory module state: start every test from a clean slate."""
    mod = sys.modules.get("api.main")
    if mod is not None:
        mod._attempts.clear()
    yield
    mod = sys.modules.get("api.main")
    if mod is not None:
        mod._attempts.clear()


class _DbGuard:
    def __init__(self):
        self.customers = set(DEMO_IDS)

    def track(self, customer_id):
        self.customers.add(int(customer_id))


def _max_id(con, table, column):
    try:
        return con.execute(f"SELECT COALESCE(MAX({column}), 0) FROM {table}").fetchone()[0]
    except sqlite3.OperationalError:  # table not created yet (api.main creates it on import)
        return 0


@pytest.fixture(autouse=True)
def _db_guard():
    """Delete twin_feedback / chat_messages rows created during the test for the customers it used."""
    guard = _DbGuard()
    if not HAS_DB:
        yield guard
        return
    con = sqlite3.connect(DB_PATH, timeout=30)
    base_feedback, base_chat = _max_id(con, "twin_feedback", "rowid"), _max_id(con, "chat_messages", "id")
    con.close()
    yield guard
    con = sqlite3.connect(DB_PATH, timeout=30)
    try:
        ids = sorted(guard.customers)
        marks = ",".join("?" * len(ids))
        for table, column, base in (("twin_feedback", "rowid", base_feedback), ("chat_messages", "id", base_chat)):
            try:
                con.execute(f"DELETE FROM {table} WHERE {column} > ? AND customer_id IN ({marks})", (base, *ids))
            except sqlite3.OperationalError:
                pass
        con.commit()
    finally:
        con.close()


# ---------------------------------------------------------------------- auth helpers

class Redacted(dict):
    """Headers / JSON body carrying a secret. repr() hides the values, so pytest's assertion
    introspection (which prints call arguments) can never show a password or token."""

    def __repr__(self):
        return "{" + ", ".join(f"{k!r}: '<redacted>'" for k in self) + "}"

    __str__ = __repr__


@pytest.fixture(scope="session")
def redacted():
    return Redacted


class DemoSecrets:
    """Demo persona passwords from data/demo_credentials.txt. Never printed: repr is redacted."""
    _LINE = re.compile(r"^\s*customer_id=(\d+)\s+\(([^)]*)\)\s+password=(\S+)\s*$")

    def __init__(self, path):
        self._pw = {}
        for line in path.read_text().splitlines():
            m = self._LINE.match(line)
            if m:
                self._pw[int(m.group(1))] = m.group(3)

    def __repr__(self):
        return f"<DemoSecrets for customers {sorted(self._pw)} (redacted)>"

    def reveal(self, customer_id):
        if customer_id not in self._pw:
            pytest.skip(f"no demo password for customer {customer_id} in data/demo_credentials.txt")
        return self._pw[customer_id]

    def login_body(self, customer_id):
        return Redacted(customer_id=customer_id, password=self.reveal(customer_id))


@pytest.fixture(scope="session")
def demo_secrets():
    if not HAS_DB:
        pytest.skip(MISSING_DB)
    if not CREDS_PATH.exists():
        pytest.skip("data/demo_credentials.txt not found: run `python -m api.seed_credentials`")
    return DemoSecrets(CREDS_PATH)


_SESSION_TOKENS = {}  # customer_id -> (token, expires_in); logging in costs a 200k-round PBKDF2


class _Login:
    def __init__(self, client, secrets_, guard):
        self._client, self._secrets, self._guard = client, secrets_, guard

    def __call__(self, customer_id):
        """Log in through POST /api/auth/login and return the Authorization header for that customer."""
        self._guard.track(customer_id)
        if customer_id not in _SESSION_TOKENS:
            r = self._client.post("/api/auth/login", json=self._secrets.login_body(customer_id))
            assert r.status_code == 200, f"demo login for customer {customer_id} failed with HTTP {r.status_code}"
            body = r.json()
            _SESSION_TOKENS[customer_id] = (body["token"], int(body.get("expires_in") or 3600))
        return Redacted(Authorization=f"Bearer {_SESSION_TOKENS[customer_id][0]}")

    def expires_in(self, customer_id):
        self(customer_id)
        return _SESSION_TOKENS[customer_id][1]


@pytest.fixture
def login(client, demo_secrets, _db_guard):
    return _Login(client, demo_secrets, _db_guard)


@pytest.fixture
def track_customer(_db_guard):
    """For tests that write through the code directly (not via login): register the customer for cleanup."""
    return _db_guard.track


@pytest.fixture
def advance_clock(monkeypatch):
    """Jump the wall clock forward (tokens, rate-limit windows) without sleeping."""
    real = time.time

    def _advance(seconds):
        fake = lambda: real() + seconds  # noqa: E731
        monkeypatch.setattr(time, "time", fake)
        for name in ("api.security", "api.main"):  # also covers a `from time import time` style import
            mod = sys.modules.get(name)
            for attr in ("time", "_time", "now"):
                if mod is not None and getattr(mod, attr, None) is real:
                    monkeypatch.setattr(mod, attr, fake)
    return _advance


# ---------------------------------------------------------------------- scripted LLM

def completion(message):
    """A real openai ChatCompletion object, so the assistant's model_dump() etc. behave as in production."""
    from openai.types.chat import ChatCompletion
    return ChatCompletion.model_validate({
        "id": "chatcmpl-test", "object": "chat.completion", "created": 0, "model": "gpt-test",
        "choices": [{"index": 0, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
                     "message": message}]})


class FakeLLM:
    """Stand-in for `OpenAI()`: replays a script of responses and records every request."""
    _ids = itertools.count(1)

    def __init__(self):
        self.script, self.calls = [], []
        self.default_answer = "Prima, dat lukt."
        self.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=self._create)))

    def say(self, text):
        self.script.append(completion({"role": "assistant", "content": text}))
        return self

    def call_tools(self, *calls):
        """Each call is (name, arguments) where arguments is a dict or a raw (possibly broken) JSON string."""
        tool_calls = [{"id": f"call_{next(self._ids)}", "type": "function",
                       "function": {"name": name, "arguments": args if isinstance(args, str) else json.dumps(args)}}
                      for name, args in calls]
        self.script.append(completion({"role": "assistant", "content": None, "tool_calls": tool_calls}))
        return self

    def fail(self, exc):
        self.script.append(exc)
        return self

    def _create(self, **kwargs):
        self.calls.append(dict(kwargs, messages=list(kwargs.get("messages", []))))
        item = self.script.pop(0) if self.script else completion({"role": "assistant", "content": self.default_answer})
        if isinstance(item, BaseException):
            raise item
        return item

    def system_prompt(self, call=0):
        first = self.calls[call]["messages"][0]
        assert first["role"] == "system"
        return first["content"]

    def tool_results(self, call=-1):
        """Tool outputs (parsed JSON) the assistant sent back to the model in the given request."""
        return [json.loads(m["content"]) for m in self.calls[call]["messages"]
                if isinstance(m, dict) and m.get("role") == "tool"]


class _NoNetworkOpenAI:
    def __init__(self, *args, **kwargs):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._refuse))

    @staticmethod
    def _refuse(**kwargs):
        raise AssertionError("a test tried to call the real OpenAI API; use the fake_openai fixture")


@pytest.fixture(autouse=True)
def _block_real_openai(monkeypatch):
    import twin.assistant
    monkeypatch.setattr(twin.assistant, "OpenAI", _NoNetworkOpenAI)


@pytest.fixture
def fake_openai(monkeypatch):
    import twin.assistant
    fake = FakeLLM()
    monkeypatch.setattr(twin.assistant, "OpenAI", lambda *a, **k: fake.client)
    return fake
