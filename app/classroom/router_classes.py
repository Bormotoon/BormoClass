import secrets
import time
import uuid
from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException, status, Query
from pydantic import BaseModel, Field

from app.db import db_session
from app.passport.middleware import require_user, require_teacher
from app.passport.generator import generate_recovery_words, hash_secret
from app.classroom.sse_hub import sse_hub

router = APIRouter(prefix="/api/classroom/classes", tags=["classes"])

# -----------------------------------------------------------------------------
# Pydantic-схемы (Zero-PII: 0 полей ПД)
# -----------------------------------------------------------------------------

class CreateClassRequest(BaseModel):
    title: str = Field(min_length=2, max_length=100)
    subject_code: str = Field(default="inf", max_length=32)
    grade_level: int = Field(default=8, ge=1, le=11)
    quarter_goal: str = Field(default="", max_length=250)

class UpdateClassRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=2, max_length=100)
    subject_code: Optional[str] = Field(default=None, max_length=32)
    grade_level: Optional[int] = Field(default=None, ge=1, le=11)
    quarter_goal: Optional[str] = Field(default=None, max_length=250)

class JoinClassRequest(BaseModel):
    join_pin: str = Field(min_length=4, max_length=10)
    seat_number: int = Field(ge=1, le=40)

class UpdateMemberRequest(BaseModel):
    is_present: Optional[int] = Field(default=None, ge=0, le=1)
    seat_number: Optional[int] = Field(default=None, ge=1, le=40)

class TrafficLightRequest(BaseModel):
    traffic_light: str = Field(pattern="^(green|yellow|red)$")

class LockRecessRequest(BaseModel):
    duration_minutes: int = Field(ge=0, le=360)  # 0 = снять блокировку

# -----------------------------------------------------------------------------
# Вспомогательные функции
# -----------------------------------------------------------------------------

def _generate_unique_pin(conn) -> str:
    for _ in range(50):
        pin = str(secrets.randbelow(90000) + 10000)  # 5-значный пин 10000..99999
        row = conn.execute("SELECT 1 FROM classes WHERE join_pin = ?", (pin,)).fetchone()
        if not row:
            return pin
    raise RuntimeError("Не удалось сгенерировать уникальный пин-код класса")

# -----------------------------------------------------------------------------
# Эндпоинты
# -----------------------------------------------------------------------------

@router.get("")
def list_classes(request: Request):
    user = require_user(request)
    user_id = user["user_id"]
    role = user["role"]

    with db_session() as conn:
        if role in ("teacher", "admin"):
            rows = conn.execute("""
                SELECT c.id, c.teacher_id, c.title, c.subject_code, c.grade_level, 
                       c.join_pin, c.quarter_goal, c.recess_locked_until, c.created_at,
                       (SELECT COUNT(*) FROM class_members cm WHERE cm.class_id = c.id) as students_count
                FROM classes c
                WHERE c.teacher_id = ?
                ORDER BY c.created_at DESC
            """, (user_id,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT c.id, c.teacher_id, c.title, c.subject_code, c.grade_level, 
                       c.join_pin, c.quarter_goal, c.recess_locked_until, c.created_at,
                       cm.seat_number, cm.traffic_light,
                       (SELECT COUNT(*) FROM class_members cm2 WHERE cm2.class_id = c.id) as students_count
                FROM classes c
                JOIN class_members cm ON c.id = cm.class_id
                WHERE cm.student_id = ?
                ORDER BY c.created_at DESC
            """, (user_id,)).fetchall()

        return [dict(r) for r in rows]

@router.post("")
def create_class(req: CreateClassRequest, request: Request):
    user = require_teacher(request)
    now = int(time.time())

    with db_session() as conn:
        pin = _generate_unique_pin(conn)
        cursor = conn.execute("""
            INSERT INTO classes (
                teacher_id, title, subject_code, grade_level, join_pin,
                quarter_goal, recess_locked_until, classroom_state_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 0, '{}', ?)
        """, (user["user_id"], req.title.strip(), req.subject_code.strip(), req.grade_level, pin, req.quarter_goal.strip(), now))

        class_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
        return dict(row)

@router.get("/{class_id}")
def get_class(class_id: int, request: Request):
    user = require_user(request)
    with db_session() as conn:
        row = conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Класс не найден")

        is_teacher = (user["role"] in ("teacher", "admin") and row["teacher_id"] == user["user_id"])
        member = conn.execute(
            "SELECT * FROM class_members WHERE class_id = ? AND student_id = ?",
            (class_id, user["user_id"])
        ).fetchone()

        if not is_teacher and not member:
            raise HTTPException(status_code=403, detail="Нет доступа к данному классу")

        result = dict(row)
        result["is_teacher"] = is_teacher
        result["my_membership"] = dict(member) if member else None
        return result

@router.patch("/{class_id}")
def update_class(class_id: int, req: UpdateClassRequest, request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        row = conn.execute("SELECT teacher_id FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Класс не найден")
        if row["teacher_id"] != user["user_id"] and user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Только владелец класса может изменять настройки")

        updates = []
        params = []
        if req.title is not None:
            updates.append("title = ?")
            params.append(req.title.strip())
        if req.subject_code is not None:
            updates.append("subject_code = ?")
            params.append(req.subject_code.strip())
        if req.grade_level is not None:
            updates.append("grade_level = ?")
            params.append(req.grade_level)
        if req.quarter_goal is not None:
            updates.append("quarter_goal = ?")
            params.append(req.quarter_goal.strip())

        if updates:
            params.append(class_id)
            conn.execute(f"UPDATE classes SET {', '.join(updates)} WHERE id = ?", params)

        updated_row = conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
        return dict(updated_row)

@router.delete("/{class_id}")
def delete_class(class_id: int, request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        row = conn.execute("SELECT teacher_id FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Класс не найден")
        if row["teacher_id"] != user["user_id"] and user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Только владелец класса может его удалить")

        conn.execute("DELETE FROM classes WHERE id = ?", (class_id,))
        return {"ok": True}

@router.post("/join")
def join_class(req: JoinClassRequest, request: Request):
    user = require_user(request)
    student_id = user["user_id"]
    now = int(time.time())

    with db_session() as conn:
        class_row = conn.execute(
            "SELECT id, title, grade_level FROM classes WHERE join_pin = ?",
            (req.join_pin.strip(),)
        ).fetchone()

        if not class_row:
            raise HTTPException(
                status_code=404,
                detail=f"Класс с кодом подключения «{req.join_pin.strip()}» не найден. Проверьте 5-значный пин-код на интерактивной доске учителя."
            )

        class_id = class_row["id"]

        # Проверяем, не занята ли парта другим учеником
        seat_taken = conn.execute(
            "SELECT student_id FROM class_members WHERE class_id = ? AND seat_number = ?",
            (class_id, req.seat_number)
        ).fetchone()

        if seat_taken and seat_taken["student_id"] != student_id:
            raise HTTPException(
                status_code=409,
                detail=f"Парта №{req.seat_number} уже занята другим учеником. Пожалуйста, выберите свободное место на схеме."
            )

        # Добавляем или обновляем парту ученика
        conn.execute("""
            INSERT INTO class_members (class_id, student_id, seat_number, is_present, traffic_light, joined_at)
            VALUES (?, ?, ?, 1, 'green', ?)
            ON CONFLICT(class_id, student_id) DO UPDATE SET
                seat_number = excluded.seat_number,
                is_present = 1
        """, (class_id, student_id, req.seat_number, now))

        # Назначаем все активные опубликованные задания класса новому ученику
        active_cw = conn.execute("""
            SELECT id FROM coursework 
            WHERE class_id = ? AND state = 'published' AND kind IN ('assignment', 'quiz', 'question')
        """, (class_id,)).fetchall()

        for cw in active_cw:
            conn.execute("""
                INSERT OR IGNORE INTO submissions (coursework_id, student_id, status, updated_at)
                VALUES (?, ?, 'assigned', ?)
            """, (cw["id"], student_id, now))

        # Оповещаем доску и поток класса о подключении парты
        sse_hub.notify_board(class_id, "seat_joined", {
            "seat_number": req.seat_number,
            "student_id": student_id,
            "handle": user["handle"]
        })
        sse_hub.notify_class(class_id, "seat_joined", {
            "seat_number": req.seat_number,
            "student_id": student_id
        })

        return {
            "ok": True,
            "class_id": class_id,
            "title": class_row["title"],
            "seat_number": req.seat_number
        }

@router.get("/{class_id}/members")
def get_class_members(class_id: int, request: Request):
    user = require_user(request)
    with db_session() as conn:
        class_row = conn.execute("SELECT teacher_id FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not class_row:
            raise HTTPException(status_code=404, detail="Класс не найден")

        is_teacher = (user["role"] in ("teacher", "admin") and class_row["teacher_id"] == user["user_id"])

        members = conn.execute("""
            SELECT cm.student_id, cm.seat_number, cm.is_present, 
                   cm.traffic_light, cm.joined_at, u.handle, u.avatar_seed
            FROM class_members cm
            JOIN users u ON cm.student_id = u.id
            WHERE cm.class_id = ?
            ORDER BY cm.seat_number ASC
        """, (class_id,)).fetchall()

        result = []
        for m in members:
            item = {
                "student_id": m["student_id"],
                "seat_number": m["seat_number"],
                "is_present": m["is_present"],
                "traffic_light": m["traffic_light"],
                "joined_at": m["joined_at"],
                "handle": m["handle"],
                "avatar_seed": m["avatar_seed"]
            }
            result.append(item)

        return result

@router.patch("/{class_id}/members/{student_id}")
def update_member(class_id: int, student_id: int, req: UpdateMemberRequest, request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        class_row = conn.execute("SELECT teacher_id FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not class_row or (class_row["teacher_id"] != user["user_id"] and user["role"] != "admin"):
            raise HTTPException(status_code=403, detail="Нет прав на управление составом класса")

        updates = []
        params = []
        if req.is_present is not None:
            updates.append("is_present = ?")
            params.append(req.is_present)
        if req.seat_number is not None:
            # Проверяем коллизию парты
            seat_taken = conn.execute(
                "SELECT student_id FROM class_members WHERE class_id = ? AND seat_number = ? AND student_id != ?",
                (class_id, req.seat_number, student_id)
            ).fetchone()
            if seat_taken:
                raise HTTPException(status_code=409, detail=f"Парта №{req.seat_number} уже занята")
            updates.append("seat_number = ?")
            params.append(req.seat_number)

        if updates:
            params.extend([class_id, student_id])
            conn.execute(f"UPDATE class_members SET {', '.join(updates)} WHERE class_id = ? AND student_id = ?", params)

        sse_hub.notify_class(class_id, "member_updated", {"student_id": student_id})
        return {"ok": True}

@router.post("/{class_id}/members/{student_id}/reset-password")
def reset_student_password(class_id: int, student_id: int, request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        class_row = conn.execute("SELECT teacher_id FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not class_row or (class_row["teacher_id"] != user["user_id"] and user["role"] != "admin"):
            raise HTTPException(status_code=403, detail="Нет прав на сброс пароля ученика")

        student = conn.execute("SELECT handle FROM users WHERE id = ?", (student_id,)).fetchone()
        if not student:
            raise HTTPException(status_code=404, detail="Ученик не найден")

        # Генерируем 4 новых секретных слова восстановления и временный пароль
        recovery_words = generate_recovery_words(4)
        recovery_text = " ".join(recovery_words)
        temp_password = f"{recovery_words[0]}{secrets.randbelow(900)+100}"
        
        pw_hash = hash_secret(temp_password)
        rec_hash = hash_secret(recovery_text)

        conn.execute("""
            UPDATE users 
            SET password_hash = ?, recovery_words_hash = ?
            WHERE id = ?
        """, (pw_hash, rec_hash, student_id))

        return {
            "ok": True,
            "handle": student["handle"],
            "temp_password": temp_password,
            "recovery_words": recovery_words
        }

@router.post("/{class_id}/traffic-light")
def set_traffic_light(class_id: int, req: TrafficLightRequest, request: Request):
    user = require_user(request)
    student_id = user["user_id"]

    with db_session() as conn:
        member = conn.execute(
            "SELECT seat_number FROM class_members WHERE class_id = ? AND student_id = ?",
            (class_id, student_id)
        ).fetchone()
        if not member:
            raise HTTPException(status_code=403, detail="Вы не являетесь участником этого класса")

        conn.execute(
            "UPDATE class_members SET traffic_light = ? WHERE class_id = ? AND student_id = ?",
            (req.traffic_light, class_id, student_id)
        )

        counts = conn.execute("""
            SELECT traffic_light, COUNT(*) as cnt 
            FROM class_members 
            WHERE class_id = ? AND is_present = 1
            GROUP BY traffic_light
        """, (class_id,)).fetchall()

        summary = {"green": 0, "yellow": 0, "red": 0}
        for c in counts:
            summary[c["traffic_light"]] = c["cnt"]

        # SSE уведомление на интерактивную доску и в класс
        event_data = {
            "student_id": student_id,
            "seat_number": member["seat_number"],
            "traffic_light": req.traffic_light,
            "summary": summary
        }
        sse_hub.notify_board(class_id, "traffic_light_changed", event_data)
        sse_hub.notify_class(class_id, "traffic_light_changed", event_data)

        return {"ok": True, "traffic_light": req.traffic_light, "summary": summary}

@router.post("/{class_id}/lock-recess")
def lock_recess(class_id: int, req: LockRecessRequest, request: Request):
    user = require_teacher(request)
    now = int(time.time())
    recess_locked_until = now + (req.duration_minutes * 60) if req.duration_minutes > 0 else 0

    with db_session() as conn:
        class_row = conn.execute("SELECT teacher_id FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not class_row or (class_row["teacher_id"] != user["user_id"] and user["role"] != "admin"):
            raise HTTPException(status_code=403, detail="Нет прав на управление перерывом класса")

        conn.execute("UPDATE classes SET recess_locked_until = ? WHERE id = ?", (recess_locked_until, class_id))

        sse_hub.notify_board(class_id, "recess_lock_changed", {"recess_locked_until": recess_locked_until})
        sse_hub.notify_class(class_id, "recess_lock_changed", {"recess_locked_until": recess_locked_until})

        return {"ok": True, "recess_locked_until": recess_locked_until}

# ============================================================================
# РАСШИРЕННЫЕ МЕТОДЫ УПРАВЛЕНИЯ КУРСОМ (ПАКЕТ 3 И 4)
# ============================================================================

class EnrollmentCodeActionRequest(BaseModel):
    action: str = Field(pattern="^(regenerate|disable|enable)$")

class ClassSettingsUpdateRequest(BaseModel):
    theme_color: Optional[str] = None
    banner_preset: Optional[str] = None
    stream_post_mode: Optional[str] = None
    stream_work_mode: Optional[str] = None
    show_deleted_items: Optional[int] = None

class CopyClassRequest(BaseModel):
    title: Optional[str] = None

class MuteStudentRequest(BaseModel):
    is_muted: int = Field(ge=0, le=1)

class BulkStudentActionRequest(BaseModel):
    student_ids: List[int]
    action: str = Field(pattern="^(unenroll|mute|unmute)$")

class MaterialSetCreateRequest(BaseModel):
    set_title: str = Field(min_length=1, max_length=200)
    materials_json: Optional[str] = "[]"
    sort_order: Optional[int] = 0

class MaterialSetUpdateRequest(BaseModel):
    set_title: Optional[str] = None
    materials_json: Optional[str] = None
    sort_order: Optional[int] = None

@router.post("/{class_id}/enrollment-code")
def manage_enrollment_code(class_id: int, req: EnrollmentCodeActionRequest, request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        class_row = conn.execute("SELECT teacher_id, join_pin, enrollment_enabled FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not class_row or (class_row["teacher_id"] != user["user_id"] and user["role"] != "admin"):
            raise HTTPException(status_code=403, detail="Нет прав на управление кодом записи")

        if req.action == "regenerate":
            new_pin = _generate_unique_pin(conn)
            conn.execute("UPDATE classes SET join_pin = ?, enrollment_enabled = 1 WHERE id = ?", (new_pin, class_id))
            return {"ok": True, "action": "regenerate", "enrollment_code": new_pin, "enrollment_enabled": 1}
        elif req.action == "disable":
            conn.execute("UPDATE classes SET enrollment_enabled = 0 WHERE id = ?", (class_id,))
            return {"ok": True, "action": "disable", "enrollment_code": class_row["join_pin"], "enrollment_enabled": 0}
        elif req.action == "enable":
            conn.execute("UPDATE classes SET enrollment_enabled = 1 WHERE id = ?", (class_id,))
            return {"ok": True, "action": "enable", "enrollment_code": class_row["join_pin"], "enrollment_enabled": 1}

@router.patch("/{class_id}/settings")
def update_class_settings(class_id: int, req: ClassSettingsUpdateRequest, request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        class_row = conn.execute("SELECT teacher_id FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not class_row or (class_row["teacher_id"] != user["user_id"] and user["role"] != "admin"):
            raise HTTPException(status_code=403, detail="Нет прав на изменение настроек курса")

        updates = []
        params = []
        if req.theme_color is not None:
            updates.append("theme_color = ?")
            params.append(req.theme_color)
        if req.banner_preset is not None:
            updates.append("banner_preset = ?")
            params.append(req.banner_preset)
        if req.stream_post_mode is not None:
            updates.append("stream_post_mode = ?")
            params.append(req.stream_post_mode)
        if req.stream_work_mode is not None:
            updates.append("stream_work_mode = ?")
            params.append(req.stream_work_mode)
        if req.show_deleted_items is not None:
            updates.append("show_deleted_items = ?")
            params.append(req.show_deleted_items)

        now = int(time.time())
        updates.append("updated_at = ?")
        params.append(now)

        params.append(class_id)
        conn.execute(f"UPDATE classes SET {', '.join(updates)} WHERE id = ?", params)
        updated = conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
        return dict(updated)

@router.post("/{class_id}/copy")
def copy_class(class_id: int, request: Request, req: Optional[CopyClassRequest] = None):
    user = require_teacher(request)
    uid = user.get("user_id") or user.get("id")
    now = int(time.time())
    if req is None:
        req = CopyClassRequest()
    with db_session() as conn:
        orig = conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not orig:
            raise HTTPException(status_code=404, detail="Исходный класс не найден")
        if orig["teacher_id"] != uid and user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Нет прав на копирование курса")

        orig_dict = dict(orig)
        new_title = (req.title or f"Копия — {orig_dict['title']}").strip()
        new_pin = _generate_unique_pin(conn)
        new_cal = f"cal_{uuid.uuid4().hex[:12]}"
        new_folder_id = f"folder_{uuid.uuid4().hex[:16]}"

        conn.execute(
            """INSERT INTO stored_folders (id, class_id, owner_user_id, folder_title, folder_kind, created_at)
               VALUES (?, NULL, ?, ?, 'COURSE_TEACHER_ROOT', ?)""",
            (new_folder_id, uid, f"{new_title} - Teacher Folder", now)
        )

        cursor = conn.execute(
            """INSERT INTO classes (
                teacher_id, title, subject_code, grade_level, join_pin,
                quarter_goal, recess_locked_until, classroom_state_json,
                section, description_heading, description, room, levels,
                course_state, enrollment_enabled, calendar_token,
                teacher_folder_id, theme_color, banner_preset,
                stream_post_mode, stream_work_mode,
                show_deleted_items, grade_calc_type, grade_display_setting,
                updated_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 0, '{}', ?, ?, ?, ?, ?, 'ACTIVE', 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                uid, new_title, orig_dict["subject_code"], orig_dict["grade_level"], new_pin,
                orig_dict["quarter_goal"], orig_dict["section"], orig_dict["description_heading"],
                orig_dict["description"], orig_dict["room"], orig_dict["levels"],
                new_cal, new_folder_id, orig_dict["theme_color"],
                orig_dict["banner_preset"],
                orig_dict["stream_post_mode"], orig_dict["stream_work_mode"], orig_dict["show_deleted_items"],
                orig_dict["grade_calc_type"], orig_dict["grade_display_setting"], now, now
            )
        )
        new_class_id = cursor.lastrowid
        conn.execute("UPDATE stored_folders SET class_id = ? WHERE id = ?", (new_class_id, new_folder_id))
        conn.execute("INSERT INTO course_teachers (class_id, teacher_id, is_primary, joined_at) VALUES (?, ?, 1, ?)", (new_class_id, uid, now))

        # Клонирование тем
        topic_map = {}
        old_topics = conn.execute("SELECT * FROM class_topics WHERE class_id = ?", (class_id,)).fetchall()
        for t in old_topics:
            t_cur = conn.execute(
                "INSERT INTO class_topics (class_id, title, frp_topic_id, sort_order, updated_at) VALUES (?, ?, ?, ?, ?)",
                (new_class_id, t["title"], t["frp_topic_id"], t["sort_order"], now)
            )
            topic_map[t["id"]] = t_cur.lastrowid

        # Клонирование категорий оценок
        cat_map = {}
        old_cats = conn.execute("SELECT * FROM grade_categories WHERE class_id = ?", (class_id,)).fetchall()
        for c in old_cats:
            c_cur = conn.execute(
                "INSERT INTO grade_categories (class_id, category_title, default_denominator, weight_micros) VALUES (?, ?, ?, ?)",
                (new_class_id, c["category_title"], c["default_denominator"], c["weight_micros"])
            )
            cat_map[c["id"]] = c_cur.lastrowid

        # Клонирование постоянных наборов материалов
        old_sets = conn.execute("SELECT * FROM course_material_sets WHERE class_id = ?", (class_id,)).fetchall()
        for s in old_sets:
            conn.execute(
                "INSERT INTO course_material_sets (class_id, set_title, materials_json, sort_order) VALUES (?, ?, ?, ?)",
                (new_class_id, s["set_title"], s["materials_json"], s["sort_order"])
            )

        # Клонирование заданий строго в статусе draft со сбросом сроков
        old_cw = conn.execute("SELECT * FROM coursework WHERE class_id = ?", (class_id,)).fetchall()
        for cw in old_cw:
            new_top_id = topic_map.get(cw["topic_id"])
            new_cat_id = cat_map.get(cw["grade_category_id"])
            cw_cur = conn.execute(
                """INSERT INTO coursework (
                    class_id, topic_id, kind, title, instructions, attachments_json,
                    rubric_json, target_students, max_points, recess_reward, is_homework,
                    state, scheduled_at, due_at, creator_user_id, creator_client_id,
                    work_type, assignee_mode, modification_mode, grade_category_id,
                    grading_period_id, choices_json, peer_replies_enabled, show_class_summary,
                    close_after_due, originality_enabled, reviewed_by_teacher, sort_order,
                    updated_at, created_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, 'all', ?, ?, ?,
                    'draft', NULL, NULL, ?, ?,
                    ?, 'ALL_STUDENTS', ?, ?,
                    NULL, ?, ?, ?,
                    ?, ?, 0, ?,
                    ?, ?
                )""",
                (
                    new_class_id, new_top_id, cw["kind"], cw["title"], cw["instructions"], cw["attachments_json"],
                    cw["rubric_json"], cw["max_points"], cw["recess_reward"], cw["is_homework"],
                    user["user_id"], cw["creator_client_id"],
                    cw["work_type"], cw["modification_mode"], new_cat_id,
                    cw["choices_json"], cw["peer_replies_enabled"], cw["show_class_summary"],
                    cw["close_after_due"], cw["originality_enabled"], cw["sort_order"],
                    now, now
                )
            )
            new_cw_id = cw_cur.lastrowid

            old_rubric = conn.execute("SELECT * FROM rubrics WHERE coursework_id = ?", (cw["id"],)).fetchone()
            if old_rubric:
                conn.execute(
                    """INSERT INTO rubrics (class_id, coursework_id, creator_client_id, source_sheet_id, is_scored, criteria_json, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (new_class_id, new_cw_id, old_rubric["creator_client_id"], old_rubric["source_sheet_id"], old_rubric["is_scored"], old_rubric["criteria_json"], now, now)
                )

            old_quiz = conn.execute("SELECT * FROM quizzes WHERE coursework_id = ?", (cw["id"],)).fetchone()
            if old_quiz:
                conn.execute(
                    """INSERT INTO quizzes (class_id, coursework_id, quiz_title, description, questions_json, shuffle_questions, time_limit_sec, lock_tab_focus, auto_import_grades, show_correct_answers, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (new_class_id, new_cw_id, old_quiz["quiz_title"], old_quiz["description"], old_quiz["questions_json"], old_quiz["shuffle_questions"], old_quiz["time_limit_sec"], old_quiz["lock_tab_focus"], old_quiz["auto_import_grades"], old_quiz["show_correct_answers"], now)
                )

            old_ps = conn.execute("SELECT * FROM practice_sets WHERE coursework_id = ?", (cw["id"],)).fetchone()
            if old_ps:
                conn.execute(
                    """INSERT INTO practice_sets (class_id, coursework_id, set_title, cards_json, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (new_class_id, new_cw_id, old_ps["set_title"], old_ps["cards_json"], now)
                )

        old_mats = conn.execute("SELECT * FROM course_materials WHERE class_id = ?", (class_id,)).fetchall()
        for m in old_mats:
            new_top_id = topic_map.get(m["topic_id"])
            conn.execute(
                """INSERT INTO course_materials (
                    class_id, topic_id, creator_user_id, creator_client_id, title,
                    description, materials_json, state, assignee_mode, target_students_json,
                    learning_goals_json, sort_order, scheduled_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'DRAFT', 'ALL_STUDENTS', '[]', ?, ?, NULL, ?, ?)""",
                (
                    new_class_id, new_top_id, user["user_id"], m["creator_client_id"], m["title"],
                    m["description"], m["materials_json"], m["learning_goals_json"], m["sort_order"], now, now
                )
            )

        new_row = conn.execute("SELECT * FROM classes WHERE id = ?", (new_class_id,)).fetchone()
        return dict(new_row)

@router.post("/{class_id}/students/{student_id}/mute")
def mute_student(class_id: int, student_id: int, req: MuteStudentRequest, request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        class_row = conn.execute("SELECT teacher_id FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not class_row or (class_row["teacher_id"] != user["user_id"] and user["role"] != "admin"):
            raise HTTPException(status_code=403, detail="Нет прав на управление заглушением ученика")

        conn.execute(
            "UPDATE class_members SET is_muted = ? WHERE class_id = ? AND student_id = ?",
            (req.is_muted, class_id, student_id)
        )
        return {"ok": True, "student_id": student_id, "is_muted": req.is_muted}

@router.post("/{class_id}/students/bulk")
def bulk_students_action(class_id: int, req: BulkStudentActionRequest, request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        class_row = conn.execute("SELECT teacher_id FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not class_row or (class_row["teacher_id"] != user["user_id"] and user["role"] != "admin"):
            raise HTTPException(status_code=403, detail="Нет прав на управление составом курса")

        if not req.student_ids:
            return {"ok": True, "affected": 0}

        placeholders = ", ".join("?" for _ in req.student_ids)
        params = list(req.student_ids)

        if req.action == "unenroll":
            conn.execute(
                f"UPDATE class_members SET enrollment_active = 0 WHERE class_id = ? AND student_id IN ({placeholders})",
                [class_id] + params
            )
            conn.execute(
                f"DELETE FROM student_group_members WHERE class_id = ? AND student_id IN ({placeholders})",
                [class_id] + params
            )
        elif req.action == "mute":
            conn.execute(
                f"UPDATE class_members SET is_muted = 1 WHERE class_id = ? AND student_id IN ({placeholders})",
                [class_id] + params
            )
        elif req.action == "unmute":
            conn.execute(
                f"UPDATE class_members SET is_muted = 0 WHERE class_id = ? AND student_id IN ({placeholders})",
                [class_id] + params
            )

        return {"ok": True, "action": req.action, "affected": len(req.student_ids)}

@router.get("/{class_id}/students/{student_id}/summary")
def get_student_summary(class_id: int, student_id: int, request: Request, filter: Optional[str] = Query(None)):
    user = require_user(request)
    with db_session() as conn:
        class_row = conn.execute("SELECT teacher_id FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not class_row:
            raise HTTPException(status_code=404, detail="Класс не найден")

        is_teacher = (user["role"] in ("teacher", "admin") and (class_row["teacher_id"] == user["user_id"] or user["role"] == "admin"))
        is_self = (user["user_id"] == student_id)

        if not is_teacher and not is_self:
            raise HTTPException(status_code=403, detail="Нет прав на просмотр сводки ученика")

        m_row = conn.execute(
            """SELECT cm.*, u.handle, u.avatar_seed FROM class_members cm
               JOIN users u ON cm.student_id = u.id
               WHERE cm.class_id = ? AND cm.student_id = ?""",
            (class_id, student_id)
        ).fetchone()
        if not m_row:
            raise HTTPException(status_code=404, detail="Ученик не найден в данном курсе")

        now = int(time.time())
        cw_rows = conn.execute(
            """SELECT cw.id, cw.title, cw.kind, cw.work_type, cw.max_points, cw.due_at,
                      s.status, s.v1_state, s.assigned_grade, s.draft_grade, s.is_late, s.updated_at
               FROM coursework cw
               LEFT JOIN submissions s ON cw.id = s.coursework_id AND s.student_id = ?
               WHERE cw.class_id = ? AND cw.state IN ('published', 'PUBLISHED')
               ORDER BY cw.created_at DESC""",
            (student_id, class_id)
        ).fetchall()

        items = []
        counts = {"ALL": 0, "TURNED_IN": 0, "ASSIGNED": 0, "RETURNED": 0, "MISSING": 0}

        for r in cw_rows:
            counts["ALL"] += 1
            v1_state = r["v1_state"] or "NEW"
            due = r["due_at"]
            is_missing = bool(due and due < now and v1_state not in ("TURNED_IN", "RETURNED"))

            item_status = "ASSIGNED"
            if v1_state == "RETURNED":
                item_status = "RETURNED"
                counts["RETURNED"] += 1
            elif v1_state == "TURNED_IN":
                item_status = "TURNED_IN"
                counts["TURNED_IN"] += 1
            elif is_missing:
                item_status = "MISSING"
                counts["MISSING"] += 1
            else:
                counts["ASSIGNED"] += 1

            if filter and filter.upper() != "ALL" and filter.upper() != item_status:
                continue

            items.append({
                "coursework_id": r["id"],
                "title": r["title"],
                "kind": r["kind"],
                "work_type": r["work_type"],
                "max_points": r["max_points"],
                "due_at": r["due_at"],
                "v1_state": v1_state,
                "assigned_grade": r["assigned_grade"],
                "draft_grade": r["draft_grade"] if is_teacher else None,
                "is_late": bool(r["is_late"]),
                "summary_status": item_status,
                "updated_at": r["updated_at"]
            })

        return {
            "student_id": student_id,
            "handle": m_row["handle"],
            "avatar_seed": m_row["avatar_seed"],
            "seat_number": m_row["seat_number"],
            "is_muted": m_row["is_muted"],
            "counts": counts,
            "items": items
        }

@router.get("/{class_id}/material-sets")
def list_material_sets(class_id: int, request: Request):
    user = require_user(request)
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM course_material_sets WHERE class_id = ? ORDER BY sort_order ASC, id ASC",
            (class_id,)
        ).fetchall()
        return [dict(r) for r in rows]

@router.post("/{class_id}/material-sets")
def create_material_set(class_id: int, req: MaterialSetCreateRequest, request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        c_row = conn.execute("SELECT teacher_id FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not c_row or (c_row["teacher_id"] != user["user_id"] and user["role"] != "admin"):
            raise HTTPException(status_code=403, detail="Нет прав на добавление постоянных материалов курса")

        cursor = conn.execute(
            "INSERT INTO course_material_sets (class_id, set_title, materials_json, sort_order) VALUES (?, ?, ?, ?)",
            (class_id, req.set_title.strip(), req.materials_json or "[]", req.sort_order or 0)
        )
        new_row = conn.execute("SELECT * FROM course_material_sets WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(new_row)

@router.patch("/{class_id}/material-sets/{set_id}")
def update_material_set(class_id: int, set_id: int, req: MaterialSetUpdateRequest, request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        c_row = conn.execute("SELECT teacher_id FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not c_row or (c_row["teacher_id"] != user["user_id"] and user["role"] != "admin"):
            raise HTTPException(status_code=403, detail="Нет прав на изменение материалов курса")

        updates = []
        params = []
        if req.set_title is not None:
            updates.append("set_title = ?")
            params.append(req.set_title.strip())
        if req.materials_json is not None:
            updates.append("materials_json = ?")
            params.append(req.materials_json)
        if req.sort_order is not None:
            updates.append("sort_order = ?")
            params.append(req.sort_order)

        if updates:
            params.extend([set_id, class_id])
            conn.execute(f"UPDATE course_material_sets SET {', '.join(updates)} WHERE id = ? AND class_id = ?", params)

        row = conn.execute("SELECT * FROM course_material_sets WHERE id = ? AND class_id = ?", (set_id, class_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Набор материалов не найден")
        return dict(row)

@router.delete("/{class_id}/material-sets/{set_id}")
def delete_material_set(class_id: int, set_id: int, request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        c_row = conn.execute("SELECT teacher_id FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not c_row or (c_row["teacher_id"] != user["user_id"] and user["role"] != "admin"):
            raise HTTPException(status_code=403, detail="Нет прав на удаление материалов курса")

        conn.execute("DELETE FROM course_material_sets WHERE id = ? AND class_id = ?", (set_id, class_id))
        return {"ok": True}

