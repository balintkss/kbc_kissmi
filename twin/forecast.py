"""Money foresight: safe-to-spend until payday and an early overdraft warning (warn BEFORE the problem).

forecast(con, customer_id, twin) projects the balance of the customer's CURRENT account day by day from
AS_OF (2026-09-30) until the day after the next payday, or for 35 days when there is no fixed payday.

What goes into the projection (all SQL scoped with `customer_id = ?`):
  * start      today's current-account balance (accounts.type = 'current');
  * bills      twin["recurring"] placed on their next_date and repeated monthly / quarterly / yearly inside the
               horizon. For a self-employed twin the next observed social-contribution payment is added when the
               engine's recurring list misses it (twin/selfemployed.py);
  * income     plan["income"] on plan["payday"]; plan["planned_savings"] leaves the day after payday.
               Without a fixed payday (irregular self-employed income, students) the horizon is 35 days and we
               assume the plan's income, which for irregular income is a QUIET month (its 25th-percentile month),
               trickles in evenly every day, minus planned savings. Invoice timing can't be predicted; this is the
               payday plan's own quiet-month assumption, so a good month only makes the picture better;
  * everyday   the typical daily discretionary spend: last 90 days of groceries / dining / shopping / leisure /
               cash / travel on the current account, internal transfers and anything already counted as a
               recurring bill (the gym) excluded, divided by 90;
  * essentials small day-to-day costs (pharmacy, doctor, parking, public transport, pet food, kids) the same way,
               plus the plan's fuel / charging estimate per day.

The twin must be the feedback-applied one (api.main.load_twin): a rejected car drops its fuel from the plan and
so from the projection; a rejected saves_monthly stops the planned savings transfer.

safe_to_spend_per_day is the largest steady everyday spend that keeps the projected balance at or above FLOOR
(EUR 50) on every day until payday (for the payday itself: before the salary lands). warning is True when the
projected balance dips below zero anywhere in the horizon.
"""
import calendar
import math
from collections import defaultdict
from datetime import date, timedelta

from twin import selfemployed
from twin.engine import AS_OF, DISCRETIONARY
from twin.recommender import _nice_date

TODAY = AS_OF.date()
FLOOR = 50
NO_PAYDAY_DAYS = 35
WINDOW_DAYS = 90
DAYS_PER_MONTH = 30.4
NO_FIXED_PAYDAY = {"irregular", "student"}
ESSENTIAL_SUBS = ("pharmacy", "doctor", "parking", "public_transport", "pet_food", "kids_shopping", "baby", "school")
CAR_ENERGY = {"fuel", "charging"}
STEP_MONTHS = {"monthly": 1, "quarterly": 3, "yearly": 12}
BIG_BILL = 100  # a bill this size (or rent / mortgage / social contributions) is named as the cause
SAYS = {"rent": "your rent", "mortgage": "your mortgage payment", "social_contributions": "your social contributions"}


def _iso(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _eur(x):
    v = round(x)
    return f"−€{-v:,}" if v < 0 else f"€{v:,}"


def fixed_payday(twin):
    """The next payday as a date, or None when income has no fixed day (irregular, student) or there is no plan."""
    plan = (twin or {}).get("plan") or {}
    if plan.get("income_kind") in NO_FIXED_PAYDAY:
        return None
    d = _iso(plan.get("payday"))
    return d if d and d > TODAY else None


def bill_events(recurring, start, end):
    """Every recurring bill due in (start, end]: dict(date, amount, name, subcategory), date as a `date`."""
    out = []
    for r in recurring or []:
        step, d, amount = STEP_MONTHS.get(r.get("frequency")), _iso(r.get("next_date")), r.get("amount")
        if not step or not d or not isinstance(amount, (int, float)) or amount <= 0:
            continue
        while d <= start:
            d = _add_months(d, step)
        while d <= end:
            out.append(dict(date=d, amount=float(amount), name=r.get("name"), subcategory=r.get("subcategory")))
            d = _add_months(d, step)
    return sorted(out, key=lambda b: (b["date"], -b["amount"]))


def project(start, bills, end, *, as_of=TODAY, daily_discretionary=0.0, daily_essentials=0.0, daily_income=0.0,
            payday=None, income=0.0, savings=0.0, floor=FLOOR):
    """Pure day-by-day projection (no database). Returns dict(series, lowest, safe_to_spend_per_day).

    End-of-day balance = previous - bills - essentials - discretionary + daily income; income lands on `payday`,
    `savings` leaves the day after. Safe-to-spend uses the same projection WITHOUT discretionary spending and
    finds the largest steady daily spend that keeps every day up to payday (before its income) at >= floor."""
    due = defaultdict(float)
    for b in bills:
        due[b["date"]] += b["amount"]
    budget_end = payday if payday and payday <= end else end
    savings_day = payday + timedelta(days=1) if payday else None
    bal = base = float(start)
    series = [dict(date=as_of.isoformat(), balance=round(bal, 2))]
    safe, d, n = None, as_of, 0
    while d < end:
        d, n = d + timedelta(days=1), n + 1
        fixed = due.get(d, 0.0) + daily_essentials - daily_income + (savings if d == savings_day else 0.0)
        bal -= fixed + daily_discretionary
        base -= fixed
        if d <= budget_end:
            room = (base - floor) / n
            safe = room if safe is None else min(safe, room)
        if d == payday:
            bal += income
            base += income
        series.append(dict(date=d.isoformat(), balance=round(bal, 2)))
    low = min(series, key=lambda p: p["balance"])  # the earliest day with the lowest balance
    low_day = _iso(low["date"])
    window = [b for b in bills if low_day - timedelta(days=3) <= b["date"] <= low_day]
    top = max(window, key=lambda b: b["amount"], default=None)
    cause = dict(name=top["name"], amount=round(top["amount"], 2), date=top["date"].isoformat(),
                 subcategory=top["subcategory"]) if top else None
    first = next((q["date"] for q in series if q["balance"] < 0), None)
    return dict(series=series, lowest=dict(date=low["date"], balance=low["balance"], cause=cause,
                                           days_ahead=(low_day - as_of).days),
                first_below_zero=first, safe_to_spend_per_day=max(0, math.floor(safe)) if safe is not None else 0)


# ---------------------------------------------------------------------- inputs from the database

def _balances(con, customer_id):
    rows = con.execute("SELECT type, COALESCE(SUM(balance), 0), COUNT(*) FROM accounts WHERE customer_id = ? GROUP BY type",
                       (customer_id,)).fetchall()
    return {t: (float(b), int(n)) for t, b, n in rows}


def daily_spend(con, customer_id, recurring):
    """(discretionary per day, small essentials per day) over the last 90 days on this customer's current account."""
    cats, subs = sorted(DISCRETIONARY), ESSENTIAL_SUBS
    rows = con.execute(f"""SELECT t.category, t.subcategory, t.counterparty, t.amount
                           FROM transactions t JOIN accounts a ON a.account_id = t.account_id
                           WHERE t.customer_id = ? AND a.customer_id = ? AND a.type = 'current'
                             AND t.booked_at > ? AND t.booked_at <= ? AND t.amount < 0
                             AND COALESCE(t.channel, '') != 'internal_transfer'
                             AND (t.category IN ({','.join('?' * len(cats))}) OR t.subcategory IN ({','.join('?' * len(subs))}))""",
                       (customer_id, customer_id, (TODAY - timedelta(days=WINDOW_DAYS)).isoformat(), TODAY.isoformat(),
                        *cats, *subs)).fetchall()
    billed = {(r.get("name"), r.get("subcategory")) for r in recurring or []}
    disc = ess = 0.0
    for category, sub, counterparty, amount in rows:
        if (counterparty, sub) in billed:
            continue  # already a recurring bill (e.g. the gym): don't count it twice
        if category in DISCRETIONARY:
            disc -= amount
        else:
            ess -= amount
    return disc / WINDOW_DAYS, ess / WINDOW_DAYS


# ---------------------------------------------------------------------- the forecast

def forecast(con, customer_id, twin):
    twin = twin or {}
    plan = twin.get("plan") or {}
    recurring = twin.get("recurring") or []
    balances = _balances(con, customer_id)
    start, n_current = balances.get("current", (0.0, 0))
    savings_balance = balances.get("savings", (0.0, 0))[0]
    payday = fixed_payday(twin)
    end = payday + timedelta(days=1) if payday else TODAY + timedelta(days=NO_PAYDAY_DAYS)

    bills = bill_events(recurring, TODAY, end)
    if selfemployed.is_self_employed(twin) and not any(r.get("subcategory") == "social_contributions" for r in recurring):
        nxt = selfemployed.next_social_payment(con, customer_id, twin)
        if nxt and TODAY < _iso(nxt["date"]) <= end:
            bills = sorted(bills + [dict(date=_iso(nxt["date"]), amount=nxt["amount"], name=nxt["name"],
                                         subcategory="social_contributions")], key=lambda b: (b["date"], -b["amount"]))

    disc, ess = daily_spend(con, customer_id, recurring)
    energy = sum(v.get("amount") or 0 for v in plan.get("variable_essentials") or [] if v.get("name") in CAR_ENERGY)
    ess += energy / DAYS_PER_MONTH
    income, planned_savings = float(plan.get("income") or 0), float(plan.get("planned_savings") or 0)
    if payday:
        daily_income, assumption = 0.0, "income on payday"
        kw = dict(payday=payday, income=income, savings=planned_savings)
    elif plan:
        daily_income = (income - planned_savings) / DAYS_PER_MONTH
        assumption = ("a quiet month's income, spread evenly" if plan.get("income_kind") == "irregular"
                      else "the plan's monthly income, spread evenly")
        kw = {}
    else:
        daily_income, assumption, kw = 0.0, "no income detected", {}

    p = project(start, bills, end, daily_discretionary=disc, daily_essentials=ess, daily_income=daily_income, **kw)
    low, safe = p["lowest"], p["safe_to_spend_per_day"]
    warning = n_current > 0 and low["balance"] < 0
    top_up = int(math.ceil((FLOOR - low["balance"]) / 10) * 10) if warning else 0
    from_savings = warning and savings_balance >= top_up
    return dict(
        as_of=TODAY.isoformat(), horizon_end=end.isoformat(), payday=payday.isoformat() if payday else None,
        income_assumption=assumption, start_balance=round(start, 2), series=p["series"], lowest=low,
        safe_to_spend_per_day=safe, floor=FLOOR, typical_daily_spend=round(disc, 2), daily_essentials=round(ess, 2),
        warning=warning, top_up=top_up or None, top_up_from_savings=bool(from_savings),
        bills=[dict(b, date=b["date"].isoformat(), amount=round(b["amount"], 2)) for b in bills],
        adjusted_for_feedback=plan.get("adjusted_for_feedback") or [],
        first_below_zero=p["first_below_zero"],
        message=_message(n_current, low, p["first_below_zero"], safe, disc, payday, warning, top_up, from_savings,
                         plan.get("income_kind") == "irregular"),
    )


def _message(n_current, low, first_neg, safe, typical, payday, warning, top_up, from_savings, quiet):
    if not n_current:
        return "We don't see a current account to look ahead on."
    span = "until payday" if payday else f"for the next {NO_PAYDAY_DAYS} days"
    until = f"until payday on {_nice_date(payday)}" if payday else span
    basis = " (planned on a quiet month)" if quiet else ""
    if not warning:
        return (f"You're on track{basis}: your lowest point is {_eur(low['balance'])} on {_nice_date(low['date'])}. "
                f"Safe to spend: €{safe}/day {until}.")
    cause, after = low.get("cause"), ""
    if cause and (cause.get("subcategory") in SAYS or cause["amount"] >= BIG_BILL):
        after = " after " + SAYS.get(cause.get("subcategory"), f"{cause['name']} (€{cause['amount']:,.0f})")
    elif payday and low["date"] == (payday - timedelta(days=1)).isoformat():
        after = ", the day before payday"
    if first_neg == TODAY.isoformat() and low["date"] != first_neg:
        head = (f"Heads-up{basis}: your balance is already below zero and would reach {_eur(low['balance'])} "
                f"on {_nice_date(low['date'])}{after}.")
    elif first_neg == TODAY.isoformat():
        head = f"Heads-up{basis}: your balance is below zero today ({_eur(low['balance'])})."
    elif first_neg and first_neg != low["date"]:
        head = (f"Heads-up{basis}: you'd go below zero on {_nice_date(first_neg)} and reach {_eur(low['balance'])} "
                f"on {_nice_date(low['date'])}{after}.")
    else:
        head = f"Heads-up{basis}: on {_nice_date(low['date'])} you'd dip to {_eur(low['balance'])}{after}."
    fix = f"Move €{top_up:,} from savings" if from_savings else "We can move a bill to after payday or spread it, no fees"
    if safe > 0:
        return f"{head} {fix}, or keep everyday spending under €{safe}/day {until} (you usually spend ≈ €{typical:.0f})."
    return (f"{head} Your bills {span} already use up your balance. {fix}"
            + (f" to keep spending as usual (≈ €{typical:.0f}/day)." if from_savings else "."))


# ---------------------------------------------------------------------- moments

def foresight_moments(con, customer_id, twin, fc=None, env=None):
    """Prebuilt moments for twin.recommender.moments(twin, extra=...): an overdraft warning and a self-employed
    reserve envelope. Both are service, never sales, so money stress never holds them back."""
    fc = forecast(con, customer_id, twin) if fc is None else fc
    env = selfemployed.envelope(con, customer_id, twin) if env is None else env
    out = []
    if fc.get("warning"):
        out.append(dict(kind="overdraft_warning", priority=94, title="Heads-up: your balance may dip below zero",
                        body=fc["message"], topic=None, sales=False))
    if env.get("applicable"):
        out.append(dict(kind="self_employed_reserve", priority=88, title="Your tax & social-contribution envelope",
                        body=env["message"], topic=None, sales=False))
    return out
