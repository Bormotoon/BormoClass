import re
import json
import time
from typing import Optional, List, Any
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.db import db_session
from app.v1.protocol import (
    api_error,
    resolve_class_id,
    resolve_user_id,
    parse_update_mask,
    ts_to_rfc3339,
    rfc3339_to_ts,
    date_to_dict,
    time_of_day_to_dict,
    date_time_to_ts,
    encode_page_token,
    decode_page_token,
)
from app.v1.rbac import (
    resolve_auth_context,
    require_scopes,
    get_course_role,
    assert_course_access,
    assert_developer_project_match,
    SCOPE_COURSES,
    SCOPE_COURSES_READONLY,
    SCOPE_TOPICS,
    SCOPE_TOPICS_READONLY,
    SCOPE_COURSEWORKMATERIALS,
    SCOPE_COURSEWORKMATERIALS_READONLY,
    SCOPE_COURSEWORK_STUDENTS,
    SCOPE_COURSEWORK_STUDENTS_READONLY,
    SCOPE_COURSEWORK_ME,
    SCOPE_COURSEWORK_ME_READONLY,
)
from app.v1.schemas import (
    Topic,
    ListTopicResponse,
    CourseWorkMaterial,
    ListCourseWorkMaterialResponse,
    CourseWork,
    ListCourseWorkResponse,
    ModifyCourseWorkAssigneesRequest,
    Empty,
    Date,
    TimeOfDay,
    Assignment,
    DriveFolder,
    MultipleChoiceQuestion,
    IndividualStudentsOptions,
)

router = APIRouter()

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _normalize_topic_title(raw_title: Optional[str]) -> str:
    if not raw_title or not raw_title.strip():
        api_error(400, "INVALID_ARGUMENT", "Название темы не может быть пустым", reason="INVALID_ARGUMENT")
    cleaned = re.sub(r"\s+", " ", raw_title.strip())
    if len(cleaned) < 1 or len(cleaned) > 100:
        api_error(400, "INVALID_ARGUMENT", "Длина темы должна быть от 1 до 100 символов", reason="INVALID_ARGUMENT")
    return cleaned

def _topic_row_to_schema(row: dict) -> Topic:
    return Topic(
        topicId=str(row["id"]),
        courseId=str(row["class_id"]),
        name=row["title"],
        updateTime=ts_to_rfc3339(row.get("updated_at") or 0),
    )

def _cwm_row_to_schema(row: dict) -> CourseWorkMaterial:
    materials_list = []
    try:
        materials_list = json.loads(row.get("materials_json") or "[]")
    except Exception:
        pass

    target_students = []
    try:
        target_students = json.loads(row.get("target_students_json") or "[]")
    except Exception:
        pass

    ind_opts = None
    if row.get("assignee_mode") == "INDIVIDUAL_STUDENTS":
        ind_opts = IndividualStudentsOptions(studentIds=[str(s) for s in target_students])

    return CourseWorkMaterial(
        id=str(row["id"]),
        courseId=str(row["class_id"]),
        title=row["title"],
        description=row.get("description") or "",
        state=row.get("state") or "PUBLISHED",
        topicId=str(row["topic_id"]) if row.get("topic_id") else None,
        creatorUserId=str(row["creator_user_id"]) if row.get("creator_user_id") else None,
        assigneeMode=row.get("assignee_mode") or "ALL_STUDENTS",
        individualStudentsOptions=ind_opts,
        materials=materials_list,
        creationTime=ts_to_rfc3339(row.get("created_at") or 0),
        updateTime=ts_to_rfc3339(row.get("updated_at") or 0),
        scheduledTime=ts_to_rfc3339(row.get("scheduled_at")),
    )

def _cw_row_to_schema(row: dict) -> CourseWork:
    materials_list = []
    try:
        materials_list = json.loads(row.get("attachments_json") or "[]")
    except Exception:
        pass

    target_students = []
    try:
        ts_val = row.get("target_students") or "all"
        if ts_val != "all":
            target_students = json.loads(ts_val)
    except Exception:
        pass

    ind_opts = None
    if row.get("assignee_mode") == "INDIVIDUAL_STUDENTS":
        ind_opts = IndividualStudentsOptions(studentIds=[str(s) for s in target_students])

    wtype = row.get("work_type") or "ASSIGNMENT"

    mc_obj = None
    if wtype == "MULTIPLE_CHOICE_QUESTION":
        choices = []
        try:
            choices = json.loads(row.get("choices_json") or "[]")
        except Exception:
            pass
        mc_obj = MultipleChoiceQuestion(choices=choices)

    assign_obj = None
    if wtype == "ASSIGNMENT":
        assign_obj = Assignment(
            studentWorkFolder=DriveFolder(
                id=f"folder_cw_{row['id']}",
                title=row.get("title") or "Assignment",
            )
        )

    due_ts = row.get("due_at")
    due_date = date_to_dict(due_ts)
    due_time = time_of_day_to_dict(due_ts)

    max_pts = float(row["max_points"]) if row.get("max_points") is not None else None

    return CourseWork(
        id=str(row["id"]),
        courseId=str(row["class_id"]),
        title=row["title"],
        description=row.get("instructions") or "",
        state=(row.get("state") or "PUBLISHED").upper(),
        workType=wtype,
        submissionModificationMode=row.get("modification_mode") or "MODIFIABLE_UNTIL_TURNED_IN",
        assigneeMode=row.get("assignee_mode") or "ALL_STUDENTS",
        individualStudentsOptions=ind_opts,
        maxPoints=max_pts,
        dueDate=Date(**due_date) if due_date else None,
        dueTime=TimeOfDay(**due_time) if due_time else None,
        scheduledTime=ts_to_rfc3339(row.get("scheduled_at")),
        topicId=str(row["topic_id"]) if row.get("topic_id") else None,
        gradingPeriodId=str(row["grading_period_id"]) if row.get("grading_period_id") else None,
        materials=materials_list,
        assignment=assign_obj,
        multipleChoiceQuestion=mc_obj,
        creationTime=ts_to_rfc3339(row.get("created_at") or 0),
        updateTime=ts_to_rfc3339(row.get("updated_at") or 0),
    )

def _populate_v1_submissions(conn, coursework_id: int, class_id: int, assignee_mode: str, target_students_val: str):
    now = int(time.time())
    if assignee_mode == "ALL_STUDENTS" or target_students_val == "all":
        students = conn.execute("SELECT student_id FROM class_members WHERE class_id = ? AND enrollment_active = 1", (class_id,)).fetchall()
        student_ids = [s["student_id"] for s in students]
    else:
        try:
            student_ids = json.loads(target_students_val)
        except Exception:
            student_ids = []

    for sid in student_ids:
        conn.execute("""
            INSERT OR IGNORE INTO submissions (coursework_id, student_id, status, v1_state, created_at, updated_at)
            VALUES (?, ?, 'assigned', 'NEW', ?, ?)
        """, (coursework_id, sid, now, now))

# -----------------------------------------------------------------------------
# 7.1. Темы курса (courses.topics)
# -----------------------------------------------------------------------------

@router.post("/v1/courses/{courseId}/topics", response_model=Topic)
def create_topic(courseId: str, req: Topic, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_TOPICS, SCOPE_COURSES))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для создания тем в данном курсе")

        title = _normalize_topic_title(req.name)
        existing = conn.execute(
            "SELECT id, title FROM class_topics WHERE class_id = ?",
            (class_id,)
        ).fetchall()
        for ex in existing:
            if ex["title"].strip().lower() == title.strip().lower():
                api_error(409, "ALREADY_EXISTS", f"Тема '{title}' уже существует в курсе", reason="TopicAlreadyExists")

        max_order = conn.execute("SELECT MAX(sort_order) as m FROM class_topics WHERE class_id = ?", (class_id,)).fetchone()["m"] or 0
        now = int(time.time())
        cursor = conn.execute("""
            INSERT INTO class_topics (class_id, title, sort_order, updated_at)
            VALUES (?, ?, ?, ?)
        """, (class_id, title, max_order + 1, now))

        row = conn.execute("SELECT * FROM class_topics WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return _topic_row_to_schema(dict(row))

@router.get("/v1/courses/{courseId}/topics/{id}", response_model=Topic)
def get_topic(courseId: str, id: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_TOPICS, SCOPE_TOPICS_READONLY, SCOPE_COURSES, SCOPE_COURSES_READONLY))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        assert_course_access(conn, class_id, ctx.user)

        try:
            tid = int(id)
        except ValueError:
            api_error(404, "NOT_FOUND", "Тема не найдена")

        row = conn.execute("SELECT * FROM class_topics WHERE id = ? AND class_id = ?", (tid, class_id)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Тема не найдена")

        return _topic_row_to_schema(dict(row))

@router.get("/v1/courses/{courseId}/topics", response_model=ListTopicResponse)
def list_topics_v1(courseId: str, request: Request, pageSize: int = 30, pageToken: Optional[str] = None):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_TOPICS, SCOPE_TOPICS_READONLY, SCOPE_COURSES, SCOPE_COURSES_READONLY))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        assert_course_access(conn, class_id, ctx.user)

        limit = min(max(1, pageSize), 100)
        fingerprint = f"topics:{class_id}"
        offset = decode_page_token(pageToken, fingerprint)

        rows = conn.execute("""
            SELECT * FROM class_topics
            WHERE class_id = ?
            ORDER BY sort_order ASC, id ASC
            LIMIT ? OFFSET ?
        """, (class_id, limit + 1, offset)).fetchall()

        items = [dict(r) for r in rows]
        has_next = len(items) > limit
        if has_next:
            items = items[:limit]
            next_token = encode_page_token(offset + limit, fingerprint)
        else:
            next_token = None

        return ListTopicResponse(
            topic=[_topic_row_to_schema(i) for i in items],
            nextPageToken=next_token,
        )

@router.patch("/v1/courses/{courseId}/topics/{id}", response_model=Topic)
def patch_topic(courseId: str, id: str, req: Topic, request: Request, updateMask: Optional[str] = None):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_TOPICS, SCOPE_COURSES))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для редактирования темы")

        try:
            tid = int(id)
        except ValueError:
            api_error(404, "NOT_FOUND", "Тема не найдена")

        row = conn.execute("SELECT * FROM class_topics WHERE id = ? AND class_id = ?", (tid, class_id)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Тема не найдена")

        fields = parse_update_mask(updateMask, {"name"})
        now = int(time.time())
        if "name" in fields:
            new_title = _normalize_topic_title(req.name)
            duplicate = conn.execute(
                "SELECT id, title FROM class_topics WHERE class_id = ? AND id != ?",
                (class_id, tid)
            ).fetchall()
            for ex in duplicate:
                if ex["title"].strip().lower() == new_title.strip().lower():
                    api_error(409, "ALREADY_EXISTS", f"Тема '{new_title}' уже существует в курсе", reason="TopicAlreadyExists")

            conn.execute("UPDATE class_topics SET title = ?, updated_at = ? WHERE id = ?", (new_title, now, tid))

        updated = conn.execute("SELECT * FROM class_topics WHERE id = ?", (tid,)).fetchone()
        return _topic_row_to_schema(dict(updated))

@router.delete("/v1/courses/{courseId}/topics/{id}", response_model=Empty)
def delete_topic_v1(courseId: str, id: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_TOPICS, SCOPE_COURSES))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для удаления темы")

        try:
            tid = int(id)
        except ValueError:
            api_error(404, "NOT_FOUND", "Тема не найдена")

        row = conn.execute("SELECT id FROM class_topics WHERE id = ? AND class_id = ?", (tid, class_id)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Тема не найдена")

        # При удалении темы задания и материалы не удаляются (topic_id -> NULL)
        conn.execute("UPDATE coursework SET topic_id = NULL WHERE topic_id = ?", (tid,))
        conn.execute("UPDATE course_materials SET topic_id = NULL WHERE topic_id = ?", (tid,))
        conn.execute("DELETE FROM class_topics WHERE id = ?", (tid,))
        return Empty()

class TopicReorderItem(BaseModel):
    id: int
    sort_order: int

class TopicReorderRequest(BaseModel):
    items: Optional[List[TopicReorderItem]] = None
    topic_ids: Optional[List[int]] = None

@router.post("/api/classroom/classes/{class_id}/topics/reorder")
def reorder_topics(class_id: int, req: TopicReorderRequest, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для изменения порядка тем")

        if req.items:
            for item in req.items:
                conn.execute("UPDATE class_topics SET sort_order = ? WHERE id = ? AND class_id = ?", (item.sort_order, item.id, class_id))
        elif req.topic_ids:
            for idx, tid in enumerate(req.topic_ids):
                conn.execute("UPDATE class_topics SET sort_order = ? WHERE id = ? AND class_id = ?", (idx, tid, class_id))

        return {"ok": True}

# -----------------------------------------------------------------------------
# 7.2. Справочные материалы (courses.courseWorkMaterials)
# -----------------------------------------------------------------------------

@router.post("/v1/courses/{courseId}/courseWorkMaterials", response_model=CourseWorkMaterial)
def create_course_work_material(courseId: str, req: CourseWorkMaterial, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSEWORKMATERIALS, SCOPE_COURSES))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для создания материалов в данном курсе")

        if not req.title or not req.title.strip():
            api_error(400, "INVALID_ARGUMENT", "Заголовок материала обязателен", reason="INVALID_ARGUMENT")

        now = int(time.time())
        state = (req.state or "PUBLISHED").upper()
        if state not in ("PUBLISHED", "DRAFT", "DELETED"):
            state = "PUBLISHED"

        scheduled_ts = rfc3339_to_ts(req.scheduledTime)
        if scheduled_ts is not None:
            if state != "DRAFT" or scheduled_ts <= now:
                api_error(400, "INVALID_ARGUMENT", "scheduledTime требует state=DRAFT и дату в будущем", reason="INVALID_ARGUMENT")

        assignee_mode = req.assigneeMode or "ALL_STUDENTS"
        target_students = []
        if assignee_mode == "INDIVIDUAL_STUDENTS":
            if not req.individualStudentsOptions or not req.individualStudentsOptions.studentIds:
                api_error(400, "INVALID_ARGUMENT", "Список учеников не может быть пустым", reason="EmptyAssignees")
            target_students = [int(s) for s in req.individualStudentsOptions.studentIds if s.isdigit()]

        materials = req.materials or []
        if len(materials) > 20:
            api_error(400, "INVALID_ARGUMENT", "Максимум 20 вложений на объект", reason="INVALID_ARGUMENT")

        materials_json = json.dumps([m.model_dump(exclude_none=True) if hasattr(m, "model_dump") else m for m in materials], ensure_ascii=False)
        target_students_json = json.dumps(target_students)

        topic_id = None
        if req.topicId:
            try:
                topic_id = int(req.topicId)
            except ValueError:
                pass

        cursor = conn.execute("""
            INSERT INTO course_materials (
                class_id, topic_id, creator_user_id, creator_client_id,
                title, description, materials_json, state, assignee_mode,
                target_students_json, scheduled_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            class_id, topic_id, ctx.user["id"], ctx.client_id,
            req.title.strip(), req.description or "", materials_json, state, assignee_mode,
            target_students_json, scheduled_ts, now, now
        ))

        row = conn.execute("SELECT * FROM course_materials WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return _cwm_row_to_schema(dict(row))

@router.get("/v1/courses/{courseId}/courseWorkMaterials/{id}", response_model=CourseWorkMaterial)
def get_course_work_material(courseId: str, id: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSEWORKMATERIALS, SCOPE_COURSEWORKMATERIALS_READONLY, SCOPE_COURSES, SCOPE_COURSES_READONLY))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)

        try:
            mid = int(id)
        except ValueError:
            api_error(404, "NOT_FOUND", "Материал не найден")

        row = conn.execute("SELECT * FROM course_materials WHERE id = ? AND class_id = ?", (mid, class_id)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Материал не найден")

        r_dict = dict(row)
        if role == "STUDENT":
            if r_dict.get("state") != "PUBLISHED":
                api_error(404, "NOT_FOUND", "Материал не найден")
            if r_dict.get("assignee_mode") == "INDIVIDUAL_STUDENTS":
                target_s = json.loads(r_dict.get("target_students_json") or "[]")
                if ctx.user["id"] not in target_s:
                    api_error(404, "NOT_FOUND", "Материал не найден")

        return _cwm_row_to_schema(r_dict)

@router.get("/v1/courses/{courseId}/courseWorkMaterials", response_model=ListCourseWorkMaterialResponse)
def list_course_work_materials(
    courseId: str,
    request: Request,
    courseWorkMaterialStates: Optional[str] = None,
    orderBy: Optional[str] = None,
    materialDriveId: Optional[str] = None,
    materialLink: Optional[str] = None,
    pageSize: int = 30,
    pageToken: Optional[str] = None
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSEWORKMATERIALS, SCOPE_COURSEWORKMATERIALS_READONLY, SCOPE_COURSES, SCOPE_COURSES_READONLY))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)

        limit = min(max(1, pageSize), 100)
        fingerprint = f"cwm:{class_id}:{courseWorkMaterialStates}:{orderBy}:{materialDriveId}:{materialLink}"
        offset = decode_page_token(pageToken, fingerprint)

        states = ["PUBLISHED"]
        if courseWorkMaterialStates:
            states = [s.strip().upper() for s in courseWorkMaterialStates.split(",") if s.strip()]

        if role == "STUDENT":
            states = ["PUBLISHED"]

        state_placeholders = ",".join("?" for _ in states)
        order_clause = "updated_at DESC, id DESC"
        if orderBy and "updatetime desc" in orderBy.lower():
            order_clause = "updated_at DESC, id DESC"
        elif orderBy and "updatetime asc" in orderBy.lower():
            order_clause = "updated_at ASC, id ASC"

        query = f"""
            SELECT * FROM course_materials
            WHERE class_id = ? AND state IN ({state_placeholders})
            ORDER BY {order_clause}
        """
        rows = conn.execute(query, [class_id, *states]).fetchall()

        filtered = []
        for r in rows:
            r_dict = dict(r)
            if role == "STUDENT" and r_dict.get("assignee_mode") == "INDIVIDUAL_STUDENTS":
                ts = json.loads(r_dict.get("target_students_json") or "[]")
                if ctx.user["id"] not in ts:
                    continue

            # Фильтры по materialDriveId / materialLink
            if materialDriveId or materialLink:
                m_list = json.loads(r_dict.get("materials_json") or "[]")
                matched = False
                for m in m_list:
                    if materialDriveId and m.get("driveFile", {}).get("driveFile", {}).get("id") == materialDriveId:
                        matched = True
                        break
                    if materialLink and m.get("link", {}).get("url") == materialLink:
                        matched = True
                        break
                if not matched:
                    continue

            filtered.append(r_dict)

        items = filtered[offset: offset + limit]
        has_next = len(filtered) > offset + limit
        next_token = encode_page_token(offset + limit, fingerprint) if has_next else None

        return ListCourseWorkMaterialResponse(
            courseWorkMaterial=[_cwm_row_to_schema(i) for i in items],
            nextPageToken=next_token,
        )

@router.patch("/v1/courses/{courseId}/courseWorkMaterials/{id}", response_model=CourseWorkMaterial)
def patch_course_work_material(courseId: str, id: str, req: CourseWorkMaterial, request: Request, updateMask: Optional[str] = None):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSEWORKMATERIALS, SCOPE_COURSES))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для редактирования материала")

        try:
            mid = int(id)
        except ValueError:
            api_error(404, "NOT_FOUND", "Материал не найден")

        row = conn.execute("SELECT * FROM course_materials WHERE id = ? AND class_id = ?", (mid, class_id)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Материал не найден")

        assert_developer_project_match(ctx, row["creator_client_id"])
        fields = parse_update_mask(updateMask, {"title", "description", "state", "scheduledTime", "topicId"})
        now = int(time.time())

        updates = ["updated_at = ?"]
        params = [now]

        if "title" in fields:
            if not req.title or not req.title.strip():
                api_error(400, "INVALID_ARGUMENT", "Заголовок не может быть пустым")
            updates.append("title = ?")
            params.append(req.title.strip())

        if "description" in fields:
            updates.append("description = ?")
            params.append(req.description or "")

        if "state" in fields:
            st = (req.state or "PUBLISHED").upper()
            updates.append("state = ?")
            params.append(st)

        if "scheduled_time" in fields or "scheduledTime" in fields:
            sch_ts = rfc3339_to_ts(req.scheduledTime)
            updates.append("scheduled_at = ?")
            params.append(sch_ts)

        if "topic_id" in fields or "topicId" in fields:
            tid = int(req.topicId) if req.topicId and req.topicId.isdigit() else None
            updates.append("topic_id = ?")
            params.append(tid)

        params.append(mid)
        conn.execute(f"UPDATE course_materials SET {', '.join(updates)} WHERE id = ?", params)

        updated = conn.execute("SELECT * FROM course_materials WHERE id = ?", (mid,)).fetchone()
        return _cwm_row_to_schema(dict(updated))

@router.delete("/v1/courses/{courseId}/courseWorkMaterials/{id}", response_model=Empty)
def delete_course_work_material_v1(courseId: str, id: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSEWORKMATERIALS, SCOPE_COURSES))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для удаления материала")

        try:
            mid = int(id)
        except ValueError:
            api_error(404, "NOT_FOUND", "Материал не найден")

        row = conn.execute("SELECT * FROM course_materials WHERE id = ? AND class_id = ?", (mid, class_id)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Материал не найден")

        assert_developer_project_match(ctx, row["creator_client_id"])
        # Мягкое удаление со state='DELETED'
        conn.execute("UPDATE course_materials SET state = 'DELETED', updated_at = ? WHERE id = ?", (int(time.time()), mid))
        return Empty()

# -----------------------------------------------------------------------------
# 7.3. Задания и Вопросы (courses.courseWork)
# -----------------------------------------------------------------------------

@router.post("/v1/courses/{courseId}/courseWork", response_model=CourseWork)
def create_course_work(courseId: str, req: CourseWork, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSEWORK_STUDENTS, SCOPE_COURSES))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для создания заданий в данном курсе")

        class_row = conn.execute("SELECT grade_level FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not req.title or not req.title.strip():
            api_error(400, "INVALID_ARGUMENT", "Заголовок задания обязателен", reason="INVALID_ARGUMENT")

        wtype = req.workType or "ASSIGNMENT"
        if wtype not in ("ASSIGNMENT", "SHORT_ANSWER_QUESTION", "MULTIPLE_CHOICE_QUESTION"):
            wtype = "ASSIGNMENT"

        # Инвариант: дедлайн требует обязательного dueTime при наличии dueDate
        due_ts = None
        if req.dueDate is not None:
            if req.dueTime is None:
                api_error(400, "INVALID_ARGUMENT", "При наличии dueDate обязателен dueTime", reason="INVALID_ARGUMENT")
            due_ts = date_time_to_ts(
                req.dueDate.model_dump(exclude_none=True) if hasattr(req.dueDate, "model_dump") else req.dueDate,
                req.dueTime.model_dump(exclude_none=True) if hasattr(req.dueTime, "model_dump") else req.dueTime
            )

        now = int(time.time())
        state = (req.state or "PUBLISHED").upper()
        if state not in ("PUBLISHED", "DRAFT", "DELETED"):
            state = "PUBLISHED"

        scheduled_ts = rfc3339_to_ts(req.scheduledTime)
        if scheduled_ts is not None:
            if state != "DRAFT" or scheduled_ts <= now:
                api_error(400, "INVALID_ARGUMENT", "scheduledTime требует state=DRAFT и дату в будущем", reason="INVALID_ARGUMENT")

        # Баллы: maxPoints == 0 означает Ungraded (Без оценки)
        max_points = 100
        if req.maxPoints is not None:
            max_points = int(req.maxPoints)

        assignee_mode = req.assigneeMode or "ALL_STUDENTS"
        target_students_val = "all"
        if assignee_mode == "INDIVIDUAL_STUDENTS":
            if not req.individualStudentsOptions or not req.individualStudentsOptions.studentIds:
                api_error(400, "INVALID_ARGUMENT", "Список учеников не может быть пустым", reason="EmptyAssignees")
            target_ids = [int(s) for s in req.individualStudentsOptions.studentIds if s.isdigit()]
            target_students_val = json.dumps(target_ids)

        choices_json = "[]"
        if wtype == "MULTIPLE_CHOICE_QUESTION":
            if not req.multipleChoiceQuestion or not req.multipleChoiceQuestion.choices:
                api_error(400, "INVALID_ARGUMENT", "Для вопроса с выбором ответа требуется список вариантов", reason="INVALID_ARGUMENT")
            choices = [c.strip() for c in req.multipleChoiceQuestion.choices if c and c.strip()]
            if len(set(choices)) < 2:
                api_error(400, "INVALID_ARGUMENT", "Вопрос с выбором ответа требует минимум 2 непустых уникальных варианта", reason="INVALID_ARGUMENT")
            choices_json = json.dumps(choices, ensure_ascii=False)

        materials = req.materials or []
        if len(materials) > 20:
            api_error(400, "INVALID_ARGUMENT", "Максимум 20 вложений на объект", reason="INVALID_ARGUMENT")

        attachments_json = json.dumps([m.model_dump(exclude_none=True) if hasattr(m, "model_dump") else m for m in materials], ensure_ascii=False)

        topic_id = None
        if req.topicId and req.topicId.isdigit():
            topic_id = int(req.topicId)

        mod_mode = req.submissionModificationMode or "MODIFIABLE_UNTIL_TURNED_IN"

        cursor = conn.execute("""
            INSERT INTO coursework (
                class_id, topic_id, kind, title, instructions,
                attachments_json, target_students, max_points, state,
                scheduled_at, due_at, creator_user_id, creator_client_id,
                work_type, assignee_mode, modification_mode, choices_json,
                sort_order, updated_at, created_at
            ) VALUES (?, ?, 'assignment', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """, (
            class_id, topic_id, req.title.strip(), req.description or "",
            attachments_json, target_students_val, max_points, state.lower(),
            scheduled_ts, due_ts, ctx.user["id"], ctx.client_id,
            wtype, assignee_mode, mod_mode, choices_json,
            now, now
        ))

        cw_id = cursor.lastrowid
        if state == "PUBLISHED":
            _populate_v1_submissions(conn, cw_id, class_id, assignee_mode, target_students_val)

        row = conn.execute("SELECT * FROM coursework WHERE id = ?", (cw_id,)).fetchone()
        return _cw_row_to_schema(dict(row))

@router.get("/v1/courses/{courseId}/courseWork/{id}", response_model=CourseWork)
def get_course_work(courseId: str, id: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSEWORK_STUDENTS, SCOPE_COURSEWORK_STUDENTS_READONLY, SCOPE_COURSEWORK_ME, SCOPE_COURSEWORK_ME_READONLY))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)

        try:
            cid = int(id)
        except ValueError:
            api_error(404, "NOT_FOUND", "Задание не найдено")

        row = conn.execute("SELECT * FROM coursework WHERE id = ? AND class_id = ?", (cid, class_id)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Задание не найдено")

        r_dict = dict(row)
        if role == "STUDENT":
            if (r_dict.get("state") or "").lower() != "published":
                api_error(404, "NOT_FOUND", "Задание не найдено")
            if r_dict.get("assignee_mode") == "INDIVIDUAL_STUDENTS":
                ts = []
                try:
                    ts = json.loads(r_dict.get("target_students") or "[]")
                except Exception:
                    pass
                if ctx.user["id"] not in ts:
                    api_error(404, "NOT_FOUND", "Задание не найдено")

        return _cw_row_to_schema(r_dict)

@router.get("/v1/courses/{courseId}/courseWork", response_model=ListCourseWorkResponse)
def list_course_work(
    courseId: str,
    request: Request,
    courseWorkStates: Optional[str] = None,
    orderBy: Optional[str] = None,
    pageSize: int = 30,
    pageToken: Optional[str] = None
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSEWORK_STUDENTS, SCOPE_COURSEWORK_STUDENTS_READONLY, SCOPE_COURSEWORK_ME, SCOPE_COURSEWORK_ME_READONLY))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)

        limit = min(max(1, pageSize), 100)
        fingerprint = f"cw:{class_id}:{courseWorkStates}:{orderBy}"
        offset = decode_page_token(pageToken, fingerprint)

        states = ["published"]
        if courseWorkMaterialStates := courseWorkStates:
            states = [s.strip().lower() for s in courseWorkMaterialStates.split(",") if s.strip()]

        if role == "STUDENT":
            states = ["published"]

        state_placeholders = ",".join("?" for _ in states)
        order_clause = "updated_at DESC, id DESC"
        if orderBy:
            ob = orderBy.lower()
            if "duedate asc" in ob:
                order_clause = "due_at ASC, id ASC"
            elif "updatetime desc" in ob:
                order_clause = "updated_at DESC, id DESC"

        query = f"""
            SELECT * FROM coursework
            WHERE class_id = ? AND state IN ({state_placeholders})
            ORDER BY {order_clause}
        """
        rows = conn.execute(query, [class_id, *states]).fetchall()

        filtered = []
        for r in rows:
            r_dict = dict(r)
            if role == "STUDENT" and r_dict.get("assignee_mode") == "INDIVIDUAL_STUDENTS":
                ts = []
                try:
                    ts = json.loads(r_dict.get("target_students") or "[]")
                except Exception:
                    pass
                if ctx.user["id"] not in ts:
                    continue
            filtered.append(r_dict)

        items = filtered[offset: offset + limit]
        has_next = len(filtered) > offset + limit
        next_token = encode_page_token(offset + limit, fingerprint) if has_next else None

        return ListCourseWorkResponse(
            courseWork=[_cw_row_to_schema(i) for i in items],
            nextPageToken=next_token,
        )

@router.patch("/v1/courses/{courseId}/courseWork/{id}", response_model=CourseWork)
def patch_course_work(courseId: str, id: str, req: CourseWork, request: Request, updateMask: Optional[str] = None):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSEWORK_STUDENTS, SCOPE_COURSES))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для редактирования задания")

        try:
            cid = int(id)
        except ValueError:
            api_error(404, "NOT_FOUND", "Задание не найдено")

        row = conn.execute("SELECT * FROM coursework WHERE id = ? AND class_id = ?", (cid, class_id)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Задание не найдено")

        assert_developer_project_match(ctx, row["creator_client_id"])
        allowed = {
            "title", "description", "state", "dueDate", "dueTime",
            "maxPoints", "scheduledTime", "submissionModificationMode",
            "topicId", "gradingPeriodId"
        }
        fields = parse_update_mask(updateMask, allowed)
        now = int(time.time())

        updates = ["updated_at = ?"]
        params = [now]

        if "title" in fields:
            if not req.title or not req.title.strip():
                api_error(400, "INVALID_ARGUMENT", "Заголовок не может быть пустым")
            updates.append("title = ?")
            params.append(req.title.strip())

        if "description" in fields:
            updates.append("instructions = ?")
            params.append(req.description or "")

        if "state" in fields:
            st = (req.state or "PUBLISHED").lower()
            updates.append("state = ?")
            params.append(st)
            if st == "published" and row["state"] != "published":
                _populate_v1_submissions(conn, cid, class_id, row["assignee_mode"], row["target_students"])

        if "due_date" in fields or "due_time" in fields:
            if req.dueDate is not None:
                if req.dueTime is None:
                    api_error(400, "INVALID_ARGUMENT", "При наличии dueDate обязателен dueTime", reason="INVALID_ARGUMENT")
                new_due_ts = date_time_to_ts(
                    req.dueDate.model_dump(exclude_none=True) if hasattr(req.dueDate, "model_dump") else req.dueDate,
                    req.dueTime.model_dump(exclude_none=True) if hasattr(req.dueTime, "model_dump") else req.dueTime
                )
            else:
                new_due_ts = None
            updates.append("due_at = ?")
            params.append(new_due_ts)

        if "max_points" in fields:
            new_max = int(req.maxPoints) if req.maxPoints is not None else 0
            updates.append("max_points = ?")
            params.append(new_max)
            # При изменении CourseWork.maxPoints дописывать GradeHistory("MAX_POINTS_CHANGE")
            subs = conn.execute("SELECT student_id FROM submissions WHERE coursework_id = ?", (cid,)).fetchall()
            for s in subs:
                conn.execute("""
                    INSERT INTO submission_history (
                        coursework_id, student_id, entry_kind, grade_change_type,
                        max_points, actor_user_id, occurred_at
                    ) VALUES (?, ?, 'GRADE_CHANGE', 'MAX_POINTS_CHANGE', ?, ?, ?)
                """, (cid, s["student_id"], float(new_max), ctx.user["id"], now))

        if "scheduled_time" in fields:
            new_sch = rfc3339_to_ts(req.scheduledTime)
            updates.append("scheduled_at = ?")
            params.append(new_sch)

        if "submission_modification_mode" in fields:
            updates.append("modification_mode = ?")
            params.append(req.submissionModificationMode or "MODIFIABLE_UNTIL_TURNED_IN")

        if "topic_id" in fields:
            tid = int(req.topicId) if req.topicId and req.topicId.isdigit() else None
            updates.append("topic_id = ?")
            params.append(tid)

        if "grading_period_id" in fields:
            gpid = int(req.gradingPeriodId) if req.gradingPeriodId and req.gradingPeriodId.isdigit() else None
            updates.append("grading_period_id = ?")
            params.append(gpid)

        params.append(cid)
        conn.execute(f"UPDATE coursework SET {', '.join(updates)} WHERE id = ?", params)

        updated = conn.execute("SELECT * FROM coursework WHERE id = ?", (cid,)).fetchone()
        return _cw_row_to_schema(dict(updated))

@router.delete("/v1/courses/{courseId}/courseWork/{id}", response_model=Empty)
def delete_course_work_v1(courseId: str, id: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSEWORK_STUDENTS, SCOPE_COURSES))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для удаления задания")

        try:
            cid = int(id)
        except ValueError:
            api_error(404, "NOT_FOUND", "Задание не найдено")

        row = conn.execute("SELECT * FROM coursework WHERE id = ? AND class_id = ?", (cid, class_id)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Задание не найдено")

        assert_developer_project_match(ctx, row["creator_client_id"])
        conn.execute("UPDATE coursework SET state = 'deleted', updated_at = ? WHERE id = ?", (int(time.time()), cid))
        return Empty()

@router.post("/v1/courses/{courseId}/courseWork/{id}:modifyAssignees", response_model=CourseWork)
def modify_course_work_assignees(courseId: str, id: str, req: ModifyCourseWorkAssigneesRequest, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_COURSEWORK_STUDENTS, SCOPE_COURSES))
        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для изменения назначений")

        try:
            cid = int(id)
        except ValueError:
            api_error(404, "NOT_FOUND", "Задание не найдено")

        row = conn.execute("SELECT * FROM coursework WHERE id = ? AND class_id = ?", (cid, class_id)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Задание не найдено")

        assignee_mode = req.assigneeMode or row["assignee_mode"]
        target_students_val = row["target_students"]

        if assignee_mode == "ALL_STUDENTS":
            target_students_val = "all"
        elif assignee_mode == "INDIVIDUAL_STUDENTS":
            current_ids = set()
            if target_students_val != "all":
                try:
                    current_ids = set(json.loads(target_students_val))
                except Exception:
                    pass

            opts = req.modifyIndividualStudentsOptions
            if opts:
                if opts.addStudentIds:
                    for s in opts.addStudentIds:
                        if s.isdigit():
                            current_ids.add(int(s))
                if opts.removeStudentIds:
                    for s in opts.removeStudentIds:
                        if s.isdigit():
                            current_ids.discard(int(s))

            if not current_ids:
                api_error(400, "INVALID_ARGUMENT", "Список учеников не может быть пустым", reason="EmptyAssignees")
            target_students_val = json.dumps(sorted(list(current_ids)))

        now = int(time.time())
        conn.execute("""
            UPDATE coursework
            SET assignee_mode = ?, target_students = ?, updated_at = ?
            WHERE id = ?
        """, (assignee_mode, target_students_val, now, cid))

        if row["state"] == "published":
            _populate_v1_submissions(conn, cid, class_id, assignee_mode, target_students_val)

        updated = conn.execute("SELECT * FROM coursework WHERE id = ?", (cid,)).fetchone()
        return _cw_row_to_schema(dict(updated))

# Регистрация в глобальном v1_router
