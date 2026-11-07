import csv
import io
import json
import secrets
import time
import zipfile
import xml.etree.ElementTree as ET
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, Response, HTTPException, status, Query, UploadFile, File
from pydantic import BaseModel, Field

from app.db import db_session
from app.passport.middleware import require_user, require_teacher
from app.classroom.sse_hub import sse_hub
from app.passport.generator import create_unique_callsign
from app.passport.pii_guard import assert_zero_pii_text

router = APIRouter(tags=["notifications_admin"])

# -----------------------------------------------------------------------------
# Вспомогательные функции проверки прав и аудита
# -----------------------------------------------------------------------------

def require_admin(request: Request) -> Dict[str, Any]:
    user = require_user(request)
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только администраторам (роль 'admin')"
        )
    return user

def log_audit(
    conn,
    actor_user_id: Optional[int],
    action_code: str,
    target_kind: str,
    target_id: str,
    details: Optional[Dict[str, Any]] = None
):
    now = int(time.time())
    details_json = json.dumps(details or {}, ensure_ascii=False)
    conn.execute(
        """INSERT INTO audit_logs (actor_user_id, action_code, target_kind, target_id, details_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (actor_user_id, action_code, target_kind, str(target_id), details_json, now)
    )

def _generate_unique_pin(conn) -> str:
    for _ in range(50):
        pin = str(secrets.randbelow(90000) + 10000)
        row = conn.execute("SELECT id FROM classes WHERE join_pin = ?", (pin,)).fetchone()
        if not row:
            return pin
    return secrets.token_hex(4)[:5]

# -----------------------------------------------------------------------------
# 1. ЦЕНТР УВЕДОМЛЕНИЙ (NOTIFICATIONS)
# -----------------------------------------------------------------------------

class NotificationPrefUpdate(BaseModel):
    global_enabled: Optional[bool] = None
    prefs: Optional[Dict[str, Any]] = None
    muted_classes: Optional[List[int]] = None

@router.get("/api/classroom/notifications")
def get_notifications(
    request: Request,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0
):
    user = require_user(request)
    user_id = user["user_id"]

    with db_session() as conn:
        base_query = "SELECT * FROM notifications WHERE user_id = ?"
        params: List[Any] = [user_id]
        if unread_only:
            base_query += " AND is_read = 0"
        base_query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([min(max(limit, 1), 100), max(offset, 0)])

        rows = conn.execute(base_query, params).fetchall()

        unread_count_row = conn.execute(
            "SELECT COUNT(*) as cnt FROM notifications WHERE user_id = ? AND is_read = 0",
            (user_id,)
        ).fetchone()
        unread_count = unread_count_row["cnt"] if unread_count_row else 0

        notifications = [
            {
                "id": r["id"],
                "class_id": r["class_id"],
                "notif_kind": r["notif_kind"],
                "title": r["title"],
                "body_text": r["body_text"],
                "link_path": r["link_path"],
                "is_read": bool(r["is_read"]),
                "created_at": r["created_at"]
            }
            for r in rows
        ]

        return {
            "notifications": notifications,
            "unread_count": unread_count
        }

@router.post("/api/classroom/notifications/read-all")
def mark_all_notifications_read(request: Request):
    user = require_user(request)
    user_id = user["user_id"]

    with db_session() as conn:
        conn.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user_id,))
        return {"ok": True}

@router.post("/api/classroom/notifications/{notif_id}/read")
def mark_notification_read(notif_id: int, request: Request):
    user = require_user(request)
    user_id = user["user_id"]

    with db_session() as conn:
        conn.execute("UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?", (notif_id, user_id))
        return {"ok": True}

@router.get("/api/classroom/notification-prefs")
def get_notification_preferences(request: Request):
    user = require_user(request)
    user_id = user["user_id"]

    with db_session() as conn:
        row = conn.execute("SELECT * FROM notification_prefs WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return {
                "user_id": user_id,
                "global_enabled": True,
                "prefs": {},
                "muted_classes": []
            }
        try:
            prefs_dict = json.loads(row["prefs_json"])
        except Exception:
            prefs_dict = {}
        try:
            muted_list = json.loads(row["muted_classes_json"])
        except Exception:
            muted_list = []

        return {
            "user_id": user_id,
            "global_enabled": bool(row["global_enabled"]),
            "prefs": prefs_dict,
            "muted_classes": muted_list
        }

@router.patch("/api/classroom/notification-prefs")
def update_notification_preferences(body: NotificationPrefUpdate, request: Request):
    user = require_user(request)
    user_id = user["user_id"]

    with db_session() as conn:
        row = conn.execute("SELECT * FROM notification_prefs WHERE user_id = ?", (user_id,)).fetchone()
        cur_global = 1
        cur_prefs = "{}"
        cur_muted = "[]"

        if row:
            cur_global = row["global_enabled"]
            cur_prefs = row["prefs_json"]
            cur_muted = row["muted_classes_json"]

        if body.global_enabled is not None:
            cur_global = 1 if body.global_enabled else 0
        if body.prefs is not None:
            cur_prefs = json.dumps(body.prefs, ensure_ascii=False)
        if body.muted_classes is not None:
            cur_muted = json.dumps(body.muted_classes, ensure_ascii=False)

        conn.execute(
            """INSERT INTO notification_prefs (user_id, global_enabled, prefs_json, muted_classes_json)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   global_enabled = excluded.global_enabled,
                   prefs_json = excluded.prefs_json,
                   muted_classes_json = excluded.muted_classes_json""",
            (user_id, cur_global, cur_prefs, cur_muted)
        )

        try:
            p_dict = json.loads(cur_prefs)
        except Exception:
            p_dict = {}
        try:
            m_list = json.loads(cur_muted)
        except Exception:
            m_list = []

        return {
            "user_id": user_id,
            "global_enabled": bool(cur_global),
            "prefs": p_dict,
            "muted_classes": m_list
        }

# -----------------------------------------------------------------------------
# 2. АДМИН-КОНСОЛЬ: ПОДРАЗДЕЛЕНИЯ (ORG_UNITS)
# -----------------------------------------------------------------------------

class OrgUnitCreate(BaseModel):
    unit_title: str = Field(min_length=1, max_length=100)
    parent_id: Optional[int] = None
    academic_year: str = Field(default="2026-2027", max_length=32)

class OrgUnitUpdate(BaseModel):
    unit_title: Optional[str] = Field(default=None, min_length=1, max_length=100)
    parent_id: Optional[int] = None
    academic_year: Optional[str] = Field(default=None, max_length=32)

@router.get("/api/classroom/admin/org-units")
def list_org_units(request: Request):
    require_admin(request)
    with db_session() as conn:
        rows = conn.execute("SELECT * FROM org_units ORDER BY parent_id ASC NULLS FIRST, unit_title ASC").fetchall()
        return [
            {
                "id": r["id"],
                "parent_id": r["parent_id"],
                "unit_title": r["unit_title"],
                "academic_year": r["academic_year"],
                "created_at": r["created_at"]
            }
            for r in rows
        ]

@router.post("/api/classroom/admin/org-units")
def create_org_unit(body: OrgUnitCreate, request: Request):
    admin = require_admin(request)
    now = int(time.time())

    with db_session() as conn:
        if body.parent_id:
            parent = conn.execute("SELECT id FROM org_units WHERE id = ?", (body.parent_id,)).fetchone()
            if not parent:
                raise HTTPException(status_code=404, detail="Родительское подразделение не найдено")

        cur = conn.execute(
            "INSERT INTO org_units (parent_id, unit_title, academic_year, created_at) VALUES (?, ?, ?, ?)",
            (body.parent_id, body.unit_title, body.academic_year, now)
        )
        unit_id = cur.lastrowid
        log_audit(conn, admin["user_id"], "ORG_UNIT_CREATED", "org_unit", str(unit_id), body.model_dump())

        row = conn.execute("SELECT * FROM org_units WHERE id = ?", (unit_id,)).fetchone()
        return {
            "id": row["id"],
            "parent_id": row["parent_id"],
            "unit_title": row["unit_title"],
            "academic_year": row["academic_year"],
            "created_at": row["created_at"]
        }

@router.patch("/api/classroom/admin/org-units/{unit_id}")
def update_org_unit(unit_id: int, body: OrgUnitUpdate, request: Request):
    admin = require_admin(request)

    with db_session() as conn:
        row = conn.execute("SELECT * FROM org_units WHERE id = ?", (unit_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Подразделение не найдено")

        updates = []
        params = []
        if body.unit_title is not None:
            updates.append("unit_title = ?")
            params.append(body.unit_title)
        if body.parent_id is not None:
            if body.parent_id == unit_id:
                raise HTTPException(status_code=400, detail="Подразделение не может быть родителем самого себя")
            updates.append("parent_id = ?")
            params.append(body.parent_id)
        if body.academic_year is not None:
            updates.append("academic_year = ?")
            params.append(body.academic_year)

        if updates:
            params.append(unit_id)
            conn.execute(f"UPDATE org_units SET {', '.join(updates)} WHERE id = ?", params)
            log_audit(conn, admin["user_id"], "ORG_UNIT_UPDATED", "org_unit", str(unit_id), body.model_dump(exclude_none=True))

        updated = conn.execute("SELECT * FROM org_units WHERE id = ?", (unit_id,)).fetchone()
        return {
            "id": updated["id"],
            "parent_id": updated["parent_id"],
            "unit_title": updated["unit_title"],
            "academic_year": updated["academic_year"],
            "created_at": updated["created_at"]
        }

@router.delete("/api/classroom/admin/org-units/{unit_id}")
def delete_org_unit(unit_id: int, request: Request):
    admin = require_admin(request)
    with db_session() as conn:
        row = conn.execute("SELECT id FROM org_units WHERE id = ?", (unit_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Подразделение не найдено")

        # Переназначаем дочерние
        conn.execute("UPDATE org_units SET parent_id = NULL WHERE parent_id = ?", (unit_id,))
        conn.execute("UPDATE users SET org_unit_id = NULL WHERE org_unit_id = ?", (unit_id,))
        conn.execute("DELETE FROM org_units WHERE id = ?", (unit_id,))
        log_audit(conn, admin["user_id"], "ORG_UNIT_DELETED", "org_unit", str(unit_id))
        return {"ok": True}

# -----------------------------------------------------------------------------
# 3. АДМИН-КОНСОЛЬ: УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ
# -----------------------------------------------------------------------------

class AdminUserUpdate(BaseModel):
    verified_teacher: Optional[bool] = None
    account_disabled: Optional[bool] = None
    role: Optional[str] = Field(default=None, pattern="^(student|teacher|admin)$")
    org_unit_id: Optional[int] = None

class AdminAddMember(BaseModel):
    user_id: int
    role: str = Field(default="student", pattern="^(student|teacher)$")
    seat_number: Optional[int] = Field(default=None, ge=1, le=40)

class TransferOwnershipRequest(BaseModel):
    new_teacher_id: int

@router.get("/api/classroom/admin/users")
def list_admin_users(
    request: Request,
    role: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    require_admin(request)
    with db_session() as conn:
        base_query = """
            SELECT id, handle, role, avatar_seed, recess_seconds,
                   verified_teacher, account_disabled, org_unit_id, created_at
            FROM users
            WHERE 1=1
        """
        params: List[Any] = []
        if role:
            base_query += " AND role = ?"
            params.append(role)
        if search:
            base_query += " AND handle LIKE ?"
            params.append(f"%{search}%")

        base_query += " ORDER BY id ASC LIMIT ? OFFSET ?"
        params.extend([min(max(limit, 1), 200), max(offset, 0)])

        rows = conn.execute(base_query, params).fetchall()
        return [
            {
                "id": r["id"],
                "handle": r["handle"],
                "role": r["role"],
                "avatar_seed": r["avatar_seed"],
                "recess_seconds": r["recess_seconds"],
                "verified_teacher": bool(r["verified_teacher"]),
                "account_disabled": bool(r["account_disabled"]),
                "org_unit_id": r["org_unit_id"],
                "created_at": r["created_at"]
            }
            for r in rows
        ]

@router.patch("/api/classroom/admin/users/{user_id}")
def update_admin_user(user_id: int, body: AdminUserUpdate, request: Request):
    admin = require_admin(request)
    with db_session() as conn:
        u = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not u:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        updates = []
        params = []
        if body.verified_teacher is not None:
            updates.append("verified_teacher = ?")
            params.append(1 if body.verified_teacher else 0)
        if body.account_disabled is not None:
            updates.append("account_disabled = ?")
            params.append(1 if body.account_disabled else 0)
        if body.role is not None:
            updates.append("role = ?")
            params.append(body.role)
        if body.org_unit_id is not None:
            updates.append("org_unit_id = ?")
            params.append(body.org_unit_id if body.org_unit_id > 0 else None)

        if updates:
            params.append(user_id)
            conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
            log_audit(conn, admin["user_id"], "USER_UPDATED", "user", str(user_id), body.model_dump(exclude_none=True))

        updated = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return {
            "id": updated["id"],
            "handle": updated["handle"],
            "role": updated["role"],
            "verified_teacher": bool(updated["verified_teacher"]),
            "account_disabled": bool(updated["account_disabled"]),
            "org_unit_id": updated["org_unit_id"],
            "created_at": updated["created_at"]
        }

@router.post("/api/classroom/admin/classes/{class_id}/members")
def admin_add_class_member(class_id: int, body: AdminAddMember, request: Request):
    admin = require_admin(request)
    now = int(time.time())

    with db_session() as conn:
        course = conn.execute("SELECT id FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not course:
            raise HTTPException(status_code=404, detail="Курс не найден")

        user = conn.execute("SELECT * FROM users WHERE id = ?", (body.user_id,)).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        if body.role == "teacher":
            conn.execute(
                """INSERT INTO course_teachers (class_id, teacher_id, joined_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(class_id, teacher_id) DO NOTHING""",
                (class_id, body.user_id, now)
            )
        else:
            seat = body.seat_number or 1
            conn.execute(
                """INSERT INTO class_members (class_id, student_id, seat_number, enrollment_active, joined_at)
                   VALUES (?, ?, ?, 1, ?)
                   ON CONFLICT(class_id, student_id) DO UPDATE SET
                       enrollment_active = 1,
                       seat_number = COALESCE(excluded.seat_number, class_members.seat_number)""",
                (class_id, body.user_id, seat, now)
            )

        log_audit(conn, admin["user_id"], "CLASS_MEMBER_ADDED", "class", str(class_id), body.model_dump())
        return {"ok": True, "class_id": class_id, "user_id": body.user_id, "role": body.role}

@router.post("/api/classroom/admin/classes/{class_id}/transfer-ownership")
def transfer_class_ownership(class_id: int, body: TransferOwnershipRequest, request: Request):
    admin = require_admin(request)

    with db_session() as conn:
        course = conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
        if not course:
            raise HTTPException(status_code=404, detail="Курс не найден")

        new_teacher = conn.execute("SELECT * FROM users WHERE id = ?", (body.new_teacher_id,)).fetchone()
        if not new_teacher:
            raise HTTPException(status_code=404, detail="Учитель не найден")

        old_teacher_id = course["teacher_id"]
        conn.execute("UPDATE classes SET teacher_id = ? WHERE id = ?", (body.new_teacher_id, class_id))

        # Предыдущего владельца добавляем в со-учителя, если он ещё там не состоит
        now = int(time.time())
        conn.execute(
            """INSERT INTO course_teachers (class_id, teacher_id, joined_at)
               VALUES (?, ?, ?)
               ON CONFLICT(class_id, teacher_id) DO NOTHING""",
            (class_id, old_teacher_id, now)
        )

        log_audit(conn, admin["user_id"], "CLASS_OWNERSHIP_TRANSFERRED", "class", str(class_id), {
            "old_teacher_id": old_teacher_id,
            "new_teacher_id": body.new_teacher_id
        })

        return {
            "ok": True,
            "class_id": class_id,
            "old_teacher_id": old_teacher_id,
            "new_teacher_id": body.new_teacher_id
        }

# -----------------------------------------------------------------------------
# 4. ИМПОРТ РАСПИСАНИЯ OneRoster CSV
# -----------------------------------------------------------------------------

class OneRosterImportRequest(BaseModel):
    csv_text: Optional[str] = None
    classes_csv: Optional[str] = None
    users_csv: Optional[str] = None
    enrollments_csv: Optional[str] = None

@router.post("/api/classroom/admin/import-oneroster")
def import_oneroster(req: Optional[OneRosterImportRequest] = None, request: Request = None):
    admin = require_admin(request)
    now = int(time.time())

    classes_data = ""
    users_data = ""
    enrollments_data = ""

    if req:
        if req.csv_text:
            classes_data = req.csv_text
        if req.classes_csv:
            classes_data = req.classes_csv
        if req.users_csv:
            users_data = req.users_csv
        if req.enrollments_csv:
            enrollments_data = req.enrollments_csv

    for text_val in (classes_data, users_data, enrollments_data):
        if text_val:
            assert_zero_pii_text(text_val)

    imported_classes = 0
    imported_users = 0
    imported_enrollments = 0

    with db_session() as conn:
        # 1. Импорт классов
        if classes_data:
            reader = csv.DictReader(io.StringIO(classes_data))
            for row in reader:
                title = row.get("title") or row.get("className") or row.get("name") or "Новый класс"
                grade = 8
                try:
                    if row.get("grade") or row.get("gradeLevel"):
                        grade = max(1, min(11, int(row.get("grade") or row.get("gradeLevel"))))
                except Exception:
                    grade = 8
                subject = row.get("subject") or row.get("subjectCode") or "inf"
                pin = _generate_unique_pin(conn)

                cur = conn.execute(
                    """INSERT INTO classes (
                        teacher_id, title, subject_code, grade_level, join_pin,
                        course_state, created_at
                    ) VALUES (?, ?, ?, ?, ?, 'PROVISIONED', ?)""",
                    (admin["user_id"], title, subject, grade, pin, now)
                )
                cid = cur.lastrowid
                imported_classes += 1

                # Привязка псевдонима, если есть sourcedId
                sourced_id = row.get("sourcedId")
                if sourced_id:
                    alias_key = f"d:{sourced_id}"
                    conn.execute(
                        "INSERT OR IGNORE INTO course_aliases (alias_key, class_id, scope_kind, created_at) VALUES (?, ?, 'DOMAIN', ?)",
                        (alias_key, cid, now)
                    )

        # 2. Импорт пользователей (Zero-PII: строго анонимный позывной через create_unique_callsign!)
        handle_to_id = {}
        if users_data:
            reader = csv.DictReader(io.StringIO(users_data))
            for row in reader:
                ref_key = row.get("sourcedId") or row.get("username") or row.get("handle")
                handle = create_unique_callsign(conn)
                role = "teacher" if row.get("role") in ("teacher", "administrator") else "student"

                cur = conn.execute(
                    """INSERT INTO users (
                        handle, role, password_hash, recovery_words_hash, avatar_seed, created_at
                    ) VALUES (?, ?, 'provisioned_placeholder', 'provisioned_placeholder', 1, ?)""",
                    (handle, role, now)
                )
                uid = cur.lastrowid
                if ref_key:
                    handle_to_id[ref_key] = uid
                handle_to_id[handle] = uid
                imported_users += 1

        # 3. Импорт зачислений
        if enrollments_data:
            reader = csv.DictReader(io.StringIO(enrollments_data))
            for row in reader:
                class_ref = row.get("classSourcedId") or row.get("class_id")
                user_ref = row.get("userSourcedId") or row.get("handle") or row.get("username")
                enroll_role = row.get("role") or "student"

                target_cid = None
                if class_ref and class_ref.isdigit():
                    target_cid = int(class_ref)
                elif class_ref:
                    a_row = conn.execute("SELECT class_id FROM course_aliases WHERE alias_key = ?", (f"d:{class_ref}",)).fetchone()
                    if a_row:
                        target_cid = a_row["class_id"]

                target_uid = handle_to_id.get(user_ref)
                if not target_uid and user_ref and user_ref.isdigit():
                    target_uid = int(user_ref)

                if target_cid and target_uid:
                    if enroll_role == "teacher":
                        conn.execute(
                            "INSERT OR IGNORE INTO course_teachers (class_id, teacher_id, joined_at) VALUES (?, ?, ?)",
                            (target_cid, target_uid, now)
                        )
                    else:
                        conn.execute(
                            """INSERT INTO class_members (class_id, student_id, seat_number, enrollment_active, joined_at)
                               VALUES (?, ?, 1, 1, ?)
                               ON CONFLICT(class_id, student_id) DO UPDATE SET enrollment_active = 1""",
                            (target_cid, target_uid, now)
                        )
                    imported_enrollments += 1

        log_audit(conn, admin["user_id"], "ONEROSTER_IMPORTED", "domain", "school", {
            "imported_classes": imported_classes,
            "imported_users": imported_users,
            "imported_enrollments": imported_enrollments
        })

        return {
            "ok": True,
            "imported_classes": imported_classes,
            "imported_users": imported_users,
            "imported_enrollments": imported_enrollments,
            "course_state": "PROVISIONED"
        }

# -----------------------------------------------------------------------------
# 5. ЖУРНАЛ АУДИТА (AUDIT LOGS)
# -----------------------------------------------------------------------------

@router.get("/api/classroom/admin/audit-logs")
def get_audit_logs(
    request: Request,
    action_code: Optional[str] = None,
    target_kind: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    require_admin(request)
    with db_session() as conn:
        base_query = "SELECT * FROM audit_logs WHERE 1=1"
        params: List[Any] = []
        if action_code:
            base_query += " AND action_code = ?"
            params.append(action_code)
        if target_kind:
            base_query += " AND target_kind = ?"
            params.append(target_kind)

        base_query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([min(max(limit, 1), 200), max(offset, 0)])

        rows = conn.execute(base_query, params).fetchall()
        return [
            {
                "id": r["id"],
                "actor_user_id": r["actor_user_id"],
                "action_code": r["action_code"],
                "target_kind": r["target_kind"],
                "target_id": r["target_id"],
                "details": json.loads(r["details_json"]) if r["details_json"] else {},
                "created_at": r["created_at"]
            }
            for r in rows
        ]

# -----------------------------------------------------------------------------
# 6. ВЫГРУЗКА ДАННЫХ И IMS COMMON CARTRIDGE (Data Takeout)
# -----------------------------------------------------------------------------

def _generate_takeout_zip(conn, teacher_id: Optional[int] = None) -> bytes:
    if teacher_id is not None:
        classes_rows = conn.execute(
            "SELECT id, title, subject_code, grade_level, course_state, created_at FROM classes WHERE teacher_id = ? OR id IN (SELECT class_id FROM course_teachers WHERE teacher_id = ?)",
            (teacher_id, teacher_id)
        ).fetchall()
        class_ids = [c["id"] for c in classes_rows]
        if class_ids:
            ph = ",".join("?" for _ in class_ids)
            topics_rows = conn.execute(f"SELECT id, class_id, title FROM class_topics WHERE class_id IN ({ph})", class_ids).fetchall()
            coursework_rows = conn.execute(f"SELECT id, class_id, topic_id, kind, title, instructions, max_points, due_at, created_at FROM coursework WHERE class_id IN ({ph})", class_ids).fetchall()
            cw_ids = [cw["id"] for cw in coursework_rows]
            if cw_ids:
                cw_ph = ",".join("?" for _ in cw_ids)
                rubrics_rows = conn.execute(f"SELECT id, class_id, coursework_id, criteria_json, created_at FROM rubrics WHERE coursework_id IN ({cw_ph})", cw_ids).fetchall()
                submissions_rows = conn.execute(f"SELECT coursework_id, student_id, status, grade_points, grade_five, updated_at FROM submissions WHERE coursework_id IN ({cw_ph})", cw_ids).fetchall()
            else:
                rubrics_rows = []
                submissions_rows = []
        else:
            topics_rows = []
            coursework_rows = []
            rubrics_rows = []
            submissions_rows = []
    else:
        classes_rows = conn.execute("SELECT id, title, subject_code, grade_level, course_state, created_at FROM classes").fetchall()
        topics_rows = conn.execute("SELECT id, class_id, title FROM class_topics").fetchall()
        coursework_rows = conn.execute("SELECT id, class_id, topic_id, kind, title, instructions, max_points, due_at, created_at FROM coursework").fetchall()
        rubrics_rows = conn.execute("SELECT id, class_id, coursework_id, criteria_json, created_at FROM rubrics").fetchall()
        submissions_rows = conn.execute("SELECT coursework_id, student_id, status, grade_points, grade_five, updated_at FROM submissions").fetchall()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Чистый локальный JSON-бэкап (100% автономность, Zero-PII)
        zf.writestr("courses.json", json.dumps([dict(r) for r in classes_rows], ensure_ascii=False, indent=2))
        zf.writestr("topics.json", json.dumps([dict(r) for r in topics_rows], ensure_ascii=False, indent=2))
        zf.writestr("coursework.json", json.dumps([dict(r) for r in coursework_rows], ensure_ascii=False, indent=2))
        zf.writestr("rubrics.json", json.dumps([dict(r) for r in rubrics_rows], ensure_ascii=False, indent=2))
        zf.writestr("submissions.json", json.dumps([dict(r) for r in submissions_rows], ensure_ascii=False, indent=2))

    return buf.getvalue()

@router.get("/api/classroom/admin/takeout.zip")
def export_admin_takeout_zip(request: Request):
    require_admin(request)
    with db_session() as conn:
        zip_bytes = _generate_takeout_zip(conn, teacher_id=None)
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=bormoclass-admin-takeout.zip"}
        )

@router.get("/api/classroom/takeout.zip")
def export_teacher_takeout_zip(request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        zip_bytes = _generate_takeout_zip(conn, teacher_id=user["user_id"])
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=bormoclass-takeout.zip"}
        )
