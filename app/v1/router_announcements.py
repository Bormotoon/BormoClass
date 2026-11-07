import json
import time
import secrets
from typing import Optional, List, Any

from fastapi import APIRouter, Request, Query, HTTPException
from pydantic import BaseModel, Field

from app.db import db_session
from app.v1.rbac import (
    resolve_auth_context,
    require_scopes,
    assert_course_access,
    assert_course_modifiable,
    assert_developer_project_match,
    get_course_role,
    SCOPE_ANNOUNCEMENTS,
    SCOPE_ANNOUNCEMENTS_READONLY
)
from app.v1.protocol import (
    api_error,
    resolve_class_id,
    resolve_user_id,
    ts_to_rfc3339,
    rfc3339_to_ts,
    parse_update_mask,
    encode_page_token,
    decode_page_token,
    apply_fields_selector
)
from app.v1.schemas import (
    Announcement,
    ModifyAnnouncementAssigneesRequest,
    Empty
)
from app.storage.engine import validate_materials_list, save_blob, get_blob_path
from app.classroom.sse_hub import sse_hub

router = APIRouter(tags=["announcements"])

# -----------------------------------------------------------------------------
# Хелпер форматирования Announcement
# -----------------------------------------------------------------------------

def format_announcement(row: Any) -> dict:
    d = dict(row)
    scheduled_ts = d.get("scheduled_at")
    scheduled_time = ts_to_rfc3339(scheduled_ts) if scheduled_ts else None

    materials = []
    try:
        raw_mats = d.get("materials_json") or "[]"
        materials = json.loads(raw_mats) if isinstance(raw_mats, str) else raw_mats
    except Exception:
        materials = []

    target_students = []
    try:
        raw_targets = d.get("target_students_json") or "[]"
        target_students = json.loads(raw_targets) if isinstance(raw_targets, str) else raw_targets
    except Exception:
        target_students = []

    res = {
        "id": str(d["id"]),
        "courseId": str(d["class_id"]),
        "text": d.get("body_text", ""),
        "materials": materials,
        "state": d.get("state", "PUBLISHED"),
        "alternateLink": f"/board/{d['class_id']}",
        "creationTime": ts_to_rfc3339(d.get("created_at")),
        "updateTime": ts_to_rfc3339(d.get("updated_at")),
        "scheduledTime": scheduled_time,
        "assigneeMode": d.get("assignee_mode", "ALL_STUDENTS"),
        "creatorUserId": str(d.get("creator_user_id", "")),
        "isPinned": bool(d.get("is_pinned", 0))
    }

    if d.get("assignee_mode") == "INDIVIDUAL_STUDENTS":
        res["individualStudentsOptions"] = {
            "studentIds": [str(s) for s in target_students]
        }

    return res

# -----------------------------------------------------------------------------
# 6 базовых методов Google Classroom REST API v1
# -----------------------------------------------------------------------------

@router.post("/v1/courses/{courseId}/announcements")
def create_announcement(courseId: str, req: Announcement, request: Request, fields: Optional[str] = None):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ANNOUNCEMENTS,))

        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        assert_course_modifiable(conn, class_id)

        now = int(time.time())

        # Проверка прав ученика
        if role == "STUDENT":
            course = conn.execute(
                "SELECT stream_post_mode FROM classes WHERE id = ?", (class_id,)
            ).fetchone()
            if course and course["stream_post_mode"] != "STUDENTS_CAN_POST_AND_COMMENT":
                api_error(403, "PERMISSION_DENIED", "Публикация записей учениками отключена учителем")

            member = conn.execute(
                "SELECT is_muted FROM class_members WHERE class_id = ? AND student_id = ?",
                (class_id, ctx.user["id"])
            ).fetchone()
            if member and member["is_muted"] == 1:
                api_error(403, "PERMISSION_DENIED", "Вам запрещено публиковать записи в этом курсе")

            if req.state and req.state != "PUBLISHED":
                api_error(403, "PERMISSION_DENIED", "Ученики могут публиковать только со state=PUBLISHED")

            if req.assigneeMode and req.assigneeMode != "ALL_STUDENTS":
                api_error(403, "PERMISSION_DENIED", "Ученики не могут настраивать индивидуальных адресатов")

            if req.scheduledTime:
                api_error(403, "PERMISSION_DENIED", "Ученики не могут откладывать публикацию")

        # Валидация scheduledTime
        scheduled_at = None
        state = req.state or "PUBLISHED"
        if req.scheduledTime:
            scheduled_at = rfc3339_to_ts(req.scheduledTime)
            if state != "DRAFT" or not scheduled_at or scheduled_at <= now:
                api_error(400, "INVALID_ARGUMENT", "scheduledTime требует state=DRAFT и дату в будущем")

        # Валидация EmptyAssignees
        assignee_mode = req.assigneeMode or "ALL_STUDENTS"
        target_student_ids = []
        if assignee_mode == "INDIVIDUAL_STUDENTS":
            if req.individualStudentsOptions and req.individualStudentsOptions.studentIds:
                target_student_ids = [
                    int(resolve_user_id(conn, sid, ctx.user))
                    for sid in req.individualStudentsOptions.studentIds
                ]
            if not target_student_ids:
                api_error(400, "INVALID_ARGUMENT", "Список учеников не может быть пустым", reason="EmptyAssignees")

        # Валидация вложений
        raw_materials = []
        if req.materials:
            validate_materials_list(req.materials)
            raw_materials = [
                m.model_dump(by_alias=True, exclude_none=True) if hasattr(m, "model_dump") else m
                for m in req.materials
            ]

        cursor = conn.execute("""
            INSERT INTO announcements (
                class_id, creator_user_id, creator_client_id, body_text,
                materials_json, state, assignee_mode, target_students_json,
                is_pinned, scheduled_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
        """, (
            class_id, ctx.user["id"], ctx.client_id, req.text or "",
            json.dumps(raw_materials, ensure_ascii=False), state, assignee_mode,
            json.dumps(target_student_ids), scheduled_at, now, now
        ))

        ann_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM announcements WHERE id = ?", (ann_id,)).fetchone()
        res = format_announcement(row)

        if state == "PUBLISHED":
            sse_hub.notify_class(class_id, "announcement_created", res)
            # Уведомления назначенным ученикам
            students_to_notify = target_student_ids
            if assignee_mode == "ALL_STUDENTS":
                members = conn.execute(
                    "SELECT student_id FROM class_members WHERE class_id = ? AND enrollment_active = 1",
                    (class_id,)
                ).fetchall()
                students_to_notify = [m["student_id"] for m in members]

            for sid in students_to_notify:
                if sid != ctx.user["id"]:
                    conn.execute("""
                        INSERT INTO notifications (user_id, class_id, notif_kind, title, body_text, link_path, created_at)
                        VALUES (?, ?, 'ANNOUNCEMENT', 'Новое объявление в классе', ?, ?, ?)
                    """, (sid, class_id, (req.text or "")[:100], f"/board/{class_id}", now))

        return apply_fields_selector(res, fields)

@router.get("/v1/courses/{courseId}/announcements/{id}")
def get_announcement(courseId: str, id: str, request: Request, fields: Optional[str] = None):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ANNOUNCEMENTS_READONLY, SCOPE_ANNOUNCEMENTS))

        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)

        try:
            ann_id = int(id)
        except ValueError:
            api_error(404, "NOT_FOUND", "Объявление не найдено")

        row = conn.execute(
            "SELECT * FROM announcements WHERE id = ? AND class_id = ?",
            (ann_id, class_id)
        ).fetchone()

        if not row:
            api_error(404, "NOT_FOUND", "Объявление не найдено")

        state = row["state"]
        if role == "STUDENT":
            if state != "PUBLISHED":
                api_error(404, "NOT_FOUND", "Объявление не найдено")
            if row["assignee_mode"] == "INDIVIDUAL_STUDENTS":
                try:
                    targets = json.loads(row["target_students_json"] or "[]")
                    if ctx.user["id"] not in targets:
                        api_error(404, "NOT_FOUND", "Объявление не найдено")
                except Exception:
                    api_error(404, "NOT_FOUND", "Объявление не найдено")

        if state == "DELETED":
            course = conn.execute("SELECT show_deleted_items FROM classes WHERE id = ?", (class_id,)).fetchone()
            if not course or course["show_deleted_items"] != 1:
                api_error(404, "NOT_FOUND", "Объявление удалено")

        return apply_fields_selector(format_announcement(row), fields)

@router.get("/v1/courses/{courseId}/announcements")
def list_announcements(
    courseId: str,
    request: Request,
    announcementStates: Optional[List[str]] = Query(None),
    orderBy: Optional[str] = "updateTime desc",
    pageSize: int = 30,
    pageToken: Optional[str] = None,
    fields: Optional[str] = None
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ANNOUNCEMENTS_READONLY, SCOPE_ANNOUNCEMENTS))

        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)

        limit = min(max(pageSize, 1), 100)
        fingerprint = f"{class_id}:{role}:{announcementStates}:{orderBy}"
        offset = decode_page_token(pageToken, fingerprint)

        query = "SELECT * FROM announcements WHERE class_id = ?"
        params: List[Any] = [class_id]

        if role == "STUDENT":
            query += " AND state = 'PUBLISHED'"
        else:
            if announcementStates:
                placeholders = ",".join(["?"] * len(announcementStates))
                query += f" AND state IN ({placeholders})"
                params.extend(announcementStates)
            else:
                query += " AND state = 'PUBLISHED'"

        # Сортировка: закрепленные всегда наверху, далее по времени
        if orderBy and "asc" in orderBy.lower():
            query += " ORDER BY is_pinned DESC, updated_at ASC"
        else:
            query += " ORDER BY is_pinned DESC, updated_at DESC"

        query += " LIMIT ? OFFSET ?"
        params.extend([limit + 1, offset])

        rows = conn.execute(query, params).fetchall()

        # Фильтрация по индивидуальным адресатам для ученика
        visible_rows = []
        for r in rows:
            if role == "STUDENT" and r["assignee_mode"] == "INDIVIDUAL_STUDENTS":
                try:
                    targets = json.loads(r["target_students_json"] or "[]")
                    if ctx.user["id"] in targets:
                        visible_rows.append(r)
                except Exception:
                    pass
            else:
                visible_rows.append(r)

        has_next = len(visible_rows) > limit
        items = visible_rows[:limit]

        next_page_token = encode_page_token(offset + limit, fingerprint) if has_next else None

        res = {
            "announcements": [format_announcement(r) for r in items],
            "nextPageToken": next_page_token
        }
        return apply_fields_selector(res, fields)

@router.patch("/v1/courses/{courseId}/announcements/{id}")
def patch_announcement(
    courseId: str,
    id: str,
    req: Announcement,
    request: Request,
    updateMask: Optional[str] = Query(None),
    fields: Optional[str] = None
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ANNOUNCEMENTS,))

        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        assert_course_modifiable(conn, class_id)

        try:
            ann_id = int(id)
        except ValueError:
            api_error(404, "NOT_FOUND", "Объявление не найдено")

        row = conn.execute(
            "SELECT * FROM announcements WHERE id = ? AND class_id = ?",
            (ann_id, class_id)
        ).fetchone()

        if not row:
            api_error(404, "NOT_FOUND", "Объявление не найдено")

        assert_developer_project_match(ctx, row["creator_client_id"])

        if role not in ("OWNER", "TEACHER", "ADMIN") and row["creator_user_id"] != ctx.user["id"]:
            api_error(403, "PERMISSION_DENIED", "Нет прав на редактирование объявления")

        allowed_fields = {"text", "state", "scheduled_time", "assignee_mode"}
        mask = parse_update_mask(updateMask, allowed_fields)

        now = int(time.time())
        updates = []
        params = []

        if "text" in mask:
            updates.append("body_text = ?")
            params.append(req.text or "")

        new_state = req.state if "state" in mask else row["state"]

        if "scheduled_time" in mask:
            if req.scheduledTime:
                sched_at = rfc3339_to_ts(req.scheduledTime)
                if new_state != "DRAFT" or not sched_at or sched_at <= now:
                    api_error(400, "INVALID_ARGUMENT", "scheduledTime требует state=DRAFT и дату в будущем")
                updates.append("scheduled_at = ?")
                params.append(sched_at)
            else:
                updates.append("scheduled_at = NULL")

        if "state" in mask and req.state:
            updates.append("state = ?")
            params.append(req.state)
            if req.state == "PUBLISHED":
                updates.append("scheduled_at = NULL")

        if "assignee_mode" in mask and req.assigneeMode:
            updates.append("assignee_mode = ?")
            params.append(req.assigneeMode)

        updates.append("updated_at = ?")
        params.append(now)

        params.extend([ann_id, class_id])
        conn.execute(f"UPDATE announcements SET {', '.join(updates)} WHERE id = ? AND class_id = ?", params)

        updated_row = conn.execute("SELECT * FROM announcements WHERE id = ?", (ann_id,)).fetchone()
        res = format_announcement(updated_row)
        sse_hub.notify_class(class_id, "announcement_updated", res)
        return apply_fields_selector(res, fields)

@router.delete("/v1/courses/{courseId}/announcements/{id}")
def delete_announcement(courseId: str, id: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ANNOUNCEMENTS,))

        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        assert_course_modifiable(conn, class_id)

        try:
            ann_id = int(id)
        except ValueError:
            api_error(404, "NOT_FOUND", "Объявление не найдено")

        row = conn.execute(
            "SELECT * FROM announcements WHERE id = ? AND class_id = ?",
            (ann_id, class_id)
        ).fetchone()

        if not row:
            api_error(404, "NOT_FOUND", "Объявление не найдено")

        assert_developer_project_match(ctx, row["creator_client_id"])

        if role not in ("OWNER", "TEACHER", "ADMIN") and row["creator_user_id"] != ctx.user["id"]:
            api_error(403, "PERMISSION_DENIED", "Нет прав на удаление объявления")

        now = int(time.time())
        conn.execute("UPDATE announcements SET state = 'DELETED', updated_at = ? WHERE id = ?", (now, ann_id))
        sse_hub.notify_class(class_id, "announcement_deleted", {"id": str(ann_id)})
        return {}

@router.post("/v1/courses/{courseId}/announcements/{id}:modifyAssignees")
def modify_announcement_assignees(
    courseId: str,
    id: str,
    req: ModifyAnnouncementAssigneesRequest,
    request: Request,
    fields: Optional[str] = None
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_ANNOUNCEMENTS,))

        class_id = resolve_class_id(conn, courseId, ctx.client_id)
        role = assert_course_access(conn, class_id, ctx.user)
        assert_course_modifiable(conn, class_id)

        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Только учителя могут изменять адресатов")

        try:
            ann_id = int(id)
        except ValueError:
            api_error(404, "NOT_FOUND", "Объявление не найдено")

        row = conn.execute(
            "SELECT * FROM announcements WHERE id = ? AND class_id = ?",
            (ann_id, class_id)
        ).fetchone()

        if not row:
            api_error(404, "NOT_FOUND", "Объявление не найдено")

        assert_developer_project_match(ctx, row["creator_client_id"])

        current_assignee_mode = req.assigneeMode or row["assignee_mode"]
        current_targets = set()
        try:
            current_targets = set(json.loads(row["target_students_json"] or "[]"))
        except Exception:
            pass

        if req.modifyIndividualStudentsOptions:
            opts = req.modifyIndividualStudentsOptions
            if opts.addStudentIds:
                for sid in opts.addStudentIds:
                    current_targets.add(int(resolve_user_id(conn, sid, ctx.user)))
            if hasattr(opts, "removeStudentIds") and opts.removeStudentIds:
                for sid in opts.removeStudentIds:
                    current_targets.discard(int(resolve_user_id(conn, sid, ctx.user)))

        if current_assignee_mode == "INDIVIDUAL_STUDENTS" and not current_targets:
            api_error(400, "INVALID_ARGUMENT", "Список учеников не может быть пустым", reason="EmptyAssignees")

        now = int(time.time())
        conn.execute("""
            UPDATE announcements
            SET assignee_mode = ?, target_students_json = ?, updated_at = ?
            WHERE id = ?
        """, (current_assignee_mode, json.dumps(sorted(list(current_targets))), now, ann_id))

        updated_row = conn.execute("SELECT * FROM announcements WHERE id = ?", (ann_id,)).fetchone()
        return apply_fields_selector(format_announcement(updated_row), fields)

# -----------------------------------------------------------------------------
# Расширенные функции Ленты (Закрепление, Мульти-постинг, Reuse Post)
# -----------------------------------------------------------------------------

@router.post("/api/classroom/classes/{class_id}/announcements/{id}/pin")
def pin_announcement(class_id: int, id: int, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Только учителя могут закреплять объявления")

        row = conn.execute("SELECT is_pinned FROM announcements WHERE id = ? AND class_id = ?", (id, class_id)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Объявление не найдено")

        new_pinned = 0 if row["is_pinned"] == 1 else 1
        now = int(time.time())
        conn.execute("UPDATE announcements SET is_pinned = ?, updated_at = ? WHERE id = ?", (new_pinned, now, id))
        sse_hub.notify_class(class_id, "announcement_pinned", {"id": id, "is_pinned": new_pinned})
        return {"ok": True, "is_pinned": new_pinned}

class MultiPostRequest(BaseModel):
    target_class_ids: List[int] = Field(min_length=1)
    kind: str = Field(default="announcement", pattern="^(announcement|material|assignment)$")
    text: str = Field(default="")
    title: Optional[str] = None
    materials: Optional[List[Any]] = None

@router.post("/api/classroom/stream/multi-post")
def multi_post(req: MultiPostRequest, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        now = int(time.time())

        # Инвариант Google Classroom: при отправке в > 1 класс автоматически применяется ALL_STUDENTS
        assignee_mode = "ALL_STUDENTS"
        created_ids = []

        mats_json = json.dumps(req.materials or [], ensure_ascii=False)

        for cid in req.target_class_ids:
            role = get_course_role(conn, cid, ctx.user)
            if role not in ("OWNER", "TEACHER", "ADMIN"):
                continue

            if req.kind == "announcement":
                cursor = conn.execute("""
                    INSERT INTO announcements (
                        class_id, creator_user_id, creator_client_id, body_text,
                        materials_json, state, assignee_mode, target_students_json,
                        is_pinned, scheduled_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'PUBLISHED', ?, '[]', 0, NULL, ?, ?)
                """, (cid, ctx.user["id"], ctx.client_id, req.text, mats_json, assignee_mode, now, now))
                created_ids.append({"class_id": cid, "announcement_id": cursor.lastrowid})
                sse_hub.notify_class(cid, "announcement_created", {"id": str(cursor.lastrowid)})

            elif req.kind == "material":
                cursor = conn.execute("""
                    INSERT INTO course_materials (
                        class_id, topic_id, creator_user_id, creator_client_id,
                        title, description, materials_json, state, assignee_mode,
                        target_students_json, learning_goals_json, sort_order,
                        scheduled_at, created_at, updated_at
                    ) VALUES (?, NULL, ?, ?, ?, ?, ?, 'PUBLISHED', ?, '[]', '[]', 0, NULL, ?, ?)
                """, (cid, ctx.user["id"], ctx.client_id, req.title or "Материал", req.text, mats_json, assignee_mode, now, now))
                created_ids.append({"class_id": cid, "material_id": cursor.lastrowid})

        return {"created": created_ids}

@router.get("/api/classroom/reuse-posts")
def get_reuse_posts_catalog(request: Request, q: Optional[str] = None, kind: Optional[str] = None):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        user_id = ctx.user["id"]

        results = []

        # Объявления учителя (включая ARCHIVED курсы)
        ann_query = """
            SELECT a.id, a.class_id, a.body_text AS title, a.materials_json, a.created_at,
                   c.title AS class_title, c.course_state, 'announcement' AS item_kind
            FROM announcements a
            JOIN classes c ON c.id = a.class_id
            WHERE (c.teacher_id = ? OR a.creator_user_id = ?) AND a.state != 'DELETED'
        """
        params = [user_id, user_id]
        if q:
            ann_query += " AND a.body_text LIKE ?"
            params.append(f"%{q}%")

        ann_rows = conn.execute(ann_query, params).fetchall()
        results.extend([dict(r) for r in ann_rows])

        # Задания учителя
        cw_query = """
            SELECT cw.id, cw.class_id, cw.title, cw.materials_json, cw.created_at,
                   c.title AS class_title, c.course_state, 'coursework' AS item_kind
            FROM coursework cw
            JOIN classes c ON c.id = cw.class_id
            WHERE (c.teacher_id = ? OR cw.creator_user_id = ?) AND cw.state != 'DELETED'
        """
        params_cw = [user_id, user_id]
        if q:
            cw_query += " AND cw.title LIKE ?"
            params_cw.append(f"%{q}%")

        cw_rows = conn.execute(cw_query, params_cw).fetchall()
        results.extend([dict(r) for r in cw_rows])

        # Сортировка по времени
        results.sort(key=lambda x: x["created_at"], reverse=True)
        return results

class ReusePostRequest(BaseModel):
    source_item_kind: str = Field(pattern="^(announcement|coursework|material)$")
    source_item_id: int
    copy_attachments: bool = True

@router.post("/api/classroom/classes/{class_id}/reuse-post")
def reuse_post(class_id: int, req: ReusePostRequest, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        role = assert_course_access(conn, class_id, ctx.user)
        if role not in ("OWNER", "TEACHER", "ADMIN"):
            api_error(403, "PERMISSION_DENIED", "Нет прав на публикацию в данный курс")

        assert_course_modifiable(conn, class_id)
        now = int(time.time())

        if req.source_item_kind == "announcement":
            source = conn.execute("SELECT * FROM announcements WHERE id = ?", (req.source_item_id,)).fetchone()
            if not source:
                api_error(404, "NOT_FOUND", "Исходное объявление не найдено")

            materials_json = source["materials_json"]
            # Опция "Создать новые копии всех вложений"
            if req.copy_attachments and materials_json:
                try:
                    mats = json.loads(materials_json)
                    new_mats = []
                    for m in mats:
                        if "driveFile" in m:
                            fid = m["driveFile"].get("id") or m["driveFile"].get("driveFile", {}).get("id")
                            f_row = conn.execute("SELECT * FROM stored_files WHERE id = ?", (fid,)).fetchone()
                            if f_row:
                                new_fid = f"file_{secrets.token_hex(8)}"
                                conn.execute("""
                                    INSERT INTO stored_files (
                                        id, folder_id, owner_user_id, file_title, mime_type,
                                        size_bytes, sha256_hex, disk_rel_path, file_kind,
                                        source_template_id, created_at, updated_at
                                    ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    new_fid, ctx.user["id"], f_row["file_title"], f_row["mime_type"],
                                    f_row["size_bytes"], f_row["sha256_hex"], f_row["disk_rel_path"],
                                    f_row["file_kind"], fid, now, now
                                ))
                                new_mats.append({
                                    "driveFile": {
                                        "id": new_fid,
                                        "title": f_row["file_title"],
                                        "alternateLink": f"/api/storage/files/{new_fid}",
                                        "thumbnailUrl": f"/api/storage/files/{new_fid}/thumbnail.svg"
                                    }
                                })
                        else:
                            new_mats.append(m)
                    materials_json = json.dumps(new_mats, ensure_ascii=False)
                except Exception:
                    pass

            cursor = conn.execute("""
                INSERT INTO announcements (
                    class_id, creator_user_id, creator_client_id, body_text,
                    materials_json, state, assignee_mode, target_students_json,
                    is_pinned, scheduled_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'PUBLISHED', 'ALL_STUDENTS', '[]', 0, NULL, ?, ?)
            """, (class_id, ctx.user["id"], ctx.client_id, source["body_text"], materials_json, now, now))

            return {"ok": True, "new_announcement_id": cursor.lastrowid}

        return {"ok": False, "detail": "Тип поста пока не поддерживается"}
