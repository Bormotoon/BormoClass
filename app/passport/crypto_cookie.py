import base64
import hmac
import hashlib
import json
import sqlite3
import time
from typing import Optional, Dict, Any
from app.config import settings

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")

def _b64url_decode(s: str) -> bytes:
    padding = 4 - (len(s) % 4)
    if padding and padding < 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s.encode("utf-8"))

def sign_cookie_payload(payload: Dict[str, Any], ttl_seconds: int = 30 * 86400) -> str:
    data = dict(payload)
    if "exp" not in data:
        data["exp"] = int(time.time()) + ttl_seconds
    raw_json = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload_b64 = _b64url_encode(raw_json)
    signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256
    ).digest()
    sig_b64 = _b64url_encode(signature)
    return f"{payload_b64}.{sig_b64}"

def verify_cookie_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token or "." not in token:
        return None
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        expected_sig = hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            payload_b64.encode("utf-8"),
            hashlib.sha256
        ).digest()
        provided_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, provided_sig):
            return None
        raw_json = _b64url_decode(payload_b64)
        data = json.loads(raw_json.decode("utf-8"))
        if data.get("exp", 0) < int(time.time()):
            return None
        return data
    except Exception:
        return None
