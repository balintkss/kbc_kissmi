"""Customer corrections on top of a precomputed twin ("That's right" / "That's not me").

Twins are built overnight into twin_profile; corrections arrive any time through
POST /api/me/facts/{fact}/feedback. apply_feedback() lays those corrections over the
stored twin at read time, so a correction takes effect immediately without rebuilding:

  * every corrected fact is marked rejected_by_customer / confirmed_by_customer
    (+ customer_note); the recommender, moments and Kate already ignore rejected facts;
  * the payday plan drops what a rejected fact put into it, and its totals are
    recomputed with the engine's formulas (twin/engine.py Twin.plan):
        has_car       -> the "car upkeep" reserve and the estimated fuel / charging cost
        pet           -> the "<dog|cat> care" reserve
        saves_monthly -> planned_savings becomes 0

Bills (plan["bills"], bills_until_next_payday and the "yearly bills" reserve) are left
alone on purpose: they come from observed recurring transactions, not from inferred
facts, so a rejected fact never removes a bill that is actually being paid.
"""
import copy

WEEKS_PER_MONTH = 4.3  # same divisor as the engine's free_per_week
CAR_ENERGY = {"fuel", "charging"}  # engine: "fuel" for a combustion car, "charging" otherwise


def apply_feedback(twin: dict, rows: list[tuple[str, int, str | None]]) -> dict:
    """Return a NEW twin with the customer's corrections applied; the input is never mutated.

    rows are (fact, correct, note) ordered oldest -> newest, so the last row per fact wins.
    Feedback on a fact the twin does not have is ignored. The plan gets
    plan["adjusted_for_feedback"] = [fact keys] only when a rejection actually changed it.
    Applying the rows to an already-adjusted twin cannot restore what was dropped: always
    start from the precomputed twin.
    """
    twin = copy.deepcopy(twin)
    facts = twin.get("facts") or {}
    for fact, correct, note in rows:
        if fact in facts:
            facts[fact]["rejected_by_customer"] = not correct
            facts[fact]["confirmed_by_customer"] = bool(correct)
            if note:
                facts[fact]["customer_note"] = note
    if isinstance(twin.get("plan"), dict):
        _adjust_plan(twin, twin["plan"], facts)
    return twin


def _rejected(facts, key):
    f = facts.get(key)
    return isinstance(f, dict) and bool(f.get("rejected_by_customer"))


def _reserve_labels(key, fact):
    """The reserve for_ label(s) the engine gives to a fact's reserve."""
    if key == "has_car":
        return {"car upkeep"}
    value = fact.get("value")
    return {f"{value} care"} if value else {"dog care", "cat care"}


def _adjust_plan(twin, plan, facts):
    reserves = list(plan.get("reserves") or [])
    variable = list(plan.get("variable_essentials") or [])
    freed, adjusted = 0, []

    for key in ("has_car", "pet", "saves_monthly"):
        if not _rejected(facts, key):
            continue
        changed = False
        if key in ("has_car", "pet"):
            labels = _reserve_labels(key, facts[key])
            dropped = [r for r in reserves if r.get("for_") in labels]
            reserves = [r for r in reserves if r.get("for_") not in labels]
            freed += sum(r.get("monthly") or 0 for r in dropped)
            changed = bool(dropped)
        if key == "has_car":
            dropped = [v for v in variable if v.get("name") in CAR_ENERGY]
            variable = [v for v in variable if v.get("name") not in CAR_ENERGY]
            freed += sum(v.get("amount") or 0 for v in dropped)
            changed = changed or bool(dropped)
        if key == "saves_monthly" and plan.get("planned_savings"):
            freed += plan["planned_savings"]
            plan["planned_savings"] = 0
            changed = True
        if changed:
            adjusted.append(key)

    if not adjusted:
        return
    if "reserves" in plan:
        plan["reserves"] = reserves
        reserve_total = sum(r.get("monthly") or 0 for r in reserves)
        plan["reserve_total"] = round(reserve_total)
    else:
        reserve_total = plan.get("reserve_total") or 0
    if "variable_essentials" in plan:
        plan["variable_essentials"] = variable

    bills = _monthly_bills(twin, plan)
    if plan.get("income") is not None and bills is not None:
        # Engine: free = income - bills - reserve_total - savings, then minus variable essentials.
        free = plan["income"] - bills - reserve_total - (plan.get("planned_savings") or 0)
        free -= sum(v.get("amount") or 0 for v in variable)
    elif plan.get("free_to_spend") is not None:
        free = plan["free_to_spend"] + freed  # too little to recompute from: shift by what was freed
    else:
        free = None
    if free is not None:
        plan["free_to_spend"] = round(free)
        plan["free_per_week"] = round(free / WEEKS_PER_MONTH)
    plan["adjusted_for_feedback"] = adjusted


def _monthly_bills(twin, plan):
    """Engine formula: monthly bills + the monthly share of quarterly bills (unrounded)."""
    recurring = twin.get("recurring")
    if isinstance(recurring, list):
        return (sum(r.get("amount") or 0 for r in recurring if r.get("frequency") == "monthly")
                + sum(r.get("monthly_equivalent") or 0 for r in recurring if r.get("frequency") == "quarterly"))
    return plan.get("bills_until_next_payday")
