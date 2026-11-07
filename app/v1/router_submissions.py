import json
import time
from typing import Optional, List, Any, Dict
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.db import db_session
from app.v1.protocol import (
    api_error,
    resolve_class_id,
    resolve_user_id,
    parse_update_mask,
    ts_to_rfc3339,
    encode_page_token,
    decode_page_token,
)
from app.v1.rbac import (
    resolve_auth_context,
    require_scopes,
    assert_course_access,
    assert_developer_project_match,
    SCOPE_COURSES,
    SCOPE_COURSEWORK_STUDENTS,
    SCOPE_COURSEWORK_STUDENTS_READONLY,
    SCOPE_COURSEWORK_ME,
    SCOPE_COURSEWORK_ME_READONLY,
)
from app.v1.schemas import (
    StudentSubmission,
    ListStudentSubmissionsResponse,
    ModifyAttachmentsRequest,
    TurnInStudentSubmissionRequest,
    ReclaimStudentSubmissionRequest,
    ReturnStudentSubmissionRequest,
    SubmissionHistory,
    StateHistory,
    GradeHistory,
    AssignmentSubmission,
    Attachment,
    ShortAnswerSubmission,
    MultipleChoiceSubmission,
    Empty,
)

router = APIRouter()

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def sync_submission_acl_safe(conn, coursework_id: int, student_id: int, new_v1_state: str):
    try:
        from app.storage.engine import sync_submission_acl
        sync_submission_acl(conn, coursework_id, student_id, new_v1_state)
    except (ImportError, AttributeError):
        pass

def _find_submission_row(conn, coursework_id: int, raw_id: str):
    try:
        sub_id = int(raw_id)
        row = conn.execute("SELECT * FROM submissions WHERE coursework_id = ? AND id = ?", (coursework_id, sub_id)).fetchone()
        if row:
            return row
    except ValueError:
        pass

    if "_" in raw_id:
        parts = raw_id.split("_")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            cw_id, s_id = int(parts[0]), int(parts[1])
            if cw_id == coursework_id:
                row = conn.execute("SELECT * FROM submissions WHERE coursework_id = ? AND student_id = ?", (cw_id, s_id)).fetchone()
                if row:
                    return row

    try:
        s_id = int(raw_id)
        row = conn.execute("SELECT * FROM submissions WHERE coursework_id = ? AND student_id = ?", (coursework_id, s_id)).fetchone()
        if row:
            return row
    except ValueError:
        pass

    return None

def _submission_row_to_schema(conn, row: dict, cw: dict, is_student: bool) -> StudentSubmission:
    cid = row["coursework_id"]
    sid = row["student_id"]

    sub_id = str(row["id"]) if row.get("id") else f"{cid}_{sid}"
    wtype = cw.get("work_type") or "ASSIGNMENT"

    # Вложения
    att_rows = conn.execute(
        "SELECT attachment_json FROM submission_attachments WHERE coursework_id = ? AND student_id = ?",
        (cid, sid)
    ).fetchall()
    attachments = []
    for ar in att_rows:
        try:
            attachments.append(Attachment(**json.loads(ar["attachment_json"])))
        except Exception:
            pass

    # История переходов и оценок
    hist_rows = conn.execute(
        "SELECT * FROM submission_history WHERE coursework_id = ? AND student_id = ? ORDER BY occurred_at ASC, id ASC",
        (cid, sid)
    ).fetchall()

    history_list = []
    for hr in hist_rows:
        ek = hr["entry_kind"]
        if ek == "STATE_CHANGE":
            history_list.append(SubmissionHistory(
                stateHistory=StateHistory(
                    state=hr["state_val"],
                    stateTimestamp=ts_to_rfc3339(hr["occurred_at"]),
                    actorUserId=str(hr["actor_user_id"]),
                )
            ))
        elif ek == "GRADE_CHANGE":
            history_list.append(SubmissionHistory(
                gradeHistory=GradeHistory(
                    pointsEarned=hr["points_earned"],
                    maxPoints=hr["max_points"],
                    gradeChangeType=hr["grade_change_type"],
                    actorUserId=str(hr["actor_user_id"]),
                    gradeTimestamp=ts_to_rfc3339(hr["occurred_at"]),
                )
            ))

    # Жёсткая фильтрация приватности: для STUDENT draftGrade скрыт (None) до момента return!
    draft_grade = None if is_student else row.get("draft_grade")
    draft_rubric = None
    if not is_student:
        try:
            draft_rubric = json.loads(row.get("draft_rubric_json") or "{}")
        except Exception:
            draft_rubric = {}

    assigned_rubric = {}
    try:
        assigned_rubric = json.loads(row.get("assigned_rubric_json") or "{}")
    except Exception:
        pass

    short_ans = None
    if wtype == "SHORT_ANSWER_QUESTION":
        short_ans = ShortAnswerSubmission(answer=row.get("short_answer_text") or "")

    mc_ans = None
    if wtype == "MULTIPLE_CHOICE_QUESTION":
        mc_ans = MultipleChoiceSubmission(answer=row.get("mc_answer_text") or "")

    return StudentSubmission(
        id=sub_id,
        courseId=str(cw["class_id"]),
        courseWorkId=str(cid),
        userId=str(sid),
        state=row.get("v1_state") or "NEW",
        late=bool(row.get("is_late", 0)),
        courseWorkType=wtype,
        creationTime=ts_to_rfc3339(row.get("created_at") or 0),
        updateTime=ts_to_rfc3339(row.get("updated_at") or 0),
        draftGrade=draft_grade,
        assignedGrade=row.get("assigned_grade"),
        draftRubricGrades=draft_rubric,
        assignedRubricGrades=assigned_rubric,
        assignmentSubmission=AssignmentSubmission(attachments=attachments),
        shortAnswerSubmission=short_ans,
        multipleChoiceSubmission=mc_ans,
        submissionHistory=history_list,
    )

# -----------------------------------------------------------------------------
# 8.1. Ресурс courses.courseWork.studentSubmissions
# -----------------------------------------------------------------------------

@router.get("/v1/courses/{courseId}/courseWork/{courseWorkId}/studentSubmissions/{id}", response_model=StudentSubmission)
def get_student_submission(courseId: str, courseWorkId: str, id: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (
            SCOPE_COURSEWORK_STUDENTS,
            SCOPE_COURSEWORK_STUDENTS_READONLY,
            SCOPE_COURSEWORK_ME,
            SCOPE_COURSEWORK_ME_READONLY,
        ))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)

        try:
            cw_id = int(courseWorkId)
        except ValueError:
            api_error(404, "NOT_FOUND", "Задание не найдено")

        cw = conn.execute("SELECT * FROM coursework WHERE id = ? AND class_id = ?", (cw_id, class_id)).fetchone()
        if not cw:
            api_error(404, "NOT_FOUND", "Задание не найдено")
        cw = dict(cw)

        row = _find_submission_row(conn, cw_id, id)
        if not row:
            api_error(404, "NOT_FOUND", "Работа не найдена")
        row = dict(row)

        is_student = (role == "STUDENT")
        if is_student and row["student_id"] != ctx.user["id"]:
            api_error(403, "PERMISSION_DENIED", "Нет доступа к работе другого ученика")

        return _submission_row_to_schema(conn, dict(row), dict(cw), is_student)

@router.get("/v1/courses/{courseId}/courseWork/{courseWorkId}/studentSubmissions", response_model=ListStudentSubmissionsResponse)
def list_student_submissions(
    courseId: str,
    courseWorkId: str,
    request: Request,
    userId: Optional[str] = None,
    states: Optional[str] = None,
    late: Optional[str] = None,
    pageSize: int = 30,
    pageToken: Optional[str] = None
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (
            SCOPE_COURSEWORK_STUDENTS,
            SCOPE_COURSEWORK_STUDENTS_READONLY,
            SCOPE_COURSEWORK_ME,
            SCOPE_COURSEWORK_ME_READONLY,
        ))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)

        is_student = (role == "STUDENT")
        target_uid = None
        if userId and userId != "-":
            target_uid = resolve_user_id(conn, userId, ctx.user, allow_wildcard=True)

        if is_student:
            target_uid = ctx.user["id"]

        limit = min(max(1, pageSize), 100)
        fingerprint = f"subs:{class_id}:{courseWorkId}:{target_uid}:{states}:{late}"
        offset = decode_page_token(pageToken, fingerprint)

        params: List[Any] = [class_id]
        where_clauses = ["cw.class_id = ?"]

        # Поддержка WILDCARD courseWorkId="-"
        if courseWorkId != "-":
            try:
                cw_id = int(courseWorkId)
                where_clauses.append("s.coursework_id = ?")
                params.append(cw_id)
            except ValueError:
                api_error(404, "NOT_FOUND", "Задание не найдено")

        if target_uid is not None and target_uid != "-":
            where_clauses.append("s.student_id = ?")
            params.append(target_uid)

        if states:
            state_list = [st.strip().upper() for st in states.split(",") if st.strip()]
            if state_list:
                placeholders = ",".join("?" for _ in state_list)
                where_clauses.append(f"s.v1_state IN ({placeholders})")
                params.extend(state_list)

        if late == "LATE_ONLY":
            where_clauses.append("s.is_late = 1")
        elif late == "NOT_LATE_ONLY":
            where_clauses.append("s.is_late = 0")

        query = f"""
            SELECT s.*, cw.class_id, cw.title as cw_title, cw.max_points,
                   cw.work_type, cw.modification_mode, cw.due_at, cw.creator_client_id
            FROM submissions s
            JOIN coursework cw ON s.coursework_id = cw.id
            WHERE {' AND '.join(where_clauses)}
            ORDER BY s.updated_at DESC, s.coursework_id ASC, s.student_id ASC
        """
        rows = conn.execute(query, params).fetchall()

        items = rows[offset: offset + limit]
        has_next = len(rows) > offset + limit
        next_token = encode_page_token(offset + limit, fingerprint) if has_next else None

        schemas = []
        for r in items:
            r_dict = dict(r)
            cw_dict = {
                "class_id": r_dict["class_id"],
                "work_type": r_dict["work_type"],
                "max_points": r_dict["max_points"],
            }
            schemas.append(_submission_row_to_schema(conn, r_dict, cw_dict, is_student))

        return ListStudentSubmissionsResponse(
            studentSubmissions=schemas,
            nextPageToken=next_token,
        )

@router.post("/v1/courses/{courseId}/courseWork/{courseWorkId}/studentSubmissions/{id}:modifyAttachments", response_model=StudentSubmission)
def modify_attachments(courseId: str, courseWorkId: str, id: str, req: ModifyAttachmentsRequest, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSEWORK_STUDENTS, SCOPE_COURSEWORK_ME, SCOPE_COURSES))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)

        try:
            cw_id = int(courseWorkId)
        except ValueError:
            api_error(404, "NOT_FOUND", "Задание не найдено")

        cw = conn.execute("SELECT * FROM coursework WHERE id = ? AND class_id = ?", (cw_id, class_id)).fetchone()
        if not cw:
            api_error(404, "NOT_FOUND", "Задание не найдено")
        cw = dict(cw)

        row = _find_submission_row(conn, cw_id, id)
        if not row:
            api_error(404, "NOT_FOUND", "Работа не найдена")
        row = dict(row)

        # Изменять вложения может только сам ученик
        if row["student_id"] != ctx.user["id"]:
            api_error(403, "PERMISSION_DENIED", "Только ученик может изменять свои вложения")

        now = int(time.time())
        # Проверка дедлайна при close_after_due
        if cw.get("close_after_due") == 1 and cw.get("due_at") is not None and now > cw["due_at"]:
            api_error(403, "PERMISSION_DENIED", "Задание закрыто для сдачи после дедлайна")

        current_state = row.get("v1_state") or "NEW"
        if current_state not in ("NEW", "CREATED", "RECLAIMED_BY_STUDENT", "RETURNED"):
            api_error(400, "FAILED_PRECONDITION", f"Нельзя добавлять вложения в состоянии {current_state}")

        new_state = current_state
        if current_state == "NEW":
            new_state = "CREATED"

        if req.addAttachments:
            for att in req.addAttachments:
                att_dict = att.model_dump(exclude_none=True) if hasattr(att, "model_dump") else att
                conn.execute("""
                    INSERT INTO submission_attachments (coursework_id, student_id, attachment_json, created_by_template, created_at)
                    VALUES (?, ?, ?, 0, ?)
                """, (cw_id, row["student_id"], json.dumps(att_dict, ensure_ascii=False), now))

        conn.execute("""
            UPDATE submissions
            SET v1_state = ?, updated_at = ?
            WHERE coursework_id = ? AND student_id = ?
        """, (new_state, now, cw_id, row["student_id"]))

        updated = conn.execute("SELECT * FROM submissions WHERE coursework_id = ? AND student_id = ?", (cw_id, row["student_id"])).fetchone()
        return _submission_row_to_schema(conn, dict(updated), dict(cw), is_student=True)

@router.post("/v1/courses/{courseId}/courseWork/{courseWorkId}/studentSubmissions/{id}:turnIn", response_model=Empty)
def turn_in_submission_v1(courseId: str, courseWorkId: str, id: str, request: Request, req: Optional[TurnInStudentSubmissionRequest] = None):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSEWORK_STUDENTS, SCOPE_COURSEWORK_ME, SCOPE_COURSES))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        assert_course_access(conn, class_id, ctx.user)

        try:
            cw_id = int(courseWorkId)
        except ValueError:
            api_error(404, "NOT_FOUND", "Задание не найдено")

        cw = conn.execute("SELECT * FROM coursework WHERE id = ? AND class_id = ?", (cw_id, class_id)).fetchone()
        if not cw:
            api_error(404, "NOT_FOUND", "Задание не найдено")
        cw = dict(cw)

        row = _find_submission_row(conn, cw_id, id)
        if not row:
            api_error(404, "NOT_FOUND", "Работа не найдена")
        row = dict(row)

        # Доступен ТОЛЬКО самому ученику
        if row["student_id"] != ctx.user["id"]:
            api_error(403, "PERMISSION_DENIED", "Сдать работу может только сам ученик")

        now = int(time.time())
        # Проверка дедлайна при close_after_due
        if cw.get("close_after_due") == 1 and cw.get("due_at") is not None and now > cw["due_at"]:
            api_error(403, "PERMISSION_DENIED", "Задание закрыто для сдачи после дедлайна")

        is_late = int(cw.get("due_at") is not None and now > cw["due_at"])

        conn.execute("""
            UPDATE submissions
            SET v1_state = 'TURNED_IN', status = 'turned_in', is_late = ?, updated_at = ?
            WHERE coursework_id = ? AND student_id = ?
        """, (is_late, now, cw_id, row["student_id"]))

        sync_submission_acl_safe(conn, cw_id, row["student_id"], "TURNED_IN")

        conn.execute("""
            INSERT INTO submission_history (
                coursework_id, student_id, entry_kind, state_val,
                actor_user_id, occurred_at
            ) VALUES (?, ?, 'STATE_CHANGE', 'TURNED_IN', ?, ?)
        """, (cw_id, row["student_id"], ctx.user["id"], now))

        return Empty()

@router.post("/v1/courses/{courseId}/courseWork/{courseWorkId}/studentSubmissions/{id}:reclaim", response_model=Empty)
def reclaim_submission_v1(courseId: str, courseWorkId: str, id: str, request: Request, req: Optional[ReclaimStudentSubmissionRequest] = None):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSEWORK_STUDENTS, SCOPE_COURSEWORK_ME, SCOPE_COURSES))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        assert_course_access(conn, class_id, ctx.user)

        try:
            cw_id = int(courseWorkId)
        except ValueError:
            api_error(404, "NOT_FOUND", "Задание не найдено")

        cw = conn.execute("SELECT * FROM coursework WHERE id = ? AND class_id = ?", (cw_id, class_id)).fetchone()
        if not cw:
            api_error(404, "NOT_FOUND", "Задание не найдено")
        cw = dict(cw)

        row = _find_submission_row(conn, cw_id, id)
        if not row:
            api_error(404, "NOT_FOUND", "Работа не найдена")
        row = dict(row)

        if row["student_id"] != ctx.user["id"]:
            api_error(403, "PERMISSION_DENIED", "Отозвать работу может только сам ученик")

        if row.get("v1_state") != "TURNED_IN":
            api_error(400, "FAILED_PRECONDITION", "Отозвать можно только сданную работу (TURNED_IN)")

        wtype = cw.get("work_type") or "ASSIGNMENT"
        mod_mode = cw.get("modification_mode") or "MODIFIABLE_UNTIL_TURNED_IN"
        if wtype != "ASSIGNMENT" and mod_mode != "MODIFIABLE":
            api_error(400, "FAILED_PRECONDITION", "Данный тип вопроса запрещает отзыв работы")

        now = int(time.time())
        conn.execute("""
            UPDATE submissions
            SET v1_state = 'RECLAIMED_BY_STUDENT', status = 'assigned', updated_at = ?
            WHERE coursework_id = ? AND student_id = ?
        """, (now, cw_id, row["student_id"]))

        sync_submission_acl_safe(conn, cw_id, row["student_id"], "RECLAIMED_BY_STUDENT")

        conn.execute("""
            INSERT INTO submission_history (
                coursework_id, student_id, entry_kind, state_val,
                actor_user_id, occurred_at
            ) VALUES (?, ?, 'STATE_CHANGE', 'RECLAIMED_BY_STUDENT', ?, ?)
        """, (cw_id, row["student_id"], ctx.user["id"], now))

        return Empty()

@router.patch("/v1/courses/{courseId}/courseWork/{courseWorkId}/studentSubmissions/{id}", response_model=StudentSubmission)
def patch_student_submission(courseId: str, courseWorkId: str, id: str, req: StudentSubmission, request: Request, updateMask: Optional[str] = None):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSEWORK_STUDENTS, SCOPE_COURSES))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для оценивания работ")

        try:
            cw_id = int(courseWorkId)
        except ValueError:
            api_error(404, "NOT_FOUND", "Задание не найдено")

        cw = conn.execute("SELECT * FROM coursework WHERE id = ? AND class_id = ?", (cw_id, class_id)).fetchone()
        if not cw:
            api_error(404, "NOT_FOUND", "Задание не найдено")
        cw = dict(cw)

        row = _find_submission_row(conn, cw_id, id)
        if not row:
            api_error(404, "NOT_FOUND", "Работа не найдена")
        row = dict(row)

        assert_developer_project_match(ctx, cw.get("creator_client_id") or "first_party")
        fields = parse_update_mask(updateMask, {"draftGrade", "assignedGrade", "draftRubricGrades", "assignedRubricGrades"})

        now = int(time.time())
        updates = ["updated_at = ?"]
        params = [now]

        if "draft_grade" in fields or "draftGrade" in fields:
            dg = float(req.draftGrade) if req.draftGrade is not None else None
            updates.append("draft_grade = ?")
            params.append(dg)
            conn.execute("""
                INSERT INTO submission_history (
                    coursework_id, student_id, entry_kind, grade_change_type,
                    points_earned, max_points, actor_user_id, occurred_at
                ) VALUES (?, ?, 'GRADE_CHANGE', 'DRAFT_GRADE_POINTS_EARNED_CHANGE', ?, ?, ?, ?)
            """, (cw_id, row["student_id"], dg, cw["max_points"], ctx.user["id"], now))

        if "assigned_grade" in fields or "assignedGrade" in fields:
            ag = float(req.assignedGrade) if req.assignedGrade is not None else None
            updates.append("assigned_grade = ?")
            params.append(ag)
            conn.execute("""
                INSERT INTO submission_history (
                    coursework_id, student_id, entry_kind, grade_change_type,
                    points_earned, max_points, actor_user_id, occurred_at
                ) VALUES (?, ?, 'GRADE_CHANGE', 'ASSIGNED_GRADE_POINTS_EARNED_CHANGE', ?, ?, ?, ?)
            """, (cw_id, row["student_id"], ag, cw["max_points"], ctx.user["id"], now))

        if "draft_rubric_grades" in fields or "draftRubricGrades" in fields:
            drg_str = json.dumps(req.draftRubricGrades or {}, ensure_ascii=False)
            updates.append("draft_rubric_json = ?")
            params.append(drg_str)

        if "assigned_rubric_grades" in fields or "assignedRubricGrades" in fields:
            arg_str = json.dumps(req.assignedRubricGrades or {}, ensure_ascii=False)
            updates.append("assigned_rubric_json = ?")
            params.append(arg_str)

        params.extend([cw_id, row["student_id"]])
        conn.execute(f"UPDATE submissions SET {', '.join(updates)} WHERE coursework_id = ? AND student_id = ?", params)

        updated = conn.execute("SELECT * FROM submissions WHERE coursework_id = ? AND student_id = ?", (cw_id, row["student_id"])).fetchone()
        return _submission_row_to_schema(conn, dict(updated), dict(cw), is_student=False)

@router.post("/v1/courses/{courseId}/courseWork/{courseWorkId}/studentSubmissions/{id}:return", response_model=Empty)
def return_submission_v1(courseId: str, courseWorkId: str, id: str, request: Request, req: Optional[ReturnStudentSubmissionRequest] = None):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSEWORK_STUDENTS, SCOPE_COURSES))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для возврата работ")

        try:
            cw_id = int(courseWorkId)
        except ValueError:
            api_error(404, "NOT_FOUND", "Задание не найдено")

        cw = conn.execute("SELECT * FROM coursework WHERE id = ? AND class_id = ?", (cw_id, class_id)).fetchone()
        if not cw:
            api_error(404, "NOT_FOUND", "Задание не найдено")
        cw = dict(cw)

        row = _find_submission_row(conn, cw_id, id)
        if not row:
            api_error(404, "NOT_FOUND", "Работа не найдена")
        row = dict(row)

        now = int(time.time())
        # При возврате: assigned_grade = draft_grade, assigned_rubric_json = draft_rubric_json
        assigned_grade = row["draft_grade"] if row["draft_grade"] is not None else row["assigned_grade"]
        assigned_rubric = row["draft_rubric_json"] if row["draft_rubric_json"] != "{}" else row["assigned_rubric_json"]

        conn.execute("""
            UPDATE submissions
            SET v1_state = 'RETURNED', status = 'returned',
                assigned_grade = ?, assigned_rubric_json = ?,
                grade_points = ?, updated_at = ?
            WHERE coursework_id = ? AND student_id = ?
        """, (
            assigned_grade, assigned_rubric,
            int(assigned_grade) if assigned_grade is not None else None,
            now, cw_id, row["student_id"]
        ))

        sync_submission_acl_safe(conn, cw_id, row["student_id"], "RETURNED")

        conn.execute("""
            INSERT INTO submission_history (
                coursework_id, student_id, entry_kind, state_val,
                actor_user_id, occurred_at
            ) VALUES (?, ?, 'STATE_CHANGE', 'RETURNED', ?, ?)
        """, (cw_id, row["student_id"], ctx.user["id"], now))

        # Уведомление ученику
        conn.execute("""
            INSERT INTO notifications (user_id, class_id, notif_kind, title, body_text, link_path, is_read, created_at)
            VALUES (?, ?, 'submission_returned', 'Работа проверена', ?, ?, 0, ?)
        """, (
            row["student_id"], class_id,
            f"Учитель вернул вашу работу по заданию «{cw['title']}»",
            f"/classes/{class_id}/coursework/{cw_id}",
            now
        ))

        return Empty()

class BatchReturnRequest(BaseModel):
    comment: Optional[str] = None

@router.post("/api/classroom/classes/{class_id}/coursework/{cw_id}/batch-return")
def batch_return_submissions(class_id: int, cw_id: int, req: BatchReturnRequest, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для массового возврата работ")

        cw = conn.execute("SELECT * FROM coursework WHERE id = ? AND class_id = ?", (cw_id, class_id)).fetchone()
        if not cw:
            api_error(404, "NOT_FOUND", "Задание не найдено")

        subs_to_return = conn.execute("""
            SELECT * FROM submissions
            WHERE coursework_id = ? AND draft_grade IS NOT NULL
        """, (cw_id,)).fetchall()

        now = int(time.time())
        returned_count = 0

        for row in subs_to_return:
            sid = row["student_id"]
            assigned_grade = row["draft_grade"]
            assigned_rubric = row["draft_rubric_json"]
            t_comment = req.comment if req.comment else row["teacher_comment"]

            conn.execute("""
                UPDATE submissions
                SET v1_state = 'RETURNED', status = 'returned',
                    assigned_grade = ?, assigned_rubric_json = ?,
                    grade_points = ?, teacher_comment = ?, updated_at = ?
                WHERE coursework_id = ? AND student_id = ?
            """, (assigned_grade, assigned_rubric, int(assigned_grade), t_comment, now, cw_id, sid))

            sync_submission_acl_safe(conn, cw_id, sid, "RETURNED")

            conn.execute("""
                INSERT INTO submission_history (
                    coursework_id, student_id, entry_kind, state_val,
                    actor_user_id, occurred_at
                ) VALUES (?, ?, 'STATE_CHANGE', 'RETURNED', ?, ?)
            """, (cw_id, sid, ctx.user["id"], now))

            conn.execute("""
                INSERT INTO notifications (user_id, class_id, notif_kind, title, body_text, link_path, is_read, created_at)
                VALUES (?, ?, 'submission_returned', 'Работа проверена', ?, ?, 0, ?)
            """, (
                sid, class_id,
                f"Учитель вернул вашу работу по заданию «{cw['title']}»",
                f"/classes/{class_id}/coursework/{cw_id}",
                now
            ))
            returned_count += 1

        return {"ok": True, "returned_count": returned_count}

# Регистрация в глобальном v1_router
