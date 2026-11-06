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
            SELECT cm.student_id, cm.seat_number, cm.encrypted_note, u.handle, u.avatar_seed
            FROM class_members cm
            JOIN users u ON cm.student_id = u.id
            WHERE cm.class_id = ? AND cm.is_present = 1
            ORDER BY cm.seat_number ASC
        """, (class_id,)).fetchall()

        return [dict(c) for c in candidates]

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
