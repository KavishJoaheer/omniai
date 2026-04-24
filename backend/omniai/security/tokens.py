from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def create_session_token(payload: dict[str, Any], secret: str) -> str:
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded_payload = _b64encode(payload_bytes)
    signature = hmac.new(secret.encode("utf-8"), encoded_payload.encode("utf-8"), hashlib.sha256).digest()
    return f"sess.{encoded_payload}.{_b64encode(signature)}"


def verify_session_token(token: str, secret: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "sess":
        raise ValueError("Invalid session token format.")

    encoded_payload = parts[1]
    encoded_signature = parts[2]
    expected_signature = _b64encode(
        hmac.new(secret.encode("utf-8"), encoded_payload.encode("utf-8"), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(expected_signature, encoded_signature):
        raise ValueError("Invalid session token signature.")

    payload = json.loads(_b64decode(encoded_payload).decode("utf-8"))
    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("Session token has expired.")
    return payload
