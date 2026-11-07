import json
import time
import hashlib
from dataclasses import dataclass
from typing import Optional, Set, Tuple
from fastapi import Request
from app.config import settings
from app.passport.crypto_cookie import verify_cookie_token
from app.v1.protocol import api_error

# Внутренние OAuth 2.0 скоупы BormoClass (100% автономность, Zero-Google)
SCOPE_COURSES = "bormoclass:courses"
SCOPE_COURSES_READONLY = "bormoclass:courses.readonly"
SCOPE_ROSTERS = "bormoclass:rosters"
SCOPE_ROSTERS_READONLY = "bormoclass:rosters.readonly"
SCOPE_PROFILE_EMAILS = "bormoclass:profile.emails"
SCOPE_PROFILE_PHOTOS = "bormoclass:profile.photos"
SCOPE_COURSEWORK_STUDENTS = "bormoclass:coursework.students"
SCOPE_COURSEWORK_STUDENTS_READONLY = "bormoclass:coursework.students.readonly"
SCOPE_COURSEWORK_ME = "bormoclass:coursework.me"
SCOPE_COURSEWORK_ME_READONLY = "bormoclass:coursework.me.readonly"
SCOPE_COURSEWORKMATERIALS = "bormoclass:courseworkmaterials"
SCOPE_COURSEWORKMATERIALS_READONLY = "bormoclass:courseworkmaterials.readonly"
SCOPE_ANNOUNCEMENTS = "bormoclass:announcements"
SCOPE_ANNOUNCEMENTS_READONLY = "bormoclass:announcements.readonly"
SCOPE_TOPICS = "bormoclass:topics"
SCOPE_TOPICS_READONLY = "bormoclass:topics.readonly"
SCOPE_GUARDIANLINKS_STUDENTS = "bormoclass:guardianlinks.students"
SCOPE_GUARDIANLINKS_STUDENTS_READONLY = "bormoclass:guardianlinks.students.readonly"
SCOPE_GUARDIANLINKS_ME_READONLY = "bormoclass:guardianlinks.me.readonly"
SCOPE_PUSH_NOTIFICATIONS = "bormoclass:push-notifications"
SCOPE_SUBMISSIONS_STUDENTS_READONLY = "bormoclass:student-submissions.students.readonly"
SCOPE_SUBMISSIONS_ME_READONLY = "bormoclass:student-submissions.me.readonly"
SCOPE_ADDONS_TEACHER = "bormoclass:addons.teacher"
SCOPE_ADDONS_STUDENT = "bormoclass:addons.student"

ALL_24_SCOPES: Set[str] = {
    SCOPE_COURSES, SCOPE_COURSES_READONLY,
    SCOPE_ROSTERS, SCOPE_ROSTERS_READONLY,
    SCOPE_PROFILE_EMAILS, SCOPE_PROFILE_PHOTOS,
    SCOPE_COURSEWORK_STUDENTS, SCOPE_COURSEWORK_STUDENTS_READONLY,
    SCOPE_COURSEWORK_ME, SCOPE_COURSEWORK_ME_READONLY,
    SCOPE_COURSEWORKMATERIALS, SCOPE_COURSEWORKMATERIALS_READONLY,
    SCOPE_ANNOUNCEMENTS, SCOPE_ANNOUNCEMENTS_READONLY,
    SCOPE_TOPICS, SCOPE_TOPICS_READONLY,
    SCOPE_GUARDIANLINKS_STUDENTS, SCOPE_GUARDIANLINKS_STUDENTS_READONLY, SCOPE_GUARDIANLINKS_ME_READONLY,
    SCOPE_PUSH_NOTIFICATIONS,
    SCOPE_SUBMISSIONS_STUDENTS_READONLY, SCOPE_SUBMISSIONS_ME_READONLY,
    SCOPE_ADDONS_TEACHER, SCOPE_ADDONS_STUDENT
}

# Маппинг: какой write-скоуп покрывает какой readonly-скоуп
SCOPE_IMPLICATIONS = {
    SCOPE_COURSES: {SCOPE_COURSES, SCOPE_COURSES_READONLY},
    SCOPE_ROSTERS: {SCOPE_ROSTERS, SCOPE_ROSTERS_READONLY},
    SCOPE_COURSEWORK_STUDENTS: {SCOPE_COURSEWORK_STUDENTS, SCOPE_COURSEWORK_STUDENTS_READONLY},
    SCOPE_COURSEWORK_ME: {SCOPE_COURSEWORK_ME, SCOPE_COURSEWORK_ME_READONLY},
    SCOPE_COURSEWORKMATERIALS: {SCOPE_COURSEWORKMATERIALS, SCOPE_COURSEWORKMATERIALS_READONLY},
    SCOPE_ANNOUNCEMENTS: {SCOPE_ANNOUNCEMENTS, SCOPE_ANNOUNCEMENTS_READONLY},
    SCOPE_TOPICS: {SCOPE_TOPICS, SCOPE_TOPICS_READONLY},
    SCOPE_GUARDIANLINKS_STUDENTS: {SCOPE_GUARDIANLINKS_STUDENTS, SCOPE_GUARDIANLINKS_STUDENTS_READONLY, SCOPE_GUARDIANLINKS_ME_READONLY},
    SCOPE_ADDONS_TEACHER: {SCOPE_ADDONS_TEACHER, SCOPE_ADDONS_STUDENT},
}

@dataclass
class AuthContext:
    user: dict
    client_id: str
    scopes: Set[str]
    is_first_party: bool

def resolve_auth_context(request: Request, conn) -> AuthContext:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        # 1. Поиск в oauth_tokens
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = int(time.time())
        token_row = conn.execute(
            "SELECT * FROM oauth_tokens WHERE token_hash = ? AND expires_at > ?",
            (token_hash, now)
        ).fetchone()
        if token_row:
            u_row = conn.execute("SELECT * FROM users WHERE id = ?", (token_row["user_id"],)).fetchone()
            if not u_row:
                api_error(401, "UNAUTHENTICATED", "Пользователь не найден")
            u_dict = dict(u_row)
            if u_dict.get("account_disabled") == 1:
                api_error(403, "PERMISSION_DENIED", "Аккаунт деактивирован администратором")
            scopes = set(json.loads(token_row["scopes_json"]))
            return AuthContext(user=u_dict, client_id=token_row["client_id"], scopes=scopes, is_first_party=False)

        # 2. Проверка cookie-токена в Bearer заголовке
        cookie_user = verify_cookie_token(token)
        if cookie_user:
            uid = cookie_user.get("id") or cookie_user.get("user_id")
            u_row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
            if not u_row:
                api_error(401, "UNAUTHENTICATED", "Пользователь не найден")
            u_dict = dict(u_row)
            if u_dict.get("account_disabled") == 1:
                api_error(403, "PERMISSION_DENIED", "Аккаунт деактивирован администратором")
            return AuthContext(user=u_dict, client_id="first_party", scopes=ALL_24_SCOPES, is_first_party=True)

        api_error(401, "UNAUTHENTICATED", "Недействительный OAuth-токен")

    # 3. Проверка штатной HttpOnly cookie pb_pass
    cookie_token = request.cookies.get(settings.COOKIE_NAME)
    cookie_user = verify_cookie_token(cookie_token)
    if cookie_user:
        uid = cookie_user.get("id") or cookie_user.get("user_id")
        u_row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if not u_row:
            api_error(401, "UNAUTHENTICATED", "Пользователь не найден")
        u_dict = dict(u_row)
        if u_dict.get("account_disabled") == 1:
            api_error(403, "PERMISSION_DENIED", "Аккаунт деактивирован администратором")
        return AuthContext(user=u_dict, client_id="first_party", scopes=ALL_24_SCOPES, is_first_party=True)

    api_error(401, "UNAUTHENTICATED", "Требуется авторизация")

def require_scopes(ctx: AuthContext, any_of: Tuple[str, ...]):
    effective_scopes = set()
    for s in ctx.scopes:
        effective_scopes.add(s)
        if s in SCOPE_IMPLICATIONS:
            effective_scopes.update(SCOPE_IMPLICATIONS[s])

    for required in any_of:
        if required in effective_scopes:
            return
    api_error(403, "PERMISSION_DENIED", "Недостаточно OAuth scopes", reason="ACCESS_TOKEN_SCOPE_INSUFFICIENT")

def get_course_role(conn, class_id: int, user: dict) -> Optional[str]:
    if user.get("role") == "admin":
        return "ADMIN"

    course = conn.execute("SELECT teacher_id FROM classes WHERE id = ?", (class_id,)).fetchone()
    if not course:
        return None

    if course["teacher_id"] == user["id"]:
        return "OWNER"

    teacher = conn.execute(
        "SELECT 1 FROM course_teachers WHERE class_id = ? AND teacher_id = ?",
        (class_id, user["id"])
    ).fetchone()
    if teacher:
        return "TEACHER"

    member = conn.execute(
        "SELECT 1 FROM class_members WHERE class_id = ? AND student_id = ? AND enrollment_active = 1",
        (class_id, user["id"])
    ).fetchone()
    if member:
        return "STUDENT"

    return None

def assert_course_access(conn, class_id: int, user: dict) -> str:
    role = get_course_role(conn, class_id, user)
    if not role:
        api_error(404, "NOT_FOUND", "Курс не найден или нет доступа")
    return role

def assert_course_modifiable(conn, class_id: int) -> None:
    row = conn.execute("SELECT course_state FROM classes WHERE id = ?", (class_id,)).fetchone()
    if not row:
        api_error(404, "NOT_FOUND", "Курс не найден")
    state = row["course_state"]
    if state == "ARCHIVED":
        api_error(400, "FAILED_PRECONDITION", "Курс заархивирован и недоступен для изменений", reason="CourseArchived")
    if state == "DECLINED":
        api_error(400, "FAILED_PRECONDITION", "Курс отклонен", reason="CourseDeclined")

def assert_developer_project_match(ctx: AuthContext, creator_client_id: str):
    if not ctx.is_first_party:
        if creator_client_id and creator_client_id != ctx.client_id:
            api_error(403, "PERMISSION_DENIED", "Объект создан другим приложением", reason="ProjectPermissionDenied")

def can_create_course(user: dict) -> bool:
    if user.get("role") == "admin":
        return True
    policy = settings.COURSE_CREATE_POLICY
    if policy == "ANY_USER":
        return True
    if policy == "ANY_TEACHER":
        return user.get("role") == "teacher"
    if policy == "VERIFIED_TEACHERS_ONLY":
        return user.get("role") == "teacher" and bool(user.get("verified_teacher", 0))
    if policy == "ADMINS_ONLY":
        return False
    return user.get("role") == "teacher"
