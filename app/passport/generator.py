import secrets
import sqlite3
from typing import List, Optional

from app.passport.dictionaries import ADJECTIVES, NOUNS, RECOVERY_WORDS
from app.passport.crypto import (
    hash_secret as _hash_secret,
    verify_secret as _verify_secret,
    pick_recovery_words
)

def generate_callsign(wide_range: bool = False) -> str:
    """Генерация позывного «Прилагательное-Существительное-Код» из словарей Паспорта (Zero-PII)."""
    adj = secrets.choice(ADJECTIVES)
    noun = secrets.choice(NOUNS)
    num = (secrets.randbelow(9000) + 1000) if wide_range else (secrets.randbelow(900) + 100)
    return f"{adj}-{noun}-{num}"

def create_unique_callsign(conn: sqlite3.Connection, max_attempts: int = 20) -> str:
    for attempt in range(max_attempts):
        candidate = generate_callsign(wide_range=(attempt >= 10))
        row = conn.execute("SELECT 1 FROM users WHERE handle = ?", (candidate,)).fetchone()
        if not row:
            return candidate
    raise RuntimeError("Не удалось сгенерировать уникальный позывной")

def generate_recovery_words(count: int = 4) -> List[str]:
    """Выбор 4 секретных слов восстановления из словаря 512 слов (каждое несёт 9 бит энтропии)."""
    return pick_recovery_words(count)

def hash_secret(secret_text: str, salt: Optional[str] = None) -> str:
    return _hash_secret(secret_text, salt=salt, algo="pbkdf2")

def verify_secret(secret_text: str, stored_hash: str) -> bool:
    return _verify_secret(secret_text, stored_hash)
