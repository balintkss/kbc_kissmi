"""Approve-to-act payday sorter: Kate proposes how to split the next payday, the customer approves, only then it acts.

This is the "agentic, but only with explicit customer approval" pattern from KBC's Kate roadmap, in the shape of
Monzo's salary sorter (docs/research/kate_ecosystem_pfa.md §C, idea 1):

  proposal(twin)  pots for the next payday, straight from the (feedback-applied) payday plan, in this order:
                    bills          bills until the next payday                      (moved to a bills pot)
                    everyday       groceries & fuel estimate                        (stays on the current account)
                    <reserve ids>  one pot per plan reserve: yearly_bills, car_upkeep, pet_care, ...  (moved)
                    savings        the planned savings transfer                     (moved)
                    free_to_spend  whatever is left                                 (stays on the current account)
                  Each pot is funded in that order until the income runs out, so under a shortfall the bills come
                  first and the shortfall is shown, never hidden. Under money stress there is no savings pot.
  approve(...)    the client sends pot ids only. Unknown or non-movable ids are rejected; amounts are always
                  recomputed here, at approval time. Stores a row in sorter_mandates (the previous active mandate
                  is superseded).
  revoke(...)     stops the active mandate.

PoC: nothing is ever moved. Every response says so ("simulation": true).
Pot ids are stable: they come from fixed names or the reserve label ("car upkeep" -> car_upkeep, any "<pet> care"
-> pet_care), never from amounts or positions.
"""
import json
import re
import sqlite3
from datetime import datetime, timezone

from twin.forecast import fixed_payday
from twin.recommender import _fact, _nice_date

SCHEMA = """CREATE TABLE IF NOT EXISTS sorter_mandates (
    id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER NOT NULL, created_at TEXT NOT NULL,
    pots_json TEXT NOT NULL, status TEXT NOT NULL)"""
INDEX = "CREATE INDEX IF NOT EXISTS idx_sorter_mandates_customer ON sorter_mandates(customer_id, status)"
SIMULATION = ("Simulation: in this prototype no money moves. For real, nothing would move without your approval, "
              "and you can stop it any time.")
KEEP = {"everyday", "free_to_spend"}  # these stay on the current account: nothing to move, nothing to approve


class UnknownPots(ValueError):
    """Pot ids that are not movable pots of the server's current proposal."""

    def __init__(self, ids):
        super().__init__(f"unknown pot ids: {ids}")
        self.ids = ids


class NoPlan(ValueError):
    pass


def ensure_schema(con):
    con.execute(SCHEMA)
    con.execute(INDEX)
    con.commit()


def _reserve_id(label):
    text = (label or "").strip().lower()
    if text.endswith(" care"):
        return "pet_care"
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")[:40] or "reserve"


def _money(x):
    return f"€{round(x):,}"


def _when(twin):
    payday = fixed_payday(twin)
    if payday:
        return payday, f"On {_nice_date(payday)}"
    kind = ((twin or {}).get("plan") or {}).get("income_kind")
    return None, "When your next invoice lands" if kind == "irregular" else "When your next income lands"


def _join(parts):
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _moves(pots):
    return [f"{_money(p['amount'])} to {p['label']}" for p in pots if p["id"] not in KEEP and round(p["amount"]) > 0]


def proposal(twin):
    """Pots for the next payday. Amounts are the plan's; ids are stable."""
    plan = (twin or {}).get("plan")
    if not isinstance(plan, dict) or not isinstance(plan.get("income"), (int, float)):
        return dict(available=False, payday=None, pots=[], shortfall=0, simulation=True,
                    message="We don't see a regular income yet, so there's no payday to sort.")
    stress = _fact(twin, "money_stress") is not None
    payday, when = _when(twin)
    wanted = [dict(id="bills", label="Bills", need=plan.get("bills_until_next_payday") or 0,
                   items=[b.get("name") for b in plan.get("bills") or []]),
              dict(id="everyday", label="Groceries & fuel",
                   need=sum(v.get("amount") or 0 for v in plan.get("variable_essentials") or []),
                   items=[v.get("name") for v in plan.get("variable_essentials") or []])]
    seen = {"bills", "everyday", "savings", "free_to_spend"}
    for r in plan.get("reserves") or []:
        pid, n = _reserve_id(r.get("for_")), 2
        while pid in seen:
            pid, n = f"{_reserve_id(r.get('for_'))}_{n}", n + 1
        seen.add(pid)
        label = (r.get("for_") or "Reserve")
        wanted.append(dict(id=pid, label=label[:1].upper() + label[1:], need=r.get("monthly") or 0, items=r.get("items") or []))
    if not stress and plan.get("planned_savings"):
        wanted.append(dict(id="savings", label="Savings", need=plan["planned_savings"], items=[]))

    left = float(plan["income"])
    pots = []
    for w in wanted:
        amount = max(0.0, min(float(w["need"]), left))
        left -= amount
        pots.append(dict(id=w["id"], label=w["label"], amount=round(amount), planned=round(w["need"]),
                         short=round(w["need"] - amount), approvable=w["id"] not in KEEP, items=w["items"]))
    free = max(0.0, left)
    pots.append(dict(id="free_to_spend", label="Free to spend", amount=round(free), planned=round(free), short=0,
                     approvable=False, items=[]))
    shortfall = round(max(0.0, sum(float(w["need"]) for w in wanted) - float(plan["income"])))

    moves = _moves(pots)
    everyday = next(p for p in pots if p["id"] == "everyday")
    text = f"{when} Kate would move " + _join(moves) + "." if moves else f"{when} there's nothing left to move."
    if everyday["amount"]:
        text += f" {_money(everyday['amount'])} stays for groceries & fuel"
        text += f" and {_money(free)} is free to spend." if round(free) else "."
    if shortfall:
        text += f" Honestly: this plan is {_money(shortfall)} short, so bills come first and the rest waits."
    if stress:
        text += " No savings pot for now: bills first."
    return dict(available=True, payday=payday.isoformat() if payday else None, income=round(plan["income"]),
                income_kind=plan.get("income_kind"), support_first=stress, pots=pots, shortfall=shortfall,
                message=text + " " + SIMULATION, simulation=True)


# ---------------------------------------------------------------------- mandates

def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row(row):
    if not row:
        return None
    mid, created, pots_json, status = row
    return dict(id=mid, created_at=created, status=status, pots=json.loads(pots_json))


def current_mandate(con, customer_id):
    try:
        row = con.execute("""SELECT id, created_at, pots_json, status FROM sorter_mandates
                             WHERE customer_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1""", (customer_id,)).fetchone()
    except sqlite3.OperationalError:  # table not created yet
        return None
    return _row(row)


def approve(con, customer_id, twin, pot_ids):
    """Store a mandate for the approved pot ids. Amounts come from the server's proposal, never from the client."""
    prop = proposal(twin)
    if not prop["available"]:
        raise NoPlan(prop["message"])
    movable = {p["id"]: p for p in prop["pots"] if p["approvable"]}
    ids = list(dict.fromkeys(pot_ids))
    unknown = [i for i in ids if i not in movable]
    if unknown:
        raise UnknownPots(unknown)
    chosen = [dict(id=p["id"], label=p["label"], amount=p["amount"]) for p in prop["pots"] if p["id"] in ids]
    ensure_schema(con)
    con.execute("UPDATE sorter_mandates SET status = 'superseded' WHERE customer_id = ? AND status = 'active'", (customer_id,))
    cur = con.execute("INSERT INTO sorter_mandates (customer_id, created_at, pots_json, status) VALUES (?, ?, ?, 'active')",
                      (customer_id, _now(), json.dumps(chosen)))
    con.commit()
    mandate = dict(id=cur.lastrowid, created_at=None, status="active", pots=chosen)
    mandate = current_mandate(con, customer_id) or mandate
    return dict(mandate=mandate, message=_will_move(twin, chosen), simulation=True)


def _will_move(twin, pots):
    _, when = _when(twin)
    moves = _moves(pots)
    text = (f"{when} Kate will move " + _join(moves) + "." if moves else
            f"{when} there's nothing to move: the approved pots are empty in this month's plan.")
    return f"{text} {SIMULATION}"


def preview(twin, mandate):
    """What an active mandate does on the next payday, with amounts recomputed from today's plan."""
    if not mandate:
        return None
    ids = {p["id"] for p in mandate["pots"]}
    prop = proposal(twin)
    pots = [dict(id=p["id"], label=p["label"], amount=p["amount"]) for p in prop["pots"] if p["id"] in ids and p["approvable"]]
    return dict(pots=pots, message=_will_move(twin, pots))


def revoke(con, customer_id):
    ensure_schema(con)
    n = con.execute("UPDATE sorter_mandates SET status = 'revoked' WHERE customer_id = ? AND status = 'active'",
                    (customer_id,)).rowcount
    con.commit()
    return dict(revoked=n, mandate=None, simulation=True,
                message="Stopped: Kate won't sort your payday any more." if n else "There was no payday sorter to stop.")
