"""Money foresight for the logged-in customer: forecast, approve-to-act payday sorter, self-employed envelope.

  GET  /api/me/forecast                 safe-to-spend until payday + early overdraft warning (twin/forecast.py)
  GET  /api/me/payday-sorter            proposed pots for the next payday + the active mandate, if any (twin/sorter.py)
  POST /api/me/payday-sorter/approve    {"pots": ["bills", "car_upkeep", ...]}: pot ids only, amounts are recomputed
                                        here; unknown / non-movable ids -> 422
  POST /api/me/payday-sorter/revoke     stop the active mandate
  GET  /api/me/self-employed            reserve envelope, or {"applicable": false} (twin/selfemployed.py)
  GET  /api/me/moments-plus             /api/me/moments + foresight moments (overdraft_warning, self_employed_reserve)
                                        + life moments (life_checklist, coverage_gap, benefit_hint, turning_25,
                                        household_change_prompt); a checklist replaces the single-event message

Identity comes only from the customer token (api.main.current_customer): no customer id in any path, query or body.
POSTs are lightly rate-limited per customer. api.main mounts this router at its bottom, so everything from
api.main is imported lazily inside the dependencies (no circular import, whichever module is imported first).
Nothing moves money: the sorter is a simulation and says so in every response.
"""
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, StringConstraints

from twin import selfemployed, sorter
from twin.engine import DB
from twin.forecast import forecast, foresight_moments
from twin.recommender import moments

router = APIRouter(prefix="/api/me", tags=["foresight"])

POSTS_PER_MINUTE = 10
PotId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]{1,40}$")]

_con = sqlite3.connect(DB, timeout=10)
try:
    sorter.ensure_schema(_con)
finally:
    _con.close()


def _customer(authorization: str | None = Header(default=None)):
    from api.main import current_customer  # lazy: api.main mounts this router
    return current_customer(authorization)


def _db():
    from api.main import db  # lazy: api.main mounts this router
    yield from db()


def _twin(con, cid):
    from api.main import load_twin  # feedback-applied twin, 404 when none was built
    return load_twin(con, cid)


def _throttle(cid):
    from api.main import _rate_limited
    if _rate_limited(f"foresight:{cid}", limit=POSTS_PER_MINUTE, window=60):
        raise HTTPException(429, "Slow down a little")


@router.get("/forecast")
def my_forecast(cid=Depends(_customer), con=Depends(_db)):
    return forecast(con, cid, _twin(con, cid))


@router.get("/payday-sorter")
def my_sorter(cid=Depends(_customer), con=Depends(_db)):
    twin = _twin(con, cid)
    mandate = sorter.current_mandate(con, cid)
    if mandate:
        mandate["next_run"] = sorter.preview(twin, mandate)
    return dict(sorter.proposal(twin), mandate=mandate)


class Approval(BaseModel):
    """Only pot ids from GET /api/me/payday-sorter. Amounts are never taken from the client (extra keys are ignored)."""
    pots: list[PotId] = Field(min_length=1, max_length=20)


@router.post("/payday-sorter/approve")
def approve_sorter(body: Approval, cid=Depends(_customer), con=Depends(_db)):
    _throttle(cid)
    twin = _twin(con, cid)
    try:
        return sorter.approve(con, cid, twin, body.pots)
    except sorter.UnknownPots as e:
        raise HTTPException(422, [dict(loc=["body", "pots", body.pots.index(p)], type="value_error",
                                       msg="This pot stays on your current account" if p in sorter.KEEP else "Unknown pot id")
                                  for p in e.ids]) from None
    except sorter.NoPlan as e:
        raise HTTPException(409, str(e)) from None


@router.post("/payday-sorter/revoke")
def revoke_sorter(cid=Depends(_customer), con=Depends(_db)):
    _throttle(cid)
    return sorter.revoke(con, cid)


@router.get("/self-employed")
def my_self_employed(cid=Depends(_customer), con=Depends(_db)):
    return selfemployed.envelope(con, cid, _twin(con, cid))


# A life-moment checklist replaces the older single-event message about the same event.
_COVERED_BY_CHECKLIST = {"moved": {"moved"}, "new_car": {"new_car"}, "new_job": {"first_job", "new_job"},
                         "new_baby": {"new_baby"}}


@router.get("/moments-plus")
def my_moments_plus(cid=Depends(_customer), con=Depends(_db)):
    """Moments + foresight (overdraft, self-employed reserve) + life moments (checklists, gaps, benefits)."""
    from twin.checklists import checklists, life_moments  # lazy: keeps this router importable on its own

    twin = _twin(con, cid)
    events = {c.get("event") for c in checklists(con, cid, twin)}
    drop = {kind for kind, evs in _COVERED_BY_CHECKLIST.items() if evs & events}
    result = moments(twin, extra=foresight_moments(con, cid, twin) + life_moments(con, cid, twin))
    if not drop:
        return result
    ranked = sorted((m for m in result["push"] + result["feed"] if m["kind"] not in drop), key=lambda m: -m["priority"])
    n_push = len(result["push"])
    # held_back stays complete: it is the evidence of what KBC deliberately did not send
    return dict(result, push=ranked[:n_push], feed=ranked[n_push:])
