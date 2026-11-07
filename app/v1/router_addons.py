import base64
import hashlib
import hmac
import json
import time
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, Query
from pydantic import BaseModel

from app.config import settings
from app.db import db_session
from app.classroom.sse_hub import sse_hub
from app.v1.protocol import (
    api_error,
    resolve_class_id,
    date_to_dict,
    time_of_day_to_dict,
    date_time_to_ts,
    encode_page_token,
    decode_page_token,
    parse_update_mask,
    apply_fields_selector
)
from app.v1.rbac import (
    resolve_auth_context,
    require_scopes,
    assert_course_access,
    assert_developer_project_match,
    SCOPE_ADDONS_TEACHER,
    SCOPE_ADDONS_STUDENT,
    SCOPE_COURSES,
    SCOPE_COURSES_READONLY
)
from app.v1.schemas import (
    AddOnAttachment,
    AddOnAttachmentStudentSubmission,
    AddOnContext,
    TeacherContext,
    StudentContext,
    EmbedUri,
    Date,
    TimeOfDay,
    CopyHistory,
    ListAddOnAttachmentsResponse,
    ListAddOnAttachmentStudentSubmissionsResponse
)

router = APIRouter(tags=["addOns"])

# -----------------------------------------------------------------------------
# Вспомогательные функции сериализации и токенов
# -----------------------------------------------------------------------------

def _row_to_attachment(row: dict) -> AddOnAttachment:
    due_date = date_to_dict(row.get("due_at")) if row.get("due_at") else None
    due_time = time_of_day_to_dict(row.get("due_at")) if row.get("due_at") else None
    copy_history = []
    if row.get("copy_history_json"):
        try:
            raw_ch = json.loads(row["copy_history_json"])
            if isinstance(raw_ch, list):
                copy_history = [CopyHistory(**item) for item in raw_ch if isinstance(item, dict)]
        except Exception:
            pass

    return AddOnAttachment(
        id=str(row["id"]),
        courseId=str(row["class_id"]),
        itemId=str(row["item_id"]) if row.get("item_kind") != "posts" else None,
        postId=str(row["item_id"]) if row.get("item_kind") == "posts" else None,
        title=row.get("title", ""),
        teacherViewUri=EmbedUri(uri=row.get("teacher_view_uri", "")) if row.get("teacher_view_uri") else None,
        studentViewUri=EmbedUri(uri=row.get("student_view_uri", "")) if row.get("student_view_uri") else None,
        studentWorkReviewUri=EmbedUri(uri=row.get("review_uri", "")) if row.get("review_uri") else None,
        maxPoints=float(row["max_points"]) if row.get("max_points") is not None else None,
        gradeSyncEnabled=bool(row.get("grade_sync_enabled", 0)),
        dueDate=Date(**due_date) if due_date else None,
        dueTime=TimeOfDay(**due_time) if due_time else None,
        copyHistory=copy_history or None
    )

def _build_student_submission(
    attachment_id: str,
    student_id: int,
    cw_sub_id: str,
    points_earned: Optional[float],
    post_state: str = "CREATED"
) -> AddOnAttachmentStudentSubmission:
    return AddOnAttachmentStudentSubmission(
        id=f"addon_sub_{attachment_id}_{student_id}",
        userId=str(student_id),
        pointsEarned=points_earned,
        courseWorkSubmissionId=str(cw_sub_id),
        postSubmissionState=post_state
    )

def create_addon_token(
    course_id: int,
    item_id: int,
    item_kind: str,
    user_id: int,
    mode: str,
    attachment_id: Optional[int] = None,
    submission_id: Optional[str] = None
) -> str:
    now = int(time.time())
    payload = {
        "course_id": course_id,
        "item_id": item_id,
        "item_kind": item_kind,
        "user_id": user_id,
        "mode": mode,
        "attachment_id": attachment_id,
        "submission_id": submission_id,
        "iat": now,
        "exp": now + 7200
    }
    dumped = json.dumps(payload, separators=(',', ':'), sort_keys=True)
    b64_payload = base64.urlsafe_b64encode(dumped.encode()).decode().rstrip('=')
    sig = hmac.new(settings.SECRET_KEY.encode(), b64_payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{b64_payload}.{sig}"

def verify_addon_token(token: str) -> Optional[dict]:
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        b64_payload, sig = parts
        expected_sig = hmac.new(settings.SECRET_KEY.encode(), b64_payload.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sig, expected_sig):
            return None
        padded = b64_payload + "=" * ((4 - len(b64_payload) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None

# =============================================================================
# 1. 4 МЕТОДА getAddOnContext
# =============================================================================

def _get_addon_context_impl(
    course_id_str: str,
    item_kind: str,
    raw_item_id: str,
    request: Request
) -> AddOnContext:
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ADDONS_TEACHER, SCOPE_ADDONS_STUDENT, SCOPE_COURSES, SCOPE_COURSES_READONLY))
        class_id = resolve_class_id(conn, course_id_str, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)

        try:
            item_id = int(raw_item_id)
        except ValueError:
            item_id = 0

        supports_student_work = (item_kind == "courseWork")
        teacher_ctx = None
        student_ctx = None

        if role in ("OWNER", "TEACHER", "ADMIN"):
            teacher_ctx = TeacherContext()
        else:
            sub_id = f"sub_{item_id}_{ctx.user['id']}"
            if item_kind == "courseWork":
                sub_row = conn.execute(
                    "SELECT id FROM submissions WHERE coursework_id = ? AND student_id = ?",
                    (item_id, ctx.user["id"])
                ).fetchone()
                if sub_row and sub_row["id"]:
                    sub_id = str(sub_row["id"])
            student_ctx = StudentContext(submissionId=sub_id)

        return AddOnContext(
            courseId=str(class_id),
            itemId=str(item_id) if item_kind != "posts" else None,
            postId=str(item_id) if item_kind == "posts" else None,
            supportsStudentWork=supports_student_work,
            teacherContext=teacher_ctx,
            studentContext=student_ctx
        )

@router.get("/v1/courses/{courseId}/courseWork/{itemId}/addOnContext", response_model=AddOnContext)
def get_coursework_addon_context(courseId: str, itemId: str, request: Request):
    return _get_addon_context_impl(courseId, "courseWork", itemId, request)

@router.get("/v1/courses/{courseId}/announcements/{itemId}/addOnContext", response_model=AddOnContext)
def get_announcements_addon_context(courseId: str, itemId: str, request: Request):
    return _get_addon_context_impl(courseId, "announcements", itemId, request)

@router.get("/v1/courses/{courseId}/courseWorkMaterials/{itemId}/addOnContext", response_model=AddOnContext)
def get_materials_addon_context(courseId: str, itemId: str, request: Request):
    return _get_addon_context_impl(courseId, "courseWorkMaterials", itemId, request)

@router.get("/v1/courses/{courseId}/posts/{postId}/addOnContext", response_model=AddOnContext)
def get_posts_addon_context(courseId: str, postId: str, request: Request):
    return _get_addon_context_impl(courseId, "posts", postId, request)

# =============================================================================
# 2. 20 МЕТОДОВ addOnAttachments (CRUD для courseWork, announcements, courseWorkMaterials, posts)
# =============================================================================

def _create_attachment_impl(
    course_id_str: str,
    item_kind: str,
    raw_item_id: str,
    body: AddOnAttachment,
    request: Request
) -> AddOnAttachment:
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ADDONS_TEACHER,))
        class_id = resolve_class_id(conn, course_id_str, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Создавать вложения дополнений могут только учителя")

        try:
            item_id = int(raw_item_id)
        except ValueError:
            api_error(400, "INVALID_ARGUMENT", f"Некорректный itemId '{raw_item_id}'")

        grade_sync = bool(body.gradeSyncEnabled)
        # ИНВАРИАНТ: не более 1 вложения с gradeSyncEnabled=True на задание courseWork
        if item_kind == "courseWork" and grade_sync:
            existing_grade_sync = conn.execute(
                "SELECT 1 FROM addon_attachments WHERE class_id = ? AND item_kind = 'courseWork' AND item_id = ? AND grade_sync_enabled = 1",
                (class_id, item_id)
            ).fetchone()
            if existing_grade_sync:
                api_error(400, "FAILED_PRECONDITION", "На одно задание допускается не более одного вложения с gradeSyncEnabled=True", reason="MaxOneGradeSyncAttachmentExceeded")

        teacher_view_uri = body.teacherViewUri.uri if body.teacherViewUri else ""
        student_view_uri = body.studentViewUri.uri if body.studentViewUri else ""
        review_uri = body.studentWorkReviewUri.uri if body.studentWorkReviewUri else ""
        due_at = date_time_to_ts(
            body.dueDate.model_dump() if body.dueDate else None,
            body.dueTime.model_dump() if body.dueTime else None
        )
        copy_history_json = "[]"
        if body.copyHistory:
            copy_history_json = json.dumps([ch.model_dump(exclude_none=True) for ch in body.copyHistory], ensure_ascii=False)

        now = int(time.time())
        cur = conn.execute(
            """INSERT INTO addon_attachments (
                class_id, item_kind, item_id, client_id, title,
                teacher_view_uri, student_view_uri, review_uri,
                max_points, grade_sync_enabled, due_at, copy_history_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                class_id, item_kind, item_id, ctx.client_id, body.title or "",
                teacher_view_uri, student_view_uri, review_uri,
                body.maxPoints, 1 if grade_sync else 0, due_at, copy_history_json, now
            )
        )
        att_id = cur.lastrowid
        row = conn.execute("SELECT * FROM addon_attachments WHERE id = ?", (att_id,)).fetchone()
        sse_hub.notify_class(class_id, "addon_attachment_created", {"attachmentId": str(att_id), "itemKind": item_kind, "itemId": item_id})
        return _row_to_attachment(dict(row))

def _get_attachment_impl(
    course_id_str: str,
    item_kind: str,
    raw_item_id: str,
    attachment_id_str: str,
    request: Request
) -> AddOnAttachment:
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ADDONS_TEACHER, SCOPE_ADDONS_STUDENT, SCOPE_COURSES, SCOPE_COURSES_READONLY))
        class_id = resolve_class_id(conn, course_id_str, ctx.client_id)
        assert_course_access(conn, class_id, ctx.user)

        try:
            att_id = int(attachment_id_str)
            item_id = int(raw_item_id)
        except ValueError:
            api_error(404, "NOT_FOUND", "Вложение дополнения не найдено")

        row = conn.execute(
            "SELECT * FROM addon_attachments WHERE id = ? AND class_id = ? AND item_id = ?",
            (att_id, class_id, item_id)
        ).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Вложение дополнения не найдено")

        return _row_to_attachment(dict(row))

def _list_attachments_impl(
    course_id_str: str,
    item_kind: str,
    raw_item_id: str,
    page_size: int,
    page_token: Optional[str],
    request: Request
) -> ListAddOnAttachmentsResponse:
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ADDONS_TEACHER, SCOPE_ADDONS_STUDENT, SCOPE_COURSES, SCOPE_COURSES_READONLY))
        class_id = resolve_class_id(conn, course_id_str, ctx.client_id)
        assert_course_access(conn, class_id, ctx.user)

        try:
            item_id = int(raw_item_id)
        except ValueError:
            return ListAddOnAttachmentsResponse(addOnAttachments=[])

        fp = f"{class_id}:{item_kind}:{item_id}"
        offset = decode_page_token(page_token, fp) if page_token else 0
        limit = min(max(page_size, 1), 100)

        rows = conn.execute(
            "SELECT * FROM addon_attachments WHERE class_id = ? AND item_id = ? ORDER BY id ASC LIMIT ? OFFSET ?",
            (class_id, item_id, limit + 1, offset)
        ).fetchall()

        has_more = len(rows) > limit
        items = rows[:limit]
        next_token = encode_page_token(offset + limit, fp) if has_more else None

        return ListAddOnAttachmentsResponse(
            addOnAttachments=[_row_to_attachment(dict(r)) for r in items],
            nextPageToken=next_token
        )

def _patch_attachment_impl(
    course_id_str: str,
    item_kind: str,
    raw_item_id: str,
    attachment_id_str: str,
    body: AddOnAttachment,
    update_mask: Optional[str],
    request: Request
) -> AddOnAttachment:
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ADDONS_TEACHER,))
        class_id = resolve_class_id(conn, course_id_str, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Редактировать вложения могут только учителя")

        try:
            att_id = int(attachment_id_str)
            item_id = int(raw_item_id)
        except ValueError:
            api_error(404, "NOT_FOUND", "Вложение дополнения не найдено")

        row = conn.execute(
            "SELECT * FROM addon_attachments WHERE id = ? AND class_id = ? AND item_id = ?",
            (att_id, class_id, item_id)
        ).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Вложение дополнения не найдено")

        assert_developer_project_match(ctx, row["client_id"])

        allowed = {
            "title", "teacher_view_uri", "teacherViewUri",
            "student_view_uri", "studentViewUri",
            "student_work_review_uri", "studentWorkReviewUri",
            "max_points", "maxPoints",
            "grade_sync_enabled", "gradeSyncEnabled",
            "due_date", "dueDate", "due_time", "dueTime",
            "copy_history", "copyHistory"
        }
        mask_fields = parse_update_mask(update_mask, allowed)

        updates = []
        params = []

        if "title" in mask_fields and body.title is not None:
            updates.append("title = ?")
            params.append(body.title)
        if ("teacher_view_uri" in mask_fields or "teacherViewUri" in mask_fields) and body.teacherViewUri is not None:
            updates.append("teacher_view_uri = ?")
            params.append(body.teacherViewUri.uri)
        if ("student_view_uri" in mask_fields or "studentViewUri" in mask_fields) and body.studentViewUri is not None:
            updates.append("student_view_uri = ?")
            params.append(body.studentViewUri.uri)
        if ("student_work_review_uri" in mask_fields or "studentWorkReviewUri" in mask_fields) and body.studentWorkReviewUri is not None:
            updates.append("review_uri = ?")
            params.append(body.studentWorkReviewUri.uri)
        if ("max_points" in mask_fields or "maxPoints" in mask_fields):
            updates.append("max_points = ?")
            params.append(body.maxPoints)
        if ("grade_sync_enabled" in mask_fields or "gradeSyncEnabled" in mask_fields) and body.gradeSyncEnabled is not None:
            if body.gradeSyncEnabled and item_kind == "courseWork":
                other = conn.execute(
                    "SELECT 1 FROM addon_attachments WHERE class_id = ? AND item_kind = 'courseWork' AND item_id = ? AND grade_sync_enabled = 1 AND id != ?",
                    (class_id, item_id, att_id)
                ).fetchone()
                if other:
                    api_error(400, "FAILED_PRECONDITION", "На одно задание допускается не более одного вложения с gradeSyncEnabled=True", reason="MaxOneGradeSyncAttachmentExceeded")
            updates.append("grade_sync_enabled = ?")
            params.append(1 if body.gradeSyncEnabled else 0)
        if ("due_date" in mask_fields or "dueDate" in mask_fields or "due_time" in mask_fields or "dueTime" in mask_fields):
            ts = date_time_to_ts(
                body.dueDate.model_dump() if body.dueDate else None,
                body.dueTime.model_dump() if body.dueTime else None
            )
            updates.append("due_at = ?")
            params.append(ts)
        if ("copy_history" in mask_fields or "copyHistory" in mask_fields) and body.copyHistory is not None:
            ch_json = json.dumps([ch.model_dump(exclude_none=True) for ch in body.copyHistory], ensure_ascii=False)
            updates.append("copy_history_json = ?")
            params.append(ch_json)

        if updates:
            params.append(att_id)
            conn.execute(f"UPDATE addon_attachments SET {', '.join(updates)} WHERE id = ?", params)

        updated_row = conn.execute("SELECT * FROM addon_attachments WHERE id = ?", (att_id,)).fetchone()
        sse_hub.notify_class(class_id, "addon_attachment_updated", {"attachmentId": str(att_id), "itemKind": item_kind, "itemId": item_id})
        return _row_to_attachment(dict(updated_row))

def _delete_attachment_impl(
    course_id_str: str,
    item_kind: str,
    raw_item_id: str,
    attachment_id_str: str,
    request: Request
) -> dict:
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ADDONS_TEACHER,))
        class_id = resolve_class_id(conn, course_id_str, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Удалять вложения могут только учителя")

        try:
            att_id = int(attachment_id_str)
            item_id = int(raw_item_id)
        except ValueError:
            api_error(404, "NOT_FOUND", "Вложение дополнения не найдено")

        row = conn.execute(
            "SELECT * FROM addon_attachments WHERE id = ? AND class_id = ? AND item_id = ?",
            (att_id, class_id, item_id)
        ).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Вложение дополнения не найдено")

        assert_developer_project_match(ctx, row["client_id"])
        conn.execute("DELETE FROM addon_attachments WHERE id = ?", (att_id,))
        sse_hub.notify_class(class_id, "addon_attachment_deleted", {"attachmentId": str(att_id), "itemKind": item_kind, "itemId": item_id})
        return {}

# 2.1. courseWork (5 методов)
@router.post("/v1/courses/{courseId}/courseWork/{itemId}/addOnAttachments", response_model=AddOnAttachment)
def create_coursework_attachment(courseId: str, itemId: str, body: AddOnAttachment, request: Request):
    return _create_attachment_impl(courseId, "courseWork", itemId, body, request)

@router.get("/v1/courses/{courseId}/courseWork/{itemId}/addOnAttachments/{attachmentId}", response_model=AddOnAttachment)
def get_coursework_attachment(courseId: str, itemId: str, attachmentId: str, request: Request):
    return _get_attachment_impl(courseId, "courseWork", itemId, attachmentId, request)

@router.get("/v1/courses/{courseId}/courseWork/{itemId}/addOnAttachments", response_model=ListAddOnAttachmentsResponse)
def list_coursework_attachments(courseId: str, itemId: str, request: Request, pageSize: int = 100, pageToken: Optional[str] = None):
    return _list_attachments_impl(courseId, "courseWork", itemId, pageSize, pageToken, request)

@router.patch("/v1/courses/{courseId}/courseWork/{itemId}/addOnAttachments/{attachmentId}", response_model=AddOnAttachment)
def patch_coursework_attachment(courseId: str, itemId: str, attachmentId: str, body: AddOnAttachment, request: Request, updateMask: Optional[str] = Query(None)):
    return _patch_attachment_impl(courseId, "courseWork", itemId, attachmentId, body, updateMask, request)

@router.delete("/v1/courses/{courseId}/courseWork/{itemId}/addOnAttachments/{attachmentId}")
def delete_coursework_attachment(courseId: str, itemId: str, attachmentId: str, request: Request):
    return _delete_attachment_impl(courseId, "courseWork", itemId, attachmentId, request)

# 2.2. announcements (5 методов)
@router.post("/v1/courses/{courseId}/announcements/{itemId}/addOnAttachments", response_model=AddOnAttachment)
def create_announcement_attachment(courseId: str, itemId: str, body: AddOnAttachment, request: Request):
    return _create_attachment_impl(courseId, "announcements", itemId, body, request)

@router.get("/v1/courses/{courseId}/announcements/{itemId}/addOnAttachments/{attachmentId}", response_model=AddOnAttachment)
def get_announcement_attachment(courseId: str, itemId: str, attachmentId: str, request: Request):
    return _get_attachment_impl(courseId, "announcements", itemId, attachmentId, request)

@router.get("/v1/courses/{courseId}/announcements/{itemId}/addOnAttachments", response_model=ListAddOnAttachmentsResponse)
def list_announcement_attachments(courseId: str, itemId: str, request: Request, pageSize: int = 100, pageToken: Optional[str] = None):
    return _list_attachments_impl(courseId, "announcements", itemId, pageSize, pageToken, request)

@router.patch("/v1/courses/{courseId}/announcements/{itemId}/addOnAttachments/{attachmentId}", response_model=AddOnAttachment)
def patch_announcement_attachment(courseId: str, itemId: str, attachmentId: str, body: AddOnAttachment, request: Request, updateMask: Optional[str] = Query(None)):
    return _patch_attachment_impl(courseId, "announcements", itemId, attachmentId, body, updateMask, request)

@router.delete("/v1/courses/{courseId}/announcements/{itemId}/addOnAttachments/{attachmentId}")
def delete_announcement_attachment(courseId: str, itemId: str, attachmentId: str, request: Request):
    return _delete_attachment_impl(courseId, "announcements", itemId, attachmentId, request)

# 2.3. courseWorkMaterials (5 методов)
@router.post("/v1/courses/{courseId}/courseWorkMaterials/{itemId}/addOnAttachments", response_model=AddOnAttachment)
def create_material_attachment(courseId: str, itemId: str, body: AddOnAttachment, request: Request):
    return _create_attachment_impl(courseId, "courseWorkMaterials", itemId, body, request)

@router.get("/v1/courses/{courseId}/courseWorkMaterials/{itemId}/addOnAttachments/{attachmentId}", response_model=AddOnAttachment)
def get_material_attachment(courseId: str, itemId: str, attachmentId: str, request: Request):
    return _get_attachment_impl(courseId, "courseWorkMaterials", itemId, attachmentId, request)

@router.get("/v1/courses/{courseId}/courseWorkMaterials/{itemId}/addOnAttachments", response_model=ListAddOnAttachmentsResponse)
def list_material_attachments(courseId: str, itemId: str, request: Request, pageSize: int = 100, pageToken: Optional[str] = None):
    return _list_attachments_impl(courseId, "courseWorkMaterials", itemId, pageSize, pageToken, request)

@router.patch("/v1/courses/{courseId}/courseWorkMaterials/{itemId}/addOnAttachments/{attachmentId}", response_model=AddOnAttachment)
def patch_material_attachment(courseId: str, itemId: str, attachmentId: str, body: AddOnAttachment, request: Request, updateMask: Optional[str] = Query(None)):
    return _patch_attachment_impl(courseId, "courseWorkMaterials", itemId, attachmentId, body, updateMask, request)

@router.delete("/v1/courses/{courseId}/courseWorkMaterials/{itemId}/addOnAttachments/{attachmentId}")
def delete_material_attachment(courseId: str, itemId: str, attachmentId: str, request: Request):
    return _delete_attachment_impl(courseId, "courseWorkMaterials", itemId, attachmentId, request)

# 2.4. posts (5 методов)
@router.post("/v1/courses/{courseId}/posts/{postId}/addOnAttachments", response_model=AddOnAttachment)
def create_post_attachment(courseId: str, postId: str, body: AddOnAttachment, request: Request):
    return _create_attachment_impl(courseId, "posts", postId, body, request)

@router.get("/v1/courses/{courseId}/posts/{postId}/addOnAttachments/{attachmentId}", response_model=AddOnAttachment)
def get_post_attachment(courseId: str, postId: str, attachmentId: str, request: Request):
    return _get_attachment_impl(courseId, "posts", postId, attachmentId, request)

@router.get("/v1/courses/{courseId}/posts/{postId}/addOnAttachments", response_model=ListAddOnAttachmentsResponse)
def list_post_attachments(courseId: str, postId: str, request: Request, pageSize: int = 100, pageToken: Optional[str] = None):
    return _list_attachments_impl(courseId, "posts", postId, pageSize, pageToken, request)

@router.patch("/v1/courses/{courseId}/posts/{postId}/addOnAttachments/{attachmentId}", response_model=AddOnAttachment)
def patch_post_attachment(courseId: str, postId: str, attachmentId: str, body: AddOnAttachment, request: Request, updateMask: Optional[str] = Query(None)):
    return _patch_attachment_impl(courseId, "posts", postId, attachmentId, body, updateMask, request)

@router.delete("/v1/courses/{courseId}/posts/{postId}/addOnAttachments/{attachmentId}")
def delete_post_attachment(courseId: str, postId: str, attachmentId: str, request: Request):
    return _delete_attachment_impl(courseId, "posts", postId, attachmentId, request)

# =============================================================================
# 3. 5 МЕТОДОВ addOnAttachments.studentSubmissions (get, list, patch)
# =============================================================================

def _resolve_submission_student_id(conn, raw_submission_id: str, coursework_id: int) -> int:
    sub_row = None
    if raw_submission_id.isdigit():
        uid = int(raw_submission_id)
        sub_row = conn.execute(
            "SELECT student_id FROM submissions WHERE (id = ? OR student_id = ?) AND coursework_id = ?",
            (uid, uid, coursework_id)
        ).fetchone()
        if sub_row:
            return sub_row["student_id"]
        # Check if student exists in users
        u = conn.execute("SELECT id FROM users WHERE id = ?", (uid,)).fetchone()
        if u:
            return u["id"]

    if "_" in raw_submission_id:
        parts = raw_submission_id.split("_")
        if parts[-1].isdigit():
            return int(parts[-1])

    # Lookup by handle
    u = conn.execute("SELECT id FROM users WHERE handle = ?", (raw_submission_id,)).fetchone()
    if u:
        return u["id"]

    api_error(404, "NOT_FOUND", f"Сдача с ID '{raw_submission_id}' не найдена")

def _get_student_submission_impl(
    course_id_str: str,
    raw_item_id: str,
    attachment_id_str: str,
    submission_id_str: str,
    request: Request
) -> AddOnAttachmentStudentSubmission:
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ADDONS_TEACHER, SCOPE_ADDONS_STUDENT))
        class_id = resolve_class_id(conn, course_id_str, ctx.client_id)
        assert_course_access(conn, class_id, ctx.user)

        try:
            att_id = int(attachment_id_str)
            item_id = int(raw_item_id)
        except ValueError:
            api_error(404, "NOT_FOUND", "Вложение дополнения не найдено")

        att = conn.execute("SELECT * FROM addon_attachments WHERE id = ? AND class_id = ?", (att_id, class_id)).fetchone()
        if not att:
            api_error(404, "NOT_FOUND", "Вложение дополнения не найдено")

        student_id = _resolve_submission_student_id(conn, submission_id_str, item_id)
        sub = conn.execute(
            "SELECT * FROM addon_submissions WHERE attachment_id = ? AND student_id = ?",
            (att_id, student_id)
        ).fetchone()

        pts = float(sub["points_earned"]) if sub and sub["points_earned"] is not None else None
        return _build_student_submission(attachment_id_str, student_id, submission_id_str, pts)

def _list_student_submissions_impl(
    course_id_str: str,
    raw_item_id: str,
    attachment_id_str: str,
    request: Request,
    page_size: int = 100,
    page_token: Optional[str] = None
) -> ListAddOnAttachmentStudentSubmissionsResponse:
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ADDONS_TEACHER,))
        class_id = resolve_class_id(conn, course_id_str, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Просматривать сдачи могут только учителя")

        try:
            att_id = int(attachment_id_str)
            item_id = int(raw_item_id)
        except ValueError:
            api_error(404, "NOT_FOUND", "Вложение не найдено")

        att = conn.execute("SELECT * FROM addon_attachments WHERE id = ? AND class_id = ?", (att_id, class_id)).fetchone()
        if not att:
            api_error(404, "NOT_FOUND", "Вложение не найдено")

        fp = f"{class_id}:{att_id}:{item_id}"
        offset = decode_page_token(page_token, fp) if page_token else 0
        limit = min(max(page_size, 1), 100)

        # Список учеников класса
        students = conn.execute(
            """SELECT cm.student_id, COALESCE(s.id, cm.student_id) as cw_sub_id, asub.points_earned
               FROM class_members cm
               LEFT JOIN submissions s ON s.coursework_id = ? AND s.student_id = cm.student_id
               LEFT JOIN addon_submissions asub ON asub.attachment_id = ? AND asub.student_id = cm.student_id
               WHERE cm.class_id = ? AND cm.enrollment_active = 1
               ORDER BY cm.student_id ASC
               LIMIT ? OFFSET ?""",
            (item_id, att_id, class_id, limit + 1, offset)
        ).fetchall()

        has_more = len(students) > limit
        items = students[:limit]
        next_token = encode_page_token(offset + limit, fp) if has_more else None

        res_items = [
            _build_student_submission(
                attachment_id_str,
                r["student_id"],
                str(r["cw_sub_id"]),
                float(r["points_earned"]) if r["points_earned"] is not None else None
            )
            for r in items
        ]
        return ListAddOnAttachmentStudentSubmissionsResponse(
            addOnAttachmentStudentSubmissions=res_items,
            nextPageToken=next_token
        )

def _patch_student_submission_impl(
    course_id_str: str,
    raw_item_id: str,
    attachment_id_str: str,
    submission_id_str: str,
    body: AddOnAttachmentStudentSubmission,
    update_mask: Optional[str],
    request: Request
) -> AddOnAttachmentStudentSubmission:
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ADDONS_TEACHER, SCOPE_ADDONS_STUDENT))
        class_id = resolve_class_id(conn, course_id_str, ctx.client_id)
        assert_course_access(conn, class_id, ctx.user)

        try:
            att_id = int(attachment_id_str)
            item_id = int(raw_item_id)
        except ValueError:
            api_error(404, "NOT_FOUND", "Вложение дополнения не найдено")

        att = conn.execute("SELECT * FROM addon_attachments WHERE id = ? AND class_id = ?", (att_id, class_id)).fetchone()
        if not att:
            api_error(404, "NOT_FOUND", "Вложение дополнения не найдено")

        assert_developer_project_match(ctx, att["client_id"])

        student_id = _resolve_submission_student_id(conn, submission_id_str, item_id)
        points_earned = body.pointsEarned
        now_ts = int(time.time())

        # Upsert в addon_submissions
        conn.execute(
            """INSERT INTO addon_submissions (attachment_id, student_id, points_earned, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(attachment_id, student_id) DO UPDATE SET
                   points_earned = excluded.points_earned,
                   updated_at = excluded.updated_at""",
            (att_id, student_id, points_earned, now_ts)
        )

        # СИНХРОНИЗАЦИЯ БАЛЛОВ: если gradeSyncEnabled == 1 и переданы баллы
        if points_earned is not None and att["grade_sync_enabled"] == 1:
            att_max = float(att["max_points"]) if att["max_points"] else 100.0
            cw = conn.execute("SELECT max_points FROM coursework WHERE id = ?", (item_id,)).fetchone()
            cw_max = float(cw["max_points"]) if cw and cw["max_points"] is not None else 100.0

            scaled_grade = round((float(points_earned) / att_max) * cw_max, 2)

            conn.execute(
                """INSERT INTO submissions (coursework_id, student_id, draft_grade, grade_points, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(coursework_id, student_id) DO UPDATE SET
                       draft_grade = excluded.draft_grade,
                       grade_points = CASE WHEN grade_points IS NULL THEN CAST(ROUND(excluded.draft_grade) AS INTEGER) ELSE grade_points END,
                       updated_at = excluded.updated_at""",
                (item_id, student_id, scaled_grade, int(round(scaled_grade)), now_ts)
            )

            # Запись в историю оценок submission_history
            conn.execute(
                """INSERT INTO submission_history (
                    coursework_id, student_id, entry_kind, grade_change_type,
                    points_earned, max_points, actor_user_id, occurred_at
                ) VALUES (
                    ?, ?, 'gradeHistory', 'DRAFT_GRADE_POINTS_EARNED_CHANGE',
                    ?, ?, ?, ?
                )""",
                (item_id, student_id, scaled_grade, cw_max, ctx.user["id"], now_ts)
            )

        sse_hub.notify_class(class_id, "addon_submission_graded", {
            "attachmentId": str(att_id),
            "studentId": student_id,
            "pointsEarned": points_earned
        })

        return _build_student_submission(
            attachment_id_str,
            student_id,
            submission_id_str,
            points_earned,
            body.postSubmissionState or "TURNED_IN"
        )

# 3.1. courseWork studentSubmissions (3 метода: get, list, patch)
@router.get(
    "/v1/courses/{courseId}/courseWork/{itemId}/addOnAttachments/{attachmentId}/studentSubmissions/{submissionId}",
    response_model=AddOnAttachmentStudentSubmission
)
def get_coursework_attachment_student_submission(
    courseId: str, itemId: str, attachmentId: str, submissionId: str, request: Request
):
    return _get_student_submission_impl(courseId, itemId, attachmentId, submissionId, request)

@router.get(
    "/v1/courses/{courseId}/courseWork/{itemId}/addOnAttachments/{attachmentId}/studentSubmissions",
    response_model=ListAddOnAttachmentStudentSubmissionsResponse
)
def list_coursework_attachment_student_submissions(
    courseId: str, itemId: str, attachmentId: str, request: Request, pageSize: int = 100, pageToken: Optional[str] = None
):
    return _list_student_submissions_impl(courseId, itemId, attachmentId, request, pageSize, pageToken)

@router.patch(
    "/v1/courses/{courseId}/courseWork/{itemId}/addOnAttachments/{attachmentId}/studentSubmissions/{submissionId}",
    response_model=AddOnAttachmentStudentSubmission
)
def patch_coursework_attachment_student_submission(
    courseId: str, itemId: str, attachmentId: str, submissionId: str, body: AddOnAttachmentStudentSubmission, request: Request, updateMask: Optional[str] = Query(None)
):
    return _patch_student_submission_impl(courseId, itemId, attachmentId, submissionId, body, updateMask, request)

# 3.2. posts studentSubmissions (2 метода: get, patch)
@router.get(
    "/v1/courses/{courseId}/posts/{postId}/addOnAttachments/{attachmentId}/studentSubmissions/{submissionId}",
    response_model=AddOnAttachmentStudentSubmission
)
def get_post_attachment_student_submission(
    courseId: str, postId: str, attachmentId: str, submissionId: str, request: Request
):
    return _get_student_submission_impl(courseId, postId, attachmentId, submissionId, request)

@router.patch(
    "/v1/courses/{courseId}/posts/{postId}/addOnAttachments/{attachmentId}/studentSubmissions/{submissionId}",
    response_model=AddOnAttachmentStudentSubmission
)
def patch_post_attachment_student_submission(
    courseId: str, postId: str, attachmentId: str, submissionId: str, body: AddOnAttachmentStudentSubmission, request: Request, updateMask: Optional[str] = Query(None)
):
    return _patch_student_submission_impl(courseId, postId, attachmentId, submissionId, body, updateMask, request)

# =============================================================================
# 4. ИФРЕЙМ-ТОКЕНЫ И МОСТ LTI 1.3
# =============================================================================

class AddOnTokenRequest(BaseModel):
    course_id: int
    item_id: int
    item_kind: str = "courseWork"
    mode: str = "attachmentDiscovery"  # attachmentDiscovery | teacherView | studentView | studentWorkReview
    attachment_id: Optional[int] = None
    submission_id: Optional[str] = None

class LTILaunchRequest(BaseModel):
    coursework_id: Optional[int] = None
    task_id: Optional[str] = None
    score: Optional[float] = None
    launch_mode: str = "deep_link"
    resource_link_id: Optional[str] = None
    target_link_uri: Optional[str] = None

@router.post("/api/classroom/addons/token")
def issue_addon_token(req: AddOnTokenRequest, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        assert_course_access(conn, req.course_id, ctx.user)
        token = create_addon_token(
            course_id=req.course_id,
            item_id=req.item_id,
            item_kind=req.item_kind,
            user_id=ctx.user["id"],
            mode=req.mode,
            attachment_id=req.attachment_id,
            submission_id=req.submission_id
        )
        return {"addOnToken": token, "expiresIn": 7200, "mode": req.mode}

@router.get("/api/classroom/addons/token-info")
def inspect_addon_token(addOnToken: str):
    payload = verify_addon_token(addOnToken)
    if not payload:
        api_error(401, "UNAUTHENTICATED", "Недействительный или просроченный addOnToken")
    return payload

@router.post("/api/lti/launch")
def lti_launch_bridge(req: LTILaunchRequest, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        user_id = ctx.user["id"]
        now = int(time.time())

        # Если переданы результаты решения (Grade Passback)
        if req.coursework_id and req.score is not None:
            cw = conn.execute("SELECT * FROM coursework WHERE id = ?", (req.coursework_id,)).fetchone()
            if cw:
                norm_score = max(0.0, min(100.0, float(req.score)))
                max_pts = float(cw["max_points"]) if cw["max_points"] is not None else 100.0
                calc_points = round((norm_score / 100.0) * max_pts, 2)
                grade_five = 5 if norm_score >= 85 else (4 if norm_score >= 65 else (3 if norm_score >= 40 else 2))

                conn.execute(
                    """INSERT INTO submissions (
                        coursework_id, student_id, status, grade_points, grade_five, draft_grade, updated_at
                    ) VALUES (?, ?, 'turned_in', ?, ?, ?, ?)
                    ON CONFLICT(coursework_id, student_id) DO UPDATE SET
                        status = 'turned_in',
                        draft_grade = excluded.draft_grade,
                        grade_points = excluded.grade_points,
                        grade_five = excluded.grade_five,
                        updated_at = excluded.updated_at""",
                    (req.coursework_id, user_id, int(round(calc_points)), grade_five, calc_points, now)
                )

                # Награда секундами перемены
                reward = cw["recess_reward"] or 300
                conn.execute(
                    "UPDATE users SET recess_seconds = recess_seconds + ? WHERE id = ?",
                    (reward, user_id)
                )

                sse_hub.notify_class(cw["class_id"], "submission_turned_in", {
                    "coursework_id": req.coursework_id,
                    "student_id": user_id,
                    "score": norm_score
                })

        launch_token = create_addon_token(
            course_id=0,
            item_id=req.coursework_id or 0,
            item_kind="lti",
            user_id=user_id,
            mode=req.launch_mode
        )

        return {
            "ok": True,
            "lti_version": "1.3.0",
            "launch_token": launch_token,
            "target_link_uri": req.target_link_uri or "/static/board.html",
            "message": "LTI 1.3 launch bridge active"
        }
