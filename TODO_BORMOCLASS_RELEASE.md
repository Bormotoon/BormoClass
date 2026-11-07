# Мастер-план предрелизной доводки BormoClass (Todo для Gemini 3.8 Flash)

> **Профиль исполнения для AI-агента (Gemini 3.8 Flash):**
> - **Режим работы:** детерминированное пакетное исполнение (Пакеты 1–6 по очереди), `Zero Tool-Thrashing` (читай целевые файлы пакета целиком, вноси все правки за один проход, затем запускай проверочную команду пакета).
> - **Железные инварианты проекта:**
>   1. **100% Zero-PII (152-ФЗ РФ):** 0 байт персональных данных (ФИО, email, телефоны, СНИЛС, IP-адреса, оригинальные имена файлов) в SQLite, логах и куках.
>   2. **100% Автономность (Zero External CDN):** никаких внешних скриптов, шрифтов или сетевых вызовов наружу; строгий CSP `default-src 'self'`.
>   3. **Синхронные обработчики БД:** все роуты FastAPI, вызывающие `with db_session() as conn:`, объявляются строго через `def` (не `async def`), чтобы не блокировать event loop и `sse_hub`.

---

## Сводная матрица дефектов и улучшений

| Пакет | Категория | Затронутые файлы | Суть исправления / улучшения |
| :--- | :--- | :--- | :--- |
| **Пакет 1** | Критические `500` / `NameError` / `AttributeError` | `router_submissions.py`, `router_coursework.py`, `router_quizzes_and_sets.py`, `storage/engine.py`, `router_notifications_admin.py`, `router_classes.py` | Починка сломанного `return` в `delete_comment`, инициализация `new_file_id` в `ensure_student_copy`, замена `.get()` у `sqlite3.Row`, исправление колонок `joined_at` |
| **Пакет 2** | Рассинхрон контрактов Frontend ↔ Backend | `router_quizzes_and_sets.py`, `classwork-and-quizzes.js`, `speedgrader.js`, `gradebook-periods.js`, `global-calendar-admin.js`, `stream-and-comments.js` | Префикс `/api/classroom` для квизов/практикумов, синхронизация полей сдачи квизов, динамический плеер практикумов, исправление формата уведомлений и метрик СОУ |
| **Пакет 3** | Архитектура E2EE (`BORMO_E2EE_V1`) vs Сервер | `e2ee-crypto.js`, `pii_guard.py`, `router_quizzes_and_sets.py`, `router_comments.py`, `router_global.py` | Детерминированный обмен ключами класса, клиентские хэши антиплагиата (`fingerprints`), фильтрация банка комментариев на клиенте, передача `mentioned_handles`, чистый `.ics` |
| **Пакет 4** | Безопасность, RBAC, IDOR и Паспорт | `router_board.py`, `router_comments.py`, `router_submissions.py`, `router_classes.py`, `router_coursework.py`, `router_notifications_admin.py`, `passport/router.py` | Авторизация SSE, изоляция `private_comments`, закрытие чужих оценок в матрице, защита `takeout.zip`, проверка словаря позывных, `check_ticket` и `HttpOnly` кука |
| **Пакет 5** | Интеграция UI-модулей и защита от DOM XSS | `bormoclass-app.js`, `classwork-and-quizzes.js`, `home-and-drawer.js`, `people-groups-guardians.js`, `stream-and-comments.js` | Подключение `SpeedGrader`, `GradebookPeriodsView`, `DrawerNav`, `NotificationCenter` в основной SPA-роутер, генерация печатных карточек А4 на 40 парт, `escapeHtml` |
| **Пакет 6** | Сборка доски в Docker, PWA и E2E-тесты | `Dockerfile`, `app/static/sw.js`, `app/static/board.html`, `tests/test_release_readiness.py` | Multi-stage сборка `board-src/` (Excalidraw) в `Dockerfile`, актуализация кэша Service Worker, полный набор автотестов `pytest` |

---

## ПАКЕТ 1. Устранение блокирующих серверных ошибок (`500 Internal Server Error`)

### [ ] 1.1. Исправить `NameError` при удалении комментария из банка (`app/classroom/router_submissions.py`)
* **Проблема:** В функции `delete_comment(comment_id: int, request: Request)` (строки 231–239) по ошибке вставлен `return` из метода настроек журнала (`calc_type`, `req.grade_display_setting`, `class_row`), что вызывает `NameError`.
* **Решение:** Заменить тело `delete_comment` на:
  ```python
  @router.delete("/comments/{comment_id}")
  def delete_comment(comment_id: int, request: Request):
      user = require_teacher(request)
      with db_session() as conn:
          conn.execute(
              "DELETE FROM comment_bank WHERE id = ? AND teacher_id = ?",
              (comment_id, user["user_id"])
          )
          return {"ok": True, "id": comment_id}
  ```

### [ ] 1.2. Исправить `NameError: name 'new_file_id' is not defined` в `ensure_student_copy` (`app/storage/engine.py`)
* **Проблема:** В функции `ensure_student_copy` на строке 204 в `INSERT INTO stored_files` передаётся переменная `new_file_id`, которая нигде не объявлена. При любом открытии индивидуальной доски задания (`GET /api/classroom/coursework/{id}/board`) или публикации задания с режимом `STUDENT_COPY` сервер падает с `500`.
* **Решение:** Перед `new_file_title = f"Вложение #{new_sha[:8]}.{ext}"` (строка 196) добавить генерацию идентификатора:
  ```python
  new_file_id = f"file_{secrets.token_hex(8)}"
  ```

### [ ] 1.3. Убрать вызовы `.get()` у объектов `sqlite3.Row` (`AttributeError`)
Объект `sqlite3.Row` не имеет метода `.get()`. Необходимо явно приводить строку к `dict(row)` перед вызовом `.get()`:
1. **`app/classroom/router_coursework.py` -> `reuse_coursework` (строки 205–238):**
   Сразу после проверки `if not source_cw:` добавить `source_cw = dict(source_cw)`.
2. **`app/classroom/router_quizzes_and_sets.py` -> `run_originality_check` (строки 435–455):**
   - Заменить `text_to_check = sub.get("payload_json") or ""` на `text_to_check = dict(sub).get("payload_json") or ""`.
   - В цикле `for os in other_subs:` заменить `other_text = os.get("payload_json") or ""` на `other_text = dict(os).get("payload_json") or ""`.
3. **`app/classroom/router_classes.py` -> `copy_class` (строки 400–520):**
   В начале функции определена переменная `uid = user.get("user_id") or user.get("id")`, но ниже при клонировании `coursework` (строка 481) и `course_materials` (строка 516) снова написано `user["user_id"]`. Заменить все вхождения `user["user_id"]` в `copy_class` на `uid`.

### [ ] 1.4. Исправить имена колонок `joined_at` вместо `created_at` (`app/classroom/router_notifications_admin.py`)
* **Проблема:** В `app/schema.sql` таблицы `course_teachers` и `class_members` имеют колонку `joined_at INTEGER NOT NULL` (а не `created_at`).
* **Решение:** В файле `app/classroom/router_notifications_admin.py`:
  1. В `admin_add_class_member`: заменить `INSERT INTO course_teachers (class_id, teacher_id, created_at)` на `INSERT INTO course_teachers (class_id, teacher_id, joined_at)` и `INSERT INTO class_members (class_id, student_id, seat_number, enrollment_active, created_at)` на `INSERT INTO class_members (class_id, student_id, seat_number, enrollment_active, joined_at)`.
  2. В `transfer_class_ownership`: заменить `INSERT INTO course_teachers (class_id, teacher_id, created_at)` на `INSERT INTO course_teachers (class_id, teacher_id, joined_at)`.
  3. В `import_oneroster`: заменить `created_at` на `joined_at` при вставке в `course_teachers` и `class_members`.

---

## ПАКЕТ 2. Синхронизация контрактов и маршрутов Frontend ↔ Backend

### [ ] 2.1. Добавить префикс `/api/classroom` в `app/classroom/router_quizzes_and_sets.py`
* **Проблема:** В `router_quizzes_and_sets.py` объявлен `router = APIRouter(tags=["quizzes_and_sets"])` без префикса, из-за чего эндпоинты монтируются в корень (`/quizzes/{id}`), тогда как фронтенд (`classwork-and-quizzes.js`, `router_files.py`) обращается к `/api/classroom/quizzes/{id}`.
* **Решение:** Изменить объявление роутера в `app/classroom/router_quizzes_and_sets.py` на:
  ```python
  router = APIRouter(prefix="/api/classroom", tags=["quizzes_and_sets"])
  ```

### [ ] 2.2. Исправить пути в `speedgrader.js`, `gradebook-periods.js` и `stream-and-comments.js`
1. В `app/static/js/modules/speedgrader.js`:
   - В `saveDraftGrade` заменить `/coursework/${this.courseworkId}/submissions/${this.studentId}/grade-rubric` на `/api/classroom/coursework/${this.courseworkId}/submissions/${this.studentId}/grade-rubric`.
   - В `toggleExcused` заменить `/coursework/${this.courseworkId}/submissions/${this.studentId}/excuse` на `/api/classroom/coursework/${this.courseworkId}/submissions/${this.studentId}/excuse`.
2. В `app/static/js/modules/gradebook-periods.js`:
   - В `saveExcused` заменить `/coursework/${courseworkId}/submissions/${studentId}/excuse` на `/api/classroom/coursework/${courseworkId}/submissions/${studentId}/excuse`.
   - В `updateMetricsPanel(analytics, calcType)` синхронизировать ключи с ответом бэкенда (`calculate_sou_metrics` отдаёт `usp`, `kz`, `sou`):
     ```javascript
     if (usp) usp.textContent = `${analytics.usp ?? analytics.usp_percent ?? 0}%`;
     if (kz) kz.textContent = `${analytics.kz ?? analytics.kz_percent ?? 0}%`;
     if (sou) sou.textContent = `${analytics.sou ?? analytics.sou_percent ?? 0}%`;
     ```
3. В `app/static/js/modules/stream-and-comments.js`:
   - В `loadPostComments` заменить URL удаления комментария с `/api/classroom/comments/${btn.dataset.id}` на `/api/classroom/classes/${courseId}/comments/${btn.dataset.id}`.
4. В `app/static/js/modules/global-calendar-admin.js`:
   - В `NotificationCenter.pollNotifications()` учесть, что `GET /api/classroom/notifications` возвращает объект `{ notifications: [...], unread_count: N }`:
     ```javascript
     const data = await res.json();
     this.notifications = Array.isArray(data) ? data : (data.notifications || []);
     this.unreadCount = typeof data.unread_count === "number"
       ? data.unread_count
       : this.notifications.filter((n) => !n.is_read).length;
     ```
   - В `CalendarView.render()` убрать захардкоженный `user_1.ics` и формировать ссылку из реального `user.id` (или `course.calendar_token`): `/api/classroom/calendar/user_${window.pbPassport?.getUser()?.id || 1}.ics`.

### [ ] 2.3. Синхронизировать плеер тестов (`Quiz`) и практикумов (`Practice Sets`) в `app/static/js/modules/classwork-and-quizzes.js`
1. **Сдача теста (`initQuizPlayer`):**
   - Привести имена типов вопросов к единому регистру (поддержать на бэкенде в `_score_single_question` как верхний, так и нижний регистр: `SINGLE_CHOICE` / `single_choice`, `MULTIPLE_CHOICE` / `multiple_choice`, `SHORT_TEXT` / `short_answer`, `NUMERIC_TOLERANCE` / `numeric`, `MATCHING` / `matching`, `ORDERING` / `ordering`).
   - Удалить из `renderQuestionAnswerInput` и `collectQuizAnswers` запрещённый стандартом Zero-PII тип `paragraph`.
   - В `collectQuizAnswers` собирать ключи по `String(q.id ?? idx)` и корректно сериализовать ответы для `matching` (объект `{ [left]: rightValue }`) и `ordering` (массив элементов в текущем порядке DOM).
   - При отправке `POST /api/classroom/quizzes/${quiz.id}/submit` передавать тело строго по схеме `QuizSubmitRequest`:
     ```javascript
     body: {
       answers_json: answers,
       focus_lost_count: tabSwitchViolations
     }
     ```
   - При рендере экрана результатов читать поля ответа бэкенда (`auto_score`, `max_score`):
     ```javascript
     const score = res.auto_score ?? res.score ?? 0;
     const maxScore = res.max_score ?? 0;
     const percent = maxScore > 0 ? Math.round((score / maxScore) * 100) : 100;
     ```
2. **Конструктор и плеер практикумов (`openPracticeSetCreator` и `openPracticeSetModal`):**
   - Реализовать недостающую функцию `export function openPracticeSetCreator(courseId, onReload)` — модальное окно создания практикума (`set_title`, добавление карточек `{ id, prompt, answer, hints: [] }`), отправляющее `POST /api/classroom/practice-sets`.
   - В `openPracticeSetModal(setId)` убрать хардкод про `x = 4` и `"49"`: загружать карточки через `v1Fetch(\`/api/classroom/practice-sets/${setId}\`)`, переключать карточки и проверять ответ через `POST /api/classroom/practice-sets/${setId}/check-card` с передачей `{ card_id, answer, used_hint, scratchpad_json }`.

---

## ПАКЕТ 3. Устранение конфликта E2EE (`BORMO_E2EE_V1`) с серверными функциями

### [ ] 3.1. Детерминированное управление ключами класса в `app/static/js/e2ee-crypto.js`
* **Проблема:** Сейчас `getActiveKey(classId)` при отсутствии закэшированного ключа в памяти создаёт случайный ключ `bormo_e2ee_fallback_key` в `sessionStorage`. Из-за этого учитель в новой вкладке и ученики за партами шифруют данные разными случайными ключами и видят нерасшифрованные строки `BORMO_E2EE_V1:...`.
* **Решение:**
  1. При получении списка классов (`/api/classroom/classes`), объекта класса (`/api/classroom/classes/{id}`) или входе в класс (`/api/classroom/classes/join`) автоматически выводить ключ класса из `join_pin`:
     ```javascript
     const ck = await deriveKeyFromSecret(String(cls.join_pin), "bormo-class-pin:" + String(cls.id));
     ```
     Сохранять экспортированный ключ в `localStorage.setItem("bormo_ck_" + cls.id, rawKeyB64u)` и в `localStorage.setItem("bormo_active_ck", rawKeyB64u)`.
  2. В `getActiveKey(classId)`: если `classId` передан, искать в `classKeys` -> `localStorage.getItem("bormo_ck_" + classId)`. Если URL не содержит `/classes/{id}` (например, `/api/classroom/coursework/{cw_id}`), использовать активный ключ текущего открытого класса из `localStorage.getItem("bormo_active_ck")` и перебирать все сохранённые ключи `bormo_ck_*` при дешифровании в `decryptText` и `decryptBlob`.

### [ ] 3.2. Перевод антиплагиата (`originality-check`) на Zero-Knowledge отпечатки (`app/classroom/router_quizzes_and_sets.py` и `e2ee-crypto.js`)
* **Проблема:** `payload_json` шифруется на клиенте в `BORMO_E2EE_V1:...`, поэтому серверный `_get_winnowing_fingerprints` и `ast.parse` в `run_originality_check` анализируют base64-шифротекст вместо текста работы.
* **Решение:**
  1. В `app/static/js/e2ee-crypto.js` добавить функцию `computeOriginalityFingerprints(text)` (5-граммы Winnowing по нормализованным словам -> массив 32-битных целых чисел `fingerprints`).
  2. При вызове `/turn-in` или `/originality-check` передавать массив числовых хэшей `fingerprints` (не содержащий открытого текста).
  3. В `app/classroom/router_quizzes_and_sets.py` в `run_originality_check`: если в запросе переданы `req.fingerprints` (или если `content_text` не зашифрован), сравнивать множества отпечатков по коэффициенту Жаккара / вхождения:
     $$\text{match\_percent} = \frac{|FP_1 \cap FP_2|}{\min(|FP_1|, |FP_2|)} \times 100\%$$
     и сохранять JSON-список отпечатков в `originality_reports`, чтобы сервер никогда не нуждался в расшифровке текста ученика.

### [ ] 3.3. Поиск по банку комментариев и `@handle` упоминания при включённом E2EE (`app/classroom/router_comments.py`)
1. **Банк комментариев (`search_comment_bank`):**
   - Поскольку `comment_text` хранится в БД в виде `BORMO_E2EE_V1:...`, SQL-запрос `AND comment_text LIKE ?` по шифротексту ничего не найдёт.
   - В `GET /api/classroom/comment-bank` возвращать все записи учителя (`SELECT * FROM comment_bank WHERE teacher_id = ? ORDER BY id DESC LIMIT 200`), а фильтрацию по подстроке `q` / `#хештегу` выполнять на клиенте после прозрачной расшифровки ответа перехватчиком `e2ee-crypto.js`.
2. **Упоминания `@handle` (`create_class_comment`):**
   - Добавить в `ClassCommentCreateRequest` опциональное поле `mentioned_handles: Optional[List[str]] = None`.
   - В `e2ee-crypto.js` перед шифрованием поля `body_text` извлекать регулярным выражением `/@([\w\-А-Яа-яЁё]+)/g` список позывных и подставлять их в `mentioned_handles`, чтобы сервер отправлял уведомления `MENTION` без чтения открытого текста комментария.

### [ ] 3.4. Защита экспорта `.ics` календаря от шифротекста (`app/classroom/router_global.py`)
* В `export_calendar_ics(calendar_token: str)`: проверять `r["title"]` и `r["instructions"]` через `is_e2ee_envelope()`. Если поле зашифровано (`BORMO_E2EE_V1:`), подставлять в `SUMMARY` читаемую метку `f"Задание #{r['id']} [{r['class_title']}]"`, а в `DESCRIPTION` — `"Откройте BormoClass для просмотра зашифрованной инструкции"`.

---

## ПАКЕТ 4. Безопасность, RBAC, защита от IDOR и укрепление Паспорта

### [ ] 4.1. Закрыть неавторизованный доступ к SSE и утечку `private_comments`
1. В `app/classroom/router_board.py`:
   - В `board_stream(class_id: int, request: Request)` и `classroom_stream(class_id: int, request: Request)` добавить в начале проверку пользователя и членства в классе:
     ```python
     user = require_user(request)
     with db_session() as conn:
         ctx = resolve_auth_context(request, conn)
         if not get_course_role(conn, class_id, ctx.user):
             raise HTTPException(status_code=403, detail="Нет доступа к потоку событий класса")
     ```
2. В `app/classroom/router_comments.py`:
   - В `create_private_comment` **не отправлять** полный объект личного комментария в общий поток класса! Заменить `sse_hub.notify_class(class_id, "private_comment", result)` на отправку обезличенного сигнала без текста:
     ```python
     sse_hub.notify_class(class_id, "private_comment_ping", {
         "coursework_id": cw_id,
         "student_id": student_id
     })
     ```

### [ ] 4.2. Закрыть IDOR в матрице оценок, журнале, заданиях и выгрузке архива (`takeout.zip`)
1. **`app/classroom/router_submissions.py` (`get_class_matrix`, `get_gradebook`, `get_class_analytics`):**
   - Проверять принадлежность пользователя к классу (`get_course_role(conn, class_id, user)`).
   - В `get_class_matrix` и `get_gradebook`: если пользователь не является учителем данного класса (`role == "STUDENT"`), фильтровать список `students` и словарь `submissions` строго по `student_id == user["user_id"]`, чтобы ученик видел только свои оценки.
2. **`app/classroom/router_classes.py` и `app/classroom/router_coursework.py`:**
   - В `get_board_state`, `get_class_members`, `list_material_sets`, `list_topics`, `list_coursework`, `get_coursework` проверять, что текущий пользователь — учитель этого класса, админ или активный ученик в `class_members` (иначе `HTTPException(403)`).
3. **`app/classroom/router_notifications_admin.py` (`export_takeout_zip`):**
   - Разделить маршруты: `/api/classroom/admin/takeout.zip` требует `require_admin(request)`, а `/api/classroom/takeout.zip` требует `require_teacher(request)` и передаёт `teacher_id = user["user_id"]` в `_generate_takeout_zip(conn, teacher_id=...)`, выгружая только курсы и задания этого учителя.

### [ ] 4.3. Активировать словарную валидацию позывных и талоны в `app/passport/router.py`
1. В `POST /api/passport/register`:
   - Если передан `req.handle`, после `candidate = canon_handle(req.handle)` обязательно проверять:
     ```python
     if not is_valid_dictionary_handle(candidate):
         raise HTTPException(
             status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
             detail="Позывной должен состоять из слов официального словаря Паспорта (Прилагательное-Существительное-Код)."
         )
     ```
   - Если передан `req.ticket`, проверять его через `check_ticket(settings.SECRET_KEY.encode("utf-8"), req.ticket, time.time())`.
2. В `POST /api/passport/recover`:
   - Добавить защиту от перебора через `limiter`:
     ```python
     limiter_key = f"recover:{handle}"
     if limiter.blocked(limiter_key, limit=5, window=900):
         raise HTTPException(status_code=429, detail="Слишком много попыток восстановления. Подождите 15 минут.")
     ```
     При ошибке вызывать `limiter.hit(limiter_key, 900)`, при успехе — `limiter.reset(limiter_key)`.
3. **Защита сессионной куки (`_set_auth_cookie`):**
   - Выставлять основную авторизационную куку `settings.COOKIE_NAME` (`pb_pass`) с флагом `httponly=True`, а для мгновенного чтения профиля клиентским скриптом `pb-passport.js` выставлять вторую несекретную куку `pb_pass_ui` (`httponly=False`), содержащую только публичные поля профиля без права авторизации API-запросов. В `pb-passport.js` в `readPass()` читать `pb_pass_ui || pb_pass`.

---

## ПАКЕТ 5. Интеграция продвинутых UI-модулей, Печать А4 и защита от DOM XSS

### [ ] 5.1. Защита от DOM XSS во всех фронтенд-модулях (`app/static/js/`)
* Добавить универсальную функцию экранирования `export function escapeHtml(str)` в `app/static/js/modules/api-v1.js`:
  ```javascript
  export function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }
  ```
* Обернуть в `escapeHtml(...)` все пользовательские поля (`title`, `instructions`, `description`, `handle`, `quarter_goal`, `name`, `prompt`, `body_text`) перед подстановкой в шаблонные строки `.innerHTML` в файлах:
  - `app/static/js/bormoclass-app.js`
  - `app/static/js/modules/classwork-and-quizzes.js`
  - `app/static/js/modules/home-and-drawer.js`
  - `app/static/js/modules/people-groups-guardians.js`
  - `app/static/js/modules/stream-and-comments.js`

### [ ] 5.2. Подключить готовые расширенные модули в `app/static/js/bormoclass-app.js`
Сейчас модули из `app/static/js/modules/` импортированы в `bormoclass-app.js`, но не вызываются при навигации. Необходимо:
1. В шапке `top-app-bar` (`app/static/index.html` и `bormoclass-app.js`) добавить кнопку гамбургер-меню для открытия `HomeDrawer.drawerNav.toggle()` и колокольчик уведомлений `notifBellBtn` с бейджем `notifBadge`, инициализируя `new GlobalCalendarAdmin.NotificationCenter().init()`.
2. Во вкладке `grades` (`renderGradesTab(cls)`) добавить переключатель в расширенный 2D-журнал `new GradebookPeriods.GradebookPeriodsView({ container, classId: cls.id }).render()` и кнопку быстрого запуска `SpeedGrader.openSpeedGrader({ classId: cls.id, courseworkId, studentId })` при клике по сданной работе.
3. На глобальных маршрутах `#to-review`, `#to-do`, `#calendar` и `#admin` монтировать соответствующие классы из `GlobalCalendarAdmin`: `ToReviewView`, `ToDoView`, `CalendarView` и `DomainAdminConsole` (для роли `admin`).

### [ ] 5.3. Реализовать генерацию печатного листа А4 (`generatePrintA4` в `bormoclass-app.js`)
* **Проблема:** Сейчас метод `generatePrintA4(classId)` в `bormoclass-app.js` состоит из одной строки `window.print()`, ничего не рендеря на страницу.
* **Решение:** В `generatePrintA4(classId)` загружать данные класса, список участников (`/api/classroom/classes/${classId}/members`) и заданий (`/api/classroom/classes/${classId}/coursework`), формировать скрытый в обычном режиме контейнер `#printArea` с классом `.print-page` и сеткой `.print-card-grid` (карточки для парт №1..30 с позывным ученика, пин-кодом класса, индивидуальным вариантом задания и отрывным полем ответа + отдельный лист ключей для учителя), после чего вызывать `window.print()`.

---

## ПАКЕТ 6. Multi-Stage сборка доски в Docker, PWA и тестовое покрытие

### [ ] 6.1. Multi-stage сборка Excalidraw (`board-src/`) в `Dockerfile`
* **Проблема:** В `app/static/board/index.html` и `app/static/board.html` зашиты ссылки на `./assets/index-CyasA8SH.js` и `./assets/index-D0jcgTwT.css`, которые отсутствуют в чистом Git-клоне без предварительной сборки `board-src/`.Кроме того, в `app/static/board.html` пропущен тег `<script src="/static/js/e2ee-crypto.js"></script>`.
* **Решение:**
  1. Синхронизировать `app/static/board.html` с `app/static/board/index.html` (или оставить единый `app/static/board/index.html`).
  2. Обновить `Dockerfile` до двухступенчатой сборки (Multi-stage build):
     - **Stage 1 (`node:20-alpine` AS `board-builder`):** копирует `board-src/`, выполняет `npm install`, запускает `node patches/translate-ru.mjs`, `npm run build`, `node patches/strip-cdn-fallback.mjs` и копирует шрифты `node_modules/@excalidraw/excalidraw/dist/prod/fonts` в `dist/fonts`.
     - **Stage 2 (`python:3.12-slim`):** устанавливает зависимости Python, копирует код приложения и копирует собранные ассеты из `--from=board-builder` в `/srv/bormoclass/app/static/board/`.
  3. В `docker-compose.yml` убрать перекрывающий bind-mount `./app/static:/srv/bormoclass/app/static:ro` (или монтировать статику через именованный том), чтобы собранные внутри образа файлы `/static/board/assets/` не затирались папкой хоста.

### [ ] 6.2. Обновить Service Worker (`app/static/sw.js`)
* Добавить в массив `PRECACHE_ASSETS` в `app/static/sw.js` ключевые скрипты и стили:
  - `"/static/css/classroom-ext.css"`
  - `"/static/js/e2ee-crypto.js"`
  - `"/static/js/pb-passport.js"`
  - `"/static/js/bormoclass-app.js"`
  - `"/static/js/modules/api-v1.js"`
  - `"/static/js/modules/home-and-drawer.js"`
  - `"/static/js/modules/stream-and-comments.js"`
  - `"/static/js/modules/classwork-and-quizzes.js"`
  - `"/static/js/modules/people-groups-guardians.js"`

### [ ] 6.3. Написать комплексный автотест релиза `tests/test_release_readiness.py`
Создать файл `tests/test_release_readiness.py`, проверяющий все исправленные узлы через `fastapi.testclient.TestClient`:
1. **`test_zero_pii_and_airgap_invariants`**:
   - Проверка всех таблиц SQLite на отсутствие запрещённых колонок (`email`, `phone`, `first_name`, `last_name`, `full_name`, `patronymic`, `birth_date`, `ip_address`, `encrypted_note`).
   - Сканирование всех файлов в `app/` на отсутствие внешних ссылок `http://` и `https://` (кроме стандартного пространства имён `http://www.w3.org/2000/svg`).
   - Проверка `pii_guard.py`: отправка ФИО, телефона РФ, СНИЛС или email в название задания или комментарий блокируется кодом `422`.
2. **`test_passport_dictionary_and_rate_limit`**:
   - Попытка зарегистрировать произвольный `handle="Иванов-Иван-123"` вне словаря `ADJECTIVES`/`NOUNS` отклоняется кодом `422`.
   - Регистрация валидного словарного позывного выдаёт куки `pb_pass` (`HttpOnly`) и `pb_pass_ui`.
3. **`test_comment_bank_delete_and_e2ee`**:
   - Добавление зашифрованного комментария (`e2ee_encrypt_text_helper`) в банк комментариев и его удаление через `DELETE /api/classroom/comments/{id}` возвращает `200 OK` (`{"ok": True, "id": ...}`) без `NameError`.
4. **`test_student_copy_materialization`**:
   - Создание задания с вложением `shareMode="STUDENT_COPY"` и вызов `GET /api/classroom/coursework/{id}/board` от имени ученика успешно материализует копию файла в `stored_files` без `NameError: new_file_id`.
5. **`test_quiz_and_practice_set_lifecycle`**:
   - Создание квиза по адресу `POST /api/classroom/quizzes`, прохождение учеником (`POST /api/classroom/quizzes/{id}/submit` с `answers_json` и `focus_lost_count`) и проверка автоматического импорта оценки в `submissions`.
6. **`test_rbac_idor_isolation`**:
   - Ученик А не может получить оценки ученика Б через `GET /api/classroom/classes/{id}/matrix` или `GET /api/classroom/classes/{id}/gradebook`.
   - Ученик не может скачать `GET /api/classroom/takeout.zip` (`403 Forbidden`).
   - Посторонний пользователь, не состоящий в классе, получает `403` при попытке подключиться к `/api/classroom/{id}/stream` или `/api/classroom/classes/{id}/members`.

---

## Команды финальной верификации перед публикацией на GitHub

После выполнения всех 6 пакетов агент обязан выполнить:
```bash
# 1. Проверка синтаксиса всех Python-модулей
python3 -m compileall -q app/ scripts/ tests/

# 2. Прогон полного набора тестов
pytest -v

# 3. Проверка отсутствия забытых секретов, .db и .env в git status
git status --ignored
```