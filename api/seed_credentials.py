"""Create a login for every customer (random password, PBKDF2-hashed in the DB).

Plain-text passwords for the demo personas are written to data/demo_credentials.txt
(git-ignored, chmod 600) so the team can log in during the demo. Nothing else ever stores them.

Re-running is idempotent: existing logins keep their password. Only customers without a login
get one, and a demo persona whose password isn't known yet (no valid line in the file, e.g. a
newly flagged persona) gets a fresh one, added to the file. `--rotate` drops every login and
issues new passwords for everyone (all old demo passwords stop working).

Usage:  python -m api.seed_credentials            # add what's missing, keep existing passwords
        python -m api.seed_credentials --rotate   # new passwords for every customer
"""
import argparse
import os
import re
import secrets
import sqlite3
from pathlib import Path

from api.security import hash_password, verify_password
from twin.engine import DB

SCHEMA = """CREATE TABLE IF NOT EXISTS credentials (
    customer_id INTEGER PRIMARY KEY REFERENCES customers(customer_id), password_hash TEXT NOT NULL)"""
NON_DEMO_ITERATIONS = 1_000  # non-demo passwords are random and never handed out; keeps seeding 5K users fast
_LINE = re.compile(r"^\s*customer_id=(\d+)\s+\([^)]*\)\s+password=(\S+)\s*$")


def _credentials_file():
    return Path(DB).parent / "demo_credentials.txt"


def _read_lines(path):
    """customer_id -> (line, password) for every well-formed line of the credentials file."""
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        m = _LINE.match(line)
        if m:
            out[int(m.group(1))] = (line, m.group(2))
    return out


def _write_private(path, lines):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # never world-readable, not even briefly
    with os.fdopen(fd, "w") as fh:
        fh.write("\n".join(lines) + ("\n" if lines else ""))
    path.chmod(0o600)


def _line(cid, first, password):
    return f"customer_id={cid}  ({first})  password={password}"


def _new_login(demo):
    password = secrets.token_urlsafe(12)
    return password, hash_password(password) if demo else hash_password(password, NON_DEMO_ITERATIONS)


def rotate(con, out):
    """Drop every login and issue new passwords for everyone."""
    with con:
        con.execute("DROP TABLE IF EXISTS credentials")
        con.execute(SCHEMA)
        lines = []
        for cid, first, demo in con.execute("SELECT customer_id, first_name, is_demo_persona FROM customers "
                                            "ORDER BY customer_id").fetchall():
            password, hashed = _new_login(demo)
            con.execute("INSERT INTO credentials VALUES (?,?)", (cid, hashed))
            if demo:
                lines.append(_line(cid, first, password))
    _write_private(out, lines)
    return {"created": con.execute("SELECT COUNT(*) FROM credentials").fetchone()[0], "demo_issued": len(lines)}


def top_up(con, out):
    """Idempotent: create missing logins; (re)issue only demo passwords nobody knows. Returns what changed."""
    known = _read_lines(out)
    created, issued = 0, []
    with con:
        con.execute(SCHEMA)
        rows = con.execute("""SELECT c.customer_id, c.first_name, c.is_demo_persona, cr.password_hash
                              FROM customers c LEFT JOIN credentials cr USING (customer_id)
                              ORDER BY c.customer_id""").fetchall()
        for cid, first, demo, stored in rows:
            if stored is not None:
                if not demo:
                    continue
                entry = known.get(cid)
                if entry and verify_password(entry[1], stored):
                    continue  # the team already has a working password: keep it
            password, hashed = _new_login(demo)
            con.execute("INSERT OR REPLACE INTO credentials VALUES (?,?)", (cid, hashed))
            created += stored is None
            if demo:
                issued.append((cid, first))
                known[cid] = (_line(cid, first, password), None)
    if issued or not out.exists():
        _write_private(out, [known[cid][0] for cid in sorted(known)])  # existing lines kept verbatim
    else:
        out.chmod(0o600)
    return {"created": created, "demo_issued": len(issued), "issued_for": issued}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Create customer logins; demo passwords -> data/demo_credentials.txt")
    ap.add_argument("--rotate", action="store_true", help="drop every login and issue new passwords for everyone")
    a = ap.parse_args(argv)
    out = _credentials_file()
    con = sqlite3.connect(DB, timeout=30)
    try:
        result = rotate(con, out) if a.rotate else top_up(con, out)
    finally:
        con.close()
    if a.rotate:
        print(f"Rotated: new passwords for all {result['created']} customers; demo persona logins written to {out}")
    else:
        who = ", ".join(f"{cid} ({first})" for cid, first in result["issued_for"]) or "none"
        print(f"Created {result['created']} missing logins; new demo passwords: {who}. "
              f"Existing passwords unchanged. Demo persona logins are in {out}")
    return result


if __name__ == "__main__":
    main()
