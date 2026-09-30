"""Score the digital twin against the hidden ground truth (truth_* tables).

Usage:  python -m twin.evaluate
"""
import json
import sqlite3

from twin.engine import DB


def main():
    con = sqlite3.connect(DB)
    facts = {cid: json.loads(p)["facts"] for cid, p in con.execute("SELECT customer_id, profile_json FROM twin_profile")}
    truth = {}
    for cid, trait, value in con.execute("SELECT customer_id, trait, value FROM truth_traits"):
        truth.setdefault(cid, {})[trait] = value
    events = {}
    for cid, event in con.execute("SELECT customer_id, event FROM truth_events"):
        events.setdefault(cid, set()).add(event)

    checks = {
        "owns a car": (lambda t: t["has_car"] == "true", lambda f: bool(f.get("has_car"))),
        "electric car": (lambda t: t.get("car_fuel") == "electric", lambda f: f.get("has_car", {}).get("powertrain") == "electric"),
        "has a pet": (lambda t: t["pet"] != "none", lambda f: "pet" in f),
        "dog vs cat": (lambda t: t["pet"] == "dog", lambda f: f.get("pet", {}).get("value") == "dog"),
        "commutes by train": (lambda t: t["commutes_by_train"] == "true", lambda f: "commutes_by_train" in f),
        "saves monthly": (lambda t: t["saver"] == "true", lambda f: "saves_monthly" in f),
        "has children": (lambda t: t["children"] != "0", lambda f: "children" in f or "life_event_new_baby" in f),
    }
    ev_checks = {
        "just bought a car": ("new_car", "life_event_new_car"),
        "new baby": ("new_baby", "life_event_new_baby"),
        "moved house": ("moved", "life_event_moved"),
        "new job": ("new_job", "life_event_new_job"),
        "first job": ("first_job", "life_event_first_job"),
    }
    print(f"{'fact':<22}{'accuracy':>9}{'precision':>11}{'recall':>8}   n")
    rows = [(name, [(t_fn(truth[c]), f_fn(facts.get(c, {}))) for c in truth]) for name, (t_fn, f_fn) in checks.items()]
    rows += [(name, [(ev in events.get(c, ()), key in facts.get(c, {})) for c in truth]) for name, (ev, key) in ev_checks.items()]
    for name, pairs in rows:
        tp = sum(t and p for t, p in pairs); fp = sum(p and not t for t, p in pairs); fn = sum(t and not p for t, p in pairs)
        acc = sum(t == p for t, p in pairs) / len(pairs)
        prec = tp / (tp + fp) if tp + fp else 0; rec = tp / (tp + fn) if tp + fn else 0
        print(f"{name:<22}{acc:>9.1%}{prec:>11.1%}{rec:>8.1%}   {tp + fn}")


if __name__ == "__main__":
    main()
