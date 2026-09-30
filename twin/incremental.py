"""Daily update of the digital twins from each day's new transactions (part 2 of the pipeline).

twin/engine.py builds a twin from a year of history (part 1). This module keeps every twin current day by day
without rebuilding every customer every night:

  Tier 0  streaming, per transaction: on_transaction(state, tx) -> (state, events). A pure function, well under a
          millisecond. A salary landing -> the payday-plan push; every current-account booking -> the balance
          forecast is re-projected to payday (overdraft warning when it would dip below zero); a large unusual
          debit -> a "spread it?" service message. It never rebuilds the twin.
  Tier 1  nightly, only customers who had transactions that day (nightly()):
          (a) balance-only day: only subcategories no inference rule reads (groceries, dining, shopping, cash,
              doctor, pharmacy, bonus, refunds, savings-account moves) -> refresh_money(): financial_buffer,
              money_stress and the payday plan, recomputed with the engine's own code on the last 90 days;
          (b) signal-bearing day: salary, rent / mortgage, fuel / EV, insurance, child benefit, moving / notary,
              pet, invoices, subscriptions, any debit that can be a recurring bill, or a product opened that day
              -> rebuild(): Twin.build() on the customer's history up to that day.
  Tier 2  calendar, customers whose twin changes only because a day passed (also nightly()):
          - a current-account transaction left the 90-day money window -> refresh_money();
          - a known expiry date is reached (calendar_expiry(): a bill or subscription that stopped, rent / mortgage
            / pension recency, the 200-day "new car" flag, the fuel average, the 1st of the month) -> rebuild().

Exactness contract (`python -m twin.incremental --verify daily`, tests/test_incremental.py): after replaying days
D+1..D+k on twins built as of D, every twin equals Twin.build() as of D+k: same JSON for facts (every field),
recurring, plan and the profile fields. The one intended difference is `as_of`: it is the last day the twin was
recomputed, and a twin that did not change keeps its older stamp.

Customer corrections (twin_feedback) and memories are overlays applied on read (api.main.load_twin); persist()
writes only twin_profile, twin_facts and twin_state, so the update can never overwrite them. Tier 0 expects the
read-time twin (corrections applied) in its state.

Every night is a pure function of (yesterday's twins, the ledger, the date): re-running a night gives the same
twins (idempotent), and a missed night is caught up by passing prev_day (every window and expiry uses ranges).

Usage (the database is opened read-only):
  python -m twin.incremental --db data/kbc_twin.db --start 2026-09-23 --days 7 --workers 8 --verify daily
"""
import argparse
import json
import math
import multiprocessing as mp
import platform
import sqlite3
import statistics
import time
from dataclasses import dataclass, replace
from datetime import timedelta

import numpy as np
import pandas as pd

from twin.engine import AS_OF, DB, DISCRETIONARY, VARIABLE_SUBS, WINDOW_START, Twin, _d
from twin.forecast import ESSENTIAL_SUBS, NO_FIXED_PAYDAY, NO_PAYDAY_DAYS, bill_events, project
from twin.recommender import _nice_date

DAY = pd.Timedelta(days=1)
MONEY_WINDOW = 90     # days: Twin.infer_money and the plan's groceries look back this far
HISTORY_DAYS = 396    # a rebuild reads ~13 months (the synthetic data has 12, so this is all of it)
MONEY_FACTS = ("saves_monthly", "financial_buffer", "money_stress")  # infer_money adds them last, in this order

# Every subcategory an inference rule in twin/engine.py reads (Twin.sub(...) and the train-pass filter).
RULE_SUBS = frozenset({
    "salary", "student_job", "pension", "benefit", "invoice", "family_transfer",                 # infer_income
    "fuel", "ev_charging", "maintenance", "car", "road_tax", "registration_tax", "inspection",
    "car_purchase", "car_loan", "parking",                                                         # infer_car
    "pet_food", "vet", "adoption",                                                                 # infer_pet
    "child_benefit", "baby", "birth_allowance", "childcare", "hospital",                          # infer_family
    "rent", "mortgage", "property_tax", "energy", "moving", "notary", "furniture_diy",             # infer_housing
    "public_transport", "gym", "streaming", "flights",                                             # infer_lifestyle
    "transfer_to_savings",                                                                          # saves_monthly
})
SALARY_SUBS = ("salary", "pension", "benefit")
BIG_DEBIT_MIN = 500          # EUR: never call a smaller debit "large"
BIG_DEBIT_FACTOR = 2.0       # ... and only when it is twice the customer's 99th-percentile debit of the last 90 days
KBC_CUSTOMERS = 2_300_000


# ---------------------------------------------------------------------- classification

def tx_is_signal(acc_type, amount, category, subcategory, channel):
    """True when a transaction can change more than the balance-dependent parts of the twin.

    Signal: a subcategory an inference rule reads, or a current-account debit that recurring() could count as a
    (monthly, quarterly or yearly) bill. Everything else only moves balances and the 90-day money window."""
    if acc_type != "current":
        return False  # savings-account side of a transfer: only the savings balance moves
    if subcategory in RULE_SUBS:
        return True
    return (amount < 0 and channel != "internal_transfer" and (category not in DISCRETIONARY or subcategory == "gym")
            and subcategory not in VARIABLE_SUBS)


def signal_mask(tx):
    """Vectorised tx_is_signal over a transactions DataFrame (engine.load columns)."""
    cur = (tx.acc_type == "current").to_numpy()
    rule = tx.subcategory.isin(RULE_SUBS).to_numpy()
    bill = ((tx.amount < 0) & (tx.channel != "internal_transfer")
            & (~tx.category.isin(DISCRETIONARY) | (tx.subcategory == "gym")) & ~tx.subcategory.isin(VARIABLE_SUBS)).to_numpy()
    return cur & (rule | bill)


def classify_day(txs, product_change=False):
    """'signal' or 'balance_only' for one customer's transactions of a day (iterable of rows with engine columns)."""
    if product_change or any(tx_is_signal(t.acc_type, t.amount, t.category, t.subcategory, t.channel) for t in txs):
        return "signal"
    return "balance_only"


# ---------------------------------------------------------------------- the ledger (read-only, sliceable by day)

TX_SQL = """SELECT t.tx_id, t.customer_id, t.booked_at, t.amount, t.counterparty, t.description, t.category,
                   t.subcategory, t.channel, t.balance_after, a.type AS acc_type
            FROM transactions t JOIN accounts a USING(account_id) {where} ORDER BY t.customer_id, t.booked_at, t.tx_id"""


class Ledger:
    """What the bank knows about a set of customers, readable as of any day (same columns as engine.load)."""

    def __init__(self, tx, customers, products, accounts):
        self.tx = tx.reset_index(drop=True)
        self.empty = self.tx.iloc[0:0]
        self.customers = {int(c.customer_id): c for c in customers.itertuples()}
        self._dates = self.tx.booked_at.to_numpy()
        self._cid = self.tx.customer_id.to_numpy()
        self._current = (self.tx.acc_type == "current").to_numpy()
        self._by, self._bal = {}, {}
        for cid, g in self.tx.groupby("customer_id", sort=False):
            self._by[int(cid)] = (g, g.booked_at.to_numpy())
            for acc_type, a in g.groupby("acc_type", sort=False):
                first = a.iloc[0]
                self._bal[(int(cid), acc_type)] = (a.booked_at.to_numpy(), a.balance_after.to_numpy(),
                                                   first.balance_after - first.amount)
        self._accounts = {int(cid): list(zip(g.type, g.balance)) for cid, g in accounts.groupby("customer_id")}
        self._products = {int(cid): list(zip(g.product_code, g.started_at)) for cid, g in products.groupby("customer_id")}
        self._prod_starts = products.started_at.to_numpy(), products.customer_id.to_numpy()

    @classmethod
    def from_db(cls, con, lo=None, hi=None):
        """Load customers lo..hi (all when None) from a SQLite connection; nothing is written."""
        rng = lo is not None
        args = (lo, hi) if rng else ()
        tx = pd.read_sql(TX_SQL.format(where="WHERE t.customer_id BETWEEN ? AND ?" if rng else ""), con,
                         params=args, parse_dates=["booked_at"])
        where = "WHERE customer_id BETWEEN ? AND ?" if rng else ""
        cust = pd.read_sql(f"SELECT * FROM customers {where}", con, params=args)
        prods = pd.read_sql(f"SELECT customer_id, product_code, started_at FROM products {where}", con, params=args,
                            parse_dates=["started_at"])
        accs = pd.read_sql(f"SELECT customer_id, type, balance FROM accounts {where}", con, params=args)
        return cls(tx, cust, prods, accs)

    @property
    def customer_ids(self):
        return sorted(self.customers)

    def history(self, cid, as_of, days=None):
        """The customer's transactions booked on or before as_of (and on or after as_of - days)."""
        if cid not in self._by:
            return self.empty
        df, dates = self._by[cid]
        as_of = pd.Timestamp(as_of)
        hi = np.searchsorted(dates, as_of.to_datetime64(), "right")
        lo = np.searchsorted(dates, (as_of - pd.Timedelta(days=days)).to_datetime64(), "left") if days else 0
        return df.iloc[lo:hi]

    def balances(self, cid, as_of):
        """End-of-day balance per account type, as of that day (engine: dict(zip(type, balance)))."""
        as_of = pd.Timestamp(as_of).to_datetime64()
        out = {}
        for acc_type, final in self._accounts.get(cid, []):
            hist = self._bal.get((cid, acc_type))
            if hist is None:
                out[acc_type] = final  # no transactions at all: the balance never moved
                continue
            dates, after, opening = hist
            i = np.searchsorted(dates, as_of, "right")
            out[acc_type] = after[i - 1] if i else opening
        return out

    def products(self, cid, as_of):
        as_of = pd.Timestamp(as_of)
        return [code for code, started in self._products.get(cid, []) if pd.isna(started) or started <= as_of]

    def between(self, prev, day):
        """All transactions booked after prev and on or before day (one night's batch)."""
        m = (self._dates > pd.Timestamp(prev).to_datetime64()) & (self._dates <= pd.Timestamp(day).to_datetime64())
        return self.tx[m]

    def product_changes(self, prev, day):
        starts, cids = self._prod_starts
        m = (starts > pd.Timestamp(prev).to_datetime64()) & (starts <= pd.Timestamp(day).to_datetime64())
        return {int(c) for c in cids[m]}

    def left_money_window(self, prev, day):
        """Customers with a current-account transaction that was inside the 90-day window on prev and is not on day."""
        lo = (pd.Timestamp(prev) - pd.Timedelta(days=MONEY_WINDOW)).to_datetime64()
        hi = (pd.Timestamp(day) - pd.Timedelta(days=MONEY_WINDOW)).to_datetime64()
        m = self._current & (self._dates >= lo) & (self._dates < hi)
        return {int(c) for c in np.unique(self._cid[m])}


# ---------------------------------------------------------------------- Tier 1: the two update paths

def rebuild(ledger, cid, day):
    """Signal-bearing day (or a calendar expiry): the engine's full Twin.build() as of that day.
    Returns (twin, history) so the caller can compute calendar_expiry() without reading again."""
    day = pd.Timestamp(day)
    tx = ledger.history(cid, day, HISTORY_DAYS)
    twin = Twin(ledger.customers[cid], tx, ledger.products(cid, day), ledger.balances(cid, day), as_of=day).build()
    return twin, tx


def refresh_money(twin, ledger, cid, day):
    """Balance-only day (or the 90-day window moved): recompute what depends on balances and the last 90 days.

    Uses the engine's own infer_money() and plan() on a 90-day slice, so the result is exactly what a full rebuild
    gives: financial_buffer and money_stress are recomputed, saves_monthly is kept (it reads the whole history and
    only a savings transfer, a signal, changes it), and the plan is recomputed (groceries, money facts). Every other
    fact, the recurring bills and the product list are carried over unchanged. Returns a new dict."""
    day = pd.Timestamp(day)
    t = Twin(ledger.customers[cid], ledger.history(cid, day, MONEY_WINDOW), twin["kbc_products"],
             ledger.balances(cid, day), as_of=day)
    facts = {k: v for k, v in twin["facts"].items() if k not in MONEY_FACTS}
    t.facts = dict(facts)
    t.infer_money()
    if "saves_monthly" in twin["facts"]:
        facts["saves_monthly"] = twin["facts"]["saves_monthly"]
    facts["financial_buffer"] = t.facts["financial_buffer"]
    if "money_stress" in t.facts:
        facts["money_stress"] = t.facts["money_stress"]
    t.facts = facts
    return dict(twin, facts=facts, plan=t.plan(twin["recurring"]), as_of=_d(day))


# ---------------------------------------------------------------------- Tier 2: known expiry dates

def _bill_candidates(cur):
    """engine.Twin.recurring(): the debits that can form a recurring bill (same filter)."""
    return cur[(cur.amount < 0) & (cur.channel != "internal_transfer") & (~cur.category.isin(DISCRETIONARY) | (cur.subcategory == "gym"))
               & ~cur.subcategory.isin(VARIABLE_SUBS)]


def calendar_expiries(twin, tx, day):
    """{reason: first day after `day` on which Twin.build() changes although no transaction arrives}.

    tx is the history the twin was built from. Every as_of-dependent rule of twin/engine.py is listed here; the
    90-day money window is handled separately (Ledger.left_money_window -> refresh_money)."""
    day = pd.Timestamp(day)
    cur = tx[tx.acc_type == "current"]
    facts = twin["facts"]
    found = {}

    def put(reason, when):
        when = pd.Timestamp(when)
        if when > day and (reason not in found or when < found[reason]):
            found[reason] = when

    put("new_year", pd.Timestamp(day.year + 1, 1, 1))  # age
    if twin.get("plan") or any(r["frequency"] == "monthly" for r in twin["recurring"]):
        put("month_start", day + pd.offsets.MonthBegin(1))  # every monthly next_date and the payday move a month
    bills = _bill_candidates(cur)
    for r in twin["recurring"]:  # recurring(): a bill unpaid for 70 days drops out
        if r["frequency"] in ("monthly", "quarterly"):
            g = bills[(bills.counterparty == r["name"]) & (bills.subcategory == r["subcategory"])]
            if len(g):
                put("bill_stopped", g.booked_at.max() + pd.Timedelta(days=71))
    home = bills[bills.subcategory.isin(("rent", "mortgage"))]
    if len(home):  # recurring(): the current home is listed from a single payment for 40 days
        put("housing", home.booked_at.iloc[-1] + pd.Timedelta(days=41))
    for sub in ("rent", "mortgage"):  # infer_housing(): rent / mortgage paid less than 45 days ago
        g = cur[cur.subcategory == sub]
        if len(g):
            put("housing", g.booked_at.max() + pd.Timedelta(days=45))
    for sub in ("pension", "benefit"):  # infer_income(): paid < 45 days ago
        g = cur[cur.subcategory == sub]
        if len(g):
            put("income", g.booked_at.max() + pd.Timedelta(days=45))
    subs = facts.get("subscriptions")
    if subs:  # infer_lifestyle(): a subscription counts while paid in the last 45 days
        s = cur[cur.subcategory == "streaming"]
        for name in subs["value"]:
            put("subscription", s[s.counterparty == name].booked_at.max() + pd.Timedelta(days=46))
    car = facts.get("has_car")
    if car:
        purchase = cur[cur.subcategory == "car_purchase"]
        if car.get("bought_recently") and len(purchase):  # _is_recent(purchase, 200)
            put("new_car", purchase.booked_at.min() + pd.Timedelta(days=201))
        energy = cur[cur.subcategory.isin(("fuel", "ev_charging"))]
        first = purchase.booked_at.min() if len(purchase) else energy.booked_at.min()
        if len(energy) and not pd.isna(first):  # infer_car(): fuel / months since first seen, a denominator that grows daily
            d0, total = (day - max(first, WINDOW_START)).days, -energy.amount.sum()
            now = round(total / max(1, d0 / 30.4))
            for k in range(1, 400):
                if round(total / max(1, (d0 + k) / 30.4)) != now:
                    put("fuel_average", day + k * DAY)
                    break
    return found


def calendar_expiry(twin, tx, day):
    """The earliest calendar_expiries() date (None when nothing expires)."""
    found = calendar_expiries(twin, tx, day)
    return min(found.values()) if found else None


# ---------------------------------------------------------------------- the night

def nightly(ledger, twins, expiry, day, prev_day=None, reasons=None):
    """Tier 1 + Tier 2 for the night after `day`. Updates `twins` and `expiry` in place and returns stats.

    twins: {customer_id: twin} as of the previous night; expiry: {customer_id: Timestamp | None} from
    calendar_expiry(). prev_day (default day - 1) is the last night that ran: a missed night is caught up by
    passing it, because every window below is a range. reasons: optional {customer_id: {reason: date}} to keep
    Tier 2 statistics per reason."""
    day = pd.Timestamp(day)
    prev = pd.Timestamp(prev_day) if prev_day is not None else day - DAY
    t0 = time.perf_counter()
    batch = ledger.between(prev, day)
    sig = signal_mask(batch)
    touched = {int(c) for c in pd.unique(batch.customer_id)}
    products = ledger.product_changes(prev, day) & set(ledger.customers)
    signal = {int(c) for c in pd.unique(batch.customer_id[sig])} | products
    balance_only = touched - signal
    left = ledger.left_money_window(prev, day)
    due = {cid for cid, d in expiry.items() if d is not None and d <= day}
    new = set(ledger.customers) - set(twins)
    rebuild_ids = signal | due | new
    money_ids = (balance_only | left) - rebuild_ids
    t_classify = time.perf_counter() - t0

    due_reasons = {}
    t_rebuild = t_money = 0.0
    for cid in sorted(rebuild_ids):
        s = time.perf_counter()
        twin, tx = rebuild(ledger, cid, day)
        found = calendar_expiries(twin, tx, day)
        t_rebuild += time.perf_counter() - s
        if cid in due and cid not in signal and reasons is not None:
            for r, d in (reasons.get(cid) or {}).items():
                if d <= day:
                    due_reasons[r] = due_reasons.get(r, 0) + 1
        twins[cid], expiry[cid] = twin, (min(found.values()) if found else None)
        if reasons is not None:
            reasons[cid] = found
    for cid in sorted(money_ids):
        s = time.perf_counter()
        twins[cid] = refresh_money(twins[cid], ledger, cid, day)
        t_money += time.perf_counter() - s

    calendar_rebuild = due - signal
    return dict(
        day=_d(day), customers=len(ledger.customers), tx=int(len(batch)), touched=len(touched),
        signal=len(signal & touched), product_only=len(products - touched), balance_only=len(balance_only),
        tier1_rebuild=len(signal), tier1_money=len(balance_only - rebuild_ids),
        tier2_rebuild=len(calendar_rebuild), tier2_rebuild_untouched=len(calendar_rebuild - touched),
        tier2_money=len(money_ids - balance_only), due_reasons=due_reasons,
        rebuilds=len(rebuild_ids), money_refreshes=len(money_ids), unchanged=len(set(ledger.customers) - rebuild_ids - money_ids),
        t_classify=t_classify, t_rebuild=t_rebuild, t_money=t_money, t_total=time.perf_counter() - t0)


def initial_build(ledger, day):
    """Part 1 for the replay: every twin as of `day`. Returns (twins, expiry, reasons)."""
    twins, expiry, reasons = {}, {}, {}
    for cid in ledger.customer_ids:
        twin, tx = rebuild(ledger, cid, day)
        found = calendar_expiries(twin, tx, day)
        twins[cid], expiry[cid], reasons[cid] = twin, (min(found.values()) if found else None), found
    return twins, expiry, reasons


# ---------------------------------------------------------------------- equality

def _canon(twin):
    return json.dumps({k: v for k, v in twin.items() if k != "as_of"}, ensure_ascii=False, default=str)


def same_twin(a, b):
    """Strict equality: identical JSON (key order included) for everything except the as_of stamp."""
    return _canon(a) == _canon(b)


def twin_diff(a, b):
    """Which parts differ: 'facts.<key>' per fact, or a top-level key ('recurring', 'plan', ...). [] when equal."""
    out = []
    fa, fb = a.get("facts") or {}, b.get("facts") or {}
    out += [f"facts.{k}" for k in sorted(set(fa) | set(fb)) if fa.get(k) != fb.get(k)]
    if not out and list(fa) != list(fb):
        out.append("facts(order)")
    out += [k for k in sorted((set(a) | set(b)) - {"facts", "as_of"}) if a.get(k) != b.get(k)]
    return out


def core_equal(a, b):
    """Looser check: the same fact keys with the same value and confidence."""
    fa, fb = a.get("facts") or {}, b.get("facts") or {}
    return set(fa) == set(fb) and all(fa[k].get("value") == fb[k].get("value") and fa[k].get("confidence") == fb[k].get("confidence")
                                      for k in fa)


# ---------------------------------------------------------------------- Tier 0: streaming

@dataclass(frozen=True)
class StreamState:
    """What Tier 0 needs per customer, prepared by the nightly job (stream_state) and carried through the day."""
    customer_id: int
    twin: dict                  # the read-time twin: corrections applied (api.main.load_twin)
    balance: float              # current account
    daily_discretionary: float  # twin.forecast.daily_spend: last 90 days of everyday spending / 90
    daily_essentials: float     # small essentials / 90 + the plan's fuel or charging per day
    big_debit: float            # a debit at least this large (and not a known bill) is "large and unusual"
    bills: tuple = ()           # upcoming recurring bills (twin.forecast.bill_events), dropped once paid
    warned: bool = False        # an overdraft warning was already sent for this horizon


def _payday(twin, day):
    plan = twin.get("plan") or {}
    if plan.get("income_kind") in NO_FIXED_PAYDAY or not plan.get("payday"):
        return None
    p = pd.Timestamp(plan["payday"]).date()
    return p if p > day else None


def _horizon(twin, day):
    payday = _payday(twin, day)
    return payday, (payday + timedelta(days=1) if payday else day + timedelta(days=NO_PAYDAY_DAYS))


def stream_state(twin, tx90, balance, day):
    """Build a customer's Tier 0 state for the day after `day` from the twin and its last 90 days of history."""
    day = pd.Timestamp(day).date()
    cur = tx90[(tx90.acc_type == "current") & (tx90.amount < 0) & (tx90.channel != "internal_transfer")]
    billed = {(r.get("name"), r.get("subcategory")) for r in twin.get("recurring") or []}
    spend = cur[cur.category.isin(DISCRETIONARY) | cur.subcategory.isin(ESSENTIAL_SUBS)]
    if len(spend):
        spend = spend[[(cp, s) not in billed for cp, s in zip(spend.counterparty, spend.subcategory)]]
    disc = -spend[spend.category.isin(DISCRETIONARY)].amount.sum() / MONEY_WINDOW
    ess = -spend[~spend.category.isin(DISCRETIONARY)].amount.sum() / MONEY_WINDOW
    plan = twin.get("plan") or {}
    ess += sum(v.get("amount") or 0 for v in plan.get("variable_essentials") or [] if v.get("name") in ("fuel", "charging")) / 30.4
    p99 = float(np.percentile(-cur.amount.to_numpy(), 99)) if len(cur) else 0.0
    _, end = _horizon(twin, day)
    return StreamState(customer_id=int(twin["customer_id"]), twin=twin, balance=float(balance), daily_discretionary=float(disc),
                       daily_essentials=float(ess), big_debit=max(BIG_DEBIT_MIN, BIG_DEBIT_FACTOR * p99),
                       bills=tuple(bill_events(twin.get("recurring"), day, end)))


def _known_bill(twin, tx):
    return any(r.get("name") == tx.counterparty and r.get("subcategory") == tx.subcategory
               and abs(-tx.amount - (r.get("amount") or 0)) <= 0.35 * (r.get("amount") or 0)
               for r in twin.get("recurring") or [])


def payday_push(twin, tx):
    """The payday-plan push, the moment the salary lands (same kind and priority as recommender.moments)."""
    plan = twin.get("plan") or {}
    head = f"€{tx.amount:,.0f} just arrived."
    if plan and plan.get("income_kind") not in NO_FIXED_PAYDAY:
        nxt = _nice_date(plan.get("payday"))
        body = (f"{head} Until your next payday{f' on {nxt}' if nxt else ''}: bills €{plan['bills_until_next_payday']:,}, "
                f"set aside €{plan['reserve_total']}" + (f", save €{plan['planned_savings']}" if plan.get("planned_savings") else "")
                + f" — that leaves €{plan['free_per_week']}/week to spend freely.")
    else:
        body = f"{head} Your plan is up to date."
    return dict(kind="salary_plan", priority=90, title="Your salary is in: here's your plan", body=body, topic=None,
                sales=False, trigger="salary_landed", tx_id=int(tx.tx_id))


def on_transaction(state, tx):
    """Tier 0: react to one booked transaction without rebuilding the twin. Pure: returns (new_state, events).

    tx needs the engine columns (tx_id, booked_at, amount, counterparty, category, subcategory, channel,
    balance_after, acc_type). Events: 'forecast' (every current-account booking), 'overdraft_warning' (first time
    the projection to payday dips below zero), 'salary_plan' (salary / pension / benefit landed) and 'large_debit'.
    None of them is a sales message, and none is a fraud decision (fraud monitoring is a separate workstream)."""
    if tx.acc_type != "current":
        return state, []  # a savings-account booking: the nightly buffer refresh covers it
    events = []
    day = pd.Timestamp(tx.booked_at).date()
    twin = state.twin
    bills = tuple(b for b in state.bills if b["date"] > day
                  and not (b["name"] == tx.counterparty and b["subcategory"] == tx.subcategory))
    if tx.amount > 0 and tx.subcategory in SALARY_SUBS:
        events.append(payday_push(twin, tx))
    if (tx.amount < 0 and tx.channel != "internal_transfer" and -tx.amount >= state.big_debit
            and not _known_bill(twin, tx)):
        events.append(dict(kind="large_debit", priority=85, title="A large payment just left your account",
                           body=f"€{-tx.amount:,.0f} to {tx.counterparty}. We've updated your look-ahead; if it's tight, "
                                f"we can spread a bill or move one to after payday, no fees.",
                           topic=None, sales=False, tx_id=int(tx.tx_id)))
    plan = twin.get("plan") or {}
    payday, end = _horizon(twin, day)
    if payday:
        kw = dict(payday=payday, income=float(plan.get("income") or 0), savings=float(plan.get("planned_savings") or 0))
        daily_income = 0.0
    else:
        kw = {}
        daily_income = (float(plan.get("income") or 0) - float(plan.get("planned_savings") or 0)) / 30.4 if plan else 0.0
    p = project(float(tx.balance_after), [b for b in bills if b["date"] <= end], end, as_of=day,
                daily_discretionary=state.daily_discretionary, daily_essentials=state.daily_essentials,
                daily_income=daily_income, **kw)
    low = p["lowest"]
    events.append(dict(kind="forecast", balance=round(float(tx.balance_after), 2), lowest=low["balance"],
                       lowest_on=low["date"], safe_to_spend_per_day=p["safe_to_spend_per_day"]))
    warn = low["balance"] < 0
    if warn and not state.warned:
        events.append(dict(kind="overdraft_warning", priority=94, title="Heads-up: your balance may dip below zero",
                           body=f"After this payment your balance could reach €{low['balance']:,.0f} on "
                                f"{_nice_date(low['date'])}. We can move a bill to after payday or spread it, no fees.",
                           topic=None, sales=False, tx_id=int(tx.tx_id)))
    return replace(state, balance=float(tx.balance_after), bills=bills, warned=warn), events


# ---------------------------------------------------------------------- persistence (idempotent upserts)

PERSIST_SCHEMA = """
CREATE TABLE IF NOT EXISTS twin_profile (customer_id INTEGER PRIMARY KEY, profile_json TEXT NOT NULL, built_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS twin_facts (customer_id INTEGER, fact TEXT, value TEXT, confidence REAL, since TEXT, summary TEXT, evidence TEXT);
CREATE TABLE IF NOT EXISTS twin_state (customer_id INTEGER PRIMARY KEY, as_of TEXT NOT NULL, refresh_on TEXT);
"""


def persist(con, twins, expiry, built_at):
    """Upsert the changed twins (same rows as `python -m twin.engine`) and their next expiry date.

    Touches only twin_profile, twin_facts and twin_state: twin_feedback (corrections), memories and every other
    table are never written, so the overlays applied on read survive every update. Running it twice with the same
    input leaves the same rows (idempotent)."""
    con.executescript(PERSIST_SCHEMA)
    with con:
        for cid, twin in twins.items():
            con.execute("INSERT OR REPLACE INTO twin_profile VALUES (?,?,?)",
                        (cid, json.dumps(twin, ensure_ascii=False, default=str), built_at))
            con.execute("DELETE FROM twin_facts WHERE customer_id = ?", (cid,))
            con.executemany("INSERT INTO twin_facts VALUES (?,?,?,?,?,?,?)",
                            [(cid, f["key"], json.dumps(f["value"], default=str), f["confidence"], f["since"], f["summary"],
                              json.dumps(f["evidence"])) for f in twin["facts"].values()])
            con.execute("INSERT OR REPLACE INTO twin_state VALUES (?,?,?)", (cid, twin["as_of"], _d(expiry.get(cid))))


# ---------------------------------------------------------------------- replay experiment (one partition)

class Partition:
    """A slice of customers (id range) replayed day by day: the unit a production worker would own."""

    def __init__(self, db, lo, hi, start, verify="final", variants=True):
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        t = time.perf_counter()
        self.ledger = Ledger.from_db(con, lo, hi)
        self.t_load = time.perf_counter() - t
        con.close()
        self.start, self.verify, self.day = pd.Timestamp(start), verify, pd.Timestamp(start)
        t = time.perf_counter()
        self.twins, self.expiry, self.reasons = initial_build(self.ledger, self.start)
        self.t_initial = time.perf_counter() - t
        self.truth_prev = dict(self.twins)
        # comparison variants: what the twins look like with less than all tiers (for the staleness numbers)
        self.variants = ({k: dict(self.twins) for k in ("none", "tier1", "tier1_money", "sweep7")}
                         if variants and verify == "daily" else {})

    def stream_day(self, day):
        """Tier 0 over the day's bookings, states prepared from last night's twins. Returns latencies and events."""
        prev = day - DAY
        t = time.perf_counter()
        states = {cid: stream_state(tw, self.ledger.history(cid, prev, MONEY_WINDOW), self.ledger.balances(cid, prev).get("current", 0.0), prev)
                  for cid, tw in self.twins.items()}
        t_prep = time.perf_counter() - t
        lat, kinds = [], {}
        for tx in self.ledger.between(prev, day).itertuples(index=False):
            s = time.perf_counter_ns()
            states[tx.customer_id], events = on_transaction(states[tx.customer_id], tx)
            lat.append((time.perf_counter_ns() - s) / 1e6)
            for e in events:
                kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
        return dict(latency_ms=lat, events=kinds, t_prep=t_prep, states=len(states))

    def run_day(self, day):
        day = pd.Timestamp(day)
        out = dict(stream=self.stream_day(day))
        out["night"] = nightly(self.ledger, self.twins, self.expiry, day, reasons=self.reasons)
        if self.verify == "daily" or (self.verify == "final" and day == self.final_day):
            out["verify"] = self._verify(day)
        self.day = day
        return out

    def _verify(self, day):
        t = time.perf_counter()
        truth = {cid: rebuild(self.ledger, cid, day)[0] for cid in self.ledger.customer_ids}
        t_truth = time.perf_counter() - t
        res = dict(t_truth=t_truth, strict_mismatch=[], core_mismatch=0, diff_parts={})
        for cid, tw in truth.items():
            if not same_twin(self.twins[cid], tw):
                res["strict_mismatch"].append(cid)
                for part in twin_diff(self.twins[cid], tw):
                    res["diff_parts"][part] = res["diff_parts"].get(part, 0) + 1
            res["core_mismatch"] += not core_equal(self.twins[cid], tw)
        # which twins really changed today (full rebuild today vs yesterday), and why
        changed = {cid for cid in truth if not same_twin(truth[cid], self.truth_prev[cid])}
        res["changed_today"] = len(changed)
        self.truth_prev = truth
        if self.variants:
            res["variants"] = self._advance_variants(day, truth)
        return res

    def _advance_variants(self, day, truth):
        """Advance the comparison variants by one day (rebuilds come from `truth`: same pure function)."""
        led, prev = self.ledger, day - DAY
        batch = led.between(prev, day)
        touched = {int(c) for c in pd.unique(batch.customer_id)}
        signal = {int(c) for c in pd.unique(batch.customer_id[signal_mask(batch)])} | led.product_changes(prev, day)
        left = led.left_money_window(prev, day)
        sweep = {cid for cid in led.customer_ids if cid % 7 == (day - self.start).days % 7}
        out = {}
        for name, tw in self.variants.items():
            if name != "none":
                rebuild_ids = signal | (sweep if name == "sweep7" else set())
                money = (touched - rebuild_ids) | (left - rebuild_ids if name in ("tier1_money", "sweep7") else set())
                for cid in rebuild_ids:
                    tw[cid] = truth[cid]
                for cid in money:
                    tw[cid] = refresh_money(tw[cid], led, cid, day)
            out[name] = sum(not same_twin(tw[cid], truth[cid]) for cid in truth)
        return out


def _worker(conn, db, lo, hi, start, verify, variants, final_day):
    p = Partition(db, lo, hi, start, verify, variants)
    p.final_day = pd.Timestamp(final_day)
    conn.send(dict(t_load=p.t_load, t_initial=p.t_initial, customers=len(p.ledger.customers), tx=len(p.ledger.tx)))
    while True:
        msg = conn.recv()
        if msg is None:
            break
        conn.send(p.run_day(msg))
    conn.close()


def _ranges(db, workers):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    ids = [r[0] for r in con.execute("SELECT customer_id FROM customers ORDER BY customer_id")]
    con.close()
    k = math.ceil(len(ids) / workers)
    return [(ids[i], ids[min(i + k, len(ids)) - 1]) for i in range(0, len(ids), k)]


def replay(db, start, days, workers=1, verify="final", variants=True, log=print):
    """Build every twin as of `start`, then run `days` nights with `workers` partitions. Returns a report dict."""
    start = pd.Timestamp(start)
    final_day = start + days * DAY
    ctx = mp.get_context("spawn")
    procs = []
    for lo, hi in _ranges(db, workers):
        a, b = ctx.Pipe()
        pr = ctx.Process(target=_worker, args=(b, db, lo, hi, _d(start), verify, variants, _d(final_day)), daemon=True)
        pr.start()
        procs.append((pr, a))
    init = [a.recv() for _, a in procs]
    log(f"loaded {sum(i['customers'] for i in init):,} customers / {sum(i['tx'] for i in init):,} transactions "
        f"in {max(i['t_load'] for i in init):.1f} s; initial build as of {_d(start)}: "
        f"{sum(i['t_initial'] for i in init):.1f} CPU-s ({max(i['t_initial'] for i in init):.1f} s wall)")
    report = dict(start=_d(start), days=days, workers=workers, init=init, nights=[])
    for k in range(1, days + 1):
        day = start + k * DAY
        t = time.perf_counter()
        for _, a in procs:
            a.send(day)
        parts = [a.recv() for _, a in procs]
        report["nights"].append(_merge(day, parts, time.perf_counter() - t))
        n = report["nights"][-1]
        log(_night_line(n))
    for pr, a in procs:
        a.send(None)
        pr.join(timeout=10)
    report["summary"] = _summary(report)
    return report


def _merge(day, parts, wall):
    nights = [p["night"] for p in parts]
    agg = {k: sum(n[k] for n in nights) for k in nights[0] if isinstance(nights[0][k], (int, float))}
    agg["due_reasons"] = {}
    for n in nights:
        for r, c in n["due_reasons"].items():
            agg["due_reasons"][r] = agg["due_reasons"].get(r, 0) + c
    agg["day"] = _d(day)
    agg["t_wall_nightly"] = max(n["t_total"] for n in nights)  # partitions run in parallel
    lat = [x for p in parts for x in p["stream"]["latency_ms"]]
    events = {}
    for p in parts:
        for kname, c in p["stream"]["events"].items():
            events[kname] = events.get(kname, 0) + c
    agg["stream"] = dict(events=events, n=len(lat), p50_ms=_pct(lat, 50), p95_ms=_pct(lat, 95), p99_ms=_pct(lat, 99),
                         max_ms=max(lat) if lat else 0, total_s=sum(lat) / 1000,
                         t_prep=sum(p["stream"]["t_prep"] for p in parts), states=sum(p["stream"]["states"] for p in parts))
    if "verify" in parts[0]:
        v = [p["verify"] for p in parts]
        agg["verify"] = dict(strict_mismatch=sorted(c for x in v for c in x["strict_mismatch"]),
                             core_mismatch=sum(x["core_mismatch"] for x in v),
                             changed_today=sum(x["changed_today"] for x in v),
                             diff_parts={}, t_truth=sum(x["t_truth"] for x in v))
        for x in v:
            for part, c in x["diff_parts"].items():
                agg["verify"]["diff_parts"][part] = agg["verify"]["diff_parts"].get(part, 0) + c
        if "variants" in v[0]:
            agg["verify"]["variants"] = {k: sum(x["variants"][k] for x in v) for k in v[0]["variants"]}
    agg["t_round_trip"] = wall
    return agg


def _pct(values, q):
    if not values:
        return 0.0
    return float(np.percentile(values, q))


def _night_line(n):
    s = (f"{n['day']}  tx {n['tx']:>6,}  touched {n['touched']:>5,} ({n['touched'] / n['customers']:.0%})  "
         f"signal {n['signal']:>5,}  balance-only {n['balance_only']:>5,}  products {n['product_only']}  "
         f"t2-money {n['tier2_money']:>5,}  t2-rebuild {n['tier2_rebuild']:>4,}  "
         f"nightly {n['t_total']:.1f} CPU-s / {n['t_wall_nightly']:.1f} s wall  "
         f"tier0 p50 {n['stream']['p50_ms'] * 1000:.0f} µs p95 {n['stream']['p95_ms'] * 1000:.0f} µs")
    if "verify" in n:
        v = n["verify"]
        s += f"  | equal: {n['customers'] - len(v['strict_mismatch']):,}/{n['customers']:,}  changed today {v['changed_today']:,}"
        if "variants" in v:
            s += "  stale if only " + ", ".join(f"{k}={c}" for k, c in v["variants"].items())
    return s


def _summary(report):
    nights = report["nights"]
    n_cust = nights[0]["customers"]
    tot = lambda k: sum(n[k] for n in nights)  # noqa: E731
    reb, mon = tot("rebuilds"), tot("money_refreshes")
    ms_rebuild = 1000 * tot("t_rebuild") / reb if reb else 0
    ms_money = 1000 * tot("t_money") / mon if mon else 0
    lat = dict(p50_ms=statistics.median(n["stream"]["p50_ms"] for n in nights),
               p95_ms=max(n["stream"]["p95_ms"] for n in nights), p99_ms=max(n["stream"]["p99_ms"] for n in nights))
    days = len(nights)
    s = dict(customers=n_cust, nights=days,
             tx_per_day=tot("tx") / days, tx_per_customer_day=tot("tx") / days / n_cust,
             touched_share=tot("touched") / days / n_cust,
             signal_share_of_touched=tot("signal") / tot("touched"), balance_only_share_of_touched=tot("balance_only") / tot("touched"),
             rebuild_share=reb / days / n_cust, money_share=mon / days / n_cust,
             tier2_rebuild_share=tot("tier2_rebuild") / days / n_cust, tier2_money_share=tot("tier2_money") / days / n_cust,
             ms_per_rebuild=ms_rebuild, ms_per_money_refresh=ms_money,
             nightly_cpu_s_per_day=tot("t_total") / days, nightly_wall_s_per_day=sum(n["t_wall_nightly"] for n in nights) / days,
             tier0=lat, tier0_us_mean=1e6 * sum(n["stream"]["total_s"] for n in nights) / max(1, sum(n["stream"]["n"] for n in nights)))
    if "verify" in nights[-1]:
        s["final_equal"] = n_cust - len(nights[-1]["verify"]["strict_mismatch"])
        s["all_nights_equal"] = all(not n["verify"]["strict_mismatch"] for n in nights if "verify" in n)
    return s


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(DB))
    ap.add_argument("--start", default=_d(AS_OF - 7 * DAY), help="build twins as of this day, then replay the next --days")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--verify", choices=("daily", "final", "none"), default="final")
    ap.add_argument("--no-variants", action="store_true", help="skip the staleness comparison variants")
    ap.add_argument("--json", help="write the full report to this file")
    a = ap.parse_args()
    print(f"{platform.machine()} · {platform.python_version()} · pandas {pd.__version__} · {a.workers} worker(s)")
    rep = replay(a.db, a.start, a.days, a.workers, a.verify, not a.no_variants)
    print(json.dumps(rep["summary"], indent=2, default=str))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(rep, f, indent=1, default=str)


if __name__ == "__main__":
    main()
