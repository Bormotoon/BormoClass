# MASTER TODO: Полноценный Open-Source аналог Google Classroom (100% API v1 + Web UI Parity)

> **Целевой профиль исполнения:** Оптимизировано специально под агентный цикл **Gemini 3.8 Flash** (детерминированные атомарные пакеты `[P1]..[P12]`, нулевая архитектурная неоднозначность, пакетные вызовы инструментов без холостых циклов чтения, точные сигнатуры файлов, таблиц и маршрутов).  
> **Эталон спецификации:** `docs/google_classroom/discovery/classroom_v1.json` (ревизия `20261106`: **24 REST-ресурса**, **105 HTTP-методов**, **85 схем данных**, **24 OAuth 2.0 скоупа**) + архитектурные спецификации `docs/google_classroom/architecture/01..04_*.md` + полный функционал веб-клиента Google Classroom (включая все возможности *Education Plus*, доступные **100% бесплатно**).

---

## Содержание

- [0. Протокол исполнения и жёсткие инварианты для Gemini 3.8 Flash](#0-протокол-исполнения-и-жёсткие-инварианты-для-gemini-38-flash)
- [1. Целевая файловая архитектура репозитория (Карта пакетов P1–P12)](#1-целевая-файловая-архитектура-репозитория-карта-пакетов-p1p12)
- [ПАКЕТ 1: Расширенная схема SQLite WAL (Zero-PII) и Протокольное ядро `/v1` (`updateMask`, `fields`, `pageToken`, 85 схем)](#пакет-1-расширенная-схема-sqlite-wal-zero-pii-и-протокольное-ядро-v1-updatemask-fields-pagetoken-85-схем)
- [ПАКЕТ 2: Профили (`userProfiles`), OAuth2 (24 скоупа), `verifiedTeacher` и 5-ролевой RBAC-движок](#пакет-2-профили-userprofiles-oauth2-24-скоупа-verifiedteacher-и-5-ролевой-rbac-движок)
- [ПАКЕТ 3: Курсы (`courses`), 5 состояний `courseState`, Псевдонимы (`aliases`), Копирование курса и «О курсе»](#пакет-3-курсы-courses-5-состояний-coursestate-псевдонимы-aliases-копирование-курса-и-о-курсе)
- [ПАКЕТ 4: Ростер (`teachers`, `students`), Приглашения (`invitations`), Подгруппы (`studentGroups`) и Опекуны (`guardians`)](#пакет-4-ростер-teachers-students-приглашения-invitations-подгруппы-studentgroups-и-опекуны-guardians)
- [ПАКЕТ 5: Файловое хранилище (`DriveFile`), Вложения (`Material`), Режимы `VIEW`/`EDIT`/`STUDENT_COPY`, Доски и ACL-трансфер](#пакет-5-файловое-хранилище-drivefile-вложения-material-режимы-vieweditstudent_copy-доски-и-acl-трансфер)
- [ПАКЕТ 6: Лента (`Stream`), Объявления (`announcements`), Фоновый планировщик (`scheduledTime`) и 3-уровневые комментарии](#пакет-6-лента-stream-объявления-announcements-фоновый-планировщик-scheduledtime-и-3-уровневые-комментарии)
- [ПАКЕТ 7: Темы (`topics`), Материалы (`courseWorkMaterials`), Задания (`courseWork`), Квизы, Практикумы, Антиплагиат и Стандарты](#пакет-7-темы-topics-материалы-courseworkmaterials-задания-coursework-квизы-практикумы-антиплагиат-и-стандарты)
- [ПАКЕТ 8: Сдача работ (`studentSubmissions`), Автомат 5 состояний, `SubmissionHistory`, Рубрики, Категории и Периоды](#пакет-8-сдача-работ-studentsubmissions-автомат-5-состояний-submissionhistory-рубрики-категории-и-периоды)
- [ПАКЕТ 9: Дополнения (`AddOnAttachments` — 29 методов), Push-подписки (`registrations`), Уведомления, Календарь `.ics` и Админка](#пакет-9-дополнения-addonattachments--29-методов-push-подписки-registrations-уведомления-календарь-ics-и-админка)
- [ПАКЕТ 10: Фронтенд ES-модули (Часть 1) — Навигатор, Витрина, Лента, Конструктор Заданий/Квизов, Люди и Подгруппы](#пакет-10-фронтенд-es-модули-часть-1--навигатор-витрина-лента-конструктор-заданийквизов-люди-и-подгруппы)
- [ПАКЕТ 11: Фронтенд ES-модули (Часть 2) — `SpeedGrader`, Журнал оценок, `To-review`/`To-do`/Календарь, Админка и PWA Сканер PDF](#пакет-11-фронтенд-es-модули-часть-2--speedgrader-журнал-оценок-to-reviewto-doкалендарь-админка-и-pwa-сканер-pdf)
- [ПАКЕТ 12: Контрактные автотесты `classroom_v1.json` (105 методов / 85 схем), RBAC, Автоматы и Финальная приёмка](#пакет-12-контрактные-автотесты-classroom_v1json-105-методов--85-схем-rbac-автоматы-и-финальная-приёмка)

---

## 0. Протокол исполнения и жёсткие инварианты для Gemini 3.8 Flash

При выполнении любого пакета из этого файла агент **Gemini 3.8 Flash** обязан строго соблюдать следующие **7 правил**:

1. **Пакетная дисциплина инструментов (Zero Tool-Thrashing):**
   - Выполняй работу строго последовательно по пакетам: `ПАКЕТ 1` → `ПАКЕТ 2` → … → `ПАКЕТ 12`.
   - В начале пакета прочитай все нужные существующие файлы **одним параллельным батчем `read_file`**.
   - Создавай новые модули целиком через `write_file` (не дроби создание одного файла на 5 мелких `edit_file`).
   - Запускай тесты через `.venv/bin/pytest` **ровно один раз в конце пакета** (команда `Gate Check` указана в каждом пакете; всегда используй `.venv/bin/python` и `.venv/bin/pytest`). Не запускай промежуточные `ls`, `cat`, `grep` для файлов, содержимое которых ты только что записал.
2. **Абсолютный инвариант имён колонок SQLite (`tests/test_zero_pii_invariants.py`):**
   - Сторожевой тест падает, если **в любой таблице SQLite** есть колонка из множества:
     `{"full_name", "first_name", "last_name", "middle_name", "patronymic", "fio", "name", "email", "mail", "phone", "tel", "birth_year", "birth_date", "birthday", "gender", "sex", "ip", "ip_address", "passport"}`.
   - **ЗАПРЕЩЕНО** называть колонки таблиц SQLite словом `name` или `email`! В таблицах БД всегда используй `title`, `label`, `topic_title`, `category_title`, `contact_token`, `invite_target`, а маппинг в поля JSON Google Classroom (`"name"`, `"emailAddress"`, `"invitedEmailAddress"`) выполняй **только на уровне сериализации ответа FastAPI/Pydantic**!
3. **Абсолютный запрет внешних CDN и стоп-доменов в `app/static/`:**
   - Сторожевой тест проверяет все `.html`, `.css`, `.js` внутри `app/static/` на отсутствие подстрок:
     `googleapis.com`, `gstatic.com`, `jsdelivr.net`, `unpkg.com`, `cdnjs.cloudflare.com`, `stackpath.bootstrapcdn.com`, `code.jquery.com`.
   - **ЗАПРЕЩЕНО** упоминать строку `googleapis.com` в любых файлах внутри `app/static/` (даже в комментариях или константах OAuth-скоупов!). Строки скоупов `https://www.googleapis.com/auth/classroom.*` хранятся **исключительно** в Python-коде `app/v1/`.
4. **Инвариант синхронных маршрутов FastAPI (`tests/test_classroom_and_sou.py`):**
   - Все HTTP-эндпоинты в `app/classroom/*`, `app/v1/*` и `app/storage/*`, работающие с SQLite `db_session()`, **ОБЯЗАНЫ** объявляться через `def` (НЕ `async def`!), чтобы Uvicorn выполнял их в `threadpool` без блокировки event loop. При приёме `UploadFile` внутри `def`-роута читай поток синхронно через `upload_file.file.read()`.
   - Как `async def` объявляются **только** SSE-маршруты, содержащие `/stream` в URL, и фоновые задачи `asyncio.create_task` внутри `lifespan` в `app/main.py`.
5. **Единый самодостаточный стек (Никаких «или» и внешних демонов):**
   - Никаких PostgreSQL, Redis, Celery, S3/boto3, Node.js на сервере. Только `Python 3.12+`, `FastAPI`, `Pydantic v2`, встроенный `sqlite3` (WAL), локальное хранилище файлов в `data/storage/`, нативные браузерные ES-модули (`type="module"`) и уже собранное ядро доски в `app/static/board/`. Не добавляй тяжёлые внешние пакеты в `requirements.txt`.
6. **100% обратная совместимость и 100% бесплатность:**
   - Все существующие маршруты `/api/passport/*` и `/api/classroom/*` продолжают работать со старыми контрактами, чтобы все текущие автотесты (`tests/test_*.py`) оставались зелёными на каждом шаге.
   - Никакой монетизации, подписок, тарифов, `license_keys` или `ad_free` — все функции *Education Plus* (рубрики, периоды, группы, стандарты, практикумы, антиплагиат, дополнения) открыты бесплатно для каждого учителя и ученика.
7. **Декомпозиция кода на компактные модули (≤ 350 строк на файл):**
   - Не раздувай существующий `app/static/js/bormoclass-app.js` и роутеры до тысяч строк: выноси новую логику в чётко изолированные модули из раздела 1.

---

## 1. Целевая файловая архитектура репозитория (Карта пакетов P1–P12)

```text
BormoClass/
├── TODO.md                                         # Этот мастер-план для Gemini 3.8 Flash
├── requirements.txt                                # Без изменений (fastapi, uvicorn, pydantic, python-multipart, pytest, httpx)
├── data/storage/                                   # [P5] Локальное контентно-адресуемое хранилище файлов и .excalidraw досок
├── app/
│   ├── main.py                                     # [P1,P6,P9] Подключение роутеров /v1, /api/storage и фонового воркера в lifespan
│   ├── config.py                                   # [P1] Добавление STORAGE_DIR="data/storage", MAX_UPLOAD_MB=50
│   ├── db.py                                       # [P1] WAL-менеджер + идемпотентный run_migrations(conn) для новых колонок
│   ├── schema.sql                                  # [P1] Полная Zero-PII схема БД (9 базовых + 39 новых таблиц Classroom v1)
│   ├── passport/                                   # Существующий контур авторизации pb_pass (НЕ ЛОМАТЬ)
│   ├── storage/
│   │   ├── __init__.py                             # [P5]
│   │   ├── engine.py                               # [P5] Файлы, папки курса/ученика, превью, STUDENT_COPY клонирование и ACL-трансфер
│   │   └── router_files.py                         # [P5] Загрузка, скачивание с HTTP Range, метаданные и аннотации файлов/досок
│   ├── worker/
│   │   ├── __init__.py                             # [P6]
│   │   └── scheduler.py                            # [P6,P9] Фоновый asyncio-цикл: автопубликация scheduledTime, сводки опекунов, ретраи вебхуков
│   ├── v1/                                         # 100% СОВМЕСТИМЫЙ СЛОЙ GOOGLE CLASSROOM REST API v1 (24 ресурса, 105 методов)
│   │   ├── __init__.py                             # [P1] Агрегатор v1_router (prefix="/v1")
│   │   ├── protocol.py                             # [P1] FieldMask (updateMask, fields), pageToken, ErrorEnvelope, резолверы me/- и d:/p:
│   │   ├── schemas.py                              # [P1] Все 85 Pydantic v2 схем classroom_v1.json (camelCase + RFC3339)
│   │   ├── rbac.py                                 # [P2] 5 ролей (Owner, Co-Teacher, Student, Guardian, Admin) + 24 OAuth2 скоупа
│   │   ├── router_users.py                         # [P2] userProfiles.get + управление OAuth-токенами и verifiedTeacher
│   │   ├── router_courses.py                       # [P3] courses (8 методов) + courses.aliases (3 метода) + CourseMaterialSet
│   │   ├── router_roster.py                        # [P4] teachers (4), students (4), invitations (5), studentGroups (4+3)
│   │   ├── router_guardians.py                     # [P4] guardians (3), guardianInvitations (4) + генератор сводок успеваемости
│   │   ├── router_announcements.py                 # [P6] courses.announcements (6 базовых методов)
│   │   ├── router_classwork.py                     # [P7] topics (5), courseWorkMaterials (5), courseWork (6 базовых методов)
│   │   ├── router_submissions.py                   # [P8] studentSubmissions (7 методов) + batchReturn + StateHistory/GradeHistory
│   │   ├── router_rubrics_grades.py                # [P8] rubrics (5) + updateRubric + GradebookSettings + GradingPeriodSettings
│   │   ├── router_addons.py                        # [P9] Все 29 методов addOnAttachments, addOnContext и studentSubmissions + LTI 1.3
│   │   └── router_registrations.py                 # [P9] registrations (create, delete) + HMAC-SHA256 Webhook Dispatcher
│   ├── classroom/                                  # РАСШИРЕННЫЙ WEB API (совместимый с текущим SPA + фичи UI Classroom)
│   │   ├── router_classes.py                       # [P3,P4] + архивация, копирование курса, темы баннеров, видеовстречи, Mute ученика
│   │   ├── router_coursework.py                    # [P7] + стандарты learning_goals, жёсткий дедлайн
│   │   ├── router_submissions.py                   # [P8] + расчёт весов категорий, периодов, Excused и СОУ
│   │   ├── router_global.py                        # [P9] + вкладка Reviewed, недельные корзины To-do, .ics календарь, архив
│   │   ├── router_board.py                         # [P5] + привязка персональных и групповых досок к заданиям
│   │   ├── router_comments.py                      # [P6] Публичные комментарии ленты, приватный чат сдачи, аннотации на работах
│   │   ├── router_quizzes_and_sets.py              # [P7] Конструктор автопроверяемых Quiz, адаптивные Practice Sets, Антиплагиат
│   │   └── router_notifications_admin.py           # [P9] Центр уведомлений, настройки по курсам, Админ-консоль, OneRoster CSV, Takeout
│   └── static/
│       ├── index.html                              # [P10,P11] Подключение manifest.webmanifest, sw.js и модулей интерфейса
│       ├── manifest.webmanifest                    # [P11] PWA-манифест (standalone, иконки, офлайн-поддержка)
│       ├── sw.js                                   # [P11] Service Worker (офлайн-кеш материалов и черновиков)
│       ├── css/
│       │   └── classroom-ext.css                   # [P10,P11] Стили SpeedGrader, рубрик, конструктора квизов, календаря и сканера
│       └── js/
│           ├── bormoclass-app.js                   # [P10,P11] Точка входа SPA, делегирующая рендер в модули js/modules/*
│           └── modules/
│               ├── api-v1.js                       # [P10] Клиент к /v1/* и /api/classroom/* с поддержкой pageToken и updateMask
│               ├── home-and-drawer.js              # [P10] Боковое меню, карточки с дедлайнами, DnD, PROVISIONED, инвайты, Архив
│               ├── stream-and-comments.js          # [P10] Лента, закрепление, черновики, расписание, модерация, комментарии
│               ├── classwork-and-quizzes.js        # [P10] Темы DnD, редактор заданий/вопросов, конструктор Quiz, Practice Sets, стандарты
│               ├── people-groups-guardians.js      # [P10] Со-учителя, ученики, парты, подгруппы, опекуны, Mute, профиль ученика
│               ├── speedgrader.js                  # [P11] 2-панельная проверка (PDF/фото/код/доска + рубрика + #банк комментариев + история)
│               ├── gradebook-periods.js            # [P11] Живой журнал оценок, веса категорий, четверти, Excused, СОУ, экспорт CSV
│               ├── global-calendar-admin.js        # [P11] To-review (2 вкладки), To-do (3 вкладки), Календарь .ics, Уведомления, Админка
│               └── pdf-scanner.js                  # [P11] Браузерный сканер бумажных тетрадей с камеры в многостраничный PDF
└── tests/
    ├── test_zero_pii_invariants.py                 # Существующий сторожевой тест (ОБЯЗАН БЫТЬ GREEN ВСЕГДА)
    ├── test_passport_flow.py                       # Существующий тест паспорта (ОБЯЗАН БЫТЬ GREEN ВСЕГДА)
    ├── test_classroom_and_sou.py                   # Существующий тест классов и СОУ (ОБЯЗАН БЫТЬ GREEN ВСЕГДА)
    ├── test_error_messages.py                      # Существующий тест ошибок (ОБЯЗАН БЫТЬ GREEN ВСЕГДА)
    ├── test_v1_discovery_contract.py               # [P12] Автопроверка всех 105 маршрутов и 85 схем против classroom_v1.json
    ├── test_v1_lifecycles_and_grades.py            # [P12] Тесты автоматов Course/Submission, ACL досок, рубрик, категорий и периодов
    └── test_v1_rbac_addons_and_features.py         # [P12] Тесты 5 ролей, 24 скоупов, Add-ons, Webhooks, квизов и антиплагиата
```

---

## ПАКЕТ 1: Расширенная схема SQLite WAL (Zero-PII) и Протокольное ядро `/v1` (`updateMask`, `fields`, `pageToken`, 85 схем)

### Файлы пакета `[P1]`
- **Изменить:** `app/config.py`, `app/schema.sql`, `app/db.py`, `app/main.py`
- **Создать:** `app/v1/__init__.py`, `app/v1/protocol.py`, `app/v1/schemas.py`

### Задачи пакета `[P1]`
- [x] **1.1. Конфигурация (`app/config.py`):** добавить поля `STORAGE_DIR: str = "data/storage"`, `MAX_UPLOAD_BYTES: int = 52_428_800` (50 МБ), `ALLOW_STUDENT_UNENROLL: bool = True`, `COURSE_CREATE_POLICY: str = "ANY_TEACHER"` (`"ANY_USER"` | `"ANY_TEACHER"` | `"VERIFIED_TEACHERS_ONLY"` | `"ADMINS_ONLY"`).
- [x] **1.2. Идемпотентная миграция существующих таблиц (`app/db.py`):** реализовать функцию `_ensure_columns(conn, table, col_defs: dict[str, str])`, вызываемую в `init_db()` после `executescript(SCHEMA_PATH)`, чтобы существующий файл `bormoclass.db` безопасно получал новые колонки без удаления данных:
  - В `users`: `verified_teacher INTEGER NOT NULL DEFAULT 0`, `account_disabled INTEGER NOT NULL DEFAULT 0`, `org_unit_id INTEGER`.
  - В `classes`: `section TEXT NOT NULL DEFAULT ''`, `description_heading TEXT NOT NULL DEFAULT ''`, `description TEXT NOT NULL DEFAULT ''`, `room TEXT NOT NULL DEFAULT ''`, `levels TEXT NOT NULL DEFAULT ''`, `course_state TEXT NOT NULL DEFAULT 'ACTIVE'`, `enrollment_enabled INTEGER NOT NULL DEFAULT 1`, `guardians_enabled INTEGER NOT NULL DEFAULT 1`, `calendar_token TEXT NOT NULL DEFAULT ''`, `teacher_folder_id TEXT`, `theme_color TEXT NOT NULL DEFAULT '#f57300'`, `banner_preset TEXT NOT NULL DEFAULT 'default'`, `video_room_url TEXT NOT NULL DEFAULT ''`, `video_visible_to_students INTEGER NOT NULL DEFAULT 1`, `stream_post_mode TEXT NOT NULL DEFAULT 'STUDENTS_CAN_POST_AND_COMMENT'`, `stream_work_mode TEXT NOT NULL DEFAULT 'SHOW_ATTACHMENTS_AND_DETAILS'`, `show_deleted_items INTEGER NOT NULL DEFAULT 0`, `grade_calc_type TEXT NOT NULL DEFAULT 'TOTAL_POINTS'`, `grade_display_setting TEXT NOT NULL DEFAULT 'SHOW_OVERALL_GRADE'`, `apply_periods_to_existing INTEGER NOT NULL DEFAULT 0`, `updated_at INTEGER NOT NULL DEFAULT 0`.
  - В `class_members`: `is_muted INTEGER NOT NULL DEFAULT 0`, `enrollment_active INTEGER NOT NULL DEFAULT 1`, `student_folder_id TEXT`.
  - В `class_topics`: `updated_at INTEGER NOT NULL DEFAULT 0`.
  - В `coursework`: `creator_user_id INTEGER`, `creator_client_id TEXT NOT NULL DEFAULT 'first_party'`, `work_type TEXT NOT NULL DEFAULT 'ASSIGNMENT'`, `assignee_mode TEXT NOT NULL DEFAULT 'ALL_STUDENTS'`, `modification_mode TEXT NOT NULL DEFAULT 'MODIFIABLE_UNTIL_TURNED_IN'`, `grade_category_id INTEGER`, `grading_period_id INTEGER`, `choices_json TEXT NOT NULL DEFAULT '[]'`, `peer_replies_enabled INTEGER NOT NULL DEFAULT 0`, `show_class_summary INTEGER NOT NULL DEFAULT 1`, `close_after_due INTEGER NOT NULL DEFAULT 0`, `originality_enabled INTEGER NOT NULL DEFAULT 0`, `reviewed_by_teacher INTEGER NOT NULL DEFAULT 0`, `sort_order INTEGER NOT NULL DEFAULT 0`, `updated_at INTEGER NOT NULL DEFAULT 0`.
  - В `submissions`: `id INTEGER`, `v1_state TEXT NOT NULL DEFAULT 'NEW'`, `is_late INTEGER NOT NULL DEFAULT 0`, `draft_grade REAL`, `assigned_grade REAL`, `draft_rubric_json TEXT NOT NULL DEFAULT '{}'`, `assigned_rubric_json TEXT NOT NULL DEFAULT '{}'`, `is_excused INTEGER NOT NULL DEFAULT 0`, `short_answer_text TEXT NOT NULL DEFAULT ''`, `mc_answer_text TEXT NOT NULL DEFAULT ''`, `created_at INTEGER NOT NULL DEFAULT 0`.
- [x] **1.3. Новые таблицы `app/schema.sql` (строго 0 запрещённых колонок `name`/`email`!):** добавить в `app/schema.sql` блоки `CREATE TABLE IF NOT EXISTS`:
  - `oauth_clients (client_id TEXT PRIMARY KEY, client_secret_hash TEXT NOT NULL, client_title TEXT NOT NULL, scopes_json TEXT NOT NULL DEFAULT '[]', owner_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, created_at INTEGER NOT NULL)`
  - `oauth_tokens (token_hash TEXT PRIMARY KEY, client_id TEXT NOT NULL REFERENCES oauth_clients(client_id) ON DELETE CASCADE, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, scopes_json TEXT NOT NULL, expires_at INTEGER NOT NULL, created_at INTEGER NOT NULL)`
  - `org_units (id INTEGER PRIMARY KEY AUTOINCREMENT, parent_id INTEGER REFERENCES org_units(id) ON DELETE SET NULL, unit_title TEXT NOT NULL, academic_year TEXT NOT NULL DEFAULT '2026-2027', created_at INTEGER NOT NULL)`
  - `course_aliases (alias_key TEXT PRIMARY KEY, class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE, scope_kind TEXT NOT NULL, client_id TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL)`
  - `course_teachers (class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE, teacher_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, is_primary INTEGER NOT NULL DEFAULT 0, joined_at INTEGER NOT NULL, PRIMARY KEY (class_id, teacher_id))`
  - `course_material_sets (id INTEGER PRIMARY KEY AUTOINCREMENT, class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE, set_title TEXT NOT NULL, materials_json TEXT NOT NULL DEFAULT '[]', sort_order INTEGER NOT NULL DEFAULT 0)`
  - `invitations (id INTEGER PRIMARY KEY AUTOINCREMENT, class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE, invited_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, inviter_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, role TEXT NOT NULL, created_at INTEGER NOT NULL, UNIQUE(class_id, invited_user_id))`
  - `student_groups (id INTEGER PRIMARY KEY AUTOINCREMENT, class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE, group_title TEXT NOT NULL, created_at INTEGER NOT NULL)`
  - `student_group_members (group_id INTEGER NOT NULL REFERENCES student_groups(id) ON DELETE CASCADE, class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE, student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, PRIMARY KEY (group_id, student_id))`
  - `guardian_invitations (id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, invite_target TEXT NOT NULL, invite_code_hash TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'PENDING', inviter_user_id INTEGER, created_at INTEGER NOT NULL)`
  - `guardians (id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, guardian_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, invite_target TEXT NOT NULL DEFAULT '', digest_frequency TEXT NOT NULL DEFAULT 'WEEKLY', created_at INTEGER NOT NULL, UNIQUE(student_id, guardian_user_id))`
  - `stored_folders (id TEXT PRIMARY KEY, class_id INTEGER REFERENCES classes(id) ON DELETE SET NULL, owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, folder_title TEXT NOT NULL, folder_kind TEXT NOT NULL DEFAULT 'GENERAL', created_at INTEGER NOT NULL)`
  - `stored_files (id TEXT PRIMARY KEY, folder_id TEXT REFERENCES stored_folders(id) ON DELETE SET NULL, owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, file_title TEXT NOT NULL, mime_type TEXT NOT NULL, size_bytes INTEGER NOT NULL DEFAULT 0, sha256_hex TEXT NOT NULL, disk_rel_path TEXT NOT NULL, file_kind TEXT NOT NULL DEFAULT 'FILE', source_template_id TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)`
  - `file_acl (file_id TEXT NOT NULL REFERENCES stored_files(id) ON DELETE CASCADE, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, access_mode TEXT NOT NULL DEFAULT 'VIEW', updated_at INTEGER NOT NULL, PRIMARY KEY (file_id, user_id))`
  - `announcements (id INTEGER PRIMARY KEY AUTOINCREMENT, class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE, creator_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, creator_client_id TEXT NOT NULL DEFAULT 'first_party', body_text TEXT NOT NULL, materials_json TEXT NOT NULL DEFAULT '[]', state TEXT NOT NULL DEFAULT 'PUBLISHED', assignee_mode TEXT NOT NULL DEFAULT 'ALL_STUDENTS', target_students_json TEXT NOT NULL DEFAULT '[]', is_pinned INTEGER NOT NULL DEFAULT 0, scheduled_at INTEGER, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)`
  - `course_materials (id INTEGER PRIMARY KEY AUTOINCREMENT, class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE, topic_id INTEGER REFERENCES class_topics(id) ON DELETE SET NULL, creator_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, creator_client_id TEXT NOT NULL DEFAULT 'first_party', title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', materials_json TEXT NOT NULL DEFAULT '[]', state TEXT NOT NULL DEFAULT 'PUBLISHED', assignee_mode TEXT NOT NULL DEFAULT 'ALL_STUDENTS', target_students_json TEXT NOT NULL DEFAULT '[]', learning_goals_json TEXT NOT NULL DEFAULT '[]', sort_order INTEGER NOT NULL DEFAULT 0, scheduled_at INTEGER, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)`
  - `class_comments (id INTEGER PRIMARY KEY AUTOINCREMENT, class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE, parent_kind TEXT NOT NULL, parent_id INTEGER NOT NULL, reply_to_id INTEGER REFERENCES class_comments(id) ON DELETE CASCADE, author_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, body_text TEXT NOT NULL, is_deleted INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)`
  - `private_comments (id INTEGER PRIMARY KEY AUTOINCREMENT, coursework_id INTEGER NOT NULL REFERENCES coursework(id) ON DELETE CASCADE, student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, author_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, body_text TEXT NOT NULL, created_at INTEGER NOT NULL)`
  - `file_annotations (id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT NOT NULL REFERENCES stored_files(id) ON DELETE CASCADE, coursework_id INTEGER, student_id INTEGER, author_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, page_num INTEGER NOT NULL DEFAULT 1, rect_json TEXT NOT NULL DEFAULT '{}', stroke_json TEXT NOT NULL DEFAULT '[]', body_text TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL)`
  - `rubrics (id INTEGER PRIMARY KEY AUTOINCREMENT, class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE, coursework_id INTEGER NOT NULL UNIQUE REFERENCES coursework(id) ON DELETE CASCADE, creator_client_id TEXT NOT NULL DEFAULT 'first_party', source_sheet_id TEXT NOT NULL DEFAULT '', is_scored INTEGER NOT NULL DEFAULT 1, criteria_json TEXT NOT NULL DEFAULT '[]', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)`
  - `grade_categories (id INTEGER PRIMARY KEY AUTOINCREMENT, class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE, category_title TEXT NOT NULL, default_denominator INTEGER NOT NULL DEFAULT 100, weight_micros INTEGER NOT NULL DEFAULT 0)`
  - `grading_periods (id INTEGER PRIMARY KEY AUTOINCREMENT, class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE, period_title TEXT NOT NULL, start_date_iso TEXT NOT NULL, end_date_iso TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0, UNIQUE(class_id, period_title))`
  - `submission_attachments (id INTEGER PRIMARY KEY AUTOINCREMENT, coursework_id INTEGER NOT NULL REFERENCES coursework(id) ON DELETE CASCADE, student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, attachment_json TEXT NOT NULL, created_by_template INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL)`
  - `submission_history (id INTEGER PRIMARY KEY AUTOINCREMENT, coursework_id INTEGER NOT NULL REFERENCES coursework(id) ON DELETE CASCADE, student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, entry_kind TEXT NOT NULL, state_val TEXT, grade_change_type TEXT, points_earned REAL, max_points REAL, actor_user_id INTEGER NOT NULL, occurred_at INTEGER NOT NULL)`
  - `learning_standards (id TEXT PRIMARY KEY, set_code TEXT NOT NULL, code_label TEXT NOT NULL, description TEXT NOT NULL, subject_code TEXT NOT NULL DEFAULT '', grade_level INTEGER)`
  - `course_standard_sets (class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE, set_code TEXT NOT NULL, PRIMARY KEY (class_id, set_code))`
  - `item_learning_goals (item_kind TEXT NOT NULL, item_id INTEGER NOT NULL, standard_id TEXT NOT NULL REFERENCES learning_standards(id) ON DELETE CASCADE, PRIMARY KEY (item_kind, item_id, standard_id))`
  - `quizzes (id INTEGER PRIMARY KEY AUTOINCREMENT, class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE, coursework_id INTEGER UNIQUE REFERENCES coursework(id) ON DELETE CASCADE, quiz_title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', questions_json TEXT NOT NULL DEFAULT '[]', shuffle_questions INTEGER NOT NULL DEFAULT 0, time_limit_sec INTEGER NOT NULL DEFAULT 0, lock_tab_focus INTEGER NOT NULL DEFAULT 0, auto_import_grades INTEGER NOT NULL DEFAULT 1, show_correct_answers INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL)`
  - `quiz_attempts (id INTEGER PRIMARY KEY AUTOINCREMENT, quiz_id INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE, student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, answers_json TEXT NOT NULL DEFAULT '{}', auto_score REAL NOT NULL DEFAULT 0, max_score REAL NOT NULL DEFAULT 0, focus_lost_count INTEGER NOT NULL DEFAULT 0, started_at INTEGER NOT NULL, submitted_at INTEGER, UNIQUE(quiz_id, student_id))`
  - `practice_sets (id INTEGER PRIMARY KEY AUTOINCREMENT, class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE, coursework_id INTEGER UNIQUE REFERENCES coursework(id) ON DELETE CASCADE, set_title TEXT NOT NULL, cards_json TEXT NOT NULL DEFAULT '[]', created_at INTEGER NOT NULL)`
  - `practice_attempts (practice_set_id INTEGER NOT NULL REFERENCES practice_sets(id) ON DELETE CASCADE, student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, progress_json TEXT NOT NULL DEFAULT '{}', hints_used INTEGER NOT NULL DEFAULT 0, scratchpad_json TEXT NOT NULL DEFAULT '{}', completed_count INTEGER NOT NULL DEFAULT 0, updated_at INTEGER NOT NULL, PRIMARY KEY (practice_set_id, student_id))`
  - `originality_reports (id INTEGER PRIMARY KEY AUTOINCREMENT, coursework_id INTEGER NOT NULL REFERENCES coursework(id) ON DELETE CASCADE, student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, run_by_role TEXT NOT NULL, student_runs_used INTEGER NOT NULL DEFAULT 0, match_percent REAL NOT NULL DEFAULT 0.0, matches_json TEXT NOT NULL DEFAULT '[]', created_at INTEGER NOT NULL)`
  - `addon_attachments (id INTEGER PRIMARY KEY AUTOINCREMENT, class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE, item_kind TEXT NOT NULL, item_id INTEGER NOT NULL, client_id TEXT NOT NULL, title TEXT NOT NULL, teacher_view_uri TEXT NOT NULL, student_view_uri TEXT NOT NULL, review_uri TEXT NOT NULL DEFAULT '', max_points REAL, grade_sync_enabled INTEGER NOT NULL DEFAULT 0, due_at INTEGER, copy_history_json TEXT NOT NULL DEFAULT '[]', created_at INTEGER NOT NULL)`
  - `addon_submissions (id INTEGER PRIMARY KEY AUTOINCREMENT, attachment_id INTEGER NOT NULL REFERENCES addon_attachments(id) ON DELETE CASCADE, student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, points_earned REAL, updated_at INTEGER NOT NULL, UNIQUE(attachment_id, student_id))`
  - `push_registrations (id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, client_id TEXT NOT NULL DEFAULT 'first_party', feed_type TEXT NOT NULL, class_id INTEGER REFERENCES classes(id) ON DELETE CASCADE, target_topic TEXT NOT NULL, expires_at INTEGER NOT NULL, created_at INTEGER NOT NULL)`
  - `webhook_deliveries (id INTEGER PRIMARY KEY AUTOINCREMENT, registration_id TEXT NOT NULL, target_url TEXT NOT NULL, payload_json TEXT NOT NULL, attempt_count INTEGER NOT NULL DEFAULT 0, next_retry_at INTEGER NOT NULL DEFAULT 0, delivered INTEGER NOT NULL DEFAULT 0, last_status INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL)`
  - `notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, class_id INTEGER, notif_kind TEXT NOT NULL, title TEXT NOT NULL, body_text TEXT NOT NULL DEFAULT '', link_path TEXT NOT NULL DEFAULT '', is_read INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL)`
  - `notification_prefs (user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, global_enabled INTEGER NOT NULL DEFAULT 1, prefs_json TEXT NOT NULL DEFAULT '{}', muted_classes_json TEXT NOT NULL DEFAULT '[]')`
  - `audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, actor_user_id INTEGER, action_code TEXT NOT NULL, target_kind TEXT NOT NULL, target_id TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}', created_at INTEGER NOT NULL)`
- [x] **1.4. Протокольное ядро `/v1` (`app/v1/protocol.py`):**
  - `api_error(http_code: int, status_str: str, message: str, reason: str | None = None)` -> выбрасывает `HTTPException` с каноническим Google Error JSON (`{"error": {"code": ..., "message": ..., "status": ..., "details": [{"reason": reason}]}}`) и одновременно дублирует `detail` строкой на верхнем уровне для совместимости с UI.
  - `parse_update_mask(update_mask: str | None, allowed_fields: set[str]) -> set[str]` -> конвертирует `camelCase` в `snake_case`, при пустой маске или недопустимом поле вызывает `api_error(400, "INVALID_ARGUMENT", ...)`.
  - `apply_fields_selector(payload: Any, fields_expr: str | None) -> Any` -> фильтрует отдаваемый словарь/список по синтаксису `fields=courses(id,name),nextPageToken`.
  - `encode_page_token(offset: int, filter_fingerprint: str) -> str` и `decode_page_token(page_token: str | None, filter_fingerprint: str) -> int` -> base64url + HMAC подпись от `settings.SECRET_KEY`; при несовпадении `filter_fingerprint` возвращает `400 INVALID_ARGUMENT`.
  - `resolve_user_id(conn, raw_user_id: str, current_user: dict, allow_wildcard: bool = False)` -> резолвит `"me"`, `"-"`, числовой `id` и строковый `handle`.
  - `resolve_class_id(conn, raw_course_id: str, client_id: str = "first_party")` -> резолвит `d:<alias>`, `p:<alias>` (с проверкой `client_id`) и числовой `id`.
  - Форматировщики дат: `ts_to_rfc3339(ts: int | None) -> str | None`, `rfc3339_to_ts(s: str | None) -> int | None`, конвертеры `Date {year, month, day}` + `TimeOfDay {hours, minutes, seconds, nanos}` <-> Unix UTC timestamp.
- [x] **1.5. Полный пакет 85 схем данных (`app/v1/schemas.py`):** описать все **85 моделей** из `docs/google_classroom/reference/schemas.md` (`Course`, `CourseAlias`, `CourseMaterial`, `CourseMaterialSet`, `GradingPeriod`, `GradingPeriodSettings`, `GradeCategory`, `GradebookSettings`, `Teacher`, `Student`, `UserProfile`, `Name`, `GlobalPermission`, `Invitation`, `StudentGroup`, `StudentGroupMember`, `Guardian`, `GuardianInvitation`, `Topic`, `Announcement`, `CourseWork`, `CourseWorkMaterial`, `Assignment`, `MultipleChoiceQuestion`, `Material`, `SharedDriveFile`, `DriveFile`, `DriveFolder`, `Link`, `YouTubeVideo`, `Form`, `GeminiGem`, `NotebookLmNotebook`, `IndividualStudentsOptions`, `ModifyIndividualStudentsOptions`, `ModifyCourseWorkAssigneesRequest`, `ModifyAnnouncementAssigneesRequest`, `StudentSubmission`, `AssignmentSubmission`, `Attachment`, `ShortAnswerSubmission`, `MultipleChoiceSubmission`, `ModifyAttachmentsRequest`, `TurnInStudentSubmissionRequest`, `ReclaimStudentSubmissionRequest`, `ReturnStudentSubmissionRequest`, `SubmissionHistory`, `StateHistory`, `GradeHistory`, `Rubric`, `Criterion`, `Level`, `RubricGrade`, `AddOnAttachment`, `AddOnAttachmentStudentSubmission`, `AddOnContext`, `TeacherContext`, `StudentContext`, `EmbedUri`, `CopyHistory`, `Registration`, `Feed`, `CourseRosterChangesInfo`, `CourseWorkChangesInfo`, `CloudPubsubTopic`, `Date`, `TimeOfDay`, `Empty` и все `List*Response`).
- [x] **Gate Check `[P1]`:** выполнить `.venv/bin/pytest -q` (убедиться, что новые 39 таблиц проходят `test_sqlite_schema_has_zero_pii_columns` с `0` нарушений!).


---

## ПАКЕТ 2: Профили (`userProfiles`), OAuth2 (24 скоупа), `verifiedTeacher` и 5-ролевой RBAC-движок

### Файлы пакета `[P2]`
- **Создать:** `app/v1/rbac.py`, `app/v1/router_users.py`
- **Изменить:** `app/v1/__init__.py`, `app/main.py`

### Задачи пакета `[P2]`
- [x] **2.1. Движок аутентификации и 24 OAuth 2.0 скоупов (`app/v1/rbac.py`):**
  - Объявить словарь констант всех **24 OAuth 2.0 скоупов** из `classroom_v1.json` (ТОЛЬКО в `app/v1/rbac.py`, никогда не копировать эти URL в `app/static/`!):
    1. `classroom.courses` / `classroom.courses.readonly`
    2. `classroom.rosters` / `classroom.rosters.readonly`
    3. `classroom.profile.emails` / `classroom.profile.photos`
    4. `classroom.coursework.students` / `classroom.coursework.students.readonly`
    5. `classroom.coursework.me` / `classroom.coursework.me.readonly`
    6. `classroom.courseworkmaterials` / `classroom.courseworkmaterials.readonly`
    7. `classroom.announcements` / `classroom.announcements.readonly`
    8. `classroom.topics` / `classroom.topics.readonly`
    9. `classroom.guardianlinks.students` / `classroom.guardianlinks.students.readonly` / `classroom.guardianlinks.me.readonly`
    10. `classroom.push-notifications`
    11. `classroom.student-submissions.students.readonly` / `classroom.student-submissions.me.readonly`
    12. `classroom.addons.teacher` / `classroom.addons.student`
  - Реализовать `resolve_auth_context(request: Request, conn) -> AuthContext`:
    - Если передан заголовок `Authorization: Bearer <token>`: хеширует токен `SHA-256`, ищет активную запись в `oauth_tokens` (`expires_at > now`), возвращает `AuthContext(user=..., client_id=row["client_id"], scopes=set(json.loads(row["scopes_json"])), is_first_party=False)`. При отсутствии/истечении токена -> `api_error(401, "UNAUTHENTICATED", "Недействительный OAuth-токен")`.
    - Иначе проверяет штатную HttpOnly cookie `pb_pass` через существующий `app/passport/security.py` -> при успехе возвращает `AuthContext(user=..., client_id="first_party", scopes=ALL_24_SCOPES, is_first_party=True)`.
    - Если `user["account_disabled"] == 1` -> `api_error(403, "PERMISSION_DENIED", "Аккаунт деактивирован администратором")`.
  - Реализовать `require_scopes(ctx: AuthContext, any_of: tuple[str, ...])`: проверяет пересечение `ctx.scopes` со списком разрешённых для метода скоупов (write-скоуп автоматически покрывает парный `.readonly`-скоуп); при отказе -> `api_error(403, "PERMISSION_DENIED", "Недостаточно OAuth scopes", reason="ACCESS_TOKEN_SCOPE_INSUFFICIENT")`.
- [x] **2.2. Матрица 5 ролей и проверка Developer-привязки (`app/v1/rbac.py`):**
  - Реализовать `get_course_role(conn, class_id: int, user: dict) -> str | None`:
    - `'ADMIN'` (если `user["role"] == "admin"`),
    - `'OWNER'` (если `classes.teacher_id == user["id"]`),
    - `'TEACHER'` (если есть запись в `course_teachers(class_id, user["id"])`),
    - `'STUDENT'` (если есть активная запись в `class_members(class_id, user["id"], enrollment_active=1)`),
    - `'GUARDIAN'` (если в `guardians` есть связь `guardian_user_id = user["id"]` с учеником этого курса),
    - иначе `None` -> при попытке чтения чужого курса возвращать `api_error(404, "NOT_FOUND", "Курс не найден или нет доступа")` (защита от перебора ID курсов).
  - Реализовать `assert_developer_project_match(ctx: AuthContext, creator_client_id: str)`:
    - Для сторонних OAuth-клиентов (`not ctx.is_first_party`) операции `PATCH` / `PUT` / `DELETE` над `CourseWork`, `CourseWorkMaterial`, `Announcement`, `Rubric`, `:return`, `patch(draftGrade/assignedGrade)` разрешены **только** если `creator_client_id == ctx.client_id`. При несовпадении -> `api_error(403, "PERMISSION_DENIED", "Объект создан другим приложением", reason="ProjectPermissionDenied")`.
    - Вычислять булево поле `associatedWithDeveloper = (row["creator_client_id"] == ctx.client_id)` во всех ответах API.
- [x] **2.3. Ресурс `userProfiles` и OAuth-эндпоинты (`app/v1/router_users.py`):**
  - `GET /v1/userProfiles/{userId}` (все `def`-маршруты!):
    - Резолвит `"me"`, числовой `id` или строковый `handle` через `resolve_user_id`.
    - Проверяет видимость: пользователь видит себя, коллег/учеников общих курсов, своих подопечных (`guardians`) либо всех при роли `ADMIN`.
    - Формирует Zero-PII `UserProfile`: `id=str(u["id"])`, `name={"givenName": u["handle"], "familyName": "", "fullName": u["handle"]}`, `permissions=[{"permission": "CREATE_COURSE"}]` (если политика `settings.COURSE_CREATE_POLICY` разрешает пользователю создавать курсы), `verifiedTeacher=bool(u["verified_teacher"])`.
    - Поле `emailAddress` (синтетический локальный идентификатор `f"{u['handle']}@bormoclass.local"`, без реального PII!) включается в ответ **только** при наличии скоупа `classroom.profile.emails`; поле `photoUrl` (`/api/v1-avatar/{avatar_seed}.svg` — локальный детерминированный SVG-генератор аватара) включается **только** при наличии скоупа `classroom.profile.photos`.
  - Вспомогательные маршруты выпуска локальных OAuth-токенов для интеграций и Add-ons:
    - `POST /api/v1-oauth/clients` (регистрация `oauth_clients`, выдача `client_id` и одноразового `client_secret`),
    - `POST /api/v1-oauth/token` (обмен `client_id` + `client_secret` + `scopes` для текущего пользователя или `refresh` на Bearer-токен в `oauth_tokens`),
    - `GET /api/v1-avatar/{seed}.svg` (генерация геометрического SVG-аватара на лету без диска и внешних шрифтов).
- [x] **Gate Check `[P2]`:** выполнить `.venv/bin/pytest -q` (проверить `0` ошибок в существующих тестах и отсутствие запрещённых строк).

---

## ПАКЕТ 3: Курсы (`courses`), 5 состояний `courseState`, Псевдонимы (`aliases`), Копирование курса и «О курсе»

### Файлы пакета `[P3]`
- **Создать:** `app/v1/router_courses.py`
- **Изменить:** `app/classroom/router_classes.py`, `app/v1/__init__.py`

### Задачи пакета `[P3]`
- [x] **3.1. Полный CRUD ресурса `courses` (`app/v1/router_courses.py`, 8 методов `classroom_v1.json`):**
  - `POST /v1/courses` (`courses.create`):
    - Валидация заголовка `name` (в БД колонка `classes.title`!): не пустой, `<= 250` символов, **не содержит URL** (`http://`, `https://`, `www.`) — иначе `api_error(400, "INVALID_ARGUMENT", "Название курса не может содержать URL", reason="CourseTitleCannotContainUrl")`.
    - Проверка права создания по `settings.COURSE_CREATE_POLICY`: если обычный учитель создаёт курс для `"me"`, допустим только `courseState="PROVISIONED"` или `"ACTIVE"` (по умолчанию `"PROVISIONED"` при API-вызове стороннего клиента и `"ACTIVE"` из UI); если `ADMIN` указывает чужой `ownerId`, создаётся со статусом `"PROVISIONED"`.
    - Автоматически генерирует уникальный `enrollmentCode` (6–7 символов `[a-z0-9]` без `0/o/1/l`), 5-значный `join_pin` для совместимости с партами, `calendar_token` и корневую папку учителя `teacherFolder` в `stored_folders`, а также вставляет владельца в `course_teachers(is_primary=1)`.
  - `GET /v1/courses/{id}` (`courses.get`): резолвит `id` / `d:` / `p:`, проверяет RBAC, сериализует `Course` (включая `courseMaterialSets`, `teacherFolder`, `gradebookSettings`, `calendarId`, `courseGroupEmail`, `teacherGroupEmail`, `guardiansEnabled`). Секрет `enrollmentCode` отдаётся **только** `OWNER`/`TEACHER`/`ADMIN` и только если `enrollment_enabled == 1`.
  - `GET /v1/courses` (`courses.list`):
    - Параметры `studentId`, `teacherId`, `courseStates` (повторяемый query-параметр), `pageSize` (дефолт `30`, макс `100`), `pageToken`.
    - Инвариант API: одновременная передача `studentId` и `teacherId` запрещена -> `api_error(400, "INVALID_ARGUMENT", "Нельзя указывать studentId и teacherId одновременно")`.
  - `PUT /v1/courses/{id}` (`courses.update`) и `PATCH /v1/courses/{id}` (`courses.patch` с обязательным `updateMask`):
    - Допустимые поля `updateMask`: `name`, `section`, `descriptionHeading`, `description`, `room`, `courseState`, `ownerId`, `subject`, `learningStandardSettings`, `levels`.
    - Инвариант `update`: если `levels` не передан в `PUT`, существующий `classes.levels` сохраняется (не затирается!).
  - `DELETE /v1/courses/{id}` (`courses.delete`): разрешён `OWNER` или `ADMIN` **только** когда `course_state in ('ARCHIVED', 'PROVISIONED', 'DECLINED')` (активный курс сначала нужно перевести в `ARCHIVED`, иначе `400 FAILED_PRECONDITION`).
- [x] **3.2. Конечный автомат 5 состояний `courseState` и блокировка `CourseNotModifiable`:**
  - Строгая таблица переходов в `validate_course_state_transition(old_state, new_state, actor_role)`:
    - `PROVISIONED -> ACTIVE` (`OWNER` принимает подготовленный курс в UI/API или `ADMIN`),
    - `PROVISIONED -> DECLINED` (`OWNER` отклоняет курс),
    - `DECLINED -> PROVISIONED` (только `ADMIN`),
    - `ACTIVE -> ARCHIVED` и `ARCHIVED -> ACTIVE` (`OWNER`, `TEACHER`, `ADMIN`),
    - `ACTIVE -> SUSPENDED` и `SUSPENDED -> ACTIVE` (только `ADMIN`).
    - Любой иной переход -> `api_error(400, "FAILED_PRECONDITION", "Недопустимый переход состояния курса")`.
  - Реализовать хелпер `assert_course_modifiable(course_row, actor_role)`: если `course_state in ('ARCHIVED', 'DECLINED')` или (`course_state == 'SUSPENDED'` и `actor_role != 'ADMIN'`), блокировать любые мутации заданий, сдачи, ростера и ленты с `api_error(403, "PERMISSION_DENIED", "Курс заморожен для изменений", reason="CourseNotModifiable")`.
- [x] **3.3. Псевдонимы курсов (`courses.aliases` — 3 метода `classroom_v1.json`):**
  - `POST /v1/courses/{courseId}/aliases` (`create`): поддерживает `d:<name>` (domain-scoped, требует роли `ADMIN`, виден всем приложениям) и `p:<name>` (project-scoped, привязан к `ctx.client_id`, виден только создавшему приложению). При конфликте `alias_key` -> `409 ALREADY_EXISTS`.
  - `GET /v1/courses/{courseId}/aliases` (`list`): возвращает все `d:*` + `p:*` текущего `ctx.client_id` с пагинацией.
  - `DELETE /v1/courses/{courseId}/aliases/{alias}` (`delete`): удаляет псевдоним (сам курс не удаляется).
- [x] **3.4. Управление кодом записи, передача владения, «О курсе» и `Copy Course` (`app/classroom/router_classes.py`):**
  - Управление `enrollmentCode`: `POST /api/classroom/classes/{class_id}/enrollment-code` с `action in ("regenerate", "disable", "enable")` (синхронно обновляет или отключает код и 5-значный `join_pin`, отдаёт данные для локального SVG QR-кода).
  - Передача владения курсом: `ADMIN` может сменить `ownerId` напрямую через `PATCH /v1/courses/{id}?updateMask=ownerId` (прежний владелец остаётся в `course_teachers` с `is_primary=0`, новый получает `is_primary=1`); обычный `OWNER` передаёт владение двухфазно через `Invitation` с `role="OWNER"` (Пакет 4).
  - Раздел «О курсе» (`CourseMaterialSet`) и оформление шапки: `PATCH /api/classroom/classes/{class_id}/settings` (обновление `theme_color`, `banner_preset`, `video_room_url`, `video_visible_to_students`, `stream_post_mode`, `stream_work_mode`, `show_deleted_items`, `guardians_enabled`) и CRUD наборов постоянных материалов `course_material_sets`.
  - Полное копирование курса `POST /api/classroom/classes/{class_id}/copy`: клонирует метаданные курса (`title`, `section`, `subject`, `theme_color`), все `class_topics`, все `grade_categories`, все `course_material_sets`, все `coursework` и `course_materials` **строго в статусе `DRAFT`** (со сбросом `due_at`, `scheduled_at` и `grading_period_id`), клонирует привязанные `rubrics`, `quizzes`, `practice_sets` и добавляет запись в `copy_history_json` для `addon_attachments`. Ученики, со-учителя, оценки, сдачи и объявления ленты **не копируются**.
- [x] **Gate Check `[P3]`:** выполнить `.venv/bin/pytest -q` (убедиться, что существующие тесты создания класса и входа за парту в `test_classroom_and_sou.py` полностью зелёные).

---

## ПАКЕТ 4: Ростер (`teachers`, `students`), Приглашения (`invitations`), Подгруппы (`studentGroups`) и Опекуны (`guardians`)

### Файлы пакета `[P4]`
- **Создать:** `app/v1/router_roster.py`, `app/v1/router_guardians.py`
- **Изменить:** `app/classroom/router_classes.py`, `app/v1/__init__.py`

### Задачи пакета `[P4]`
- [x] **4.1. Со-преподаватели (`courses.teachers` — 4 метода `classroom_v1.json` в `app/v1/router_roster.py`):**
  - `POST /v1/courses/{courseId}/teachers` (`create`): прямое добавление разрешено `ADMIN` (а в локальном инстансе также `OWNER`); лимит **не более 50 учителей** на курс (`400 FAILED_PRECONDITION`); запрещено добавлять пользователя, который уже числится учеником этого курса (`409 ALREADY_EXISTS`). Создаёт папку учителя и выдаёт доступ `EDIT` к материалам курса.
  - `GET /v1/courses/{courseId}/teachers/{userId}` (`get`) и `GET /v1/courses/{courseId}/teachers` (`list`, `pageSize` дефолт `30`).
  - `DELETE /v1/courses/{courseId}/teachers/{userId}` (`delete`):
    - **Запрещено** удалять основного владельца курса (`classes.teacher_id == target_id`) -> `api_error(403, "PERMISSION_DENIED", "Нельзя удалить владельца курса", reason="CannotDeleteCourseOwner")`.
    - Со-учитель имеет право удалить сам себя (`userId="me"` — покинуть курс), а `OWNER`/`ADMIN` могут удалить любого со-учителя.
- [x] **4.2. Ученики (`courses.students` — 4 метода `classroom_v1.json` + расширенные действия учителя):**
  - `POST /v1/courses/{courseId}/students` (`create`):
    - Если ученик записывается сам (`userId="me"`), обязателен query-параметр `enrollmentCode`: проверяем `classes.enrollment_enabled == 1`, `course_state == 'ACTIVE'` и точное совпадение кода; иначе `403 PERMISSION_DENIED` / `404 NOT_FOUND`.
    - Если записывает `OWNER`/`TEACHER`/`ADMIN`, код не требуется. Запрещено записывать учителя этого же курса.
    - При зачислении: создаётся/реактивируется строка в `class_members(enrollment_active=1)`, создаётся персональная папка `student_folder_id` в `stored_folders`, а для всех опубликованных заданий курса (`ALL_STUDENTS`), где у ученика ещё нет строки в `submissions`, создаются заготовки `StudentSubmission` со статусом `NEW` (если ученик возвращается после отчисления — его прежние `submissions`, история и оценки **автоматически восстанавливаются**!).
  - `GET /v1/courses/{courseId}/students/{userId}` (`get`) и `GET /v1/courses/{courseId}/students` (`list`, `pageSize` дефолт `30`).
  - `DELETE /v1/courses/{courseId}/students/{userId}` (`delete`): для `"me"` проверяет `settings.ALLOW_STUDENT_UNENROLL`; ставит `class_members.enrollment_active = 0` и удаляет из `student_group_members`, **сохраняя** записи в `submissions` на случай повторного зачисления.
  - В `app/classroom/router_classes.py` добавить:
    - `POST /api/classroom/classes/{class_id}/students/{student_id}/mute` (`is_muted = 0 | 1` — заглушенный ученик сдаёт работы, но не может писать посты и публичные комментарии),
    - `POST /api/classroom/classes/{class_id}/students/bulk` (массовое отчисление / mute / unmute выбранных чекбоксами учеников),
    - `GET /api/classroom/classes/{class_id}/students/{student_id}/summary` (индивидуальное досье ученика по курсу с фильтром: `All` / `Turned in` / `Assigned` / `Returned` / `Missing`).
- [x] **4.3. Приглашения в курс (`invitations` — 5 методов `classroom_v1.json`):**
  - `POST /v1/invitations` (`create`): `role in ("STUDENT", "TEACHER", "OWNER")`. Инвариант уникальности: на пару `(courseId, userId)` допускается не более 1 активного приглашения (`409 ALREADY_EXISTS`). Создаёт уведомление в таблице `notifications`.
  - `GET /v1/invitations/{id}` (`get`), `DELETE /v1/invitations/{id}` (`delete`).
  - `GET /v1/invitations` (`list`, `pageSize` дефолт `500`): **обязательно** требует хотя бы один из фильтров `userId` или `courseId`, иначе `api_error(400, "INVALID_ARGUMENT", "Укажите userId или courseId")`.
  - `POST /v1/invitations/{id}:accept` (`accept`): доступен только приглашённому пользователю (`invited_user_id == ctx.user["id"]`):
    - `STUDENT` -> зачисляет в `class_members`,
    - `TEACHER` -> добавляет в `course_teachers`,
    - `OWNER` -> атомарно переводит `classes.teacher_id` на нового владельца, обновляет `is_primary` в `course_teachers`, передаёт права на `teacherFolder` и удаляет использованное приглашение.
- [x] **4.4. Учебные подгруппы для дифференциации (`courses.studentGroups` — 7 методов `classroom_v1.json`):**
  - `POST /v1/courses/{courseId}/studentGroups` (`create`), `GET /v1/courses/{courseId}/studentGroups` (`list`, `pageSize` дефолт `75`), `PATCH /v1/courses/{courseId}/studentGroups/{id}` (`patch` по `updateMask=title`), `DELETE /v1/courses/{courseId}/studentGroups/{id}` (`delete`) — доступно `OWNER`/`TEACHER`/`ADMIN`.
  - Участники подгруппы (`courses.studentGroups.studentGroupMembers`):
    - `POST /v1/courses/{courseId}/studentGroups/{studentGroupId}/studentGroupMembers` (`create` — проверяет, что `userId` является активным учеником `courseId`, иначе `400 FAILED_PRECONDITION`),
    - `GET /v1/courses/{courseId}/studentGroups/{studentGroupId}/studentGroupMembers` (`list`, `pageSize` дефолт `100`),
    - `DELETE /v1/courses/{courseId}/studentGroups/{studentGroupId}/studentGroupMembers/{userId}` (`delete`).
- [x] **4.5. Опекуны / Родители и Zero-PII сводки (`app/v1/router_guardians.py` — 7 методов `classroom_v1.json`):**
  - Приглашения опекунов (`userProfiles.guardianInvitations`):
    - `POST /v1/userProfiles/{studentId}/guardianInvitations` (`create`): принимает `invitedEmailAddress` (сохраняется как обезличенный `invite_target` в `guardian_invitations` + генерируется одноразовый 8-символьный код подтверждения родителя, возвращаемый учителю для передачи родителю без отправки внешней почты!).
    - `GET /v1/userProfiles/{studentId}/guardianInvitations/{invitationId}` (`get`),
    - `GET /v1/userProfiles/{studentId}/guardianInvitations` (`list` — поддерживает `studentId="-"` для выборки по всем ученикам, фильтр `states=PENDING|COMPLETE` и `invitedEmailAddress`),
    - `PATCH /v1/userProfiles/{studentId}/guardianInvitations/{invitationId}` (`patch` с `updateMask=state`), а также удобный UI-эндпоинт `POST /api/classroom/guardians/accept-code` (родитель под своим Passport-аккаунтом вводит код подтверждения -> приглашение переходит в `COMPLETE`, создаётся связь в `guardians`).
  - Связи опекунов (`userProfiles.guardians`):
    - `GET /v1/userProfiles/{studentId}/guardians/{guardianId}` (`get`),
    - `GET /v1/userProfiles/{studentId}/guardians` (`list` — поддерживает `studentId="-"`, а также `invitedEmailAddress` и просмотр своих подопечных родителем),
    - `DELETE /v1/userProfiles/{studentId}/guardians/{guardianId}` (`delete` — доступно родителю для самоотписки, учителю или `ADMIN`).
  - Реализовать функцию `build_guardian_digest(conn, guardian_user_id: int, period_days: int = 7) -> dict` и эндпоинт `GET /api/classroom/guardians/my-digest`: собирает по всем подопечным родителя (в курсах с `guardians_enabled == 1`) три секции Google Classroom Guardian Summary **строго без прямого доступа родителя к чужим работам и чатам класса**:
    1. `missingWork` (просроченные несданные задания),
    2. `upcomingWork` (дедлайны на ближайшие 7 дней),
    3. `classActivity` (новые объявления, опубликованные задания и возвращённые оценки подопечного).
- [x] **Gate Check `[P4]`:** выполнить `.venv/bin/pytest -q`.

---

## ПАКЕТ 5: Файловое хранилище (`DriveFile`), Вложения (`Material`), Режимы `VIEW`/`EDIT`/`STUDENT_COPY`, Доски и ACL-трансфер

### Файлы пакета `[P5]`
- **Создать:** `app/storage/__init__.py`, `app/storage/engine.py`, `app/storage/router_files.py`
- **Изменить:** `app/classroom/router_board.py`, `app/main.py`

### Задачи пакета `[P5]`
- [x] **5.1. Контентно-адресуемый движок хранения и папок (`app/storage/engine.py`):**
  - Хранение бинарных блобов в `data/storage/{sha256[:2]}/{sha256}` (дедупликация одинаковых шаблонов при `STUDENT_COPY` за `O(1)` дискового места!).
  - Белый список безопасных расширений/MIME (`application/pdf`, `image/png`, `image/jpeg`, `image/webp`, `image/svg+xml`, `text/plain`, `text/markdown`, `text/csv`, `application/json`, `application/zip`, `audio/webm`, `audio/mpeg`, `video/webm`, `video/mp4`, `.py`, `.js`, `.html`, `.excalidraw`) и жёсткий лимит `settings.MAX_UPLOAD_BYTES`. HTML/SVG при отдаче снабжать заголовками `Content-Security-Policy: sandbox` и `X-Content-Type-Options: nosniff` для защиты от Stored XSS.
  - Иерархия виртуальных папок `stored_folders`:
    - `COURSE_TEACHER_ROOT` (`Course.teacherFolder`),
    - `ASSIGNMENT_WORK_FOLDER` (`Assignment.studentWorkFolder`),
    - `STUDENT_COURSE_FOLDER` (`Student.studentWorkFolder`).
  - Валидатор вложений `validate_materials_list(materials: list[dict])`: **строго не более 20 вложений** (`Material` или `Attachment`) на один объект (`CourseWork`, `Announcement`, `CourseWorkMaterial`, `StudentSubmission`), иначе `api_error(400, "INVALID_ARGUMENT", "Максимум 20 вложений на объект")`.
- [x] **5.2. Маршруты загрузки, HTTP Range-стриминга, ссылок и записи голоса/видео (`app/storage/router_files.py`, все маршруты синхронные `def`!):**
  - `POST /api/storage/upload`: принимает `UploadFile` (`data = file.file.read()`), вычисляет `sha256`, сохраняет блоб на диск, создаёт запись в `stored_files` и `file_acl(owner, 'OWNER')`, возвращает объект, сериализуемый как Google Classroom `DriveFile {id, title, alternateLink, thumbnailUrl}`.
  - `GET /api/storage/files/{file_id}` и `GET /api/storage/files/{file_id}/download`: проверяет доступ через `check_file_access(conn, file_id, user)` (владелец, учитель курса, явный `file_acl` или вложение опубликованного поста курса); поддерживает заголовок `Range: bytes=start-end` (`206 Partial Content`) для перемотки локальных видеолекций и голосовых инструкций учителя (`MediaRecorder` `.webm`).
  - `GET /api/storage/files/{file_id}/thumbnail.svg`: генерирует аккуратную локальную SVG-превьюшку по типу файла/доски.
  - `POST /api/storage/link-preview`: валидирует внешний URL, блокирует приватные/локальные IP (`127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16`, `::1` — защита от SSRF!) и реализует **Smart Link Upgrade**: если ссылка указывает на внутренний `/api/storage/files/{id}`, квиз `/quiz/{id}` или доску `/board/{id}`, автоматически повышает тип вложения `Link` до типизированного `DriveFile` / `Form`!
  - `GET /api/storage/files/{file_id}/annotations` и `POST /api/storage/files/{file_id}/annotations`: сохранение и чтение координатных рамок `rect_json`, рукописных штрихов красной ручки `stroke_json` и текстовых заметок учителя на конкретной странице `page_num` работы ученика (используется в `SpeedGrader`).
- [x] **5.3. Три режима раздачи файлов (`ShareMode`) и интеграция персональных/групповых досок (`app/storage/engine.py` + `app/classroom/router_board.py`):**
  - Реализовать обработку всех 3 режимов `SharedDriveFile.shareMode`:
    1. `VIEW` (*Students can view file*): всем назначенным ученикам выдаётся `VIEW` (только чтение).
    2. `EDIT` (*Students can edit file*): всем назначенным ученикам (или членам выбранной `studentGroup`) выдаётся общий `EDIT` на один файл или общую групповую Excalidraw-доску.
    3. `STUDENT_COPY` (*Make a copy for each student*): реализовать идемпотентную функцию `ensure_student_copy(conn, coursework_row, student_id: int)`:
       - Для каждого шаблона с `shareMode == "STUDENT_COPY"` проверяет в `submission_attachments`, создана ли уже копия с `source_template_id`.
       - Если нет — создаёт персональную запись в `stored_files` с заголовком `f"{student_handle} — {template_title}"` (для `.excalidraw` создаёт независимый JSON-холст с предзаполненным шаблоном учителя!), назначает `owner_user_id = student_id`, выдаёт `EDIT` ученику и всем учителям курса, и прикрепляет в `submission_attachments(created_by_template=1)`.
       - Вызывается автоматически при публикации задания, при дозачислении нового ученика в курс и лениво при первом открытии сдачи учеником.
- [x] **5.4. Автоматический трансфер прав доступа (`ACL Ownership & Lock Transfer`) при сдаче и возврате (`app/storage/engine.py`):**
  - Реализовать функцию `sync_submission_acl(conn, coursework_id: int, student_id: int, new_v1_state: str)`, вызываемую при каждом переходе `StudentSubmission`:
    - При `TURNED_IN`: все прикреплённые файлы и персональные Excalidraw-доски ученика в `file_acl` для `student_id` мгновенно переключаются в режим `'VIEW'` (**заморозка редактирования после сдачи!** Ученик видит свою работу, но любая попытка перезаписать файл или холст доски отклоняется с `403 Locked after Turn-In`), а учителя курса получают `'EDIT'` + право рисовать слой проверки в `file_annotations`.
    - При `RECLAIMED_BY_STUDENT` или `RETURNED`: в `file_acl` для `student_id` возвращается режим `'EDIT'` (ученик снова может дорабатывать файл/доску, при этом замечания и красные пометки учителя в `file_annotations` остаются сохранёнными как отдельный неизменяемый слой!).
- [x] **Gate Check `[P5]`:** выполнить `.venv/bin/pytest -q`.


---

## ПАКЕТ 6: Лента (`Stream`), Объявления (`announcements`), Фоновый планировщик (`scheduledTime`) и 3-уровневые комментарии

### Файлы пакета `[P6]`
- **Создать:** `app/v1/router_announcements.py`, `app/classroom/router_comments.py`, `app/worker/__init__.py`, `app/worker/scheduler.py`
- **Изменить:** `app/v1/__init__.py`, `app/main.py`

### Задачи пакета `[P6]`
- [x] **6.1. Ресурс `courses.announcements` (`app/v1/router_announcements.py` — 6 базовых методов `classroom_v1.json`):**
  - `POST /v1/courses/{courseId}/announcements` (`create`):
    - Проверяет `assert_course_modifiable`. Для ученика проверяет `classes.stream_post_mode == "STUDENTS_CAN_POST_AND_COMMENT"` и `class_members.is_muted == 0` (ученик может публиковать только со `state="PUBLISHED"` и `assigneeMode="ALL_STUDENTS"`).
    - Инварианты `scheduledTime`: допустим **только** при `state == "DRAFT"` и строго в будущем (`scheduled_at > now`); иначе `api_error(400, "INVALID_ARGUMENT", "scheduledTime требует state=DRAFT и дату в будущем")`.
    - Инвариант `EmptyAssignees`: если `assigneeMode == "INDIVIDUAL_STUDENTS"` и `individualStudentsOptions.studentIds` пуст -> `api_error(400, "INVALID_ARGUMENT", "Список учеников не может быть пустым", reason="EmptyAssignees")`.
  - `GET /v1/courses/{courseId}/announcements/{id}` (`get`): ученик видит только `PUBLISHED`, где он входит в `ALL_STUDENTS` или `target_students_json`; учитель видит также `DRAFT`, а при `show_deleted_items == 1` или явном фильтре `announcementStates=DELETED` — и `DELETED`.
  - `GET /v1/courses/{courseId}/announcements` (`list`): параметры `announcementStates` (по умолчанию `PUBLISHED`), `orderBy="updateTime desc"`, `pageSize`, `pageToken`.
  - `PATCH /v1/courses/{courseId}/announcements/{id}` (`patch` по `updateMask`: `text`, `state`, `scheduledTime`) и `DELETE /v1/courses/{courseId}/announcements/{id}` (`delete` — переводит в `state="DELETED"` с сохранением для аудита учителя). Проверка `assert_developer_project_match`.
  - `POST /v1/courses/{courseId}/announcements/{id}:modifyAssignees` (`modifyAssignees`): переключает `ALL_STUDENTS` <-> `INDIVIDUAL_STUDENTS` с инкрементальным `addStudentIds` / `removeStudentIds`.
- [x] **6.2. Расширенные функции Ленты: закрепление, кросс-постинг и `Reuse Post` (`app/v1/router_announcements.py`):**
  - `POST /api/classroom/classes/{class_id}/announcements/{id}/pin`: закрепление объявления наверху ленты (`is_pinned = 1`) или «Переместить наверх» (`updated_at = now`).
  - `POST /api/classroom/stream/multi-post`: одновременная публикация объявления или задания сразу в несколько выбранных курсов `target_class_ids` (инвариант Google Classroom: при `len(target_class_ids) > 1` автоматически применяется `assignee_mode = "ALL_STUDENTS"`).
  - `GET /api/classroom/reuse-posts` и `POST /api/classroom/classes/{class_id}/reuse-post`: каталог всех прежних объявлений, заданий и материалов учителя (включая `ARCHIVED` курсы!) с поиском и мгновенным переиспользованием в текущем курсе (с опцией «Создать новые копии всех вложений»).
- [x] **6.3. Трёхуровневая система комментариев и модерации (`app/classroom/router_comments.py`):**
  - **Публичные комментарии класса (`class_comments`):**
    - `GET /api/classroom/classes/{class_id}/comments?parent_kind=...&parent_id=...`, `POST /api/classroom/classes/{class_id}/comments`, `PATCH .../comments/{id}`, `DELETE .../comments/{id}`.
    - Проверяет `stream_post_mode` (`ONLY_TEACHERS_CAN_POST_OR_COMMENT` блокирует комментарии учеников; `STUDENTS_CAN_ONLY_COMMENT` разрешает комментарии, но блокирует посты) и флаг `is_muted == 0`.
    - Парсер упоминаний `@handle`: находит участников курса по позывному и создаёт им персональную запись в `notifications`.
    - Мягкое удаление (`is_deleted = 1`): удалённый модератором комментарий скрыт от учеников, но виден учителям с пометкой *«Удалено»* при включённом тумблере `show_deleted_items`.
  - **Приватные комментарии к сдаче (`private_comments`):**
    - `GET /api/classroom/coursework/{cw_id}/submissions/{student_id}/private-comments` и `POST ...`: строгая изоляция 1-на-1 — доступ имеют **только** сам `student_id` и учителя курса (`OWNER`/`TEACHER`); мгновенная рассылка события через `sse_hub`.
  - **Банк комментариев учителя (`comment_bank`):** добавить быстрый поиск по `#хештегу` и подстроке `GET /api/classroom/comment-bank?q=...` для автодополнения в `SpeedGrader`.
- [x] **6.4. Фоновый планировщик `scheduledTime` и очередей (`app/worker/scheduler.py` + `app/main.py`):**
  - Запустить корутину `run_background_scheduler()` через `asyncio.create_task` внутри `lifespan` в `app/main.py` с чистой остановкой по `asyncio.CancelledError`:
    - Каждые `15` секунд находит `DRAFT`-записи в `announcements`, `coursework` и `course_materials`, где `scheduled_at IS NOT NULL AND scheduled_at <= now`, атомарно переводит их в `state = 'PUBLISHED'`, очищает `scheduled_at = NULL`, материализует шаблоны `STUDENT_COPY`, пишет `notifications` ученикам и пушит событие в `sse_hub` и `push_registrations`.
    - Обрабатывает ретраи недоставленных вебхуков в `webhook_deliveries` (`delivered = 0 AND next_retry_at <= now`, экспоненциальный backoff до 5 попыток).
- [x] **Gate Check `[P6]`:** выполнить `.venv/bin/pytest -q`.

---

## ПАКЕТ 7: Темы (`topics`), Материалы (`courseWorkMaterials`), Задания (`courseWork`), Квизы, Практикумы, Антиплагиат и Стандарты

### Файлы пакета `[P7]`
- **Создать:** `app/v1/router_classwork.py`, `app/classroom/router_quizzes_and_sets.py`
- **Изменить:** `app/classroom/router_coursework.py`, `app/v1/__init__.py`, `app/main.py`

### Задачи пакета `[P7]`
- [x] **7.1. Темы курса (`courses.topics` — 5 методов `classroom_v1.json` в `app/v1/router_classwork.py`):**
  - `POST /v1/courses/{courseId}/topics` (`create`), `GET .../topics/{id}` (`get`), `GET .../topics` (`list`, `pageSize` дефолт `30`), `PATCH .../topics/{id}` (`patch` по `updateMask=name`), `DELETE .../topics/{id}` (`delete`).
  - Нормализация `name` (в БД колонка `class_topics.title`!): обрезка крайних пробелов, схлопывание внутренних пробелов, длина `1..100` символов, проверка регистронезависимой уникальности внутри курса. При удалении темы сами задания и материалы **не удаляются** (`topic_id` сбрасывается в `NULL`).
  - `POST /api/classroom/classes/{class_id}/topics/reorder`: сохранение порядка тем и карточек внутри темы (`sort_order`) после Drag-and-Drop.
- [x] **7.2. Справочные материалы (`courses.courseWorkMaterials` — 5 базовых методов `classroom_v1.json`):**
  - `POST /v1/courses/{courseId}/courseWorkMaterials` (`create`), `GET .../courseWorkMaterials/{id}` (`get`), `GET .../courseWorkMaterials` (`list` с фильтрами `courseWorkMaterialStates`, `orderBy`, `materialDriveId`, `materialLink`), `PATCH .../courseWorkMaterials/{id}` (`patch`), `DELETE .../courseWorkMaterials/{id}` (`delete`).
  - Не имеют оценок, дедлайнов и `StudentSubmission`; поддерживают `PUBLISHED`/`DRAFT`/`DELETED`, `scheduledTime`, `topicId` и индивидуальное назначение ученикам/подгруппам.
- [x] **7.3. Задания и Вопросы (`courses.courseWork` — 6 базовых методов `classroom_v1.json`):**
  - `POST /v1/courses/{courseId}/courseWork` (`create`), `GET .../courseWork/{id}` (`get`), `GET .../courseWork` (`list` с `courseWorkStates`, `orderBy="updateTime desc" | "dueDate asc"`, `pageSize`), `PATCH .../courseWork/{id}` (`patch` по `updateMask`: `title`, `description`, `state`, `dueDate`, `dueTime`, `maxPoints`, `scheduledTime`, `submissionModificationMode`, `topicId`, `gradingPeriodId`), `DELETE .../courseWork/{id}` (`delete`), `POST .../courseWork/{id}:modifyAssignees` (`modifyAssignees`).
  - Полная реализация всех **3 типов `workType`**:
    1. `ASSIGNMENT`: создаёт `Assignment.studentWorkFolder`, материализует `STUDENT_COPY`-файлы/доски при публикации.
    2. `SHORT_ANSWER_QUESTION`: учитывает `submissionModificationMode` (`MODIFIABLE_UNTIL_TURNED_IN` vs `MODIFIABLE`) и флаг `peer_replies_enabled` — если включён, эндпоинт `GET /api/classroom/coursework/{cw_id}/peer-answers` открывает ответы одноклассников и ветку обсуждения **только тем ученикам, кто уже сдал собственный ответ (`TURNED_IN`/`RETURNED`)**!
    3. `MULTIPLE_CHOICE_QUESTION`: минимум 2 непустых уникальных варианта в `choices_json`; при `show_class_summary == 1` после сдачи возвращает ученику живую гистограмму голосов класса по вариантам.
  - Инварианты баллов и дедлайнов: `maxPoints == 0` означает задание **«Без оценки» (Ungraded)**; если задан `dueDate`, то в `/v1` обязателен и `dueTime` (UTC), иначе `400 INVALID_ARGUMENT`; флаг `close_after_due == 1` жёстко блокирует сдачу и изменение вложений после наступления `due_at`.
  - Поддержка назначения на учебные подгруппы `studentGroups`: эндпоинт `POST /api/classroom/classes/{class_id}/coursework/assign-groups` разворачивает выбранные `group_ids` в список `studentIds` для `INDIVIDUAL_STUDENTS`.
- [x] **7.4. Автопроверяемые Квизы (`Quiz Assignment`), Адаптивные `Practice Sets`, Антиплагиат и Стандарты (`app/classroom/router_quizzes_and_sets.py`):**
  - **Встроенный движок тестов (`quizzes` + `quiz_attempts`):**
    - CRUD теста `POST/GET/PATCH /api/classroom/quizzes` с **7 типами вопросов**: `SINGLE_CHOICE`, `MULTIPLE_CHOICE`, `SHORT_TEXT` (точное совпадение без регистра), `PARAGRAPH` (ручная допроверка), `NUMERIC_TOLERANCE` (`|ans - target| <= eps`), `MATCHING` (соответствие пар), `ORDERING` (правильный порядок).
    - Настройки: `shuffle_questions`, таймер `time_limit_sec`, анти-списывание `lock_tab_focus` (счётчик ухода с вкладки `focus_lost_count`), `show_correct_answers`, `auto_import_grades`.
    - `POST /api/classroom/quizzes/{quiz_id}/submit`: мгновенно рассчитывает `auto_score`, при `auto_import_grades == 1` записывает балл в `submissions.draft_grade` и автоматически переводит `StudentSubmission` в `TURNED_IN`!
  - **Интерактивные практикумы (`practice_sets` + `practice_attempts`):**
    - CRUD карточек задач с массивом пошаговых подсказок `hints`, проверкой ответа налету `POST /api/classroom/practice-sets/{id}/check-card`, сохранением чернового рукописного блокнота решения `scratchpad_json` и аналитикой учителя `GET /api/classroom/practice-sets/{id}/insights` (тепловая карта «проблемных карточек», где ученики ошибались `>= 2` раз или брали подсказки).
  - **Локальные отчёты об уникальности (`Originality Reports` — `originality_reports`):**
    - 100% локальный алгоритм без облаков: извлекает текст из текстовых файлов/ответов/кода и ищет совпадения по базе всех работ курса и материалов с помощью **шингла Winnowing `5-gram`** (для текста) и **структурного сравнения токенов `ast`** (для `.py`/`.js`).
    - Контроль лимита: ученик может запустить самопроверку **не более 3 раз** до сдачи (`student_runs_used <= 3`), для учителя проверка запускается без лимитов при `:turnIn` и по кнопке; возвращает `match_percent` и подсвеченные цитаты `matches_json`.
  - **Образовательные стандарты и навыки (`learning_standards` + `item_learning_goals`):**
    - Предзаполнить справочник демонстрационными стандартами **IMS Global CASE GUID** и кодификатором **ФГОС / ФРП** (`POST /api/classroom/standards/seed`), реализовать привязку `learning_goals` к заданиям и матрицу освоения стандартов учениками курса `GET /api/classroom/classes/{class_id}/standards-mastery`.
- [x] **Gate Check `[P7]`:** выполнить `.venv/bin/pytest -q` (включая проверку сохранения правила 1-го класса и существующих заданий в `test_classroom_and_sou.py`).

---

## ПАКЕТ 8: Сдача работ (`studentSubmissions`), Автомат 5 состояний, `SubmissionHistory`, Рубрики, Категории и Периоды

### Файлы пакета `[P8]`
- **Создать:** `app/v1/router_submissions.py`, `app/v1/router_rubrics_grades.py`
- **Изменить:** `app/classroom/router_submissions.py`, `app/v1/__init__.py`

### Задачи пакета `[P8]`
- [x] **8.1. Ресурс `courses.courseWork.studentSubmissions` (`app/v1/router_submissions.py` — 7 базовых методов `classroom_v1.json`):**
  - `GET /v1/courses/{courseId}/courseWork/{courseWorkId}/studentSubmissions/{id}` (`get`).
  - `GET /v1/courses/{courseId}/courseWork/{courseWorkId}/studentSubmissions` (`list`):
    - Полная поддержка **wildcard `courseWorkId="-"`** (выгрузка сдач сразу по всем заданиям курса за один запрос!).
    - Фильтры `userId`, `states` (мульти-фильтр), `late` (`LATE_ONLY` | `NOT_LATE_ONLY`), `pageSize`, `pageToken`.
  - `POST .../studentSubmissions/{id}:modifyAttachments` (`modifyAttachments`): добавляет вложения в `submission_attachments` (доступно при `NEW`, `CREATED`, `RECLAIMED_BY_STUDENT`, `RETURNED`; при первом действии переводит `NEW -> CREATED`; при `close_after_due == 1` и `now > due_at` отклоняет с `403 PERMISSION_DENIED`).
  - `POST .../studentSubmissions/{id}:turnIn` (`turnIn`): доступен **только самому ученику**; проверяет `close_after_due`; переводит в `TURNED_IN`, фиксирует `is_late = int(due_at is not None and now > due_at)`, вызывает `sync_submission_acl(..., 'TURNED_IN')`, пишет `StateHistory("TURNED_IN")`.
  - `POST .../studentSubmissions/{id}:reclaim` (`reclaim`): доступен **только самому ученику** из `TURNED_IN` (при `workType == "ASSIGNMENT"` или `submissionModificationMode == "MODIFIABLE"`); переводит в `RECLAIMED_BY_STUDENT`, вызывает `sync_submission_acl(..., 'RECLAIMED_BY_STUDENT')`, пишет `StateHistory("RECLAIMED_BY_STUDENT")`.
  - `PATCH .../studentSubmissions/{id}` (`patch` по `updateMask`: `draftGrade`, `assignedGrade`, `draftRubricGrades`, `assignedRubricGrades`): доступен учителям курса (с проверкой `assert_developer_project_match`), пишет `GradeHistory` (`DRAFT_GRADE_POINTS_EARNED_CHANGE` / `ASSIGNED_GRADE_POINTS_EARNED_CHANGE`). При изменении `CourseWork.maxPoints` в Пакете 7 автоматически дописывать `GradeHistory("MAX_POINTS_CHANGE")`!
  - `POST .../studentSubmissions/{id}:return` (`return`): доступен учителям курса; если `draft_grade is not None`, копирует `assigned_grade = draft_grade` и `assigned_rubric_json = draft_rubric_json`, переводит в `RETURNED` (даже если ученик не нажимал `turnIn` — например, оценка за устный ответ!), вызывает `sync_submission_acl(..., 'RETURNED')`, пишет `StateHistory("RETURNED")`, создаёт уведомление ученику.
  - **Жёсткая фильтрация приватности оценок:** для `STUDENT` поля `draftGrade` и `draftRubricGrades` **всегда скрываются** (`None`) до момента `:return`!
  - Добавить `POST /api/classroom/classes/{class_id}/coursework/{cw_id}/batch-return` (массовый возврат всех проверенных работ с черновой оценкой одним кликом и общим комментарием).
- [x] **8.2. Критериальные Рубрики (`courses.courseWork.rubrics` — 5 методов + `updateRubric` в `app/v1/router_rubrics_grades.py`):**
  - `POST /v1/courses/{courseId}/courseWork/{courseWorkId}/rubrics` (`create`), `GET .../rubrics/{id}` (`get`), `GET .../rubrics` (`list`), `PATCH .../rubrics/{id}` (`patch`), `DELETE .../rubrics/{id}` (`delete`) и `PATCH /v1/courses/{courseId}/courseWork/{courseWorkId}/rubric` (`courses.courseWork.updateRubric`).
  - Поддержка **оцениваемых (`is_scored=1`)** и **неоцениваемых (`is_scored=0`)** рубрик (до 50 критериев, до 10 уровней в критерии; инвариант: баллы уровней указаны либо во всех критериях, либо ни в одном).
  - Блокировка структуры: если хотя бы одной работе в задании уже выставлены баллы по рубрике, изменение списка критериев блокируется с `400 FAILED_PRECONDITION` до сброса оценок или удаления рубрики.
  - Клик по уровням критериев в `SpeedGrader` (`POST /api/classroom/coursework/{cw_id}/submissions/{student_id}/grade-rubric`) автоматически суммирует баллы уровней и пересчитывает `draft_grade`.
  - Импорт и экспорт рубрик в JSON и табличный CSV (`POST /api/classroom/classes/{class_id}/rubrics/import`, `GET /api/classroom/rubrics/{id}/export.csv`).
- [x] **8.3. Настройки журнала (`GradebookSettings`), Категории оценок, Учебные периоды (`GradingPeriodSettings`), `Excused` и `СОУ`:**
  - Управление `GradeCategory` и `GradebookSettings` (`PATCH /api/classroom/classes/{class_id}/gradebook-settings`):
    - Режимы `TOTAL_POINTS` и `WEIGHTED_CATEGORIES` (при `WEIGHTED_CATEGORIES` сумма `weight_micros` всех категорий обязана равняться ровно `1_000_000` = `100%`; если в какой-то категории у ученика пока `0` оценённых работ, веса остальных активных категорий пропорционально нормируются!).
    - Настройка видимости итогового балла ученикам: `SHOW_OVERALL_GRADE` | `HIDE_OVERALL_GRADE` | `SHOW_TEACHERS_ONLY`.
    - Статус `is_excused = 1` (**«Освобождён / Зачтено без влияния»**): полностью исключает задание из числителя и знаменателя итогового балла конкретного ученика.
  - Ресурс `courses.gradingPeriodSettings` (2 метода `classroom_v1.json`):
    - `GET /v1/courses/{courseId}/gradingPeriodSettings` и `PATCH /v1/courses/{courseId}/gradingPeriodSettings` (`updateMask`: `gradingPeriods`, `applyToExistingCoursework`).
    - Валидация четвертей/триместров/семестров: `startDate <= endDate`, строгое отсутствие пересечений дат между периодами и уникальность названий (`400 INVALID_ARGUMENT` при нарушении). При `applyToExistingCoursework == True` автоматически проставляет `grading_period_id` всем заданиям курса, чей `due_at` попадает в интервал периода!
  - Сводная матрица журнала `GET /api/classroom/classes/{class_id}/gradebook` (с фильтром по `grading_period_id`): возвращает сетку `ученики × задания`, среднее по каждому заданию (`Class average`), итоговый `%` по каждому ученику, а также российские метрики **Успеваемость (%)**, **Качество знаний (%)** и **СОУ (%)**.
- [x] **Gate Check `[P8]`:** выполнить `.venv/bin/pytest -q` (убедиться, что расчёт СОУ в `test_classroom_and_sou.py` проходит без единой регрессии).

---

## ПАКЕТ 9: Дополнения (`AddOnAttachments` — 29 методов), Push-подписки (`registrations`), Уведомления, Календарь `.ics` и Админка

### Файлы пакета `[P9]`
- **Создать:** `app/v1/router_addons.py`, `app/v1/router_registrations.py`, `app/classroom/router_notifications_admin.py`
- **Изменить:** `app/classroom/router_global.py`, `app/worker/scheduler.py`, `app/v1/__init__.py`, `app/main.py`

### Задачи пакета `[P9]`
- [x] **9.1. Полный фреймворк расширений Classroom Add-ons — все 29 методов `classroom_v1.json` + LTI 1.3 (`app/v1/router_addons.py`):**
  - Контекст запуска iframe (**4 метода** `getAddOnContext`):
    - `GET /v1/courses/{courseId}/courseWork/{itemId}/addOnContext`
    - `GET /v1/courses/{courseId}/announcements/{itemId}/addOnContext`
    - `GET /v1/courses/{courseId}/courseWorkMaterials/{itemId}/addOnContext`
    - `GET /v1/courses/{courseId}/posts/{postId}/addOnContext` (полиморфный ресурс `posts`).
    - Возвращает `AddOnContext` с `courseId`, `itemId`, `postId`, `supportsStudentWork` (`True` для `courseWork`), а также `teacherContext` либо `studentContext(submissionId=...)` в зависимости от роли вызывающего!
  - CRUD вложений дополнений (**20 методов** `addOnAttachments` — по 5 методов `create`, `get`, `list`, `patch`, `delete` для каждого из 4 ресурсов `courseWork`, `announcements`, `courseWorkMaterials` и `posts`):
    - Инвариант: на одно задание `courseWork` допускается **не более 1 вложения с `gradeSyncEnabled=True`** (Activity-type add-on с возвратом оценки); остальные вложения — Content-type.
    - Поддержка `copyHistory` при копировании курса или `Reuse Post`.
  - Синхронизация сдачи и оценок из внешнего тренажёра (**5 методов** `addOnAttachments.studentSubmissions`: `get`, `list`, `patch` для `courseWork` + `get`, `patch` для `posts`; `4 + 20 + 5 = 29` канонических методов Add-ons из `classroom_v1.json`!):
    - `GET` и `PATCH /v1/courses/{courseId}/courseWork/{itemId}/addOnAttachments/{attachmentId}/studentSubmissions/{submissionId}`: при передаче `pointsEarned` и `gradeSyncEnabled == 1` автоматически пересчитывает масштаб `(pointsEarned / addon.max_points) * coursework.max_points` и записывает оценку в `submissions.draft_grade` с записью в `submission_history`!
  - Выдача короткоживущего подписанного `addOnToken` для 4 режимов iframe (`Attachment Discovery`, `Teacher View`, `Student View`, `Student Work Review`) + мост `POST /api/lti/launch` (локальный адаптер LTI 1.3 Deep Linking & Grade Passback, совместимый с существующим `pb-passport-bridge.js`).
- [x] **9.2. Реактивные подписки `registrations` и Webhook-диспетчер (`app/v1/router_registrations.py` — 2 метода `classroom_v1.json`):**
  - `POST /v1/registrations` (`create`): поддерживает все 3 типа `feedType`:
    1. `DOMAIN_ROSTER_CHANGES` (доступен только `ADMIN`),
    2. `COURSE_ROSTER_CHANGES` (изменения учителей и учеников конкретного `courseId`),
    3. `COURSE_WORK_CHANGES` (создание/изменение заданий, материалов, сдач и оценок в `courseId`).
    - Срок жизни подписки `expiryTime = now + 7 суток` (продление повторным `POST` до истечения TTL).
  - `DELETE /v1/registrations/{registrationId}` (`delete`).
  - Функция `emit_classroom_feed_event(conn, feed_type, class_id, resource_payload)`: ставит задачу доставки с подписью `X-BormoClass-Signature: sha256=<hmac>` в `webhook_deliveries` и мгновенно транслирует событие в браузерный `sse_hub`.
- [x] **9.3. Сквозные экраны (`To-review`, `To-do`, Календарь `.ics`, Видеовстречи), Центр уведомлений и Админ-консоль (`app/classroom/router_global.py` + `app/classroom/router_notifications_admin.py`):**
  - В `app/classroom/router_global.py`:
    - `GET /api/classroom/global/to-review`: две вкладки учителя **«На проверку» (`work_to_review`)** и **«Проверено» (`reviewed`)**, фильтр по курсу, счётчики `Turned in / Assigned / Graded` и кнопка `POST /api/classroom/coursework/{cw_id}/mark-reviewed`.
    - `GET /api/classroom/global/todo`: три вкладки ученика **«Назначено» (`assigned`)**, **«Пропущено» (`missing`)**, **«Выполнено» (`done`)** с группировкой по корзинам `Без срока`, `На этой неделе`, `На следующей неделе`, `Позже`.
    - `GET /api/classroom/calendar/events` (сетка недели/месяца по всем курсам) и `GET /api/classroom/calendar/{calendar_token}.ics` (бескукисный экспорт дедлайнов в стандарт **RFC 5545 iCalendar** `BEGIN:VCALENDAR ... BEGIN:VEVENT` для подписки из любого внешнего календаря).
    - `POST /api/classroom/classes/{class_id}/video-room`: генерация ссылки на самодостаточную комнату Jitsi / BigBlueButton / LiveKit (`video_room_url`) с переключателем видимости для учеников.
  - В `app/classroom/router_notifications_admin.py`:
    - Колокольчик уведомлений: `GET /api/classroom/notifications`, `POST /api/classroom/notifications/read-all`, `GET/PATCH /api/classroom/notification-prefs` (глобальный рубильник, матрица типов событий и индивидуальное отключение уведомлений по отдельным курсам `muted_classes_json`!).
    - **Доменная Админ-консоль (`/api/classroom/admin/*`, только `ADMIN`):**
      - CRUD подразделений школы `org_units` (параллели, кафедры, учебные годы),
      - Управление пользователями: выдача статуса `verified_teacher`, блокировка `account_disabled`, принудительное добавление учителя/ученика в любой курс и смена владельца осиротевшего курса,
      - **Пакетный импорт расписания и классов `OneRoster CSV`** (`POST /api/classroom/admin/import-oneroster` — создаёт курсы в статусе `PROVISIONED` и предзаполняет ростер к началу учебного года!),
      - Просмотр журнала аудита `GET /api/classroom/admin/audit-logs`,
      - **Суверенность данных и архивный вынос (`Data Takeout` + `IMS Common Cartridge`)**: `GET /api/classroom/takeout.zip` (выгружает полный ZIP-архив курсов, структуры тем, заданий, рубрик, работ и манифест `imsmanifest.xml` формата `.imscc`).
- [x] **Gate Check `[P9]`:** выполнить `.venv/bin/pytest -q`.


---

## ПАКЕТ 10: Фронтенд ES-модули (Часть 1) — Навигатор, Витрина, Лента, Конструктор Заданий/Квизов, Люди и Подгруппы

### Файлы пакета `[P10]`
- **Создать:** `app/static/css/classroom-ext.css`, `app/static/js/modules/api-v1.js`, `app/static/js/modules/home-and-drawer.js`, `app/static/js/modules/stream-and-comments.js`, `app/static/js/modules/classwork-and-quizzes.js`, `app/static/js/modules/people-groups-guardians.js`
- **Инвариант `app/static/`:** `0` внешних CDN, `0` вхождений подстрок `googleapis.com` и `gstatic.com` (даже в комментариях!).

### Задачи пакета `[P10]`
- [x] **10.1. Транспортный клиент и реактивная шина (`app/static/js/modules/api-v1.js`):**
  - Обёртка `v1Fetch(path, options)` с автоматической сборкой `updateMask`, обработкой Google Error JSON (`error.message` / `error.details`), хелпером автопагинации `fetchAllPages(path, listKey)` по `nextPageToken` и подпиской на `EventSource` SSE-поток курса.
- [x] **10.2. Главный экран курсов и выдвижной Гамбургер-навигатор (`app/static/js/modules/home-and-drawer.js`):**
  - Боковое меню (`Drawer`): *Курсы (Home)*, *Календарь*, секция *Преподаю* (`На проверку / To review` + список активных курсов), секция *Учусь* (`Список дел / To-do` + список курсов), *Архив курсов (`Archived classes`)*, *Админ-консоль* (для `admin`), *Настройки уведомлений*.
  - Витрина карточек курсов: цветная шапка (`theme_color` + локальный SVG-паттерн `banner_preset`), геометрический SVG-аватар владельца, **до 2 ближайших дедлайнов прямо на карточке курса**, быстрые кнопки перехода в Журнал и Папку работ, Drag-and-Drop сортировка карточек.
  - Специальные состояния карточек на витрине: для курсов `PROVISIONED` — плашка *«Администратор подготовил курс»* с кнопками **[Принять]** / **[Отклонить]**; для входящих `Invitation` — кнопки **[Принять приглашение]** / **[Отклонить]**; кнопка **[+]** в шапке (*Присоединиться по `enrollmentCode` или 5-значному ПИН парты* / *Создать курс*).
- [x] **10.3. Вкладка «Лента» (`Stream`) и 3-уровневые комментарии (`app/static/js/modules/stream-and-comments.js`):**
  - Баннер курса: полноэкранное модальное окно демонстрации `enrollmentCode` и локального SVG QR-кода для проектора в классе, кнопка видеовстречи (Jitsi / BBB / LiveKit), панель постоянных материалов **«О курсе» (`CourseMaterialSet`)** и шестерёнка настроек курса.
  - Левый виджет **«Предстоящие задания»** (сводка дедлайнов на 7 дней + переход в `To-do`).
  - Редактор объявлений: мультивыбор целевых курсов (кросс-постинг), селектор получателей (`Все ученики` / `Выбранные ученики` / `Учебные подгруппы`), панель вложений (Файл с диска, Ссылка с превью, Новая Excalidraw-доска, Запись голосового/видеообращения через `MediaRecorder`), сплит-кнопка **[Опубликовать | Запланировать (`scheduledTime`) | Сохранить черновик]**, модальное окно **«Использовать повторно» (`Reuse post`)** с поиском по всем активным и архивным курсам.
  - Закрепление постов (`Pin / Move to top`), тумблер учителя *«Показывать удалённые записи»*, разворачиваемая ветка публичных комментариев `Class Comments` с автодополнением `@handle`.
- [x] **10.4. Вкладка «Задания» (`Classwork`), Квизы, Практикумы и Стандарты (`app/static/js/modules/classwork-and-quizzes.js`):**
  - Меню **[+ Создать]**: *Задание (`Assignment`)*, *Задание с тестом (`Quiz assignment`)*, *Интерактивный практикум (`Practice set`)*, *Вопрос (`Short answer` / `Multiple choice`)*, *Материал (`Material`)*, *Использовать повторно (`Reuse post`)*, *Тема (`Topic`)*.
  - Боковой фильтр по темам + Drag-and-Drop перетаскивание тем и карточек внутри тем.
  - Полный конструктор задания: баллы (`maxPoints` или *«Без оценки»*), дата/время сдачи + чекбокс *«Запретить сдачу после срока» (`close_after_due`)*, выбор темы, категории оценки (`GradeCategory`), учебного периода (`GradingPeriod`), переключатель режима каждого файла/доски (`Просмотр` / `Редактирование` / **`Копия для каждого ученика`**), визуальный конструктор/импорт **Рубрики**, тумблер **Проверки на уникальность (`Originality`)**, пикер **Образовательных стандартов (`CASE / ФГОС`)** и подключение **Add-ons** в iframe.
  - Встроенный редактор и плеер **Quiz Assignment** (все 7 типов вопросов, таймер обратного отсчёта, индикатор потери фокуса вкладки, мгновенный автоподсчёт) и плеер **Practice Sets** (пошаговая проверка карточки, лампочка прогрессивных подсказок, холст черновика решения и тепловая карта ошибок для учителя).
- [x] **10.5. Вкладка «Пользователи» (`People`), Парты, Подгруппы и Опекуны (`app/static/js/modules/people-groups-guardians.js`):**
  - Блок *Преподаватели* (бейдж владельца, приглашение со-учителя, передача владения курсом).
  - Блок *Учащиеся*: чекбоксы массовых действий (`Отчислить`, `Заглушить в ленте / Mute`, `Разрешить писать`), сохранение фирменного переключателя **«Схема 30 парт класса»**, клик по ученику открывает индивидуальную карточку успеваемости (`All / Turned in / Assigned / Returned / Missing`).
  - Вкладка/панель **«Учебные подгруппы» (`studentGroups`)** (создание групп для дифференцированного обучения и быстрое распределение учеников) и панель **«Опекуны» (`guardians`)** (генерация Zero-PII кода привязки родителя и просмотр родительской сводки).
- [x] **Gate Check `[P10]`:** выполнить `.venv/bin/pytest -q` (особенно проверить `test_no_external_cdn_links_in_static` — строго `0` внешних доменов и `0` строк `googleapis.com` в `app/static/`!).

---

## ПАКЕТ 11: Фронтенд ES-модули (Часть 2) — `SpeedGrader`, Журнал оценок, `To-review`/`To-do`/Календарь, Админка и PWA Сканер PDF

### Файлы пакета `[P11]`
- **Создать:** `app/static/js/modules/speedgrader.js`, `app/static/js/modules/gradebook-periods.js`, `app/static/js/modules/global-calendar-admin.js`, `app/static/js/modules/pdf-scanner.js`, `app/static/manifest.webmanifest`, `app/static/sw.js`
- **Изменить:** `app/static/index.html`, `app/static/js/bormoclass-app.js`, `app/static/css/classroom-ext.css`

### Задачи пакета `[P11]`
- [x] **11.1. Двухпанельное рабочее место проверки работ `SpeedGrader` (`app/static/js/modules/speedgrader.js`):**
  - Верхняя панель: выпадающий переключатель учеников со стрелками `< Пред. | След. >`, фильтрацией (`Все / Сдано / Оценено / Пропущено`), бейджем статуса (`TURNED_IN`, `Сдано с опозданием`, `RETURNED`) и сплит-кнопкой **[Вернуть работу | Вернуть несколько работ]**.
  - Левая панель предпросмотра (`70%` ширины) без скачивания на диск:
    - Просмотрщик PDF и фото тетрадей с зумом + **инструмент «Красная ручка» и рамочные комментарии по координатам страницы** (`file_annotations`),
    - Просмотрщик кода и текста с подсветкой, живой холст персональной доски ученика `.excalidraw`, детальный разбор ответов `Quiz` / `Practice Set` и выдвижная шторка **Отчёта об уникальности** с подсветкой совпавших фрагментов (`match_percent`).
  - Правая инспекторская панель (`30%` ширины):
    - Ввод `draftGrade` (`X / maxPoints`) и тумблер **«Освобождён (`Excused`)»**,
    - Интерактивная **сетка Рубрики** (клик по ячейке уровня подсвечивает уровень и мгновенно пересчитывает `draftGrade`),
    - **Банк комментариев** с мгновенной вставкой по `#хештегу`,
    - Живой чат **Приватных комментариев** (`1-на-1`) и модальное окно **Истории сдачи и оценок (`SubmissionHistory`)**.
- [x] **11.2. Интерактивный Журнал оценок (`Grades`) и Периоды (`app/static/js/modules/gradebook-periods.js`):**
  - Фиксированная 2D-таблица (`sticky` колонка учеников + `sticky` строка **«Средний балл класса»** + `sticky` заголовки заданий с категорией, периодом и максимумом баллов).
  - Селектор учебных периодов (`Все периоды` / `1–4 четверть`), быстрый ввод черновых оценок прямо в ячейке с навигацией клавишами `Enter` / `ArrowDown` / `ArrowUp` и контекстным меню ячейки (`Вернуть`, `Освободить / Excused`, `Открыть работу`).
  - Колонка итогового балла (`TOTAL_POINTS` / `WEIGHTED_CATEGORIES`), панель российских метрик (**Усп%**, **КЗ%**, **СОУ%**), вкладка **Матрица освоения стандартов** и клиентский **Zero-PII CSV-экспорт** (с поддержкой существующего локального `WebCrypto AES-GCM` справочника ФИО в браузере учителя без отправки персональных данных на сервер).
- [x] **11.3. Сквозные разделы `To-review`, `To-do`, Календарь `.ics`, Уведомления и Админ-консоль (`app/static/js/modules/global-calendar-admin.js`):**
  - Экран учителя **«На проверку»** (вкладки `На проверку` и `Проверено`, фильтр по курсу, счётчики `Сдано / Назначено / Оценено`).
  - Экран ученика **«Список дел»** (вкладки `Назначено`, `Пропущено`, `Выполнено` с недельными корзинами).
  - Сетка **Календаря** (неделя / месяц) с цветовыми чипами курсов + кнопки **[Скопировать WebCal `.ics` ссылку]** и **[Скачать `.ics`]**.
  - Колокольчик **Центра уведомлений** в шапке с бейджем непрочитанных и матрицей отключения уведомлений по отдельным курсам.
  - Экран **Доменной Админ-консоли**: дерево `org_units`, верификация учителей (`verified_teacher`), Drag-and-Drop импорт расписания `OneRoster CSV`, просмотр `audit_logs` и выгрузка полного архива `Takeout (.zip / .imscc)`.
- [x] **11.4. Браузерный сканер тетрадей в PDF, PWA-офлайн, WCAG 2.1 AA и `ru`/`en` локализация (`app/static/js/modules/pdf-scanner.js`, `manifest.webmanifest`, `sw.js`, `index.html`, `bormoclass-app.js`):**
  - В карточке сдачи ученика (`Ваша работа`) добавить кнопку **«Сканировать тетрадь в PDF»**: захват с камеры `getUserMedia`, кадрирование листа на `Canvas` с повышением контрастности текста и чистая JS-сборка многостраничного файла `%PDF-1.4` из JPEG-страниц без единой внешней библиотеки с прямой прикрепкой в `StudentSubmission`!
  - Настроить `manifest.webmanifest` и `sw.js` (кеширование статики и открытых учебных материалов для офлайн-чтения + очередь офлайн-черновиков в `IndexedDB`).
  - Подключить новые ES-модули и `classroom-ext.css` в `app/static/index.html` и `app/static/js/bormoclass-app.js`, обеспечить полную клавиатурную доступность **WCAG 2.1 AA** (`aria-label`, `focus-visible`, `Escape` в модалках), светлую/тёмную тему и переключатель языка интерфейса `RU / EN`.
- [x] **Gate Check `[P11]`:** выполнить `.venv/bin/pytest -q` (проверить `0` регрессий и прохождение всех инвариантов `app/static/`).

---

## ПАКЕТ 12: Контрактные автотесты `classroom_v1.json` (105 методов / 85 схем), RBAC, Автоматы и Финальная приёмка

### Файлы пакета `[P12]`
- **Создать:** `tests/test_v1_discovery_contract.py`, `tests/test_v1_lifecycles_and_grades.py`, `tests/test_v1_rbac_addons_and_features.py`

### Задачи пакета `[P12]`
- [x] **12.1. Автоматический контрактный тест против эталона Google Discovery (`tests/test_v1_discovery_contract.py`):**
  - Читает `docs/google_classroom/discovery/classroom_v1.json` напрямую в `pytest`:
    1. Рекурсивно собирает все **24 ресурса** и все **105 HTTP-методов** (`httpMethod` + `flatPath`/`path`) и проверяет, что каждый из 105 маршрутов зарегистрирован в `app.routes` с точным совпадением HTTP-глагола!
    2. Проверяет наличие и валидность всех **85 схем** `discovery["schemas"]` в `app/v1/schemas.py`.
    3. Проверяет протокольные механизмы `/v1`: `updateMask` (отклонение неизвестного поля с `400 INVALID_ARGUMENT`), селектор `fields=...`, подписанный `pageToken` (`nextPageToken`) и резолвинг `"me"`, `"-"`, `d:<alias>`, `p:<alias>`.
- [x] **12.2. Сквозной тест жизненных циклов, ACL файлов/досок и оценивания (`tests/test_v1_lifecycles_and_grades.py`):**
  - Автомат `Course`: `PROVISIONED -> ACTIVE -> ARCHIVED -> ACTIVE -> SUSPENDED`, ошибка `CourseTitleCannotContainUrl`, ошибка `CourseNotModifiable` в архиве, полное клонирование `Copy Course` со сбросом заданий в `DRAFT`.
  - Автомат `StudentSubmission` + `STUDENT_COPY` + `ACL`: публикация задания с шаблоном доски `.excalidraw` в режиме `STUDENT_COPY` -> автоматическое создание независимой копии у ученика -> `turnIn` блокирует запись ученика (`403`) -> учитель рисует `file_annotations` и ставит `draftGrade` (проверка, что ученик **не видит** `draftGrade`!) -> `reclaim` возвращает `EDIT` ученику -> повторный `turnIn` -> `return` публикует `assignedGrade`, фиксирует `StateHistory` + `GradeHistory` (`MAX_POINTS_CHANGE`) и корректно считает `late`.
  - Рубрики и Журнал: создание оцениваемой рубрики, блокировка её структуры после начала проверки, расчёт `TOTAL_POINTS` и `WEIGHTED_CATEGORIES` (`weight_micros = 1_000_000`), нормировка пустых категорий, статус `Excused`, валидация непересекающихся `GradingPeriods` с `applyToExistingCoursework=True` и расчёт `СОУ`.
- [x] **12.3. Сквозной тест 5 ролей, 24 OAuth-скоупов, Add-ons, Квизов и Антиплагиата (`tests/test_v1_rbac_addons_and_features.py`):**
  - Проверка OAuth2 Bearer-токенов: отказ `403 ACCESS_TOKEN_SCOPE_INSUFFICIENT` при нехватке скоупа и отказ `403 ProjectPermissionDenied` при попытке стороннего `client_id` изменить чужое задание.
  - Проверка `invitations:accept` (включая передачу владения `OWNER`), `CannotDeleteCourseOwner`, `studentGroups`, Zero-PII привязки родителя `guardians` и изолированной сводки `build_guardian_digest`.
  - Проверка фонового планировщика `scheduledTime` (автопубликация отложенного объявления и задания), всех операций `AddOnAttachments` с автосинхронизацией баллов `gradeSyncEnabled -> draftGrade`, `registrations` с HMAC-подписью вебхука, автопроверки `Quiz Assignment`, лимита `3` самопроверок ученика в `Originality Reports`, экспорта валидного `RFC 5545 .ics`, импорта `OneRoster CSV` и выгрузки `Takeout .zip`.

### Контрольная матрица 100% покрытия Google Classroom API v1 (24 ресурса / 105 методов)
- [x] `registrations` (**2**: `create`, `delete`)
- [x] `userProfiles` (**1**: `get`)
- [x] `userProfiles.guardians` (**3**: `get`, `list`, `delete`)
- [x] `userProfiles.guardianInvitations` (**4**: `create`, `get`, `list`, `patch`)
- [x] `invitations` (**5**: `create`, `get`, `list`, `delete`, `accept`)
- [x] `courses` (**8**: `create`, `get`, `list`, `update`, `patch`, `delete`, `getGradingPeriodSettings`, `updateGradingPeriodSettings`)
- [x] `courses.aliases` (**3**: `create`, `list`, `delete`)
- [x] `courses.teachers` (**4**: `create`, `get`, `list`, `delete`)
- [x] `courses.students` (**4**: `create`, `get`, `list`, `delete`)
- [x] `courses.studentGroups` (**4**: `create`, `list`, `patch`, `delete`)
- [x] `courses.studentGroups.studentGroupMembers` (**3**: `create`, `list`, `delete`)
- [x] `courses.topics` (**5**: `create`, `get`, `list`, `patch`, `delete`)
- [x] `courses.announcements` (**7**: `create`, `get`, `list`, `patch`, `delete`, `modifyAssignees`, `getAddOnContext`)
- [x] `courses.announcements.addOnAttachments` (**5**: `create`, `get`, `list`, `patch`, `delete`)
- [x] `courses.courseWorkMaterials` (**6**: `create`, `get`, `list`, `patch`, `delete`, `getAddOnContext`)
- [x] `courses.courseWorkMaterials.addOnAttachments` (**5**: `create`, `get`, `list`, `patch`, `delete`)
- [x] `courses.courseWork` (**8**: `create`, `get`, `list`, `patch`, `delete`, `modifyAssignees`, `updateRubric`, `getAddOnContext`)
- [x] `courses.courseWork.rubrics` (**5**: `create`, `get`, `list`, `patch`, `delete`)
- [x] `courses.courseWork.studentSubmissions` (**7**: `get`, `list`, `patch`, `modifyAttachments`, `turnIn`, `reclaim`, `return`)
- [x] `courses.courseWork.addOnAttachments` (**5**: `create`, `get`, `list`, `patch`, `delete`)
- [x] `courses.courseWork.addOnAttachments.studentSubmissions` (**3**: `get`, `list`, `patch`)
- [x] `courses.posts` (**1**: `getAddOnContext`)
- [x] `courses.posts.addOnAttachments` (**5**: `create`, `get`, `list`, `patch`, `delete`)
- [x] `courses.posts.addOnAttachments.studentSubmissions` (**2**: `get`, `patch`)
- **ИТОГО:** **24 ресурса / 105 HTTP-методов / 85 схем / 24 OAuth-скоупа = 100% паритет.**

### Финальный Gate Check (Definition of Done всего проекта)
- [x] Запустить `.venv/bin/pytest -v` — **100% тестов зелёные**, включая все 4 исходных сторожевых набора (`test_zero_pii_invariants.py`, `test_passport_flow.py`, `test_classroom_and_sou.py`, `test_error_messages.py`) и все 3 новых набора `test_v1_*.py`.
