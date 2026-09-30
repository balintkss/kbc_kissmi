"""One API for every channel (app, website, advisor tools).

The customer is always taken from the signed token, never from the URL or body,
so one customer can never read another customer's twin (no IDOR).

Run:  uvicorn api.main:app --reload
"""
import json
import os
import sqlite3
import time
from collections import defaultdict, deque

import api.env  # noqa: F401  (must run before api.security reads TWIN_SECRET)
from fastapi import Depends, FastAPI, Header, HTTPException, Path, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api.security import issue_token, read_token, verify_password
from twin.assistant import Assistant
from twin.catalog import CATALOG
from twin.engine import DB
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

_attempts = defaultdict(deque)
MAX_ATTEMPTS, WINDOW = 5, 300


def _rate_limited(key, limit=MAX_ATTEMPTS, window=WINDOW):
    q, now = _attempts[key], time.time()
    while q and q[0] < now - window:
        q.popleft()
    if len(q) >= limit:
        return True
    q.append(now)
    return False


class Login(BaseModel):
    customer_id: int = Field(gt=0)
    password: str = Field(min_length=1, max_length=128)


@app.post("/api/auth/login")
def login(body: Login, request: Request, con=Depends(db)):
    ip = request.client.host if request.client else "unknown"
    if _rate_limited(f"ip:{ip}") or _rate_limited(f"cid:{body.customer_id}"):
        raise HTTPException(429, "Too many attempts, try again in a few minutes")
    row = con.execute("SELECT password_hash FROM credentials WHERE customer_id = ?", (body.customer_id,)).fetchone()
    if not row or not verify_password(body.password, row[0]):
        raise HTTPException(401, "Invalid customer id or password")
    return {"token": issue_token(body.customer_id), "token_type": "bearer", "expires_in": 3600}


def _customer_from_header(authorization):
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    cid = read_token(token) if scheme.lower() == "bearer" else None
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
    # Customer corrections win over inference: a fact they rejected is never used again.
    for fact, correct, note in con.execute(
            "SELECT fact, correct, note FROM twin_feedback WHERE customer_id = ? ORDER BY created_at", (cid,)):
        if fact in twin["facts"]:
            twin["facts"][fact]["rejected_by_customer"] = not correct
            twin["facts"][fact]["confirmed_by_customer"] = bool(correct)
            if note:
                twin["facts"][fact]["customer_note"] = note
    return twin


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


@app.get("/api/experience/{topic}")
def experience(topic: str = Path(pattern=r"^[a-z_]{1,40}$"), channel: str = "web",
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
