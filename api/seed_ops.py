"""Create the ops/advisor login for the population dashboard (/ops).

Creates the ops_users table if needed and upserts one user, `advisor`, with a fresh random
password (PBKDF2-hashed in the DB). The plain login is written to data/ops_credentials.txt
(git-ignored, chmod 600) so the team can log in during the demo. Nothing else stores it.
Re-running rotates the password.

Usage:  python -m api.seed_ops
"""
import os
import secrets
import sqlite3
from pathlib import Path

from api.security import hash_password
from twin.engine import DB

OPS_SCHEMA = """CREATE TABLE IF NOT EXISTS ops_users (
    username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, role TEXT NOT NULL)"""
USERNAME, ROLE = "advisor", "ops"


def main():
    password = secrets.token_urlsafe(12)
    con = sqlite3.connect(DB)
    try:
        with con:  # one transaction
            con.execute(OPS_SCHEMA)
            con.execute("""INSERT INTO ops_users (username, password_hash, role) VALUES (?,?,?)
                           ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash, role = excluded.role""",
                        (USERNAME, hash_password(password), ROLE))
    finally:
        con.close()
    out = Path(DB).parent / "ops_credentials.txt"
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # never world-readable, not even briefly
    with os.fdopen(fd, "w") as fh:
        fh.write(f"username={USERNAME}  password={password}\n")
    out.chmod(0o600)
    print(f"Ops login '{USERNAME}' created; credentials written to {out}")


if __name__ == "__main__":
    main()
