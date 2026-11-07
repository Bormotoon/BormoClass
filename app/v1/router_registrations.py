import hashlib
import hmac
import json
import time
import uuid
from typing import Optional, Dict, Any
from fastapi import APIRouter, Request

from app.config import settings
from app.db import db_session
from app.classroom.sse_hub import sse_hub
from app.v1.protocol import (
    api_error,
    resolve_class_id,
    ts_to_rfc3339
)
from app.v1.rbac import (
    resolve_auth_context,
    require_scopes,
    assert_course_access,
    SCOPE_PUSH_NOTIFICATIONS
)
from app.v1.schemas import (
    Registration,
    CloudPubsubTopic,
    Feed,
    CourseRosterChangesInfo,
    CourseWorkChangesInfo
)

router = APIRouter(tags=["registrations"])

TTL_SECONDS = 7 * 24 * 3600  # 7 суток (604800 сек)

def _build_registration_model(row: dict) -> Registration:
    class_id_str = str(row["class_id"]) if row.get("class_id") else None
    feed_type = row["feed_type"]

    roster_info = None
    cw_info = None
    if feed_type == "COURSE_ROSTER_CHANGES":
        roster_info = CourseRosterChangesInfo(courseId=class_id_str)
    elif feed_type == "COURSE_WORK_CHANGES":
        cw_info = CourseWorkChangesInfo(courseId=class_id_str)

    feed = Feed(
        feedType=feed_type,
        courseRosterChangesInfo=roster_info,
        courseWorkChangesInfo=cw_info
    )

    return Registration(
        registrationId=row["id"],
        cloudPubsubTopic=CloudPubsubTopic(topicName=row["target_topic"]),
        feed=feed,
        expiryTime=ts_to_rfc3339(row["expires_at"])
    )

# -----------------------------------------------------------------------------
# 1. POST /v1/registrations (create)
# -----------------------------------------------------------------------------

@router.post("/v1/registrations", response_model=Registration)
def create_registration(body: Registration, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_PUSH_NOTIFICATIONS,))

        if not body.feed or not body.feed.feedType:
            api_error(400, "INVALID_ARGUMENT", "Поле feed.feedType обязательно", reason="INVALID_ARGUMENT")

        feed_type = body.feed.feedType
        target_topic = ""
        if body.cloudPubsubTopic and body.cloudPubsubTopic.topicName:
            target_topic = body.cloudPubsubTopic.topicName
        if not target_topic:
            api_error(400, "INVALID_ARGUMENT", "Поле cloudPubsubTopic.topicName обязательно", reason="INVALID_ARGUMENT")

        class_id: Optional[int] = None

        if feed_type == "DOMAIN_ROSTER_CHANGES":
            # Доступно только администратору
            if ctx.user.get("role") != "admin":
                api_error(403, "PERMISSION_DENIED", "Подписка DOMAIN_ROSTER_CHANGES доступна только администраторам", reason="ADMINS_ONLY")

        elif feed_type == "COURSE_ROSTER_CHANGES":
            course_id_raw = None
            if body.feed.courseRosterChangesInfo and body.feed.courseRosterChangesInfo.courseId:
                course_id_raw = body.feed.courseRosterChangesInfo.courseId
            if not course_id_raw:
                api_error(400, "INVALID_ARGUMENT", "Для COURSE_ROSTER_CHANGES необходимо указать courseRosterChangesInfo.courseId", reason="INVALID_ARGUMENT")
            class_id = resolve_class_id(conn, course_id_raw, ctx.client_id)
            assert_course_access(conn, class_id, ctx.user)

        elif feed_type == "COURSE_WORK_CHANGES":
            course_id_raw = None
            if body.feed.courseWorkChangesInfo and body.feed.courseWorkChangesInfo.courseId:
                course_id_raw = body.feed.courseWorkChangesInfo.courseId
            if not course_id_raw:
                api_error(400, "INVALID_ARGUMENT", "Для COURSE_WORK_CHANGES необходимо указать courseWorkChangesInfo.courseId", reason="INVALID_ARGUMENT")
            class_id = resolve_class_id(conn, course_id_raw, ctx.client_id)
            assert_course_access(conn, class_id, ctx.user)

        else:
            api_error(400, "INVALID_ARGUMENT", f"Неизвестный тип подписки: '{feed_type}'", reason="INVALID_ARGUMENT")

        now = int(time.time())
        expires_at = now + TTL_SECONDS

        # Проверяем, существует ли уже активная подписка данного клиента/пользователя на этот фид
        existing = conn.execute(
            """SELECT * FROM push_registrations
               WHERE user_id = ? AND client_id = ? AND feed_type = ?
                 AND ((class_id IS NULL AND ? IS NULL) OR class_id = ?)""",
            (ctx.user["id"], ctx.client_id, feed_type, class_id, class_id)
        ).fetchone()

        if existing:
            # Продлеваем срок жизни существующей подписки
            reg_id = existing["id"]
            conn.execute(
                "UPDATE push_registrations SET target_topic = ?, expires_at = ? WHERE id = ?",
                (target_topic, expires_at, reg_id)
            )
        else:
            reg_id = f"reg_{uuid.uuid4().hex[:16]}"
            conn.execute(
                """INSERT INTO push_registrations (
                    id, user_id, client_id, feed_type, class_id, target_topic, expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (reg_id, ctx.user["id"], ctx.client_id, feed_type, class_id, target_topic, expires_at, now)
            )

        row = conn.execute("SELECT * FROM push_registrations WHERE id = ?", (reg_id,)).fetchone()
        return _build_registration_model(dict(row))

# -----------------------------------------------------------------------------
# 2. DELETE /v1/registrations/{registrationId} (delete)
# -----------------------------------------------------------------------------

@router.delete("/v1/registrations/{registrationId}")
def delete_registration(registrationId: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_PUSH_NOTIFICATIONS,))

        row = conn.execute("SELECT * FROM push_registrations WHERE id = ?", (registrationId,)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Подписка не найдена")

        if ctx.user.get("role") != "admin" and row["user_id"] != ctx.user["id"]:
            api_error(403, "PERMISSION_DENIED", "Недостаточно прав для удаления подписки")

        conn.execute("DELETE FROM push_registrations WHERE id = ?", (registrationId,))
        return {}

# -----------------------------------------------------------------------------
# 3. Функция диспетчеризации событий emit_classroom_feed_event
# -----------------------------------------------------------------------------

def emit_classroom_feed_event(conn, feed_type: str, class_id: Optional[int], resource_payload: Dict[str, Any]):
    """
    Ставит задачу доставки с подписью X-BormoClass-Signature в webhook_deliveries
    и мгновенно транслирует событие в браузерный sse_hub.
    """
    now = int(time.time())

    # Поиск подходящих активных регистраций
    if feed_type == "DOMAIN_ROSTER_CHANGES":
        query = "SELECT * FROM push_registrations WHERE feed_type = 'DOMAIN_ROSTER_CHANGES' AND expires_at > ?"
        params = (now,)
    else:
        query = "SELECT * FROM push_registrations WHERE feed_type = ? AND class_id = ? AND expires_at > ?"
        params = (feed_type, class_id, now)

    registrations = conn.execute(query, params).fetchall()

    for reg in registrations:
        envelope = {
            "registrationId": reg["id"],
            "feedType": feed_type,
            "courseId": str(class_id) if class_id else None,
            "resource": resource_payload,
            "eventTime": ts_to_rfc3339(now)
        }
        envelope_str = json.dumps(envelope, ensure_ascii=False)
        sig = hmac.new(settings.SECRET_KEY.encode("utf-8"), envelope_str.encode("utf-8"), hashlib.sha256).hexdigest()

        delivery_payload = {
            "envelope": envelope,
            "signature": f"sha256={sig}",
            "headers": {
                "X-BormoClass-Signature": f"sha256={sig}",
                "Content-Type": "application/json"
            }
        }
        delivery_json = json.dumps(delivery_payload, ensure_ascii=False)

        conn.execute(
            """INSERT INTO webhook_deliveries (
                registration_id, target_url, payload_json, attempt_count, next_retry_at, delivered, last_status, created_at
            ) VALUES (?, ?, ?, 0, ?, 0, 0, ?)""",
            (reg["id"], reg["target_topic"], delivery_json, now, now)
        )

    # Трансляция в браузерный sse_hub
    if class_id:
        sse_hub.notify_class(class_id, feed_type, resource_payload)
    else:
        # Для доменных событий оповещаем всех
        for cid in [r["id"] for r in conn.execute("SELECT id FROM classes").fetchall()]:
            sse_hub.notify_class(cid, feed_type, resource_payload)
