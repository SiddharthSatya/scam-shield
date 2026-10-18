"""Signed, short-lived check tokens.

/check-payment returns a token holding the money result; /context sends it back.
This keeps the API stateless (no database) and stops a caller from editing the
money score in between: any change breaks the signature.
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Any


class InvalidToken(ValueError):
    pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(body: str, secret: str) -> str:
    return _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())


def issue(payload: dict[str, Any], secret: str, ttl_seconds: int, now: float | None = None) -> str:
    now = time.time() if now is None else now
    body = _b64(json.dumps({**payload, "exp": int(now) + ttl_seconds}).encode())
    return f"{body}.{_sign(body, secret)}"


def verify(token: str, secret: str, now: float | None = None) -> dict[str, Any]:
    """Return the payload, or raise InvalidToken if tampered, malformed or expired."""
    try:
        body, signature = token.split(".")
    except ValueError as e:
        raise InvalidToken("malformed token") from e
    if not hmac.compare_digest(signature, _sign(body, secret)):
        raise InvalidToken("bad signature")
    try:
        payload = json.loads(_unb64(body))
    except ValueError as e:
        raise InvalidToken("malformed token") from e
    if payload.get("exp", 0) < (time.time() if now is None else now):
        raise InvalidToken("token expired")
    return payload
