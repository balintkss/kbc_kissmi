"""The population behind the twins: ops dashboard aggregates and the advisor drill-down.

Everything here comes from what the twin engine inferred (twin_profile / twin_facts), the
customers' master data, their KBC products and their own corrections (twin_feedback).
It never reads the evaluation-only tables, the credentials or the chat history.

  overview(con)                      -> population aggregates (computed once, cached in-process)
  search(con, has, event, limit)     -> customers with a fact / a recent life event (advisor picker)
  customer_view(con, cid, twin=None) -> what an advisor sees before meeting one customer
"""
import json
import sqlite3
import threading
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from twin.catalog import CATALOG
from twin.engine import AS_OF
from twin.recommender import moments, page

AS_OF_DATE = AS_OF.date()
EVENT_WINDOW_DAYS = 90
EVENT_FROM = AS_OF_DATE - timedelta(days=EVENT_WINDOW_DAYS)

# Scale. Headline build benchmark from the README: one full `python -m twin.engine` run (5,000 customers,
# ~2.16M transactions, one process on a laptop) takes ~80 s. It is quoted here, not re-run: a run rewrites
# the twin tables. Every twin only reads its own customer's transactions, so the build parallelises linearly.
TARGET_CUSTOMERS = 2_300_000
BENCH_CUSTOMERS, BENCH_SECONDS = 5_000, 80
CLUSTER_CORES = 32
CACHE_SECONDS = 600

FACT_LABELS = {
    "employment": "Employment status known", "income": "Net income & payday", "has_car": "Owns a car",
    "pet": "Has a pet", "children": "Has children", "childcare": "Pays for childcare", "housing": "Housing situation",
    "commutes_by_train": "Commutes by train", "gym_member": "Gym member", "subscriptions": "Streaming subscriptions",
    "travels": "Travels by plane", "saves_monthly": "Saves every month", "financial_buffer": "Financial buffer",
    "money_stress": "Shows money stress",
}
EVENT_LABELS = {"new_car": "Bought a car", "new_baby": "New baby", "moved": "Moved house",
                "first_job": "First job", "new_job": "New job", "new_pet": "New pet"}
KNOWN_FACTS = frozenset(FACT_LABELS) | {f"life_event_{e}" for e in EVENT_LABELS}
VIEW_LABELS = {  # short labels for one customer's fact cards
    "employment": "Employment", "income": "Net income", "has_car": "Owns a car", "pet": "Pet", "children": "Children",
    "childcare": "Childcare", "housing": "Housing", "commutes_by_train": "Commutes by train", "gym_member": "Gym",
    "subscriptions": "Subscriptions", "travels": "Flights this year", "saves_monthly": "Saves monthly",
    "financial_buffer": "Financial buffer", "money_stress": "Money stress",
}
KIND_LABELS = {"salary_plan": "Payday plan", "support": "Support (money stress)", "new_car": "New car",
               "new_baby": "New baby", "moved": "Moved house", "new_job": "New job"}

_cache = {"at": 0.0, "data": None}
_lock = threading.Lock()


# ---------------------------------------------------------------------- helpers

def _iso(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _event_date(fact):
    return _iso(fact.get("since")) or _iso(fact.get("value"))


def _is_recent_event(fact):
    d = _event_date(fact)
    return d is not None and EVENT_FROM <= d <= AS_OF_DATE


def _feedback(con, customer_id=None):
    """Latest correction per (customer, fact): True = 'that's right', False = 'that's not me'."""
    sql = "SELECT customer_id, fact, correct, note FROM twin_feedback"
    args = ()
    if customer_id is not None:
        sql, args = sql + " WHERE customer_id = ?", (customer_id,)
    try:
        rows = con.execute(sql + " ORDER BY created_at", args).fetchall()
    except sqlite3.OperationalError:  # table not created yet
        return {}
    return {(cid, fact): (bool(correct), note) for cid, fact, correct, note in rows}


def _apply_feedback(twin, feedback):
    """Customer corrections win over inference, exactly like the customer-facing API."""
    for (cid, fact), (correct, note) in feedback.items():
        if cid == twin["customer_id"] and fact in twin["facts"]:
            twin["facts"][fact]["rejected_by_customer"] = not correct
            twin["facts"][fact]["confirmed_by_customer"] = correct
            if note:
                twin["facts"][fact]["customer_note"] = note
    return twin


def _active(twin):
    return {k: f for k, f in twin["facts"].items() if not f.get("rejected_by_customer")}


def _bucket(key, fact):
    """Sub-category shown next to a coverage bar (e.g. combustion vs electric)."""
    v = fact.get("value")
    if key == "has_car":
        return fact.get("powertrain")
    if key in ("pet", "employment", "housing"):
        return str(v).replace("_", " ")
    if key == "children" and isinstance(v, (int, float)):
        return "3+ children" if v >= 3 else f"{int(v)} child{'ren' if v > 1 else ''}"
    if key == "financial_buffer" and isinstance(v, (int, float)):
        return "< 1 month" if v < 1 else "1–3 months" if v < 3 else "3–6 months" if v < 6 else "6+ months"
    return None


def _headline(fact, value, since):
    if fact.startswith("life_event_"):
        return f"{EVENT_LABELS.get(fact[11:], fact[11:])} ({since})"
    if fact == "has_car":
        return "Car owner"
    if fact == "pet":
        return f"Has a {value}"
    if fact == "children":
        return f"{value} child{'ren' if isinstance(value, int) and value > 1 else ''}"
    if fact == "money_stress":
        return "Money stress"
    if fact == "commutes_by_train":
        return "Train commuter"
    if fact == "housing":
        return str(value).replace("_", " ").capitalize()
    return FACT_LABELS.get(fact, fact)


def _highlight_ids(twin):
    out = {}
    for topic in CATALOG:
        block = page(twin, topic)
        out[topic] = block["highlight"]["id"] if block["personalized"] else None
    return out


# ---------------------------------------------------------------------- population overview

OPPORTUNITIES = [
    ("car_insurance_elsewhere", "Car owners insured at another insurer",
     "Quote in 2 minutes from what the twin already knows (car, price, age)",
     lambda f, p, t: "has_car" in f and f["has_car"].get("insured_at") not in (None, "KBC")),
    ("renters_healthy_buffer", "Renters with ≥ 3 months of buffer",
     "A home-loan payment close to today's rent builds own capital",
     lambda f, p, t: f.get("housing", {}).get("value") == "renting" and f.get("financial_buffer", {}).get("value", 0) >= 3),
    ("newborn_no_hospital_cover", "New baby, no KBC hospitalisation insurance",
     "Adding a newborn now avoids a waiting period",
     lambda f, p, t: "life_event_new_baby" in f and "hospital_insurance" not in p),
    ("moved_no_home_insurance", "Moved in the last 90 days, no KBC home insurance",
     "New home and contents need cover",
     lambda f, p, t: "life_event_moved" in f and _is_recent_event(f["life_event_moved"]) and "home_insurance" not in p),
    ("pension_gap", "Working, healthy buffer, no pension savings",
     "25–30% tax reduction they are not using",
     lambda f, p, t: f.get("employment", {}).get("value") in ("employee", "self_employed") and t["age"] < 64
     and f.get("financial_buffer", {}).get("value", 0) >= 3 and "pension_savings" not in p),
]


def _compute(con):
    started = time.perf_counter()
    customers = con.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    feedback = _feedback(con)
    fb_by_customer = defaultdict(dict)
    for (cid, fact), val in feedback.items():
        fb_by_customer[cid][(cid, fact)] = val

    coverage, buckets = Counter(), defaultdict(Counter)
    events_recent, events_year = Counter(), Counter()
    customers_with_recent_event = 0
    facts_total, conf_total = 0, 0.0
    push_kind, feed_kind, held_kind = Counter(), Counter(), Counter()
    push_total = feed_total = held_total = reached = customers_held = stressed = 0
    opp, opp_quiet = Counter(), Counter()
    insurers = Counter()
    highlights = {topic: Counter() for topic in CATALOG}
    twins = 0

    view_started = time.perf_counter()
    for cid, profile_json in con.execute("SELECT customer_id, profile_json FROM twin_profile"):
        twin = _apply_feedback(json.loads(profile_json), fb_by_customer.get(cid, {}))
        twins += 1
        facts = _active(twin)
        products = set(twin["kbc_products"])
        facts_total += len(facts)
        conf_total += sum(f["confidence"] for f in facts.values())
        recent = False
        for key, f in facts.items():
            if key.startswith("life_event_"):
                kind = key[11:]
                events_year[kind] += 1
                if _is_recent_event(f):
                    events_recent[kind] += 1
                    recent = True
                continue
            coverage[key] += 1
            b = _bucket(key, f)
            if b:
                buckets[key][b] += 1
        customers_with_recent_event += recent

        m = moments(twin)
        push_total += len(m["push"])
        feed_total += len(m["feed"])
        held_total += len(m["held_back"])
        reached += bool(m["push"])
        customers_held += bool(m["held_back"])
        push_kind.update(x["kind"] for x in m["push"])
        feed_kind.update(x["kind"] for x in m["feed"])
        held_kind.update(x["kind"] for x in m["held_back"])

        under_stress = "money_stress" in facts
        stressed += under_stress
        for oid, _label, _why, rule in OPPORTUNITIES:
            if rule(facts, products, twin):
                (opp_quiet if under_stress else opp)[oid] += 1
        car = facts.get("has_car")
        if car and car.get("insured_at") not in (None, "KBC") and not under_stress:
            insurers[car["insured_at"]] += 1

        for topic, vid in _highlight_ids(twin).items():
            highlights[topic][vid] += 1
    view_seconds = time.perf_counter() - view_started

    per_customer = BENCH_SECONDS / BENCH_CUSTOMERS
    one_core_hours = TARGET_CUSTOMERS * per_customer / 3600
    cluster_minutes = TARGET_CUSTOMERS * per_customer / CLUSTER_CORES / 60
    view_ms = view_seconds / twins * 1000 if twins else 0
    confirmed = sum(1 for correct, _ in feedback.values() if correct)

    return {
        "as_of": AS_OF_DATE.isoformat(),
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "population": {
            "customers": customers, "twins_built": twins, "facts_inferred": facts_total,
            "facts_per_customer": round(facts_total / twins, 1) if twins else 0,
            "avg_confidence": round(conf_total / facts_total, 3) if facts_total else 0,
        },
        "coverage": sorted(
            [{"fact": k, "label": FACT_LABELS.get(k, k), "customers": n, "share": round(n / twins, 4) if twins else 0,
              "breakdown": [{"value": v, "customers": c} for v, c in buckets[k].most_common()]}
             for k, n in coverage.items()], key=lambda r: -r["customers"]),
        "life_events": {
            "window_days": EVENT_WINDOW_DAYS, "from": EVENT_FROM.isoformat(), "to": AS_OF_DATE.isoformat(),
            "total": sum(events_recent.values()), "customers": customers_with_recent_event,
            "by_type": [{"event": e, "label": EVENT_LABELS.get(e, e), "customers": events_recent[e],
                         "whole_year": events_year[e]} for e in sorted(events_year, key=lambda e: -events_recent[e])],
        },
        "moments": {
            "max_push_per_customer": 2, "push_total": push_total, "customers_reached": reached,
            "feed_total": feed_total, "held_back_total": held_total, "customers_held_back": customers_held,
            "customers_money_stress": stressed, "support_offered": push_kind["support"] + feed_kind["support"],
            "by_kind": [{"kind": k, "label": KIND_LABELS.get(k, k), "push": push_kind[k], "feed": feed_kind[k],
                         "held_back": held_kind[k]}
                        for k in sorted(set(push_kind) | set(feed_kind) | set(held_kind),
                                        key=lambda k: -(push_kind[k] + feed_kind[k] + held_kind[k]))],
        },
        "opportunities": [{"id": oid, "label": label, "why": why, "customers": opp[oid],
                           "not_approached_money_stress": opp_quiet[oid]} for oid, label, why, _ in OPPORTUNITIES],
        "car_insurance_elsewhere_by_insurer": [{"insurer": k, "customers": n} for k, n in insurers.most_common()],
        "highlights": [{
            "topic": topic, "title": cat["title"], "generic": highlights[topic][None],
            "variants": [{"id": vid, "name": v["name"], "customers": highlights[topic][vid]} for vid, v in cat["variants"].items()],
        } for topic, cat in CATALOG.items()],
        "corrections": {"confirmed": confirmed, "rejected": len(feedback) - confirmed,
                        "customers": len({cid for cid, _ in feedback})},
        "scale": {
            "target_customers": TARGET_CUSTOMERS,
            "build_benchmark": {"customers": BENCH_CUSTOMERS, "seconds": BENCH_SECONDS,
                                "note": "full twin engine run, one process on a laptop (README benchmark)"},
            "build_per_customer_ms": round(per_customer * 1000, 1),
            "build_one_core_hours": round(one_core_hours, 1),
            "build_cluster_cores": CLUSTER_CORES,
            "build_cluster_minutes": round(cluster_minutes, 1),
            "view_measured": {"customers": twins, "seconds": round(view_seconds, 3), "ms_per_customer": round(view_ms, 3),
                              "note": "measured now: load twin + moments + 5 highlight pages per customer"},
            "view_one_core_minutes": round(TARGET_CUSTOMERS * view_ms / 1000 / 60, 1),
            "llm_calls_for_inference": 0,
            "llm_used_for": "Kate's chat replies only, when a customer asks something",
            "headline": (f"{BENCH_CUSTOMERS // 1000}K twins in {BENCH_SECONDS} s → {TARGET_CUSTOMERS / 1e6:.1f}M in "
                         f"~{one_core_hours:.0f} h on one core / ~{cluster_minutes:.0f} min on {CLUSTER_CORES} cores; "
                         f"0 LLM calls for inference"),
        },
        "compute_seconds": round(time.perf_counter() - started, 3),
    }


def overview(con, max_age=CACHE_SECONDS):
    """Population aggregates. ~5K JSON parses, so computed once and cached in-process."""
    with _lock:
        if _cache["data"] is None or time.time() - _cache["at"] > max_age:
            _cache["data"], _cache["at"] = _compute(con), time.time()
        return _cache["data"]


# ---------------------------------------------------------------------- advisor drill-down

def search(con, has=None, event=None, limit=20):
    """Customers with fact `has` and/or life event `event` in the last 90 days. Filters must be known keys."""
    if has is not None and has not in KNOWN_FACTS:
        raise ValueError("unknown fact")
    if event is not None and event not in EVENT_LABELS:
        raise ValueError("unknown event")
    where, args = [], []
    if has:
        where.append("c.customer_id IN (SELECT customer_id FROM twin_facts WHERE fact = ?)")
        args.append(has)
    if event:
        where.append("c.customer_id IN (SELECT customer_id FROM twin_facts WHERE fact = ? AND since BETWEEN ? AND ?)")
        args += [f"life_event_{event}", EVENT_FROM.isoformat(), AS_OF_DATE.isoformat()]
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    base = f"FROM customers c JOIN twin_profile p ON p.customer_id = c.customer_id {clause}"
    total = con.execute(f"SELECT COUNT(*) {base}", args).fetchone()[0]
    rows = con.execute(f"""SELECT c.customer_id, c.first_name, c.last_name, c.city {base}
                           ORDER BY c.is_demo_persona DESC, c.customer_id LIMIT ?""", (*args, int(limit))).fetchall()
    ids = [r[0] for r in rows]
    heads = defaultdict(list)
    if ids:
        marks = ",".join("?" * len(ids))
        priority = ["life_event_new_baby", "life_event_new_car", "life_event_moved", "life_event_first_job",
                    "life_event_new_job", "life_event_new_pet", "money_stress", "has_car", "children", "pet",
                    "commutes_by_train", "housing"]
        for cid, fact, value, since in con.execute(
                f"SELECT customer_id, fact, value, since FROM twin_facts WHERE customer_id IN ({marks})", ids):
            if fact in priority and (not fact.startswith("life_event_") or EVENT_FROM.isoformat() <= (since or "") <= AS_OF_DATE.isoformat()):
                heads[cid].append((priority.index(fact), _headline(fact, json.loads(value), since)))
    return {
        "total": total,
        "customers": [{"customer_id": cid, "name": f"{first} {last}", "city": city,
                       "headline": [h for _, h in sorted(heads[cid])[:4]]} for cid, first, last, city in rows],
    }


FACT_CORE = {"key", "value", "confidence", "since", "summary", "implies", "evidence",
             "rejected_by_customer", "confirmed_by_customer", "customer_note"}


def _load_twin(con, customer_id):
    row = con.execute("SELECT profile_json FROM twin_profile WHERE customer_id = ?", (customer_id,)).fetchone()
    return _apply_feedback(json.loads(row[0]), _feedback(con, customer_id)) if row else None


def customer_view(con, customer_id, twin=None):
    """One customer as the advisor sees them before a meeting: the same twin the customer sees.

    `twin` lets the API pass the twin exactly as the customer-facing endpoints load it.
    Returns None for an unknown customer or one without a twin.
    """
    row = con.execute("""SELECT first_name, last_name, city, language, region, birth_year, customer_since
                         FROM customers WHERE customer_id = ?""", (customer_id,)).fetchone()
    if not row:
        return None
    twin = twin if twin is not None else _load_twin(con, customer_id)
    if twin is None:
        return None
    first, last, city, language, region, birth_year, since = row
    products = [{"code": code, "name": name, "since": started}
                for code, name, started in con.execute(
                    "SELECT product_code, product_name, started_at FROM products WHERE customer_id = ? ORDER BY product_code",
                    (customer_id,))]
    order = lambda f: (0 if f["key"].startswith("life_event_") else 1 if f["key"] == "money_stress" else 2)
    facts = []
    for f in sorted(twin["facts"].values(), key=order):
        key = f["key"]
        label = EVENT_LABELS.get(key[11:], key) if key.startswith("life_event_") else VIEW_LABELS.get(key, key)
        facts.append({
            "key": key, "label": label, "value": f.get("value"), "summary": f.get("summary"),
            "confidence": f.get("confidence"), "since": f.get("since"), "implies": f.get("implies", []),
            "evidence_count": len(f.get("evidence") or []),
            "details": {k: v for k, v in f.items() if k not in FACT_CORE and (v is None or isinstance(v, (str, int, float, bool)))},
            "rejected_by_customer": bool(f.get("rejected_by_customer")),
            "confirmed_by_customer": bool(f.get("confirmed_by_customer")),
            "customer_note": f.get("customer_note"),
        })
    highlights = []
    for topic in CATALOG:
        block = page(twin, topic)
        h = block["highlight"]
        highlights.append({
            "topic": topic, "title": block["title"], "personalized": block["personalized"],
            "highlight": {"id": h["id"], "name": h["name"], "summary": h["summary"], "reason": h["reason"],
                          "because": h["because"]} if h else None,
            "alternatives": [a["name"] for a in block.get("alternatives", [])],
        })
    return {
        "customer_id": customer_id, "name": f"{first} {last}", "first_name": first, "city": city,
        "language": language, "region": region, "age": twin.get("age"),
        "customer_since": since, "as_of": twin.get("as_of"), "products": products, "facts": facts,
        "plan": twin.get("plan"), "moments": moments(twin), "highlights": highlights,
        # Money stress: the advisor leads with support, not with the product pages' highlights.
        "support_first": "money_stress" in _active(twin),
    }
