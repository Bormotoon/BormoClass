import time
from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException
from app.db import db_session
from app.passport.middleware import require_user, require_teacher

router = APIRouter(prefix="/api/classroom/global", tags=["global"])

@router.get("/to-review")
def get_to_review(request: Request):
    user = require_teacher(request)
    teacher_id = user["user_id"]

    with db_session() as conn:
        rows = conn.execute("""
            SELECT s.coursework_id, s.student_id, s.status, s.updated_at, s.payload_json,
                   cw.title as coursework_title, cw.max_points, cw.due_at,
                   c.id as class_id, c.title as class_title,
                   u.handle as student_handle, u.avatar_seed,
                   cm.seat_number, cm.encrypted_note
            FROM submissions s
            JOIN coursework cw ON s.coursework_id = cw.id
            JOIN classes c ON cw.class_id = c.id
            JOIN users u ON s.student_id = u.id
            LEFT JOIN class_members cm ON s.student_id = cm.student_id AND cm.class_id = c.id
            WHERE c.teacher_id = ? AND s.status = 'turned_in'
            ORDER BY s.updated_at ASC
        """, (teacher_id,)).fetchall()

        return [dict(r) for r in rows]

@router.get("/to-do")
def get_to_do(request: Request):
    user = require_user(request)
    student_id = user["user_id"]
    now = int(time.time())

    with db_session() as conn:
        # Все опубликованные задания классов, в которых состоит ученик
        rows = conn.execute("""
            SELECT cw.id as coursework_id, cw.class_id, cw.title as coursework_title,
                   cw.kind, cw.instructions, cw.max_points, cw.due_at, cw.recess_reward,
                   c.title as class_title,
                   COALESCE(s.status, 'assigned') as status,
                   s.grade_five, s.grade_points, s.updated_at as submitted_at
            FROM class_members cm
            JOIN classes c ON cm.class_id = c.id
            JOIN coursework cw ON c.id = cw.class_id
            LEFT JOIN submissions s ON cw.id = s.coursework_id AND s.student_id = ?
            WHERE cm.student_id = ? AND cw.state = 'published' AND cw.kind IN ('assignment', 'quiz', 'question')
            ORDER BY cw.due_at ASC NULLS LAST, cw.created_at DESC
        """, (student_id, student_id)).fetchall()

        assigned = []
        missing = []
        done = []

        for r in rows:
            item = dict(r)
            stat = item["status"]
            due = item["due_at"]

            if stat in ("turned_in", "returned"):
                done.append(item)
            elif due and due < now:
                missing.append(item)
            else:
                assigned.append(item)

        return {
            "assigned": assigned,
            "missing": missing,
            "done": done
        }

@router.get("/calendar")
def get_calendar(request: Request):
    user = require_user(request)
    user_id = user["user_id"]
    is_teacher = user["role"] in ("teacher", "admin")

    with db_session() as conn:
        if is_teacher:
            rows = conn.execute("""
                SELECT cw.id, cw.class_id, cw.title, cw.due_at, c.title as class_title
                FROM coursework cw
                JOIN classes c ON cw.class_id = c.id
                WHERE c.teacher_id = ? AND cw.due_at IS NOT NULL
                ORDER BY cw.due_at ASC
            """, (user_id,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT cw.id, cw.class_id, cw.title, cw.due_at, c.title as class_title,
                       s.status as my_status
                FROM class_members cm
                JOIN classes c ON cm.class_id = c.id
                JOIN coursework cw ON c.id = cw.class_id
                LEFT JOIN submissions s ON cw.id = s.coursework_id AND s.student_id = ?
                WHERE cm.student_id = ? AND cw.due_at IS NOT NULL AND cw.state = 'published'
                ORDER BY cw.due_at ASC
            """, (user_id, user_id)).fetchall()

        return [dict(r) for r in rows]
