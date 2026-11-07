import json
import time
from datetime import datetime, timezone, date
from typing import Optional, List, Any, Dict
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.db import db_session
from app.v1.protocol import (
    api_error,
    resolve_class_id,
    parse_update_mask,
    ts_to_rfc3339,
)
from app.v1.rbac import (
    resolve_auth_context,
    require_scopes,
    assert_course_access,
    SCOPE_COURSES,
    SCOPE_COURSES_READONLY,
    SCOPE_COURSEWORK_STUDENTS,
    SCOPE_COURSEWORK_STUDENTS_READONLY,
)
from app.v1.schemas import (
    Rubric,
    ListRubricsResponse,
    Criterion,
    Level,
    GradingPeriodSettings,
    GradingPeriod,
    Date,
    Empty,
)

router = APIRouter()

# -----------------------------------------------------------------------------
# Helpers: Rubrics
# -----------------------------------------------------------------------------

def _validate_rubric_criteria(criteria: List[Criterion]) -> bool:
    if len(criteria) > 50:
        api_error(400, "INVALID_ARGUMENT", "Рубрика не может содержать более 50 критериев", reason="INVALID_ARGUMENT")

    has_points = None
    for c in criteria:
        levels = c.levels or []
        if len(levels) > 10:
            api_error(400, "INVALID_ARGUMENT", "Критерий не может содержать более 10 уровней", reason="INVALID_ARGUMENT")

        c_has_pts = any(lvl.points is not None for lvl in levels)
        if has_points is None:
            has_points = c_has_pts
        elif has_points != c_has_pts:
            api_error(400, "INVALID_ARGUMENT", "Баллы должны быть указаны либо во всех критериях, либо ни в одном", reason="INVALID_ARGUMENT")

    return bool(has_points)

def _rubric_row_to_schema(row: dict) -> Rubric:
    criteria_raw = []
    try:
        criteria_raw = json.loads(row.get("criteria_json") or "[]")
    except Exception:
        pass

    criteria_list = []
    for c in criteria_raw:
        levels = [Level(**lvl) for lvl in c.get("levels", [])]
        criteria_list.append(Criterion(
            id=c.get("id"),
            title=c.get("title"),
            description=c.get("description"),
            levels=levels,
        ))

    return Rubric(
        id=str(row["id"]),
        courseId=str(row["class_id"]),
        courseWorkId=str(row["coursework_id"]),
        creationTime=ts_to_rfc3339(row.get("created_at") or 0),
        updateTime=ts_to_rfc3339(row.get("updated_at") or 0),
        sourceSpreadsheetId=row.get("source_sheet_id") or "",
        criteria=criteria_list,
    )

# -----------------------------------------------------------------------------
# 8.2. Критериальные Рубрики (courses.courseWork.rubrics)
# -----------------------------------------------------------------------------

@router.post("/v1/courses/{courseId}/courseWork/{courseWorkId}/rubrics", response_model=Rubric)
def create_rubric(courseId: str, courseWorkId: str, req: Rubric, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSEWORK_STUDENTS, SCOPE_COURSES))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для создания рубрики")

        try:
            cw_id = int(courseWorkId)
        except ValueError:
            api_error(404, "NOT_FOUND", "Задание не найдено")

        cw = conn.execute("SELECT id FROM coursework WHERE id = ? AND class_id = ?", (cw_id, class_id)).fetchone()
        if not cw:
            api_error(404, "NOT_FOUND", "Задание не найдено")

        existing = conn.execute("SELECT id FROM rubrics WHERE coursework_id = ?", (cw_id,)).fetchone()
        if existing:
            api_error(409, "ALREADY_EXISTS", "Рубрика для данного задания уже создана")

        criteria = req.criteria or []
        is_scored = 1 if _validate_rubric_criteria(criteria) else 0

        criteria_dicts = [c.model_dump(exclude_none=True) if hasattr(c, "model_dump") else c for c in criteria]
        criteria_json = json.dumps(criteria_dicts, ensure_ascii=False)
        now = int(time.time())

        cursor = conn.execute("""
            INSERT INTO rubrics (
                class_id, coursework_id, creator_client_id, source_sheet_id,
                is_scored, criteria_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            class_id, cw_id, ctx.client_id, req.sourceSpreadsheetId or "",
            is_scored, criteria_json, now, now
        ))

        row = conn.execute("SELECT * FROM rubrics WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return _rubric_row_to_schema(dict(row))

@router.get("/v1/courses/{courseId}/courseWork/{courseWorkId}/rubrics/{id}", response_model=Rubric)
def get_rubric(courseId: str, courseWorkId: str, id: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSEWORK_STUDENTS, SCOPE_COURSEWORK_STUDENTS_READONLY, SCOPE_COURSES, SCOPE_COURSES_READONLY))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        assert_course_access(conn, class_id, ctx.user)

        try:
            cw_id = int(courseWorkId)
            rid = int(id)
        except ValueError:
            api_error(404, "NOT_FOUND", "Рубрика не найдена")

        row = conn.execute("SELECT * FROM rubrics WHERE id = ? AND coursework_id = ? AND class_id = ?", (rid, cw_id, class_id)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Рубрика не найдена")

        return _rubric_row_to_schema(dict(row))

@router.get("/v1/courses/{courseId}/courseWork/{courseWorkId}/rubrics", response_model=ListRubricsResponse)
def list_rubrics(courseId: str, courseWorkId: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSEWORK_STUDENTS, SCOPE_COURSEWORK_STUDENTS_READONLY, SCOPE_COURSES, SCOPE_COURSES_READONLY))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        assert_course_access(conn, class_id, ctx.user)

        try:
            cw_id = int(courseWorkId)
        except ValueError:
            api_error(404, "NOT_FOUND", "Задание не найдено")

        rows = conn.execute("SELECT * FROM rubrics WHERE coursework_id = ? AND class_id = ?", (cw_id, class_id)).fetchall()
        return ListRubricsResponse(
            rubrics=[_rubric_row_to_schema(dict(r)) for r in rows],
            nextPageToken=None,
        )

def _update_rubric_common(conn, cw_id: int, req: Rubric):
    row = conn.execute("SELECT * FROM rubrics WHERE coursework_id = ?", (cw_id,)).fetchone()
    if not row:
        api_error(404, "NOT_FOUND", "Рубрика не найдена")

    # Блокировка структуры: если хотя бы одной работе выставлены баллы по рубрике
    graded = conn.execute("""
        SELECT 1 FROM submissions
        WHERE coursework_id = ? AND (draft_rubric_json != '{}' OR assigned_rubric_json != '{}')
    """, (cw_id,)).fetchone()
    if graded:
        api_error(400, "FAILED_PRECONDITION", "Нельзя изменять структуру критериев, если уже выставлены оценки по рубрике")

    criteria = req.criteria or []
    is_scored = 1 if _validate_rubric_criteria(criteria) else 0

    criteria_dicts = [c.model_dump(exclude_none=True) if hasattr(c, "model_dump") else c for c in criteria]
    criteria_json = json.dumps(criteria_dicts, ensure_ascii=False)
    now = int(time.time())

    conn.execute("""
        UPDATE rubrics
        SET criteria_json = ?, is_scored = ?, updated_at = ?
        WHERE id = ?
    """, (criteria_json, is_scored, now, row["id"]))

    updated = conn.execute("SELECT * FROM rubrics WHERE id = ?", (row["id"],)).fetchone()
    return _rubric_row_to_schema(dict(updated))

@router.patch("/v1/courses/{courseId}/courseWork/{courseWorkId}/rubrics/{id}", response_model=Rubric)
def patch_rubric(courseId: str, courseWorkId: str, id: str, req: Rubric, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSEWORK_STUDENTS, SCOPE_COURSES))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для редактирования рубрики")

        try:
            cw_id = int(courseWorkId)
        except ValueError:
            api_error(404, "NOT_FOUND", "Задание не найдено")

        return _update_rubric_common(conn, cw_id, req)

@router.patch("/v1/courses/{courseId}/courseWork/{courseWorkId}/rubric", response_model=Rubric)
def update_rubric_alias(courseId: str, courseWorkId: str, req: Rubric, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSEWORK_STUDENTS, SCOPE_COURSES))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для редактирования рубрики")

        try:
            cw_id = int(courseWorkId)
        except ValueError:
            api_error(404, "NOT_FOUND", "Задание не найдено")

        return _update_rubric_common(conn, cw_id, req)

@router.delete("/v1/courses/{courseId}/courseWork/{courseWorkId}/rubrics/{id}", response_model=Empty)
def delete_rubric(courseId: str, courseWorkId: str, id: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSEWORK_STUDENTS, SCOPE_COURSES))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для удаления рубрики")

        try:
            cw_id = int(courseWorkId)
            rid = int(id)
        except ValueError:
            api_error(404, "NOT_FOUND", "Рубрика не найдена")

        row = conn.execute("SELECT id FROM rubrics WHERE id = ? AND coursework_id = ? AND class_id = ?", (rid, cw_id, class_id)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Рубрика не найдена")

        conn.execute("DELETE FROM rubrics WHERE id = ?", (rid,))
        return Empty()

# -----------------------------------------------------------------------------
# 8.3. Периоды обучения (courses.gradingPeriodSettings)
# -----------------------------------------------------------------------------

def _date_model_to_iso(d: Date) -> str:
    y = d.year or 2026
    m = d.month or 1
    day = d.day or 1
    return f"{y:04d}-{m:02d}-{day:02d}"

def _iso_to_date_model(s: str) -> Date:
    parts = s.split("-")
    return Date(year=int(parts[0]), month=int(parts[1]), day=int(parts[2]))

@router.get("/v1/courses/{courseId}/gradingPeriodSettings", response_model=GradingPeriodSettings)
def get_grading_period_settings(courseId: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSES, SCOPE_COURSES_READONLY))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        assert_course_access(conn, class_id, ctx.user)

        class_row = conn.execute("SELECT apply_periods_to_existing FROM classes WHERE id = ?", (class_id,)).fetchone()
        apply_flag = bool(class_row["apply_periods_to_existing"]) if class_row else False

        rows = conn.execute("""
            SELECT * FROM grading_periods
            WHERE class_id = ?
            ORDER BY sort_order ASC, start_date_iso ASC
        """, (class_id,)).fetchall()

        period_schemas = []
        for r in rows:
            period_schemas.append(GradingPeriod(
                id=str(r["id"]),
                title=r["period_title"],
                startDate=_iso_to_date_model(r["start_date_iso"]),
                endDate=_iso_to_date_model(r["end_date_iso"]),
            ))

        return GradingPeriodSettings(
            gradingPeriods=period_schemas,
            applyToExistingCoursework=apply_flag,
        )

@router.patch("/v1/courses/{courseId}/gradingPeriodSettings", response_model=GradingPeriodSettings)
def patch_grading_period_settings(courseId: str, req: GradingPeriodSettings, request: Request, updateMask: Optional[str] = None):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSES,))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для настройки периодов обучения")

        fields = parse_update_mask(updateMask, {"gradingPeriods", "applyToExistingCoursework"})

        apply_val = req.applyToExistingCoursework
        if "apply_to_existing_coursework" in fields or "applyToExistingCoursework" in fields:
            if apply_val is not None:
                conn.execute("UPDATE classes SET apply_periods_to_existing = ? WHERE id = ?", (1 if apply_val else 0, class_id))

        if "grading_periods" in fields or "gradingPeriods" in fields:
            periods = req.gradingPeriods or []
            parsed_periods = []
            seen_titles = set()

            for p in periods:
                title = (p.title or "").strip()
                if not title:
                    api_error(400, "INVALID_ARGUMENT", "Название периода обязательно")
                if title.lower() in seen_titles:
                    api_error(400, "INVALID_ARGUMENT", f"Период с названием '{title}' дублируется")
                seen_titles.add(title.lower())

                if not p.startDate or not p.endDate:
                    api_error(400, "INVALID_ARGUMENT", "Даты начала и окончания периода обязательны")

                start_iso = _date_model_to_iso(p.startDate)
                end_iso = _date_model_to_iso(p.endDate)

                if start_iso > end_iso:
                    api_error(400, "INVALID_ARGUMENT", f"Дата начала ({start_iso}) позже даты окончания ({end_iso}) в периоде '{title}'")

                parsed_periods.append({
                    "title": title,
                    "start": start_iso,
                    "end": end_iso,
                })

            # Проверка непересекающихся дат между периодами
            sorted_by_start = sorted(parsed_periods, key=lambda x: x["start"])
            for i in range(len(sorted_by_start) - 1):
                cur = sorted_by_start[i]
                nxt = sorted_by_start[i+1]
                if cur["end"] >= nxt["start"]:
                    api_error(400, "INVALID_ARGUMENT", f"Периоды '{cur['title']}' и '{nxt['title']}' пересекаются по датам")

            # Перезапись периодов в grading_periods
            conn.execute("DELETE FROM grading_periods WHERE class_id = ?", (class_id,))
            for idx, item in enumerate(sorted_by_start):
                conn.execute("""
                    INSERT INTO grading_periods (class_id, period_title, start_date_iso, end_date_iso, sort_order)
                    VALUES (?, ?, ?, ?, ?)
                """, (class_id, item["title"], item["start"], item["end"], idx))

            # Если applyToExistingCoursework: сопоставляем due_at с периодом
            class_row = conn.execute("SELECT apply_periods_to_existing FROM classes WHERE id = ?", (class_id,)).fetchone()
            if (apply_val is True) or (class_row and class_row["apply_periods_to_existing"] == 1):
                db_periods = conn.execute("SELECT * FROM grading_periods WHERE class_id = ?", (class_id,)).fetchall()
                cw_rows = conn.execute("SELECT id, due_at FROM coursework WHERE class_id = ? AND due_at IS NOT NULL", (class_id,)).fetchall()
                for cw in cw_rows:
                    dt_str = datetime.fromtimestamp(cw["due_at"], tz=timezone.utc).strftime("%Y-%m-%d")
                    matched_pid = None
                    for p in db_periods:
                        if p["start_date_iso"] <= dt_str <= p["end_date_iso"]:
                            matched_pid = p["id"]
                            break
                    if matched_pid:
                        conn.execute("UPDATE coursework SET grading_period_id = ? WHERE id = ?", (matched_pid, cw["id"]))

        class_row = conn.execute("SELECT apply_periods_to_existing FROM classes WHERE id = ?", (class_id,)).fetchone()
        apply_flag = bool(class_row["apply_periods_to_existing"]) if class_row else False

        rows = conn.execute("""
            SELECT * FROM grading_periods
            WHERE class_id = ?
            ORDER BY sort_order ASC, start_date_iso ASC
        """, (class_id,)).fetchall()

        period_schemas = []
        for r in rows:
            period_schemas.append(GradingPeriod(
                id=str(r["id"]),
                title=r["period_title"],
                startDate=_iso_to_date_model(r["start_date_iso"]),
                endDate=_iso_to_date_model(r["end_date_iso"]),
            ))

        return GradingPeriodSettings(
            gradingPeriods=period_schemas,
            applyToExistingCoursework=apply_flag,
        )

# Регистрация в глобальном v1_router
