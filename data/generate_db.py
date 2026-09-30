#!/usr/bin/env python3
"""Generate a synthetic KBC customer database for the digital-twin PoC.

Every customer gets 12 months of realistic Belgian banking activity. Life facts
(owns a car, has a dog, commutes by train, just had a baby, moved house, ...)
are never stored on the customer — they only *show up* as transaction patterns.
The digital twin has to infer them. The ground truth lives in the `truth_*`
tables so we can score how well the twin recovers it; the twin must never read
those tables.

Usage:
    python data/generate_db.py                      # 5000 customers -> data/kbc_twin.db
    python data/generate_db.py --customers 500 --seed 7 --out /tmp/small.db
"""
import argparse
import calendar
import datetime as dt
import random
import sqlite3
from pathlib import Path

START = dt.date(2025, 10, 1)
END = dt.date(2026, 9, 30)
DAY = dt.timedelta(days=1)

# --------------------------------------------------------------------------- reference data

CITIES = {
    "Flanders": [("Gent", "9000"), ("Antwerpen", "2000"), ("Leuven", "3000"), ("Brugge", "8000"),
                 ("Mechelen", "2800"), ("Hasselt", "3500"), ("Kortrijk", "8500"), ("Aalst", "9300"),
                 ("Sint-Niklaas", "9100"), ("Genk", "3600"), ("Roeselare", "8800"), ("Turnhout", "2300")],
    "Wallonia": [("Namur", "5000"), ("Liège", "4000"), ("Charleroi", "6000"), ("Mons", "7000"),
                 ("Wavre", "1300"), ("Louvain-la-Neuve", "1348"), ("Arlon", "6700")],
    "Brussels": [("Brussel", "1000"), ("Etterbeek", "1040"), ("Ixelles", "1050"),
                 ("Schaerbeek", "1030"), ("Anderlecht", "1070"), ("Uccle", "1180")],
}
REGION_WEIGHTS = {"Flanders": 0.72, "Brussels": 0.13, "Wallonia": 0.15}

FIRST_NL_F = ["Lotte", "Emma", "Sofie", "Lien", "Fien", "Marie", "Nora", "Hanne", "Elien", "Julie", "An", "Els", "Katrien", "Liesbeth", "Ine", "Charlotte", "Mila", "Anouk"]
FIRST_NL_M = ["Pieter", "Jens", "Thomas", "Wout", "Arne", "Bram", "Ruben", "Koen", "Tom", "Jan", "Stijn", "Dries", "Lars", "Seppe", "Jef", "Maarten", "Wim", "Robbe"]
FIRST_FR_F = ["Julie", "Camille", "Manon", "Chloé", "Léa", "Sarah", "Amélie", "Laura", "Élise", "Pauline", "Céline", "Aurélie", "Inès", "Louise"]
FIRST_FR_M = ["Julien", "Nicolas", "Maxime", "Antoine", "Hugo", "Thomas", "Lucas", "Mathieu", "Olivier", "Sébastien", "Romain", "Arnaud", "Noah", "Louis"]
FIRST_EN = ["Anna", "Marco", "Elena", "David", "Sara", "Luca", "Maria", "Andrei", "Kasia", "Ahmed", "Yasmine", "Daniel"]
LAST_NL = ["Peeters", "Janssens", "Maes", "Jacobs", "Mertens", "Willems", "Claes", "Goossens", "Wouters", "De Smet", "Vermeulen", "Van den Broeck", "Hermans", "Aerts", "Declercq", "Verstraete", "Desmet", "Lambrechts"]
LAST_FR = ["Dubois", "Lambert", "Dupont", "Martin", "Leclercq", "Simon", "Laurent", "Renard", "Lejeune", "Collard", "Gilson", "Denis", "Delvaux", "François"]
LAST_EN = ["Rossi", "Kowalski", "Popescu", "Garcia", "El Amrani", "Nowak", "Silva", "Fernandes", "Müller", "Schmidt"]

EMPLOYERS = {
    "nl": ["UZ Gent", "Colruyt Group", "Barco", "Proximus", "Deloitte Belgium", "Stad Antwerpen", "Telenet", "Janssen Pharmaceutica", "Umicore", "AB InBev", "Vlaamse Overheid", "KU Leuven", "Bekaert", "Puratos", "VDAB", "AZ Groeninge"],
    "fr": ["UCLouvain", "CHU de Liège", "SPW Wallonie", "Solvay", "ORES", "UCB", "Engie", "Ville de Namur", "Le Forem", "Delhaize Le Lion", "Sonaca"],
    "en": ["European Commission", "NATO", "Deloitte Belgium", "Accenture Belgium", "Toyota Motor Europe", "Euroclear"],
}
CLIENTS_SELF = ["Factuur klant", "Facture client", "Invoice client"]

GROCERIES = {"Flanders": ["Colruyt", "Delhaize", "Aldi", "Lidl", "Carrefour Market", "Albert Heijn", "Okay", "Spar"],
             "Wallonia": ["Colruyt", "Delhaize", "Aldi", "Lidl", "Carrefour", "Intermarché", "Cora"],
             "Brussels": ["Delhaize", "Carrefour Express", "Aldi", "Lidl", "Colruyt", "Proxy Delhaize"]}
FUEL = ["TotalEnergies", "Q8", "Shell", "Esso", "Lukoil", "DATS 24", "Gabriëls"]
EV_CHARGING = ["Allego", "Shell Recharge", "Ionity", "Blue Corner", "Fastned"]
GARAGES = ["Garage Peeters", "D'Ieteren Car Center", "Garage Dubois", "Autocenter Verstraete", "Garage Lambert"]
TYRES = ["Vulco", "Euromaster", "Carglass", "Point S"]
INSPECTION = {"Flanders": "GOCA Autokeuring", "Wallonia": "Autosécurité", "Brussels": "Autocontrole Brussel"}
ROAD_TAX = {"Flanders": "Vlaamse Belastingdienst", "Wallonia": "SPW Fiscalité", "Brussels": "Brussel Fiscaliteit"}
PROPERTY_TAX = ROAD_TAX
INSURERS_OTHER = ["AG Insurance", "Ethias", "Baloise", "P&V", "Allianz Benelux"]
ENERGY = ["Engie", "Luminus", "TotalEnergies Power & Gas", "Eneco", "Mega", "Bolt Energie"]
WATER = {"Flanders": ["De Watergroep", "Farys", "Pidpa", "Water-link"], "Wallonia": ["SWDE", "CILE", "inBW"], "Brussels": ["Vivaqua"]}
TELECOM = ["Proximus", "Telenet", "Orange Belgium", "Mobile Vikings", "Scarlet", "VOO"]
STREAMING = [("Netflix", 13.99), ("Spotify", 11.99), ("Disney+", 8.99), ("Streamz", 12.95), ("Amazon Prime", 6.99),
             ("YouTube Premium", 13.99), ("Apple.com/bill", 2.99), ("HBO Max", 9.99)]
GYMS = [("Basic-Fit", 29.99), ("Jims", 34.99), ("Anytime Fitness", 44.00)]
DINING = ["Exki", "Panos", "Le Pain Quotidien", "Quick", "McDonald's", "Deliveroo", "Uber Eats", "Takeaway.com", "Brasserie Het Anker", "Pizza Hut", "Starbucks", "Brasserie du Marché"]
SHOPPING = ["Bol.com", "Zalando", "Coolblue", "MediaMarkt", "Action", "HEMA", "Primark", "Kruidvat", "Decathlon", "Fnac", "IKEA", "Amazon.com.be", "C&A", "JBC"]
PHARMACY = ["Multipharma", "Apotheek Centrum", "Pharmacie du Centre", "Newpharma"]
MUTUALITY = ["CM - Christelijke Mutualiteit", "Solidaris", "Helan", "Partenamut", "Liberale Mutualiteit"]
DOCTORS = ["Dr. Vermeulen huisarts", "Dr. Martin médecin", "Tandarts De Clercq", "Dentiste Lejeune", "AZ Sint-Jan", "Kinesist Wouters"]
PET_SHOPS = ["Tom&Co", "Maxi Zoo", "Zooplus", "Aveve"]
VETS = ["Dierenarts De Vos", "Clinique Vétérinaire Renard", "Dierenkliniek Noord"]
BABY = ["Dreambaby", "Baby-Dump", "Kruidvat", "Bol.com", "Prénatal"]
CHILDCARE = ["Kinderdagverblijf 't Kapoentje", "Crèche Les Petits Loups", "Kinderopvang Zonnestraal"]
CHILD_BENEFIT = {"Flanders": ["Kidslife", "FONS", "Infino", "MyFamily"], "Wallonia": ["FAMIWAL", "Parentia", "Camille"], "Brussels": ["Famiris", "Parentia", "Brussels Family"]}
TRAVEL_FLIGHTS = ["Ryanair", "Brussels Airlines", "TUI fly", "Transavia"]
TRAVEL_STAY = ["Booking.com", "Airbnb", "Sunweb", "Center Parcs"]
LEISURE = ["Kinepolis", "Ticketmaster", "Sportoase", "Bowling Stones", "Plopsaland", "Standaard Boekhandel", "Club Brugge tickets"]
MOVERS = ["Verhuisfirma Snel", "Déménagements Renard", "Verhuizingen Goossens"]
DIY = ["Gamma", "Brico", "Hubo", "IKEA", "Leenbakker"]
TRAIN = {"Flanders": "NMBS", "Wallonia": "SNCB", "Brussels": "NMBS/SNCB"}
LOCAL_TRANSPORT = {"Flanders": "De Lijn", "Wallonia": "TEC", "Brussels": "STIB-MIVB"}

# KBC product catalogue: code -> (name, monthly amount range or None)
PRODUCTS = {
    "current_account": "KBC Zichtrekening",
    "savings_account": "KBC Spaarrekening",
    "credit_card": "KBC Mastercard",
    "home_loan": "KBC Woonkrediet",
    "car_loan": "KBC Autolening",
    "car_insurance": "KBC Autoverzekering",
    "home_insurance": "KBC Woningverzekering",
    "hospital_insurance": "KBC Hospitalisatieverzekering",
    "pension_savings": "KBC Pensioensparen",
    "investment_plan": "KBC Beleggingsplan",
    "family_insurance": "KBC Familiale Verzekering",
}


def tr(lang, nl, fr, en=None):
    return {"nl": nl, "fr": fr}.get(lang, en or nl)


# --------------------------------------------------------------------------- date helpers

def months():
    y, m = START.year, START.month
    while dt.date(y, m, 1) <= END:
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def dom(y, m, day):
    return dt.date(y, m, min(day, calendar.monthrange(y, m)[1]))


def workday_before(d):
    while d.weekday() >= 5:
        d -= DAY
    return d


def in_window(d, start=START, end=END):
    return start <= d <= end


# --------------------------------------------------------------------------- generator

class CustomerGen:
    def __init__(self, cid, rnd, override=None):
        self.cid = cid
        self.r = rnd
        self.tx = []            # (date, amount, counterparty, description, category, subcategory, channel, account, discretionary)
        self.products = []      # (code, started_at, monthly_amount)
        self.traits = []        # (trait, value, since)
        self.events = []        # (event, date, details)
        self.p = self.make_profile(override or {})

    # ---------------------------------------------------------------- profile
    def make_profile(self, o):
        r = self.r
        region = o.get("region") or r.choices(list(REGION_WEIGHTS), list(REGION_WEIGHTS.values()))[0]
        city, postcode = o.get("city") or r.choice(CITIES[region])
        if region == "Flanders":
            lang = "nl"
        elif region == "Wallonia":
            lang = "fr"
        else:
            lang = r.choices(["fr", "nl", "en"], [0.6, 0.3, 0.1])[0]
        lang = o.get("lang", lang)
        female = r.random() < 0.5
        if lang == "nl":
            first = r.choice(FIRST_NL_F if female else FIRST_NL_M); last = r.choice(LAST_NL)
        elif lang == "fr":
            first = r.choice(FIRST_FR_F if female else FIRST_FR_M); last = r.choice(LAST_FR)
        else:
            first = r.choice(FIRST_EN); last = r.choice(LAST_EN)
        first, last = o.get("first", first), o.get("last", last)

        age = o.get("age") or r.choices([r.randint(18, 24), r.randint(25, 34), r.randint(35, 49), r.randint(50, 64), r.randint(65, 85)],
                                        [12, 20, 27, 22, 19])[0]
        if "employment" in o:
            emp = o["employment"]
        elif age <= 23:
            emp = "student" if r.random() < 0.7 else "employee"
        elif age >= 66:
            emp = "retired"
        else:
            emp = r.choices(["employee", "self_employed", "unemployed"], [80, 13, 7])[0]

        if "household" in o:
            hh = o["household"]
        elif emp == "student":
            hh = "single"
        elif age < 35:
            hh = r.choices(["single", "couple", "family"], [40, 35, 25])[0]
        elif age < 50:
            hh = r.choices(["single", "couple", "family", "single_parent"], [20, 20, 50, 10])[0]
        elif age < 65:
            hh = r.choices(["single", "couple", "family"], [25, 50, 25])[0]
        else:
            hh = r.choices(["single", "couple"], [45, 55])[0]
        kids = o.get("kids")
        if kids is None:
            kids = []
            if hh in ("family", "single_parent"):
                max_kid_age = max(0, min(17, age - 22))
                kids = sorted(r.randint(0, max_kid_age) for _ in range(r.choices([1, 2, 3], [40, 45, 15])[0]))

        if "housing" in o:
            housing = o["housing"]
        elif emp == "student":
            housing = r.choice(["parents", "kot"])
        elif age < 30:
            housing = r.choices(["rent", "mortgage", "parents"], [60, 25, 15])[0]
        elif age < 60:
            housing = r.choices(["rent", "mortgage", "owner"], [30, 55, 15])[0]
        else:
            housing = r.choices(["rent", "mortgage", "owner"], [25, 15, 60])[0]

        car_p = {"student": 0.15, "retired": 0.6}.get(emp, 0.8 if kids else 0.7)
        if region == "Brussels":
            car_p -= 0.25
        has_car = o.get("car", r.random() < car_p)
        car_fuel = o.get("car_fuel", r.choices(["petrol", "diesel", "electric"], [55, 30, 15])[0]) if has_car or o.get("new_car") else None

        return dict(
            region=region, city=city, postcode=postcode, lang=lang, first=first, last=last,
            gender="F" if female else "M", age=age, employment=emp, household=hh, kids=kids, housing=housing,
            has_car=has_car, car_fuel=car_fuel, car_old=r.random() < 0.6,
            pet=o.get("pet", r.choices([None, "dog", "cat"], [75, 13, 12])[0]),
            train=o.get("train", emp == "employee" and r.random() < (0.35 if region == "Brussels" else 0.15)),
            gym=o.get("gym", r.random() < (0.3 if age < 45 else 0.1)),
            saver=o.get("saver", r.random()),
            overspend=o.get("overspend", r.choice([r.uniform(0.75, 0.97), r.uniform(0.9, 1.08)])),
            salary=o.get("salary"), salary_day=o.get("salary_day"), opening_balance=o.get("opening_balance"),
            events=o.get("events"),
        )

    # ---------------------------------------------------------------- helpers
    def add(self, d, amount, cp, desc, cat, sub, channel, account="current", disc=False):
        if in_window(d):
            self.tx.append((d, round(amount, 2), cp, desc, cat, sub, channel, account, disc))

    def rand_date(self, start=START, end=END):
        return start + dt.timedelta(days=self.r.randrange((end - start).days + 1))

    def every(self, mean, jitter, start=START, end=END):
        d = start + dt.timedelta(days=self.r.randrange(max(1, int(mean))))
        while d <= end:
            yield d
            d += dt.timedelta(days=max(1, round(self.r.gauss(mean, jitter))))

    def from_savings(self, d, amount):
        """Move money from savings to current so a big one-off purchase does not overdraw the account."""
        lang = self.p["lang"]
        self.p["savings_topup"] += amount
        self.add(d, amount, tr(lang, "Eigen spaarrekening", "Propre compte épargne", "Own savings account"), tr(lang, "Overschrijving van spaarrekening", "Virement du compte épargne", "Transfer from savings"), "savings", "withdrawal", "internal_transfer")
        self.add(d, -amount, tr(lang, "Eigen zichtrekening", "Propre compte à vue", "Own current account"), tr(lang, "Overschrijving naar zichtrekening", "Virement vers compte à vue", "Transfer to current account"), "savings", "withdrawal", "internal_transfer", account="savings")

    def has_product(self, code):
        return any(p[0] == code for p in self.products)

    # ---------------------------------------------------------------- life timeline
    def build_timeline(self):
        """Turn the profile + sampled life events into dated segments."""
        p, r, lang = self.p, self.r, self.p["lang"]
        emp = p["employment"]
        employer = r.choice(EMPLOYERS["en" if lang == "en" else lang])

        # income segments
        if emp == "employee":
            base = r.uniform(2100, 4300) * (1.15 if p["region"] == "Brussels" else 1)
            inc = [dict(kind="salary", payer=employer, amount=p["salary"] or base, day=p["salary_day"] or r.choice([25, 26, 27, 28, 31]), start=START, end=END)]
        elif emp == "self_employed":
            inc = [dict(kind="self", payer=None, amount=r.uniform(1800, 5500), day=None, start=START, end=END)]
        elif emp == "retired":
            inc = [dict(kind="pension", payer=tr(lang, "Federale Pensioendienst", "Service fédéral des Pensions", "Federal Pension Service"),
                        amount=r.uniform(1400, 2700), day=1, start=START, end=END)]
        elif emp == "unemployed":
            inc = [dict(kind="benefit", payer=tr(lang, "RVA", "ONEM", "RVA/ONEM"), amount=r.uniform(1100, 1650), day=r.randint(3, 8), start=START, end=END)]
        else:
            inc = [dict(kind="student", payer=None, amount=r.uniform(350, 900), day=None, start=START, end=END)]

        p["monthly_income"] = inc[0]["amount"] + (275 if emp == "student" else 0)
        p["savings_topup"] = 0.0

        # housing segments
        h = p["housing"]
        housing = [self.housing_segment(h, START, END)]

        events = p["events"]
        if events is None:
            events = []
            young_parent_age = 25 <= p["age"] <= 42 and p["household"] in ("couple", "family")
            if r.random() < 0.07: events.append(("moved", self.rand_date(), {}))
            if not p["has_car"] and emp != "student" and r.random() < 0.12: events.append(("new_car", self.rand_date(), {}))
            if young_parent_age and r.random() < 0.12: events.append(("new_baby", self.rand_date(), {}))
            if emp == "employee" and r.random() < 0.06: events.append(("new_job", self.rand_date(), {}))
            if emp == "employee" and r.random() < 0.02: events.append(("job_loss", self.rand_date(), {}))
            if emp == "student" and p["age"] >= 21 and r.random() < 0.2: events.append(("first_job", self.rand_date(START + 180 * DAY), {}))
            if p["pet"] is None and r.random() < 0.03: events.append(("got_pet", self.rand_date(), {"pet": r.choice(["dog", "cat"])}))

        p["car_since"] = START - dt.timedelta(days=r.randint(200, 3000)) if p["has_car"] else None
        p["pet_since"] = START - dt.timedelta(days=r.randint(100, 2500)) if p["pet"] else None
        p["baby_date"] = None

        for name, d, det in events:
            if name == "moved":
                old = housing[-1]
                old["end"] = d - DAY
                if det.get("to"):
                    new_kind = det["to"]
                elif old["kind"] in ("parents", "kot") or emp == "student":
                    new_kind = "rent"
                else:
                    new_kind = r.choice(["mortgage", "rent"]) if old["kind"] == "rent" else "rent"
                housing.append(self.housing_segment(new_kind, d, END, bigger=True))
                det = {"from": old["kind"], "to": new_kind}
            elif name == "new_car":
                p["car_since"] = d
                p["car_fuel"] = det.get("fuel") or p["car_fuel"] or r.choices(["petrol", "diesel", "electric"], [55, 25, 20])[0]
                p["car_old"] = det.get("used", r.random() < 0.5)
                det = {"fuel": p["car_fuel"], "used": p["car_old"], "financing": det.get("financing", r.choice(["cash", "loan"])), "price": det.get("price", round(r.uniform(9000, 34000), -2))}
                p["car_purchase"] = det
            elif name == "new_baby":
                p["baby_date"] = d
                if p["household"] == "couple":
                    p["household"] = "family"
            elif name in ("new_job", "first_job"):
                cur = inc[-1]
                cur["end"] = d - DAY
                new_employer = det.get("employer") or r.choice([e for e in EMPLOYERS["en" if lang == "en" else lang] if e != cur.get("payer")])
                amount = det.get("salary") or (cur["amount"] * r.uniform(1.05, 1.25) if name == "new_job" else r.uniform(2050, 2700))
                inc.append(dict(kind="salary", payer=new_employer, amount=amount, day=det.get("day", r.choice([25, 26, 28, 31])), start=d, end=END))
                det = {"employer": new_employer, "net_salary": round(amount)}
                if name == "first_job":
                    p["employment"] = "employee"
            elif name == "job_loss":
                cur = inc[-1]
                cur["end"] = d - DAY
                inc.append(dict(kind="benefit", payer=tr(lang, "RVA", "ONEM", "RVA/ONEM"), amount=min(cur["amount"], 2900) * 0.62,
                                day=r.randint(3, 8), start=d + 30 * DAY, end=END))
                p["employment"] = "unemployed"
            elif name == "got_pet":
                p["pet"] = det["pet"]
                p["pet_since"] = d
            self.events.append((name, d, det))

        p["income"], p["housing_segments"] = inc, housing

    def housing_segment(self, kind, start, end, bigger=False):
        r, lang = self.r, self.p["lang"]
        seg = dict(kind=kind, start=start, end=end, day=r.randint(1, 5))
        income = self.p["monthly_income"]
        if kind == "rent":
            seg.update(amount=min(1700, max(550, income * r.uniform(0.25, 0.38))) * (1.1 if bigger else 1), cp=f"{r.choice(['J.', 'M.', 'A.', 'P.'])} {r.choice(LAST_NL + LAST_FR)}")
        elif kind == "kot":
            seg.update(amount=r.uniform(380, 590), cp=r.choice(["Studentenhuis De Kot", "Kotbaas Vermeulen", "Résidence Étudiante"]))
        elif kind == "mortgage":
            seg.update(amount=min(1800, max(500, income * r.uniform(0.22, 0.35))) * (1.1 if bigger else 1), cp="KBC Woonkrediet")
        else:
            seg.update(amount=0, cp=None)
        return seg

    # ---------------------------------------------------------------- transaction builders
    def gen_income(self):
        p, r, lang = self.p, self.r, self.p["lang"]
        for seg in p["income"]:
            for y, m in months():
                if seg["kind"] == "salary":
                    d = workday_before(dom(y, m, seg["day"]))
                    if in_window(d, seg["start"], seg["end"]):
                        self.add(d, seg["amount"] * r.uniform(0.99, 1.01), seg["payer"], tr(lang, f"Loon {m:02d}/{y}", f"Salaire {m:02d}/{y}", f"Salary {m:02d}/{y}"), "income", "salary", "incoming_transfer")
                    if m == 5 and in_window(dom(y, 5, 28), seg["start"], seg["end"]):
                        self.add(workday_before(dom(y, 5, 28)), seg["amount"] * 0.92, seg["payer"], tr(lang, "Vakantiegeld", "Pécule de vacances", "Holiday pay"), "income", "holiday_pay", "incoming_transfer")
                    if m == 12 and in_window(dom(y, 12, 20), seg["start"], seg["end"]):
                        self.add(workday_before(dom(y, 12, 20)), seg["amount"] * 0.9, seg["payer"], tr(lang, "Eindejaarspremie", "Prime de fin d'année", "End-of-year bonus"), "income", "bonus", "incoming_transfer")
                elif seg["kind"] in ("pension", "benefit"):
                    d = dom(y, m, seg["day"])
                    if in_window(d, seg["start"], seg["end"]):
                        self.add(d, seg["amount"], seg["payer"], tr(lang, f"Uitkering {m:02d}/{y}", f"Allocation {m:02d}/{y}", f"Benefit {m:02d}/{y}"), "income", seg["kind"], "incoming_transfer")
                elif seg["kind"] == "self":
                    for _ in range(r.randint(1, 4)):
                        d = dom(y, m, r.randint(1, 28))
                        if in_window(d, seg["start"], seg["end"]):
                            self.add(d, seg["amount"] / 2.5 * r.uniform(0.4, 1.8), f"{r.choice(['BV', 'SRL', 'NV'])} {r.choice(LAST_NL + LAST_FR)}", r.choice(CLIENTS_SELF) + f" {r.randint(100, 999)}", "income", "invoice", "incoming_transfer")
                    d = dom(y, m, 20)
                    if m in (1, 4, 7, 10) and in_window(d, seg["start"], seg["end"]):
                        self.add(d, -seg["amount"] * 0.2, "Xerius Sociaal Verzekeringsfonds", tr(lang, "Sociale bijdragen", "Cotisations sociales", "Social contributions"), "taxes", "social_contributions", "direct_debit")
                else:  # student
                    d = dom(y, m, r.randint(1, 10))
                    if in_window(d, seg["start"], seg["end"]):
                        self.add(d, r.uniform(150, 400), tr(lang, "Ouders", "Parents", "Parents"), tr(lang, "Zakgeld", "Argent de poche", "Allowance"), "income", "family_transfer", "incoming_transfer")
                        if r.random() < 0.7:
                            self.add(dom(y, m, r.randint(20, 28)), seg["amount"] * r.uniform(0.3, 1.2), r.choice(["Randstad", "Start People", "Tempo-Team"]), tr(lang, "Studentenjob", "Job étudiant", "Student job"), "income", "student_job", "incoming_transfer")

        # income tax settlement (June–September)
        if p["employment"] != "student" and r.random() < 0.8:
            d = self.rand_date(dt.date(2026, 6, 15), dt.date(2026, 9, 25))
            amt = r.uniform(150, 1400) if r.random() < 0.7 else -r.uniform(100, 1800)
            self.add(d, amt, tr(lang, "FOD Financiën", "SPF Finances", "FPS Finance"), tr(lang, "Aanslagbiljet personenbelasting", "Avertissement-extrait de rôle IPP", "Income tax assessment"), "taxes", "income_tax", "incoming_transfer" if amt > 0 else "sepa_transfer")

    def gen_housing(self):
        p, r, lang = self.p, self.r, self.p["lang"]
        region = p["region"]
        for i, seg in enumerate(p["housing_segments"]):
            kind = seg["kind"]
            for y, m in months():
                d = dom(y, m, seg["day"])
                if not in_window(d, seg["start"], seg["end"]):
                    continue
                if kind in ("rent", "kot"):
                    self.add(d, -seg["amount"], seg["cp"], tr(lang, f"Huur {m:02d}/{y}", f"Loyer {m:02d}/{y}", f"Rent {m:02d}/{y}"), "housing", "rent", "sepa_transfer")
                elif kind == "mortgage":
                    self.add(d, -seg["amount"], seg["cp"], tr(lang, "Aflossing woonkrediet", "Remboursement crédit hypothécaire", "Mortgage repayment"), "housing", "mortgage", "direct_debit")
            if kind == "mortgage" and not self.has_product("home_loan"):
                self.products.append(("home_loan", seg["start"] if seg["start"] > START else START - dt.timedelta(days=r.randint(300, 6000)), round(seg["amount"], 2)))
            if kind in ("mortgage", "owner"):
                d = self.rand_date(dt.date(2026, 6, 1), dt.date(2026, 9, 20))
                if in_window(d, seg["start"], seg["end"]):
                    self.add(d, -r.uniform(550, 1600), PROPERTY_TAX[region], tr(lang, "Onroerende voorheffing", "Précompte immobilier", "Property tax"), "taxes", "property_tax", "sepa_transfer")

            # utilities for independent households
            if kind in ("rent", "mortgage", "owner"):
                energy = r.choice(ENERGY)
                adv = r.uniform(85, 230) * (1.4 if p["car_fuel"] == "electric" else 1) * (1 + 0.15 * len(p["kids"]))
                eday = r.randint(10, 20)
                for y, m in months():
                    d = dom(y, m, eday)
                    if in_window(d, seg["start"], seg["end"]):
                        self.add(d, -adv, energy, tr(lang, "Voorschot energie", "Acompte énergie", "Energy advance"), "utilities", "energy", "direct_debit")
                settle = self.rand_date(seg["start"], seg["end"]) if seg["end"] > seg["start"] + 60 * DAY else seg["end"]
                self.add(settle, r.uniform(-450, 280), energy, tr(lang, "Jaarafrekening energie", "Décompte annuel énergie", "Annual energy settlement"), "utilities", "energy", "direct_debit")
                water = r.choice(WATER[region])
                for d in self.every(91, 5, seg["start"], seg["end"]):
                    self.add(d, -r.uniform(55, 140), water, tr(lang, "Voorschot water", "Acompte eau", "Water advance"), "utilities", "water", "direct_debit")
                if i > 0:  # a move: movers + furniture + DIY
                    s = seg["start"]
                    self.add(s - 2 * DAY, -r.uniform(450, 1400), r.choice(MOVERS), tr(lang, "Verhuis", "Déménagement", "Moving"), "housing", "moving", "sepa_transfer")
                    for _ in range(r.randint(2, 5)):
                        self.add(s + dt.timedelta(days=r.randint(-10, 40)), -r.uniform(60, 900), r.choice(DIY), r.choice(DIY), "housing", "furniture_diy", "card")
                    self.add(s + dt.timedelta(days=r.randint(1, 20)), -r.uniform(80, 250), "bpost", tr(lang, "Adreswijziging/doorsturen post", "Réexpédition courrier", "Mail forwarding"), "housing", "moving", "card")
                    if kind == "mortgage":
                        fees = round(r.uniform(9000, 22000), 2)
                        self.from_savings(s - 6 * DAY, fees)
                        self.add(s - 5 * DAY, -fees, f"Notaris {r.choice(LAST_NL + LAST_FR)}", tr(lang, "Aktekosten aankoop woning", "Frais d'acte achat immobilier", "Notary fees home purchase"), "housing", "notary", "sepa_transfer")

        # telecom (everyone), home insurance
        tele = r.choice(TELECOM)
        tday = r.randint(5, 25)
        tamt = r.uniform(15, 30) if p["housing"] in ("kot", "parents") else r.uniform(45, 110)
        for y, m in months():
            self.add(dom(y, m, tday), -tamt, tele, tr(lang, "Factuur", "Facture", "Invoice") + f" {m:02d}/{y}", "utilities", "telecom", "direct_debit")
        if p["housing"] in ("rent", "mortgage", "owner") or any(s["kind"] in ("rent", "mortgage") for s in p["housing_segments"]):
            if r.random() < 0.5:
                prem = r.uniform(18, 45)
                self.products.append(("home_insurance", START - dt.timedelta(days=r.randint(100, 3000)), round(prem, 2)))
                for y, m in months():
                    self.add(dom(y, m, 2), -prem, "KBC Verzekeringen", PRODUCTS["home_insurance"], "insurance", "home", "direct_debit")
            else:
                self.add(self.rand_date(), -r.uniform(220, 520), r.choice(INSURERS_OTHER), tr(lang, "Brandverzekering jaarpremie", "Assurance incendie prime annuelle", "Home insurance annual premium"), "insurance", "home", "sepa_transfer")

    def gen_car(self):
        p, r, lang = self.p, self.r, self.p["lang"]
        since = p["car_since"]
        if not since:
            return
        region, start = p["region"], max(since, START)
        purchase = p.get("car_purchase")
        if purchase:
            dealer = r.choice(["D'Ieteren Car Center", "Autohandel De Smet", "Garage Lambert", "Tesla Belgium" if p["car_fuel"] == "electric" else "Toyota Center Gent"])
            if purchase["financing"] == "loan":
                monthly = purchase["price"] / 60 * 1.06
                self.products.append(("car_loan", since, round(monthly, 2)))
                self.from_savings(since - DAY, round(purchase["price"] * 0.15, 2))
                self.add(since, -purchase["price"] * 0.15, dealer, tr(lang, "Voorschot wagen", "Acompte véhicule", "Car down payment"), "transport", "car_purchase", "sepa_transfer")
                for y, m in months():
                    d = dom(y, m, 5)
                    if d > since:
                        self.add(d, -monthly, "KBC Autolening", PRODUCTS["car_loan"], "transport", "car_loan", "direct_debit")
            else:
                self.from_savings(since - DAY, purchase["price"])
                self.add(since, -purchase["price"], dealer, tr(lang, "Aankoop wagen", "Achat véhicule", "Car purchase"), "transport", "car_purchase", "sepa_transfer")
            self.add(since + dt.timedelta(days=r.randint(0, 3)), -r.uniform(40, 90), "DIV - Inschrijving voertuigen", tr(lang, "Nummerplaat", "Plaque d'immatriculation", "Licence plate"), "transport", "registration", "card")
            if region == "Flanders":
                self.add(since + dt.timedelta(days=r.randint(20, 45)), -r.uniform(0, 2) if p["car_fuel"] == "electric" else -r.uniform(90, 900), ROAD_TAX[region], "Belasting op inverkeerstelling", "taxes", "registration_tax", "sepa_transfer")

        # energy for the car
        if p["car_fuel"] == "electric":
            for d in self.every(9, 4, start):
                self.add(d, -r.uniform(12, 38), r.choice(EV_CHARGING), "EV charging", "transport", "ev_charging", "card")
        else:
            fav = r.sample(FUEL, 2)
            for d in self.every(12, 4, start):
                self.add(d, -r.uniform(45, 88), r.choice(fav) if r.random() < 0.8 else r.choice(FUEL), tr(lang, "Tankstation", "Station-service", "Fuel station"), "transport", "fuel", "card")
        # parking via KBC Mobile (4411) and city parking
        for d in self.every(r.choice([7, 14, 30]), 4, start):
            self.add(d, -r.uniform(1.5, 12), r.choice(["4411", "4411", "Interparking", "Q-Park"]), "Parking", "transport", "parking", "card", disc=True)
        # maintenance & tyres (irregular, never budgeted)
        if since < START or r.random() < 0.3:
            for _ in range(r.choice([1, 1, 2])):
                self.add(self.rand_date(start), -r.uniform(180, 720), r.choice(GARAGES), tr(lang, "Onderhoud wagen", "Entretien véhicule", "Car service"), "transport", "maintenance", "card")
        if r.random() < 0.35:
            self.add(self.rand_date(start), -r.uniform(280, 750), r.choice(TYRES), tr(lang, "Banden", "Pneus", "Tyres"), "transport", "maintenance", "card")
        if p["car_old"] and since < START:
            self.add(self.rand_date(start), -r.uniform(42, 60), INSPECTION[region], tr(lang, "Technische keuring", "Contrôle technique", "Vehicle inspection"), "transport", "inspection", "card")
        # yearly road tax (EVs exempt/low in Flanders)
        if since < START:
            self.add(self.rand_date(), -(r.uniform(0, 90) if p["car_fuel"] == "electric" else r.uniform(120, 520)), ROAD_TAX[region], tr(lang, "Verkeersbelasting", "Taxe de circulation", "Road tax"), "taxes", "road_tax", "sepa_transfer")
        # insurance: KBC or a competitor (competitor = cross-sell opportunity)
        if r.random() < 0.4 and not purchase:
            prem = r.uniform(38, 95)
            self.products.append(("car_insurance", since, round(prem, 2)))
            for y, m in months():
                d = dom(y, m, 3)
                if d >= start:
                    self.add(d, -prem, "KBC Verzekeringen", PRODUCTS["car_insurance"], "insurance", "car", "direct_debit")
        else:
            insurer = r.choice(INSURERS_OTHER)
            if purchase or r.random() < 0.5:
                prem = r.uniform(45, 105)
                for y, m in months():
                    d = dom(y, m, 8)
                    if d >= start + 3 * DAY:
                        self.add(d, -prem, insurer, tr(lang, "Autoverzekering maandpremie", "Assurance auto prime mensuelle", "Car insurance monthly premium"), "insurance", "car", "direct_debit")
            else:
                self.add(self.rand_date(start), -r.uniform(480, 1150), insurer, tr(lang, "Autoverzekering jaarpremie", "Assurance auto prime annuelle", "Car insurance annual premium"), "insurance", "car", "sepa_transfer")

    def gen_family(self):
        p, r, lang = self.p, self.r, self.p["lang"]
        region = p["region"]
        kids = list(p["kids"])
        benefit_payer = r.choice(CHILD_BENEFIT[region])
        for y, m in months():
            month_start = dt.date(y, m, 1)
            n = len(kids) + (1 if p["baby_date"] and p["baby_date"] < month_start else 0)
            if n:
                self.add(dom(y, m, r.randint(8, 12)), 175 * n * r.uniform(0.95, 1.1), benefit_payer, tr(lang, "Groeipakket", "Allocations familiales", "Child benefit"), "income", "child_benefit", "incoming_transfer")
            for age in kids:
                if age < 3:
                    self.add(dom(y, m, 3), -r.uniform(380, 650), r.choice(CHILDCARE), tr(lang, "Kinderopvang", "Crèche", "Childcare"), "family", "childcare", "sepa_transfer")
                elif age <= 17 and m != 7 and m != 8:
                    self.add(dom(y, m, r.randint(10, 25)), -r.uniform(20, 90) * (2.5 if m == 9 else 1), tr(lang, "Basisschool De Regenboog", "École communale", "School"), tr(lang, "Schoolrekening", "Frais scolaires", "School bill"), "family", "school", "sepa_transfer")
            if kids and r.random() < 0.6:
                self.add(dom(y, m, r.randint(1, 28)), -r.uniform(25, 120), r.choice(["JBC", "Zeeman", "Decathlon", "Dreamland", "Fun"]), "Kids", "family", "kids_shopping", "card", disc=True)
        bd = p["baby_date"]
        if bd:
            for _ in range(r.randint(4, 8)):  # preparing for the baby
                self.add(bd - dt.timedelta(days=r.randint(10, 120)), -r.uniform(40, 650), r.choice(BABY), tr(lang, "Babyuitzet", "Articles bébé", "Baby gear"), "family", "baby", "card")
            self.add(bd + dt.timedelta(days=r.randint(1, 3)), -r.uniform(300, 1200), r.choice(["AZ Sint-Jan", "UZ Leuven", "CHU UCL Namur", "Ziekenhuis Oost-Limburg"]), tr(lang, "Ziekenhuisfactuur bevalling", "Facture hôpital accouchement", "Hospital bill delivery"), "health", "hospital", "sepa_transfer")
            self.add(bd + dt.timedelta(days=r.randint(20, 45)), r.uniform(1100, 1250), benefit_payer, tr(lang, "Startbedrag Groeipakket", "Prime de naissance", "Birth allowance"), "income", "birth_allowance", "incoming_transfer")
            for d in self.every(9, 3, bd):
                self.add(d, -r.uniform(18, 55), r.choice(["Kruidvat", "Di", "Delhaize", "Bol.com"]), tr(lang, "Luiers & verzorging", "Couches & soins", "Diapers & care"), "family", "baby", "card")
            care_start = bd + dt.timedelta(days=r.randint(90, 150))
            for y, m in months():
                d = dom(y, m, 3)
                if d >= care_start:
                    self.add(d, -r.uniform(380, 650), r.choice(CHILDCARE), tr(lang, "Kinderopvang", "Crèche", "Childcare"), "family", "childcare", "sepa_transfer")

    def gen_pet(self):
        p, r, lang = self.p, self.r, self.p["lang"]
        if not p["pet"]:
            return
        start = max(p["pet_since"], START)
        if p["pet_since"] >= START:
            self.add(start, -r.uniform(80, 450), r.choice(["Dierenasiel Gent", "Refuge SRPA", "Vives Kennel"]), tr(lang, "Adoptie", "Adoption", "Adoption"), "pets", "adoption", "sepa_transfer")
        shop = r.choice(PET_SHOPS)
        food = r.uniform(35, 85) if p["pet"] == "dog" else r.uniform(20, 50)
        for d in self.every(28, 6, start):
            self.add(d, -food * r.uniform(0.8, 1.2), shop, tr(lang, "Dierenvoeding", "Nourriture animaux", "Pet food"), "pets", "pet_food", "card")
        for _ in range(r.randint(1, 3)):
            self.add(self.rand_date(start), -r.uniform(45, 320), r.choice(VETS), tr(lang, "Consultatie dierenarts", "Consultation vétérinaire", "Vet visit"), "pets", "vet", "card")

    def gen_lifestyle(self):
        p, r, lang = self.p, self.r, self.p["lang"]
        region = p["region"]
        size = {"single": 1, "couple": 2}.get(p["household"], 2) + len(p["kids"]) * 0.6
        # groceries
        fav = r.sample(GROCERIES[region], 2)
        per_visit = r.uniform(22, 55) * size ** 0.8
        for d in self.every(r.choice([3, 4, 5, 7]), 1.5):
            self.add(d, -per_visit * r.uniform(0.5, 1.6), r.choice(fav) if r.random() < 0.8 else r.choice(GROCERIES[region]), p["city"], "groceries", "supermarket", "card", disc=True)
        # subscriptions
        for name, price in r.sample(STREAMING, r.choices([0, 1, 2, 3, 4], [15, 30, 30, 18, 7])[0]):
            sday = r.randint(1, 28)
            for y, m in months():
                self.add(dom(y, m, sday), -price, name, name, "subscriptions", "streaming", "card")
        if p["gym"]:
            gname, gprice = r.choice(GYMS)
            for d in self.every(28, 0):
                self.add(d, -gprice, gname, gname, "leisure", "gym", "direct_debit")
        # health
        mut = r.choice(MUTUALITY)
        self.add(self.rand_date(START, dt.date(2026, 1, 31)), -r.uniform(40, 130) * size, mut, tr(lang, "Ledenbijdrage", "Cotisation annuelle", "Membership fee"), "health", "mutuality", "direct_debit")
        for d in self.every(24 if p["age"] < 60 else 12, 8):
            self.add(d, -r.uniform(6, 60), r.choice(PHARMACY), tr(lang, "Apotheek", "Pharmacie", "Pharmacy"), "health", "pharmacy", "card")
        for d in self.every(60 if p["age"] < 60 else 30, 20):
            fee = r.uniform(30, 90)
            self.add(d, -fee, r.choice(DOCTORS), tr(lang, "Consultatie", "Consultation", "Consultation"), "health", "doctor", "card")
            self.add(d + dt.timedelta(days=r.randint(5, 20)), fee * r.uniform(0.55, 0.75), mut, tr(lang, "Terugbetaling", "Remboursement", "Reimbursement"), "health", "reimbursement", "incoming_transfer")
        # commuting
        if p["train"]:
            pass_price, pass_day = r.uniform(75, 190), r.randint(1, 3)
            for y, m in months():
                if m != 8:
                    self.add(dom(y, m, pass_day), -pass_price, TRAIN[region], tr(lang, "Treinabonnement", "Abonnement train", "Train pass"), "transport", "public_transport", "card")
        for d in self.every(r.choice([10, 21, 45]), 5):
            self.add(d, -r.uniform(2.5, 25), r.choice([LOCAL_TRANSPORT[region], TRAIN[region]]), "Ticket", "transport", "public_transport", "card", disc=True)
        # discretionary
        dining_freq = 5 if p["age"] < 35 else 9 if p["age"] < 60 else 16
        for d in self.every(dining_freq, 3):
            place = r.choice(DINING)
            self.add(d, -r.uniform(8, 75), place, place, "dining", "restaurant_takeaway", "card", disc=True)
        for d in self.every(9, 4):
            self.add(d, -r.uniform(12, 180), r.choice(SHOPPING), "Online/retail", "shopping", "general", "card", disc=True)
        for d in self.every(r.choice([14, 30]), 7):
            self.add(d, -r.uniform(10, 90), r.choice(LEISURE), "Leisure", "leisure", "outing", "card", disc=True)
        for d in self.every(r.choice([14, 30, 60]), 7):
            self.add(d, -r.choice([20, 40, 50, 100]), tr(lang, "Geldautomaat KBC", "Distributeur CBC", "ATM"), tr(lang, "Geldopname", "Retrait", "Cash withdrawal"), "cash", "atm", "atm", disc=True)
        for _ in range(r.choices([0, 1, 2, 3], [20, 40, 30, 10])[0]):
            trip = self.rand_date()
            self.add(trip - dt.timedelta(days=r.randint(20, 90)), -r.uniform(90, 450) * size, r.choice(TRAVEL_FLIGHTS), tr(lang, "Vliegtickets", "Billets d'avion", "Flights"), "travel", "flights", "card", disc=True)
            self.add(trip - dt.timedelta(days=r.randint(10, 60)), -r.uniform(250, 1400) * size ** 0.7, r.choice(TRAVEL_STAY), tr(lang, "Verblijf", "Séjour", "Stay"), "travel", "accommodation", "card", disc=True)

    def gen_kbc_products(self):
        p, r, lang = self.p, self.r, self.p["lang"]
        self.products.append(("current_account", START - dt.timedelta(days=r.randint(200, 9000)), None))
        if p["age"] >= 25 and p["employment"] != "student":
            if r.random() < 0.35:
                self.products.append(("pension_savings", START - dt.timedelta(days=r.randint(200, 6000)), 85.0))
                for y, m in months():
                    self.add(dom(y, m, 15), -85.0, "KBC Pensioensparen", PRODUCTS["pension_savings"], "savings", "pension_savings", "direct_debit")
            if r.random() < 0.3:
                self.products.append(("hospital_insurance", START - dt.timedelta(days=r.randint(200, 6000)), None))
                self.add(self.rand_date(), -r.uniform(90, 480), "KBC Verzekeringen", PRODUCTS["hospital_insurance"], "insurance", "health", "direct_debit")
            if r.random() < 0.18:
                amt = r.choice([50, 75, 100, 150, 250])
                self.products.append(("investment_plan", START - dt.timedelta(days=r.randint(100, 3000)), float(amt)))
                for y, m in months():
                    self.add(dom(y, m, 20), -amt, "KBC Beleggingsplan", PRODUCTS["investment_plan"], "savings", "investment", "direct_debit")
            if r.random() < 0.4:
                self.products.append(("family_insurance", START - dt.timedelta(days=r.randint(100, 5000)), None))
                self.add(self.rand_date(), -r.uniform(70, 160), "KBC Verzekeringen", PRODUCTS["family_insurance"], "insurance", "liability", "direct_debit")
        if r.random() < 0.4 and p["employment"] != "student":
            self.products.append(("credit_card", START - dt.timedelta(days=r.randint(100, 5000)), None))

    def gen_savings(self, fixed_out, income_in):
        """Monthly 'pay yourself first' transfer for savers, sized on what is left over."""
        p, r, lang = self.p, self.r, self.p["lang"]
        leftover = (income_in - fixed_out) / 12
        if p["saver"] < 0.35 or leftover < 150:
            return 0.0
        amt = round(leftover * r.uniform(0.08, 0.25) / 25) * 25
        if amt <= 0:
            return 0.0
        sday = r.randint(1, 3)
        salary = p["income"][0]
        for y, m in months():
            if salary.get("day"):
                d = workday_before(dom(y, m, salary["day"])) + DAY  # the day after salary lands
            else:
                d = dom(y, m, sday)
            self.add(d, -amt, tr(lang, "Eigen spaarrekening", "Propre compte épargne", "Own savings account"), tr(lang, "Maandelijks sparen", "Épargne mensuelle", "Monthly savings"), "savings", "transfer_to_savings", "internal_transfer")
            self.add(d, amt, tr(lang, "Eigen zichtrekening", "Propre compte à vue", "Own current account"), tr(lang, "Maandelijks sparen", "Épargne mensuelle", "Monthly savings"), "savings", "transfer_to_savings", "internal_transfer", account="savings")
        return amt * 12

    # ---------------------------------------------------------------- orchestrate
    def generate(self):
        self.build_timeline()
        self.gen_income()
        self.gen_housing()
        self.gen_car()
        self.gen_family()
        self.gen_pet()
        self.gen_lifestyle()
        self.gen_kbc_products()

        cur = [t for t in self.tx if t[7] == "current" and t[6] != "internal_transfer"]
        income_in = sum(t[1] for t in cur if t[1] > 0) + self.p["savings_topup"]  # big buys funded from savings
        fixed_out = -sum(t[1] for t in cur if t[1] < 0 and not t[8])
        disc_out = -sum(t[1] for t in cur if t[1] < 0 and t[8])
        saved = self.gen_savings(fixed_out, income_in)

        # scale discretionary spending so the year roughly balances (some customers overspend -> money stress)
        target = max(0.08 * income_in, (income_in - fixed_out - saved) * self.p["overspend"])
        if disc_out > 0:
            k = max(0.2, min(4.0, target / disc_out))
            self.tx = [t[:1] + (round(t[1] * k, 2),) + t[2:] if t[8] else t for t in self.tx]
        if saved and not self.has_product("savings_account"):
            self.products.append(("savings_account", START - dt.timedelta(days=self.r.randint(100, 6000)), None))
        elif self.r.random() < 0.5 and not self.has_product("savings_account"):
            self.products.append(("savings_account", START - dt.timedelta(days=self.r.randint(100, 6000)), None))
        if self.p["savings_topup"] and not self.has_product("savings_account"):
            self.products.append(("savings_account", START - dt.timedelta(days=500), None))

        self.tx.sort(key=lambda t: (t[0], -t[1]))
        self.build_truth()
        return self

    def build_truth(self):
        p = self.p
        add = self.traits.append
        add(("employment", p["employment"], None))
        add(("household", p["household"], None))
        add(("children", str(len(p["kids"]) + (1 if p["baby_date"] else 0)), None))
        add(("housing", p["housing_segments"][-1]["kind"], p["housing_segments"][-1]["start"]))
        add(("has_car", "true" if p["car_since"] else "false", p["car_since"]))
        if p["car_since"]:
            add(("car_fuel", p["car_fuel"], p["car_since"]))
            has_kbc = self.has_product("car_insurance")
            add(("car_insured_at", "KBC" if has_kbc else "competitor", None))
        add(("pet", p["pet"] or "none", p["pet_since"]))
        add(("commutes_by_train", "true" if p["train"] else "false", None))
        add(("gym_member", "true" if p["gym"] else "false", None))
        add(("saver", "true" if any(t[5] == "transfer_to_savings" for t in self.tx) else "false", None))


# --------------------------------------------------------------------------- demo personas

DEMO_PERSONAS = [
    # 1. Lotte — bought a (used, petrol) car in June 2026; insured elsewhere; no car buffer. Salary on the 25th.
    dict(first="Lotte", last="Peeters", age=29, region="Flanders", city=("Gent", "9000"), lang="nl", employment="employee",
         household="single", kids=[], housing="rent", car=False, car_fuel="petrol", pet=None, train=False, gym=True,
         saver=0.9, overspend=0.99, salary=2850, salary_day=25, opening_balance=1450,
         events=[("new_car", dt.date(2026, 6, 13), {"fuel": "petrol", "financing": "cash", "price": 11500, "used": True})]),
    # 2. Julien — expecting & now has a baby (born 2026-07-18), owns a diesel car, has a dog, mortgage at KBC.
    dict(first="Julien", last="Dubois", age=34, region="Wallonia", city=("Namur", "5000"), lang="fr", employment="employee",
         household="couple", kids=[], housing="mortgage", car=True, car_fuel="diesel", pet="dog", train=False, gym=False,
         saver=0.6, overspend=1.0, events=[("new_baby", dt.date(2026, 7, 18), {})]),
    # 3. Emma — student in Leuven, landed her first job at Deloitte (first salary Sept 2026), moved out of her kot.
    dict(first="Emma", last="Claes", age=23, region="Flanders", city=("Leuven", "3000"), lang="nl", employment="student",
         household="single", kids=[], housing="kot", car=False, pet=None, train=True, gym=True, saver=0.1, overspend=0.95,
         events=[("first_job", dt.date(2026, 9, 1), {"employer": "Deloitte Belgium", "salary": 2380, "day": 26}),
                 ("moved", dt.date(2026, 8, 20), {"to": "rent"})]),
    # 4. Marc — self-employed, irregular income, money stress: spends slightly more than he earns.
    dict(first="Marc", last="Wouters", age=47, region="Flanders", city=("Antwerpen", "2000"), lang="nl", employment="self_employed",
         household="family", kids=[9, 13], housing="mortgage", car=True, car_fuel="electric", pet="cat", train=False, gym=False,
         saver=0.1, overspend=1.12, events=[]),
]


# --------------------------------------------------------------------------- DB

SCHEMA = """
CREATE TABLE customers (
    customer_id     INTEGER PRIMARY KEY,
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    gender          TEXT,
    birth_year      INTEGER,
    language        TEXT,          -- nl / fr / en
    region          TEXT,          -- Flanders / Wallonia / Brussels
    city            TEXT,
    postcode        TEXT,
    customer_since  DATE,
    is_demo_persona INTEGER DEFAULT 0
);
CREATE TABLE accounts (
    account_id  INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    type        TEXT NOT NULL,     -- current / savings
    iban        TEXT UNIQUE,
    opened_at   DATE,
    balance     REAL
);
CREATE TABLE transactions (
    tx_id         INTEGER PRIMARY KEY,
    account_id    INTEGER NOT NULL REFERENCES accounts(account_id),
    customer_id   INTEGER NOT NULL REFERENCES customers(customer_id),
    booked_at     DATE NOT NULL,
    amount        REAL NOT NULL,   -- negative = money out
    currency      TEXT DEFAULT 'EUR',
    counterparty  TEXT,
    description   TEXT,
    category      TEXT,            -- KBC-style categorisation (already exists at KBC)
    subcategory   TEXT,
    channel       TEXT,            -- card / direct_debit / sepa_transfer / incoming_transfer / internal_transfer / atm
    balance_after REAL
);
CREATE TABLE products (
    customer_id    INTEGER NOT NULL REFERENCES customers(customer_id),
    product_code   TEXT NOT NULL,
    product_name   TEXT NOT NULL,
    started_at     DATE,
    monthly_amount REAL,
    PRIMARY KEY (customer_id, product_code)
);
-- Ground truth. For evaluating the twin ONLY — the twin must never read these.
CREATE TABLE truth_traits (
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    trait       TEXT NOT NULL,
    value       TEXT,
    since       DATE
);
CREATE TABLE truth_events (
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    event       TEXT NOT NULL,
    event_date  DATE,
    details     TEXT
);
CREATE INDEX idx_tx_customer_date ON transactions(customer_id, booked_at);
CREATE INDEX idx_tx_category ON transactions(category, subcategory);
"""


def iban(rnd):
    return f"BE{rnd.randint(10, 99)} 7{rnd.randint(100, 999)} {rnd.randint(1000, 9999)} {rnd.randint(1000, 9999)}"


def build(n_customers, seed, out):
    import json
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    con = sqlite3.connect(out)
    con.executescript(SCHEMA)
    rnd = random.Random(seed)
    account_id = 0
    tx_rows, n_tx = [], 0

    for cid in range(1, n_customers + 1):
        override = DEMO_PERSONAS[cid - 1] if cid <= len(DEMO_PERSONAS) else None
        g = CustomerGen(cid, random.Random(rnd.random()), override).generate()
        p = g.p
        since = min(pr[1] for pr in g.products)
        con.execute("INSERT INTO customers VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (cid, p["first"], p["last"], p["gender"], END.year - p["age"], p["lang"], p["region"], p["city"], p["postcode"],
                     since.isoformat(), 1 if override else 0))

        balances = {}
        acc_ids = {}
        for acc_type in ("current", "savings"):
            if acc_type == "savings" and not g.has_product("savings_account"):
                continue
            account_id += 1
            acc_ids[acc_type] = account_id
            if acc_type == "current":
                balances[acc_type] = p["opening_balance"] if p["opening_balance"] is not None else round(g.r.uniform(250, 4500), 2)
            else:
                balances[acc_type] = round(g.r.uniform(500, 6000) * (1 + p["age"] / 20) * (1.5 if p["saver"] > 0.6 else 1), 2)
                balances[acc_type] += p["savings_topup"]
        opening = dict(balances)

        for d, amount, cp, desc, cat, sub, channel, acc, _disc in g.tx:
            if acc not in acc_ids:
                continue
            balances[acc] = round(balances[acc] + amount, 2)
            n_tx += 1
            tx_rows.append((n_tx, acc_ids[acc], cid, d.isoformat(), amount, "EUR", cp, desc, cat, sub, channel, balances[acc]))

        for acc_type, aid in acc_ids.items():
            con.execute("INSERT INTO accounts VALUES (?,?,?,?,?,?)",
                        (aid, cid, acc_type, iban(g.r), since.isoformat(), balances[acc_type]))
        seen = set()
        for code, started, monthly in g.products:
            if code in seen:
                continue
            seen.add(code)
            con.execute("INSERT INTO products VALUES (?,?,?,?,?)", (cid, code, PRODUCTS[code], started.isoformat(), monthly))
        con.executemany("INSERT INTO truth_traits VALUES (?,?,?,?)",
                        [(cid, t, v, s.isoformat() if s else None) for t, v, s in g.traits])
        con.executemany("INSERT INTO truth_events VALUES (?,?,?,?)",
                        [(cid, e, d.isoformat(), json.dumps(det, default=str)) for e, d, det in g.events])

        if len(tx_rows) > 50_000:
            con.executemany("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", tx_rows)
            tx_rows = []
    con.executemany("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", tx_rows)
    con.commit()
    con.close()
    return n_tx


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--customers", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(Path(__file__).parent / "kbc_twin.db"))
    a = ap.parse_args()
    n = build(a.customers, a.seed, a.out)
    print(f"Wrote {a.customers} customers and {n:,} transactions to {a.out}")
