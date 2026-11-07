import os
import json
import time
import secrets
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import sqlite3

from app.config import settings
from app.v1.protocol import api_error

STORAGE_DIR = Path(settings.STORAGE_DIR)

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/svg+xml",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/zip",
    "audio/webm",
    "audio/mpeg",
    "video/webm",
    "video/mp4",
    "text/x-python",
    "application/x-python",
    "text/javascript",
    "application/javascript",
    "text/html",
    "application/vnd.excalidraw+json",
}

EXT_TO_MIME = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
    ".zip": "application/zip",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
    ".py": "text/x-python",
    ".js": "application/javascript",
    ".html": "text/html",
    ".htm": "text/html",
    ".excalidraw": "application/vnd.excalidraw+json",
}

def detect_mime_type(filename: str, provided_mime: Optional[str] = None) -> str:
    ext = Path(filename).suffix.lower()
    if ext in EXT_TO_MIME:
        return EXT_TO_MIME[ext]
    if provided_mime and provided_mime in ALLOWED_MIME_TYPES:
        return provided_mime
    return "application/octet-stream"

def save_blob(data: bytes) -> Tuple[str, str, int]:
    size = len(data)
    if size > settings.MAX_UPLOAD_BYTES:
        api_error(400, "INVALID_ARGUMENT", f"Файл превышает лимит {settings.MAX_UPLOAD_BYTES} байт")
    sha256_hex = hashlib.sha256(data).hexdigest()
    prefix = sha256_hex[:2]
    rel_path = f"{prefix}/{sha256_hex}"
    full_dir = STORAGE_DIR / prefix
    full_dir.mkdir(parents=True, exist_ok=True)
    full_path = STORAGE_DIR / rel_path
    if not full_path.exists():
        temp_path = STORAGE_DIR / f"{rel_path}.tmp.{secrets.token_hex(4)}"
        temp_path.write_bytes(data)
        temp_path.replace(full_path)
    return sha256_hex, rel_path, size

def get_blob_path(disk_rel_path: str) -> Path:
    return STORAGE_DIR / disk_rel_path

# -----------------------------------------------------------------------------
# Виртуальная иерархия папок (stored_folders)
# -----------------------------------------------------------------------------

def ensure_teacher_folder(conn: sqlite3.Connection, class_id: int, teacher_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM stored_folders WHERE class_id = ? AND folder_kind = 'COURSE_TEACHER_ROOT'",
        (class_id,)
    ).fetchone()
    if row:
        return dict(row)

    folder_id = f"folder_teacher_{class_id}"
    now = int(time.time())
    conn.execute("""
        INSERT INTO stored_folders (id, class_id, owner_user_id, folder_title, folder_kind, created_at)
        VALUES (?, ?, ?, ?, 'COURSE_TEACHER_ROOT', ?)
    """, (folder_id, class_id, teacher_id, f"Папка курса #{class_id}", now))

    conn.execute("UPDATE classes SET teacher_folder_id = ? WHERE id = ?", (folder_id, class_id))
    return {
        "id": folder_id,
        "class_id": class_id,
        "owner_user_id": teacher_id,
        "folder_title": f"Папка курса #{class_id}",
        "folder_kind": "COURSE_TEACHER_ROOT",
        "created_at": now
    }

def ensure_assignment_work_folder(conn: sqlite3.Connection, class_id: int, coursework_id: int, teacher_id: int) -> dict:
    folder_title = f"Задание #{coursework_id}"
    row = conn.execute(
        "SELECT * FROM stored_folders WHERE class_id = ? AND folder_title = ? AND folder_kind = 'ASSIGNMENT_WORK_FOLDER'",
        (class_id, folder_title)
    ).fetchone()
    if row:
        return dict(row)

    folder_id = f"folder_cw_{coursework_id}"
    now = int(time.time())
    conn.execute("""
        INSERT INTO stored_folders (id, class_id, owner_user_id, folder_title, folder_kind, created_at)
        VALUES (?, ?, ?, ?, 'ASSIGNMENT_WORK_FOLDER', ?)
    """, (folder_id, class_id, teacher_id, folder_title, now))

    return {
        "id": folder_id,
        "class_id": class_id,
        "owner_user_id": teacher_id,
        "folder_title": folder_title,
        "folder_kind": "ASSIGNMENT_WORK_FOLDER",
        "created_at": now
    }

def ensure_student_work_folder(conn: sqlite3.Connection, class_id: int, student_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM stored_folders WHERE class_id = ? AND owner_user_id = ? AND folder_kind = 'STUDENT_COURSE_FOLDER'",
        (class_id, student_id)
    ).fetchone()
    if row:
        return dict(row)

    u_row = conn.execute("SELECT handle FROM users WHERE id = ?", (student_id,)).fetchone()
    handle = u_row["handle"] if u_row else f"student_{student_id}"
    folder_title = f"Работы — {handle}"
    folder_id = f"folder_student_{class_id}_{student_id}"
    now = int(time.time())
    conn.execute("""
        INSERT INTO stored_folders (id, class_id, owner_user_id, folder_title, folder_kind, created_at)
        VALUES (?, ?, ?, ?, 'STUDENT_COURSE_FOLDER', ?)
    """, (folder_id, class_id, student_id, folder_title, now))

    conn.execute(
        "UPDATE class_members SET student_folder_id = ? WHERE class_id = ? AND student_id = ?",
        (folder_id, class_id, student_id)
    )

    return {
        "id": folder_id,
        "class_id": class_id,
        "owner_user_id": student_id,
        "folder_title": folder_title,
        "folder_kind": "STUDENT_COURSE_FOLDER",
        "created_at": now
    }

# -----------------------------------------------------------------------------
# Валидатор вложений (строго не более 20 вложений)
# -----------------------------------------------------------------------------

def validate_materials_list(materials: Optional[List[Any]]) -> None:
    if materials and len(materials) > 20:
        api_error(400, "INVALID_ARGUMENT", "Максимум 20 вложений на объект", reason="INVALID_ARGUMENT")

# -----------------------------------------------------------------------------
# STUDENT_COPY и ShareMode
# -----------------------------------------------------------------------------

def ensure_student_copy(conn: sqlite3.Connection, coursework_row: Any, student_id: int) -> None:
    cw_dict = dict(coursework_row)
    cw_id = cw_dict["id"]
    class_id = cw_dict["class_id"]

    raw_materials = cw_dict.get("materials_json") or "[]"
    try:
        materials = json.loads(raw_materials) if isinstance(raw_materials, str) else raw_materials
    except Exception:
        materials = []

    if not isinstance(materials, list):
        return

    for mat in materials:
        if not isinstance(mat, dict):
            continue

        drive_file_wrapper = mat.get("localFile") or mat.get("driveFile")
        if not drive_file_wrapper or not isinstance(drive_file_wrapper, dict):
            continue

        share_mode = drive_file_wrapper.get("shareMode") or mat.get("shareMode")
        if share_mode != "STUDENT_COPY":
            continue

        inner_df = drive_file_wrapper.get("localFile") or drive_file_wrapper.get("driveFile")
        if isinstance(inner_df, dict):
            inner_df = inner_df
        else:
            inner_df = drive_file_wrapper
        template_file_id = inner_df.get("id")
        if not template_file_id:
            continue

        # Проверяем, не была ли уже создана копия для этого шаблона
        existing = conn.execute("""
            SELECT attachment_json FROM submission_attachments
            WHERE coursework_id = ? AND student_id = ? AND created_by_template = 1
        """, (cw_id, student_id)).fetchall()

        already_copied = False
        for att in existing:
            try:
                data = json.loads(att["attachment_json"])
                if data.get("source_template_id") == template_file_id:
                    already_copied = True
                    break
            except Exception:
                pass

        if already_copied:
            continue

        template_row = conn.execute(
            "SELECT * FROM stored_files WHERE id = ?", (template_file_id,)
        ).fetchone()
        if not template_row:
            continue

        now = int(time.time())
        student_folder = ensure_student_work_folder(conn, class_id, student_id)

        # Если это доска .excalidraw, создаем независимый JSON-холст
        is_board = (
            template_row["file_kind"] == "BOARD" or
            template_row["mime_type"] == "application/vnd.excalidraw+json" or
            template_row["file_title"].endswith(".excalidraw")
        )

        if is_board:
            source_blob = get_blob_path(template_row["disk_rel_path"])
            content = source_blob.read_bytes() if source_blob.exists() else b"{}"
            new_sha, new_rel, new_size = save_blob(content + f"\n// student_copy:{student_id}:{now}".encode("utf-8"))
            file_kind = "BOARD"
            ext = "excalidraw"
        else:
            # Дедупликация O(1) дискового места
            new_sha = template_row["sha256_hex"]
            new_rel = template_row["disk_rel_path"]
            new_size = template_row["size_bytes"]
            file_kind = template_row["file_kind"]
            ext = Path(template_row["file_title"]).suffix.lstrip(".") or "bin"

        new_file_id = f"file_{secrets.token_hex(8)}"
        new_file_title = f"Вложение #{new_sha[:8]}.{ext}"

        conn.execute("""
            INSERT INTO stored_files (
                id, folder_id, owner_user_id, file_title, mime_type,
                size_bytes, sha256_hex, disk_rel_path, file_kind,
                source_template_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            new_file_id, student_folder["id"], student_id, new_file_title, template_row["mime_type"],
            new_size, new_sha, new_rel, file_kind,
            template_file_id, now, now
        ))

        # Выдаем права EDIT ученику
        conn.execute("""
            INSERT OR REPLACE INTO file_acl (file_id, user_id, access_mode, updated_at)
            VALUES (?, ?, 'EDIT', ?)
        """, (new_file_id, student_id, now))

        # Выдаем права EDIT учителям курса
        teachers = conn.execute("""
            SELECT teacher_id FROM course_teachers WHERE class_id = ?
            UNION
            SELECT teacher_id FROM classes WHERE id = ?
        """, (class_id, class_id)).fetchall()
        for t in teachers:
            conn.execute("""
                INSERT OR REPLACE INTO file_acl (file_id, user_id, access_mode, updated_at)
                VALUES (?, ?, 'EDIT', ?)
            """, (new_file_id, t[0], now))

        # Прикрепляем в submission_attachments
        attachment_payload = {
            "localFile": {
                "id": new_file_id,
                "title": new_file_title,
                "alternateLink": f"/api/storage/files/{new_file_id}",
                "thumbnailUrl": f"/api/storage/files/{new_file_id}/thumbnail.svg"
            },
            "source_template_id": template_file_id
        }
        conn.execute("""
            INSERT INTO submission_attachments (
                coursework_id, student_id, attachment_json, created_by_template, created_at
            ) VALUES (?, ?, ?, 1, ?)
        """, (cw_id, student_id, json.dumps(attachment_payload, ensure_ascii=False), now))

# -----------------------------------------------------------------------------
# ACL Ownership & Lock Transfer при сдаче и возврате
# -----------------------------------------------------------------------------

def sync_submission_acl(conn: sqlite3.Connection, coursework_id: int, student_id: int, new_v1_state: str) -> None:
    attachments = conn.execute("""
        SELECT attachment_json FROM submission_attachments
        WHERE coursework_id = ? AND student_id = ?
    """, (coursework_id, student_id)).fetchall()

    file_ids = set()
    for att in attachments:
        try:
            data = json.loads(att["attachment_json"])
            file_obj = data.get("localFile") or data.get("driveFile")
            if file_obj and isinstance(file_obj, dict):
                fid = file_obj.get("id")
                if fid:
                    file_ids.add(fid)
        except Exception:
            pass

    if not file_ids:
        return

    course_row = conn.execute("""
        SELECT c.id AS class_id, c.teacher_id
        FROM classes c
        JOIN coursework cw ON cw.class_id = c.id
        WHERE cw.id = ?
    """, (coursework_id,)).fetchone()
    if not course_row:
        return

    class_id = course_row["class_id"]
    teachers = conn.execute("""
        SELECT teacher_id FROM course_teachers WHERE class_id = ?
        UNION
        SELECT ?
    """, (class_id, course_row["teacher_id"])).fetchall()

    now = int(time.time())

    if new_v1_state == "TURNED_IN":
        # Заморозка редактирования учеником (VIEW)
        for fid in file_ids:
            conn.execute("""
                INSERT OR REPLACE INTO file_acl (file_id, user_id, access_mode, updated_at)
                VALUES (?, ?, 'VIEW', ?)
            """, (fid, student_id, now))
            # Учителя курса получают EDIT
            for t in teachers:
                conn.execute("""
                    INSERT OR REPLACE INTO file_acl (file_id, user_id, access_mode, updated_at)
                    VALUES (?, ?, 'EDIT', ?)
                """, (fid, t[0], now))

    elif new_v1_state in ("RECLAIMED_BY_STUDENT", "RETURNED", "NEW", "CREATED"):
        # Возврат права редактирования ученику (EDIT)
        for fid in file_ids:
            conn.execute("""
                INSERT OR REPLACE INTO file_acl (file_id, user_id, access_mode, updated_at)
                VALUES (?, ?, 'EDIT', ?)
            """, (fid, student_id, now))

# -----------------------------------------------------------------------------
# Проверка прав доступа к файлу (check_file_access)
# -----------------------------------------------------------------------------

def check_file_access(conn: sqlite3.Connection, file_id: str, user: dict, required_mode: str = "VIEW") -> bool:
    if user.get("role") == "admin":
        return True

    file_row = conn.execute("SELECT * FROM stored_files WHERE id = ?", (file_id,)).fetchone()
    if not file_row:
        return False

    user_id = user["id"]

    acl_row = conn.execute(
        "SELECT access_mode FROM file_acl WHERE file_id = ? AND user_id = ?",
        (file_id, user_id)
    ).fetchone()

    if required_mode == "EDIT":
        if acl_row:
            return acl_row["access_mode"] in ("EDIT", "OWNER")
        if file_row["owner_user_id"] == user_id:
            return True
        return False

    # required_mode == "VIEW"
    if acl_row:
        return True

    if file_row["owner_user_id"] == user_id:
        return True

    # Проверка, является ли пользователь учителем курса, в чьей папке лежит файл
    if file_row["folder_id"]:
        folder = conn.execute(
            "SELECT class_id FROM stored_folders WHERE id = ?", (file_row["folder_id"],)
        ).fetchone()
        if folder and folder["class_id"]:
            cid = folder["class_id"]
            is_teacher = conn.execute("""
                SELECT 1 FROM classes WHERE id = ? AND teacher_id = ?
                UNION
                SELECT 1 FROM course_teachers WHERE class_id = ? AND teacher_id = ?
            """, (cid, user_id, cid, user_id)).fetchone()
            if is_teacher:
                return True

            is_student = conn.execute("""
                SELECT 1 FROM class_members WHERE class_id = ? AND student_id = ? AND enrollment_active = 1
            """, (cid, user_id)).fetchone()
            if is_student:
                return True

    # Проверка, прикреплен ли файл к опубликованным материалам или сдаче
    in_sub = conn.execute("""
        SELECT sa.student_id, cw.class_id
        FROM submission_attachments sa
        JOIN coursework cw ON cw.id = sa.coursework_id
        WHERE sa.attachment_json LIKE ?
    """, (f'%{file_id}%',)).fetchone()
    if in_sub:
        if in_sub["student_id"] == user_id:
            return True
        cid = in_sub["class_id"]
        is_teacher = conn.execute("""
            SELECT 1 FROM classes WHERE id = ? AND teacher_id = ?
            UNION
            SELECT 1 FROM course_teachers WHERE class_id = ? AND teacher_id = ?
        """, (cid, user_id, cid, user_id)).fetchone()
        if is_teacher:
            return True

    return False

# -----------------------------------------------------------------------------
# SVG-генератор локальных превью
# -----------------------------------------------------------------------------

def generate_svg_thumbnail(file_title: str, mime_type: str, file_kind: str = "FILE") -> str:
    color = "#2563eb"
    badge = "FILE"

    if "pdf" in mime_type:
        color = "#dc2626"
        badge = "PDF"
    elif "image" in mime_type:
        color = "#16a34a"
        badge = "IMG"
    elif "video" in mime_type:
        color = "#ea580c"
        badge = "VID"
    elif "audio" in mime_type:
        color = "#0891b2"
        badge = "AUD"
    elif file_kind == "BOARD" or "excalidraw" in mime_type:
        color = "#7c3aed"
        badge = "BOARD"
    elif "python" in mime_type or "javascript" in mime_type or "html" in mime_type:
        color = "#059669"
        badge = "CODE"
    elif "zip" in mime_type:
        color = "#475569"
        badge = "ZIP"

    safe_title = file_title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")[:24]

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="240" height="160" viewBox="0 0 240 160">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#f8fafc"/>
      <stop offset="100%" stop-color="#e2e8f0"/>
    </linearGradient>
  </defs>
  <rect width="240" height="160" rx="8" fill="url(#bg)"/>
  <rect x="20" y="20" width="200" height="120" rx="6" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.5"/>
  <rect x="35" y="35" width="48" height="24" rx="4" fill="{color}"/>
  <text x="59" y="51" fill="#ffffff" font-family="system-ui, sans-serif" font-size="11" font-weight="700" text-anchor="middle">{badge}</text>
  <text x="35" y="90" fill="#1e293b" font-family="system-ui, sans-serif" font-size="13" font-weight="600">{safe_title}</text>
  <text x="35" y="112" fill="#64748b" font-family="system-ui, sans-serif" font-size="11">{mime_type[:28]}</text>
</svg>"""
