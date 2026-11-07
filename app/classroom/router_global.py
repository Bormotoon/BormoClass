import datetime
import io
import json
import secrets
import time
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, Response, HTTPException, status, Query
from pydantic import BaseModel, Field

from app.db import db_session
from app.passport.middleware import require_user, require_teacher
from app.classroom.sse_hub import sse_hub
router = APIRouter(tags=["global"])

# -----------------------------------------------------------------------------
# 1. GET /api/classroom/global/to-review (На проверку и Проверено)
# -----------------------------------------------------------------------------

@router.get("/api/classroom/global/to-review")
def get_to_review(
    request: Request,
    course_id: Optional[int] = None,
    tab: Optional[str] = None,
    format: Optional[str] = None
):
    user = require_teacher(request)
    teacher_id = user["user_id"]

    with db_session() as conn:
        # Проверяем фильтр курса
        course_clause = "AND c.id = ?" if course_id else ""
        course_params = (teacher_id, course_id) if course_id else (teacher_id,)

        # Выбираем сданные работы
        rows = conn.execute(f"""
            SELECT s.coursework_id, s.student_id, s.status, s.updated_at, s.payload_json,
                   cw.title as coursework_title, cw.max_points, cw.due_at,
                   COALESCE(cw.reviewed_by_teacher, 0) as reviewed_by_teacher,
                   c.id as class_id, c.title as class_title,
                   u.handle as student_handle, u.avatar_seed,
                   cm.seat_number
            FROM submissions s
            JOIN coursework cw ON s.coursework_id = cw.id
            JOIN classes c ON cw.class_id = c.id
            JOIN users u ON s.student_id = u.id
            LEFT JOIN class_members cm ON s.student_id = cm.student_id AND cm.class_id = c.id
            WHERE (c.teacher_id = ? OR EXISTS (
                SELECT 1 FROM course_teachers ct WHERE ct.class_id = c.id AND ct.teacher_id = ?
            )) {course_clause}
            ORDER BY s.updated_at ASC
        """, (teacher_id, teacher_id, course_id) if course_id else (teacher_id, teacher_id)).fetchall()

        # Подсчёт счётчиков Turned in / Assigned / Graded по заданиям
        cw_stats_query = f"""
            SELECT cw.id as coursework_id,
                   COUNT(CASE WHEN s.status = 'turned_in' THEN 1 END) as turned_in_count,
                   COUNT(CASE WHEN s.status = 'assigned' OR s.status IS NULL THEN 1 END) as assigned_count,
                   COUNT(CASE WHEN s.status = 'returned' OR s.grade_points IS NOT NULL OR s.grade_five IS NOT NULL THEN 1 END) as graded_count
            FROM coursework cw
            JOIN classes c ON cw.class_id = c.id
            LEFT JOIN submissions s ON s.coursework_id = cw.id
            WHERE (c.teacher_id = ? OR EXISTS (
                SELECT 1 FROM course_teachers ct WHERE ct.class_id = c.id AND ct.teacher_id = ?
            )) {course_clause}
            GROUP BY cw.id
        """
        cw_stats_params = (teacher_id, teacher_id, course_id) if course_id else (teacher_id, teacher_id)
        cw_stats_rows = conn.execute(cw_stats_query, cw_stats_params).fetchall()
        cw_stats = {
            r["coursework_id"]: {
                "turned_in_count": r["turned_in_count"],
                "assigned_count": r["assigned_count"],
                "graded_count": r["graded_count"]
            }
            for r in cw_stats_rows
        }

        work_to_review = []
        reviewed = []

        for r in rows:
            item = dict(r)
            stats = cw_stats.get(item["coursework_id"], {"turned_in_count": 0, "assigned_count": 0, "graded_count": 0})
            item.update(stats)
            if item["status"] == "turned_in" and not item["reviewed_by_teacher"]:
                work_to_review.append(item)
            elif item["reviewed_by_teacher"] or item["status"] in ("returned", "graded"):
                reviewed.append(item)
            else:
                work_to_review.append(item)

        if tab == "reviewed":
            return reviewed
        if tab == "work_to_review":
            return work_to_review
        if format == "tabs" or tab == "all":
            return {
                "work_to_review": work_to_review,
                "reviewed": reviewed
            }

        # По умолчанию возвращаем список работ на проверку (для 100% совместимости с существующим тестом и UI)
        return work_to_review

# -----------------------------------------------------------------------------
# 2. POST /api/classroom/coursework/{coursework_id}/mark-reviewed
# -----------------------------------------------------------------------------

class MarkReviewedRequest(BaseModel):
    reviewed: bool = True

@router.post("/api/classroom/coursework/{coursework_id}/mark-reviewed")
@router.post("/api/classroom/global/coursework/{coursework_id}/mark-reviewed")
def mark_coursework_reviewed(coursework_id: int, request: Request, req_body: Optional[MarkReviewedRequest] = None):
    user = require_teacher(request)
    teacher_id = user["user_id"]
    is_reviewed = req_body.reviewed if req_body is not None else True

    with db_session() as conn:
        cw = conn.execute("""
            SELECT cw.id, cw.class_id, c.teacher_id
            FROM coursework cw
            JOIN classes c ON cw.class_id = c.id
            WHERE cw.id = ?
        """, (coursework_id,)).fetchone()

        if not cw:
            raise HTTPException(status_code=404, detail="Задание не найдено")

        # Проверка прав доступа
        if user.get("role") != "admin" and cw["teacher_id"] != teacher_id:
            ct = conn.execute(
                "SELECT 1 FROM course_teachers WHERE class_id = ? AND teacher_id = ?",
                (cw["class_id"], teacher_id)
            ).fetchone()
            if not ct:
                raise HTTPException(status_code=403, detail="Нет прав на изменение статуса проверки данного задания")

        conn.execute(
            "UPDATE coursework SET reviewed_by_teacher = ? WHERE id = ?",
            (1 if is_reviewed else 0, coursework_id)
        )

        sse_hub.notify_class(cw["class_id"], "coursework_reviewed_changed", {
            "coursework_id": coursework_id,
            "reviewed": is_reviewed
        })

        return {"ok": True, "coursework_id": coursework_id, "reviewed": is_reviewed}

# -----------------------------------------------------------------------------
# 3. GET /api/classroom/global/todo (3 вкладки по корзинам дедлайнов)
# -----------------------------------------------------------------------------

def _compute_due_bucket(due_at: Optional[int], now: int) -> str:
    if not due_at:
        return "no_due_date"
    if due_at < now:
        return "earlier"

    # Вычисляем границы текущей недели (до воскресенья 23:59:59 UTC)
    dt_now = datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc)
    weekday = dt_now.weekday()  # 0 = Monday, 6 = Sunday
    days_to_end_of_week = 6 - weekday
    end_of_week = dt_now.replace(hour=23, minute=59, second=59) + datetime.timedelta(days=days_to_end_of_week)
    end_of_week_ts = int(end_of_week.timestamp())
    end_of_next_week_ts = end_of_week_ts + 7 * 86400

    if due_at <= end_of_week_ts:
        return "this_week"
    if due_at <= end_of_next_week_ts:
        return "next_week"
    return "later"

@router.get("/api/classroom/global/todo")
@router.get("/api/classroom/global/to-do")
def get_to_do(request: Request):
    user = require_user(request)
    student_id = user["user_id"]
    now = int(time.time())

    with db_session() as conn:
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

        assigned_buckets: Dict[str, list] = {"no_due_date": [], "this_week": [], "next_week": [], "later": []}
        missing_buckets: Dict[str, list] = {"earlier": [], "this_week": []}
        done_buckets: Dict[str, list] = {"this_week": [], "earlier": []}

        for r in rows:
            item = dict(r)
            stat = item["status"]
            due = item["due_at"]
            bucket = _compute_due_bucket(due, now)
            item["bucket"] = bucket

            if stat in ("turned_in", "returned"):
                done.append(item)
                if bucket in done_buckets:
                    done_buckets[bucket].append(item)
                else:
                    done_buckets["earlier"].append(item)
            elif due and due < now:
                missing.append(item)
                if bucket in missing_buckets:
                    missing_buckets[bucket].append(item)
                else:
                    missing_buckets["earlier"].append(item)
            else:
                assigned.append(item)
                if bucket in assigned_buckets:
                    assigned_buckets[bucket].append(item)
                else:
                    assigned_buckets["later"].append(item)

        return {
            "assigned": assigned,
            "missing": missing,
            "done": done,
            "buckets": {
                "assigned": assigned_buckets,
                "missing": missing_buckets,
                "done": done_buckets
            }
        }

# -----------------------------------------------------------------------------
# 4. КАЛЕНДАРЬ: СОБЫТИЯ И СТАНДАРТ RFC 5545 .ics
# -----------------------------------------------------------------------------

@router.get("/api/classroom/calendar/events")
@router.get("/api/classroom/global/calendar")
def get_calendar_events(
    request: Request,
    class_id: Optional[int] = None,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None
):
    user = require_user(request)
    user_id = user["user_id"]
    is_teacher = user["role"] in ("teacher", "admin")

    with db_session() as conn:
        filter_clause = ""
        params: List[Any] = []

        if class_id:
            filter_clause += " AND cw.class_id = ?"
            params.append(class_id)
        if start_time:
            filter_clause += " AND cw.due_at >= ?"
            params.append(start_time)
        if end_time:
            filter_clause += " AND cw.due_at <= ?"
            params.append(end_time)

        if is_teacher:
            q = f"""
                SELECT cw.id, cw.id as coursework_id, cw.class_id, cw.title, cw.due_at,
                       cw.kind, cw.max_points, c.title as class_title
                FROM coursework cw
                JOIN classes c ON cw.class_id = c.id
                WHERE (c.teacher_id = ? OR EXISTS (
                    SELECT 1 FROM course_teachers ct WHERE ct.class_id = c.id AND ct.teacher_id = ?
                )) AND cw.due_at IS NOT NULL {filter_clause}
                ORDER BY cw.due_at ASC
            """
            all_params = [user_id, user_id] + params
            rows = conn.execute(q, all_params).fetchall()
        else:
            q = f"""
                SELECT cw.id, cw.id as coursework_id, cw.class_id, cw.title, cw.due_at,
                       cw.kind, cw.max_points, c.title as class_title,
                       COALESCE(s.status, 'assigned') as my_status
                FROM class_members cm
                JOIN classes c ON cm.class_id = c.id
                JOIN coursework cw ON c.id = cw.class_id
                LEFT JOIN submissions s ON cw.id = s.coursework_id AND s.student_id = ?
                WHERE cm.student_id = ? AND cw.due_at IS NOT NULL AND cw.state = 'published' {filter_clause}
                ORDER BY cw.due_at ASC
            """
            all_params = [user_id, user_id] + params
            rows = conn.execute(q, all_params).fetchall()

        return [dict(r) for r in rows]

def _format_ics_timestamp(ts: int) -> str:
    dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
    return dt.strftime("%Y%m%dT%H%M%SZ")

@router.get("/api/classroom/calendar/{calendar_token}.ics")
def export_calendar_ics(calendar_token: str):
    """
    Бескукисный экспорт дедлайнов в формат RFC 5545 iCalendar для внешних календарей.
    """
    with db_session() as conn:
        # Поиск по токену курса
        course = conn.execute("SELECT * FROM classes WHERE calendar_token = ?", (calendar_token,)).fetchone()
        now_ts = int(time.time())

        if course:
            cal_name = f"BormoClass: {course['title']}"
            rows = conn.execute("""
                SELECT cw.id, cw.title, cw.instructions, cw.due_at, c.title as class_title
                FROM coursework cw
                JOIN classes c ON cw.class_id = c.id
                WHERE cw.class_id = ? AND cw.due_at IS NOT NULL AND cw.state = 'published'
                ORDER BY cw.due_at ASC
            """, (course["id"],)).fetchall()
        else:
            # Поиск по пользователю (например, токен вида user_<uid>)
            user_id = None
            if calendar_token.startswith("user_"):
                try:
                    user_id = int(calendar_token.split("_")[1])
                except Exception:
                    user_id = None

            if not user_id:
                raise HTTPException(status_code=404, detail="Календарный токен не найден")

            cal_name = "BormoClass: Мои дедлайны"
            rows = conn.execute("""
                SELECT cw.id, cw.title, cw.instructions, cw.due_at, c.title as class_title
                FROM class_members cm
                JOIN classes c ON cm.class_id = c.id
                JOIN coursework cw ON c.id = cw.class_id
                WHERE cm.student_id = ? AND cw.due_at IS NOT NULL AND cw.state = 'published'
                ORDER BY cw.due_at ASC
            """, (user_id,)).fetchall()

        now_formatted = _format_ics_timestamp(now_ts)

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//BormoClass//Calendar RFC5545//RU",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            f"X-WR-CALNAME:{cal_name}",
            "X-WR-TIMEZONE:UTC"
        ]

        for r in rows:
            due_at = r["due_at"]
            due_formatted = _format_ics_timestamp(due_at)
            due_end_formatted = _format_ics_timestamp(due_at + 3600)
            summary = f"{r['title']} [{r['class_title']}]"
            desc = (r["instructions"] or "").replace("\n", "\\n").replace("\r", "")

            lines.extend([
                "BEGIN:VEVENT",
                f"UID:cw-{r['id']}@bormoclass.local",
                f"DTSTAMP:{now_formatted}",
                f"DTSTART:{due_formatted}",
                f"DTEND:{due_end_formatted}",
                f"SUMMARY:{summary}",
                f"DESCRIPTION:{desc}",
                "STATUS:CONFIRMED",
                "END:VEVENT"
            ])

        lines.append("END:VCALENDAR")
        ics_content = "\r\n".join(lines) + "\r\n"

        return Response(
            content=ics_content,
            media_type="text/calendar; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={calendar_token}.ics"}
        )
