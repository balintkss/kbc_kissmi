"""Turn a digital twin into channel-agnostic experience blocks.

  page(twin, topic)  -> one highlighted variant with the reason, alternatives collapsed
                        (twin=None -> the generic page every anonymous visitor gets)
  moments(twin)      -> proactive push messages, with the ones we deliberately hold back

The same JSON feeds the app, the website and any other channel.
"""
from twin.catalog import CATALOG

LOAN_MONTHS = 60
LOAN_RATE = 0.055  # illustrative yearly rate, only used to size an affordable loan


def _fact(twin, key):
    f = twin["facts"].get(key)
    return None if f is None or f.get("rejected_by_customer") else f


def _affordable_loan(twin, share=0.35):
    plan = twin.get("plan")
    if not plan or plan["free_to_spend"] <= 0:
        return None
    monthly = round(plan["free_to_spend"] * share, -1)
    r = LOAN_RATE / 12
    principal = monthly * (1 - (1 + r) ** -LOAN_MONTHS) / r
    return dict(monthly=monthly, max_amount=round(principal, -2), months=LOAN_MONTHS)


def _pick_car_loan(t):
    car, buffer = _fact(t, "has_car"), _fact(t, "financial_buffer")
    loan = _affordable_loan(t)
    fit = f" Based on your salary-day plan you can comfortably pay €{loan['monthly']:.0f}/month (≈ €{loan['max_amount']:,.0f} over {loan['months']} months)." if loan else ""
    if car and car.get("bought_recently") and not car.get("has_car_loan"):
        return "used_car_loan", (f"You bought your car on {car['since']} with your own savings, so you probably don't need a new one. "
                                 f"If you're looking at a second car, this keeps the payment within budget.") + fit, ["has_car", "life_event_new_car"]
    if car and car["powertrain"] == "electric":
        return "green_car_loan", "You already drive electric, so your next car qualifies for the green rate." + fit, ["has_car"]
    if car and car.get("older_car"):
        fuel = next((i["monthly"] for i in car["implies"] if i["cost"] == "fuel"), 0)
        return "green_car_loan", (f"Your car is over 4 years old and fuel costs you ≈ €{fuel}/month. Charging an EV typically costs "
                                  f"a third of that, and the green rate is the lowest we offer.") + fit, ["has_car"]
    if loan and loan["max_amount"] < 18000:
        return "used_car_loan", "A second-hand car keeps the monthly payment within what your budget comfortably allows." + fit, ["income", "financial_buffer"]
    return "new_car_loan", ("Your income and buffer comfortably support a new car." if buffer and buffer["value"] >= 3 else "") + fit, ["income"]


def _pick_car_insurance(t):
    car = _fact(t, "has_car")
    if not car:
        return None
    where = car.get("insured_at")
    elsewhere = f" You currently insure it at {where}: we can quote in 2 minutes using what we already know." if where and where != "KBC" else ""
    price = car.get("purchase_price")
    if car.get("bought_recently") and price and price >= 20000 and not car.get("older_car"):
        return "omnium", f"Your car is recent and worth ≈ €{price:,.0f}; full omnium protects that value." + elsewhere, ["has_car"]
    if car.get("older_car") and (not price or price < 8000):
        return "liability", "Your car is over 4 years old; own-damage cover rarely pays off at this age." + elsewhere, ["has_car"]
    return "mini_omnium", (f"For a {'€' + format(price, ',.0f') + ' ' if price else ''}second-hand car, mini-omnium covers theft, glass "
                           f"and storm without paying for own-damage you'd rarely claim.") + elsewhere, ["has_car"]


def _pick_savings(t):
    buffer, emp = _fact(t, "financial_buffer"), _fact(t, "employment")
    products = set(t["kbc_products"])
    if buffer and buffer["value"] < 3:
        target = buffer["monthly_spending"] * 3
        return "savings_account", (f"Your savings cover {buffer['value']} months of spending. Three months (≈ €{target:,.0f}) "
                                   f"is a safe buffer; an automatic transfer on payday gets you there."), ["financial_buffer"]
    if "pension_savings" not in products and emp and emp["value"] in ("employee", "self_employed") and t["age"] < 64:
        return "pension_savings", ("Your buffer is healthy and you don't use pension savings yet: every euro you put in "
                                   "gives 25–30% back via your taxes."), ["financial_buffer", "employment"]
    if "investment_plan" not in products:
        return "investment_plan", (f"With {buffer['value']} months of buffer, money above that grows more in a monthly "
                                   f"investment plan than on a savings account."), ["financial_buffer"]
    return "savings_account", "Keep topping up your buffer automatically on payday.", ["financial_buffer"]


def _pick_home(t):
    housing, buffer = _fact(t, "housing"), _fact(t, "financial_buffer")
    moved = _fact(t, "life_event_moved")
    if moved:
        return "home_insurance", f"You moved on {moved['value']}: make sure your new home and contents are insured.", ["life_event_moved"]
    if housing and housing["value"] == "renting" and buffer and buffer["value"] >= 3 and (_fact(t, "income") or {}).get("value", 0) >= 2400:
        return "home_loan", (f"You pay €{housing['monthly']:,.0f} rent every month and have a solid buffer: a home loan "
                             f"payment of a similar amount could build your own capital instead."), ["housing", "financial_buffer"]
    if housing and housing["value"] in ("owner", "owner_with_mortgage"):
        return "renovation_loan", "As an owner, energy works lower your bills and raise your home's value.", ["housing"]
    return "home_insurance", "Protect your home and belongings, whether you rent or own.", ["housing"]


def _pick_family(t):
    baby, kids = _fact(t, "life_event_new_baby"), _fact(t, "children")
    if baby:
        return "hospital_insurance", (f"Congratulations! Adding your baby (born around {baby['value']}) to hospitalisation "
                                      f"insurance now avoids any waiting period."), ["life_event_new_baby"]
    if kids:
        return "child_savings", (f"You receive child benefit for {kids['value']} child{'ren' if kids['value'] > 1 else ''}: "
                                 f"putting part of it aside monthly builds a start capital for later."), ["children"]
    if _fact(t, "pet"):
        return "family_liability", f"Your {_fact(t, 'pet')['value']} is covered by family liability if it causes damage to others.", ["pet"]
    return "family_liability", "Covers damage you or your household cause to others.", []


PICKERS = {"car_loan": _pick_car_loan, "car_insurance": _pick_car_insurance, "savings": _pick_savings,
           "home": _pick_home, "family": _pick_family}


def page(twin, topic):
    """Experience block for a topic: generic for anonymous visitors, one highlight for a known customer."""
    cat = CATALOG[topic]
    variants = [dict(id=k, **v) for k, v in cat["variants"].items()]
    pick = PICKERS[topic](twin) if twin else None
    if not pick:
        return dict(topic=topic, title=cat["title"], personalized=False, highlight=None, variants=variants)
    vid, reason, fact_keys = pick
    facts = [dict(key=k, summary=twin["facts"][k]["summary"], confidence=twin["facts"][k]["confidence"])
             for k in fact_keys if k in twin["facts"]]
    return dict(topic=topic, title=cat["title"], personalized=True,
                highlight=dict(id=vid, **cat["variants"][vid], reason=reason, because=facts),
                alternatives=[dict(id=v["id"], name=v["name"], summary=v["summary"]) for v in variants if v["id"] != vid])


def moments(twin, max_push=2):
    """Proactive messages ranked by priority. Sales messages are held back when the customer is under money stress."""
    f = lambda k: _fact(twin, k)
    plan, stress = twin.get("plan"), f("money_stress")
    out, held = [], []

    def add(kind, priority, title, body, topic=None, sales=False):
        m = dict(kind=kind, priority=priority, title=title, body=body, topic=topic, sales=sales)
        if sales and stress:
            held.append(dict(m, held_because="Customer shows money stress: no product offers, only support."))
        else:
            out.append(m)

    if plan and plan["income_kind"] == "irregular":
        head = f"Planned on a quiet month (€{plan['income']:,}): bills €{plan['bills_until_next_payday']:,}, set aside €{plan['reserve_total']}"
        if plan["free_to_spend"] < 0:
            add("salary_plan", 92, "A quiet month would be tight",
                head + f". That's €{-plan['free_to_spend']:,} short before groceries — keeping ≈ €{-plan['free_to_spend'] * 3:,} aside from your good months covers it.")
        else:
            add("salary_plan", 90, "Your monthly plan is ready",
                head + f" — leaves €{plan['free_per_week']}/week. Anything above that can go straight to your buffer.")
    elif plan:
        body = (f"€{plan['income']:,} arrives on {plan['payday']}. Bills €{plan['bills_until_next_payday']:,}, "
                f"set aside €{plan['reserve_total']}" + (f", save €{plan['planned_savings']}" if plan["planned_savings"] else "")
                + f" — that leaves €{plan['free_per_week']}/week to spend freely.")
        if plan["heads_up"]:
            body += " Heads-up: " + "; ".join(plan["heads_up"]) + "."
        add("salary_plan", 90, "Your payday plan is ready", body)
    if stress:
        add("support", 95, "Let's get ahead of next month",
            "Your balance dipped below zero a few times lately. We can move a bill to after payday or spread a large one — no fees, no product.")
    car = f("has_car")
    if car and car.get("bought_recently"):
        add("new_car", 80, "Congrats on the car!",
            f"Beyond fuel it will cost ≈ €{car['monthly_reserve'] * 12:,}/year (maintenance, tax, inspection). "
            f"Shall we set aside €{car['monthly_reserve']}/month from payday?", "car_insurance", sales=car.get("insured_at") not in (None, "KBC"))
    if f("life_event_new_baby"):
        add("new_baby", 85, "Welcome to your little one", "We've prepared what changes now: childcare costs, hospital cover and child benefit.", "family", sales=True)
    if f("life_event_moved"):
        add("moved", 75, "Settled in?", "Your new address, energy contract and home insurance — we've listed what's left to arrange.", "home", sales=True)
    for key in ("life_event_first_job", "life_event_new_job"):
        if f(key):
            add("new_job", 70, "New job, new plan", f"Your salary from {f(key)['value']} changes your budget: here's your updated payday plan and a savings suggestion.", "savings", sales=True)
    out.sort(key=lambda m: -m["priority"])
    return dict(push=out[:max_push], feed=out[max_push:], held_back=held)
