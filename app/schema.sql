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
