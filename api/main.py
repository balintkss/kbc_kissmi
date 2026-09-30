"""One API for every channel (app, website, advisor tools).

The customer is always taken from the signed token, never from the URL or body,
so one customer can never read another customer's twin (no IDOR).

Run:  uvicorn api.main:app --reload
"""
import json
import os
import sqlite3
import threading
import time
from collections import defaultdict, deque
from typing import Literal

import api.env  # noqa: F401  (must run before api.security reads TWIN_SECRET)
from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api.security import issue_token, read_token, verify_password
from twin.assistant import Assistant
from twin.catalog import CATALOG
from twin.engine import DB
from twin.feedback import apply_feedback
from twin.recommender import moments, page

app = FastAPI(title="KBC Digital Twin API", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000,http://localhost:8000").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


def db():
    con = sqlite3.connect(DB, check_same_thread=False)
    try:
        yield con
    finally:
        con.close()


with sqlite3.connect(DB) as _con:
    _con.execute("""CREATE TABLE IF NOT EXISTS twin_feedback (
        customer_id INTEGER NOT NULL, fact TEXT NOT NULL, correct INTEGER NOT NULL, note TEXT, created_at REAL NOT NULL)""")
    _con.execute("""CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER NOT NULL, role TEXT NOT NULL,
        content TEXT NOT NULL, created_at TEXT NOT NULL)""")


# ---------------------------------------------------------------------- auth

_attempts = defaultdict(deque)   # key -> timestamps (in-memory, reset on restart)
_attempts_lock = threading.Lock()  # sync endpoints run in a thread pool
MAX_ATTEMPTS, WINDOW = 5, 300       # login: 5 FAILED attempts per 5 min, per IP and per account


def _prune(q, now, window):
    while q and q[0] < now - window:
        q.popleft()


def _rate_limited(key, limit=MAX_ATTEMPTS, window=WINDOW):
    """Count this request against `key`; True when over the limit (chat, ops views: every call counts)."""
    with _attempts_lock:
        q, now = _attempts[key], time.time()
        _prune(q, now, window)
        if len(q) >= limit:
            return True
        q.append(now)
        return False


def begin_login_attempt(keys, limit=MAX_ATTEMPTS, window=WINDOW):
    """Login throttle, checked BEFORE the password is verified. Only failed attempts count.

    Returns None when any key already has `limit` failures in the window (-> 429). Otherwise it
    reserves one slot on every key and returns a ticket for `end_login_attempt`. The slot is held
    while the password is checked, so a burst of parallel guesses can't all slip past the check.
    """
    with _attempts_lock:
        now = time.time()
        queues = [_attempts[k] for k in keys]
        for q in queues:
            _prune(q, now, window)
        if any(len(q) >= limit for q in queues):
            return None
        for q in queues:
            q.append(now)
        return now


def end_login_attempt(keys, ticket, ok, clear=()):
    """A failed attempt keeps its slot. A successful one gives it back (logging in and out is free)
    and also clears the failure history of the keys in `clear` (the account, never the IP)."""
    if not ok:
        return
    with _attempts_lock:
        for k in keys:
            q = _attempts.get(k)
            if q is not None and ticket in q:
                q.remove(ticket)
        for k in clear:
            _attempts.pop(k, None)


class Login(BaseModel):
    customer_id: int = Field(gt=0, lt=2**31)  # 32-bit ids: huge values are a clean 422, never a SQLite OverflowError (500)
    password: str = Field(min_length=1, max_length=128)


@app.post("/api/auth/login")
def login(body: Login, request: Request, con=Depends(db)):
    ip = request.client.host if request.client else "unknown"
    keys = (f"ip:{ip}", f"cid:{body.customer_id}")
    ticket = begin_login_attempt(keys)
    if ticket is None:
        raise HTTPException(429, "Too many attempts, try again in a few minutes")
    ok = False
    try:
        row = con.execute("SELECT password_hash FROM credentials WHERE customer_id = ?", (body.customer_id,)).fetchone()
        ok = bool(row) and verify_password(body.password, row[0])
    finally:
        end_login_attempt(keys, ticket, ok, clear=(f"cid:{body.customer_id}",))
    if not ok:
        raise HTTPException(401, "Invalid customer id or password")
    return {"token": issue_token(body.customer_id), "token_type": "bearer", "expires_in": 3600}


class DemoLogin(BaseModel):
    customer_id: int = Field(gt=0, lt=2**31)


@app.post("/api/auth/demo-login")
def demo_login(body: DemoLogin, request: Request, con=Depends(db)):
    """One-click login for the flagged SYNTHETIC demo personas only (customers.is_demo_persona = 1), no password.

    Deliberate demo convenience: every other customer still needs POST /api/auth/login. The token is an ordinary
    customer token (same role, TTL and scoping), so it only ever opens that persona's own data. Disable with
    TWIN_DEMO_LOGIN=0; a real deployment would not ship this endpoint.
    """
    if os.environ.get("TWIN_DEMO_LOGIN", "1") == "0":
        raise HTTPException(404, "Not found")
    ip = request.client.host if request.client else "unknown"
    if _rate_limited(f"demo:{ip}", limit=30, window=60):
        raise HTTPException(429, "Too many attempts, try again in a minute")
    row = con.execute("SELECT is_demo_persona FROM customers WHERE customer_id = ?", (body.customer_id,)).fetchone()
    if not row or not row[0]:
        raise HTTPException(403, "One-click login is only available for the synthetic demo personas")
    return {"token": issue_token(body.customer_id), "token_type": "bearer", "expires_in": 3600, "demo": True}


def _customer_from_header(authorization):
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    cid = read_token(token, role="customer") if scheme.lower() == "bearer" else None  # ops tokens never pass
    if cid is None:
        raise HTTPException(401, "Invalid or expired session", headers={"WWW-Authenticate": "Bearer"})
    return cid


def optional_customer(authorization: str | None = Header(default=None)):
    return _customer_from_header(authorization)


def current_customer(authorization: str | None = Header(default=None)):
    cid = _customer_from_header(authorization)
    if cid is None:
        raise HTTPException(401, "Login required", headers={"WWW-Authenticate": "Bearer"})
    return cid


# ---------------------------------------------------------------------- twin access

def load_twin(con, cid):
    row = con.execute("SELECT profile_json FROM twin_profile WHERE customer_id = ?", (cid,)).fetchone()
    if not row:
        raise HTTPException(404, "No twin built for this customer yet")
    twin = json.loads(row[0])
    # Customer corrections win over inference: a rejected fact is never used again and no longer shapes the plan.
    rows = con.execute(
        "SELECT fact, correct, note FROM twin_feedback WHERE customer_id = ? ORDER BY created_at", (cid,)).fetchall()
    return apply_feedback(twin, rows)


def _evidence(con, cid, tx_ids):
    if not tx_ids:
        return []
    marks = ",".join("?" * len(tx_ids))
    rows = con.execute(f"""SELECT tx_id, booked_at, amount, counterparty, description FROM transactions
                           WHERE customer_id = ? AND tx_id IN ({marks}) ORDER BY booked_at DESC""", (cid, *tx_ids)).fetchall()
    return [dict(zip(("tx_id", "date", "amount", "counterparty", "description"), r)) for r in rows]


# ---------------------------------------------------------------------- endpoints

@app.get("/api/topics")
def topics():
    return [{"id": k, "title": v["title"]} for k, v in CATALOG.items()]


Channel = Literal["app", "web", "advisor"]


@app.get("/api/experience/{topic}")
def experience(topic: str = Path(pattern=r"^[a-z_]{1,40}$"), channel: Channel = Query(default="web"),
               cid=Depends(optional_customer), con=Depends(db)):
    """Channel-agnostic block. Anonymous: every variant. Logged in: one highlight + reason."""
    if topic not in CATALOG:
        raise HTTPException(404, "Unknown topic")
    block = page(load_twin(con, cid) if cid else None, topic)
    return dict(block, channel=channel)


@app.get("/api/me")
def me(cid=Depends(current_customer), con=Depends(db)):
    t = load_twin(con, cid)
    return {k: t[k] for k in ("customer_id", "name", "first_name", "language", "city", "age", "kbc_products")}


@app.get("/api/me/twin")
def my_twin(with_evidence: bool = False, cid=Depends(current_customer), con=Depends(db)):
    """Glass box: everything KBC believes about me, why, and what it means."""
    t = load_twin(con, cid)
    facts = []
    for f in t["facts"].values():
        item = {k: v for k, v in f.items() if k != "evidence"}
        if with_evidence:
            item["evidence"] = _evidence(con, cid, f["evidence"])
        facts.append(item)
    return dict(name=t["name"], as_of=t["as_of"], facts=facts, recurring=t["recurring"])


@app.get("/api/me/plan")
def my_plan(cid=Depends(current_customer), con=Depends(db)):
    return load_twin(con, cid)["plan"]


@app.get("/api/me/moments")
def my_moments(cid=Depends(current_customer), con=Depends(db)):
    return moments(load_twin(con, cid))


class Feedback(BaseModel):
    correct: bool
    note: str | None = Field(default=None, max_length=280)


@app.post("/api/me/facts/{fact}/feedback")
def fact_feedback(body: Feedback, fact: str = Path(pattern=r"^[a-z_]{1,40}$"), cid=Depends(current_customer), con=Depends(db)):
    """'That's right' / 'That's not me' — the customer corrects their own twin."""
    if fact not in load_twin(con, cid)["facts"]:
        raise HTTPException(404, "Unknown fact")
    con.execute("INSERT INTO twin_feedback VALUES (?,?,?,?,?)", (cid, fact, int(body.correct), body.note, time.time()))
    con.commit()
    return {"fact": fact, "correct": body.correct}


# ---------------------------------------------------------------------- chat (pull)

class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


@app.get("/api/me/chat")
def chat_history(cid=Depends(current_customer), con=Depends(db)):
    """History plus Kate's opener, so the customer never has to start from zero."""
    kate = Assistant(con, cid, load_twin(con, cid))
    return {"opener": kate.opener(), "history": kate.history(limit=30)}


@app.post("/api/me/chat")
def chat(body: ChatIn, request: Request, cid=Depends(current_customer), con=Depends(db)):
    if _rate_limited(f"chat:{cid}", limit=20, window=60):
        raise HTTPException(429, "Slow down a little")
    try:
        return Assistant(con, cid, load_twin(con, cid)).reply(body.message)
    except Exception as e:  # never leak provider errors or keys to the client
        if e.__class__.__module__.startswith("openai"):
            raise HTTPException(503, "Kate is unavailable right now") from None
        raise


# ---------------------------------------------------------------------- ops & advisor channel (api/ops.py)

from api.ops import pages as ops_pages, router as ops_router  # noqa: E402  (ops role tokens only)

app.include_router(ops_router)   # /api/ops/*
app.include_router(ops_pages)    # /ops dashboard (static, same origin)


# ---------------------------------------------------------------------- money foresight (api/routes_foresight.py)

from api.routes_foresight import router as foresight_router  # noqa: E402  (customer token only)

app.include_router(foresight_router)  # /api/me/forecast, /api/me/payday-sorter*, /api/me/self-employed, /api/me/moments-plus


# ---------------------------------------------------------------------- life moments & gaps (api/routes_life.py)

from api.routes_life import router as life_router  # noqa: E402  (customer token only)

app.include_router(life_router)  # /api/me/life-checklists, /api/me/coverage-gaps, /api/me/benefits
