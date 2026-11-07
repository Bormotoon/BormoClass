import io
import csv
import json
import time
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, HTTPException, status, Response
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

class GradeRubricRequest(BaseModel):
    criteria_scores: Dict[str, Any] = Field(default_factory=dict)
    teacher_comment: Optional[str] = None

class ExcuseRequest(BaseModel):
    is_excused: bool = True

class GradeCategoryItem(BaseModel):
    id: Optional[int] = None
    category_title: str
    default_denominator: int = 100
    weight_micros: int = 0

class GradebookSettingsUpdateRequest(BaseModel):
    grade_calc_type: Optional[str] = Field(default=None, pattern="^(TOTAL_POINTS|WEIGHTED_CATEGORIES)$")
    grade_display_setting: Optional[str] = Field(default=None, pattern="^(SHOW_OVERALL_GRADE|HIDE_OVERALL_GRADE|SHOW_TEACHERS_ONLY)$")
    categories: Optional[List[GradeCategoryItem]] = None

class RubricImportRequest(BaseModel):
    coursework_id: int
    rubric_json: Optional[str] = None
    csv_content: Optional[str] = None

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
            SELECT cw.id, cw.class_id, cw.recess_reward, cw.state, cw.due_at, cw.close_after_due, c.teacher_id
            FROM coursework cw
            JOIN classes c ON cw.class_id = c.id
            WHERE cw.id = ?
        """, (coursework_id,)).fetchone()

        if not cw or cw["state"] != "published":
            raise HTTPException(status_code=404, detail="Задание не найдено или закрыто")
        cw = dict(cw)

        if cw.get("close_after_due") == 1 and cw.get("due_at") is not None and now > cw["due_at"]:
            raise HTTPException(status_code=403, detail="Задание закрыто для сдачи после дедлайна")

        is_late = int(cw.get("due_at") is not None and now > cw["due_at"])

        existing = conn.execute("""
            SELECT status FROM submissions
            WHERE coursework_id = ? AND student_id = ?
        """, (coursework_id, student_id)).fetchone()

        awarded_recess = False
        if not existing:
            conn.execute("""
                INSERT INTO submissions (coursework_id, student_id, status, v1_state, is_late, payload_json, updated_at)
                VALUES (?, ?, 'turned_in', 'TURNED_IN', ?, ?, ?)
            """, (coursework_id, student_id, is_late, req.payload_json, now))
            award_recess_seconds(conn, student_id, cw["recess_reward"])
            awarded_recess = True
        elif existing["status"] == "assigned":
            conn.execute("""
                UPDATE submissions
                SET status = 'turned_in', v1_state = 'TURNED_IN', is_late = ?, payload_json = ?, updated_at = ?
                WHERE coursework_id = ? AND student_id = ?
            """, (is_late, req.payload_json, now, coursework_id, student_id))
            award_recess_seconds(conn, student_id, cw["recess_reward"])
            awarded_recess = True
        else:
            # Повторная сдача - обновляем ответ без повторного начисления секунд
            conn.execute("""
                UPDATE submissions
                SET status = 'turned_in', v1_state = 'TURNED_IN', is_late = ?, payload_json = ?, updated_at = ?
                WHERE coursework_id = ? AND student_id = ?
            """, (is_late, req.payload_json, now, coursework_id, student_id))

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

        # Если grade_five не указан явно, но есть grade_points, рассчитываем по шкале РФ
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
                coursework_id, student_id, status, v1_state, rubric_scores,
                grade_points, grade_five, draft_grade, assigned_grade,
                teacher_comment, updated_at
            ) VALUES (?, ?, 'returned', 'RETURNED', ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(coursework_id, student_id) DO UPDATE SET
                status = 'returned',
                v1_state = 'RETURNED',
                rubric_scores = excluded.rubric_scores,
                grade_points = excluded.grade_points,
                grade_five = excluded.grade_five,
                draft_grade = excluded.draft_grade,
                assigned_grade = excluded.assigned_grade,
                teacher_comment = excluded.teacher_comment,
                updated_at = excluded.updated_at
        """, (
            coursework_id, student_id, req.rubric_scores or "{}",
            req.grade_points, grade_five,
            float(req.grade_points) if req.grade_points is not None else None,
            float(req.grade_points) if req.grade_points is not None else None,
            req.teacher_comment or "", now
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
        return {
            "ok": True,
            "grade_calc_type": calc_type,
            "grade_display_setting": req.grade_display_setting or class_row["grade_display_setting"]
        }

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

        subs_map = {f"{s['coursework_id']}_{s['student_id']}": dict(s) for s in subs}
        all_grades = [s["grade_five"] for s in subs if s["grade_five"] in (2, 3, 4, 5)]
        summary_analytics = calculate_sou_metrics(all_grades)

        return {
            "students": students_list,
            "coursework": [dict(c) for c in courseworks],
            "submissions": subs_map,
            "analytics": summary_analytics
        }

# -----------------------------------------------------------------------------
# 8.2 & 8.3. Рубрики (SpeedGrader), Экспорт/Импорт, Настройки журнала и Gradebook
# -----------------------------------------------------------------------------

@router.post("/coursework/{cw_id}/submissions/{student_id}/grade-rubric")
def grade_rubric(cw_id: int, student_id: int, req: GradeRubricRequest, request: Request):
    user = require_teacher(request)
    now = int(time.time())

    with db_session() as conn:
        cw = conn.execute("SELECT class_id, max_points FROM coursework WHERE id = ?", (cw_id,)).fetchone()
        if not cw:
            raise HTTPException(status_code=404, detail="Задание не найдено")

        # Суммируем баллы по критериям
        total_points = 0.0
        for crit_id, val in req.criteria_scores.items():
            if isinstance(val, dict):
                pts = val.get("points", 0.0)
            elif isinstance(val, (int, float)):
                pts = float(val)
            else:
                pts = 0.0
            total_points += float(pts)

        rubric_json_str = json.dumps(req.criteria_scores, ensure_ascii=False)
        conn.execute("""
            INSERT INTO submissions (
                coursework_id, student_id, draft_grade, draft_rubric_json,
                teacher_comment, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(coursework_id, student_id) DO UPDATE SET
                draft_grade = excluded.draft_grade,
                draft_rubric_json = excluded.draft_rubric_json,
                teacher_comment = COALESCE(NULLIF(excluded.teacher_comment, ''), submissions.teacher_comment),
                updated_at = excluded.updated_at
        """, (cw_id, student_id, total_points, rubric_json_str, req.teacher_comment or "", now))

        return {
            "ok": True,
            "draft_grade": total_points,
            "rubric_scores": req.criteria_scores,
        }

@router.get("/rubrics/{id}/export.csv")
def export_rubric_csv(id: int, request: Request):
    require_user(request)
    with db_session() as conn:
        row = conn.execute("SELECT * FROM rubrics WHERE id = ?", (id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Рубрика не найдена")

        criteria = []
        try:
            criteria = json.loads(row["criteria_json"])
        except Exception:
            pass

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Criterion ID", "Criterion Title", "Criterion Description", "Level Title", "Points", "Level Description"])

        for c in criteria:
            cid = c.get("id", "")
            ctitle = c.get("title", "")
            cdesc = c.get("description", "")
            levels = c.get("levels", [])
            if not levels:
                writer.writerow([cid, ctitle, cdesc, "", "", ""])
            for lvl in levels:
                writer.writerow([
                    cid, ctitle, cdesc,
                    lvl.get("title", ""),
                    lvl.get("points", ""),
                    lvl.get("description", "")
                ])

        csv_data = output.getvalue()
        return Response(content=csv_data, media_type="text/csv", headers={
            "Content-Disposition": f"attachment; filename=rubric_{id}.csv"
        })

@router.post("/classes/{class_id}/rubrics/import")
def import_rubric(class_id: int, req: RubricImportRequest, request: Request):
    user = require_teacher(request)
    now = int(time.time())

    criteria = []
    if req.rubric_json:
        try:
            criteria = json.loads(req.rubric_json)
        except Exception:
            raise HTTPException(status_code=400, detail="Неверный JSON формат рубрики")
    elif req.csv_content:
        reader = csv.reader(io.StringIO(req.csv_content))
        header = next(reader, None)
        crit_map = {}
        for row in reader:
            if not row or len(row) < 2:
                continue
            cid = row[0].strip() or f"c_{len(crit_map)+1}"
            ctitle = row[1].strip()
            cdesc = row[2].strip() if len(row) > 2 else ""
            ltitle = row[3].strip() if len(row) > 3 else ""
            pts = float(row[4].strip()) if len(row) > 4 and row[4].strip() else None
            ldesc = row[5].strip() if len(row) > 5 else ""

            if cid not in crit_map:
                crit_map[cid] = {"id": cid, "title": ctitle, "description": cdesc, "levels": []}
            if ltitle or pts is not None:
                crit_map[cid]["levels"].append({
                    "id": f"l_{len(crit_map[cid]['levels'])+1}",
                    "title": ltitle,
                    "points": pts,
                    "description": ldesc
                })
        criteria = list(crit_map.values())

    if not criteria:
        raise HTTPException(status_code=400, detail="Не удалось извлечь критерии из переданных данных")

    with db_session() as conn:
        conn.execute("""
            INSERT INTO rubrics (
                class_id, coursework_id, creator_client_id, is_scored,
                criteria_json, created_at, updated_at
            ) VALUES (?, ?, 'first_party', 1, ?, ?, ?)
            ON CONFLICT(coursework_id) DO UPDATE SET
                criteria_json = excluded.criteria_json,
                updated_at = excluded.updated_at
        """, (class_id, req.coursework_id, json.dumps(criteria, ensure_ascii=False), now, now))

        return {"ok": True, "criteria_count": len(criteria)}

@router.patch("/classes/{class_id}/gradebook-settings")
def update_gradebook_settings(class_id: int, req: GradebookSettingsUpdateRequest, request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        class_row = conn.execute("SELECT teacher_id, grade_calc_type FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not class_row or (class_row["teacher_id"] != user["user_id"] and user["role"] != "admin"):
            raise HTTPException(status_code=403, detail="Нет прав на настройку журнала")

        calc_type = req.grade_calc_type or class_row["grade_calc_type"]

        # Если WEIGHTED_CATEGORIES, сумма weight_micros обязана быть 1_000_000
        if req.categories is not None:
            if calc_type == "WEIGHTED_CATEGORIES":
                total_weight = sum(c.weight_micros for c in req.categories)
                if total_weight != 1_000_000:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Сумма весов категорий должна равняться 1 000 000 (100%), получено {total_weight}"
                    )

            conn.execute("DELETE FROM grade_categories WHERE class_id = ?", (class_id,))
            for cat in req.categories:
                conn.execute("""
                    INSERT INTO grade_categories (class_id, category_title, default_denominator, weight_micros)
                    VALUES (?, ?, ?, ?)
                """, (class_id, cat.category_title.strip(), cat.default_denominator, cat.weight_micros))

        updates = []
        params = []
        if req.grade_calc_type is not None:
            updates.append("grade_calc_type = ?")
            params.append(req.grade_calc_type)
        if req.grade_display_setting is not None:
            updates.append("grade_display_setting = ?")
            params.append(req.grade_display_setting)

        if updates:
            params.append(class_id)
            conn.execute(f"UPDATE classes SET {', '.join(updates)} WHERE id = ?", params)

        return {
            "ok": True,
            "grade_calc_type": calc_type,
            "grade_display_setting": req.grade_display_setting or class_row["grade_display_setting"]
        }

@router.post("/coursework/{cw_id}/submissions/{student_id}/excuse")
def set_submission_excused(cw_id: int, student_id: int, req: ExcuseRequest, request: Request):
    user = require_teacher(request)
    now = int(time.time())
    with db_session() as conn:
        excused_val = 1 if req.is_excused else 0
        conn.execute("""
            INSERT INTO submissions (coursework_id, student_id, is_excused, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(coursework_id, student_id) DO UPDATE SET
                is_excused = excluded.is_excused,
                updated_at = excluded.updated_at
        """, (cw_id, student_id, excused_val, now))
        return {"ok": True, "is_excused": req.is_excused}

@router.get("/classes/{class_id}/gradebook")
def get_gradebook(class_id: int, request: Request, grading_period_id: Optional[int] = None):
    user = require_user(request)
    is_teacher = user["role"] in ("teacher", "admin")

    with db_session() as conn:
        class_row = conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not class_row:
            raise HTTPException(status_code=404, detail="Класс не найден")
        class_dict = dict(class_row)

        grade_calc_type = class_dict.get("grade_calc_type") or "TOTAL_POINTS"
        grade_display_setting = class_dict.get("grade_display_setting") or "SHOW_OVERALL_GRADE"

        # 1. Ученики
        members = conn.execute("""
            SELECT cm.student_id, cm.seat_number, u.handle, u.avatar_seed
            FROM class_members cm
            JOIN users u ON cm.student_id = u.id
            WHERE cm.class_id = ? AND cm.enrollment_active = 1
            ORDER BY cm.seat_number ASC, u.handle ASC
        """, (class_id,)).fetchall()

        # 2. Задания (с фильтром по периоду)
        cw_query = """
            SELECT id, title, kind, max_points, grade_category_id, grading_period_id, due_at
            FROM coursework
            WHERE class_id = ? AND state = 'published' AND kind IN ('assignment', 'quiz', 'question')
        """
        cw_params: List[Any] = [class_id]
        if grading_period_id:
            cw_query += " AND grading_period_id = ?"
            cw_params.append(grading_period_id)
        cw_query += " ORDER BY created_at ASC"

        courseworks = [dict(c) for c in conn.execute(cw_query, cw_params).fetchall()]
        cw_ids = [c["id"] for c in courseworks]

        # 3. Категории оценок
        categories = conn.execute("SELECT * FROM grade_categories WHERE class_id = ?", (class_id,)).fetchall()
        cat_map = {c["id"]: dict(c) for c in categories}

        # 4. Сдачи
        subs_map = {}
        if cw_ids:
            placeholders = ",".join("?" for _ in cw_ids)
            sub_rows = conn.execute(f"""
                SELECT * FROM submissions WHERE coursework_id IN ({placeholders})
            """, cw_ids).fetchall()
            for s in sub_rows:
                subs_map[(s["coursework_id"], s["student_id"])] = dict(s)

        # 5. Расчет средних по каждому заданию
        cw_averages = {}
        all_five_grades = []
        for cw in courseworks:
            cw_id = cw["id"]
            pts_list = []
            for m in members:
                sub = subs_map.get((cw_id, m["student_id"]))
                if sub and not sub.get("is_excused"):
                    score = sub.get("assigned_grade")
                    if score is not None:
                        pts_list.append(score)
                    if sub.get("grade_five") in (2, 3, 4, 5):
                        all_five_grades.append(sub["grade_five"])
            cw_averages[cw_id] = round(sum(pts_list) / len(pts_list), 1) if pts_list else None

        # 6. Расчет общего процента по каждому ученику
        students_report = []
        for m in members:
            stu_id = m["student_id"]
            earned_total = 0.0
            max_total = 0.0

            # Для WEIGHTED_CATEGORIES: группируем по категориям
            cat_scores: Dict[int, Dict[str, float]] = {}

            student_grades = {}
            for cw in courseworks:
                cw_id = cw["id"]
                sub = subs_map.get((cw_id, stu_id))
                score = None
                is_exc = False
                five = None
                if sub:
                    score = sub.get("assigned_grade")
                    is_exc = bool(sub.get("is_excused", 0))
                    five = sub.get("grade_five")

                student_grades[cw_id] = {
                    "assigned_grade": score,
                    "is_excused": is_exc,
                    "grade_five": five,
                }

                if not is_exc and score is not None:
                    mx = float(cw["max_points"] or 100)
                    if grade_calc_type == "TOTAL_POINTS":
                        earned_total += score
                        max_total += mx
                    elif grade_calc_type == "WEIGHTED_CATEGORIES":
                        cat_id = cw.get("grade_category_id") or 0
                        if cat_id not in cat_scores:
                            cat_scores[cat_id] = {"earned": 0.0, "max": 0.0}
                        cat_scores[cat_id]["earned"] += score
                        cat_scores[cat_id]["max"] += mx

            overall_pct = None
            if grade_calc_type == "TOTAL_POINTS":
                if max_total > 0:
                    overall_pct = round((earned_total / max_total) * 100.0, 1)
            elif grade_calc_type == "WEIGHTED_CATEGORIES":
                # Нормировка весов для категорий, где есть оценённые работы
                active_cats = {cid: data for cid, data in cat_scores.items() if data["max"] > 0 and cid in cat_map}
                sum_active_weights = sum(cat_map[cid]["weight_micros"] for cid in active_cats)
                if sum_active_weights > 0:
                    weighted_sum = 0.0
                    for cid, data in active_cats.items():
                        cat_pct = (data["earned"] / data["max"]) * 100.0
                        norm_weight = cat_map[cid]["weight_micros"] / sum_active_weights
                        weighted_sum += cat_pct * norm_weight
                    overall_pct = round(weighted_sum, 1)

            # Проверка настройки видимости итогового балла
            if not is_teacher and grade_display_setting == "HIDE_OVERALL_GRADE":
                overall_pct = None

            students_report.append({
                "student_id": stu_id,
                "handle": m["handle"],
                "seat_number": m["seat_number"],
                "avatar_seed": m["avatar_seed"],
                "grades": student_grades,
                "overall_percent": overall_pct,
            })

        metrics = calculate_sou_metrics(all_five_grades)

        return {
            "grade_calc_type": grade_calc_type,
            "grade_display_setting": grade_display_setting,
            "courseworks": [dict(c) for c in courseworks],
            "coursework_averages": cw_averages,
            "categories": [dict(c) for c in categories],
            "students": students_report,
            "analytics": metrics,
        }

# Подключение роутеров v1
import app.v1.router_submissions
import app.v1.router_rubrics_grades
