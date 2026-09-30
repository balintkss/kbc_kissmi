"""Turn a digital twin into channel-agnostic experience blocks.

  page(twin, topic)  -> one highlighted variant with the reason, alternatives collapsed
                        (twin=None -> the generic page every anonymous visitor gets)
  moments(twin)      -> proactive push messages, with the ones we deliberately hold back
                        (moments(twin, extra=[...]) also ranks prebuilt ones, e.g. twin.forecast.foresight_moments)

The same JSON feeds the app, the website and any other channel.

Rules every picker follows:
  * any fact can be missing or rejected by the customer (_fact() -> None): never index into it blindly;
  * every highlight carries a non-empty, honest reason;
  * under money stress (support-first) no credit is highlighted and no reason pushes new spending.
Customer-facing text uses friendly dates ("Fri 23 Oct", "13 Jun 2026"); structured fields keep ISO dates.

Confirmed-facts commercial gate (the Financial Understanding Contract, docs/KBC_VALUE_MATRIX.md): only facts the
customer confirmed (glass box) or stated (Kate memory, twin/memory.py) may drive a commercial journey. Every
personalized, non-support block gets `commercial_ok`; when a supporting fact is only inferred it also gets
`needs_confirmation: [{"fact", "question": "We noticed <summary>. Is that right?"}]`. Mode: env TWIN_COMMERCIAL_GATE
  confirm (default)  keep the highlight, flag it (commercial_ok false + needs_confirmation)
  strict             no product until confirmed: the highlight becomes a question card with id "confirm"
  off                no gate fields at all (the old behaviour)
Support-first (money stress) blocks are left exactly as they are: they never sell anyway.

Customer preferences (twin["preferences"], from twin/memory.py) are hard rules: a topic in `no_contact_topics`
gets a non-promotional page, and its moments are held back ("Customer asked not to be contacted about <topic>").

Production boundary (family): babies, births and children are never used unless the customer confirmed the
household change (feedback on life_event_new_baby / children, or a household_change memory). Until then no
new-baby moment, and the family page never mentions a baby, a birth, a child or a hospital.
"""
import os
import re
from datetime import date

from twin.catalog import CATALOG
from twin.engine import AS_OF

LOAN_MONTHS = 60
LOAN_RATE = 0.055  # illustrative yearly rate, only used to size an affordable loan

TODAY = AS_OF.date()
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

CREDIT_VARIANTS = {"new_car_loan", "used_car_loan", "green_car_loan", "home_loan", "renovation_loan"}
SUPPORT_LEAD = "Let's first get your payday plan back in balance"
# Shown instead of a loan when the customer is under money stress (no product, same highlight schema).
SUPPORT_HIGHLIGHT = dict(name="Your payday plan first", summary="No new credit for now: we help you get next month in balance.",
                         features=["Move a bill to after payday", "Spread a large bill, no fees", "No product, no sales pitch"])
NO_ROOM = ("Your budget has no room for a monthly payment right now — if a car is essential, a smaller second-hand loan "
           "keeps it manageable; let's first look at your payday plan.")

GATE_MODES = ("confirm", "strict", "off")
COMMERCIAL_OK = ("confirmed", "stated")  # provenance values that may drive a commercial journey
# strict gate: shown instead of a product until the customer confirmed what the highlight would rest on.
CONFIRM_HIGHLIGHT = dict(name="First, is this right?", summary="Confirm what we noticed and we'll suggest the one option that fits.",
                         features=["One tap: that's right, or that's not me", "Nothing is suggested on a guess",
                                   "Change or forget it any time"])
CONFIRM_REASON = "We only suggest a product once you've confirmed what it's based on."
HOUSEHOLD_FACTS = ("life_event_new_baby", "children", "household_change")


def _nice_date(value):
    """Friendly customer-facing date: '2026-10-23' -> 'Fri 23 Oct' (upcoming), '2026-06-13' -> '13 Jun 2026' (past).

    ISO dates inside a longer text are rewritten too ('before 2025-10-01' -> 'before 1 Oct 2025'); an upcoming date
    outside the current year keeps its year ('Tue 5 Jan 2027'). Anything else is returned unchanged; None -> ''."""
    if value is None:
        return ""
    if isinstance(value, date):
        value = value.isoformat()[:10]

    def one(m):
        try:
            d = date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return m[0]
        if d >= TODAY:
            return f"{_DAYS[d.weekday()]} {d.day} {_MONTHS[d.month - 1]}" + ("" if d.year == TODAY.year else f" {d.year}")
        return f"{d.day} {_MONTHS[d.month - 1]} {d.year}"
    return _ISO_DATE.sub(one, str(value))


def _fact(twin, key):
    f = (twin.get("facts") or {}).get(key)
    return None if not isinstance(f, dict) or f.get("rejected_by_customer") else f


def _num(fact, field="value"):
    """A numeric field of a fact, or None when the fact is missing/rejected or the value isn't a number."""
    v = fact.get(field) if fact else None
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def provenance(fact):
    """confirmed (glass-box verdict) > stated (Kate memory) > ecosystem (reserved) > inferred (engine default).

    twin/memory.apply_memories sets fact["provenance"]; a raw stored twin falls back to the feedback flags."""
    p = fact.get("provenance") if isinstance(fact, dict) else None
    if p in ("confirmed", "stated", "ecosystem", "inferred"):
        return p
    return "confirmed" if isinstance(fact, dict) and fact.get("confirmed_by_customer") else "inferred"


def gate_mode():
    """TWIN_COMMERCIAL_GATE = confirm (default) | strict | off, read on every call so it can change at runtime."""
    mode = os.environ.get("TWIN_COMMERCIAL_GATE", "confirm").strip().lower()
    return mode if mode in GATE_MODES else "confirm"


def household_confirmed(t):
    """The customer confirmed a household change themselves: feedback on a household fact, or a stated memory."""
    for key in HOUSEHOLD_FACTS:
        f = _fact(t, key)
        if f and (f.get("confirmed_by_customer") or provenance(f) in COMMERCIAL_OK):
            return True
    return False


def no_contact_topics(t):
    return set(((t or {}).get("preferences") or {}).get("no_contact_topics") or ())


def _topic_label(topic):
    return CATALOG[topic]["title"].lower() if topic in CATALOG else str(topic).replace("_", " ")


def _question(fact):
    """'We noticed <summary>. Is that right?' in friendly dates."""
    summary = _nice_date(fact.get("summary") or fact["key"].replace("_", " ")).rstrip(". ")
    if len(summary) > 1 and summary[0].isupper() and summary[1].islower():
        summary = summary[0].lower() + summary[1:]
    return f"We noticed {summary}. Is that right?"


def _affordable_loan(twin, share=0.35):
    free = (twin.get("plan") or {}).get("free_to_spend")
    if not isinstance(free, (int, float)) or free <= 0:
        return None
    monthly = round(free * share, -1)
    r = LOAN_RATE / 12
    principal = monthly * (1 - (1 + r) ** -LOAN_MONTHS) / r
    return dict(monthly=monthly, max_amount=round(principal, -2), months=LOAN_MONTHS)


def _pick_car_loan(t):
    car, buffer = _fact(t, "has_car"), _fact(t, "financial_buffer")
    loan = _affordable_loan(t)
    no_room = bool(t.get("plan")) and loan is None  # we know the budget, and it leaves nothing for a payment
    if loan:
        fit = (f" Based on your salary-day plan you can comfortably pay €{loan['monthly']:.0f}/month "
               f"(≈ €{loan['max_amount']:,.0f} over {loan['months']} months).")
    elif no_room:
        fit = " Your budget has no room for a monthly payment right now, so let's first look at your payday plan."
    else:
        fit = ""
    if car and car.get("bought_recently") and not car.get("has_car_loan"):
        since = car.get("since")
        when = f" on {_nice_date(since)}" if since and _ISO_DATE.fullmatch(str(since)) else ""
        second = ("this keeps the payment within budget." if loan else "a second-hand loan keeps the payment smallest.")
        return "used_car_loan", (f"You bought your car{when} with your own savings, so you probably don't need a new one. "
                                 f"If you're looking at a second car, {second}") + fit, ["has_car", "life_event_new_car"]
    if car and car.get("powertrain") == "electric":
        return "green_car_loan", "You already drive electric, so your next car qualifies for the green rate." + fit, ["has_car"]
    if car and car.get("older_car"):
        fuel = next((i.get("monthly") for i in car.get("implies") or [] if i.get("cost") == "fuel" and i.get("monthly")), None)
        costs = (f" and fuel costs you ≈ €{fuel}/month. Charging an EV typically costs a third of that" if fuel
                 else ". Charging an EV typically costs a third of what fuel does")
        return "green_car_loan", (f"Your car is over 4 years old{costs}, "
                                  f"and the green rate is the lowest we offer.") + fit, ["has_car"]
    if no_room:
        return "used_car_loan", NO_ROOM, ["income", "financial_buffer"]
    if not loan:  # no regular income detected, so no plan to size a payment on
        return "used_car_loan", ("We don't see a regular income yet, so a smaller second-hand loan is the safest start; "
                                 "an advisor can size it with you."), ["financial_buffer"]
    if loan["max_amount"] < 18000:
        return "used_car_loan", "A second-hand car keeps the monthly payment within what your budget comfortably allows." + fit, ["income", "financial_buffer"]
    if (_num(buffer) or 0) >= 3:
        return "new_car_loan", "Your income and buffer comfortably support a new car." + fit, ["income", "financial_buffer"]
    return "new_car_loan", "Your monthly budget leaves room for a new-car payment." + fit, ["income"]


def _pick_car_insurance(t):
    car = _fact(t, "has_car")
    if not car:
        return None
    where = car.get("insured_at")
    elsewhere = f" You currently insure it at {where}: we can quote in 2 minutes using what we already know." if where and where != "KBC" else ""
    price = _num(car, "purchase_price")
    if car.get("bought_recently") and price and price >= 20000 and not car.get("older_car"):
        return "omnium", f"Your car is recent and worth ≈ €{price:,.0f}; full omnium protects that value." + elsewhere, ["has_car"]
    if car.get("older_car") and (not price or price < 8000):
        return "liability", "Your car is over 4 years old; own-damage cover rarely pays off at this age." + elsewhere, ["has_car"]
    return "mini_omnium", (f"For a {'€' + format(price, ',.0f') + ' ' if price else ''}second-hand car, mini-omnium covers theft, glass "
                           f"and storm without paying for own-damage you'd rarely claim.") + elsewhere, ["has_car"]


def _pick_savings(t):
    buffer, emp = _fact(t, "financial_buffer"), _fact(t, "employment")
    months = _num(buffer)
    products, age = set(t.get("kbc_products") or []), t.get("age")
    if months is None:  # no buffer estimate (or the customer said ours is wrong): build the base first, no investing
        return "savings_account", ("Three months of spending on a savings account is the safe base for everything else; "
                                   "an automatic transfer on payday builds it without you having to think about it."), []
    if months < 3:
        target = (_num(buffer, "monthly_spending") or 0) * 3
        return "savings_account", (f"Your savings cover {months} months of spending. Three months{f' (≈ €{target:,.0f})' if target else ''} "
                                   f"is a safe buffer; an automatic transfer on payday gets you there."), ["financial_buffer"]
    if "pension_savings" not in products and emp and emp.get("value") in ("employee", "self_employed") and isinstance(age, int) and age < 64:
        return "pension_savings", ("Your buffer is healthy and you don't use pension savings yet: every euro you put in "
                                   "gives 25–30% back via your taxes."), ["financial_buffer", "employment"]
    if "investment_plan" not in products:
        return "investment_plan", (f"With {months} months of buffer, money above that grows more in a monthly "
                                   f"investment plan than on a savings account."), ["financial_buffer"]
    return "savings_account", "Keep topping up your buffer automatically on payday.", ["financial_buffer"]


def _moved_on(moved):
    when = _nice_date(moved.get("value") or moved.get("since"))
    return f"You moved on {when}" if when else "You moved recently"


def _pick_home(t):
    housing, buffer, income = _fact(t, "housing"), _fact(t, "financial_buffer"), _fact(t, "income")
    moved = _fact(t, "life_event_moved")
    if moved:
        return "home_insurance", f"{_moved_on(moved)}: make sure your new home and contents are insured.", ["life_event_moved"]
    tenure = housing.get("value") if housing else None
    if tenure == "renting" and (_num(buffer) or 0) >= 3 and (_num(income) or 0) >= 2400:
        rent = _num(housing, "monthly")
        return "home_loan", (f"You pay {f'€{rent:,.0f} ' if rent else ''}rent every month and have a solid buffer: a home loan "
                             f"payment of a similar amount could build your own capital instead."), ["housing", "financial_buffer"]
    if tenure in ("owner", "owner_with_mortgage"):
        return "renovation_loan", "As an owner, energy works lower your bills and raise your home's value.", ["housing"]
    return "home_insurance", "Protect your home and belongings, whether you rent or own.", ["housing"]


def _pick_family(t):
    """Production boundary: a baby or children only count once the customer confirmed the household change.

    Unconfirmed, the page falls back to pets / household liability and never mentions a baby, birth, child or hospital."""
    confirmed = household_confirmed(t)
    baby = _fact(t, "life_event_new_baby") if confirmed else None
    kids = _fact(t, "children") if confirmed else None
    change = _fact(t, "household_change") if confirmed else None
    pet = _fact(t, "pet")
    if baby:
        born = _nice_date(baby.get("value") or baby.get("since"))
        return "hospital_insurance", (f"Congratulations! Adding your baby{f' (born around {born})' if born else ''} to hospitalisation "
                                      f"insurance now avoids any waiting period."), ["life_event_new_baby"]
    if kids:
        n = _num(kids)
        count = f" for {n:g} child{'ren' if n > 1 else ''}" if n and n > 0 else ""
        return "child_savings", (f"You receive child benefit{count}: "
                                 f"putting part of it aside monthly builds a start capital for later."), ["children"]
    if change:
        return "family_liability", ("You told us your household is changing: family liability covers everyone who lives "
                                    "with you, and we can go through the rest of your cover together."), ["household_change"]
    if pet:
        return "family_liability", f"Your {pet.get('value') or 'pet'} is covered by family liability if it causes damage to others.", ["pet"]
    return "family_liability", "Covers damage you or your household cause to others.", []


PICKERS = {"car_loan": _pick_car_loan, "car_insurance": _pick_car_insurance, "savings": _pick_savings,
           "home": _pick_home, "family": _pick_family}


def _support_first(t, topic, pick):
    """Money stress: help first. Never highlight credit; keep protection and a buffer, without pushing new spending."""
    if topic == "car_loan":
        return "support", (f"{SUPPORT_LEAD} — no new loan for now. These are the options we'd look at once there's room "
                           f"each month."), ["money_stress"]
    if topic == "home":
        moved = _fact(t, "life_event_moved")
        what = (f"{_moved_on(moved)}, so the one thing worth checking is that your new home and contents are insured."
                if moved else "The one thing worth checking is that your home and belongings are insured, so one accident "
                              "never turns into a big bill.")
        return "home_insurance", f"{SUPPORT_LEAD} — no new loan for now. {what}", ["life_event_moved" if moved else "housing", "money_stress"]
    if topic == "savings":
        return "savings_account", (f"{SUPPORT_LEAD}: no investing for now. Even a small automatic transfer on payday starts a "
                                   f"buffer for unexpected bills, and it stays available any time."), ["financial_buffer", "money_stress"]
    if not pick:
        return None
    vid, reason, keys = pick
    if topic == "car_insurance":
        vid = "mini_omnium" if vid == "omnium" else vid
        cover = ("at over 4 years old, the legal minimum keeps your premium as low as it gets" if vid == "liability"
                 else "mini-omnium covers theft, glass and storm without paying for own-damage cover")
        return vid, f"{SUPPORT_LEAD}, so only the cover your car really needs: {cover}.", ["has_car", "money_stress"]
    if vid == "child_savings":
        return vid, (f"{SUPPORT_LEAD}: the child benefit is there for this month's costs. Once there's room, putting part of it "
                     f"aside builds a start capital for later."), [*keys, "money_stress"]
    return vid, f"{reason} Nothing else for now: {SUPPORT_LEAD[0].lower()}{SUPPORT_LEAD[1:]}.", [*keys, "money_stress"]


def page(twin, topic):
    """Experience block for a topic: generic for anonymous visitors, one highlight for a known customer.

    Under money stress (a non-rejected money_stress fact) the block carries support_first=True: no credit is
    highlighted (car_loan shows a 'payday plan first' card with every loan collapsed) and reasons never sell."""
    cat = CATALOG[topic]
    variants = [dict(id=k, **v) for k, v in cat["variants"].items()]
    generic = dict(topic=topic, title=cat["title"], personalized=False, highlight=None, variants=variants)
    if not twin:
        return generic
    stressed = _fact(twin, "money_stress") is not None
    flag = dict(support_first=True) if stressed else {}
    if topic in no_contact_topics(twin):  # the customer's preference is a hard rule: every option, no suggestion
        return dict(generic, **flag, no_contact=True,
                    note=f"You asked us not to contact you about {_topic_label(topic)}, so we don't suggest anything here.")
    pick = PICKERS[topic](twin)
    if stressed:
        pick = _support_first(twin, topic, pick)
    if not pick:
        return dict(generic, **flag)
    vid, reason, fact_keys = pick
    cited = [f for f in (_fact(twin, k) for k in dict.fromkeys(fact_keys)) if f]  # rejected facts are never cited
    because = [dict(key=f["key"], summary=_nice_date(f.get("summary", "")), confidence=f.get("confidence"),
                    provenance=provenance(f)) for f in cited]
    variant = SUPPORT_HIGHLIGHT if vid == "support" else cat["variants"][vid]
    block = dict(topic=topic, title=cat["title"], personalized=True, **flag,
                 highlight=dict(id=vid, **variant, reason=reason, because=because),
                 alternatives=[dict(id=v["id"], name=v["name"], summary=v["summary"]) for v in variants if v["id"] != vid])
    return block if stressed else _commercial_gate(block, cited, variants)


def _commercial_gate(block, cited, variants):
    """Only confirmed or stated facts may drive a commercial highlight (see the module docstring)."""
    mode = gate_mode()
    if mode == "off":
        return block
    unconfirmed = [f for f in cited if provenance(f) not in COMMERCIAL_OK]
    if not unconfirmed:
        return dict(block, commercial_ok=True)
    block = dict(block, commercial_ok=False,
                 needs_confirmation=[dict(fact=f["key"], question=_question(f)) for f in unconfirmed])
    if mode == "strict":
        block["highlight"] = dict(id="confirm", **CONFIRM_HIGHLIGHT, reason=CONFIRM_REASON,
                                  because=block["highlight"]["because"])
        block["alternatives"] = [dict(id=v["id"], name=v["name"], summary=v["summary"]) for v in variants]
    return block


def moments(twin, max_push=2, extra=None):
    """Proactive messages ranked by priority. Sales messages are held back when the customer is under money stress.

    extra: optional prebuilt moment dicts (kind, priority, title, body, topic?, sales?), e.g. the foresight moments
    from twin.forecast.foresight_moments(): overdraft_warning (94) and self_employed_reserve (88). They are ranked
    and held back by the same rules. With extra=None the result is exactly what it always was."""
    f = lambda k: _fact(twin, k)  # noqa: E731
    plan, stress = twin.get("plan"), f("money_stress")
    quiet = no_contact_topics(twin)
    out, held = [], []

    def add(kind, priority, title, body, topic=None, sales=False):
        m = dict(kind=kind, priority=priority, title=title, body=body, topic=topic, sales=bool(sales))
        if topic and topic in quiet:  # the customer's own preference outranks every other rule
            held.append(dict(m, held_because=f"Customer asked not to be contacted about {_topic_label(topic)}"))
        elif sales and stress:
            held.append(dict(m, held_because="Customer shows money stress: no product offers, only support."))
        else:
            out.append(m)

    if plan and plan.get("income_kind") == "irregular":
        head = f"Planned on a quiet month (€{plan['income']:,}): bills €{plan['bills_until_next_payday']:,}, set aside €{plan['reserve_total']}"
        if (plan.get("free_to_spend") or 0) < 0:
            add("salary_plan", 92, "A quiet month would be tight",
                head + f". That's €{-plan['free_to_spend']:,} short before groceries — keeping ≈ €{-plan['free_to_spend'] * 3:,} aside from your good months covers it.")
        else:
            add("salary_plan", 90, "Your monthly plan is ready",
                head + f" — leaves €{plan['free_per_week']}/week. Anything above that can go straight to your buffer.")
    elif plan:
        payday = _nice_date(plan.get("payday"))
        body = (f"€{plan['income']:,} arrives{f' on {payday}' if payday else ' on payday'}. Bills €{plan['bills_until_next_payday']:,}, "
                f"set aside €{plan['reserve_total']}" + (f", save €{plan['planned_savings']}" if plan.get("planned_savings") else "")
                + f" — that leaves €{plan['free_per_week']}/week to spend freely.")
        if plan.get("heads_up"):
            body += " Heads-up: " + "; ".join(_nice_date(h) for h in plan["heads_up"]) + "."
        add("salary_plan", 90, "Your payday plan is ready", body)
    if stress:
        add("support", 95, "Let's get ahead of next month",
            "Your balance dipped below zero a few times lately. We can move a bill to after payday or spread a large one — no fees, no product.")
    car = f("has_car")
    if car and car.get("bought_recently"):
        reserve = _num(car, "monthly_reserve")
        cost = (f"Beyond fuel it will cost ≈ €{reserve * 12:,}/year (maintenance, tax, inspection). "
                f"Shall we set aside €{reserve}/month from payday?") if reserve else \
            "Beyond fuel it brings maintenance, tax and inspection costs. Shall we set aside a little from payday?"
        add("new_car", 80, "Congrats on the car!", cost, "car_insurance", sales=car.get("insured_at") not in (None, "KBC"))
    if f("life_event_new_baby") and household_confirmed(twin):  # production boundary: never on an inferred birth
        add("new_baby", 85, "Welcome to your little one", "We've prepared what changes now: childcare costs, hospital cover and child benefit.", "family", sales=True)
    if f("life_event_moved"):
        add("moved", 75, "Settled in?", "Your new address, energy contract and home insurance — we've listed what's left to arrange.", "home", sales=True)
    for key in ("life_event_first_job", "life_event_new_job"):
        job = f(key)
        if job:
            employer = f" from {job['value']}" if job.get("value") else ""
            add("new_job", 70, "New job, new plan", f"Your salary{employer} changes your budget: here's your updated payday plan and a savings suggestion.", "savings", sales=True)
    for m in extra or ():
        add(m["kind"], m["priority"], m["title"], m["body"], m.get("topic"), m.get("sales", False))
    out.sort(key=lambda m: -m["priority"])
    return dict(push=out[:max_push], feed=out[max_push:], held_back=held)
