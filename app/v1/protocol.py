import re
import hmac
import base64
import hashlib
from datetime import datetime, timezone
from typing import Any, Optional, Set
from fastapi import HTTPException
from app.config import settings

class GoogleAPIException(HTTPException):
    def __init__(self, http_code: int, status_str: str, message: str, reason: Optional[str] = None):
        details = [{"reason": reason}] if reason else []
        self.status_str = status_str
        self.error_message = message
        self.reason = reason
        self.error_payload = {
            "code": http_code,
            "message": message,
            "status": status_str,
            "details": details
        }
        super().__init__(
            status_code=http_code,
            detail={"detail": message, "error": self.error_payload}
        )

def api_error(http_code: int, status_str: str, message: str, reason: Optional[str] = None):
    raise GoogleAPIException(http_code, status_str, message, reason)

def camel_to_snake(s: str) -> str:
    return re.sub(r'(?<!^)(?=[A-Z])', '_', s).lower()

def snake_to_camel(s: str) -> str:
    parts = s.split('_')
    return parts[0] + ''.join(x.title() for x in parts[1:])

def parse_update_mask(update_mask: Optional[str], allowed_fields: Set[str]) -> Set[str]:
    if not update_mask:
        api_error(400, "INVALID_ARGUMENT", "updateMask обязателен", reason="INVALID_ARGUMENT")
    fields = [f.strip() for f in update_mask.split(",") if f.strip()]
    if not fields:
        api_error(400, "INVALID_ARGUMENT", "updateMask не содержит полей", reason="INVALID_ARGUMENT")
    
    allowed_snake = {camel_to_snake(f): f for f in allowed_fields}
    allowed_camel = {f: camel_to_snake(f) for f in allowed_fields}
    
    res = set()
    for f in fields:
        s = camel_to_snake(f)
        if s in allowed_snake or f in allowed_camel:
            res.add(s)
        else:
            api_error(400, "INVALID_ARGUMENT", f"Недопустимое поле в updateMask: {f}", reason="INVALID_ARGUMENT")
    return res

def _parse_fields_tree(fields_expr: str) -> dict:
    root: dict[str, Any] = {}
    stack = [root]
    current_token = []
    
    for ch in fields_expr:
        if ch == '(':
            key = "".join(current_token).strip()
            current_token = []
            if key:
                sub: dict[str, Any] = {}
                stack[-1][key] = sub
                stack.append(sub)
        elif ch == ')':
            key = "".join(current_token).strip()
            current_token = []
            if key:
                stack[-1][key] = {}
            if len(stack) > 1:
                stack.pop()
        elif ch == ',':
            key = "".join(current_token).strip()
            current_token = []
            if key:
                stack[-1][key] = {}
        elif not ch.isspace():
            current_token.append(ch)
            
    key = "".join(current_token).strip()
    if key:
        stack[-1][key] = {}
    return root

def _filter_dict(data: Any, spec: dict) -> Any:
    if not spec:
        return data
    if isinstance(data, list):
        return [_filter_dict(item, spec) for item in data]
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            if k in spec:
                subspec = spec[k]
                result[k] = _filter_dict(v, subspec) if subspec else v
        return result
    return data

def apply_fields_selector(payload: Any, fields_expr: Optional[str]) -> Any:
    if not fields_expr or fields_expr.strip() in ("", "*"):
        return payload
    try:
        spec = _parse_fields_tree(fields_expr)
        return _filter_dict(payload, spec)
    except Exception:
        return payload

def encode_page_token(offset: int, filter_fingerprint: str) -> str:
    payload = f"{offset}:{filter_fingerprint}"
    sig = hmac.new(settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()

def decode_page_token(page_token: Optional[str], filter_fingerprint: str) -> int:
    if not page_token:
        return 0
    try:
        raw = base64.urlsafe_b64decode(page_token.encode()).decode()
        parts = raw.split(":")
        if len(parts) != 3:
            api_error(400, "INVALID_ARGUMENT", "Недействительный pageToken", reason="INVALID_ARGUMENT")
        offset_str, token_fp, sig = parts
        expected_payload = f"{offset_str}:{token_fp}"
        expected_sig = hmac.new(settings.SECRET_KEY.encode(), expected_payload.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected_sig):
            api_error(400, "INVALID_ARGUMENT", "Подпись pageToken недействительна", reason="INVALID_ARGUMENT")
        if token_fp != filter_fingerprint:
            api_error(400, "INVALID_ARGUMENT", "Фильтры запроса изменились для данного pageToken", reason="INVALID_ARGUMENT")
        return int(offset_str)
    except GoogleAPIException:
        raise
    except Exception:
        api_error(400, "INVALID_ARGUMENT", "Недействительный pageToken", reason="INVALID_ARGUMENT")

def resolve_user_id(conn, raw_user_id: str, current_user: dict, allow_wildcard: bool = False):
    if raw_user_id == "me":
        return current_user["id"]
    if raw_user_id == "-":
        if allow_wildcard:
            return "-"
        api_error(400, "INVALID_ARGUMENT", "Wildcard '-' не поддерживается для данного метода", reason="INVALID_ARGUMENT")
    try:
        uid = int(raw_user_id)
        row = conn.execute("SELECT id FROM users WHERE id = ?", (uid,)).fetchone()
        if row:
            return row["id"]
    except ValueError:
        pass
    row = conn.execute("SELECT id FROM users WHERE handle = ?", (raw_user_id,)).fetchone()
    if row:
        return row["id"]
    api_error(404, "NOT_FOUND", f"Пользователь '{raw_user_id}' не найден", reason="USER_NOT_FOUND")

def resolve_class_id(conn, raw_course_id: str, client_id: str = "first_party") -> int:
    if raw_course_id.startswith("d:"):
        row = conn.execute("SELECT class_id FROM course_aliases WHERE alias_key = ?", (raw_course_id,)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", f"Курс с псевдонимом '{raw_course_id}' не найден", reason="COURSE_NOT_FOUND")
        return row["class_id"]
    if raw_course_id.startswith("p:"):
        row = conn.execute(
            "SELECT class_id FROM course_aliases WHERE alias_key = ? AND (client_id = ? OR client_id = 'first_party')",
            (raw_course_id, client_id)
        ).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", f"Курс с псевдонимом '{raw_course_id}' не найден для клиента '{client_id}'", reason="COURSE_NOT_FOUND")
        return row["class_id"]
    try:
        cid = int(raw_course_id)
        row = conn.execute("SELECT id FROM classes WHERE id = ?", (cid,)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", f"Курс '{raw_course_id}' не найден", reason="COURSE_NOT_FOUND")
        return row["id"]
    except ValueError:
        api_error(404, "NOT_FOUND", f"Некорректный идентификатор курса '{raw_course_id}'", reason="COURSE_NOT_FOUND")

def ts_to_rfc3339(ts: Optional[int]) -> Optional[str]:
    if ts is None:
        return None
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def rfc3339_to_ts(s: Optional[str]) -> Optional[int]:
    if not s:
        return None
    cleaned = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
        return int(dt.timestamp())
    except Exception:
        return None

def date_to_dict(ts: Optional[int]) -> Optional[dict]:
    if ts is None:
        return None
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return {"year": dt.year, "month": dt.month, "day": dt.day}

def time_of_day_to_dict(ts: Optional[int]) -> Optional[dict]:
    if ts is None:
        return None
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return {"hours": dt.hour, "minutes": dt.minute, "seconds": dt.second, "nanos": 0}

def date_time_to_ts(date_dict: Optional[dict], time_dict: Optional[dict]) -> Optional[int]:
    if not date_dict:
        return None
    year = date_dict.get("year", 2026)
    month = date_dict.get("month", 1)
    day = date_dict.get("day", 1)
    hours = time_dict.get("hours", 23) if time_dict else 23
    minutes = time_dict.get("minutes", 59) if time_dict else 59
    seconds = time_dict.get("seconds", 59) if time_dict else 59
    dt = datetime(year, month, day, hours, minutes, seconds, tzinfo=timezone.utc)
    return int(dt.timestamp())
