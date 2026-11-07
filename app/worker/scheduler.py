import asyncio
import json
import time
import urllib.request
import urllib.error
import logging

from app.db import db_session
from app.classroom.sse_hub import sse_hub
from app.storage.engine import ensure_student_copy

logger = logging.getLogger("bormoclass.scheduler")

async def run_background_scheduler():
    logger.info("BormoClass Background Scheduler запущен")
    while True:
        try:
            await asyncio.sleep(15)
            now = int(time.time())

            with db_session() as conn:
                # 1. Публикация запланированных объявлений (announcements)
                scheduled_ann = conn.execute("""
                    SELECT * FROM announcements
                    WHERE state = 'DRAFT' AND scheduled_at IS NOT NULL AND scheduled_at <= ?
                """, (now,)).fetchall()

                for ann in scheduled_ann:
                    ann_id = ann["id"]
                    class_id = ann["class_id"]
                    conn.execute("""
                        UPDATE announcements
                        SET state = 'PUBLISHED', scheduled_at = NULL, updated_at = ?
                        WHERE id = ?
                    """, (now, ann_id))

                    sse_hub.notify_class(class_id, "announcement_published", {"id": str(ann_id)})

                    # Уведомления ученикам
                    members = conn.execute(
                        "SELECT student_id FROM class_members WHERE class_id = ? AND enrollment_active = 1",
                        (class_id,)
                    ).fetchall()
                    for m in members:
                        conn.execute("""
                            INSERT INTO notifications (user_id, class_id, notif_kind, title, body_text, link_path, created_at)
                            VALUES (?, ?, 'ANNOUNCEMENT', 'Опубликовано запланированное объявление', ?, ?, ?)
                        """, (m["student_id"], class_id, (ann["body_text"] or "")[:100], f"/board/{class_id}", now))

                # 2. Публикация запланированных заданий (coursework)
                scheduled_cw = conn.execute("""
                    SELECT * FROM coursework
                    WHERE (state = 'DRAFT' OR state = 'scheduled') AND scheduled_at IS NOT NULL AND scheduled_at <= ?
                """, (now,)).fetchall()

                for cw in scheduled_cw:
                    cw_id = cw["id"]
                    class_id = cw["class_id"]
                    conn.execute("""
                        UPDATE coursework
                        SET state = 'published', scheduled_at = NULL, updated_at = ?
                        WHERE id = ?
                    """, (now, cw_id))

                    # Материализация STUDENT_COPY файлов/досок при публикации
                    members = conn.execute(
                        "SELECT student_id FROM class_members WHERE class_id = ? AND enrollment_active = 1",
                        (class_id,)
                    ).fetchall()
                    for m in members:
                        ensure_student_copy(conn, cw, m["student_id"])

                        conn.execute("""
                            INSERT INTO notifications (user_id, class_id, notif_kind, title, body_text, link_path, created_at)
                            VALUES (?, ?, 'COURSEWORK', 'Новое опубликованное задание', ?, ?, ?)
                        """, (m["student_id"], class_id, (cw["title"] or "")[:100], f"/board/{class_id}", now))

                    sse_hub.notify_class(class_id, "coursework_published", {"id": str(cw_id)})

                # 3. Публикация запланированных материалов (course_materials)
                scheduled_mat = conn.execute("""
                    SELECT * FROM course_materials
                    WHERE state = 'DRAFT' AND scheduled_at IS NOT NULL AND scheduled_at <= ?
                """, (now,)).fetchall()

                for mat in scheduled_mat:
                    mat_id = mat["id"]
                    class_id = mat["class_id"]
                    conn.execute("""
                        UPDATE course_materials
                        SET state = 'PUBLISHED', scheduled_at = NULL, updated_at = ?
                        WHERE id = ?
                    """, (now, mat_id))

                    sse_hub.notify_class(class_id, "material_published", {"id": str(mat_id)})

                # 4. Обработка ретраев вебхуков (webhook_deliveries)
                pending_webhooks = conn.execute("""
                    SELECT * FROM webhook_deliveries
                    WHERE delivered = 0 AND next_retry_at <= ? AND attempt_count < 5
                """, (now,)).fetchall()

                for wh in pending_webhooks:
                    wh_id = wh["id"]
                    url = wh["target_url"]
                    payload = wh["payload_json"].encode("utf-8")
                    req = urllib.request.Request(
                        url,
                        data=payload,
                        headers={"Content-Type": "application/json", "User-Agent": "BormoClass-Webhook/1.0"}
                    )
                    try:
                        with urllib.request.urlopen(req, timeout=5.0) as resp:
                            status_code = resp.status
                            conn.execute("""
                                UPDATE webhook_deliveries
                                SET delivered = 1, last_status = ?
                                WHERE id = ?
                            """, (status_code, wh_id))
                    except Exception as e:
                        new_attempt = wh["attempt_count"] + 1
                        backoff = 30 * (2 ** new_attempt)
                        next_retry = now + backoff
                        status_val = 500
                        if isinstance(e, urllib.error.HTTPError):
                            status_val = e.code
                        conn.execute("""
                            UPDATE webhook_deliveries
                            SET attempt_count = ?, next_retry_at = ?, last_status = ?
                            WHERE id = ?
                        """, (new_attempt, next_retry, status_val, wh_id))

        except asyncio.CancelledError:
            logger.info("BormoClass Background Scheduler остановлен")
            break
        except Exception as e:
            logger.error(f"Ошибка в фоновом планировщике: {e}", exc_info=True)
            await asyncio.sleep(5)
