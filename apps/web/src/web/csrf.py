"""Signed double-submit CSRF tokens.

The token is `<nonce>.<hmac(nonce)>`. It is sent as an HttpOnly,
SameSite=Strict cookie and echoed in a hidden form field. A request passes
when both copies match and the signature is ours.
"""

import hashlib
import hmac
import secrets

CSRF_COOKIE = "csrf_token"
CSRF_FIELD = "csrf_token"


def sign(nonce: str, secret: str) -> str:
    """Return the hex HMAC-SHA256 of a nonce."""
    return hmac.new(secret.encode(), nonce.encode(), hashlib.sha256).hexdigest()


def issue_token(secret: str) -> str:
    """Create a fresh signed token."""
    nonce = secrets.token_hex(16)
    return f"{nonce}.{sign(nonce, secret)}"


def is_signed(token: str, secret: str) -> bool:
    """Return True when the token carries a valid signature."""
    nonce, _, signature = token.partition(".")
    if not nonce or not signature:
        return False
    return hmac.compare_digest(signature.encode(), sign(nonce, secret).encode())


def is_valid(cookie: str | None, field: str | None, secret: str) -> bool:
    """Return True when cookie and form field match and are signed."""
    if not cookie or not field:
        return False
    if not hmac.compare_digest(cookie.encode(), field.encode()):
        return False
    return is_signed(cookie, secret)
