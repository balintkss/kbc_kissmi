"""Coverage-gap finder: protection a customer's life already calls for, but that we don't see in their payments.

  coverage_gaps(con, customer_id, twin)   -> [gap]   sorted essential -> recommended -> nice-to-have
  coverage_review(con, customer_id, twin) -> {as_of, support_first, gaps, household_prompt}  (GET /api/me/coverage-gaps)

Each gap: id, kind ("gap" | "check" | "compare"), severity (essential | recommended | nice-to-have), title, why (citing
the facts), because (fact keys), topic (links to /api/experience/{topic} or None), sales, and source (URL) where a
legal rule is quoted. KBC's own research found no proactive coverage-gap check today
(docs/research/kbc_retail_insurance.md §3); this one only uses payments already on the account.

Rules
  * a car with no car-insurance payment at all -> essential: third-party liability (BA) is required by law;
  * a car insured elsewhere is NOT a gap: a "compare" item, nice-to-have;
  * a tenant without home insurance -> essential: tenant liability for fire and water damage is required by law in
    all three regions (Flanders since 1 Jan 2019, Wallonia since 1 Sep 2018, Brussels for leases signed or renewed
    since 1 Nov 2024; source: Wikifin/FSMA, WIKIFIN_HOME below). An owner without it -> recommended (not legally
    required, but mortgage contracts usually ask for it). After a move with only an older, non-KBC premium -> a
    recommended "check" that the policy moved along;
  * a pet or children without family liability -> recommended; a newborn not on hospitalisation insurance ->
    recommended; frequent flyers (3+ flight bookings) without travel cover -> nice-to-have, and we say travel
    insurance is not in our catalogue (twin/catalog.py);
  * under money stress (support_first): only essential gaps, no sales wording, every gap carries support_first=True.

Production-safe behaviour: children and newborn gaps need the customer's own confirmation of the household change
(see twin/checklists.py). Until then they are withheld and the response carries the neutral household_prompt.
"""
from twin.checklists import (TODAY, confirmed, fact, household_confirmed, household_prompt, HOUSEHOLD_PROMPT,
                             pick, products, recent_event, support_first, _tx)
from twin.recommender import _nice_date, _num

SEVERITIES = ("essential", "recommended", "nice-to-have")
WIKIFIN_HOME = "https://www.wikifin.be/nl/budget-betalen-lenen-en-verzekeren/verzekeren/wonen/wie-moet-een-woonverzekering-afsluiten"
TENANT_RULE = {"Flanders": "in Flanders since 1 Jan 2019", "Wallonia": "in Wallonia since 1 Sep 2018",
               "Brussels": "in Brussels for leases signed or renewed since 1 Nov 2024"}
FREQUENT_FLYER = 3  # flight bookings in the last year


def _gap(gap_id, severity, title, why, because, topic=None, sales=True, kind="gap", source=None):
    g = dict(id=gap_id, kind=kind, severity=severity, title=title, why=why, because=because, topic=topic, sales=bool(sales))
    if source:
        g["source"] = source
    return g


def _car(twin, tx, prods):
    car = fact(twin, "has_car")
    if not car:
        return []
    insurer = car.get("insured_at")
    if "car_insurance" in prods or insurer == "KBC":
        return []
    if not insurer and not pick(tx, "car"):
        return [_gap("car_uninsured", "essential", "Your car has no insurance we can see",
                     f"You drive a car ({car.get('summary') or 'we see fuel or charging payments'}), but we see no car-insurance "
                     f"premium. Third-party liability (BA) is required by law for every car on the road.",
                     ["has_car"], "car_insurance", sales=False)]
    where = insurer or pick(tx, "car")[-1].counterparty
    return [_gap("car_insured_elsewhere", "nice-to-have", "Compare your car insurance",
                 f"Not a gap: your car is insured at {where}. If you'd like a second opinion, we can compare it "
                 f"without making you repeat yourself.", ["has_car"], "car_insurance", sales=True, kind="compare")]


def _home(twin, tx, prods):
    housing = fact(twin, "housing")
    tenure = housing.get("value") if housing else None
    moved, moved_on = recent_event(twin, "life_event_moved")
    home = pick(tx, "home")
    if "home_insurance" in prods:
        return []
    if not home:
        if tenure == "renting":
            rule = TENANT_RULE.get(twin.get("region"), "in every Belgian region")
            rent = _num(housing, "monthly")
            return [_gap("home_uninsured_tenant", "essential", "Insure your rented home",
                         f"You rent your home{f' (€{rent:,.0f}/month)' if rent else ''} and we see no home insurance. "
                         f"A tenant must insure their liability for fire and water damage ({rule}).",
                         ["housing"], "home", sales=False, source=WIKIFIN_HOME)]
        if tenure in ("owner", "owner_with_mortgage"):
            return [_gap("home_uninsured_owner", "recommended", "Insure your home",
                         "You own your home and we see no home (fire) insurance. It isn't required by law for owners, "
                         "but mortgage contracts usually ask for it, and one fire or water leak can turn into a very large bill.",
                         ["housing"], "home", source=WIKIFIN_HOME)]
        if moved:
            return [_gap("home_uninsured_after_move", "recommended", "Insure your new home",
                         f"You moved on {_nice_date(moved_on)} and we see no home insurance for the new place.",
                         ["life_event_moved"], "home")]
        return []
    if moved and not [t for t in home if (t.day - moved_on).days >= -15]:
        last = home[-1]
        return [_gap("home_after_move", "recommended", "Check your home insurance moved with you",
                     f"We last saw your {last.counterparty} home premium on {_nice_date(last.day)}, before your move on "
                     f"{_nice_date(moved_on)}. Make sure the policy covers your new address.",
                     ["life_event_moved", "housing"], "home", sales=False, kind="check")]
    return []


def _family(twin, tx, prods):
    """Pets are ordinary facts; children and newborn items need the customer's confirmation (production-safe)."""
    gaps, withheld = [], False
    baby, _ = recent_event(twin, "life_event_new_baby", days=365)
    if baby and "hospital_insurance" not in prods and not pick(tx, "health"):
        if confirmed(twin, "life_event_new_baby"):
            gaps.append(_gap("newborn_hospitalisation_cover", "recommended", "Hospitalisation cover for your little one",
                             "Your little one isn't on a hospitalisation policy that we can see. Adding them early "
                             "avoids a waiting period.", ["life_event_new_baby"], "family"))
        else:
            withheld = True
    if "family_insurance" not in prods and not pick(tx, "liability"):
        pet = fact(twin, "pet")
        kids = fact(twin, "children") or fact(twin, "life_event_new_baby")
        who, because = [], []
        if pet:
            who.append(f"your {pet.get('value') if isinstance(pet.get('value'), str) else 'pet'}")
            because.append("pet")
        if kids and household_confirmed(twin):
            who.append("your children")
            because.append("children" if fact(twin, "children") else "life_event_new_baby")
        elif kids:
            withheld = True
        if who:
            gaps.append(_gap("family_liability", "recommended", "Family liability insurance",
                             f"We see no family liability insurance. It pays for damage {' or '.join(who)} "
                             f"{'causes' if because == ['pet'] else 'cause'} to others.", because, "family"))
    return gaps, withheld


def _travel(twin, tx, prods):
    trips = _num(fact(twin, "travels"))
    if not trips or trips < FREQUENT_FLYER:
        return []
    return [_gap("travel_cover", "nice-to-have", "Travel cover for your trips",
                 f"You booked {trips:g} flights this year and we see no travel insurance. Travel insurance is not in our "
                 f"catalogue here, so check what your card package or current insurer already covers.",
                 ["travels"], None, sales=False)]


def coverage_review(con, customer_id, twin, *, tx=None):
    """Response body of GET /api/me/coverage-gaps."""
    if not twin:
        return dict(as_of=TODAY.isoformat(), support_first=False, gaps=[], household_prompt=None)
    tx = _tx(con, customer_id, tx)
    prods, stressed = products(twin), support_first(twin)
    family, withheld = _family(twin, tx, prods)
    gaps = [*_car(twin, tx, prods), *_home(twin, tx, prods), *family, *_travel(twin, tx, prods)]
    if stressed:  # help first: only what protects the customer, never a sales line
        gaps = [dict(g, support_first=True, sales=False) for g in gaps if g["severity"] == "essential"]
        withheld = False
    gaps.sort(key=lambda g: SEVERITIES.index(g["severity"]))
    prompt = household_prompt(twin) or (dict(HOUSEHOLD_PROMPT) if withheld else None)
    return dict(as_of=TODAY.isoformat(), support_first=stressed, gaps=gaps, household_prompt=prompt)


def coverage_gaps(con, customer_id, twin, *, tx=None):
    """The gaps only (see coverage_review for the response with support_first and the household prompt)."""
    return coverage_review(con, customer_id, twin, tx=tx)["gaps"]
