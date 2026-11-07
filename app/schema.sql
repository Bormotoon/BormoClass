-- ============================================================================
-- БЛОК 1: ТАБЛИЦЫ АВТОРИЗАЦИИ И ПАСПОРТОВ ПОЛЬЗОВАТЕЛЕЙ (0 БАЙТ ПД, 152-ФЗ РФ)
-- ============================================================================

-- 1. Безымянные паспорта пользователей (0 байт ПД)
CREATE TABLE IF NOT EXISTS users (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    handle              TEXT NOT NULL UNIQUE,           -- Позывной: "Бодрый-Енот-428"
    role                TEXT NOT NULL DEFAULT 'student',-- 'student' | 'teacher' | 'admin'
    password_hash       TEXT NOT NULL,                  -- Формат "salt$hex" или "scrypt$..."
    recovery_words_hash TEXT NOT NULL,                  -- Хэш от 4 секретных слов восстановления
    avatar_seed         INTEGER NOT NULL DEFAULT 1,     -- Сид генерации детерминированного аватара
    recess_seconds      INTEGER NOT NULL DEFAULT 0,     -- Игровой баланс кошелька "Билет на перемену"
    streak_days         INTEGER NOT NULL DEFAULT 1,
    last_active_day     TEXT,                           -- 'YYYY-MM-DD'
    trial_used          INTEGER NOT NULL DEFAULT 0,
    pro_until           INTEGER NOT NULL DEFAULT 0,
    temp_pin_hash       TEXT,                           -- Одноразовый ПИН сброса от учителя
    temp_pin_exp        INTEGER DEFAULT 0,
    verified_teacher    INTEGER NOT NULL DEFAULT 0,
    account_disabled    INTEGER NOT NULL DEFAULT 0,
    org_unit_id         INTEGER,
    created_at          INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS license_keys (
    code_hash           TEXT PRIMARY KEY,
    batch_name          TEXT NOT NULL DEFAULT 'dev',
    duration_days       INTEGER NOT NULL DEFAULT 365,
    activated_by        INTEGER REFERENCES users(id) ON DELETE SET NULL,
    activated_at        INTEGER,
    created_at          INTEGER NOT NULL
);

-- 2. Учебные классы
CREATE TABLE IF NOT EXISTS classes (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id                 INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title                      TEXT NOT NULL,                 -- Например: "8А — Информатика"
    subject_code               TEXT NOT NULL DEFAULT 'inf',   -- Код предмета
    grade_level                INTEGER NOT NULL DEFAULT 8 CHECK (grade_level BETWEEN 1 AND 11),
    join_pin                   TEXT NOT NULL UNIQUE,          -- 5-значный пин-код для входа с интерактивной доски
    quarter_goal               TEXT NOT NULL DEFAULT '',      -- "Цель класса на четверть" в шапке Ленты
    recess_locked_until        INTEGER NOT NULL DEFAULT 0,    -- Рубильник блокировки игр на время контрольной
    classroom_state_json       TEXT NOT NULL DEFAULT '{}',    -- JSON: рассадка 3 рядов парт, слайды доски и состояние
    section                    TEXT NOT NULL DEFAULT '',
    description_heading        TEXT NOT NULL DEFAULT '',
    description                TEXT NOT NULL DEFAULT '',
    room                       TEXT NOT NULL DEFAULT '',
    levels                     TEXT NOT NULL DEFAULT '',
    course_state               TEXT NOT NULL DEFAULT 'ACTIVE',
    enrollment_enabled         INTEGER NOT NULL DEFAULT 1,
    calendar_token             TEXT NOT NULL DEFAULT '',
    teacher_folder_id          TEXT,
    theme_color                TEXT NOT NULL DEFAULT '#f57300',
    banner_preset              TEXT NOT NULL DEFAULT 'default',
    stream_post_mode           TEXT NOT NULL DEFAULT 'STUDENTS_CAN_POST_AND_COMMENT',
    stream_work_mode           TEXT NOT NULL DEFAULT 'SHOW_ATTACHMENTS_AND_DETAILS',
    show_deleted_items         INTEGER NOT NULL DEFAULT 0,
    grade_calc_type            TEXT NOT NULL DEFAULT 'TOTAL_POINTS',
    grade_display_setting      TEXT NOT NULL DEFAULT 'SHOW_OVERALL_GRADE',
    apply_periods_to_existing  INTEGER NOT NULL DEFAULT 0,
    updated_at                 INTEGER NOT NULL DEFAULT 0,
    created_at                 INTEGER NOT NULL
);

-- 4. Участники класса и номера парт (1..40)
CREATE TABLE IF NOT EXISTS class_members (
    class_id           INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    student_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    seat_number        INTEGER NOT NULL CHECK (seat_number BETWEEN 1 AND 40), -- Номер парты (1..40)
    is_present         INTEGER NOT NULL DEFAULT 1,          -- Присутствие на уроке (1 = на месте, 0 = отсутствует)
    traffic_light      TEXT NOT NULL DEFAULT 'green',       -- 'green' (понятно) | 'yellow' (вопрос) | 'red' (нужна помощь)
    is_muted           INTEGER NOT NULL DEFAULT 0,
    enrollment_active  INTEGER NOT NULL DEFAULT 1,
    student_folder_id  TEXT,
    joined_at          INTEGER NOT NULL,
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
    sort_order   INTEGER NOT NULL DEFAULT 0,
    updated_at   INTEGER NOT NULL DEFAULT 0
);

-- 8. Поток объявлений и заданий (Stream & Classwork)
CREATE TABLE IF NOT EXISTS coursework (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id               INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    topic_id               INTEGER REFERENCES class_topics(id) ON DELETE SET NULL,
    kind                   TEXT NOT NULL DEFAULT 'assignment', -- 'announcement' | 'assignment' | 'quiz' | 'question' | 'material'
    title                  TEXT NOT NULL,
    instructions           TEXT NOT NULL DEFAULT '',
    attachments_json       TEXT NOT NULL DEFAULT '[]',         -- [{"task_id":"py_01","url":"/pythonteaching/","mode":"copy"}]
    rubric_json            TEXT NOT NULL DEFAULT '[]',         -- Критерии оценивания [{"id": "c1", "title": "...", "max": 2}]
    target_students        TEXT NOT NULL DEFAULT 'all',        -- 'all' или JSON-массив student_id
    max_points             INTEGER NOT NULL DEFAULT 5,         -- Максимальный балл (по умолчанию 5 или 100)
    recess_reward          INTEGER NOT NULL DEFAULT 300,       -- Секунды в кошелёк "Билета на перемену"
    is_homework            INTEGER NOT NULL DEFAULT 0,         -- 1 = ДЗ (автоматически блокируется при grade_level = 1)
    state                  TEXT NOT NULL DEFAULT 'published',  -- 'draft' | 'scheduled' | 'published'
    scheduled_at           INTEGER,
    due_at                 INTEGER,
    creator_user_id        INTEGER,
    creator_client_id      TEXT NOT NULL DEFAULT 'first_party',
    work_type              TEXT NOT NULL DEFAULT 'ASSIGNMENT',
    assignee_mode          TEXT NOT NULL DEFAULT 'ALL_STUDENTS',
    modification_mode      TEXT NOT NULL DEFAULT 'MODIFIABLE_UNTIL_TURNED_IN',
    grade_category_id      INTEGER,
    grading_period_id      INTEGER,
    choices_json           TEXT NOT NULL DEFAULT '[]',
    peer_replies_enabled   INTEGER NOT NULL DEFAULT 0,
    show_class_summary     INTEGER NOT NULL DEFAULT 1,
    close_after_due        INTEGER NOT NULL DEFAULT 0,
    originality_enabled    INTEGER NOT NULL DEFAULT 0,
    reviewed_by_teacher    INTEGER NOT NULL DEFAULT 0,
    sort_order             INTEGER NOT NULL DEFAULT 0,
    updated_at             INTEGER NOT NULL DEFAULT 0,
    created_at             INTEGER NOT NULL
);

-- 9. Сдачи работ учениками и ведомость оценок (Submissions & Gradebook)
CREATE TABLE IF NOT EXISTS submissions (
    coursework_id         INTEGER NOT NULL REFERENCES coursework(id) ON DELETE CASCADE,
    student_id            INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status                TEXT NOT NULL DEFAULT 'assigned',    -- 'assigned' | 'turned_in' | 'returned'
    payload_json          TEXT NOT NULL DEFAULT '{}',          -- Текстовый ответ, ответы квиза или отчёт от pb-passport-bridge.js
    rubric_scores         TEXT NOT NULL DEFAULT '{}',          -- Баллы по критериям {"c1": 2}
    grade_points          INTEGER,                             -- Выставленный первичный балл (0..max_points)
    grade_five            INTEGER CHECK (grade_five IS NULL OR grade_five BETWEEN 2 AND 5), -- Оценка по шкале РФ (2..5)
    teacher_comment       TEXT NOT NULL DEFAULT '',
    id                    INTEGER,
    v1_state              TEXT NOT NULL DEFAULT 'NEW',
    is_late               INTEGER NOT NULL DEFAULT 0,
    draft_grade           REAL,
    assigned_grade        REAL,
    draft_rubric_json     TEXT NOT NULL DEFAULT '{}',
    assigned_rubric_json  TEXT NOT NULL DEFAULT '{}',
    is_excused            INTEGER NOT NULL DEFAULT 0,
    mc_answer_text        TEXT NOT NULL DEFAULT '',
    created_at            INTEGER NOT NULL DEFAULT 0,
    updated_at            INTEGER NOT NULL,
    PRIMARY KEY (coursework_id, student_id)
);

-- 10. Личный банк комментариев учителя (Comment Bank)
CREATE TABLE IF NOT EXISTS comment_bank (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    comment_text TEXT NOT NULL
);

-- ============================================================================
-- БЛОК 3: ТАБЛИЦЫ GOOGLE CLASSROOM REST API v1 (ZERO-PII)
-- ============================================================================

CREATE TABLE IF NOT EXISTS oauth_clients (
    client_id          TEXT PRIMARY KEY,
    client_secret_hash TEXT NOT NULL,
    client_title       TEXT NOT NULL,
    scopes_json        TEXT NOT NULL DEFAULT '[]',
    owner_user_id      INTEGER REFERENCES users(id) ON DELETE CASCADE,
    created_at         INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS oauth_tokens (
    token_hash  TEXT PRIMARY KEY,
    client_id   TEXT NOT NULL REFERENCES oauth_clients(client_id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scopes_json TEXT NOT NULL,
    expires_at  INTEGER NOT NULL,
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS org_units (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id     INTEGER REFERENCES org_units(id) ON DELETE SET NULL,
    unit_title    TEXT NOT NULL,
    academic_year TEXT NOT NULL DEFAULT '2026-2027',
    created_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS course_aliases (
    alias_key  TEXT PRIMARY KEY,
    class_id   INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    scope_kind TEXT NOT NULL,
    client_id  TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS course_teachers (
    class_id   INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    teacher_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    is_primary INTEGER NOT NULL DEFAULT 0,
    joined_at  INTEGER NOT NULL,
    PRIMARY KEY (class_id, teacher_id)
);

CREATE TABLE IF NOT EXISTS course_material_sets (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id       INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    set_title      TEXT NOT NULL,
    materials_json TEXT NOT NULL DEFAULT '[]',
    sort_order     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS invitations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id        INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    invited_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    inviter_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    created_at      INTEGER NOT NULL,
    UNIQUE(class_id, invited_user_id)
);

CREATE TABLE IF NOT EXISTS student_groups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id    INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    group_title TEXT NOT NULL,
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS student_group_members (
    group_id   INTEGER NOT NULL REFERENCES student_groups(id) ON DELETE CASCADE,
    class_id   INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (group_id, student_id)
);

CREATE TABLE IF NOT EXISTS stored_folders (
    id            TEXT PRIMARY KEY,
    class_id      INTEGER REFERENCES classes(id) ON DELETE SET NULL,
    owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    folder_title  TEXT NOT NULL,
    folder_kind   TEXT NOT NULL DEFAULT 'GENERAL',
    created_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS stored_files (
    id                 TEXT PRIMARY KEY,
    folder_id          TEXT REFERENCES stored_folders(id) ON DELETE SET NULL,
    owner_user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    file_title         TEXT NOT NULL,
    mime_type          TEXT NOT NULL,
    size_bytes         INTEGER NOT NULL DEFAULT 0,
    sha256_hex         TEXT NOT NULL,
    disk_rel_path      TEXT NOT NULL,
    file_kind          TEXT NOT NULL DEFAULT 'FILE',
    source_template_id TEXT,
    created_at         INTEGER NOT NULL,
    updated_at         INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS file_acl (
    file_id     TEXT NOT NULL REFERENCES stored_files(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    access_mode TEXT NOT NULL DEFAULT 'VIEW',
    updated_at  INTEGER NOT NULL,
    PRIMARY KEY (file_id, user_id)
);

CREATE TABLE IF NOT EXISTS announcements (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id            INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    creator_user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    creator_client_id   TEXT NOT NULL DEFAULT 'first_party',
    body_text           TEXT NOT NULL,
    materials_json      TEXT NOT NULL DEFAULT '[]',
    state               TEXT NOT NULL DEFAULT 'PUBLISHED',
    assignee_mode       TEXT NOT NULL DEFAULT 'ALL_STUDENTS',
    target_students_json TEXT NOT NULL DEFAULT '[]',
    is_pinned           INTEGER NOT NULL DEFAULT 0,
    scheduled_at        INTEGER,
    created_at          INTEGER NOT NULL,
    updated_at          INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS course_materials (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id            INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    topic_id            INTEGER REFERENCES class_topics(id) ON DELETE SET NULL,
    creator_user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    creator_client_id   TEXT NOT NULL DEFAULT 'first_party',
    title               TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    materials_json      TEXT NOT NULL DEFAULT '[]',
    state               TEXT NOT NULL DEFAULT 'PUBLISHED',
    assignee_mode       TEXT NOT NULL DEFAULT 'ALL_STUDENTS',
    target_students_json TEXT NOT NULL DEFAULT '[]',
    learning_goals_json TEXT NOT NULL DEFAULT '[]',
    sort_order          INTEGER NOT NULL DEFAULT 0,
    scheduled_at        INTEGER,
    created_at          INTEGER NOT NULL,
    updated_at          INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS class_comments (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id       INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    parent_kind    TEXT NOT NULL,
    parent_id      INTEGER NOT NULL,
    reply_to_id    INTEGER REFERENCES class_comments(id) ON DELETE CASCADE,
    author_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body_text      TEXT NOT NULL,
    is_deleted     INTEGER NOT NULL DEFAULT 0,
    created_at     INTEGER NOT NULL,
    updated_at     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS private_comments (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    coursework_id  INTEGER NOT NULL REFERENCES coursework(id) ON DELETE CASCADE,
    student_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    author_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body_text      TEXT NOT NULL,
    created_at     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS file_annotations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id        TEXT NOT NULL REFERENCES stored_files(id) ON DELETE CASCADE,
    coursework_id  INTEGER,
    student_id     INTEGER,
    author_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    page_num       INTEGER NOT NULL DEFAULT 1,
    rect_json      TEXT NOT NULL DEFAULT '{}',
    stroke_json    TEXT NOT NULL DEFAULT '[]',
    body_text      TEXT NOT NULL DEFAULT '',
    created_at     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS rubrics (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id          INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    coursework_id     INTEGER NOT NULL UNIQUE REFERENCES coursework(id) ON DELETE CASCADE,
    creator_client_id TEXT NOT NULL DEFAULT 'first_party',
    source_sheet_id   TEXT NOT NULL DEFAULT '',
    is_scored         INTEGER NOT NULL DEFAULT 1,
    criteria_json     TEXT NOT NULL DEFAULT '[]',
    created_at        INTEGER NOT NULL,
    updated_at        INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS grade_categories (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id            INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    category_title      TEXT NOT NULL,
    default_denominator INTEGER NOT NULL DEFAULT 100,
    weight_micros       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS grading_periods (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id       INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    period_title   TEXT NOT NULL,
    start_date_iso TEXT NOT NULL,
    end_date_iso   TEXT NOT NULL,
    sort_order     INTEGER NOT NULL DEFAULT 0,
    UNIQUE(class_id, period_title)
);

CREATE TABLE IF NOT EXISTS submission_attachments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    coursework_id       INTEGER NOT NULL REFERENCES coursework(id) ON DELETE CASCADE,
    student_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    attachment_json     TEXT NOT NULL,
    created_by_template INTEGER NOT NULL DEFAULT 0,
    created_at          INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS submission_history (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    coursework_id     INTEGER NOT NULL REFERENCES coursework(id) ON DELETE CASCADE,
    student_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    entry_kind        TEXT NOT NULL,
    state_val         TEXT,
    grade_change_type TEXT,
    points_earned     REAL,
    max_points        REAL,
    actor_user_id     INTEGER NOT NULL,
    occurred_at       INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS learning_standards (
    id           TEXT PRIMARY KEY,
    set_code     TEXT NOT NULL,
    code_label   TEXT NOT NULL,
    description  TEXT NOT NULL,
    subject_code TEXT NOT NULL DEFAULT '',
    grade_level  INTEGER
);

CREATE TABLE IF NOT EXISTS course_standard_sets (
    class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    set_code TEXT NOT NULL,
    PRIMARY KEY (class_id, set_code)
);

CREATE TABLE IF NOT EXISTS item_learning_goals (
    item_kind   TEXT NOT NULL,
    item_id     INTEGER NOT NULL,
    standard_id TEXT NOT NULL REFERENCES learning_standards(id) ON DELETE CASCADE,
    PRIMARY KEY (item_kind, item_id, standard_id)
);

CREATE TABLE IF NOT EXISTS quizzes (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id             INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    coursework_id        INTEGER UNIQUE REFERENCES coursework(id) ON DELETE CASCADE,
    quiz_title           TEXT NOT NULL,
    description          TEXT NOT NULL DEFAULT '',
    questions_json       TEXT NOT NULL DEFAULT '[]',
    shuffle_questions    INTEGER NOT NULL DEFAULT 0,
    time_limit_sec       INTEGER NOT NULL DEFAULT 0,
    lock_tab_focus       INTEGER NOT NULL DEFAULT 0,
    auto_import_grades   INTEGER NOT NULL DEFAULT 1,
    show_correct_answers INTEGER NOT NULL DEFAULT 1,
    created_at           INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS quiz_attempts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id          INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    student_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    answers_json     TEXT NOT NULL DEFAULT '{}',
    auto_score       REAL NOT NULL DEFAULT 0,
    max_score        REAL NOT NULL DEFAULT 0,
    focus_lost_count INTEGER NOT NULL DEFAULT 0,
    started_at       INTEGER NOT NULL,
    submitted_at     INTEGER,
    UNIQUE(quiz_id, student_id)
);

CREATE TABLE IF NOT EXISTS practice_sets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id      INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    coursework_id INTEGER UNIQUE REFERENCES coursework(id) ON DELETE CASCADE,
    set_title     TEXT NOT NULL,
    cards_json    TEXT NOT NULL DEFAULT '[]',
    created_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS practice_attempts (
    practice_set_id INTEGER NOT NULL REFERENCES practice_sets(id) ON DELETE CASCADE,
    student_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    progress_json   TEXT NOT NULL DEFAULT '{}',
    hints_used      INTEGER NOT NULL DEFAULT 0,
    scratchpad_json TEXT NOT NULL DEFAULT '{}',
    completed_count INTEGER NOT NULL DEFAULT 0,
    updated_at      INTEGER NOT NULL,
    PRIMARY KEY (practice_set_id, student_id)
);

CREATE TABLE IF NOT EXISTS originality_reports (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    coursework_id     INTEGER NOT NULL REFERENCES coursework(id) ON DELETE CASCADE,
    student_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    run_by_role       TEXT NOT NULL,
    student_runs_used INTEGER NOT NULL DEFAULT 0,
    match_percent     REAL NOT NULL DEFAULT 0.0,
    matches_json      TEXT NOT NULL DEFAULT '[]',
    created_at        INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    class_id   INTEGER,
    notif_kind TEXT NOT NULL,
    title      TEXT NOT NULL,
    body_text  TEXT NOT NULL DEFAULT '',
    link_path  TEXT NOT NULL DEFAULT '',
    is_read    INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS notification_prefs (
    user_id            INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    global_enabled     INTEGER NOT NULL DEFAULT 1,
    prefs_json         TEXT NOT NULL DEFAULT '{}',
    muted_classes_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER,
    action_code   TEXT NOT NULL,
    target_kind   TEXT NOT NULL,
    target_id     TEXT NOT NULL,
    details_json  TEXT NOT NULL DEFAULT '{}',
    created_at    INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_class_members_student ON class_members(student_id);
CREATE INDEX IF NOT EXISTS idx_coursework_class ON coursework(class_id, state);
CREATE INDEX IF NOT EXISTS idx_submissions_student ON submissions(student_id, status);
