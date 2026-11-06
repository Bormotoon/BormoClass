import secrets
import time
from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException, status
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
    encrypted_note: Optional[str] = None
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
            raise HTTPException(status_code=404, detail="Класс с таким пин-кодом не найден")

        class_id = class_row["id"]

        # Проверяем, не занята ли парта другим учеником
        seat_taken = conn.execute(
            "SELECT student_id FROM class_members WHERE class_id = ? AND seat_number = ?",
            (class_id, req.seat_number)
        ).fetchone()

        if seat_taken and seat_taken["student_id"] != student_id:
            raise HTTPException(status_code=409, detail=f"Парта №{req.seat_number} уже занята другим учеником")

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
            SELECT cm.student_id, cm.seat_number, cm.encrypted_note, cm.is_present, 
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
            # Только учитель получает зашифрованные заметки/ФИО
            if is_teacher:
                item["encrypted_note"] = m["encrypted_note"]
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
        if req.encrypted_note is not None:
            updates.append("encrypted_note = ?")
            params.append(req.encrypted_note)
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
