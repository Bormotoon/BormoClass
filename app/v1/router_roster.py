import time
import uuid
from typing import Optional, List
from fastapi import APIRouter, Request, Query
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
    resolve_user_id
)
from app.v1.rbac import (
    resolve_auth_context,
    require_scopes,
    get_course_role,
    assert_course_access,
    SCOPE_ROSTERS,
    SCOPE_ROSTERS_READONLY,
    SCOPE_PROFILE_EMAILS,
    SCOPE_PROFILE_PHOTOS
)
from app.v1.schemas import (
    Teacher,
    Student,
    UserProfile,
    Name,
    DriveFolder,
    Invitation,
    StudentGroup,
    StudentGroupMember,
    ListTeachersResponse,
    ListStudentsResponse,
    ListInvitationsResponse,
    ListStudentGroupsResponse,
    ListStudentGroupMembersResponse,
    Empty
)
from app.v1.router_courses import assert_course_modifiable

router = APIRouter(tags=["roster"])

def _build_user_profile(u: dict, ctx) -> UserProfile:
    email_address = None
    if SCOPE_PROFILE_EMAILS in ctx.scopes or ctx.is_first_party:
        email_address = f"{u['handle']}@bormoclass.local"

    photo_url = None
    if SCOPE_PROFILE_PHOTOS in ctx.scopes or ctx.is_first_party:
        seed = u.get("avatar_seed", 1)
        photo_url = f"/api/v1-avatar/{seed}.svg"

    return UserProfile(
        id=str(u["id"]),
        name=Name(
            givenName=u["handle"],
            familyName="",
            fullName=u["handle"]
        ),
        emailAddress=email_address,
        photoUrl=photo_url,
        verifiedTeacher=bool(u.get("verified_teacher", 0))
    )

def _get_next_free_seat(conn, class_id: int) -> int:
    used = {r["seat_number"] for r in conn.execute(
        "SELECT seat_number FROM class_members WHERE class_id = ?",
        (class_id,)
    ).fetchall()}
    for s in range(1, 41):
        if s not in used:
            return s
    return 1

# ============================================================================
# 4.1. courses.teachers (4 метода)
# ============================================================================

@router.post("/v1/courses/{courseId}/teachers")
def create_teacher(courseId: str, req: Teacher, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ROSTERS,))

        class_id = resolve_class_id(conn, courseId, client_id=ctx.client_id)
        caller_role = get_course_role(conn, class_id, ctx.user)
        if caller_role not in ("OWNER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Добавление преподавателя доступно только владельцу курса или администратору")

        c_row = conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not c_row:
            api_error(404, "NOT_FOUND", "Курс не найден")
        assert_course_modifiable(dict(c_row), caller_role)

        target_id = resolve_user_id(conn, req.userId or "me", ctx.user)

        # Проверка лимита: не более 50 учителей на курс
        cnt_row = conn.execute(
            "SELECT COUNT(*) as cnt FROM course_teachers WHERE class_id = ?",
            (class_id,)
        ).fetchone()
        if cnt_row and cnt_row["cnt"] >= 50:
            api_error(400, "FAILED_PRECONDITION", "В курсе не может быть более 50 преподавателей", reason="TeacherLimitReached")

        # Проверка: нельзя добавить ученика этого же курса в учителя
        as_student = conn.execute(
            "SELECT 1 FROM class_members WHERE class_id = ? AND student_id = ? AND enrollment_active = 1",
            (class_id, target_id)
        ).fetchone()
        if as_student:
            api_error(409, "ALREADY_EXISTS", "Пользователь уже числится учеником этого курса", reason="UserAlreadyStudent")

        existing_t = conn.execute(
            "SELECT 1 FROM course_teachers WHERE class_id = ? AND teacher_id = ?",
            (class_id, target_id)
        ).fetchone()
        if existing_t:
            api_error(409, "ALREADY_EXISTS", "Пользователь уже является преподавателем курса")

        now = int(time.time())
        conn.execute(
            "INSERT INTO course_teachers (class_id, teacher_id, is_primary, joined_at) VALUES (?, ?, 0, ?)",
            (class_id, target_id, now)
        )

        u_row = conn.execute("SELECT * FROM users WHERE id = ?", (target_id,)).fetchone()
        profile = _build_user_profile(dict(u_row), ctx)
        return Teacher(courseId=str(class_id), userId=str(target_id), profile=profile)

@router.get("/v1/courses/{courseId}/teachers/{userId}")
def get_teacher(courseId: str, userId: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ROSTERS, SCOPE_ROSTERS_READONLY))

        class_id = resolve_class_id(conn, courseId, client_id=ctx.client_id)
        assert_course_access(conn, class_id, ctx.user)

        target_id = resolve_user_id(conn, userId, ctx.user)
        t_row = conn.execute(
            "SELECT teacher_id FROM course_teachers WHERE class_id = ? AND teacher_id = ?",
            (class_id, target_id)
        ).fetchone()
        if not t_row:
            api_error(404, "NOT_FOUND", "Преподаватель не найден в данном курсе")

        u_row = conn.execute("SELECT * FROM users WHERE id = ?", (target_id,)).fetchone()
        profile = _build_user_profile(dict(u_row), ctx)
        return Teacher(courseId=str(class_id), userId=str(target_id), profile=profile)

@router.get("/v1/courses/{courseId}/teachers")
def list_teachers(
    courseId: str,
    request: Request,
    pageSize: int = Query(30, ge=1, le=100),
    pageToken: Optional[str] = Query(None)
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ROSTERS, SCOPE_ROSTERS_READONLY))

        class_id = resolve_class_id(conn, courseId, client_id=ctx.client_id)
        assert_course_access(conn, class_id, ctx.user)

        fingerprint = f"teachers:{class_id}"
        offset = decode_page_token(pageToken, fingerprint)

        rows = conn.execute(
            """SELECT u.* FROM course_teachers ct
               JOIN users u ON ct.teacher_id = u.id
               WHERE ct.class_id = ?
               ORDER BY ct.is_primary DESC, ct.joined_at ASC
               LIMIT ? OFFSET ?""",
            (class_id, pageSize + 1, offset)
        ).fetchall()

        has_next = len(rows) > pageSize
        items = rows[:pageSize]
        teachers_list = [
            Teacher(courseId=str(class_id), userId=str(r["id"]), profile=_build_user_profile(dict(r), ctx))
            for r in items
        ]
        next_token = encode_page_token(offset + pageSize, fingerprint) if has_next else None

        return ListTeachersResponse(
            teachers=teachers_list if teachers_list else None,
            nextPageToken=next_token
        )

@router.delete("/v1/courses/{courseId}/teachers/{userId}")
def delete_teacher(courseId: str, userId: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ROSTERS,))

        class_id = resolve_class_id(conn, courseId, client_id=ctx.client_id)
        caller_role = get_course_role(conn, class_id, ctx.user)
        target_id = resolve_user_id(conn, userId, ctx.user)

        c_row = conn.execute("SELECT teacher_id, course_state FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not c_row:
            api_error(404, "NOT_FOUND", "Курс не найден")
        assert_course_modifiable(dict(c_row), caller_role)

        # Запрещено удалять владельца курса
        if c_row["teacher_id"] == target_id:
            api_error(403, "PERMISSION_DENIED", "Нельзя удалить владельца курса", reason="CannotDeleteCourseOwner")

        # Со-учитель может удалить себя сам, либо OWNER / ADMIN
        if target_id != ctx.user["id"] and caller_role not in ("OWNER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для удаления преподавателя")

        existing = conn.execute(
            "SELECT 1 FROM course_teachers WHERE class_id = ? AND teacher_id = ?",
            (class_id, target_id)
        ).fetchone()
        if not existing:
            api_error(404, "NOT_FOUND", "Преподаватель не найден в курсе")

        conn.execute("DELETE FROM course_teachers WHERE class_id = ? AND teacher_id = ?", (class_id, target_id))
        return Empty()

# ============================================================================
# 4.2. courses.students (4 метода)
# ============================================================================

@router.post("/v1/courses/{courseId}/students")
def create_student(
    courseId: str,
    req: Student,
    request: Request,
    enrollmentCode: Optional[str] = Query(None)
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ROSTERS,))

        class_id = resolve_class_id(conn, courseId, client_id=ctx.client_id)
        caller_role = get_course_role(conn, class_id, ctx.user)

        c_row = conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not c_row:
            api_error(404, "NOT_FOUND", "Курс не найден")
        course_data = dict(c_row)
        assert_course_modifiable(course_data, caller_role or "STUDENT")

        target_id = resolve_user_id(conn, req.userId or "me", ctx.user)
        is_self = (target_id == ctx.user["id"])

        if is_self:
            # Самостоятельная запись ученика требует enrollmentCode
            if course_data.get("enrollment_enabled", 1) != 1:
                api_error(403, "PERMISSION_DENIED", "Запись в курс отключена преподавателем", reason="EnrollmentDisabled")
            if course_data.get("course_state") != "ACTIVE":
                api_error(403, "PERMISSION_DENIED", "Запись возможна только в активные курсы", reason="CourseNotActive")
            if not enrollmentCode or enrollmentCode.strip() != course_data["join_pin"]:
                api_error(403, "PERMISSION_DENIED", "Неверный код записи в курс", reason="InvalidEnrollmentCode")
        else:
            if caller_role not in ("OWNER", "TEACHER", "ADMIN"):
                api_error(403, "PERMISSION_DENIED", "Только преподаватель или администратор может зачислять других учеников")

        # Проверка: учитель этого же курса не может быть зачислен учеником
        as_teacher = conn.execute(
            "SELECT 1 FROM course_teachers WHERE class_id = ? AND teacher_id = ?",
            (class_id, target_id)
        ).fetchone()
        if as_teacher or course_data["teacher_id"] == target_id:
            api_error(409, "ALREADY_EXISTS", "Преподаватель курса не может быть зачислен учеником")

        now = int(time.time())

        # Создание или реактивация в class_members
        existing_m = conn.execute(
            "SELECT enrollment_active, student_folder_id FROM class_members WHERE class_id = ? AND student_id = ?",
            (class_id, target_id)
        ).fetchone()

        folder_id = None
        if existing_m:
            if existing_m["enrollment_active"] == 1:
                api_error(409, "ALREADY_EXISTS", "Ученик уже зачислен в курс")
            folder_id = existing_m["student_folder_id"]
            conn.execute(
                "UPDATE class_members SET enrollment_active = 1 WHERE class_id = ? AND student_id = ?",
                (class_id, target_id)
            )
        else:
            seat_num = _get_next_free_seat(conn, class_id)
            folder_id = f"folder_st_{class_id}_{target_id}"
            conn.execute(
                """INSERT INTO stored_folders (id, class_id, owner_user_id, folder_title, folder_kind, created_at)
                   VALUES (?, ?, ?, ?, 'STUDENT_COURSE_FOLDER', ?)""",
                (folder_id, class_id, target_id, f"Student Folder {target_id}", now)
            )
            conn.execute(
                """INSERT INTO class_members (
                    class_id, student_id, seat_number, is_present, traffic_light,
                    is_muted, enrollment_active, student_folder_id, joined_at
                ) VALUES (?, ?, ?, 1, 'green', 0, 1, ?, ?)""",
                (class_id, target_id, seat_num, folder_id, now)
            )

        # Создание строк submissions для опубликованных заданий (если ещё нет)
        active_cw = conn.execute(
            "SELECT id FROM coursework WHERE class_id = ? AND state IN ('published', 'PUBLISHED')",
            (class_id,)
        ).fetchall()
        for cw in active_cw:
            conn.execute(
                """INSERT OR IGNORE INTO submissions (
                    coursework_id, student_id, status, v1_state, is_late,
                    draft_rubric_json, assigned_rubric_json, short_answer_text, mc_answer_text,
                    created_at, updated_at
                ) VALUES (?, ?, 'assigned', 'NEW', 0, '{}', '{}', '', '', ?, ?)""",
                (cw["id"], target_id, now, now)
            )

        u_row = conn.execute("SELECT * FROM users WHERE id = ?", (target_id,)).fetchone()
        profile = _build_user_profile(dict(u_row), ctx)
        work_folder = DriveFolder(
            id=folder_id,
            title="Student Folder",
            alternateLink=f"/api/storage/folders/{folder_id}"
        ) if folder_id else None

        return Student(
            courseId=str(class_id),
            userId=str(target_id),
            profile=profile,
            studentWorkFolder=work_folder
        )

@router.get("/v1/courses/{courseId}/students/{userId}")
def get_student(courseId: str, userId: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ROSTERS, SCOPE_ROSTERS_READONLY))

        class_id = resolve_class_id(conn, courseId, client_id=ctx.client_id)
        assert_course_access(conn, class_id, ctx.user)

        target_id = resolve_user_id(conn, userId, ctx.user)
        m_row = conn.execute(
            "SELECT student_folder_id FROM class_members WHERE class_id = ? AND student_id = ? AND enrollment_active = 1",
            (class_id, target_id)
        ).fetchone()
        if not m_row:
            api_error(404, "NOT_FOUND", "Ученик не найден в данном курсе")

        u_row = conn.execute("SELECT * FROM users WHERE id = ?", (target_id,)).fetchone()
        profile = _build_user_profile(dict(u_row), ctx)
        work_folder = None
        if m_row["student_folder_id"]:
            work_folder = DriveFolder(
                id=m_row["student_folder_id"],
                title="Student Folder",
                alternateLink=f"/api/storage/folders/{m_row['student_folder_id']}"
            )

        return Student(
            courseId=str(class_id),
            userId=str(target_id),
            profile=profile,
            studentWorkFolder=work_folder
        )

@router.get("/v1/courses/{courseId}/students")
def list_students(
    courseId: str,
    request: Request,
    pageSize: int = Query(30, ge=1, le=100),
    pageToken: Optional[str] = Query(None)
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ROSTERS, SCOPE_ROSTERS_READONLY))

        class_id = resolve_class_id(conn, courseId, client_id=ctx.client_id)
        assert_course_access(conn, class_id, ctx.user)

        fingerprint = f"students:{class_id}"
        offset = decode_page_token(pageToken, fingerprint)

        rows = conn.execute(
            """SELECT u.*, cm.student_folder_id FROM class_members cm
               JOIN users u ON cm.student_id = u.id
               WHERE cm.class_id = ? AND cm.enrollment_active = 1
               ORDER BY cm.seat_number ASC
               LIMIT ? OFFSET ?""",
            (class_id, pageSize + 1, offset)
        ).fetchall()

        has_next = len(rows) > pageSize
        items = rows[:pageSize]

        students_list = []
        for r in items:
            profile = _build_user_profile(dict(r), ctx)
            wf = None
            if r["student_folder_id"]:
                wf = DriveFolder(
                    id=r["student_folder_id"],
                    title="Student Folder",
                    alternateLink=f"/api/storage/folders/{r['student_folder_id']}"
                )
            students_list.append(Student(
                courseId=str(class_id),
                userId=str(r["id"]),
                profile=profile,
                studentWorkFolder=wf
            ))

        next_token = encode_page_token(offset + pageSize, fingerprint) if has_next else None
        return ListStudentsResponse(
            students=students_list if students_list else None,
            nextPageToken=next_token
        )

@router.delete("/v1/courses/{courseId}/students/{userId}")
def delete_student(courseId: str, userId: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ROSTERS,))

        class_id = resolve_class_id(conn, courseId, client_id=ctx.client_id)
        caller_role = get_course_role(conn, class_id, ctx.user)
        target_id = resolve_user_id(conn, userId, ctx.user)

        if target_id == ctx.user["id"]:
            if not settings.ALLOW_STUDENT_UNENROLL:
                api_error(403, "PERMISSION_DENIED", "Самостоятельный выход из курса запрещен администратором", reason="StudentUnenrollDisabled")
        else:
            if caller_role not in ("OWNER", "TEACHER", "ADMIN"):
                api_error(403, "PERMISSION_DENIED", "Недостаточно прав для отчисления ученика")

        row = conn.execute(
            "SELECT 1 FROM class_members WHERE class_id = ? AND student_id = ? AND enrollment_active = 1",
            (class_id, target_id)
        ).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Ученик не найден в данном курсе")

        # Отчисление: переводим в inactive, удаляем из подгрупп, сохраняем submissions
        conn.execute(
            "UPDATE class_members SET enrollment_active = 0 WHERE class_id = ? AND student_id = ?",
            (class_id, target_id)
        )
        conn.execute(
            "DELETE FROM student_group_members WHERE class_id = ? AND student_id = ?",
            (class_id, target_id)
        )
        return Empty()

# ============================================================================
# 4.3. Приглашения в курс (invitations - 5 методов)
# ============================================================================

@router.post("/v1/invitations")
def create_invitation(req: Invitation, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ROSTERS,))

        if not req.courseId or not req.userId or not req.role:
            api_error(400, "INVALID_ARGUMENT", "Поля courseId, userId и role обязательны")

        class_id = resolve_class_id(conn, req.courseId, client_id=ctx.client_id)
        caller_role = get_course_role(conn, class_id, ctx.user)

        if req.role not in ("STUDENT", "TEACHER", "OWNER"):
            api_error(400, "INVALID_ARGUMENT", f"Недопустимая роль приглашения: {req.role}")

        if req.role == "OWNER" and caller_role not in ("OWNER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Передать владение может только текущий владелец или администратор")
        elif caller_role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для отправки приглашения")

        target_id = resolve_user_id(conn, req.userId, ctx.user)

        existing = conn.execute(
            "SELECT id FROM invitations WHERE class_id = ? AND invited_user_id = ?",
            (class_id, target_id)
        ).fetchone()
        if existing:
            api_error(409, "ALREADY_EXISTS", "Приглашение для данного пользователя в этот курс уже существует", reason="InvitationAlreadyExists")

        now = int(time.time())
        cursor = conn.execute(
            """INSERT INTO invitations (class_id, invited_user_id, inviter_user_id, role, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (class_id, target_id, ctx.user["id"], req.role, now)
        )
        new_inv_id = cursor.lastrowid

        # Создание оповещения
        c_row = conn.execute("SELECT title FROM classes WHERE id = ?", (class_id,)).fetchone()
        course_title = c_row["title"] if c_row else "Курс"
        conn.execute(
            """INSERT INTO notifications (user_id, class_id, notif_kind, title, body_text, link_path, created_at)
               VALUES (?, ?, 'INVITATION', ?, ?, ?, ?)""",
            (target_id, class_id, f"Приглашение в курс: {course_title}", f"Вам отправлено приглашение с ролью {req.role}", f"/course/{class_id}", now)
        )

        return Invitation(
            id=str(new_inv_id),
            courseId=str(class_id),
            userId=str(target_id),
            role=req.role
        )

@router.get("/v1/invitations/{id}")
def get_invitation(id: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ROSTERS, SCOPE_ROSTERS_READONLY))

        row = conn.execute("SELECT * FROM invitations WHERE id = ?", (id,)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Приглашение не найдено")

        inv = dict(row)
        caller_id = ctx.user["id"]
        is_admin = (ctx.user.get("role") == "admin")
        is_participant = (inv["invited_user_id"] == caller_id or inv["inviter_user_id"] == caller_id)

        if not is_admin and not is_participant:
            caller_role = get_course_role(conn, inv["class_id"], ctx.user)
            if caller_role not in ("OWNER", "TEACHER"):
                api_error(403, "PERMISSION_DENIED", "Нет доступа к просмотру данного приглашения")

        return Invitation(
            id=str(inv["id"]),
            courseId=str(inv["class_id"]),
            userId=str(inv["invited_user_id"]),
            role=inv["role"]
        )

@router.get("/v1/invitations")
def list_invitations(
    request: Request,
    userId: Optional[str] = Query(None),
    courseId: Optional[str] = Query(None),
    pageSize: int = Query(500, ge=1, le=1000),
    pageToken: Optional[str] = Query(None)
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ROSTERS, SCOPE_ROSTERS_READONLY))

        if not userId and not courseId:
            api_error(400, "INVALID_ARGUMENT", "Укажите userId или courseId")

        conditions = []
        params = []

        if userId:
            uid = resolve_user_id(conn, userId, ctx.user)
            conditions.append("invited_user_id = ?")
            params.append(uid)

        if courseId:
            cid = resolve_class_id(conn, courseId, client_id=ctx.client_id)
            conditions.append("class_id = ?")
            params.append(cid)

        fingerprint = f"invs:{userId or ''}:{courseId or ''}"
        offset = decode_page_token(pageToken, fingerprint)

        where_clause = f"WHERE {' AND '.join(conditions)}"
        rows = conn.execute(
            f"SELECT * FROM invitations {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [pageSize + 1, offset]
        ).fetchall()

        has_next = len(rows) > pageSize
        items = rows[:pageSize]

        inv_list = [
            Invitation(
                id=str(r["id"]),
                courseId=str(r["class_id"]),
                userId=str(r["invited_user_id"]),
                role=r["role"]
            )
            for r in items
        ]

        next_token = encode_page_token(offset + pageSize, fingerprint) if has_next else None
        return ListInvitationsResponse(
            invitations=inv_list if inv_list else None,
            nextPageToken=next_token
        )

@router.delete("/v1/invitations/{id}")
def delete_invitation(id: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ROSTERS,))

        row = conn.execute("SELECT * FROM invitations WHERE id = ?", (id,)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Приглашение не найдено")

        inv = dict(row)
        caller_id = ctx.user["id"]
        is_admin = (ctx.user.get("role") == "admin")
        is_actor = (inv["invited_user_id"] == caller_id or inv["inviter_user_id"] == caller_id)

        if not is_admin and not is_actor:
            caller_role = get_course_role(conn, inv["class_id"], ctx.user)
            if caller_role != "OWNER":
                api_error(403, "PERMISSION_DENIED", "Недостаточно прав для отзыва приглашения")

        conn.execute("DELETE FROM invitations WHERE id = ?", (id,))
        return Empty()

@router.post("/v1/invitations/{id}:accept")
def accept_invitation(id: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ROSTERS,))

        row = conn.execute("SELECT * FROM invitations WHERE id = ?", (id,)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Приглашение не найдено")

        inv = dict(row)
        if inv["invited_user_id"] != ctx.user["id"]:
            api_error(403, "PERMISSION_DENIED", "Принять приглашение может только приглашённый пользователь", reason="NotInvitedUser")

        class_id = inv["class_id"]
        user_id = ctx.user["id"]
        role = inv["role"]
        now = int(time.time())

        if role == "STUDENT":
            existing = conn.execute(
                "SELECT 1 FROM class_members WHERE class_id = ? AND student_id = ?",
                (class_id, user_id)
            ).fetchone()
            if existing:
                conn.execute("UPDATE class_members SET enrollment_active = 1 WHERE class_id = ? AND student_id = ?", (class_id, user_id))
            else:
                seat = _get_next_free_seat(conn, class_id)
                folder_id = f"folder_st_{class_id}_{user_id}"
                conn.execute(
                    """INSERT INTO stored_folders (id, class_id, owner_user_id, folder_title, folder_kind, created_at)
                       VALUES (?, ?, ?, ?, 'STUDENT_COURSE_FOLDER', ?)""",
                    (folder_id, class_id, user_id, f"Student Folder {user_id}", now)
                )
                conn.execute(
                    """INSERT INTO class_members (class_id, student_id, seat_number, is_present, traffic_light, is_muted, enrollment_active, student_folder_id, joined_at)
                       VALUES (?, ?, ?, 1, 'green', 0, 1, ?, ?)""",
                    (class_id, user_id, seat, folder_id, now)
                )

            # Назначаем опубликованные задания
            active_cw = conn.execute("SELECT id FROM coursework WHERE class_id = ? AND state IN ('published', 'PUBLISHED')", (class_id,)).fetchall()
            for cw in active_cw:
                conn.execute(
                    """INSERT OR IGNORE INTO submissions (coursework_id, student_id, status, v1_state, created_at, updated_at)
                       VALUES (?, ?, 'assigned', 'NEW', ?, ?)""",
                    (cw["id"], user_id, now, now)
                )

        elif role == "TEACHER":
            conn.execute(
                """INSERT INTO course_teachers (class_id, teacher_id, is_primary, joined_at)
                   VALUES (?, ?, 0, ?)
                   ON CONFLICT(class_id, teacher_id) DO NOTHING""",
                (class_id, user_id, now)
            )

        elif role == "OWNER":
            # Атомарная передача владения курсом
            old_owner_row = conn.execute("SELECT teacher_id FROM classes WHERE id = ?", (class_id,)).fetchone()
            if old_owner_row:
                old_owner_id = old_owner_row["teacher_id"]
                conn.execute("UPDATE course_teachers SET is_primary = 0 WHERE class_id = ? AND teacher_id = ?", (class_id, old_owner_id))

            conn.execute("UPDATE classes SET teacher_id = ?, updated_at = ? WHERE id = ?", (user_id, now, class_id))
            conn.execute(
                """INSERT INTO course_teachers (class_id, teacher_id, is_primary, joined_at)
                   VALUES (?, ?, 1, ?)
                   ON CONFLICT(class_id, teacher_id) DO UPDATE SET is_primary = 1""",
                (class_id, user_id, now)
            )

        # Удаляем использованное приглашение
        conn.execute("DELETE FROM invitations WHERE id = ?", (id,))
        return Empty()

# ============================================================================
# 4.4. Подгруппы учеников (courses.studentGroups - 7 методов)
# ============================================================================

@router.post("/v1/courses/{courseId}/studentGroups")
def create_student_group(courseId: str, req: StudentGroup, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ROSTERS,))

        class_id = resolve_class_id(conn, courseId, client_id=ctx.client_id)
        caller_role = get_course_role(conn, class_id, ctx.user)
        if caller_role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Управление подгруппами доступно только преподавателям курса")

        title = (req.title or "").strip()
        if not title:
            api_error(400, "INVALID_ARGUMENT", "Название подгруппы не может быть пустым")

        now = int(time.time())
        cursor = conn.execute(
            "INSERT INTO student_groups (class_id, group_title, created_at) VALUES (?, ?, ?)",
            (class_id, title, now)
        )
        new_id = cursor.lastrowid
        return StudentGroup(id=str(new_id), courseId=str(class_id), title=title)

@router.get("/v1/courses/{courseId}/studentGroups/{id}")
def get_student_group(courseId: str, id: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ROSTERS, SCOPE_ROSTERS_READONLY))

        class_id = resolve_class_id(conn, courseId, client_id=ctx.client_id)
        assert_course_access(conn, class_id, ctx.user)

        row = conn.execute(
            "SELECT * FROM student_groups WHERE id = ? AND class_id = ?",
            (id, class_id)
        ).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Подгруппа не найдена")

        return StudentGroup(id=str(row["id"]), courseId=str(class_id), title=row["group_title"])

@router.get("/v1/courses/{courseId}/studentGroups")
def list_student_groups(
    courseId: str,
    request: Request,
    pageSize: int = Query(75, ge=1, le=100),
    pageToken: Optional[str] = Query(None)
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ROSTERS, SCOPE_ROSTERS_READONLY))

        class_id = resolve_class_id(conn, courseId, client_id=ctx.client_id)
        assert_course_access(conn, class_id, ctx.user)

        fingerprint = f"sg:{class_id}"
        offset = decode_page_token(pageToken, fingerprint)

        rows = conn.execute(
            "SELECT * FROM student_groups WHERE class_id = ? ORDER BY id ASC LIMIT ? OFFSET ?",
            (class_id, pageSize + 1, offset)
        ).fetchall()

        has_next = len(rows) > pageSize
        items = rows[:pageSize]
        groups = [StudentGroup(id=str(r["id"]), courseId=str(class_id), title=r["group_title"]) for r in items]
        next_token = encode_page_token(offset + pageSize, fingerprint) if has_next else None

        return ListStudentGroupsResponse(
            studentGroups=groups if groups else None,
            nextPageToken=next_token
        )

@router.patch("/v1/courses/{courseId}/studentGroups/{id}")
def patch_student_group(courseId: str, id: str, req: StudentGroup, request: Request, updateMask: Optional[str] = Query(None)):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ROSTERS,))

        class_id = resolve_class_id(conn, courseId, client_id=ctx.client_id)
        caller_role = get_course_role(conn, class_id, ctx.user)
        if caller_role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Управление подгруппами доступно только преподавателям")

        mask = parse_update_mask(updateMask, {"title"})
        row = conn.execute("SELECT * FROM student_groups WHERE id = ? AND class_id = ?", (id, class_id)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Подгруппа не найдена")

        new_title = (req.title or "").strip()
        if "title" in mask:
            if not new_title:
                api_error(400, "INVALID_ARGUMENT", "Название подгруппы не может быть пустым")
            conn.execute("UPDATE student_groups SET group_title = ? WHERE id = ? AND class_id = ?", (new_title, id, class_id))

        updated_row = conn.execute("SELECT * FROM student_groups WHERE id = ? AND class_id = ?", (id, class_id)).fetchone()
        return StudentGroup(id=str(updated_row["id"]), courseId=str(class_id), title=updated_row["group_title"])

@router.delete("/v1/courses/{courseId}/studentGroups/{id}")
def delete_student_group(courseId: str, id: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ROSTERS,))

        class_id = resolve_class_id(conn, courseId, client_id=ctx.client_id)
        caller_role = get_course_role(conn, class_id, ctx.user)
        if caller_role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Удаление подгруппы доступно только преподавателям")

        row = conn.execute("SELECT 1 FROM student_groups WHERE id = ? AND class_id = ?", (id, class_id)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Подгруппа не найдена")

        conn.execute("DELETE FROM student_groups WHERE id = ? AND class_id = ?", (id, class_id))
        return Empty()

# --- Участники подгрупп ---

@router.post("/v1/courses/{courseId}/studentGroups/{studentGroupId}/studentGroupMembers")
def add_student_group_member(courseId: str, studentGroupId: str, req: StudentGroupMember, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ROSTERS,))

        class_id = resolve_class_id(conn, courseId, client_id=ctx.client_id)
        caller_role = get_course_role(conn, class_id, ctx.user)
        if caller_role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Управление подгруппами доступно только преподавателям")

        grp = conn.execute("SELECT 1 FROM student_groups WHERE id = ? AND class_id = ?", (studentGroupId, class_id)).fetchone()
        if not grp:
            api_error(404, "NOT_FOUND", "Подгруппа не найдена")

        target_id = resolve_user_id(conn, req.userId or "me", ctx.user)
        is_active = conn.execute(
            "SELECT 1 FROM class_members WHERE class_id = ? AND student_id = ? AND enrollment_active = 1",
            (class_id, target_id)
        ).fetchone()
        if not is_active:
            api_error(400, "FAILED_PRECONDITION", "Пользователь не является активным учеником курса", reason="UserNotCourseStudent")

        conn.execute(
            """INSERT INTO student_group_members (group_id, class_id, student_id)
               VALUES (?, ?, ?)
               ON CONFLICT(group_id, student_id) DO NOTHING""",
            (studentGroupId, class_id, target_id)
        )
        return StudentGroupMember(studentGroupId=str(studentGroupId), userId=str(target_id), courseId=str(class_id))

@router.get("/v1/courses/{courseId}/studentGroups/{studentGroupId}/studentGroupMembers")
def list_student_group_members(
    courseId: str,
    studentGroupId: str,
    request: Request,
    pageSize: int = Query(100, ge=1, le=100),
    pageToken: Optional[str] = Query(None)
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ROSTERS, SCOPE_ROSTERS_READONLY))

        class_id = resolve_class_id(conn, courseId, client_id=ctx.client_id)
        assert_course_access(conn, class_id, ctx.user)

        grp = conn.execute("SELECT 1 FROM student_groups WHERE id = ? AND class_id = ?", (studentGroupId, class_id)).fetchone()
        if not grp:
            api_error(404, "NOT_FOUND", "Подгруппа не найдена")

        fingerprint = f"sgm:{studentGroupId}"
        offset = decode_page_token(pageToken, fingerprint)

        rows = conn.execute(
            "SELECT student_id FROM student_group_members WHERE group_id = ? AND class_id = ? ORDER BY student_id ASC LIMIT ? OFFSET ?",
            (studentGroupId, class_id, pageSize + 1, offset)
        ).fetchall()

        has_next = len(rows) > pageSize
        items = rows[:pageSize]
        members = [
            StudentGroupMember(studentGroupId=str(studentGroupId), userId=str(r["student_id"]), courseId=str(class_id))
            for r in items
        ]
        next_token = encode_page_token(offset + pageSize, fingerprint) if has_next else None

        return ListStudentGroupMembersResponse(
            studentGroupMembers=members if members else None,
            nextPageToken=next_token
        )

@router.delete("/v1/courses/{courseId}/studentGroups/{studentGroupId}/studentGroupMembers/{userId}")
def delete_student_group_member(courseId: str, studentGroupId: str, userId: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ROSTERS,))

        class_id = resolve_class_id(conn, courseId, client_id=ctx.client_id)
        caller_role = get_course_role(conn, class_id, ctx.user)
        if caller_role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Управление подгруппами доступно только преподавателям")

        target_id = resolve_user_id(conn, userId, ctx.user)
        conn.execute(
            "DELETE FROM student_group_members WHERE group_id = ? AND class_id = ? AND student_id = ?",
            (studentGroupId, class_id, target_id)
        )
        return Empty()
