# MASTER TODO: Разработка автономной платформы BormoClass (Zero-PII Classroom + Passport + Interactive Board)

> **Профиль спецификации:** Оптимизировано для детерминированной кодогенерации **Gemini 3.8 Flash** (пакетная генерация без холостых вызовов инструментов).  
> **Архитектурный стандарт:** Zero-PII (152-ФЗ РФ — $0\text{ байт}$ персональных данных на сервере), Zero-Bloat (один процесс Python FastAPI + SQLite WAL, $0$ внешних CDN, клиентский бандл $\le 15\text{ КБ}$ Vanilla JS + CSS Material Design 3.0 `Ember Newsroom` `#f57300`).

---

## 0. Системные инварианты и правила для AI-агента (System Prompt Rules)

При выполнении любого пункта из данного `bormoclass_todo.md` модель обязана соблюдать следующие жёсткие ограничения:

1. **Запрет на внешние зависимости и тяжёлые рантаймы:**
   * Никаких контейнеров PostgreSQL, Redis, Celery, Supabase, Node.js SSR.
   * Никаких ИИ-коннекторов, серверных генераторов `DOCX`/`XLSX` и встроенных тяжёлых WASM-песочниц (Pyodide/ArtCraft) внутри репозитория. Тренажёры подключаются исключительно через лёгкий JS-мост `pb-passport-bridge.js` (`iframe` + `postMessage` + `/api/passport/solve`).
   * Никаких внешних CDN (Google Fonts, Bootstrap, unpkg, cdnjs, jsdelivr). Все шрифты (локальный сабсет `190 КБ`) и SVG-иконки раздаются локально.
2. **Абсолютный инвариант Zero-PII (152-ФЗ):**
   * В таблицах SQLite, Pydantic-моделях, куках и логах **физически запрещены** поля: `full_name`, `first_name`, `last_name`, `middle_name`, `patronymic`, `fio`, `name`, `email`, `mail`, `phone`, `tel`, `birth_year`, `birth_date`, `birthday`, `gender`, `sex`, `ip`, `ip_address`, `passport`.
   * В UI ученика **запрещены** свободные текстовые поля (`<input type="text">`) при регистрации и входе в класс, куда ребёнок мог бы случайно вписать свою фамилию или телефон.
   * Реальные фамилии учеников хранятся исключительно в поле `encrypted_note` в виде шифротекста `AES-GCM` ($256\text{ бит}$), ключ от которого живёт только в браузере учителя (`localStorage` / парольная фраза в памяти с индивидуальной солью `teacher_id`).
3. **Полноценный `pedobraz-passport` и биллинг внутри ядра:**
   * Подсистема паспорта реализуется **в полном объёме (1-в-1)**: генератор словарных позывных (`Прилагательное-Существительное-Код`) с защитой от коллизий, самодостаточный формат хэшей `salt$hash` (`PBKDF2-HMAC-SHA256`), пароль + $4$ секретных слова восстановления, stateless-кука `pb_pass` (`HMAC-SHA256`), игровой кошелёк `recess_seconds` («Билет на перемену») с защитой от повторного начисления (анти-фарм), подписка учителя `pro_until` + 7-дневный авто-триал (`trial_used`) + таблица пин-кодов `license_keys` (активирующая флаг `ad_free: true` для всего класса и глобальный метод `window.pbPassport.isAdFree()`).
4. **Неблокирующая работа SQLite WAL и SSE-потоков:**
   * Все HTTP-роуты FastAPI, обращающиеся к синхронному контекстному менеджеру `db_session()`, **обязаны** объявляться как обычные синхронные функции `def` (не `async def`), чтобы Uvicorn исполнял их в `threadpool` и никогда не блокировал главный `asyncio` event loop.
   * Как `async def` объявляются **только** маршруты Server-Sent Events (`/api/classroom/{class_id}/stream` и `/api/board/{class_id}/stream`), работающие через асинхронные очереди `asyncio.Queue` в `sse_hub.py`.

---

## 1. Целевая файловая структура репозитория `bormoclass`

```text
bormoclass/
├── LICENSE                                  # Лицензия Apache-2.0
├── README.md                                # Документация проекта и Zero-PII архитектуры
├── .env.example                             # Конфигурация (SECRET_KEY, COOKIE_DOMAIN, PORT=8010)
├── requirements.txt                         # Только fastapi, uvicorn[standard], pydantic, pytest, httpx
├── Dockerfile                               # Образ python:3.12-slim
├── docker-compose.yml                       # Связка bormoclass (8010) + caddy (80/443)
├── manage_codes.py                          # CLI-генератор и сидер PRO-ключей (--seed-dev-codes, --generate)
├── edge/
│   └── Caddyfile                            # Прокси, sendfile, zstd/gzip, отключённый буфер для обоих SSE-потоков
│
├── app/
│   ├── __init__.py
│   ├── main.py                              # Инициализация FastAPI, статики, мидлвари pb_pass и роутеров
│   ├── config.py                            # Настройки из окружения и возрастные константы СанПиН
│   ├── db.py                                # Менеджер SQLite WAL (busy_timeout=5000) + авто-миграция при старте
│   ├── schema.sql                           # Полная схема из 10 таблиц (6 Passport/Billing + 4 Classroom)
│   ├── words_ru.json                        # Расширенные словари прилагательных, существительных и слов восстановления
│   │
│   ├── passport/                            # ПОЛНАЯ РЕАЛИЗАЦИЯ PEDOBRAZ-PASSPORT + БИЛЛИНГ
│   │   ├── __init__.py
│   │   ├── crypto_cookie.py                 # Подпись и stateless-верификация куки pb_pass (HMAC-SHA256)
│   │   ├── generator.py                     # Генерация уникального позывного, пароля, 4 слов и salt$hash
│   │   ├── middleware.py                    # Чтение pb_pass, инжект request.state.user и расчёт ad_free
│   │   ├── recess.py                        # Идемпотентный кошелёк recess_seconds и блокировка на контрольной
│   │   └── router.py                        # /api/passport/* (register, login, recover, solve, recess, activate-code, trial)
│   │
│   ├── classroom/                           # ЯДРО GOOGLE CLASSROOM + ШКОЛЬНЫЕ ФУНКЦИИ РФ
│   │   ├── __init__.py
│   │   ├── router_classes.py                # Классы, 5-значный пин-код, схема 3 рядов парт (1..40), присутствие, сброс пароля
│   │   ├── router_coursework.py             # Лента, темы, задания, квизы, Reuse post, фильтр ДЗ 1-го класса
│   │   ├── router_submissions.py            # Сдача работ, рубрики, шкала 2..5, банк комментариев, расчёт СОУ
│   │   ├── router_global.py                 # Глобальные вкладки "На проверку" (To review), "Список дел" (To-do), Календарь
│   │   ├── router_board.py                  # Состояние встроенной интерактивной доски и "Светофора понимания"
│   │   └── sse_hub.py                       # Асинхронный SSE-брокер для живой матрицы оценок и доски
│   │
│   └── static/
│       ├── index.html                       # Главный SPA-интерфейс BormoClass (Классы, 4 вкладки, To-do, To-review)
│       ├── board.html                       # Встроенная интерактивная школьная доска (замена page-board.php)
│       ├── css/
│       │   ├── md3-tokens.css               # Системные токены Material Design 3.0 (Ember Newsroom #f57300, Light/Dark)
│       │   ├── app.css                      # Стили карточек, 4 вкладок, схемы парт, печатных листов А4 и матрицы оценок
│       │   └── board.css                    # Стили холста доски, сетки (клетка/линейка), QR-оверлея и Колеса вызова
│       ├── fonts/
│       │   └── material-symbols-subset.woff2# Локальный сабсет 190 КБ (123 иконки)
│       └── js/
│           ├── icons.js                     # Карта инлайновых SVG-контуров (портировано из inc/icons.php)
│           ├── pb-passport-bridge.js        # Полный клиентский мост (window.pbPassport), виджет входа и фильтр postMessage
│           ├── webcrypto-vault.js           # Браузерное шифрование/расшифровка имён учеников (AES-GCM 256-bit + экспорт JWK)
│           ├── bormoclass-app.js            # Ядро интерфейса классов (~15 КБ Vanilla JS, View Transitions, SSE, СОУ, CSV)
│           ├── board-app.js                 # Логика интерактивной доски (2D Canvas, слои, Колесо вызова, Светофор, SVG QR)
│           └── sanpin-timer.js              # Контроль непрерывного экранного времени по СанПиН 1.2.3685-21
│
└── tests/
    ├── test_zero_pii_invariants.py          # Строгий автотест отсутствия ПД в БД, сериализаторах и шаблонах
    ├── test_passport_flow.py                # Тесты куки pb_pass, 4 слов, идемпотентности recess_seconds, триала и пин-кодов
    └── test_classroom_and_sou.py            # Тесты выдачи заданий, блокировки ДЗ 1 класса, шкалы 2..5 и расчёта СОУ
```

---

## 2. Пошаговый план реализации с эталонным кодом

### ЭТАП 1: База данных SQLite WAL и полная схема (10 таблиц)

- [ ] **Задача 1.1:** Создать файл `app/schema.sql`, объединяющий 6 таблиц контура `pedobraz-passport` (`users`, `license_keys`, `classes`, `class_members`, `assignments`, `solved_tasks`) и 4 таблицы расширения `BormoClass` (`class_topics`, `coursework`, `submissions`, `comment_bank`).
- [ ] **Задача 1.2:** Создать модуль `app/db.py` с разделением персистентных прагм инициализации (`WAL`, `synchronous=NORMAL`, `mmap_size`) и быстрых пер-коннектных прагм (`foreign_keys=ON`, `busy_timeout=5000`, `temp_store=MEMORY`).

#### Эталонный код `app/schema.sql`:
```sql
-- ============================================================================
-- БЛОК 1: ТАБЛИЦЫ PEDOBRAZ-PASSPORT И БИЛЛИНГА (6 ТАБЛИЦ, 100% СОВМЕСТИМОСТЬ)
-- ============================================================================

-- 1. Безымянные паспорта пользователей (0 байт ПД)
CREATE TABLE IF NOT EXISTS users (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    handle              TEXT NOT NULL UNIQUE,           -- Позывной: "Бодрый-Енот-428"
    role                TEXT NOT NULL DEFAULT 'student',-- 'student' | 'teacher' | 'admin'
    password_hash       TEXT NOT NULL,                  -- Формат "salt$hex" (PBKDF2-HMAC-SHA256)
    recovery_words_hash TEXT NOT NULL,                  -- Формат "salt$hex" от 4 секретных слов восстановления
    avatar_seed         INTEGER NOT NULL DEFAULT 1,     -- Сид генерации геометрического/звериного аватара
    recess_seconds      INTEGER NOT NULL DEFAULT 0,     -- Баланс игрового кошелька "Билет на перемену"
    pro_until           INTEGER NOT NULL DEFAULT 0,     -- Unix-timestamp подписки "Пульт учителя" (дает ad_free классу)
    trial_used          INTEGER NOT NULL DEFAULT 0,     -- 0 = доступен 7-дневный триал, 1 = триал уже использован
    created_at          INTEGER NOT NULL
);

-- 2. Оффлайн-ключи активации подписки "Пульт учителя" (0 байт ПД)
CREATE TABLE IF NOT EXISTS license_keys (
    code          TEXT PRIMARY KEY,                     -- Код формата "PED-26-K8M4-P9X2-7F"
    tariff        TEXT NOT NULL DEFAULT 'month',        -- 'month' (30 дней) | 'year' (365 дней)
    duration_days INTEGER NOT NULL DEFAULT 30,
    used_by       INTEGER REFERENCES users(id) ON DELETE SET NULL,
    used_at       INTEGER,
    created_at    INTEGER NOT NULL
);

-- 3. Учебные классы
CREATE TABLE IF NOT EXISTS classes (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title                TEXT NOT NULL,                 -- Например: "8А — Информатика"
    subject_code         TEXT NOT NULL DEFAULT 'inf',   -- Код предмета
    grade_level          INTEGER NOT NULL DEFAULT 8 CHECK (grade_level BETWEEN 1 AND 11),
    join_pin             TEXT NOT NULL UNIQUE,          -- 5-значный пин-код для входа с интерактивной доски
    quarter_goal         TEXT NOT NULL DEFAULT '',      -- "Цель класса на четверть" в шапке Ленты
    recess_locked_until  INTEGER NOT NULL DEFAULT 0,    -- Рубильник блокировки игр на время контрольной
    classroom_state_json TEXT NOT NULL DEFAULT '{}',    -- JSON: рассадка 3 рядов парт, слайды доски и состояние
    created_at           INTEGER NOT NULL
);

-- 4. Участники класса, номера парт и клиентский шифротекст учителя
CREATE TABLE IF NOT EXISTS class_members (
    class_id       INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    student_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    seat_number    INTEGER NOT NULL CHECK (seat_number BETWEEN 1 AND 40), -- Номер парты (1..40)
    encrypted_note TEXT NOT NULL DEFAULT '',            -- AES-GCM шифротекст с ФИО (ключ только в браузере учителя)
    is_present     INTEGER NOT NULL DEFAULT 1,          -- Присутствие на уроке (1 = на месте, 0 = отсутствует)
    traffic_light  TEXT NOT NULL DEFAULT 'green',       -- 'green' (понятно) | 'yellow' (вопрос) | 'red' (нужна помощь)
    joined_at      INTEGER NOT NULL,
    PRIMARY KEY (class_id, student_id),
    UNIQUE (class_id, seat_number)
);

-- 5. Базовые назначения задач тренажёров (таблица совместимости pedobraz-passport)
CREATE TABLE IF NOT EXISTS assignments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id      INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    title         TEXT NOT NULL,
    task_ids_json TEXT NOT NULL DEFAULT '[]',           -- Массив строковых task_id внешних тренажёров
    recess_reward INTEGER NOT NULL DEFAULT 300,         -- Награда в секундах за решение
    due_at        INTEGER,
    created_at    INTEGER NOT NULL
);

-- 6. Базовый лог решённых задач тренажёров (таблица совместимости pedobraz-passport)
CREATE TABLE IF NOT EXISTS solved_tasks (
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    task_id       TEXT NOT NULL,                        -- Идентификатор задачи тренажёра (например, "kege-15-042")
    class_id      INTEGER REFERENCES classes(id) ON DELETE SET NULL,
    score         INTEGER NOT NULL DEFAULT 100,
    solved_at     INTEGER NOT NULL,
    PRIMARY KEY (user_id, task_id)
);

-- ============================================================================
-- БЛОК 2: ТАБЛИЦЫ ЯДРА BORMOCLASS (GOOGLE CLASSROOM MODEL)
-- ============================================================================

-- 7. Темы внутри класса (Topics)
CREATE TABLE IF NOT EXISTS class_topics (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id     INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    frp_topic_id TEXT,                                  -- Опциональный код темы по ФРП ЕДСОО
    sort_order   INTEGER NOT NULL DEFAULT 0
);

-- 8. Поток объявлений и заданий (Stream & Classwork)
CREATE TABLE IF NOT EXISTS coursework (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id         INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    topic_id         INTEGER REFERENCES class_topics(id) ON DELETE SET NULL,
    kind             TEXT NOT NULL DEFAULT 'assignment', -- 'announcement' | 'assignment' | 'quiz' | 'question' | 'material'
    title            TEXT NOT NULL,
    instructions     TEXT NOT NULL DEFAULT '',
    attachments_json TEXT NOT NULL DEFAULT '[]',         -- [{"task_id":"py_01","url":"/pythonteaching/","mode":"copy"}]
    rubric_json      TEXT NOT NULL DEFAULT '[]',         -- Критерии оценивания [{"id": "c1", "title": "...", "max": 2}]
    target_students  TEXT NOT NULL DEFAULT 'all',        -- 'all' или JSON-массив student_id
    max_points       INTEGER NOT NULL DEFAULT 5,         -- Максимальный балл (по умолчанию 5 или 100)
    recess_reward    INTEGER NOT NULL DEFAULT 300,       -- Секунды в кошелёк "Билета на перемену"
    is_homework      INTEGER NOT NULL DEFAULT 0,         -- 1 = ДЗ (автоматически блокируется при grade_level = 1)
    state            TEXT NOT NULL DEFAULT 'published',  -- 'draft' | 'scheduled' | 'published'
    scheduled_at     INTEGER,
    due_at           INTEGER,
    created_at       INTEGER NOT NULL
);

-- 9. Сдачи работ учениками и ведомость оценок (Submissions & Gradebook)
CREATE TABLE IF NOT EXISTS submissions (
    coursework_id   INTEGER NOT NULL REFERENCES coursework(id) ON DELETE CASCADE,
    student_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status          TEXT NOT NULL DEFAULT 'assigned',    -- 'assigned' | 'turned_in' | 'returned'
    payload_json    TEXT NOT NULL DEFAULT '{}',          -- Текстовый ответ, ответы квиза или отчёт от pb-passport-bridge.js
    rubric_scores   TEXT NOT NULL DEFAULT '{}',          -- Баллы по критериям {"c1": 2}
    grade_points    INTEGER,                             -- Выставленный первичный балл (0..max_points)
    grade_five      INTEGER CHECK (grade_five IS NULL OR grade_five BETWEEN 2 AND 5), -- Оценка по шкале РФ (2..5)
    teacher_comment TEXT NOT NULL DEFAULT '',
    updated_at      INTEGER NOT NULL,
    PRIMARY KEY (coursework_id, student_id)
);

-- 10. Личный банк комментариев учителя (Comment Bank)
CREATE TABLE IF NOT EXISTS comment_bank (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    comment_text TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_class_members_student ON class_members(student_id);
CREATE INDEX IF NOT EXISTS idx_coursework_class ON coursework(class_id, state);
CREATE INDEX IF NOT EXISTS idx_submissions_student ON submissions(student_id, status);
```

#### Эталонный код `app/db.py`:
```python
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from app.config import settings

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DB_PATH, timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    return conn

@contextmanager
def db_session():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db() -> None:
    Path(settings.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with db_session() as conn:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA mmap_size = 268435456;")
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
```

---

### ЭТАП 2: Полная реализация `pedobraz-passport` и биллинга внутри BormoClass

- [ ] **Задача 2.1:** Реализовать генератор словарных позывных (`app/passport/generator.py`) с проверкой уникальности в БД (до $20$ попыток с расширением диапазона до $1000\dots 9999$ при коллизии) и самодостаточными функциями `hash_secret` / `verify_secret` (формат `salt$hex`).
- [ ] **Задача 2.2:** Реализовать stateless-подпись и валидацию First-Party куки `pb_pass` через `HMAC-SHA256` (`app/passport/crypto_cookie.py`) и функцию `compute_user_ad_free(conn, user_id, role)`:
  * Если `role == 'teacher'`, возвращает `True`, когда `users.pro_until > now`.
  * Если `role == 'student'`, возвращает `True`, когда `users.pro_until > now` ИЛИ ученик состоит хотя бы в одном классе (`class_members`), у учителя которого `pro_until > now`.
- [ ] **Задача 2.3:** Реализовать систему активации PRO-кодов (`POST /api/passport/activate-code`), 7-дневного авто-триала учителя и CLI-утилиту `manage_codes.py` (`--seed-dev-codes`, `--generate N --tariff month|year`):
  * Если учитель с `trial_used == 0` и `pro_until == 0` выполняет мутирующий учительский запрос (например, создание класса или включение триала), автоматически выставлять `trial_used = 1`, `pro_until = now + 7 * 86400`, перевыпускать куку `pb_pass` с `ad_free=True` и добавлять HTTP-заголовок `X-Passport-Trial-Started: 1`.
- [ ] **Задача 2.4:** Реализовать идемпотентный эндпоинт `POST /api/passport/solve`:
  * Принимает `task_id`, `score` ($0\dots 100$) и опциональный `coursework_id`.
  * Выполняет `INSERT OR IGNORE INTO solved_tasks (user_id, task_id, class_id, score, solved_at) VALUES (?, ?, ?, ?, ?)`.
  * **Защита от фарма:** Секунды `recess_reward` начисляются в `users.recess_seconds` **только** если `cursor.rowcount == 1` (задача решена впервые) ИЛИ если связанная запись в `submissions` переходит из статуса `'assigned'` в `'turned_in'`.
  * Переводит процент выполнения в пятибалльную оценку РФ (`<50 -> 2`, `50..69 -> 3`, `70..84 -> 4`, `>=85 -> 5`), сохраняет в `submissions` и рассылает SSE-событие `submission_updated` в живую матрицу учителя.

#### Эталонный код `app/passport/generator.py`:
```python
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
        return json.loads(WORDS_FILE.read_text(encoding="utf-8"))
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
```

- [ ] **Задача 2.5:** Написать обязательный сторожевой тест `tests/test_zero_pii_invariants.py`, проверяющий все $10$ таблиц SQLite и отсутствие внешних CDN в статических файлах.

#### Эталонный код `tests/test_zero_pii_invariants.py`:
```python
from pathlib import Path
from app.db import init_db, db_session

FORBIDDEN_COLUMNS = {
    "full_name", "first_name", "last_name", "middle_name", "patronymic",
    "fio", "name", "email", "mail", "phone", "tel", "birth_year",
    "birth_date", "birthday", "gender", "sex", "ip", "ip_address", "passport"
}

FORBIDDEN_CDN_HOSTS = (
    "googleapis.com", "gstatic.com", "jsdelivr.net", "unpkg.com",
    "cdnjs.cloudflare.com", "stackpath.bootstrapcdn.com", "code.jquery.com"
)

def test_sqlite_schema_has_zero_pii_columns():
    init_db()
    with db_session() as conn:
        tables = [
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if not row["name"].startswith("sqlite_")
        ]
        assert len(tables) >= 10, "Должны быть созданы все 10 таблиц (6 Passport/Billing + 4 Classroom)"
        for table in tables:
            cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
            col_names = {c["name"].lower() for c in cols}
            violations = col_names.intersection(FORBIDDEN_COLUMNS)
            assert not violations, f"Нарушение 152-ФЗ (Zero-PII) в таблице {table}: найдены поля {violations}"

def test_static_files_have_zero_external_cdns():
    static_dir = Path(__file__).parent.parent / "app" / "static"
    for path in static_dir.rglob("*"):
        if path.suffix in {".html", ".css", ".js"}:
            content = path.read_text(encoding="utf-8").lower()
            for host in FORBIDDEN_CDN_HOSTS:
                assert host not in content, f"Нарушение 152-ФЗ: внешний CDN {host} найден в {path.name}"
```

---

### ЭТАП 3: Клиентское Zero-Knowledge шифрование (`AES-GCM`) и мост `pb-passport-bridge.js`

- [ ] **Задача 3.1:** Реализовать модуль `app/static/js/webcrypto-vault.js` с привязкой соли `PBKDF2` к `teacherId` и функциями экспорта/импорта JWK-ключа.
- [ ] **Задача 3.2:** Реализовать `app/static/js/pb-passport-bridge.js`:
  * Экспортирует глобальный объект `window.pbPassport = { isAdFree: () => Boolean(state.ad_free), getUser: () => state.user, solveTask: (taskId, score, cwId) => ... }`.
  * Проверяет `event.origin === window.location.origin` при приёме `postMessage` (`{ type: "PB_TASK_SOLVED", task_id, score, coursework_id }`).
  * При `ad_free === true` выставляет `document.documentElement.setAttribute("data-ad-free", "true")`.

#### Эталонный код `app/static/js/webcrypto-vault.js`:
```javascript
export class TeacherZeroKnowledgeVault {
  constructor(teacherId = "default") {
    this.teacherId = String(teacherId);
    this.storageKey = `bc_teacher_aes_jwk_${this.teacherId}`;
    this.cryptoKey = null;
  }

  async initOrLoadKey(passphrase = null) {
    if (passphrase) {
      const enc = new TextEncoder();
      const keyMaterial = await crypto.subtle.importKey(
        "raw",
        enc.encode(passphrase),
        { name: "PBKDF2" },
        false,
        ["deriveKey"]
      );
      this.cryptoKey = await crypto.subtle.deriveKey(
        {
          name: "PBKDF2",
          salt: enc.encode(`bormoclass-zero-pii-salt-v1-${this.teacherId}`),
          iterations: 100000,
          hash: "SHA-256",
        },
        keyMaterial,
        { name: "AES-GCM", length: 256 },
        true,
        ["encrypt", "decrypt"]
      );
      const jwk = await crypto.subtle.exportKey("jwk", this.cryptoKey);
      localStorage.setItem(this.storageKey, JSON.stringify(jwk));
      return true;
    }

    const saved = localStorage.getItem(this.storageKey);
    if (saved) {
      this.cryptoKey = await crypto.subtle.importKey(
        "jwk",
        JSON.parse(saved),
        { name: "AES-GCM" },
        true,
        ["encrypt", "decrypt"]
      );
      return true;
    }
    return false;
  }

  async encryptStudentName(plainName) {
    if (!this.cryptoKey) throw new Error("Ключ учителя не инициализирован");
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const encoded = new TextEncoder().encode(plainName.trim());
    const cipherBuf = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, this.cryptoKey, encoded);
    const ivB64 = btoa(String.fromCharCode(...iv));
    const cipherB64 = btoa(String.fromCharCode(...new Uint8Array(cipherBuf)));
    return `${ivB64}:${cipherB64}`;
  }

  async decryptStudentName(encryptedNote) {
    if (!encryptedNote || !encryptedNote.includes(":") || !this.cryptoKey) return null;
    try {
      const [ivB64, cipherB64] = encryptedNote.split(":");
      const iv = Uint8Array.from(atob(ivB64), (c) => c.charCodeAt(0));
      const cipher = Uint8Array.from(atob(cipherB64), (c) => c.charCodeAt(0));
      const plainBuf = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, this.cryptoKey, cipher);
      return new TextDecoder().decode(plainBuf);
    } catch {
      return "🔒 [Неверный ключ]";
    }
  }
}
```

---

### ЭТАП 4: Встроенная интерактивная школьная доска (`board.html` + `board-app.js` + `router_board.py`)

- [ ] **Задача 4.1:** Сверстать интерфейс доски `app/static/board.html` и стили `app/static/css/board.css` в палитре Material Design 3.0 (`Ember Newsroom`), адаптированный под разрешение школьных интерактивных панелей ($1920\times 1080$, крупные зоны нажатия $\ge 48\text{ px}$).
- [ ] **Задача 4.2:** Реализовать в `app/static/js/board-app.js` графическое ядро на HTML5 2D Canvas:
  * **Инструменты рисования:** Маркер ($4$ цвета + толщина), Текстовый выделитель (полупрозрачный), Ластик, Прямая линия, Прямоугольник, Координатная ось, Очистка слайда, история `Undo` / `Redo` (до $30$ шагов), поддержка многостраничных слайдов урока (`Слайд 1 / N`) с сохранением в `classes.classroom_state_json`.
  * **Фоновые сетки для школы:** Переключение фона в 1 клик: «Чистый лист», «Тетрадная клетка», «Широкая линейка», «Координатная сетка», «Тёмная графитовая доска».
- [ ] **Задача 4.3:** Встроить в верхнюю панель интерактивной доски 5 фирменных виджетов управления уроком:
  1. **Оверлей «Код класса и QR на весь экран»:** Выводит поверх доски крупный 5-значный `join_pin`, автономный векторный SVG QR-код и живой счётчик подключившихся парт.
  2. **Виджет «Умное колесо вызова к доске»:** Выбирает случайного ученика строго из числа присутствующих (`is_present = 1`), ещё не вызывавшихся за урок, с локальной расшифровкой имени через `TeacherZeroKnowledgeVault`.
  3. **Живой индикатор «Светофор понимания»:** Отображает сводную полоску (`🟢 Всё понятно`, `🟡 Есть вопрос`, `🔴 Нужна помощь`), мгновенно обновляемую через SSE `/api/board/{class_id}/stream`.
  4. **Таймер норм СанПиН 1.2.3685-21 (`sanpin-timer.js`):** Отсчитывает непрерывное время работы с экраном по параллели (`1..2` класс — $20\text{ мин}$, `3..4` класс — $25\text{ мин}$, `5..9` класс — $30\text{ мин}$, `10..11` класс — $35\text{ мин}$).
  5. **Рубильник «Контрольная работа (Блокировка перемены)»:** Одним кликом выставляет `recess_locked_until`, замораживая трату секунд «Билета на перемену» у всего класса.

---

### ЭТАП 5: Четырёхвкладочное ядро Google Classroom, бумажный дублёр А4 и школьная аналитика РФ

- [ ] **Задача 5.1:** Реализовать глобальные экраны навигации (`app/classroom/router_global.py` + `bormoclass-app.js`):
  * **Главная витрина классов:** Карточки классов в стиле MD3 (`border-radius: 24px`), создание класса, вход ученика по 5-значному пин-коду и выбор номера парты ($1\dots 40$) по клику на сетку парт (без текстового ввода).
  * **Режим учителя «На проверку» (`To review`):** Сводный список всех работ в статусе `'turned_in'` по всем классам учителя.
  * **Режим ученика «Список дел» (`To-do`) и «Календарь»:** Вкладки «Назначено», «Пропущено», «Выполнено» и календарь дедлайнов.
- [ ] **Задача 5.2:** Реализовать 4 вкладки внутри класса (`bormoclass-app.js`):
  1. **Вкладка 1 — «Лента» (Stream):** Баннер с `join_pin`, кнопка открытия **«Школьной доски»**, «Цель класса на четверть» (`quarter_goal`), кнопки «Светофора понимания» для ученика и публикация объявлений (включая кросс-постинг в несколько классов).
  2. **Вкладка 2 — «Задания» (Classwork):**
     * Выпуск заданий, квизов, вопросов и материалов с группировкой по темам (`class_topics`), переиспользованием постов (`Reuse post`) и тремя режимами вложений (`view`, `edit`, `copy`).
     * Автоматическая блокировка флага `is_homework = 1` для $1$-го класса (`grade_level == 1`) по нормам Минпросвещения РФ.
     * Кнопка **«Печать на класс (А4 под ножницы)»**: верстает в браузере печатный лист (`@media print`) с индивидуальными карточками вариантов по номерам парт ($1\dots 40$) и отдельным листом ключей для учителя.
  3. **Вкладка 3 — «Люди и Парты» (People & Seats):**
     * Схема из **3 рядов двухместных парт** (места $1\dots 40$), локальная расшифровка ФИО через `AES-GCM`, отметка присутствия (`is_present`) и сброс забытого пароля ученика в 1 клик (генерация новых $4$ секретных слов).
  4. **Вкладка 4 — «Оценки» (Grades — Живая матрица + СОУ):**
     * Живая таблица `Парты × Задания` по SSE `/api/classroom/{class_id}/stream`, проверка по рубрикам, автодополняемый «Банк комментариев» (`comment_bank`), перевод баллов в оценку $2\dots 5$.
     * Расчёт трёх показателей для отчёта завучу:
       * **Абсолютная успеваемость ($\text{Усп}$):**
         $$\text{Усп} = \frac{N_5 + N_4 + N_3}{N_{\text{всего}}} \times 100\%$$
       * **Качество знаний ($\text{КЗ}$):**
         $$\text{КЗ} = \frac{N_5 + N_4}{N_{\text{всего}}} \times 100\%$$
       * **Степень обученности учащихся по В. П. Симонову ($\text{СОУ}$):**
         $$\text{СОУ} = \frac{100 \cdot N_5 + 64 \cdot N_4 + 36 \cdot N_3 + 16 \cdot N_2}{N_{\text{всего}}}\%$$
     * Клиентский экспорт ведомости в CSV (`UTF-8 with BOM`) с локальной подстановкой расшифрованных в браузере имён без отправки ФИО на сервер.

---

### ЭТАП 6: Дизайн-система Material Design 3.0 (`Ember Newsroom`) и конфигурация Caddy

- [ ] **Задача 6.1:** Создать `app/static/css/md3-tokens.css` (палитра `Ember Newsroom` `#f57300`, светлая и тёмная темы через `[data-theme="dark"]`, локальный `@font-face` для `material-symbols-subset.woff2`).
- [ ] **Задача 6.2:** Настроить `edge/Caddyfile` с отключением буферизации (`flush_interval -1`) для обоих SSE-потоков (матрицы класса и интерактивной доски).

#### Эталонный код `edge/Caddyfile`:
```caddyfile
{$BORMOCLASS_DOMAIN:localhost} {
    encode zstd gzip

    handle_path /static/* {
        root * /srv/bormoclass/app/static
        file_server
        header Cache-Control "public, max-age=31536000, immutable"
    }

    @sse_streams path /api/classroom/*/stream /api/board/*/stream
    handle @sse_streams {
        reverse_proxy bormoclass:8010 {
            flush_interval -1
        }
    }

    handle {
        reverse_proxy bormoclass:8010
    }
}
```

---

## 3. Чек-лист приёмки и верификации (Definition of Done)

Перед завершением разработки агент обязан выполнить следующие проверки и убедиться в коде возврата `0`:

1. `pytest tests/test_zero_pii_invariants.py` — **PASSED** (в $10$ таблицах SQLite гарантированно $0$ колонок с ПД; в `.html`/`.css`/`.js` гарантированно $0$ ссылок на внешние CDN).
2. `pytest tests/test_passport_flow.py` — **PASSED** (регистрация выдаёт уникальный позывной и $4$ секретных слова; `salt$hash` верифицирует пароли; кука `pb_pass` проходит `HMAC-SHA256`; повторная отправка `/api/passport/solve` по одной и той же задаче не накручивает `recess_seconds`; активация пин-кода из `license_keys` и 7-дневный авто-триал выставляют `ad_free: true`).
3. `pytest tests/test_classroom_and_sou.py` — **PASSED** (блокировка ДЗ для $1$-го класса возвращает `400 Bad Request` или принудительно сбрасывает `is_homework = 0`; формулы успеваемости, качества знаний и $\text{СОУ}$ по Симонову считают точно; все синхронные роуты БД объявлены через `def`).