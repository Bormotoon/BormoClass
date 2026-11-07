"""Криптография Паспорта: хэши секретов, подписанные токены, лимит попыток, коды активации.
Интегрировано из PedObraz (Zero-PII).
"""
import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Optional, List, Tuple, Dict, Any

from app.passport.dictionaries import RECOVERY_WORDS

# ── scrypt ────────────────────────────────────────────────────────────────────
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1
_scrypt_slots = threading.BoundedSemaphore(2)

def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

def _unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))

def _scrypt(secret: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    with _scrypt_slots:
        return hashlib.scrypt(secret.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32)

def scrypt_hash_secret(secret: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _scrypt(secret, salt, _SCRYPT_N, _SCRYPT_R, _SCRYPT_P)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64u(salt)}${_b64u(digest)}"

def pbkdf2_hash_secret(secret_text: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(16)
    normalized = " ".join(secret_text.strip().lower().split())
    dk = hashlib.pbkdf2_hmac("sha256", normalized.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${dk.hex()}"

def hash_secret(secret: str, salt: Optional[str] = None, algo: str = "pbkdf2") -> str:
    """Генерация хэша пароля/секрета. По умолчанию PBKDF2 (совместимость с BormoClass), либо scrypt."""
    if algo == "scrypt":
        return scrypt_hash_secret(secret)
    return pbkdf2_hash_secret(secret, salt)

def verify_secret(secret: str, stored: str) -> bool:
    """Проверка секрета. Автоматически поддерживает как scrypt (PedObraz), так и PBKDF2 (BormoClass)."""
    if not stored or "$" not in stored:
        return False
    if stored.startswith("scrypt$"):
        try:
            _, n, r, p, salt, digest = stored.split("$")
            got = _scrypt(secret, _unb64u(salt), int(n), int(r), int(p))
            return hmac.compare_digest(got, _unb64u(digest))
        except (ValueError, AttributeError):
            return False
    # PBKDF2 salt$hex
    try:
        salt, _ = stored.split("$", 1)
        normalized = " ".join(secret.strip().lower().split())
        dk = hashlib.pbkdf2_hmac("sha256", normalized.encode("utf-8"), salt.encode("utf-8"), 100_000)
        expected = f"{salt}${dk.hex()}"
        if hmac.compare_digest(expected, stored):
            return True
        # Проверка без lower
        dk_raw = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt.encode("utf-8"), 100_000)
        return hmac.compare_digest(f"{salt}${dk_raw.hex()}", stored)
    except Exception:
        return False

# ── слова восстановления ──────────────────────────────────────────────────────
_RECOVERY_SET = frozenset(RECOVERY_WORDS)

def pick_recovery_words(count: int = 4) -> List[str]:
    return secrets.SystemRandom().sample(RECOVERY_WORDS, count)

def normalize_words(words) -> Optional[str]:
    """Список или строка -> каноническая фраза либо None, если слова не из словаря."""
    if isinstance(words, str):
        words = words.split()
    if not isinstance(words, (list, tuple)) or len(words) != 4:
        return None
    norm = [str(w).strip().lower().replace("ё", "е") for w in words]
    return " ".join(norm) if all(w in _RECOVERY_SET for w in norm) else None

# ── подписанные токены (кука pb_pass и талоны) ────────────────────────────────
def sign(key: bytes, payload: dict) -> str:
    body = _b64u(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    mac = hmac.new(key, body.encode("utf-8"), hashlib.sha256).digest()
    return f"{body}.{_b64u(mac)}"

def unsign(key: bytes, token: str) -> Optional[dict]:
    try:
        body, mac = token.split(".")
        want = hmac.new(key, body.encode("utf-8"), hashlib.sha256).digest()
        if not hmac.compare_digest(want, _unb64u(mac)):
            return None
        payload = json.loads(_unb64u(body).decode("utf-8"))
    except (ValueError, AttributeError, Exception):
        return None
    return payload if isinstance(payload, dict) else None

def issue_ticket(key: bytes, now: float, **extra) -> str:
    return sign(key, {"iat": int(now), **extra})

def check_ticket(key: bytes, token: Optional[str], now: float, min_age: int = 2, max_age: int = 3600) -> Tuple[Optional[dict], Optional[str]]:
    payload = unsign(key, token) if isinstance(token, str) else None
    if payload is None or not isinstance(payload.get("iat"), int):
        return None, "bad_ticket"
    age = now - payload["iat"]
    if age < min_age:
        return None, "too_fast"
    if age > max_age:
        return None, "expired"
    return payload, None

# ── лимит попыток в памяти ────────────────────────────────────────────────────
class RateLimiter:
    """Скользящее окно по ключу (ник или действие, без IP по 152-ФЗ)."""
    def __init__(self, clock=time.time):
        self._clock = clock
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def _trim(self, key, window):
        q = self._hits[key]
        cutoff = self._clock() - window
        while q and q[0] <= cutoff:
            q.popleft()
        if not q:
            self._hits.pop(key, None)
        return q

    def blocked(self, key, limit, window):
        with self._lock:
            return len(self._trim(key, window)) >= limit

    def hit(self, key, window):
        with self._lock:
            self._trim(key, window)
            self._hits[key].append(self._clock())

    def reset(self, key):
        with self._lock:
            self._hits.pop(key, None)

# ── ключи активации PED-26-XXXX-XXXX-CC ───────────────────────────────────────
ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CODE_PREFIX = "PED-26"

def code_checksum(body: str) -> str:
    h = 0x811C9DC5
    for byte in body.encode("utf-8"):
        h = ((h ^ byte) * 0x01000193) & 0xFFFFFFFF
    v = h & 1023
    return ALPHABET[v >> 5] + ALPHABET[v & 31]

def format_code(body8: str) -> str:
    part1 = body8[:4]
    part2 = body8[4:]
    body = f"{CODE_PREFIX}-{part1}-{part2}"
    return f"{body}-{code_checksum(body)}"

def new_code() -> str:
    return format_code("".join(secrets.choice(ALPHABET) for _ in range(8)))

def normalize_code(raw: str) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    flat = "".join(ch for ch in raw.upper() if ch.isalnum())
    if len(flat) != 15 or not flat.startswith("PED26"):
        return None
    body, cc = flat[5:13], flat[13:]
    if any(ch not in ALPHABET for ch in body + cc):
        return None
    code = format_code(body)
    return code if code.endswith(cc) else None

def code_hash(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
