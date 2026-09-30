"""Life-moment checklists: what a life event usually means, auto-ticked from what KBC can already see.

The promise is "KBC already knows, without making you repeat yourself". For every recent life event in the twin
(a move, a first or new job, a new car, a new pet and, only after the customer confirmed it, a household change)
we list the handful of things that usually need arranging and tick off what the twin and the customer's own
transactions already show:

  checklists(con, customer_id, twin)       -> [checklist]; each item has id, label, status (done | todo | unknown),
                                              evidence {text, tx_ids} and an optional topic (/api/experience/{topic})
  life_checklists(con, customer_id, twin)  -> {as_of, intro, checklists, household_prompt} for GET /api/me/life-checklists
  household_prompt(twin)                   -> the neutral "Has your household changed?" item, or None
  life_moments(con, customer_id, twin)     -> moment dicts in the shape of twin.recommender.moments() items
                                              (kind, priority, title, body, topic, sales) for checklists, coverage
                                              gaps (twin/gaps.py), benefit hints and turning 25 (twin/benefits.py)

Rules
  * only facts the customer has not rejected count (a rejected life event gives no checklist);
  * only events of the last WINDOW_DAYS (180) days: older moves or jobs are simply life, not a moment;
  * statuses are honest: "unknown" when payments can't show it (registering a new address at the municipality);
  * all SQL is read-only and scoped `WHERE customer_id = ?`, so evidence only ever cites the customer's own
    transactions; descriptions are never read, and health-related spending (pharmacy, doctor, hospital, baby shops)
    is not even loaded: insurance subcategories are only read as insurance premiums;
  * under money stress (support_first) nothing here sells: life_moments() never returns a sales=True moment.

Production-safe behaviour (family / household)
  The synthetic data contains newborn and family facts only to test the pipeline end to end. In production KBC
  must never infer birth, pregnancy or health from payments (special-category data, GDPR Art. 9 as read by the
  CJEU in C-184/20 and C-252/21; see docs/research/kate_ecosystem_pfa.md §D1 and the "Production boundary" in
  README.md / AGENTS.md). So every family item (the household checklist here, newborn/children coverage gaps in
  twin/gaps.py, family benefit hints in twin/benefits.py) only appears once the customer confirmed the
  `life_event_new_baby` (or `children`) fact themselves (POST /api/me/facts/{fact}/feedback {"correct": true}).
  Until then the customer only gets a neutral `household_change_prompt` that never mentions a baby, a birth,
  a pregnancy or a hospital.
"""
from datetime import date, timedelta
from typing import NamedTuple

from twin.engine import AS_OF
from twin.recommender import _fact, _nice_date, _num, page

TODAY = AS_OF.date()
WINDOW_DAYS = 180
INTRO = "We ticked off what we can already see in your payments, without making you repeat yourself."

ADDRESS_SOURCE = "https://www.belgium.be/nl/huisvesting/verhuizen/adreswijziging"  # 8 working days (FPS portal)
TRAIN_SOURCE = "https://werk.belgie.be/nl/themas/verloning/tussenkomst-van-de-werkgever-de-verplaatsingskosten-woon-werkverkeer"
PENSION_SOURCE = "https://www.wikifin.be/nl/belasting-werk-en-inkomen/belastingaangifte/belastingverminderingen/pensioensparen"
FAMILY_FUND_SOURCE = {
    "Flanders": "https://www.groeipakket.be",
    "Wallonia": "https://www.aviq.be/fr/allocations-familiales",
    "Brussels": "https://www.iriscare.brussels/fr/citoyens/familles-avec-enfants/informations-generales-pour-vos-allocations-familiales/",
}

# Neutral, production-safe prompt: never names a baby, a birth, a pregnancy or a hospital.
HOUSEHOLD_PROMPT = dict(
    kind="household_change_prompt", id="household_change", title="Has your household changed?",
    body="Tell us only if you want KBC to take it into account.",
    why="We only use a household change once you tell us about it yourself.",
    cta="Review what KBC knows about me", link="/api/me/twin", sales=False)

# Only these subcategories are read. Health spending is deliberately absent; insurance premiums are only read as
# premiums (category = 'insurance'), e.g. 'health' is the hospitalisation-insurance premium, never a medical bill.
LIFE_SUBS = ("salary", "moving", "notary", "energy", "home", "car", "liability", "health", "registration",
             "registration_tax", "inspection", "car_purchase", "child_benefit", "birth_allowance", "childcare",
             "vet", "adoption", "pension_savings")
INSURANCE_SUBS = ("home", "car", "liability", "health")


class Tx(NamedTuple):
    tx_id: int
    day: date
    amount: float
    counterparty: str
    category: str
    subcategory: str


# ---------------------------------------------------------------------- shared helpers (also used by gaps/benefits)

def _to_date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def load_life_tx(con, customer_id):
    """The customer's own transactions this module needs (read-only, scoped to customer_id), oldest first."""
    if con is None:
        return []
    marks = ",".join("?" * len(LIFE_SUBS))
    ins = ",".join("?" * len(INSURANCE_SUBS))
    rows = con.execute(
        f"""SELECT tx_id, booked_at, amount, counterparty, category, subcategory FROM transactions
            WHERE customer_id = ? AND subcategory IN ({marks})
              AND (category = 'insurance' OR subcategory NOT IN ({ins}))
            ORDER BY booked_at, tx_id""", (int(customer_id), *LIFE_SUBS, *INSURANCE_SUBS)).fetchall()
    out = []
    for tx_id, booked, amount, counterparty, category, sub in rows:
        day = _to_date(booked)
        if day is not None:
            out.append(Tx(int(tx_id), day, float(amount or 0), counterparty or "", category or "", sub))
    return out


def _tx(con, customer_id, tx):
    return load_life_tx(con, customer_id) if tx is None else tx


def pick(tx, *subs, after=None, before=None):
    """Transactions of the given subcategories between two dates (inclusive), oldest first."""
    return [t for t in tx if t.subcategory in subs and (after is None or t.day >= after) and (before is None or t.day <= before)]


def ids(txs, n=3):
    """Evidence: the most recent tx ids."""
    return [t.tx_id for t in sorted(txs, key=lambda t: (t.day, t.tx_id), reverse=True)[:n]]


def fact(twin, key):
    """A fact the customer has not rejected, or None."""
    return _fact(twin or {}, key)


def confirmed(twin, key):
    f = fact(twin, key)
    return bool(f and f.get("confirmed_by_customer"))


def household_confirmed(twin):
    """Production-safe gate for every family item: the customer confirmed the household change themselves."""
    return confirmed(twin, "life_event_new_baby") or confirmed(twin, "children")


def support_first(twin):
    """Money stress: a non-rejected money_stress fact, or the recommender's own pages say support-first."""
    if fact(twin, "money_stress") is not None:
        return True
    return bool(twin) and bool(page(twin, "home").get("support_first"))


def products(twin):
    return set((twin or {}).get("kbc_products") or [])


def event_date(f):
    """The ISO date a life-event fact happened on (life_event_* keep it in value or since), or None."""
    for v in (f.get("since"), f.get("value")):
        d = _to_date(v) if isinstance(v, str) and len(v) >= 10 and v[:4].isdigit() else None
        if d:
            return d
    return None


def recent_event(twin, key, days=WINDOW_DAYS):
    """(fact, date) for a non-rejected life event within `days` of AS_OF, else (None, None)."""
    f = fact(twin, key)
    d = event_date(f) if f else None
    if d is None or not 0 <= (TODAY - d).days <= days:
        return None, None
    return f, d


def reserve(twin, label):
    plan = (twin or {}).get("plan") or {}
    return next((r for r in plan.get("reserves") or [] if isinstance(r, dict) and r.get("for_") == label), None)


def _item(item_id, label, status, text, txs=(), topic=None, source=None, extra_ids=()):
    evidence = dict(text=text, tx_ids=ids(txs) if txs else [int(i) for i in extra_ids][:3])
    item = dict(id=item_id, label=label, status=status, evidence=evidence, topic=topic)
    if source:
        item["source"] = source
    return item


def _checklist(event, fact_key, title, when, noun, items):
    done, total = sum(i["status"] == "done" for i in items), len(items)
    left = total - done
    summary = f"{done} of {total} things done for {noun}" + (f" — {left} left" if left else " — all set")
    return dict(kind="life_checklist", id=event, event=event, fact=fact_key, title=title, date=when.isoformat(),
                done=done, total=total, left=left, summary=summary, items=items)


def _money(amount):
    return f"€{abs(amount):,.0f}"


def _insurer(t):
    return t.counterparty or "your insurer"


# ---------------------------------------------------------------------- one builder per life event

def _moved(twin, f, when, tx):
    prods = products(twin)
    items = []
    movers = [t for t in pick(tx, "moving", after=when - timedelta(days=30)) if "bpost" not in t.counterparty.lower()]
    notary = pick(tx, "notary", after=when - timedelta(days=60))
    if movers:
        m = movers[0]
        items.append(_item("movers", "Movers paid", "done", f"{m.counterparty}, {_nice_date(m.day)}", movers))
    if notary or f.get("bought_home"):
        items.append(_item("notary", "Notary deed for your new home", "done" if notary else "unknown",
                           f"Notary fees paid on {_nice_date(notary[0].day)}" if notary
                           else "We don't see the notary payment; it may have gone through another account", notary))
    mail = [t for t in pick(tx, "moving", after=when - timedelta(days=10)) if "bpost" in t.counterparty.lower()]
    items.append(_item("mail_forwarding", "Mail forwarding (bpost)", "done" if mail else "todo",
                       f"bpost mail forwarding paid on {_nice_date(mail[0].day)}" if mail
                       else "Forward your mail with bpost for the first months, so nothing gets lost", mail))

    energy = [t for t in pick(tx, "energy", after=when) if t.amount < 0]
    if energy:
        items.append(_item("energy", "Energy contract at the new address", "done",
                           f"{energy[0].counterparty}, first payment since the move on {_nice_date(energy[0].day)}", energy))
    elif (TODAY - when).days < 35:
        items.append(_item("energy", "Energy contract at the new address", "unknown",
                           "The first energy bill at a new address usually comes within a month"))
    else:
        items.append(_item("energy", "Energy contract at the new address", "todo",
                           "We don't see an energy payment since your move: check the contract is in your name"))

    home = pick(tx, "home")
    after_move = [t for t in home if t.day >= when - timedelta(days=15)]
    before_move = [t for t in home if t.day < when - timedelta(days=15)]
    housing = fact(twin, "housing")
    if "home_insurance" in prods:
        items.append(_item("home_insurance", "Home insurance for the new place", "done",
                           "Your KBC home insurance is running" + (f" (last premium {_nice_date(home[-1].day)})" if home else ""),
                           home))
    elif after_move:
        t = after_move[-1]
        items.append(_item("home_insurance", "Home insurance for the new place", "done",
                           f"{_insurer(t)} home premium paid on {_nice_date(t.day)}", after_move))
    elif before_move:
        t = before_move[-1]
        items.append(_item("home_insurance", "Home insurance for the new place", "todo",
                           f"We last saw your {_insurer(t)} home premium on {_nice_date(t.day)}, before your move: "
                           f"tell them your new address, as cover follows a move only for a limited time", before_move, topic="home"))
    else:
        tenant = housing and housing.get("value") == "renting"
        items.append(_item("home_insurance", "Home insurance for the new place", "todo",
                           "We see no home insurance payment" + (": as a tenant, fire and water-damage cover is required by law"
                                                                 if tenant else ""), topic="home"))
    items.append(_item("municipality", "New address registered at the municipality", "unknown",
                       "We can't see this in your payments: register at your new municipality within 8 working days of moving",
                       source=ADDRESS_SOURCE))
    return _checklist("moved", "life_event_moved", "Your move", when, "your move", items)


def _job(twin, f, when, tx, key, stressed):
    employer = f.get("value") if isinstance(f.get("value"), str) else None
    salaries = [t for t in pick(tx, "salary", after=when - timedelta(days=5)) if t.amount > 0
                and (not employer or t.counterparty == employer)]
    items = []
    if salaries:
        s = salaries[0]
        items.append(_item("first_salary", "First salary in", "done",
                           f"{'First salary' if key == 'life_event_first_job' else 'Salary'} from {s.counterparty} on "
                           f"{_nice_date(s.day)} (≈ {_money(s.amount)})", salaries))
    else:
        items.append(_item("first_salary", "First salary in", "unknown", f"We'll tick this off when the salary{' from ' + employer if employer else ''} arrives"))

    plan, income = (twin or {}).get("plan"), fact(twin, "income")
    runs_on_it = bool(plan) and bool(income) and (not employer or income.get("source") == employer)
    payday = _nice_date(plan.get("payday")) if runs_on_it else ""
    items.append(_item("payday_plan", "Payday plan updated", "done" if runs_on_it else "todo",
                       (f"Your payday plan already runs on this salary" + (f": next payday {payday}" if payday else ""))
                       if runs_on_it else "Your payday plan doesn't use the new salary yet", salaries if runs_on_it else ()))

    buffer = fact(twin, "financial_buffer")
    months = _num(buffer)
    if months is None:
        items.append(_item("buffer", "Savings buffer", "unknown", "We can't estimate your buffer yet"))
    elif months >= 3:
        items.append(_item("buffer", "Savings buffer", "done", f"Your savings cover {months:g} months of spending"))
    else:
        target = (_num(buffer, "monthly_spending") or 0) * 3
        items.append(_item("buffer", "Savings buffer", "todo",
                           f"Build a 3-month buffer{f' (≈ €{target:,.0f})' if target else ''} with a small transfer on payday",
                           topic="savings"))

    if not stressed:  # money stress: no saving-for-later suggestions, the payday plan comes first
        pension = pick(tx, "pension_savings")
        if "pension_savings" in products(twin) or pension:
            items.append(_item("pension_savings", "Pension savings", "done", "Your pension savings are running", pension))
        else:
            items.append(_item("pension_savings", "Pension savings", "todo",
                               "Pension savings give 30% back via your taxes on up to €1,050 a year (2026)",
                               topic="savings", source=PENSION_SOURCE))

    train, emp = fact(twin, "commutes_by_train"), fact(twin, "employment")
    if train and emp and emp.get("value") == "employee":
        items.append(_item("train_contribution", "Train pass contribution from your employer", "unknown",
                           "You pay your train pass yourself: employers must contribute to it, so ask HR",
                           extra_ids=train.get("evidence") or (), source=TRAIN_SOURCE))
    first = key == "life_event_first_job"
    event = "first_job" if first else "new_job"
    where = f" at {employer}" if employer else ""
    return _checklist(event, key, f"Your {'first' if first else 'new'} job{where}", when, "your new job", items)


def _new_car(twin, f, when, tx):
    car, prods = fact(twin, "has_car"), products(twin)
    items = []
    premiums = [t for t in pick(tx, "car") if t.day >= when - timedelta(days=30)]
    insurer = car.get("insured_at") if car else None
    if "car_insurance" in prods:
        items.append(_item("insured", "Car insured", "done", "Insured with KBC", premiums))
    elif premiums or insurer:
        where = premiums[-1].counterparty if premiums else insurer
        since = f" (premium since {_nice_date(premiums[0].day)})" if premiums else ""
        items.append(_item("insured", "Car insured", "done", f"Insured at {where}{since}", premiums))
    else:
        items.append(_item("insured", "Car insured", "todo",
                           "Insure it before you drive: third-party liability (BA) is required by law", topic="car_insurance"))
    plate = pick(tx, "registration", after=when - timedelta(days=10))
    items.append(_item("registration", "Number plate registered", "done" if plate else "unknown",
                       f"Registered on {_nice_date(plate[0].day)}" if plate
                       else "Your dealer or insurer usually requests the number plate for you", plate))
    tax = pick(tx, "registration_tax", after=when - timedelta(days=10))
    items.append(_item("registration_tax", "Registration tax paid", "done" if tax else "unknown",
                       f"Paid on {_nice_date(tax[0].day)} ({_money(tax[0].amount)})" if tax
                       else "The registration-tax letter usually arrives within a few weeks", tax))
    upkeep = reserve(twin, "car upkeep")
    if upkeep and upkeep.get("monthly"):
        items.append(_item("upkeep_reserve", "Money set aside for upkeep", "done",
                           f"Your payday plan sets aside €{upkeep['monthly']}/month for maintenance and road tax"))
    else:
        items.append(_item("upkeep_reserve", "Money set aside for upkeep", "todo",
                           "Set aside a little each payday for maintenance and road tax"))
    price = _num(car, "purchase_price") if car else None
    if car and (car.get("older_car") or (price and price < 20000)):
        insp = pick(tx, "inspection", after=when - timedelta(days=30))
        items.append(_item("inspection", "Technical inspection", "done" if insp else "unknown",
                           f"Inspection on {_nice_date(insp[0].day)}" if insp
                           else "A second-hand car needs a yearly inspection (≈ €55): check the date on its certificate", insp))
    return _checklist("new_car", "life_event_new_car", "Your new car", when, "your new car", items)


def _new_pet(twin, f, when, tx):
    pet = fact(twin, "pet")
    kind = pet.get("value") if pet and isinstance(pet.get("value"), str) else "pet"
    items = []
    vet = pick(tx, "vet", after=when)
    items.append(_item("vet", "First vet visit", "done" if vet else "todo",
                       f"Vet visit on {_nice_date(vet[0].day)}" if vet else "Book a first check-up and the vaccinations", vet))
    liability = pick(tx, "liability")
    covered = "family_insurance" in products(twin) or bool(liability)
    items.append(_item("family_liability", f"Family liability covers your {kind}", "done" if covered else "todo",
                       f"Your family liability covers damage your {kind} causes to others" if covered
                       else f"Family liability covers damage your {kind} causes to others", liability,
                       topic=None if covered else "family"))
    care = reserve(twin, f"{kind} care")
    items.append(_item("care_reserve", "Money set aside for vet & care", "done" if care and care.get("monthly") else "todo",
                       f"Your payday plan sets aside €{care['monthly']}/month" if care and care.get("monthly")
                       else "Set aside a little each payday for vet and care costs"))
    return _checklist("new_pet", "life_event_new_pet", f"Your new {kind}", when, f"your new {kind}", items)


def _household(twin, f, when, tx):
    """Only runs after the customer confirmed the household change (production-safe path, see module docstring).

    Special-category rule (docs/research/kate_ecosystem_pfa.md §D1): never infer or expose pregnancy or health data.
    No text here mentions a pregnancy, a delivery or any medical payment; load_life_tx() doesn't even read them, and
    no health-related transaction id is cited. Wording stays with "your little one", and hospitalisation cover is
    treated strictly as an insurance item."""
    region, prods = (twin or {}).get("region"), products(twin)
    fund = FAMILY_FUND_SOURCE.get(region)
    items = []
    allowance = pick(tx, "birth_allowance", after=when - timedelta(days=90))
    items.append(_item("birth_allowance", "One-off birth allowance received", "done" if allowance else "todo",
                       f"Received from {allowance[0].counterparty} on {_nice_date(allowance[0].day)}" if allowance
                       else "Ask your family-allowance fund for the one-off allowance", allowance, source=None if allowance else fund))
    benefit = pick(tx, "child_benefit", after=when)
    items.append(_item("child_benefit", "Child benefit coming in", "done" if benefit else "todo",
                       f"{benefit[-1].counterparty} pays it, last on {_nice_date(benefit[-1].day)}" if benefit
                       else "Register your little one with a family-allowance fund", benefit, source=None if benefit else fund))
    care = pick(tx, "childcare", after=when)
    items.append(_item("childcare", "Childcare arranged", "done" if care else "todo",
                       f"{care[0].counterparty}, since {_nice_date(care[0].day)}" if care
                       else "Book a childcare place early: waiting lists can be long", care))
    cover = pick(tx, "health")  # hospitalisation-insurance premiums only (category = 'insurance')
    if "hospital_insurance" in prods or cover:
        items.append(_item("hospitalisation_cover", "Your little one on your hospitalisation insurance", "unknown",
                           "You have hospitalisation insurance: check your little one is added (early avoids a waiting period)",
                           cover, topic="family"))
    else:
        items.append(_item("hospitalisation_cover", "Your little one on a hospitalisation insurance", "todo",
                           "Add your little one to a hospitalisation insurance, yours or your employer's", topic="family"))
    liability = pick(tx, "liability")
    covered = "family_insurance" in prods or bool(liability)
    items.append(_item("family_liability", "Family liability for the whole household", "done" if covered else "todo",
                       "Your family liability covers the whole household" if covered
                       else "Family liability covers damage anyone in your household causes to others", liability,
                       topic=None if covered else "family"))
    return _checklist("new_baby", "life_event_new_baby", "Your little one", when, "your little one", items)


# ---------------------------------------------------------------------- public API

def household_prompt(twin):
    """The neutral prompt for a recent household change the customer hasn't confirmed (production-safe path)."""
    f, _ = recent_event(twin, "life_event_new_baby")
    return dict(HOUSEHOLD_PROMPT) if f and not f.get("confirmed_by_customer") else None


def checklists(con, customer_id, twin, *, tx=None):
    """One checklist per recent, non-rejected life event. The household checklist needs the customer's confirmation."""
    if not twin:
        return []
    tx = _tx(con, customer_id, tx)
    stressed = support_first(twin)
    out = []
    f, when = recent_event(twin, "life_event_moved")
    if f:
        out.append(_moved(twin, f, when, tx))
    for key in ("life_event_first_job", "life_event_new_job"):
        f, when = recent_event(twin, key)
        if f:
            out.append(_job(twin, f, when, tx, key, stressed))
    f, when = recent_event(twin, "life_event_new_car")
    if f:
        out.append(_new_car(twin, f, when, tx))
    f, when = recent_event(twin, "life_event_new_pet")
    if f:
        out.append(_new_pet(twin, f, when, tx))
    f, when = recent_event(twin, "life_event_new_baby")
    if f and f.get("confirmed_by_customer"):  # production-safe: only a household change the customer confirmed
        out.append(_household(twin, f, when, tx))
    out.sort(key=lambda c: c["date"], reverse=True)
    return out


def life_checklists(con, customer_id, twin, *, tx=None):
    """Response body of GET /api/me/life-checklists."""
    return dict(as_of=TODAY.isoformat(), intro=INTRO, checklists=checklists(con, customer_id, twin, tx=tx),
                household_prompt=household_prompt(twin))


def _moment(kind, priority, title, body, topic=None, sales=False):
    return dict(kind=kind, priority=priority, title=title, body=body, topic=topic, sales=bool(sales))


def life_moments(con, customer_id, twin, *, tx=None, max_gaps=2):
    """Life-moment messages for twin.recommender.moments(extra=...). Never sales=True under money stress."""
    from twin.benefits import benefits, turning_25  # lazy: benefits/gaps import this module's helpers
    from twin.gaps import coverage_gaps

    if not twin:
        return []
    tx = _tx(con, customer_id, tx)
    stressed = support_first(twin)
    out = []
    for c in checklists(con, customer_id, twin, tx=tx):
        if c["left"]:
            topic = next((i["topic"] for i in c["items"] if i["status"] == "todo" and i.get("topic")), None)
            out.append(_moment("life_checklist", 78, f"{c['title']}: {c['left']} thing{'s' if c['left'] > 1 else ''} left",
                               f"{c['summary']}. {INTRO}", topic))
    prompt = household_prompt(twin)
    if prompt:
        out.append(_moment("household_change_prompt", 65, prompt["title"], prompt["body"]))
    gaps = [g for g in coverage_gaps(con, customer_id, twin, tx=tx) if g["severity"] in ("essential", "recommended")]
    for g in gaps[:max_gaps]:
        out.append(_moment("coverage_gap", 76, g["title"], g["why"], g.get("topic"), g.get("sales")))
    hints = benefits(con, customer_id, twin, tx=tx)
    if hints:
        more = len(hints) - 1
        out.append(_moment("benefit_hint", 72, hints[0]["title"],
                           hints[0]["body"] + (f" We found {more} more thing{'s' if more > 1 else ''} worth checking." if more else "")))
    t25 = turning_25(twin)
    if t25:
        out.append(_moment("turning_25", 74, t25["title"], f"{t25['body']} {t25['highlight']['reason']}"))
    if stressed:
        out = [m for m in out if not m["sales"]]
    out.sort(key=lambda m: -m["priority"])
    return out
