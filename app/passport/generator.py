import hashlib
import hmac
import json
import secrets
import sqlite3
from pathlib import Path
from typing import List, Optional

WORDS_FILE = Path(__file__).parent.parent / "words_ru.json"

DEFAULT_WORDS = {
    "adjectives": [
        "Бодрый", "Смелый", "Умный", "Быстрый", "Яркий", "Точный", "Добрый", "Зоркий",
        "Ловкий", "Мудрый", "Честный", "Верный", "Гордый", "Тихий", "Славный", "Чуткий",
        "Резвый", "Стойкий", "Ясный", "Сильный", "Вольный", "Мирный", "Храбрый", "Чудный"
    ],
    "nouns": [
        "Енот", "Сокол", "Барс", "Бобр", "Кит", "Лис", "Рысь", "Гриф",
        "Волк", "Тигр", "Заяц", "Кедр", "Стриж", "Грач", "Клёст", "Ёж",
        "Лось", "Морж", "Крач", "Ястреб", "Соболь", "Песец", "Беркут", "Дельфин"
    ],
    "recovery": [
        "маяк", "компас", "парус", "комета", "орбита", "кварц", "зенит", "фотон",
        "вулкан", "ледник", "океан", "тайга", "кристалл", "вектор", "импульс", "спектр",
        "планета", "галактика", "метеор", "спутник", "призма", "магнит", "радуга", "вершина"
    ]
}

def _load_words() -> dict:
    if WORDS_FILE.exists():
        try:
            return json.loads(WORDS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return DEFAULT_WORDS

def generate_callsign(wide_range: bool = False) -> str:
    words = _load_words()
    adj = secrets.choice(words["adjectives"]).capitalize()
    noun = secrets.choice(words["nouns"]).capitalize()
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
    words = _load_words()["recovery"]
    return [secrets.choice(words) for _ in range(count)]

def hash_secret(secret_text: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(16)
    normalized = " ".join(secret_text.strip().lower().split())
    dk = hashlib.pbkdf2_hmac("sha256", normalized.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${dk.hex()}"

def verify_secret(secret_text: str, stored_hash: str) -> bool:
    if not stored_hash or "$" not in stored_hash:
        return False
    salt, _ = stored_hash.split("$", 1)
    return hmac.compare_digest(hash_secret(secret_text, salt), stored_hash)
