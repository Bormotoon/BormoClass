import re
import time
from typing import Optional, List, Any

from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field

from app.db import db_session
from app.v1.rbac import resolve_auth_context, get_course_role
from app.v1.protocol import api_error
from app.classroom.sse_hub import sse_hub

router = APIRouter(tags=["comments"])

# -----------------------------------------------------------------------------
# Публичные комментарии класса (class_comments)
# -----------------------------------------------------------------------------

class ClassCommentCreateRequest(BaseModel):
    parent_kind: str = Field(pattern="^(announcement|coursework|material)$")
    parent_id: int
    body_text: str = Field(min_length=1, max_length=2000)
    reply_to_id: Optional[int] = None

class ClassCommentUpdateRequest(BaseModel):
    body_text: str = Field(min_length=1, max_length=2000)

@router.get("/api/classroom/classes/{class_id}/comments")
def get_class_comments(
    class_id: int,
    parent_kind: str,
    parent_id: int,
    request: Request
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        role = get_course_role(conn, class_id, ctx.user)
        if not role:
            api_error(403, "PERMISSION_DENIED", "Нет доступа к комментариям курса")

        course = conn.execute("SELECT show_deleted_items FROM classes WHERE id = ?", (class_id,)).fetchone()
        show_deleted = bool(course and course["show_deleted_items"] == 1 and role in ("OWNER", "TEACHER", "ADMIN"))

        rows = conn.execute("""
            SELECT cc.*, u.handle AS author_handle, u.avatar_seed AS author_avatar_seed
            FROM class_comments cc
            JOIN users u ON cc.author_user_id = u.id
            WHERE cc.class_id = ? AND cc.parent_kind = ? AND cc.parent_id = ?
            ORDER BY cc.created_at ASC
        """, (class_id, parent_kind, parent_id)).fetchall()

        results = []
        for r in rows:
            d = dict(r)
            if d["is_deleted"] == 1:
                if show_deleted:
                    d["body_text"] = "[Удалено модератором]"
                    results.append(d)
            else:
                results.append(d)

        return results

@router.post("/api/classroom/classes/{class_id}/comments")
def create_class_comment(
    class_id: int,
    req: ClassCommentCreateRequest,
    request: Request
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        role = get_course_role(conn, class_id, ctx.user)
        if not role:
            api_error(403, "PERMISSION_DENIED", "Нет доступа к курсу")

        # Проверка настроек постинга для учеников
        if role == "STUDENT":
            course = conn.execute("SELECT stream_post_mode FROM classes WHERE id = ?", (class_id,)).fetchone()
            if course and course["stream_post_mode"] == "ONLY_TEACHERS_CAN_POST_OR_COMMENT":
                api_error(403, "PERMISSION_DENIED", "Комментарии отключены учителем")

            member = conn.execute(
                "SELECT is_muted FROM class_members WHERE class_id = ? AND student_id = ?",
                (class_id, ctx.user["id"])
            ).fetchone()
            if member and member["is_muted"] == 1:
                api_error(403, "PERMISSION_DENIED", "Вам запрещено оставлять комментарии")

        now = int(time.time())
        cursor = conn.execute("""
            INSERT INTO class_comments (
                class_id, parent_kind, parent_id, reply_to_id,
                author_user_id, body_text, is_deleted, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
        """, (
            class_id, req.parent_kind, req.parent_id, req.reply_to_id,
            ctx.user["id"], req.body_text, now, now
        ))

        comment_id = cursor.lastrowid

        # Парсер упоминаний @handle
        mentioned_handles = set(re.findall(r'@([\w\-]+)', req.body_text))
        if mentioned_handles:
            for handle in mentioned_handles:
                target_user = conn.execute("""
                    SELECT u.id FROM users u
                    JOIN class_members cm ON cm.student_id = u.id
                    WHERE u.handle = ? AND cm.class_id = ?
                    UNION
                    SELECT u.id FROM users u
                    JOIN course_teachers ct ON ct.teacher_id = u.id
                    WHERE u.handle = ? AND ct.class_id = ?
                """, (handle, class_id, handle, class_id)).fetchone()

                if target_user and target_user["id"] != ctx.user["id"]:
                    conn.execute("""
                        INSERT INTO notifications (user_id, class_id, notif_kind, title, body_text, link_path, created_at)
                        VALUES (?, ?, 'MENTION', ?, ?, ?, ?)
                    """, (
                        target_user["id"], class_id,
                        f"Упоминание от @{ctx.user['handle']}",
                        req.body_text[:120],
                        f"/board/{class_id}",
                        now
                    ))

        new_row = conn.execute("""
            SELECT cc.*, u.handle AS author_handle, u.avatar_seed AS author_avatar_seed
            FROM class_comments cc
            JOIN users u ON cc.author_user_id = u.id
            WHERE cc.id = ?
        """, (comment_id,)).fetchone()

        result = dict(new_row)
        sse_hub.notify_class(class_id, "new_comment", result)
        return result

@router.patch("/api/classroom/classes/{class_id}/comments/{id}")
def update_class_comment(
    class_id: int,
    id: int,
    req: ClassCommentUpdateRequest,
    request: Request
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        row = conn.execute("SELECT * FROM class_comments WHERE id = ? AND class_id = ?", (id, class_id)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Комментарий не найден")

        if row["author_user_id"] != ctx.user["id"] and ctx.user.get("role") != "admin":
            api_error(403, "PERMISSION_DENIED", "Редактировать комментарий может только его автор")

        now = int(time.time())
        conn.execute("UPDATE class_comments SET body_text = ?, updated_at = ? WHERE id = ?", (req.body_text, now, id))
        return {"ok": True, "id": id, "body_text": req.body_text, "updated_at": now}

@router.delete("/api/classroom/classes/{class_id}/comments/{id}")
def delete_class_comment(
    class_id: int,
    id: int,
    request: Request
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        role = get_course_role(conn, class_id, ctx.user)
        row = conn.execute("SELECT * FROM class_comments WHERE id = ? AND class_id = ?", (id, class_id)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Комментарий не найден")

        # Автор или учитель курса могут удалить комментарий
        is_author = row["author_user_id"] == ctx.user["id"]
        is_teacher = role in ("OWNER", "TEACHER", "ADMIN")
        if not is_author and not is_teacher:
            api_error(403, "PERMISSION_DENIED", "Нет прав на удаление комментария")

        now = int(time.time())
        conn.execute("UPDATE class_comments SET is_deleted = 1, updated_at = ? WHERE id = ?", (now, id))
        sse_hub.notify_class(class_id, "comment_deleted", {"id": id})
        return {"ok": True, "id": id, "is_deleted": True}

# -----------------------------------------------------------------------------
# Приватные комментарии (private_comments)
# -----------------------------------------------------------------------------

class PrivateCommentCreateRequest(BaseModel):
    body_text: str = Field(min_length=1, max_length=2000)

@router.get("/api/classroom/coursework/{cw_id}/submissions/{student_id}/private-comments")
def get_private_comments(
    cw_id: int,
    student_id: int,
    request: Request
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)

        cw = conn.execute("SELECT class_id FROM coursework WHERE id = ?", (cw_id,)).fetchone()
        if not cw:
            api_error(404, "NOT_FOUND", "Задание не найдено")

        class_id = cw["class_id"]
        role = get_course_role(conn, class_id, ctx.user)

        # Строгая изоляция: только сам ученик и учителя курса
        if ctx.user["id"] != student_id and role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Доступ к приватным комментариям запрещен")

        rows = conn.execute("""
            SELECT pc.*, u.handle AS author_handle, u.avatar_seed AS author_avatar_seed
            FROM private_comments pc
            JOIN users u ON pc.author_user_id = u.id
            WHERE pc.coursework_id = ? AND pc.student_id = ?
            ORDER BY pc.created_at ASC
        """, (cw_id, student_id)).fetchall()

        return [dict(r) for r in rows]

@router.post("/api/classroom/coursework/{cw_id}/submissions/{student_id}/private-comments")
def create_private_comment(
    cw_id: int,
    student_id: int,
    req: PrivateCommentCreateRequest,
    request: Request
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)

        cw = conn.execute("SELECT class_id FROM coursework WHERE id = ?", (cw_id,)).fetchone()
        if not cw:
            api_error(404, "NOT_FOUND", "Задание не найдено")

        class_id = cw["class_id"]
        role = get_course_role(conn, class_id, ctx.user)

        # Строгая изоляция 1-на-1
        if ctx.user["id"] != student_id and role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Доступ к приватным комментариям запрещен")

        now = int(time.time())
        cursor = conn.execute("""
            INSERT INTO private_comments (coursework_id, student_id, author_user_id, body_text, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (cw_id, student_id, ctx.user["id"], req.body_text, now))

        comment_id = cursor.lastrowid

        # Уведомление адресату
        if ctx.user["id"] == student_id:
            # Написал ученик -> уведомить учителей
            teachers = conn.execute("""
                SELECT teacher_id FROM course_teachers WHERE class_id = ?
                UNION
                SELECT teacher_id FROM classes WHERE id = ?
            """, (class_id, class_id)).fetchall()
            for t in teachers:
                conn.execute("""
                    INSERT INTO notifications (user_id, class_id, notif_kind, title, body_text, link_path, created_at)
                    VALUES (?, ?, 'PRIVATE_COMMENT', 'Личный комментарий к сдаче', ?, ?, ?)
                """, (t[0], class_id, req.body_text[:120], f"/board/{class_id}", now))
        else:
            # Написал учитель -> уведомить ученика
            conn.execute("""
                INSERT INTO notifications (user_id, class_id, notif_kind, title, body_text, link_path, created_at)
                VALUES (?, ?, 'PRIVATE_COMMENT', 'Личный комментарий от учителя', ?, ?, ?)
            """, (student_id, class_id, req.body_text[:120], f"/board/{class_id}", now))

        new_row = conn.execute("""
            SELECT pc.*, u.handle AS author_handle, u.avatar_seed AS author_avatar_seed
            FROM private_comments pc
            JOIN users u ON pc.author_user_id = u.id
            WHERE pc.id = ?
        """, (comment_id,)).fetchone()

        result = dict(new_row)
        sse_hub.notify_class(class_id, "private_comment", result)
        return result

# -----------------------------------------------------------------------------
# Банк комментариев учителя (comment_bank)
# -----------------------------------------------------------------------------

class CommentBankCreateRequest(BaseModel):
    comment_text: str = Field(min_length=1, max_length=2000)

@router.get("/api/classroom/comment-bank")
def search_comment_bank(request: Request, q: Optional[str] = None):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        user_id = ctx.user["id"]

        query = "SELECT * FROM comment_bank WHERE teacher_id = ?"
        params = [user_id]

        if q:
            clean_q = q.strip()
            if clean_q.startswith("#"):
                # Автодополнение по #хештегам
                query += " AND comment_text LIKE ?"
                params.append(f"%{clean_q}%")
            else:
                # Поиск по подстроке
                query += " AND comment_text LIKE ?"
                params.append(f"%{clean_q}%")

        query += " ORDER BY id DESC LIMIT 50"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

@router.post("/api/classroom/comment-bank")
def add_to_comment_bank(req: CommentBankCreateRequest, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        cursor = conn.execute(
            "INSERT INTO comment_bank (teacher_id, comment_text) VALUES (?, ?)",
            (ctx.user["id"], req.comment_text.strip())
        )
        return {"id": cursor.lastrowid, "teacher_id": ctx.user["id"], "comment_text": req.comment_text.strip()}

@router.delete("/api/classroom/comment-bank/{id}")
def delete_from_comment_bank(id: int, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        conn.execute("DELETE FROM comment_bank WHERE id = ? AND teacher_id = ?", (id, ctx.user["id"]))
        return {"ok": True, "id": id}
