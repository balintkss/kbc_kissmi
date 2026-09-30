"""Ops & advisor channel: the population dashboard (/ops) and its API under /api/ops.

Security model
  * Separate identities. Ops users live in ops_users (seeded by `python -m api.seed_ops`), never in
    the customer credentials. Their tokens carry role "ops": customer endpoints reject them, and
    customer tokens are rejected here, even when a customer id and a username look alike.
  * Every ops request re-checks that the user still exists with role "ops", so revoking works at once.
  * Login is rate-limited per IP and per username (the same limiter and limits as customer login);
    drill-down reads are rate-limited per advisor to stop bulk scraping.
  * Every access to an individual customer's data (listed in the picker or opened) is written to
    ops_audit (at, username, customer_id, action). So are ops logins.
  * Responses only carry inferred twin data, master data and products: never the evaluation tables,
    credentials or chat content.
"""
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path as FilePath

import api.env  # noqa: F401  (must run before api.security reads TWIN_SECRET)
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.security import TOKEN_TTL, hash_password, issue_token, read_token, verify_password
from api.seed_ops import OPS_SCHEMA
from twin import population
from twin.engine import DB

router = APIRouter(prefix="/api/ops", tags=["ops"])
pages = APIRouter(include_in_schema=False)

ROLE = "ops"
NAME_RE = r"^[a-z_]{1,40}$"
VIEWS_PER_MINUTE = 120
DASHBOARD = FilePath(__file__).resolve().parent.parent / "dashboard"
AUDIT_SCHEMA = """CREATE TABLE IF NOT EXISTS ops_audit (
    at TEXT NOT NULL, username TEXT NOT NULL, customer_id INTEGER, action TEXT NOT NULL)"""

_con = sqlite3.connect(DB, timeout=10)
try:
    with _con:
        _con.execute(OPS_SCHEMA)
        _con.execute(AUDIT_SCHEMA)
        _con.execute("CREATE INDEX IF NOT EXISTS idx_ops_audit_customer ON ops_audit(customer_id, at)")
finally:
    _con.close()

# Unknown usernames still pay for one PBKDF2 check, so response time doesn't reveal which usernames exist.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def db():
    con = sqlite3.connect(DB, check_same_thread=False, timeout=10)
    try:
        yield con
    finally:
        con.close()


def _rate_limited(key, **kw):
    # Shared with customer login: same in-memory state (api.main._attempts) and the same limits.
    from api.main import _rate_limited as limiter  # lazy: api.main mounts this router
    return limiter(key, **kw)


def _customer_twin(con, customer_id):
    """The twin exactly as the customer-facing endpoints load it (the customer's own corrections applied)."""
    from api.main import load_twin  # lazy: api.main mounts this router
    try:
        return load_twin(con, customer_id)
    except HTTPException:
        return None


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _audit(con, username, customer_ids, action):
    ids = customer_ids if isinstance(customer_ids, list) else [customer_ids]
    con.executemany("INSERT INTO ops_audit (at, username, customer_id, action) VALUES (?,?,?,?)",
                    [(_now(), username, cid, action) for cid in ids])
    con.commit()


# ---------------------------------------------------------------------- auth

class OpsLogin(BaseModel):
    username: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_.-]+$")
    password: str = Field(min_length=1, max_length=128)


@router.post("/login")
def ops_login(body: OpsLogin, request: Request, con=Depends(db)):
    ip = request.client.host if request.client else "unknown"
    if _rate_limited(f"ops_ip:{ip}") or _rate_limited(f"ops_user:{body.username}"):
        raise HTTPException(429, "Too many attempts, try again in a few minutes")
    row = con.execute("SELECT password_hash, role FROM ops_users WHERE username = ?", (body.username,)).fetchone()
    password_ok = verify_password(body.password, row[0] if row else _DUMMY_HASH)
    ok = bool(row) and password_ok and row[1] == ROLE
    _audit(con, body.username, None, "login" if ok else "login_failed")
    if not ok:
        raise HTTPException(401, "Invalid username or password")
    return {"token": issue_token(body.username, role=ROLE), "token_type": "bearer", "expires_in": TOKEN_TTL,
            "username": body.username}


def current_ops(authorization: str | None = Header(default=None), con=Depends(db)):
    scheme, _, token = (authorization or "").partition(" ")
    user = read_token(token, role=ROLE) if scheme.lower() == "bearer" and token else None
    if user is not None:
        row = con.execute("SELECT role FROM ops_users WHERE username = ?", (user,)).fetchone()
        if row and row[0] == ROLE:
            return user
    raise HTTPException(401, "Ops login required", headers={"WWW-Authenticate": "Bearer"})


def _throttle(user):
    if _rate_limited(f"ops_view:{user}", limit=VIEWS_PER_MINUTE, window=60):
        raise HTTPException(429, "Too many requests, slow down")


# ---------------------------------------------------------------------- endpoints

@router.get("/overview")
def ops_overview(user=Depends(current_ops), con=Depends(db)):
    """Population aggregates over all twins (counts only, no individual customers)."""
    return population.overview(con)


@router.get("/customers")
def ops_customers(has: str | None = Query(default=None, pattern=NAME_RE),
                  event: str | None = Query(default=None, pattern=NAME_RE),
                  limit: int = Query(default=20, ge=1, le=50),
                  user=Depends(current_ops), con=Depends(db)):
    """Advisor picker: customers with fact `has` and/or a life event `event` in the last 90 days."""
    _throttle(user)
    try:
        result = population.search(con, has=has, event=event, limit=limit)
    except ValueError:
        raise HTTPException(422, "Unknown fact or event filter") from None
    if result["customers"]:
        _audit(con, user, [c["customer_id"] for c in result["customers"]], f"list has={has or '-'} event={event or '-'}")
    return result


@router.get("/customers/{customer_id}")
def ops_customer(customer_id: int = Path(gt=0, le=2_147_483_647), user=Depends(current_ops), con=Depends(db)):
    """The advisor sees the same twin as the customer: facts, plan, one highlight per topic, moments."""
    _throttle(user)
    view = None
    if con.execute("SELECT 1 FROM customers WHERE customer_id = ?", (customer_id,)).fetchone():
        twin = _customer_twin(con, customer_id)
        view = population.customer_view(con, customer_id, twin=twin) if twin is not None else None
    _audit(con, user, customer_id, "view" if view else "view_not_found")
    if view is None:
        raise HTTPException(404, "Unknown customer")
    return view


# ---------------------------------------------------------------------- dashboard (static, same origin)

CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
_ASSET_HEADERS = {"Content-Security-Policy": CSP, "Cross-Origin-Opener-Policy": "same-origin",
                  "Cross-Origin-Resource-Policy": "same-origin"}


def _asset(name, media_type):
    return FileResponse(DASHBOARD / name, media_type=media_type, headers=_ASSET_HEADERS)


@pages.get("/ops")
def ops_page():
    return _asset("index.html", "text/html; charset=utf-8")


@pages.get("/ops/dashboard.js")
def ops_script():
    return _asset("dashboard.js", "text/javascript; charset=utf-8")


@pages.get("/ops/dashboard.css")
def ops_styles():
    return _asset("dashboard.css", "text/css; charset=utf-8")
