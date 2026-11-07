import json
import time
from typing import Optional, List, Any
from fastapi import APIRouter, Request, HTTPException, status
from pydantic import BaseModel, Field

from app.db import db_session
from app.passport.middleware import require_user, require_teacher
from app.classroom.sse_hub import sse_hub
from app.passport.pii_guard import assert_zero_pii_text, assert_e2ee_text, is_e2ee_envelope

router = APIRouter(prefix="/api/classroom", tags=["coursework"])

# -----------------------------------------------------------------------------
# Pydantic-схемы (Zero-PII)
# -----------------------------------------------------------------------------

class TopicCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=2000)
    frp_topic_id: Optional[str] = Field(default=None, max_length=64)
    sort_order: int = Field(default=0)

class CourseworkCreateRequest(BaseModel):
    topic_id: Optional[int] = None
    kind: str = Field(default="assignment", pattern="^(announcement|assignment|quiz|question|material)$")
    title: str = Field(min_length=1, max_length=2000)
    instructions: str = Field(default="")
    attachments_json: str = Field(default="[]")
    rubric_json: str = Field(default="[]")
    target_students: str = Field(default="all")
    max_points: int = Field(default=5, ge=0, le=1000)
    recess_reward: int = Field(default=300, ge=0, le=3600)
    is_homework: int = Field(default=0, ge=0, le=1)
    state: str = Field(default="published", pattern="^(draft|scheduled|published)$")
    scheduled_at: Optional[int] = None
    due_at: Optional[int] = None
    extra_class_ids: Optional[List[int]] = None
    work_type: Optional[str] = None
    peer_replies_enabled: Optional[int] = None
    choices_json: Optional[str] = None
    close_after_due: Optional[int] = None

class CourseworkUpdateRequest(BaseModel):
    topic_id: Optional[int] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    instructions: Optional[str] = None
    attachments_json: Optional[str] = None
    rubric_json: Optional[str] = None
    target_students: Optional[str] = None
    max_points: Optional[int] = Field(default=None, ge=0, le=1000)
    recess_reward: Optional[int] = Field(default=None, ge=0, le=3600)
    is_homework: Optional[int] = Field(default=None, ge=0, le=1)
    state: Optional[str] = Field(default=None, pattern="^(draft|scheduled|published)$")
    scheduled_at: Optional[int] = None
    due_at: Optional[int] = None
    work_type: Optional[str] = None
    peer_replies_enabled: Optional[int] = None
    choices_json: Optional[str] = None
    close_after_due: Optional[int] = None

class ReusePostRequest(BaseModel):
    target_class_id: int
    is_homework: Optional[int] = None
    due_at: Optional[int] = None

class AssignGroupsRequest(BaseModel):
    coursework_id: int
    group_ids: List[int]

# -----------------------------------------------------------------------------
# Роуты тем (Topics)
# -----------------------------------------------------------------------------

@router.get("/classes/{class_id}/topics")
def list_topics(class_id: int, request: Request):
    require_user(request)
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM class_topics WHERE class_id = ? ORDER BY sort_order ASC, id ASC",
            (class_id,)
        ).fetchall()
        return [dict(r) for r in rows]

@router.post("/classes/{class_id}/topics")
def create_topic(class_id: int, req: TopicCreateRequest, request: Request):
    user = require_teacher(request)
    assert_e2ee_text(req.title, "Название темы")
    with db_session() as conn:
        class_row = conn.execute("SELECT teacher_id FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not class_row or (class_row["teacher_id"] != user["user_id"] and user["role"] != "admin"):
            raise HTTPException(status_code=403, detail="Нет прав на добавление тем")

        cursor = conn.execute("""
            INSERT INTO class_topics (class_id, title, frp_topic_id, sort_order)
            VALUES (?, ?, ?, ?)
        """, (class_id, req.title.strip(), req.frp_topic_id, req.sort_order))

        topic_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM class_topics WHERE id = ?", (topic_id,)).fetchone()
        return dict(row)

@router.delete("/classes/{class_id}/topics/{topic_id}")
def delete_topic(class_id: int, topic_id: int, request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        class_row = conn.execute("SELECT teacher_id FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not class_row or (class_row["teacher_id"] != user["user_id"] and user["role"] != "admin"):
            raise HTTPException(status_code=403, detail="Нет прав на удаление темы")

        conn.execute("UPDATE coursework SET topic_id = NULL WHERE topic_id = ?", (topic_id,))
        conn.execute("DELETE FROM class_topics WHERE id = ? AND class_id = ?", (topic_id, class_id))
        return {"ok": True}

# -----------------------------------------------------------------------------
# Роуты заданий и ленты (Coursework)
# -----------------------------------------------------------------------------

def _populate_submissions_for_coursework(conn, coursework_id: int, class_id: int, target_students: str):
    now = int(time.time())
    if target_students == "all":
        students = conn.execute("SELECT student_id FROM class_members WHERE class_id = ? AND enrollment_active = 1", (class_id,)).fetchall()
        student_ids = [s["student_id"] for s in students]
    else:
        try:
            student_ids = json.loads(target_students)
        except Exception:
            student_ids = []

    for sid in student_ids:
        conn.execute("""
            INSERT OR IGNORE INTO submissions (coursework_id, student_id, status, v1_state, created_at, updated_at)
            VALUES (?, ?, 'assigned', 'NEW', ?, ?)
        """, (coursework_id, sid, now, now))

@router.get("/classes/{class_id}/coursework")
def list_coursework(class_id: int, request: Request):
    user = require_user(request)
    user_id = user["user_id"]
    is_teacher = user["role"] in ("teacher", "admin")

    with db_session() as conn:
        if is_teacher:
            rows = conn.execute("""
                SELECT cw.*, ct.title as topic_title,
                       (SELECT COUNT(*) FROM submissions s WHERE s.coursework_id = cw.id) as assigned_count,
                       (SELECT COUNT(*) FROM submissions s WHERE s.coursework_id = cw.id AND s.status = 'turned_in') as turned_in_count,
                       (SELECT COUNT(*) FROM submissions s WHERE s.coursework_id = cw.id AND s.status = 'returned') as graded_count
                FROM coursework cw
                LEFT JOIN class_topics ct ON cw.topic_id = ct.id
                WHERE cw.class_id = ?
                ORDER BY cw.created_at DESC
            """, (class_id,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT cw.*, ct.title as topic_title,
                       sub.status as my_status, sub.grade_five as my_grade_five, sub.grade_points as my_grade_points
                FROM coursework cw
                LEFT JOIN class_topics ct ON cw.topic_id = ct.id
                LEFT JOIN submissions sub ON cw.id = sub.coursework_id AND sub.student_id = ?
                WHERE cw.class_id = ? AND cw.state = 'published'
                ORDER BY cw.created_at DESC
            """, (user_id, class_id)).fetchall()

        return [dict(r) for r in rows]

@router.post("/classes/{class_id}/coursework")
def create_coursework(class_id: int, req: CourseworkCreateRequest, request: Request):
    user = require_teacher(request)
    now = int(time.time())

    assert_zero_pii_text(req.title)
    if req.instructions:
        assert_zero_pii_text(req.instructions)
    assert_e2ee_text(req.title, "Название задания")
    if req.instructions:
        assert_e2ee_text(req.instructions, "Инструкции", allow_empty=True)

    with db_session() as conn:
        class_row = conn.execute("SELECT teacher_id, grade_level FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not class_row or (class_row["teacher_id"] != user["user_id"] and user["role"] != "admin"):
            raise HTTPException(status_code=403, detail="Нет прав на создание заданий в данном классе")

        # АРХИТЕКТУРНЫЙ ИНВАРИАНТ: запрет ДЗ для 1-го класса (СанПиН / Минпросвещения РФ)
        if class_row["grade_level"] == 1 and req.is_homework == 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Для 1-го класса домашние задания запрещены нормами СанПиН и Минпросвещения РФ"
            )

        classes_to_publish = [class_id]
        if req.extra_class_ids:
            for extra_id in req.extra_class_ids:
                if extra_id != class_id:
                    extra_row = conn.execute("SELECT teacher_id, grade_level FROM classes WHERE id = ?", (extra_id,)).fetchone()
                    if extra_row and (extra_row["teacher_id"] == user["user_id"] or user["role"] == "admin"):
                        if extra_row["grade_level"] == 1 and req.is_homework == 1:
                            continue  # Пропускаем ДЗ для 1 класса
                        classes_to_publish.append(extra_id)

        created_items = []
        wtype = req.work_type or ("MULTIPLE_CHOICE_QUESTION" if req.choices_json and req.choices_json != "[]" else "ASSIGNMENT")
        peer_replies = req.peer_replies_enabled if req.peer_replies_enabled is not None else 0
        close_after = req.close_after_due if req.close_after_due is not None else 0
        choices = req.choices_json or "[]"

        for cid in classes_to_publish:
            topic_for_class = req.topic_id if cid == class_id else None
            cursor = conn.execute("""
                INSERT INTO coursework (
                    class_id, topic_id, kind, title, instructions,
                    attachments_json, rubric_json, target_students, max_points,
                    recess_reward, is_homework, state, scheduled_at, due_at,
                    work_type, peer_replies_enabled, close_after_due, choices_json,
                    creator_user_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cid, topic_for_class, req.kind, req.title.strip(), req.instructions.strip(),
                req.attachments_json, req.rubric_json, req.target_students, req.max_points,
                req.recess_reward, req.is_homework, req.state, req.scheduled_at, req.due_at,
                wtype, peer_replies, close_after, choices,
                user["user_id"], now, now
            ))

            cw_id = cursor.lastrowid
            if req.state == "published" and req.kind in ("assignment", "quiz", "question"):
                _populate_submissions_for_coursework(conn, cw_id, cid, req.target_students)

            sse_hub.notify_class(cid, "coursework_created", {"coursework_id": cw_id, "title": req.title})
            cw_row = conn.execute("SELECT * FROM coursework WHERE id = ?", (cw_id,)).fetchone()
            created_items.append(dict(cw_row))

        return created_items[0] if len(created_items) == 1 else created_items

@router.post("/classes/{class_id}/coursework/{coursework_id}/reuse")
def reuse_coursework(class_id: int, coursework_id: int, req: ReusePostRequest, request: Request):
    user = require_teacher(request)
    now = int(time.time())

    with db_session() as conn:
        source_cw = conn.execute("SELECT * FROM coursework WHERE id = ?", (coursework_id,)).fetchone()
        if not source_cw:
            raise HTTPException(status_code=404, detail="Исходное задание не найдено")

        target_class = conn.execute("SELECT teacher_id, grade_level FROM classes WHERE id = ?", (req.target_class_id,)).fetchone()
        if not target_class or (target_class["teacher_id"] != user["user_id"] and user["role"] != "admin"):
            raise HTTPException(status_code=403, detail="Нет прав на публикацию в целевой класс")

        is_homework = req.is_homework if req.is_homework is not None else source_cw["is_homework"]
        if target_class["grade_level"] == 1 and is_homework == 1:
            raise HTTPException(status_code=400, detail="Для 1-го класса домашние задания запрещены")

        due_at = req.due_at if req.due_at is not None else source_cw["due_at"]

        cursor = conn.execute("""
            INSERT INTO coursework (
                class_id, topic_id, kind, title, instructions,
                attachments_json, rubric_json, target_students, max_points,
                recess_reward, is_homework, state, due_at,
                work_type, peer_replies_enabled, close_after_due, choices_json,
                creator_user_id, created_at, updated_at
            ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'published', ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            req.target_class_id, source_cw["kind"], source_cw["title"], source_cw["instructions"],
            source_cw["attachments_json"], source_cw["rubric_json"], source_cw["target_students"],
            source_cw["max_points"], source_cw["recess_reward"], is_homework, due_at,
            source_cw.get("work_type") or "ASSIGNMENT",
            source_cw.get("peer_replies_enabled") or 0,
            source_cw.get("close_after_due") or 0,
            source_cw.get("choices_json") or "[]",
            user["user_id"], now, now
        ))

        new_id = cursor.lastrowid
        if source_cw["kind"] in ("assignment", "quiz", "question"):
            _populate_submissions_for_coursework(conn, new_id, req.target_class_id, source_cw["target_students"])

        sse_hub.notify_class(req.target_class_id, "coursework_created", {"coursework_id": new_id, "title": source_cw["title"]})
        row = conn.execute("SELECT * FROM coursework WHERE id = ?", (new_id,)).fetchone()
        return dict(row)

@router.get("/coursework/{coursework_id}")
def get_coursework(coursework_id: int, request: Request):
    user = require_user(request)
    with db_session() as conn:
        row = conn.execute("""
            SELECT cw.*, c.title as class_title, c.grade_level, c.teacher_id
            FROM coursework cw
            JOIN classes c ON cw.class_id = c.id
            WHERE cw.id = ?
        """, (coursework_id,)).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Задание не найдено")

        return dict(row)

@router.patch("/coursework/{coursework_id}")
def update_coursework(coursework_id: int, req: CourseworkUpdateRequest, request: Request):
    user = require_teacher(request)
    now = int(time.time())
    with db_session() as conn:
        cw_row = conn.execute("""
            SELECT cw.*, c.teacher_id, c.grade_level
            FROM coursework cw
            JOIN classes c ON cw.class_id = c.id
            WHERE cw.id = ?
        """, (coursework_id,)).fetchone()

        if not cw_row or (cw_row["teacher_id"] != user["user_id"] and user["role"] != "admin"):
            raise HTTPException(status_code=403, detail="Нет прав на редактирование задания")

        if req.is_homework == 1 and cw_row["grade_level"] == 1:
            raise HTTPException(status_code=400, detail="Для 1-го класса домашние задания запрещены")

        if req.title:
            assert_e2ee_text(req.title, "Название задания")
        if req.instructions:
            assert_e2ee_text(req.instructions, "Инструкции", allow_empty=True)

        updates = ["updated_at = ?"]
        params = [now]
        for field in ("topic_id", "title", "instructions", "attachments_json", "rubric_json",
                      "target_students", "max_points", "recess_reward", "is_homework", "state", "scheduled_at", "due_at",
                      "work_type", "peer_replies_enabled", "choices_json", "close_after_due"):
            val = getattr(req, field, None)
            if val is not None:
                updates.append(f"{field} = ?")
                params.append(val)

        params.append(coursework_id)
        conn.execute(f"UPDATE coursework SET {', '.join(updates)} WHERE id = ?", params)

        sse_hub.notify_class(cw_row["class_id"], "coursework_updated", {"coursework_id": coursework_id})
        updated = conn.execute("SELECT * FROM coursework WHERE id = ?", (coursework_id,)).fetchone()
        return dict(updated)

@router.delete("/coursework/{coursework_id}")
def delete_coursework(coursework_id: int, request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        cw_row = conn.execute("""
            SELECT cw.class_id, c.teacher_id
            FROM coursework cw
            JOIN classes c ON cw.class_id = c.id
            WHERE cw.id = ?
        """, (coursework_id,)).fetchone()

        if not cw_row or (cw_row["teacher_id"] != user["user_id"] and user["role"] != "admin"):
            raise HTTPException(status_code=403, detail="Нет прав на удаление задания")

        conn.execute("DELETE FROM coursework WHERE id = ?", (coursework_id,))
        sse_hub.notify_class(cw_row["class_id"], "coursework_deleted", {"coursework_id": coursework_id})
        return {"ok": True}

# -----------------------------------------------------------------------------
# Расширения Пакета 7 (Подгруппы и Ответы одноклассников)
# -----------------------------------------------------------------------------

@router.post("/classes/{class_id}/coursework/assign-groups")
def assign_coursework_to_groups(class_id: int, req: AssignGroupsRequest, request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        class_row = conn.execute("SELECT teacher_id FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not class_row or (class_row["teacher_id"] != user["user_id"] and user["role"] != "admin"):
            raise HTTPException(status_code=403, detail="Нет прав на редактирование заданий в данном классе")

        if not req.group_ids:
            raise HTTPException(status_code=400, detail="Список групп не может быть пустым")

        placeholders = ",".join("?" for _ in req.group_ids)
        rows = conn.execute(
            f"SELECT DISTINCT student_id FROM student_group_members WHERE class_id = ? AND group_id IN ({placeholders})",
            [class_id, *req.group_ids]
        ).fetchall()

        student_ids = [r["student_id"] for r in rows]
        target_students_val = json.dumps(student_ids)
        now = int(time.time())

        conn.execute("""
            UPDATE coursework
            SET assignee_mode = 'INDIVIDUAL_STUDENTS', target_students = ?, updated_at = ?
            WHERE id = ? AND class_id = ?
        """, (target_students_val, now, req.coursework_id, class_id))

        # Если задание опубликовано, сразу создаем сдачи для этих учеников
        cw_row = conn.execute("SELECT state FROM coursework WHERE id = ?", (req.coursework_id,)).fetchone()
        if cw_row and cw_row["state"] == "published":
            _populate_submissions_for_coursework(conn, req.coursework_id, class_id, target_students_val)

        return {"ok": True, "student_ids": student_ids}
