"""Password hashing and signed session tokens (stdlib only)."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

ITERATIONS = 200_000
TOKEN_TTL = 3600

_secret = os.environ.get("TWIN_SECRET")
if not _secret:
    # Dev fallback: a random per-process secret, so tokens simply expire on restart.
    _secret = secrets.token_hex(32)
SECRET = _secret.encode()


def hash_password(password: str, iterations: int = ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations).hex()
    return f"{iterations}${salt.hex()}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        iterations, salt, digest = stored.split("$")
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, digest)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# Every token is bound to exactly one role. Customer ids and ops usernames live in different
# namespaces, so a token only ever works for the role it was issued for.
ROLES = ("customer", "ops")


def issue_token(subject, role: str = "customer") -> str:
    """Signed token: subject is a customer id (role "customer") or an ops username (role "ops")."""
    if role not in ROLES:
        raise ValueError("unknown role")
    sub = int(subject) if role == "customer" else str(subject)
    payload = _b64(json.dumps({"sub": sub, "role": role, "exp": int(time.time()) + TOKEN_TTL}).encode())
    sig = _b64(hmac.new(SECRET, payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def read_token(token: str, role: str = "customer"):
    """Return the subject of a valid, unexpired token issued for exactly `role`, else None.

    role "customer" -> the customer id (int); role "ops" -> the ops username (str).
    """
    if role not in ROLES:
        return None
    try:
        payload, sig = token.split(".")
        expected = _b64(hmac.new(SECRET, payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(_unb64(payload))
        if not isinstance(data, dict) or data.get("role") != role or data["exp"] < time.time():
            return None
        sub = data["sub"]
        if role == "customer":
            return sub if type(sub) is int and sub > 0 else None
        return sub if isinstance(sub, str) and sub else None
    except (ValueError, KeyError, TypeError, AttributeError, json.JSONDecodeError):
        return None
