import re
import time
import uuid
import secrets
from typing import Optional, List
from fastapi import APIRouter, Request, Query, Response
from pydantic import BaseModel

from app.db import db_session
from app.config import settings
from app.v1.protocol import (
    api_error,
    parse_update_mask,
    apply_fields_selector,
    encode_page_token,
    decode_page_token,
    resolve_class_id,
    resolve_user_id,
    ts_to_rfc3339
)
from app.v1.rbac import (
    resolve_auth_context,
    require_scopes,
    get_course_role,
    can_create_course,
    SCOPE_COURSES,
    SCOPE_COURSES_READONLY
)
from app.v1.schemas import (
    Course,
    CourseAlias,
    CourseMaterialSet,
    DriveFolder,
    GradebookSettings,
    GradeCategory,
    ListCoursesResponse,
    ListCourseAliasesResponse,
    Empty
)

router = APIRouter(tags=["courses"])

URL_REGEX = re.compile(r"(https?://|www\.)", re.IGNORECASE)
ENROLLMENT_ALPHABET = "abcdefghijkmnpqrstuvwxyz23456789"

def generate_enrollment_code(length: int = 7) -> str:
    return "".join(secrets.choice(ENROLLMENT_ALPHABET) for _ in range(length))

def generate_join_pin(conn) -> str:
    for _ in range(50):
        pin = str(secrets.randbelow(90000) + 10000)
        row = conn.execute("SELECT 1 FROM classes WHERE join_pin = ?", (pin,)).fetchone()
        if not row:
            return pin
    return str(secrets.randbelow(90000) + 10000)

def validate_course_state_transition(old_state: str, new_state: str, actor_role: str):
    if old_state == new_state:
        return
    valid = False
    if old_state == "PROVISIONED" and new_state == "ACTIVE":
        valid = (actor_role in ("OWNER", "ADMIN"))
    elif old_state == "PROVISIONED" and new_state == "DECLINED":
        valid = (actor_role in ("OWNER", "ADMIN"))
    elif old_state == "DECLINED" and new_state == "PROVISIONED":
        valid = (actor_role == "ADMIN")
    elif old_state == "ACTIVE" and new_state == "ARCHIVED":
        valid = (actor_role in ("OWNER", "TEACHER", "ADMIN"))
    elif old_state == "ARCHIVED" and new_state == "ACTIVE":
        valid = (actor_role in ("OWNER", "TEACHER", "ADMIN"))
    elif old_state == "ACTIVE" and new_state == "SUSPENDED":
        valid = (actor_role == "ADMIN")
    elif old_state == "SUSPENDED" and new_state == "ACTIVE":
        valid = (actor_role == "ADMIN")

    if not valid:
        api_error(400, "FAILED_PRECONDITION", f"Недопустимый переход состояния курса с '{old_state}' на '{new_state}'", reason="InvalidCourseStateTransition")

def assert_course_modifiable(course_row: dict, actor_role: str):
    state = course_row.get("course_state", "ACTIVE")
    if state in ("ARCHIVED", "DECLINED") or (state == "SUSPENDED" and actor_role != "ADMIN"):
        api_error(403, "PERMISSION_DENIED", "Курс заморожен для изменений", reason="CourseNotModifiable")

def format_course_model(row: dict, conn, ctx, role: Optional[str] = None) -> Course:
    cid = row["id"]
    if role is None:
        role = get_course_role(conn, cid, ctx.user)

    # enrollmentCode отдаётся только учителям/владельцу/админу и только если enrollment_enabled == 1
    enrollment_code = None
    if row.get("enrollment_enabled", 1) == 1 and role in ("OWNER", "TEACHER", "ADMIN"):
        enrollment_code = row.get("join_pin")

    teacher_folder = None
    if row.get("teacher_folder_id"):
        teacher_folder = DriveFolder(
            id=row["teacher_folder_id"],
            title="Teacher Folder",
            alternateLink=f"/api/storage/folders/{row['teacher_folder_id']}"
        )

    # Gradebook categories
    grade_categories = []
    cat_rows = conn.execute(
        "SELECT id, category_title, default_denominator, weight_micros FROM grade_categories WHERE class_id = ?",
        (cid,)
    ).fetchall()
    for cat in cat_rows:
        grade_categories.append(GradeCategory(
            id=str(cat["id"]),
            name=cat["category_title"],
            defaultGradeDenominator=cat["default_denominator"],
            weight=cat["weight_micros"]
        ))

    gradebook_settings = GradebookSettings(
        calculationType=row.get("grade_calc_type", "TOTAL_POINTS"),
        displaySetting=row.get("grade_display_setting", "SHOW_OVERALL_GRADE"),
        gradeCategories=grade_categories if grade_categories else None
    )

    # Material sets
    material_sets = []
    mat_rows = conn.execute(
        "SELECT set_title FROM course_material_sets WHERE class_id = ? ORDER BY sort_order ASC",
        (cid,)
    ).fetchall()
    for ms in mat_rows:
        material_sets.append(CourseMaterialSet(title=ms["set_title"]))

    return Course(
        id=str(cid),
        name=row["title"],
        section=row.get("section", ""),
        descriptionHeading=row.get("description_heading", ""),
        description=row.get("description", ""),
        room=row.get("room", ""),
        ownerId=str(row["teacher_id"]),
        creationTime=ts_to_rfc3339(row.get("created_at")),
        updateTime=ts_to_rfc3339(row.get("updated_at") or row.get("created_at")),
        enrollmentCode=enrollment_code,
        courseState=row.get("course_state", "ACTIVE"),
        alternateLink=f"/course/{cid}",
        teacherGroupEmail=f"teachers-{cid}@bormoclass.local",
        courseGroupEmail=f"course-{cid}@bormoclass.local",
        teacherFolder=teacher_folder,
        calendarId=row.get("calendar_token") or f"cal_{cid}",
        gradebookSettings=gradebook_settings,
        courseMaterialSets=material_sets if material_sets else None,
        levels=row.get("levels", ""),
        subject=row.get("subject_code", "")
    )

# ============================================================================
# CRUD courses
# ============================================================================

@router.post("/v1/courses")
def create_course(req: Course, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSES,))

        if not can_create_course(ctx.user):
            api_error(403, "PERMISSION_DENIED", "Создание курсов запрещено политикой организации", reason="CourseCreationDisabled")

        name = (req.name or "").strip()
        if not name:
            api_error(400, "INVALID_ARGUMENT", "Название курса не может быть пустым", reason="CourseTitleEmpty")
        if len(name) > 250:
            api_error(400, "INVALID_ARGUMENT", "Название курса не может превышать 250 символов", reason="CourseTitleTooLong")
        if URL_REGEX.search(name):
            api_error(400, "INVALID_ARGUMENT", "Название курса не может содержать URL", reason="CourseTitleCannotContainUrl")

        # Определение владельца и начального состояния
        owner_id = ctx.user["id"]
        is_admin = (ctx.user.get("role") == "admin")
        initial_state = req.courseState

        if req.ownerId:
            resolved_owner = resolve_user_id(conn, req.ownerId, ctx.user)
            if resolved_owner != ctx.user["id"]:
                if not is_admin:
                    api_error(403, "PERMISSION_DENIED", "Только администратор может создавать курсы для других пользователей", reason="AdminOnlyCourseOwner")
                owner_id = resolved_owner
                if not initial_state:
                    initial_state = "PROVISIONED"

        if not initial_state:
            initial_state = "ACTIVE" if ctx.is_first_party else "PROVISIONED"

        if initial_state not in ("ACTIVE", "PROVISIONED"):
            api_error(400, "INVALID_ARGUMENT", f"Недопустимое начальное состояние курса: {initial_state}", reason="InvalidCourseState")

        now = int(time.time())
        pin = generate_join_pin(conn)
        calendar_token = f"cal_{uuid.uuid4().hex[:12]}"

        # Создание виртуальной папки учителя
        teacher_folder_id = f"folder_{uuid.uuid4().hex[:16]}"
        conn.execute(
            """INSERT INTO stored_folders (id, class_id, owner_user_id, folder_title, folder_kind, created_at)
               VALUES (?, NULL, ?, ?, 'COURSE_TEACHER_ROOT', ?)""",
            (teacher_folder_id, owner_id, f"{name} - Teacher Folder", now)
        )

        cursor = conn.execute(
            """INSERT INTO classes (
                teacher_id, title, subject_code, grade_level, join_pin,
                quarter_goal, recess_locked_until, classroom_state_json,
                section, description_heading, description, room, levels,
                course_state, enrollment_enabled, calendar_token,
                teacher_folder_id, theme_color, banner_preset, updated_at, created_at
            ) VALUES (?, ?, ?, 8, ?, '', 0, '{}', ?, ?, ?, ?, ?, ?, 1, ?, ?, '#f57300', 'default', ?, ?)""",
            (
                owner_id, name, req.subject or "inf", pin,
                req.section or "", req.descriptionHeading or "", req.description or "",
                req.room or "", req.levels or "", initial_state,
                calendar_token, teacher_folder_id, now, now
            )
        )
        new_class_id = cursor.lastrowid

        # Обновляем class_id у созданной папки
        conn.execute("UPDATE stored_folders SET class_id = ? WHERE id = ?", (new_class_id, teacher_folder_id))

        # Добавляем владельца в course_teachers
        conn.execute(
            "INSERT INTO course_teachers (class_id, teacher_id, is_primary, joined_at) VALUES (?, ?, 1, ?)",
            (new_class_id, owner_id, now)
        )

        row = conn.execute("SELECT * FROM classes WHERE id = ?", (new_class_id,)).fetchone()
        course_obj = format_course_model(dict(row), conn, ctx, role="OWNER")
        return course_obj

@router.get("/v1/courses/{id}")
def get_course(id: str, request: Request, fields: Optional[str] = Query(None)):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSES, SCOPE_COURSES_READONLY))

        class_id = resolve_class_id(conn, id, client_id=ctx.client_id)
        role = get_course_role(conn, class_id, ctx.user)
        if not role:
            api_error(404, "NOT_FOUND", "Курс не найден или нет доступа")

        row = conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Курс не найден")

        course_obj = format_course_model(dict(row), conn, ctx, role=role)
        payload = course_obj.model_dump(by_alias=True, exclude_none=True)
        return apply_fields_selector(payload, fields)

@router.get("/v1/courses")
def list_courses(
    request: Request,
    studentId: Optional[str] = Query(None),
    teacherId: Optional[str] = Query(None),
    courseStates: Optional[List[str]] = Query(None),
    pageSize: int = Query(30, ge=1, le=100),
    pageToken: Optional[str] = Query(None),
    fields: Optional[str] = Query(None)
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSES, SCOPE_COURSES_READONLY))

        if studentId and teacherId:
            api_error(400, "INVALID_ARGUMENT", "Нельзя указывать studentId и teacherId одновременно")

        conditions = []
        params = []

        is_admin = (ctx.user.get("role") == "admin")

        if studentId:
            sid = resolve_user_id(conn, studentId, ctx.user)
            if not is_admin and sid != ctx.user["id"]:
                # Разрешено только себе или если учим этого ученика
                has_common = conn.execute(
                    """SELECT 1 FROM class_members cm
                       JOIN classes c ON cm.class_id = c.id
                       WHERE cm.student_id = ? AND c.teacher_id = ? LIMIT 1""",
                    (sid, ctx.user["id"])
                ).fetchone()
                if not has_common:
                    api_error(403, "PERMISSION_DENIED", "Нет доступа к просмотру курсов данного ученика")
            conditions.append("EXISTS (SELECT 1 FROM class_members cm WHERE cm.class_id = c.id AND cm.student_id = ? AND cm.enrollment_active = 1)")
            params.append(sid)

        elif teacherId:
            tid = resolve_user_id(conn, teacherId, ctx.user)
            if not is_admin and tid != ctx.user["id"]:
                api_error(403, "PERMISSION_DENIED", "Нет доступа к просмотру курсов данного преподавателя")
            conditions.append("(c.teacher_id = ? OR EXISTS (SELECT 1 FROM course_teachers ct WHERE ct.class_id = c.id AND ct.teacher_id = ?))")
            params.extend([tid, tid])

        else:
            if not is_admin:
                conditions.append(
                    """(c.teacher_id = ? 
                        OR EXISTS (SELECT 1 FROM course_teachers ct WHERE ct.class_id = c.id AND ct.teacher_id = ?)
                        OR EXISTS (SELECT 1 FROM class_members cm WHERE cm.class_id = c.id AND cm.student_id = ? AND cm.enrollment_active = 1))"""
                )
                params.extend([ctx.user["id"], ctx.user["id"], ctx.user["id"]])

        # Фильтр по courseStates
        effective_states = []
        if courseStates:
            effective_states = [s for s in courseStates if s]
        elif studentId:
            effective_states = ["ACTIVE"]

        if effective_states:
            placeholders = ", ".join("?" for _ in effective_states)
            conditions.append(f"c.course_state IN ({placeholders})")
            params.extend(effective_states)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        fingerprint = f"{studentId or ''}:{teacherId or ''}:{','.join(sorted(effective_states))}"
        offset = decode_page_token(pageToken, fingerprint)

        query = f"""
            SELECT c.* FROM classes c
            {where_clause}
            ORDER BY c.created_at DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(query, params + [pageSize + 1, offset]).fetchall()

        courses_list = []
        has_next = len(rows) > pageSize
        items = rows[:pageSize]

        for r in items:
            courses_list.append(format_course_model(dict(r), conn, ctx))

        next_token = encode_page_token(offset + pageSize, fingerprint) if has_next else None
        resp = ListCoursesResponse(
            courses=courses_list if courses_list else None,
            nextPageToken=next_token
        )
        payload = resp.model_dump(by_alias=True, exclude_none=True)
        return apply_fields_selector(payload, fields)

@router.put("/v1/courses/{id}")
def update_course(id: str, req: Course, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSES,))

        class_id = resolve_class_id(conn, id, client_id=ctx.client_id)
        role = get_course_role(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для изменения курса")

        row = conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Курс не найден")
        old_data = dict(row)

        assert_course_modifiable(old_data, role)

        name = (req.name or old_data["title"]).strip()
        if not name:
            api_error(400, "INVALID_ARGUMENT", "Название курса не может быть пустым")
        if URL_REGEX.search(name):
            api_error(400, "INVALID_ARGUMENT", "Название курса не может содержать URL", reason="CourseTitleCannotContainUrl")

        new_state = req.courseState or old_data["course_state"]
        validate_course_state_transition(old_data["course_state"], new_state, role)

        # Инвариант PUT: если levels не передан, сохраняется прежний levels
        levels_val = req.levels if req.levels is not None else old_data["levels"]
        now = int(time.time())

        conn.execute(
            """UPDATE classes SET
                title = ?, section = ?, description_heading = ?, description = ?,
                room = ?, course_state = ?, levels = ?, subject_code = ?, updated_at = ?
               WHERE id = ?""",
            (
                name, req.section or "", req.descriptionHeading or "", req.description or "",
                req.room or "", new_state, levels_val, req.subject or old_data["subject_code"],
                now, class_id
            )
        )

        updated_row = conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
        return format_course_model(dict(updated_row), conn, ctx, role=role)

@router.patch("/v1/courses/{id}")
def patch_course(id: str, req: Course, request: Request, updateMask: Optional[str] = Query(None)):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSES,))

        allowed_fields = {
            "name", "section", "descriptionHeading", "description",
            "room", "courseState", "ownerId", "subject",
            "learningStandardSettings", "levels"
        }
        mask_fields = parse_update_mask(updateMask, allowed_fields)

        class_id = resolve_class_id(conn, id, client_id=ctx.client_id)
        role = get_course_role(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для изменения курса")

        row = conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Курс не найден")
        old_data = dict(row)

        if "course_state" not in mask_fields:
            assert_course_modifiable(old_data, role)

        updates = []
        params = []
        now = int(time.time())

        if "name" in mask_fields:
            name = (req.name or "").strip()
            if not name:
                api_error(400, "INVALID_ARGUMENT", "Название курса не может быть пустым")
            if URL_REGEX.search(name):
                api_error(400, "INVALID_ARGUMENT", "Название курса не может содержать URL", reason="CourseTitleCannotContainUrl")
            updates.append("title = ?")
            params.append(name)

        if "section" in mask_fields:
            updates.append("section = ?")
            params.append(req.section or "")

        if "description_heading" in mask_fields:
            updates.append("description_heading = ?")
            params.append(req.descriptionHeading or "")

        if "description" in mask_fields:
            updates.append("description = ?")
            params.append(req.description or "")

        if "room" in mask_fields:
            updates.append("room = ?")
            params.append(req.room or "")

        if "levels" in mask_fields:
            updates.append("levels = ?")
            params.append(req.levels or "")

        if "subject" in mask_fields:
            updates.append("subject_code = ?")
            params.append(req.subject or "")

        if "course_state" in mask_fields:
            new_state = req.courseState or old_data["course_state"]
            validate_course_state_transition(old_data["course_state"], new_state, role)
            updates.append("course_state = ?")
            params.append(new_state)

        if "owner_id" in mask_fields:
            if role != "ADMIN":
                api_error(403, "PERMISSION_DENIED", "Только администратор может передавать владение через PATCH", reason="AdminOnlyOwnerTransfer")
            new_owner_id = resolve_user_id(conn, req.ownerId, ctx.user)
            updates.append("teacher_id = ?")
            params.append(new_owner_id)
            # Обновляем роли в course_teachers
            conn.execute("UPDATE course_teachers SET is_primary = 0 WHERE class_id = ?", (class_id,))
            conn.execute(
                """INSERT INTO course_teachers (class_id, teacher_id, is_primary, joined_at)
                   VALUES (?, ?, 1, ?)
                   ON CONFLICT(class_id, teacher_id) DO UPDATE SET is_primary = 1""",
                (class_id, new_owner_id, now)
            )

        updates.append("updated_at = ?")
        params.append(now)
        params.append(class_id)

        conn.execute(f"UPDATE classes SET {', '.join(updates)} WHERE id = ?", params)
        updated_row = conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
        return format_course_model(dict(updated_row), conn, ctx, role=role)

@router.delete("/v1/courses/{id}")
def delete_course(id: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSES,))

        class_id = resolve_class_id(conn, id, client_id=ctx.client_id)
        role = get_course_role(conn, class_id, ctx.user)
        if role not in ("OWNER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Только владелец или администратор может удалить курс")

        row = conn.execute("SELECT course_state FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Курс не найден")

        state = row["course_state"]
        if state not in ("ARCHIVED", "PROVISIONED", "DECLINED"):
            api_error(
                400,
                "FAILED_PRECONDITION",
                "Активный курс нельзя удалить. Сначала переведите курс в состояние ARCHIVED.",
                reason="CourseNotArchived"
            )

        conn.execute("DELETE FROM classes WHERE id = ?", (class_id,))
        return Empty()

# ============================================================================
# Псевдонимы курсов (courses.aliases)
# ============================================================================

@router.post("/v1/courses/{courseId}/aliases")
def create_course_alias(courseId: str, req: CourseAlias, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSES,))

        class_id = resolve_class_id(conn, courseId, client_id=ctx.client_id)
        role = get_course_role(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для управления псевдонимами курса")

        alias = (req.alias or "").strip()
        if not alias:
            api_error(400, "INVALID_ARGUMENT", "Псевдоним не может быть пустым")

        if alias.startswith("d:"):
            if role != "ADMIN":
                api_error(403, "PERMISSION_DENIED", "Создание domain-scoped псевдонимов (d:) доступно только администратору")
            scope_kind = "DOMAIN"
            client_id = ""
        elif alias.startswith("p:"):
            scope_kind = "PROJECT"
            client_id = ctx.client_id
        else:
            api_error(400, "INVALID_ARGUMENT", "Псевдоним должен начинаться с 'd:' или 'p:'", reason="InvalidAliasPrefix")

        existing = conn.execute("SELECT 1 FROM course_aliases WHERE alias_key = ?", (alias,)).fetchone()
        if existing:
            api_error(409, "ALREADY_EXISTS", f"Псевдоним '{alias}' уже занят", reason="AliasAlreadyExists")

        now = int(time.time())
        conn.execute(
            """INSERT INTO course_aliases (alias_key, class_id, scope_kind, client_id, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (alias, class_id, scope_kind, client_id, now)
        )
        return CourseAlias(alias=alias)

@router.get("/v1/courses/{courseId}/aliases")
def list_course_aliases(
    courseId: str,
    request: Request,
    pageSize: int = Query(30, ge=1, le=100),
    pageToken: Optional[str] = Query(None)
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSES, SCOPE_COURSES_READONLY))

        class_id = resolve_class_id(conn, courseId, client_id=ctx.client_id)
        role = get_course_role(conn, class_id, ctx.user)
        if not role:
            api_error(404, "NOT_FOUND", "Курс не найден или нет доступа")

        fingerprint = f"aliases:{class_id}:{ctx.client_id}"
        offset = decode_page_token(pageToken, fingerprint)

        rows = conn.execute(
            """SELECT alias_key FROM course_aliases
               WHERE class_id = ? AND (scope_kind = 'DOMAIN' OR client_id = ? OR client_id = 'first_party')
               ORDER BY created_at ASC
               LIMIT ? OFFSET ?""",
            (class_id, ctx.client_id, pageSize + 1, offset)
        ).fetchall()

        has_next = len(rows) > pageSize
        items = rows[:pageSize]
        aliases = [CourseAlias(alias=r["alias_key"]) for r in items]
        next_token = encode_page_token(offset + pageSize, fingerprint) if has_next else None

        return ListCourseAliasesResponse(
            aliases=aliases if aliases else None,
            nextPageToken=next_token
        )

@router.delete("/v1/courses/{courseId}/aliases/{alias}")
def delete_course_alias(courseId: str, alias: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSES,))

        class_id = resolve_class_id(conn, courseId, client_id=ctx.client_id)
        role = get_course_role(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для удаления псевдонима")

        row = conn.execute(
            "SELECT scope_kind, client_id FROM course_aliases WHERE alias_key = ? AND class_id = ?",
            (alias, class_id)
        ).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", f"Псевдоним '{alias}' не найден для данного курса")

        if row["scope_kind"] == "DOMAIN" and role != "ADMIN":
            api_error(403, "PERMISSION_DENIED", "Удаление domain-scoped псевдонимов доступно только администратору")
        if row["scope_kind"] == "PROJECT" and not ctx.is_first_party and row["client_id"] != ctx.client_id:
            api_error(403, "PERMISSION_DENIED", "Псевдоним принадлежит другому приложению")

        conn.execute("DELETE FROM course_aliases WHERE alias_key = ? AND class_id = ?", (alias, class_id))
        return Empty()
