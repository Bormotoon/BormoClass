import json
import time
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, HTTPException, status
from pydantic import BaseModel, Field

from app.db import db_session
from app.passport.middleware import require_user, require_teacher
from app.passport.recess import award_recess_seconds
from app.classroom.sse_hub import sse_hub

router = APIRouter(prefix="/api/classroom", tags=["submissions"])

# -----------------------------------------------------------------------------
# Pydantic-схемы (Zero-PII)
# -----------------------------------------------------------------------------

class TurnInRequest(BaseModel):
    payload_json: str = Field(default="{}")

class GradeSubmissionRequest(BaseModel):
    grade_points: Optional[int] = Field(default=None, ge=0)
    grade_five: Optional[int] = Field(default=None, ge=2, le=5)
    rubric_scores: Optional[str] = Field(default="{}")
    teacher_comment: Optional[str] = Field(default="")

class CommentBankRequest(BaseModel):
    comment_text: str = Field(min_length=1, max_length=500)

# -----------------------------------------------------------------------------
# Роуты сдачи и оценивания
# -----------------------------------------------------------------------------

@router.get("/coursework/{coursework_id}/submissions")
def list_submissions(coursework_id: int, request: Request):
    user = require_user(request)
    user_id = user["user_id"]
    is_teacher = user["role"] in ("teacher", "admin")

    with db_session() as conn:
        cw = conn.execute("""
            SELECT cw.class_id, c.teacher_id
            FROM coursework cw
            JOIN classes c ON cw.class_id = c.id
            WHERE cw.id = ?
        """, (coursework_id,)).fetchone()

        if not cw:
            raise HTTPException(status_code=404, detail="Задание не найдено")

        if is_teacher and (cw["teacher_id"] == user_id or user["role"] == "admin"):
            rows = conn.execute("""
                SELECT s.*, u.handle, u.avatar_seed, cm.seat_number, cm.encrypted_note
                FROM submissions s
                JOIN users u ON s.student_id = u.id
                LEFT JOIN class_members cm ON s.student_id = cm.student_id AND cm.class_id = ?
                WHERE s.coursework_id = ?
                ORDER BY cm.seat_number ASC, s.updated_at DESC
            """, (cw["class_id"], coursework_id)).fetchall()
            return [dict(r) for r in rows]
        else:
            # Ученик видит только свою работу
            row = conn.execute("""
                SELECT s.*, u.handle, u.avatar_seed
                FROM submissions s
                JOIN users u ON s.student_id = u.id
                WHERE s.coursework_id = ? AND s.student_id = ?
            """, (coursework_id, user_id)).fetchone()
            return [dict(row)] if row else []

@router.post("/coursework/{coursework_id}/turn-in")
def turn_in_submission(coursework_id: int, req: TurnInRequest, request: Request):
    user = require_user(request)
    student_id = user["user_id"]
    now = int(time.time())

    with db_session() as conn:
        cw = conn.execute("""
            SELECT cw.id, cw.class_id, cw.recess_reward, cw.state, c.teacher_id
            FROM coursework cw
            JOIN classes c ON cw.class_id = c.id
            WHERE cw.id = ?
        """, (coursework_id,)).fetchone()

        if not cw or cw["state"] != "published":
            raise HTTPException(status_code=404, detail="Задание не найдено или закрыто")

        existing = conn.execute("""
            SELECT status FROM submissions
            WHERE coursework_id = ? AND student_id = ?
        """, (coursework_id, student_id)).fetchone()

        awarded_recess = False
        if not existing:
            conn.execute("""
                INSERT INTO submissions (coursework_id, student_id, status, payload_json, updated_at)
                VALUES (?, ?, 'turned_in', ?, ?)
            """, (coursework_id, student_id, req.payload_json, now))
            award_recess_seconds(conn, student_id, cw["recess_reward"])
            awarded_recess = True
        elif existing["status"] == "assigned":
            conn.execute("""
                UPDATE submissions
                SET status = 'turned_in', payload_json = ?, updated_at = ?
                WHERE coursework_id = ? AND student_id = ?
            """, (req.payload_json, now, coursework_id, student_id))
            award_recess_seconds(conn, student_id, cw["recess_reward"])
            awarded_recess = True
        else:
            # Повторная сдача - обновляем ответ без повторного начисления секунд
            conn.execute("""
                UPDATE submissions
                SET status = 'turned_in', payload_json = ?, updated_at = ?
                WHERE coursework_id = ? AND student_id = ?
            """, (req.payload_json, now, coursework_id, student_id))

        sse_hub.notify_class(cw["class_id"], "submission_turned_in", {
            "coursework_id": coursework_id,
            "student_id": student_id,
            "handle": user["handle"]
        })

        return {"ok": True, "awarded_recess": awarded_recess, "status": "turned_in"}

@router.post("/submissions/{coursework_id}/{student_id}/grade")
def grade_submission(coursework_id: int, student_id: int, req: GradeSubmissionRequest, request: Request):
    user = require_teacher(request)
    now = int(time.time())

    with db_session() as conn:
        cw = conn.execute("""
            SELECT cw.class_id, c.teacher_id, cw.max_points
            FROM coursework cw
            JOIN classes c ON cw.class_id = c.id
            WHERE cw.id = ?
        """, (coursework_id,)).fetchone()

        if not cw or (cw["teacher_id"] != user["user_id"] and user["role"] != "admin"):
            raise HTTPException(status_code=403, detail="Нет прав на выставление оценок")

        # Если grade_five не указан явно, но есть grade_points, можно рассчитать
        grade_five = req.grade_five
        if grade_five is None and req.grade_points is not None:
            max_pts = cw["max_points"] or 5
            pct = (req.grade_points / max_pts) * 100
            if pct < 50:
                grade_five = 2
            elif pct < 70:
                grade_five = 3
            elif pct < 85:
                grade_five = 4
            else:
                grade_five = 5

        conn.execute("""
            INSERT INTO submissions (
                coursework_id, student_id, status, rubric_scores,
                grade_points, grade_five, teacher_comment, updated_at
            ) VALUES (?, ?, 'returned', ?, ?, ?, ?, ?)
            ON CONFLICT(coursework_id, student_id) DO UPDATE SET
                status = 'returned',
                rubric_scores = excluded.rubric_scores,
                grade_points = excluded.grade_points,
                grade_five = excluded.grade_five,
                teacher_comment = excluded.teacher_comment,
                updated_at = excluded.updated_at
        """, (
            coursework_id, student_id, req.rubric_scores or "{}",
            req.grade_points, grade_five, req.teacher_comment or "", now
        ))

        # Сохраняем комментарий в личный банк учителя, если он новый и не пустой
        if req.teacher_comment and len(req.teacher_comment.strip()) > 3:
            conn.execute("""
                INSERT OR IGNORE INTO comment_bank (teacher_id, comment_text)
                VALUES (?, ?)
            """, (user["user_id"], req.teacher_comment.strip()))

        sse_hub.notify_class(cw["class_id"], "submission_graded", {
            "coursework_id": coursework_id,
            "student_id": student_id,
            "grade_five": grade_five,
            "grade_points": req.grade_points
        })

        return {"ok": True, "grade_five": grade_five, "grade_points": req.grade_points, "status": "returned"}

# -----------------------------------------------------------------------------
# Банк комментариев (Comment Bank)
# -----------------------------------------------------------------------------

@router.get("/comments")
def list_comments(request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM comment_bank WHERE teacher_id = ? ORDER BY id DESC LIMIT 100",
            (user["user_id"],)
        ).fetchall()
        return [dict(r) for r in rows]

@router.post("/comments")
def add_comment(req: CommentBankRequest, request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        cursor = conn.execute("""
            INSERT INTO comment_bank (teacher_id, comment_text)
            VALUES (?, ?)
        """, (user["user_id"], req.comment_text.strip()))
        return {"id": cursor.lastrowid, "comment_text": req.comment_text.strip()}

@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: int, request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        conn.execute("DELETE FROM comment_bank WHERE id = ? AND teacher_id = ?", (comment_id, user["user_id"]))
        return {"ok": True}

# -----------------------------------------------------------------------------
# Аналитика (Усп, КЗ, СОУ по Симонову) и Матрица оценок
# -----------------------------------------------------------------------------

def calculate_sou_metrics(grades: List[int]) -> Dict[str, Any]:
    n_total = len(grades)
    if n_total == 0:
        return {
            "n_total": 0, "n5": 0, "n4": 0, "n3": 0, "n2": 0,
            "usp": 0.0, "kz": 0.0, "sou": 0.0
        }

    n5 = grades.count(5)
    n4 = grades.count(4)
    n3 = grades.count(3)
    n2 = grades.count(2)

    # 1. Абсолютная успеваемость (Усп) = (N5 + N4 + N3) / N_всего * 100%
    usp = round(((n5 + n4 + n3) / n_total) * 100.0, 1)

    # 2. Качество знаний (КЗ) = (N5 + N4) / N_всего * 100%
    kz = round(((n5 + n4) / n_total) * 100.0, 1)

    # 3. Степень обученности учащихся по В. П. Симонову (СОУ) = (100*N5 + 64*N4 + 36*N3 + 16*N2) / N_всего
    sou = round(((100 * n5 + 64 * n4 + 36 * n3 + 16 * n2) / n_total), 1)

    return {
        "n_total": n_total,
        "n5": n5,
        "n4": n4,
        "n3": n3,
        "n2": n2,
        "usp": usp,
        "kz": kz,
        "sou": sou
    }

@router.get("/classes/{class_id}/analytics")
def get_class_analytics(class_id: int, request: Request, coursework_id: Optional[int] = None):
    require_user(request)
    with db_session() as conn:
        if coursework_id:
            rows = conn.execute("""
                SELECT s.grade_five
                FROM submissions s
                JOIN coursework cw ON s.coursework_id = cw.id
                WHERE cw.class_id = ? AND s.coursework_id = ? AND s.grade_five IS NOT NULL
            """, (class_id, coursework_id)).fetchall()
        else:
            rows = conn.execute("""
                SELECT s.grade_five
                FROM submissions s
                JOIN coursework cw ON s.coursework_id = cw.id
                WHERE cw.class_id = ? AND s.grade_five IS NOT NULL
            """, (class_id,)).fetchall()

        grades = [r["grade_five"] for r in rows if r["grade_five"] in (2, 3, 4, 5)]
        return calculate_sou_metrics(grades)

@router.get("/classes/{class_id}/matrix")
def get_class_matrix(class_id: int, request: Request):
    user = require_user(request)
    is_teacher = user["role"] in ("teacher", "admin")

    with db_session() as conn:
        class_row = conn.execute("SELECT teacher_id FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not class_row:
            raise HTTPException(status_code=404, detail="Класс не найден")

        members = conn.execute("""
            SELECT cm.student_id, cm.seat_number, cm.encrypted_note, cm.is_present, u.handle, u.avatar_seed
            FROM class_members cm
            JOIN users u ON cm.student_id = u.id
            WHERE cm.class_id = ?
            ORDER BY cm.seat_number ASC
        """, (class_id,)).fetchall()

        courseworks = conn.execute("""
            SELECT id, title, kind, max_points, due_at, created_at
            FROM coursework
            WHERE class_id = ? AND state = 'published' AND kind IN ('assignment', 'quiz', 'question')
            ORDER BY created_at ASC
        """, (class_id,)).fetchall()

        subs = conn.execute("""
            SELECT s.coursework_id, s.student_id, s.status, s.grade_points, s.grade_five, s.updated_at
            FROM submissions s
            JOIN coursework cw ON s.coursework_id = cw.id
            WHERE cw.class_id = ?
        """, (class_id,)).fetchall()

        students_list = []
        for m in members:
            item = {
                "student_id": m["student_id"],
                "seat_number": m["seat_number"],
                "handle": m["handle"],
                "avatar_seed": m["avatar_seed"],
                "is_present": m["is_present"]
            }
            if is_teacher:
                item["encrypted_note"] = m["encrypted_note"]
            students_list.append(item)

        # Индексируем сдачи по (coursework_id, student_id)
        subs_map = {f"{s['coursework_id']}_{s['student_id']}": dict(s) for s in subs}

        # Считаем сводные метрики СОУ
        all_grades = [s["grade_five"] for s in subs if s["grade_five"] in (2, 3, 4, 5)]
        summary_analytics = calculate_sou_metrics(all_grades)

        return {
            "students": students_list,
            "coursework": [dict(c) for c in courseworks],
            "submissions": subs_map,
            "analytics": summary_analytics
        }
