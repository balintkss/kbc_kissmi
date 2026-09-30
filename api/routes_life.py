"""Life moments & gaps for the logged-in customer: /api/me/life-checklists, /coverage-gaps, /benefits.

Customer-scoped only: the customer id comes from the signed bearer token (api.main.current_customer, so ops
tokens are rejected); no id in the path, query or body. Every query behind these endpoints is read-only and
scoped `WHERE customer_id = ?`. The twin is loaded exactly like the other /api/me endpoints (api.main.load_twin,
customer corrections applied), so a rejected fact never drives a checklist, gap or hint.

Mounted from api/main.py with `app.include_router(router)`. api.main is imported lazily inside the dependencies
(same pattern as api/ops.py), so importing this module first never triggers a circular import.
"""
from fastapi import APIRouter, Depends, Header

from twin.benefits import benefits_review
from twin.checklists import life_checklists, load_life_tx
from twin.gaps import coverage_review

router = APIRouter(prefix="/api/me", tags=["life"])


def _customer(authorization: str | None = Header(default=None)):
    from api.main import current_customer  # lazy: api.main mounts this router
    return current_customer(authorization)


def _db():
    from api.main import db  # lazy: api.main mounts this router
    yield from db()


def _twin(con, cid):
    from api.main import load_twin  # lazy: api.main mounts this router; 404 when no twin was built
    return load_twin(con, cid)


@router.get("/life-checklists")
def my_life_checklists(cid=Depends(_customer), con=Depends(_db)):
    """One checklist per recent life event, auto-ticked from what KBC already sees."""
    twin = _twin(con, cid)
    return life_checklists(con, cid, twin, tx=load_life_tx(con, cid))


@router.get("/coverage-gaps")
def my_coverage_gaps(cid=Depends(_customer), con=Depends(_db)):
    """Protection the customer's life calls for but that we don't see; essential-only under money stress."""
    twin = _twin(con, cid)
    return coverage_review(con, cid, twin, tx=load_life_tx(con, cid))


@router.get("/benefits")
def my_benefits(cid=Depends(_customer), con=Depends(_db)):
    """'You may be entitled to…' hints with official sources, plus the turning-25 heads-up."""
    twin = _twin(con, cid)
    return benefits_review(con, cid, twin, tx=load_life_tx(con, cid))
