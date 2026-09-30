"""Benefits & premiums finder: "you may be entitled to…" hints from the twin, each with its official source.

  benefits(con, customer_id, twin)        -> [hint]  (at most 8)
  benefits_review(con, customer_id, twin) -> {as_of, region, note, benefits, turning_25, household_prompt}
                                             (GET /api/me/benefits)
  turning_25(twin)                        -> the free-youth-account heads-up, or None

Inspired by CommBank's Benefits finder (docs/research/kate_ecosystem_pfa.md §C). Hints are rule-based, never an
eligibility decision: every hint says "check your eligibility", links the official source, and quotes an amount
or rate only where that source states it plainly. Region-aware (Flanders / Wallonia / Brussels from the twin).

Rules and sources (verified by web search on 2026-09-30)
  * child_benefit      children confirmed but no child-benefit inflow in 60 days. Flanders: Groeipakket
                       https://www.groeipakket.be · Wallonia: AViQ https://www.aviq.be/fr/allocations-familiales ·
                       Brussels: Iriscare https://www.iriscare.brussels/fr/citoyens/familles-avec-enfants/informations-generales-pour-vos-allocations-familiales/
  * birth_allowance    a confirmed household change of the last year without a one-off allowance inflow.
                       Flanders: startbedrag https://www.groeipakket.be/en/faq/apply/how-apply-starting-amount-startbedrag ·
                       Wallonia: FAMIWAL https://www.famiwal.be/accedez-aux-themes/naissance-et-adoption/allocation-prime-de-naissance ·
                       Brussels: Iriscare (as above)
  * study_grant        students. Flemish studietoelage https://www.vlaanderen.be/studietoelage (depends on income,
                       household, nationality, age, programme) · French-speaking: Fédération Wallonie-Bruxelles
                       https://allocations-etudes.cfwb.be/ (2026-2027 applications 1 Jul – 31 Oct 2026)
  * train_commute      employees paying a train season ticket themselves: the employer contribution is compulsory
                       whatever the distance (CAO 19/9 as amended by CAO 19/11; FPS Employment)
                       https://werk.belgie.be/nl/themas/verloning/tussenkomst-van-de-werkgever-de-verplaatsingskosten-woon-werkverkeer
  * pension_tax        employed, 18-64, no pension savings: income year 2026 tax reduction of 30% on up to €1,050
                       or 25% on up to €1,350 (Wikifin, FSMA)
                       https://www.wikifin.be/nl/belasting-werk-en-inkomen/belastingaangifte/belastingverminderingen/pensioensparen
  * first_home_duty    Flemish renters with a solid buffer: sales duty on your only own home is 2% instead of the
                       basic 12% (conditions apply) https://www.vlaanderen.be/en/authorities/flemish-taxes/registration-taxes/sales-duty-on-real-estate
  * renovation_premium Flemish owners: Mijn VerbouwPremie still exists in 2026; the reform of 1 Mar 2026 mainly
                       hits owner-occupants in the two highest income categories https://www.vlaanderen.be/premies-voor-renovatie/mijn-verbouwpremie
  * turning_25         KBC Plus Account free until 24 (Jongerenrekening), then €4.25/month; Basic Account
                       €2.50/month (1 debit card, free withdrawals at KBC ATMs only)
                       https://www.kbc.be/particulieren/nl/product/betalen/zichtrekeningen/zichtrekeningen-vergelijken.html

Under money stress, or when the payday plan is already short (free_to_spend < 0, e.g. a self-employed quiet month),
only hints that bring money in without new spending remain (family allowances, study grant, train contribution):
no pension saving, home buying or renovation. No hint is ever a sale (sales=False).

Production-safe behaviour: family hints need the customer's own confirmation of the household change (see
twin/checklists.py); until then they are withheld and the response carries the neutral household_prompt.
"""
from datetime import timedelta

from twin.checklists import (TODAY, confirmed, fact, household_confirmed, household_prompt, HOUSEHOLD_PROMPT,
                             pick, products, recent_event, support_first, _tx)
from twin.recommender import _num

MAX_HINTS = 8
CHECK = "Check your eligibility"
NOTE = "Hints, not a decision: the official source decides whether you're entitled."

FAMILY_FUND = {
    "Flanders": ("Groeipakket (Flemish government)", "https://www.groeipakket.be"),
    "Wallonia": ("AViQ — allocations familiales", "https://www.aviq.be/fr/allocations-familiales"),
    "Brussels": ("Iriscare — allocations familiales",
                 "https://www.iriscare.brussels/fr/citoyens/familles-avec-enfants/informations-generales-pour-vos-allocations-familiales/"),
}
ALLOWANCE = {
    "Flanders": ("Groeipakket — startbedrag", "https://www.groeipakket.be/en/faq/apply/how-apply-starting-amount-startbedrag"),
    "Wallonia": ("FAMIWAL — allocation de naissance",
                 "https://www.famiwal.be/accedez-aux-themes/naissance-et-adoption/allocation-prime-de-naissance"),
    "Brussels": FAMILY_FUND["Brussels"],
}
STUDY_GRANT_NL = ("Studietoelage (Flemish government)", "https://www.vlaanderen.be/studietoelage")
STUDY_GRANT_FR = ("Allocations d'études (Fédération Wallonie-Bruxelles)", "https://allocations-etudes.cfwb.be/")
TRAIN = ("FPS Employment — employer contribution to commuting costs",
         "https://werk.belgie.be/nl/themas/verloning/tussenkomst-van-de-werkgever-de-verplaatsingskosten-woon-werkverkeer")
PENSION = ("Wikifin (FSMA) — pensioensparen",
           "https://www.wikifin.be/nl/belasting-werk-en-inkomen/belastingaangifte/belastingverminderingen/pensioensparen")
FIRST_HOME = ("Flemish Tax Service — sales duty on real estate",
              "https://www.vlaanderen.be/en/authorities/flemish-taxes/registration-taxes/sales-duty-on-real-estate")
RENOVATION = ("Mijn VerbouwPremie (Flemish government)", "https://www.vlaanderen.be/premies-voor-renovatie/mijn-verbouwpremie")
ACCOUNTS = ("KBC — compare current accounts",
            "https://www.kbc.be/particulieren/nl/product/betalen/zichtrekeningen/zichtrekeningen-vergelijken.html")
PLUS_MONTHLY, BASIC_MONTHLY = 4.25, 2.50  # € per month since 1 Jan 2026 (Plus free until 24)


def _hint(hint_id, title, body, source, region, because):
    name, url = source
    return dict(id=hint_id, title=title, body=f"{body} {CHECK}.", check=CHECK, region=region,
                source=url, source_name=name, because=because, topic=None, sales=False)


def _family(twin, tx, region):
    """Production-safe: only with the customer's confirmation of the household change."""
    hints, withheld = [], False
    kids = fact(twin, "children") or fact(twin, "life_event_new_baby") or fact(twin, "childcare")
    if kids and region in FAMILY_FUND and not pick(tx, "child_benefit", after=TODAY - timedelta(days=60)):
        if household_confirmed(twin):
            hints.append(_hint("child_benefit", "Child benefit", "You may be entitled to child benefit, and we don't see "
                               "it coming in. Your region's family-allowance fund handles it.", FAMILY_FUND[region], region,
                               ["children"] if fact(twin, "children") else ["life_event_new_baby"]))
        else:
            withheld = True
    baby, _ = recent_event(twin, "life_event_new_baby", days=365)
    if baby and region in ALLOWANCE and not pick(tx, "birth_allowance"):
        if confirmed(twin, "life_event_new_baby"):
            hints.append(_hint("birth_allowance", "One-off allowance for your little one",
                               "You may be entitled to a one-off allowance for your little one, and we don't see it yet.",
                               ALLOWANCE[region], region, ["life_event_new_baby"]))
        else:
            withheld = True
    return hints, withheld


def _study_grant(twin, region):
    emp, income = fact(twin, "employment"), fact(twin, "income")
    if not ((emp and emp.get("value") == "student") or (income and income.get("kind") == "student")):
        return []
    dutch = region == "Flanders" or (region == "Brussels" and twin.get("language") == "nl")
    if dutch:
        return [_hint("study_grant", "Study grant", "As a student you may be entitled to a Flemish study grant "
                      "(studietoelage); it depends on your household income and situation.", STUDY_GRANT_NL, region, ["employment"])]
    if region in ("Wallonia", "Brussels"):
        return [_hint("study_grant", "Study grant", "As a student you may be entitled to a study grant (allocation "
                      "d'études); applications for 2026-2027 run until 31 Oct 2026.", STUDY_GRANT_FR, region, ["employment"])]
    return []


def _train(twin):
    train, emp = fact(twin, "commutes_by_train"), fact(twin, "employment")
    if not (train and emp and emp.get("value") == "employee"):
        return []
    return [_hint("train_commute", "Train pass: your employer contributes",
                  "You pay your train season ticket from your own account. Employers must contribute to it, whatever "
                  "the distance (national CAO 19/9), and your sector may pay more: ask HR.", TRAIN, "Belgium",
                  ["commutes_by_train", "employment"])]


def _pension(twin, tx):
    emp, age = fact(twin, "employment"), twin.get("age")
    if not (emp and emp.get("value") in ("employee", "self_employed") and isinstance(age, int) and 18 <= age <= 64):
        return []
    if "pension_savings" in products(twin) or pick(tx, "pension_savings"):
        return []
    return [_hint("pension_tax", "Tax reduction on pension savings",
                  "You may be entitled to a tax reduction on pension savings: 30% of up to €1,050 a year, or 25% of up "
                  "to €1,350 (income year 2026).", PENSION, "Belgium", ["employment"])]


def _home(twin, region):
    if region != "Flanders":
        return []
    housing, buffer = fact(twin, "housing"), fact(twin, "financial_buffer")
    tenure = housing.get("value") if housing else None
    out = []
    if tenure == "renting" and (_num(buffer) or 0) >= 3 and (twin.get("age") or 0) >= 18:
        out.append(_hint("first_home_duty", "Buying your first home?",
                         "You rent and have a solid buffer. In Flanders the sales duty on your only own home is 2% "
                         "instead of the basic 12%, if you meet the conditions.", FIRST_HOME, region,
                         ["housing", "financial_buffer"]))
    if tenure in ("owner", "owner_with_mortgage"):
        out.append(_hint("renovation_premium", "Renovation premium (Mijn VerbouwPremie)",
                         "Planning energy works on your home? Mijn VerbouwPremie still exists in 2026; since the reform "
                         "of 1 Mar 2026 owner-occupants in the two highest income categories get less or nothing for many works.",
                         RENOVATION, region, ["housing"]))
    return out


def turning_25(twin):
    """Heads-up for the end of the free youth account at 25 (KBC Plus Account free until 24, then €4.25/month).

    Assumption: every current account in the synthetic data is a KBC Plus Account, so a customer under 25 holds
    the free Jongerenrekening. Twin age = 2026 - birth year: 24 turns 25 next year, 25 turns 25 this year.
    One highlighted option, no hard sell: the cheaper Basic Account unless we see trips abroad."""
    if not twin or twin.get("age") not in (24, 25) or "current_account" not in products(twin):
        return None
    year = TODAY.year + (1 if twin["age"] == 24 else 0)
    when = "next year" if year > TODAY.year else "this year"
    trips = _num(fact(twin, "travels")) or 0
    basic = dict(id="basic_account", name="KBC Basic Account", monthly=BASIC_MONTHLY,
                 summary="1 debit card, free withdrawals at KBC ATMs")
    plus = dict(id="plus_account", name="KBC Plus Account", monthly=PLUS_MONTHLY,
                summary="2 debit cards, free euro withdrawals across Europe, Apple Pay and Google Pay")
    if trips and not support_first(twin):
        chosen, other = plus, basic
        reason = (f"You travel abroad, so the free euro withdrawals across Europe are worth keeping: "
                  f"the Plus Account at €{PLUS_MONTHLY:.2f}/month.")
    else:
        chosen, other = basic, plus
        reason = (f"If one debit card and withdrawals at KBC ATMs are enough for you, the Basic Account costs "
                  f"€{BASIC_MONTHLY:.2f}/month instead of €{PLUS_MONTHLY:.2f}.")
    return dict(kind="turning_25", title="Turning 25: your free account changes", turns_25_in=year,
                body=(f"You turn 25 {when}. From your birthday the free youth account becomes the Plus Account at "
                      f"€{PLUS_MONTHLY:.2f}/month (price since 1 Jan 2026); nothing changes before that."),
                changes=[f"Free until 24, then €{PLUS_MONTHLY:.2f}/month for the Plus Account",
                         f"Or the Basic Account at €{BASIC_MONTHLY:.2f}/month: 1 debit card, free withdrawals at KBC ATMs only"],
                highlight=dict(chosen, reason=reason), alternatives=[other],
                source=ACCOUNTS[1], source_name=ACCOUNTS[0], sales=False)


def benefits_review(con, customer_id, twin, *, tx=None):
    """Response body of GET /api/me/benefits."""
    if not twin:
        return dict(as_of=TODAY.isoformat(), region=None, note=NOTE, benefits=[], turning_25=None, household_prompt=None)
    tx = _tx(con, customer_id, tx)
    region = twin.get("region")
    free = ((twin.get("plan") or {}).get("free_to_spend"))
    tight = support_first(twin) or (isinstance(free, (int, float)) and free < 0)  # money stress or a plan already short
    family, withheld = _family(twin, tx, region)
    hints = [*family, *_study_grant(twin, region), *_train(twin)]
    if not tight:  # nothing that asks for new spending or saving while money is tight
        hints += [*_pension(twin, tx), *_home(twin, region)]
    prompt = household_prompt(twin) or (dict(HOUSEHOLD_PROMPT) if withheld else None)
    return dict(as_of=TODAY.isoformat(), region=region, note=NOTE, benefits=hints[:MAX_HINTS],
                turning_25=turning_25(twin), household_prompt=prompt)


def benefits(con, customer_id, twin, *, tx=None):
    """The hints only (see benefits_review for the full response)."""
    return benefits_review(con, customer_id, twin, tx=tx)["benefits"]
