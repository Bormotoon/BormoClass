# Результаты аудита и исправления архитектуры безопасности BormoClass
**Статус**: ВСЕ ИСПРАВЛЕНИЯ ВНЕДРЕНЫ (100% АВТОНОМНОСТЬ & ZERO-PII / 152-ФЗ РФ)
**Дата верификации**: 2026-11-07
**Результаты автотестов**: 29 passed (100% success rate)

---

### Сводная таблица найденных утечек и принятых мер

| Файл в репозитории | Что обнаружено в коде | Тип угрозы | Статус исправления |
| --- | --- | --- | --- |
| `app/classroom/router_global.py` | Ссылки на `meet.jit.si`, `livekit.io`, `bigbluebutton.org` | Утечка IP и медиа наружу | **ИСПРАВЛЕНО**: Эндпоинт `video-room` и `VideoRoomRequest` удалены. Поля `video_room_url` и `video_visible_to_students` удалены из схемы БД и роутеров. |
| `app/classroom/router_notifications_admin.py` | Импорт `username` из CSV и схемы `imsglobal.org` | Запись ФИО/почты в БД | **ИСПРАВЛЕНО**: Запрещен импорт handle из CSV — всегда вызывается `create_unique_callsign(conn)`. Схемы `imsmanifest.xml` удалены, оставлен чистый локальный JSON-бэкап. |
| `app/v1/router_guardians.py` | Подсистема опекунов и приглашений родителей | Сбор контактов родителей | **ИСПРАВЛЕНО**: Файл `router_guardians.py` удален. Поле `guardians_enabled` и таблицы опекунов ликвидированы. UI опекунов удален. |
| `app/static/js/modules/pdf-scanner.js` | Съёмка тетрадей с камеры и загрузка файлов с `f.name` | Фото обложек с ФИО на сервере | **ИСПРАВЛЕНО**: Модуль сканера удален. На сервере в `router_files.py` и `engine.py` файлы всегда переименовываются в `Вложение #{sha256[:8]}.{ext}`. |
| `app/classroom/router_comments.py` | Свободный ввод текста до 2000 знаков от учеников | Ввод детьми своих ФИО и телефонов | **ИСПРАВЛЕНО**: Ученикам запрещен свободный ввод текста, разрешен только выбор из белого списка `ALLOWED_STUDENT_MESSAGES`. Для учителей текст валидируется через `assert_zero_pii_text()`. |
| `app/v1/router_addons.py`, `router_registrations.py` | Внешние iframe-аддоны и webhook-регистрации | Утечка данных сторонним сервисам | **ИСПРАВЛЕНО**: Файлы и эндпоинты удалены. Кнопка `🧩 Add-on` вырезана из интерфейса. |
| `app/static/js/modules/api-v1.js` | Класс `GoogleAPIError` | Наследие Google API | **ИСПРАВЛЕНО**: Переименован в `BormoAPIError`. |
| `app/classroom/router_board.py`, `app/storage/` | Проприетарный ключ `driveFile` | Наследие Google Drive | **ИСПРАВЛЕНО**: Заменен на внутренний `localFile`. |
| `app/static/js/modules/classwork-and-quizzes.js` | Произвольные внешние ссылки в кнопке `cwAddLinkBtn` | Утечка Referer и IP учеников | **ИСПРАВЛЕНО**: Разрешены только относительные внутренние URL, начинающиеся с `/`. |
| CSP Headers | Отсутствие строгой политики Content-Security-Policy | Риск загрузки внешних скриптов/стилей | **ИСПРАВЛЕНО**: В `app/main.py` (middleware) и `edge/Caddyfile` добавлен строгий заголовок CSP (`connect-src 'self'`, `default-src 'self'`). |

---

### Контур 1. Полная автономность (Zero-Google & Air-Gap) — ВЫПОЛНЕНО

1. **Ликвидация внешних видеокомнат:**
   - Эндпоинт `configure_video_room` и класс `VideoRoomRequest` удалены из `router_global.py`.
   - Поля `video_room_url` и `video_visible_to_students` удалены из `schema.sql`, `db.py`, `router_classes.py`.
   - Кнопка видеовстречи удалена из `stream-and-comments.js`.
2. **Удаление внешних интеграций Google Classroom API v1:**
   - Файлы `app/v1/router_registrations.py`, `app/v1/router_addons.py`, `app/v1/router_guardians.py` удалены.
   - Импорты и роутеры отключены в `app/v1/__init__.py`.
   - В `app/static/js/modules/api-v1.js` класс переименован в `BormoAPIError`.
   - Проприетарные ключи `driveFile` заменены на `localFile` в `router_board.py`, `engine.py`, `router_files.py`, `classwork-and-quizzes.js`, `stream-and-comments.js`.
   - В `app/v1/rbac.py` все константы скоупов переведены на автономные префиксы `bormoclass:...` без упоминания `google` или `https://`.
3. **Очистка скриптов и манифестов от внешних доменов:**
   - Скрипт `scripts/download_classroom_docs.py` удален.
   - В `router_notifications_admin.py` выгрузка `takeout.zip` формирует чистый локальный JSON-архив без `imsmanifest.xml` и внешних пространств имен `imsglobal.org` / `ltsc.ieee.org`.
   - В конструкторе заданий (`classwork-and-quizzes.js`) и ленте (`stream-and-comments.js`) разрешены только внутренние пути, начинающиеся с `/`.
4. **Принудительная сетевая изоляция через CSP:**
   - Во все ответы сервера в `app/main.py` и `edge/Caddyfile` добавлен заголовок:
     `Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'self'; base-uri 'self'; form-action 'self';`

---

### Контур 2. Абсолютный Zero-PII (0 байт персональных данных) — ВЫПОЛНЕНО

1. **Модуль санитайзера `app/passport/pii_guard.py`:**
   - Реализована функция `assert_zero_pii_text(text: str) -> None`.
   - Блокирует (`HTTP 422`):
     - Email-адреса;
     - Российские телефонные номера (+7 / 8...);
     - Номера СНИЛС;
     - Паттерны ФИО («Фамилия И.О.», «И.О. Фамилия» и трехсловные русские имена с отчествами на `-ович/-евич/-овна/-евна/-ич/-ична`).
2. **Запрет импорта пользовательских логинов в OneRoster:**
   - В `router_notifications_admin.py` функция `import_oneroster` всегда генерирует анонимный позывной через `create_unique_callsign(conn)`.
   - Текст CSV прогоняется через `assert_zero_pii_text()`.
3. **Ликвидация контура опекунов:**
   - Удалены роутер `router_guardians.py`, поля `guardians_enabled`, таблицы `guardians` и `guardian_invitations`.
   - Удален родительский интерфейс из `people-groups-guardians.js`.
4. **Удаление веб-сканера тетрадей и принудительное обезличивание имен файлов:**
   - Удален файл `app/static/js/modules/pdf-scanner.js` и ссылка на него в `sw.js` и `bormoclass-app.js`.
   - При любой загрузке файла в `app/storage/router_files.py` и дублировании в `app/storage/engine.py` клиентское имя файла игнорируется: файл всегда сохраняется в БД строго как `Вложение #{sha256[:8]}.{ext}`.
5. **Блокировка свободного текстового ввода для учеников:**
   - В `app/classroom/router_comments.py` ученикам (`role == "student"`) запрещен свободный ввод текста в публичных и приватных комментариях — разрешен только выбор из белого списка `ALLOWED_STUDENT_MESSAGES`.
   - Для учителей любой вводимый текст проверяется через `assert_zero_pii_text()`.
   - Удален эндпоинт `GET /coursework/{cw_id}/peer-answers` и колонка `short_answer_text`.
   - В `app/classroom/router_quizzes_and_sets.py` тип вопроса `PARAGRAPH` удален. Ответы `SHORT_TEXT` ограничены 64 символами и проверяются через `assert_zero_pii_text()`.
6. **Строгая валидация позывных при входе:**
   - В `app/passport/router.py` схемы `LoginRequest` и `RecoverRequest` валидируют поле `handle` по регулярному выражению `^[А-ЯЁа-яё]+-[А-ЯЁа-яё]+-\d{3,4}$`.

---

### Верификация автотестами
- `tests/test_zero_pii_invariants.py`:
  - `test_sqlite_schema_has_zero_pii_columns` — PASSED
  - `test_static_files_have_zero_external_cdns` — PASSED
  - `test_zero_external_links_in_app` — PASSED (сканирование исходников `app/` на отсутствие `http://` и `https://`, кроме `http://www.w3.org/2000/svg`)
  - `test_zero_pii_guards_and_filename_hashing` — PASSED (проверка блокировки ФИО/телефона/email кодом 422 в заданиях, комментариях и CSV, а также хэширования имени файла `Иванов_Иван_8А.pdf` -> `Вложение #...`)
- Общий прогон `pytest`: 29 passed.
