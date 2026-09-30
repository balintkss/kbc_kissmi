"""Create a login for every customer (random password, PBKDF2-hashed in the DB).

Plain-text passwords for the demo personas are written to data/demo_credentials.txt
(git-ignored) so the team can log in during the demo. Nothing else ever stores them.

Usage:  python -m api.seed_credentials
"""
import secrets
import sqlite3
from pathlib import Path

from api.security import hash_password
from twin.engine import DB


def main():
    con = sqlite3.connect(DB)
    con.executescript("""
        DROP TABLE IF EXISTS credentials;
        CREATE TABLE credentials (customer_id INTEGER PRIMARY KEY REFERENCES customers(customer_id),
                                  password_hash TEXT NOT NULL);
    """)
    demo_lines = []
    for cid, first, demo in con.execute("SELECT customer_id, first_name, is_demo_persona FROM customers").fetchall():
        password = secrets.token_urlsafe(12)
        # Non-demo passwords are random and never handed out; fewer iterations keeps seeding 5K users fast.
        con.execute("INSERT INTO credentials VALUES (?,?)", (cid, hash_password(password) if demo else hash_password(password, 1_000)))
        if demo:
            demo_lines.append(f"customer_id={cid}  ({first})  password={password}")
    con.commit()
    out = Path(DB).parent / "demo_credentials.txt"
    out.write_text("\n".join(demo_lines) + "\n")
    out.chmod(0o600)
    print(f"Created credentials for all customers; demo persona logins written to {out}")


if __name__ == "__main__":
    main()
