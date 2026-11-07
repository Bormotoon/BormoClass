import asyncio
import json
import secrets
import time
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.db import db_session
from app.passport.middleware import require_user, require_teacher
from app.classroom.sse_hub import sse_hub
from app.storage.engine import ensure_student_copy, get_blob_path, save_blob
from app.v1.rbac import resolve_auth_context, get_course_role

router = APIRouter(tags=["board"])

class BoardStateRequest(BaseModel):
    classroom_state_json: str = Field(default="{}")

@router.get("/api/classroom/board/{class_id}/state")
def get_board_state(class_id: int, request: Request):
    require_user(request)
    with db_session() as conn:
        row = conn.execute("""
            SELECT id, title, join_pin, grade_level, recess_locked_until, classroom_state_json
            FROM classes
            WHERE id = ?
        """, (class_id,)).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Класс не найден")

        members = conn.execute("""
            SELECT student_id, seat_number, is_present, traffic_light
            FROM class_members
            WHERE class_id = ?
            ORDER BY seat_number ASC
        """, (class_id,)).fetchall()

        traffic_summary = {"green": 0, "yellow": 0, "red": 0}
        for m in members:
            if m["is_present"] == 1 and m["traffic_light"] in traffic_summary:
                traffic_summary[m["traffic_light"]] += 1

        return {
            "class": dict(row),
            "members": [dict(m) for m in members],
            "traffic_summary": traffic_summary
        }

@router.post("/api/classroom/board/{class_id}/state")
def update_board_state(class_id: int, req: BoardStateRequest, request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        row = conn.execute("SELECT teacher_id FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not row or (row["teacher_id"] != user["user_id"] and user["role"] != "admin"):
            raise HTTPException(status_code=403, detail="Нет прав на управление интерактивной доской")

        conn.execute(
            "UPDATE classes SET classroom_state_json = ? WHERE id = ?",
            (req.classroom_state_json, class_id)
        )

        sse_hub.notify_board(class_id, "board_state_updated", {"state": req.classroom_state_json})
        return {"ok": True}

@router.get("/api/classroom/board/{class_id}/call-wheel")
def get_call_wheel_candidates(class_id: int, request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        class_row = conn.execute("SELECT teacher_id FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not class_row or (class_row["teacher_id"] != user["user_id"] and user["role"] != "admin"):
            raise HTTPException(status_code=403, detail="Нет прав на вызов к доске")

        # Выбираем только присутствующих учеников
        candidates = conn.execute("""
            SELECT cm.student_id, cm.seat_number, u.handle, u.avatar_seed
            FROM class_members cm
            JOIN users u ON cm.student_id = u.id
            WHERE cm.class_id = ? AND cm.is_present = 1
            ORDER BY cm.seat_number ASC
        """, (class_id,)).fetchall()

        return [dict(c) for c in candidates]

# -----------------------------------------------------------------------------
# Индивидуальные и групповые доски заданий (STUDENT_COPY / EDIT)
# -----------------------------------------------------------------------------

class CourseworkBoardUpdateRequest(BaseModel):
    elements_json: str = Field(default="[]")
    app_state_json: str = Field(default="{}")
    student_id: Optional[int] = None

@router.get("/api/classroom/coursework/{coursework_id}/board")
def get_coursework_board(coursework_id: int, request: Request, student_id: Optional[int] = None):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        user = ctx.user

        cw = conn.execute("SELECT * FROM coursework WHERE id = ?", (coursework_id,)).fetchone()
        if not cw:
            raise HTTPException(status_code=404, detail="Задание не найдено")

        class_id = cw["class_id"]
        role = get_course_role(conn, class_id, user)
        if not role:
            raise HTTPException(status_code=403, detail="Нет доступа к курсу")

        if role == "STUDENT":
            target_student_id = user["id"]
        else:
            target_student_id = student_id if student_id is not None else user["id"]

        ensure_student_copy(conn, cw, target_student_id)

        is_locked = False
        sub = conn.execute(
            "SELECT v1_state FROM submissions WHERE coursework_id = ? AND student_id = ?",
            (coursework_id, target_student_id)
        ).fetchone()
        if sub and sub["v1_state"] == "TURNED_IN" and role == "STUDENT":
            is_locked = True

        att_row = conn.execute("""
            SELECT sa.attachment_json, sf.id AS file_id, sf.disk_rel_path
            FROM submission_attachments sa
            JOIN stored_files sf ON sf.id = COALESCE(json_extract(sa.attachment_json, '$.localFile.id'), json_extract(sa.attachment_json, '$.driveFile.id'))
            WHERE sa.coursework_id = ? AND sa.student_id = ?
        """, (coursework_id, target_student_id)).fetchone()

        board_elements = "[]"
        file_id = None
        if att_row:
            file_id = att_row["file_id"]
            blob_path = get_blob_path(att_row["disk_rel_path"])
            if blob_path.exists():
                try:
                    board_elements = blob_path.read_text(encoding="utf-8")
                except Exception:
                    pass

        return {
            "coursework_id": coursework_id,
            "student_id": target_student_id,
            "file_id": file_id,
            "board_elements": board_elements,
            "is_locked": is_locked,
            "role": role
        }

@router.post("/api/classroom/coursework/{coursework_id}/board")
def update_coursework_board(coursework_id: int, req: CourseworkBoardUpdateRequest, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        user = ctx.user

        cw = conn.execute("SELECT * FROM coursework WHERE id = ?", (coursework_id,)).fetchone()
        if not cw:
            raise HTTPException(status_code=404, detail="Задание не найдено")

        class_id = cw["class_id"]
        role = get_course_role(conn, class_id, user)
        if not role:
            raise HTTPException(status_code=403, detail="Нет доступа к курсу")

        if role == "STUDENT":
            target_student_id = user["id"]
            sub = conn.execute(
                "SELECT v1_state FROM submissions WHERE coursework_id = ? AND student_id = ?",
                (coursework_id, target_student_id)
            ).fetchone()
            if sub and sub["v1_state"] == "TURNED_IN":
                raise HTTPException(status_code=403, detail="Locked after Turn-In")
        else:
            target_student_id = req.student_id if req.student_id is not None else user["id"]

        att_row = conn.execute("""
            SELECT sa.id, sf.id AS file_id, sf.disk_rel_path
            FROM submission_attachments sa
            JOIN stored_files sf ON sf.id = COALESCE(json_extract(sa.attachment_json, '$.localFile.id'), json_extract(sa.attachment_json, '$.driveFile.id'))
            WHERE sa.coursework_id = ? AND sa.student_id = ?
        """, (coursework_id, target_student_id)).fetchone()

        board_bytes = req.elements_json.encode("utf-8")
        sha256_hex, rel_path, size_bytes = save_blob(board_bytes)
        now = int(time.time())

        if att_row:
            conn.execute("""
                UPDATE stored_files
                SET sha256_hex = ?, disk_rel_path = ?, size_bytes = ?, updated_at = ?
                WHERE id = ?
            """, (sha256_hex, rel_path, size_bytes, now, att_row["file_id"]))
        else:
            file_id = f"file_board_{secrets.token_hex(6)}"
            conn.execute("""
                INSERT INTO stored_files (
                    id, folder_id, owner_user_id, file_title, mime_type,
                    size_bytes, sha256_hex, disk_rel_path, file_kind,
                    source_template_id, created_at, updated_at
                ) VALUES (?, NULL, ?, ?, 'application/vnd.excalidraw+json', ?, ?, ?, 'BOARD', NULL, ?, ?)
            """, (file_id, target_student_id, f"Доска задания #{coursework_id}", size_bytes, sha256_hex, rel_path, now, now))

            att_json = json.dumps({
                "localFile": {
                    "id": file_id,
                    "title": f"Доска задания #{coursework_id}",
                    "alternateLink": f"/api/storage/files/{file_id}",
                    "thumbnailUrl": f"/api/storage/files/{file_id}/thumbnail.svg"
                }
            }, ensure_ascii=False)

            conn.execute("""
                INSERT INTO submission_attachments (coursework_id, student_id, attachment_json, created_by_template, created_at)
                VALUES (?, ?, ?, 0, ?)
            """, (coursework_id, target_student_id, att_json, now))

        sse_hub.notify_class(class_id, "coursework_board_updated", {
            "coursework_id": coursework_id,
            "student_id": target_student_id,
            "updated_at": now
        })

        return {"ok": True}

# -----------------------------------------------------------------------------
# Асинхронные SSE-эндпоинты (async def, работающие с asyncio.Queue)
# -----------------------------------------------------------------------------

@router.get("/api/board/{class_id}/stream")
async def board_stream(class_id: int, request: Request):
    queue = sse_hub.subscribe_board(class_id)

    async def event_generator():
        try:
            # Отправляем приветственное ping-событие
            yield f"event: connected\ndata: {json.dumps({'class_id': class_id})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=25.0)
                    evt = msg.get("event", "message")
                    data = json.dumps(msg.get("data", {}), ensure_ascii=False)
                    yield f"event: {evt}\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    # SSE Keep-Alive пинг каждые 25 секунд
                    yield f": keep-alive\n\n"
        finally:
            sse_hub.unsubscribe_board(class_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@router.get("/api/classroom/{class_id}/stream")
async def classroom_stream(class_id: int, request: Request):
    queue = sse_hub.subscribe_class(class_id)

    async def event_generator():
        try:
            yield f"event: connected\ndata: {json.dumps({'class_id': class_id})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=25.0)
                    evt = msg.get("event", "message")
                    data = json.dumps(msg.get("data", {}), ensure_ascii=False)
                    yield f"event: {evt}\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    yield f": keep-alive\n\n"
        finally:
            sse_hub.unsubscribe_class(class_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
