"""Digital-twin engine: turn raw banking activity into a living picture of the customer.

For every customer it produces
  * facts        — what we believe about their life (has a car, has a dog, just moved, ...),
                   each with a confidence, a 'since' date and the transactions that prove it
  * implications — what that fact means financially (a car => maintenance, road tax, insurance)
  * recurring    — fixed monthly bills and yearly bills, with the next expected date
  * plan         — the salary-day plan: bills until next payday, reserves, savings, free to spend

It never reads the truth_* tables. Results go to twin_profile (JSON per customer) and twin_facts.

Usage:  python -m twin.engine                 # all customers
        python -m twin.engine --customer 1    # print one twin as JSON
"""
import argparse
import json
import sqlite3
from pathlib import Path

import pandas as pd

DB = Path(__file__).resolve().parent.parent / "data" / "kbc_twin.db"
AS_OF = pd.Timestamp("2026-09-30")
WINDOW_START = pd.Timestamp("2025-10-01")

DISCRETIONARY = {"groceries", "dining", "shopping", "leisure", "cash", "travel"}
VARIABLE_SUBS = {"fuel", "ev_charging", "parking", "pharmacy", "doctor", "hospital", "pet_food", "vet", "baby", "kids_shopping",
                 "maintenance", "furniture_diy", "moving", "notary", "car_purchase", "registration", "adoption"}
YEARLY_SUBS = {"road_tax", "property_tax", "mutuality", "inspection", "liability"}
MAINTENANCE_DEFAULT = {"combustion": 650, "electric": 350}


def _ev(df, n=5):
    """Evidence: the most recent transaction ids backing a fact."""
    return [int(x) for x in df.sort_values("booked_at", ascending=False)["tx_id"].head(n)]


def _d(ts):
    return None if ts is None or pd.isna(ts) else pd.Timestamp(ts).date().isoformat()


def _since(ts):
    """A fact first seen in the first weeks of the data was most likely true before the data starts."""
    if ts is None or pd.isna(ts):
        return None
    return "before " + WINDOW_START.date().isoformat() if ts < WINDOW_START + pd.Timedelta(days=45) else _d(ts)


def _is_recent(ts, days=120, as_of=None):
    as_of = AS_OF if as_of is None else as_of
    return ts is not None and not pd.isna(ts) and ts >= WINDOW_START + pd.Timedelta(days=45) and (as_of - ts).days <= days


class Twin:
    def __init__(self, customer, tx, products, accounts, as_of=None):
        """as_of: the day the twin is built for (default AS_OF). The caller passes only transactions booked on or
        before it and the balances of that day (twin/incremental.py does this for the daily update)."""
        self.as_of = AS_OF if as_of is None else pd.Timestamp(as_of)
        self.c = customer
        self.tx = tx
        self.cur = tx[tx.acc_type == "current"]
        self.products = set(products)
        self.accounts = accounts
        self.facts = {}

    # ------------------------------------------------------------------ helpers
    def sub(self, *subs, df=None):
        df = self.cur if df is None else df
        return df[df.subcategory.isin(subs)]

    def add(self, key, value, confidence, since=None, evidence=None, summary="", implies=None, **extra):
        self.facts[key] = dict(key=key, value=value, confidence=round(float(confidence), 2), since=since,
                               evidence=evidence or [], summary=summary, implies=implies or [], **extra)

    # ------------------------------------------------------------------ inference
    def infer_income(self):
        sal = self.sub("salary")
        if len(sal):
            last_payer = sal.iloc[-1].counterparty
            recent = sal[sal.counterparty == last_payer].tail(3)
            day = int(recent.booked_at.dt.day.median())
            amount = float(recent.amount.median())
            payers = list(dict.fromkeys(sal.counterparty))
            self.add("employment", "employee", 0.97, _since(sal.booked_at.min()), _ev(sal),
                     f"Salary from {last_payer} around day {day} of the month", employer=last_payer)
            self.add("income", round(amount), 0.95, None, _ev(recent), f"Net salary ≈ €{amount:,.0f}/month",
                     payday=day, source=last_payer, kind="salary")
            students = self.sub("student_job")
            first_new = sal[sal.counterparty == last_payer].booked_at.min()
            if len(students) and first_new > students.booked_at.max() - pd.Timedelta(days=45):
                self.add("life_event_first_job", last_payer, 0.93, _d(first_new), _ev(sal[sal.counterparty == last_payer]),
                         f"Student jobs stopped and a first salary from {last_payer} arrived")
            elif len(payers) > 1:
                self.add("life_event_new_job", last_payer, 0.9, _d(first_new), _ev(sal[sal.counterparty == last_payer]),
                         f"Salary switched from {payers[-2]} to {last_payer}")
            return
        for sub_, kind, label in (("pension", "retired", "Pension"), ("benefit", "unemployed", "Unemployment benefit")):
            s = self.sub(sub_)
            if len(s) >= 2 and (self.as_of - s.booked_at.max()).days < 45:
                amount = float(s.tail(3).amount.median())
                self.add("employment", kind, 0.95, _since(s.booked_at.min()), _ev(s), f"{label} ≈ €{amount:,.0f}/month")
                self.add("income", round(amount), 0.95, None, _ev(s), f"{label} ≈ €{amount:,.0f}/month",
                         payday=int(s.tail(3).booked_at.dt.day.median()), source=s.iloc[-1].counterparty, kind=sub_)
                return
        inv = self.sub("invoice")
        if len(inv) >= 3:
            monthly = inv.groupby(inv.booked_at.dt.to_period("M")).amount.sum()
            self.add("employment", "self_employed", 0.9, _since(inv.booked_at.min()), _ev(inv),
                     f"Client invoices, {monthly.std() / monthly.mean():.0%} month-to-month variation")
            self.add("income", round(float(monthly.mean())), 0.75, None, _ev(inv),
                     f"Irregular income ≈ €{monthly.mean():,.0f}/month (lowest month €{monthly.min():,.0f})",
                     payday=None, kind="irregular", lowest_month=round(float(monthly.min())),
                     quiet_month=round(float(monthly.quantile(0.25))))
            return
        st = self.sub("student_job", "family_transfer")
        if len(st):
            monthly = st.groupby(st.booked_at.dt.to_period("M")).amount.sum().mean()
            self.add("employment", "student", 0.85, None, _ev(st), "Student jobs and allowance from parents")
            self.add("income", round(float(monthly)), 0.7, None, _ev(st), f"≈ €{monthly:,.0f}/month from student jobs and parents",
                     payday=None, kind="student")

    def infer_car(self):
        energy = self.sub("fuel", "ev_charging")
        ev = self.sub("ev_charging")
        other = {k: self.sub(*v) for k, v in {
            "maintenance": ("maintenance",), "insurance": ("car",), "road_tax": ("road_tax", "registration_tax"),
            "inspection": ("inspection",), "purchase": ("car_purchase",), "loan": ("car_loan",), "parking": ("parking",)}.items()}
        other["insurance"] = other["insurance"][other["insurance"].category == "insurance"]
        kinds = sum(1 for k, v in other.items() if len(v) and k != "parking")
        conf = (0.6 if len(energy) >= 3 else 0.35 if len(energy) else 0) + 0.1 * kinds
        if conf < 0.6:
            return
        conf = min(0.99, conf)
        powertrain = "electric" if len(ev) > len(energy) / 2 else "combustion"
        first = other["purchase"].booked_at.min() if len(other["purchase"]) else energy.booked_at.min()
        evidence = _ev(pd.concat([energy.tail(3), *[v.tail(1) for v in other.values() if len(v)]]), 8)

        months_seen = max(1, (self.as_of - max(first, WINDOW_START)).days / 30.4)
        fuel_month = -energy.amount.sum() / months_seen
        ins = other["insurance"]
        if "car_insurance" in self.products:
            insured_at, ins_year = "KBC", -ins.amount.tail(1).sum() * 12 if len(ins) else None
        elif len(ins):
            insured_at = ins.iloc[-1].counterparty
            monthly_ins = ins[ins.description.str.contains("maand|mensuelle|monthly", case=False)]
            ins_year = -monthly_ins.amount.tail(1).sum() * 12 if len(monthly_ins) else -ins.amount.tail(1).sum()
        else:
            insured_at, ins_year = None, None
        older = len(other["inspection"]) > 0
        bought_recently = _is_recent(other["purchase"].booked_at.min() if len(other["purchase"]) else None, 200, self.as_of)
        price = -other["purchase"].amount.sum() if len(other["purchase"]) else None
        maint_obs = -other["maintenance"].amount.sum()
        maint_year = max(maint_obs, MAINTENANCE_DEFAULT[powertrain] * (1.3 if older else 1))
        road_tax = -other["road_tax"][other["road_tax"].subcategory == "road_tax"].amount.sum()
        if not road_tax:
            road_tax = 0 if powertrain == "electric" else 250
        inspection = 55 if older or (price and price < 20000) else 0

        implies = [
            dict(cost="maintenance & tyres", yearly=round(maint_year), why=f"{'observed' if maint_obs else 'typical'} for a {'older ' if older else ''}{powertrain} car"),
            dict(cost="road tax", yearly=round(road_tax), why="yearly regional road tax" + (" (observed)" if "road_tax" in set(other["road_tax"].subcategory) else " (expected)")),
            dict(cost="fuel" if powertrain == "combustion" else "charging", monthly=round(fuel_month), why=f"{len(energy)} {'fuel' if powertrain == 'combustion' else 'charging'} payments"),
        ]
        if inspection:
            implies.append(dict(cost="technical inspection", yearly=inspection, why="car older than 4 years"))
        if ins_year:
            implies.append(dict(cost="insurance", yearly=round(ins_year), why=f"insured at {insured_at}"))
        reserve = (maint_year + road_tax + inspection) / 12
        self.add("has_car", True, conf, _since(first), evidence,
                 f"{len(energy)} {'fuel' if powertrain == 'combustion' else 'charging'} payments"
                 + (f", car bought {_d(first)} for €{price:,.0f}" if bought_recently and price else "")
                 + (f", insured at {insured_at}" if insured_at else ", no car insurance payment seen"),
                 implies, powertrain=powertrain, older_car=older, insured_at=insured_at,
                 bought_recently=bool(bought_recently), purchase_price=round(price) if price else None,
                 has_car_loan="car_loan" in self.products, monthly_reserve=round(reserve))
        if len(other["purchase"]):
            self.add("life_event_new_car", _d(first), 0.95, _d(first), _ev(other["purchase"]), f"Car purchase of €{price:,.0f}")

    def infer_pet(self):
        food, vet, adopt = self.sub("pet_food"), self.sub("vet"), self.sub("adoption")
        if len(food) + len(vet) < 2:
            return
        dog = food.amount.mean() < -42 if len(food) else True
        first = pd.concat([food, vet, adopt]).booked_at.min()
        vet_year = max(-vet.amount.sum(), 250 if dog else 180)
        self.add("pet", "dog" if dog else "cat", 0.6 + min(0.35, 0.05 * (len(food) + len(vet))), _since(first),
                 _ev(pd.concat([food, vet])), f"{len(food)} pet-shop and {len(vet)} vet payments (avg €{-food.amount.mean():.0f} per food purchase)",
                 [dict(cost="vet & care", yearly=round(vet_year), why="vet visits + vaccinations")],
                 monthly_reserve=round(vet_year / 12))
        if len(adopt):
            self.add("life_event_new_pet", _d(adopt.booked_at.min()), 0.9, _d(adopt.booked_at.min()), _ev(adopt), "Paid an adoption fee")

    def infer_family(self):
        cb = self.sub("child_benefit")
        baby = self.sub("baby")
        birth = self.sub("birth_allowance")
        n = round(cb.tail(1).amount.iloc[0] / 175) if len(cb) else 0
        if n:
            self.add("children", int(n), 0.9, None, _ev(cb), f"Child benefit ≈ €{cb.tail(1).amount.iloc[0]:.0f}/month")
        care = self.sub("childcare")
        if len(care):
            self.add("childcare", round(-care.tail(3).amount.mean()), 0.9, _since(care.booked_at.min()), _ev(care),
                     f"Childcare at {care.iloc[-1].counterparty}")
        if len(birth) or (len(baby) >= 4 and len(cb) and cb.amount.iloc[-1] > cb.amount.iloc[0] * 1.2):
            born = self.sub("hospital").booked_at.max() if len(self.sub("hospital")) else (birth.booked_at.min() if len(birth) else baby.booked_at.max())
            self.add("life_event_new_baby", _d(born), 0.93, _d(born), _ev(pd.concat([birth, baby, self.sub("hospital")])),
                     "Baby gear purchases, a hospital bill and a birth allowance",
                     [dict(cost="childcare", monthly=550, why="typical Belgian childcare from ~4 months"),
                      dict(cost="nappies & care", monthly=90, why="observed baby spending")])

    def infer_housing(self):
        rent, mort = self.sub("rent"), self.sub("mortgage")
        ptax, energy = self.sub("property_tax"), self.sub("energy")
        if len(mort) and (self.as_of - mort.booked_at.max()).days < 45:
            self.add("housing", "owner_with_mortgage", 0.97, None, _ev(mort), f"Mortgage repayment €{-mort.amount.iloc[-1]:,.0f}/month",
                     monthly=round(-mort.amount.iloc[-1]), home_loan_at_kbc="home_loan" in self.products)
        elif len(rent) and (self.as_of - rent.booked_at.max()).days < 45:
            student = -rent.amount.iloc[-1] < 600 and not len(energy[energy.booked_at >= rent.booked_at.max() - pd.Timedelta(days=60)])
            self.add("housing", "student_room" if student else "renting", 0.95, None, _ev(rent),
                     f"Rent €{-rent.amount.iloc[-1]:,.0f}/month to {rent.iloc[-1].counterparty}", monthly=round(-rent.amount.iloc[-1]))
        elif len(ptax):
            self.add("housing", "owner", 0.85, None, _ev(ptax), "Pays property tax, no rent or mortgage")
        elif not len(energy):
            self.add("housing", "living_with_parents", 0.7, None, [], "No rent, mortgage or energy bills")
        moving = self.sub("moving", "notary", "furniture_diy")
        movers = self.sub("moving", "notary")
        if len(movers):
            d = movers.booked_at.min()
            bought = len(self.sub("notary")) > 0
            self.add("life_event_moved", _d(d), 0.9, _d(d), _ev(moving),
                     ("Bought a home: notary fees" if bought else "Moved: moving company") + f", {len(self.sub('furniture_diy'))} furniture/DIY purchases",
                     bought_home=bought)

    def infer_lifestyle(self):
        train = self.cur[(self.cur.subcategory == "public_transport") & self.cur.description.str.contains("abonnement|pass", case=False)]
        if len(train) >= 4:
            self.add("commutes_by_train", True, 0.92, _since(train.booked_at.min()), _ev(train), f"Monthly train pass (€{-train.amount.iloc[-1]:.0f})")
        gym = self.sub("gym")
        if len(gym) >= 3:
            self.add("gym_member", gym.iloc[-1].counterparty, 0.95, _since(gym.booked_at.min()), _ev(gym), f"{gym.iloc[-1].counterparty} membership")
        subs = self.sub("streaming")
        if len(subs):
            names = sorted(set(subs[subs.booked_at >= self.as_of - pd.Timedelta(days=45)].counterparty))
            monthly = sum(-subs[subs.counterparty == n].amount.iloc[-1] for n in names)
            if names:
                self.add("subscriptions", names, 0.95, None, _ev(subs), f"{len(names)} subscriptions, €{monthly:.2f}/month", monthly=round(monthly, 2))
        trips = self.sub("flights")
        if len(trips):
            self.add("travels", len(trips), 0.8, None, _ev(trips), f"{len(trips)} flight bookings this year")

    def infer_money(self):
        sav_tx = self.sub("transfer_to_savings")
        savings = self.accounts.get("savings", 0.0)
        current = self.accounts.get("current", 0.0)
        out = self.cur[(self.cur.amount < 0) & (self.cur.channel != "internal_transfer")]
        monthly_out = -out[out.booked_at >= self.as_of - pd.Timedelta(days=90)].amount.sum() / 3
        buffer_months = (savings + max(current, 0)) / monthly_out if monthly_out else 0
        if len(sav_tx):
            self.add("saves_monthly", round(-sav_tx.tail(3).amount.mean()), 0.95, _since(sav_tx.booked_at.min()), _ev(sav_tx),
                     f"Moves €{-sav_tx.tail(3).amount.mean():,.0f} to savings every month")
        self.add("financial_buffer", round(float(buffer_months), 1), 0.9, None, [],
                 f"Savings + current account cover {buffer_months:.1f} months of spending",
                 savings=round(savings), current=round(current), monthly_spending=round(monthly_out))
        recent = self.cur[self.cur.booked_at >= self.as_of - pd.Timedelta(days=90)]
        neg_days = recent[recent.balance_after < 0].booked_at.dt.date.nunique()
        inc = recent[(recent.amount > 0) & (recent.channel != "internal_transfer")].amount.sum()
        spend = -recent[(recent.amount < 0) & (recent.channel != "internal_transfer")].amount.sum()
        if (neg_days >= 5 and savings < monthly_out) or (inc and spend > inc * 1.08 and buffer_months < 1.5):
            self.add("money_stress", True, min(0.95, 0.6 + neg_days / 60), None,
                     _ev(recent[recent.balance_after < 0]), f"{neg_days} days in the red in the last 90 days; spent €{spend:,.0f} vs €{inc:,.0f} in")

    # ------------------------------------------------------------------ recurring & plan
    def recurring(self):
        out = self.cur[(self.cur.amount < 0) & (self.cur.channel != "internal_transfer") & (~self.cur.category.isin(DISCRETIONARY) | (self.cur.subcategory == "gym"))
                       & ~self.cur.subcategory.isin(VARIABLE_SUBS)]
        items = []
        for (cp, sub), g in out.groupby(["counterparty", "subcategory"]):
            months = g.booked_at.dt.to_period("M").nunique()
            last = g.booked_at.max()
            if (self.as_of - last).days > 70:
                continue  # stopped (e.g. old rent after a move)
            recent = g.tail(3)
            amount = float(-recent.amount.median())
            cv = float(recent.amount.std() / -recent.amount.mean()) if len(recent) > 1 else 0
            min_months = 2 if g.iloc[-1].category in ("housing", "utilities", "insurance") else 3
            if months >= min_months and cv < 0.35 and len(g) / months < 2.5:
                interval = g.booked_at.diff().dt.days.median()
                if interval and interval > 80:
                    nxt = last + pd.Timedelta(days=int(interval))
                    items.append(dict(name=cp, subcategory=sub, category=g.iloc[-1].category, frequency="quarterly",
                                      amount=round(amount, 2), next_date=_d(nxt), monthly_equivalent=round(amount / 3, 2)))
                else:
                    day = int(recent.booked_at.dt.day.median())
                    nxt = (self.as_of + pd.offsets.MonthBegin(1)).replace(day=min(day, 28))
                    items.append(dict(name=cp, subcategory=sub, category=g.iloc[-1].category, frequency="monthly",
                                      amount=round(amount, 2), day_of_month=day, next_date=_d(nxt), monthly_equivalent=round(amount, 2)))
        # housing: only the current home counts, even if it has been paid just once since a move
        home = out[out.subcategory.isin(["rent", "mortgage"])]
        if len(home):
            latest = home.iloc[-1]
            items = [i for i in items if i["subcategory"] not in ("rent", "mortgage") or i["name"] == latest.counterparty]
            if not any(i["name"] == latest.counterparty for i in items) and (self.as_of - latest.booked_at).days <= 40:
                day = int(latest.booked_at.day)
                items.append(dict(name=latest.counterparty, subcategory=latest.subcategory, category="housing", frequency="monthly",
                                  amount=round(-latest.amount, 2), day_of_month=day,
                                  next_date=_d((self.as_of + pd.offsets.MonthBegin(1)).replace(day=min(day, 28))),
                                  monthly_equivalent=round(-latest.amount, 2)))
        yearly = out[out.subcategory.isin(YEARLY_SUBS) | out.description.str.contains("jaarpremie|prime annuelle|annual premium", case=False)]
        for _, row in yearly.iterrows():
            if any(i["name"] == row.counterparty and i["subcategory"] == row.subcategory for i in items):
                continue
            nxt = row.booked_at + pd.DateOffset(years=1)
            items.append(dict(name=row.counterparty, subcategory=row.subcategory, category=row.category, frequency="yearly",
                              amount=round(-row.amount, 2), next_date=_d(nxt), monthly_equivalent=round(-row.amount / 12, 2)))
        return sorted(items, key=lambda i: i["next_date"])

    def plan(self, recurring):
        inc = self.facts.get("income")
        if not inc:
            return None
        irregular = inc.get("kind") == "irregular"
        income = inc.get("quiet_month", inc["value"]) if irregular else inc["value"]
        payday = inc.get("payday") or 1
        pay_date = (self.as_of + pd.offsets.MonthBegin(1)).replace(day=min(payday, 28))
        if pay_date.weekday() >= 5:
            pay_date -= pd.Timedelta(days=pay_date.weekday() - 4)
        next_pay = pay_date + pd.DateOffset(months=1)
        monthly_bills = [r for r in recurring if r["frequency"] == "monthly"]
        bills = sum(r["amount"] for r in monthly_bills) + sum(r["monthly_equivalent"] for r in recurring if r["frequency"] == "quarterly")
        reserves = [dict(for_="yearly bills", monthly=round(sum(r["monthly_equivalent"] for r in recurring if r["frequency"] == "yearly")),
                         items=[f"{r['name']} ({r['subcategory']}) €{r['amount']:.0f} due {r['next_date']}" for r in recurring if r["frequency"] == "yearly"])]
        for key in ("has_car", "pet"):
            f = self.facts.get(key)
            if f and f.get("monthly_reserve"):
                reserves.append(dict(for_="car upkeep" if key == "has_car" else f"{f['value']} care", monthly=f["monthly_reserve"],
                                     items=[f"{i['cost']} ≈ €{i['yearly']}/yr" for i in f["implies"] if "yearly" in i and i["cost"] != "insurance"]))
        reserve_total = sum(r["monthly"] for r in reserves)
        variable = []
        car = self.facts.get("has_car")
        if car:
            fuel = next((i["monthly"] for i in car["implies"] if i["cost"] in ("fuel", "charging")), 0)
            variable.append(dict(name="fuel" if car["powertrain"] == "combustion" else "charging", amount=fuel, estimated=True))
        groceries = self.cur[(self.cur.category == "groceries") & (self.cur.booked_at >= self.as_of - pd.Timedelta(days=90))]
        variable.append(dict(name="groceries", amount=round(-groceries.amount.sum() / 3), estimated=True))
        savings = self.facts.get("saves_monthly", {}).get("value", 0)
        big_soon = [r for r in recurring if r["frequency"] == "yearly" and pd.Timestamp(r["next_date"]) <= next_pay + pd.Timedelta(days=30)]
        free = income - bills - reserve_total - savings
        return dict(payday=None if irregular else _d(pay_date), income=round(income), income_kind=inc.get("kind"),
                    income_note="Planned on a quiet month so a slow month never catches you out" if irregular else None,
                    bills_until_next_payday=round(bills), bills=[{k: r[k] for k in ("name", "amount", "day_of_month")} for r in monthly_bills],
                    reserves=reserves, reserve_total=round(reserve_total), planned_savings=savings, variable_essentials=variable,
                    free_to_spend=round(free - sum(v["amount"] for v in variable)),
                    free_per_week=round((free - sum(v["amount"] for v in variable)) / 4.3),
                    heads_up=[f"{r['name']} €{r['amount']:.0f} expected {r['next_date']}" for r in big_soon])

    def build(self):
        for step in (self.infer_income, self.infer_car, self.infer_pet, self.infer_family, self.infer_housing,
                     self.infer_lifestyle, self.infer_money):
            step()
        rec = self.recurring()
        c = self.c
        return dict(
            customer_id=int(c.customer_id), name=f"{c.first_name} {c.last_name}", first_name=c.first_name,
            language=c.language, region=c.region, city=c.city, age=int(self.as_of.year - c.birth_year),
            kbc_products=sorted(self.products), facts=self.facts, recurring=rec, plan=self.plan(rec), as_of=_d(self.as_of),
        )


# ---------------------------------------------------------------------- batch

TWIN_SCHEMA = """
DROP TABLE IF EXISTS twin_profile;
DROP TABLE IF EXISTS twin_facts;
CREATE TABLE twin_profile (customer_id INTEGER PRIMARY KEY, profile_json TEXT NOT NULL, built_at TEXT NOT NULL);
CREATE TABLE twin_facts (customer_id INTEGER, fact TEXT, value TEXT, confidence REAL, since TEXT, summary TEXT, evidence TEXT);
CREATE INDEX idx_twin_facts ON twin_facts(fact, value);
"""


def load(con, customer_id=None):
    where = "WHERE t.customer_id = ?" if customer_id else ""
    args = (customer_id,) if customer_id else ()
    tx = pd.read_sql(f"""SELECT t.tx_id, t.customer_id, t.booked_at, t.amount, t.counterparty, t.description, t.category,
                                t.subcategory, t.channel, t.balance_after, a.type AS acc_type
                         FROM transactions t JOIN accounts a USING(account_id) {where} ORDER BY t.customer_id, t.booked_at, t.tx_id""",
                     con, params=args, parse_dates=["booked_at"])
    cust = pd.read_sql(f"SELECT * FROM customers {'WHERE customer_id = ?' if customer_id else ''}", con, params=args)
    prods = pd.read_sql(f"SELECT customer_id, product_code FROM products {'WHERE customer_id = ?' if customer_id else ''}", con, params=args)
    accs = pd.read_sql(f"SELECT customer_id, type, balance FROM accounts {'WHERE customer_id = ?' if customer_id else ''}", con, params=args)
    return tx, cust, prods, accs


def build_twins(con, customer_id=None):
    tx, cust, prods, accs = load(con, customer_id)
    prods_by = prods.groupby("customer_id").product_code.apply(list).to_dict()
    accs_by = {cid: dict(zip(g.type, g.balance)) for cid, g in accs.groupby("customer_id")}
    tx_by = dict(tuple(tx.groupby("customer_id")))
    for c in cust.itertuples():
        yield Twin(c, tx_by.get(c.customer_id, tx.iloc[0:0]), prods_by.get(c.customer_id, []), accs_by.get(c.customer_id, {})).build()


def build_one(con, customer_id):
    return next(build_twins(con, customer_id), None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer", type=int)
    ap.add_argument("--db", default=str(DB))
    a = ap.parse_args()
    con = sqlite3.connect(a.db)
    if a.customer:
        print(json.dumps(build_one(con, a.customer), indent=2, ensure_ascii=False, default=str))
        return
    con.executescript(TWIN_SCHEMA)
    built = pd.Timestamp.now().isoformat(timespec="seconds")
    n = 0
    for twin in build_twins(con):
        cid = twin["customer_id"]
        con.execute("INSERT INTO twin_profile VALUES (?,?,?)", (cid, json.dumps(twin, ensure_ascii=False, default=str), built))
        con.executemany("INSERT INTO twin_facts VALUES (?,?,?,?,?,?,?)",
                        [(cid, f["key"], json.dumps(f["value"], default=str), f["confidence"], f["since"], f["summary"], json.dumps(f["evidence"]))
                         for f in twin["facts"].values()])
        n += 1
    con.commit()
    print(f"Built {n} digital twins into {a.db}")


if __name__ == "__main__":
    main()
