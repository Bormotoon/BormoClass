import os
import json
import time
import secrets
import socket
import ipaddress
import urllib.parse
from pathlib import Path
from typing import Optional, List, Any

from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, Response
from pydantic import BaseModel, Field

from app.config import settings
from app.db import db_session
from app.v1.rbac import resolve_auth_context
from app.v1.protocol import api_error
from app.storage.engine import (
    ALLOWED_MIME_TYPES,
    detect_mime_type,
    save_blob,
    get_blob_path,
    check_file_access,
    generate_svg_thumbnail
)

router = APIRouter(prefix="/api/storage", tags=["storage"])

# -----------------------------------------------------------------------------
# Range-стриминг файлов (HTTP 206 Partial Content)
# -----------------------------------------------------------------------------

def stream_file_with_range(
    blob_path: Path,
    mime_type: str,
    file_title: str,
    range_header: Optional[str] = None,
    is_download: bool = False
) -> Response:
    if not blob_path.exists():
        raise HTTPException(status_code=404, detail="Файл на диске не найден")

    file_size = blob_path.stat().st_size
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": mime_type,
    }

    # Защита от Stored XSS для HTML и SVG
    if mime_type in ("text/html", "image/svg+xml"):
        headers["Content-Security-Policy"] = "sandbox"
        headers["X-Content-Type-Options"] = "nosniff"

    if is_download:
        headers["Content-Disposition"] = f'attachment; filename="{file_title}"'
    else:
        headers["Content-Disposition"] = f'inline; filename="{file_title}"'

    if not range_header or not range_header.startswith("bytes="):
        content = blob_path.read_bytes()
        headers["Content-Length"] = str(file_size)
        return Response(content=content, status_code=200, headers=headers)

    range_val = range_header[6:].strip()
    try:
        if "-" not in range_val:
            raise ValueError()
        start_str, end_str = range_val.split("-", 1)
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
        if start >= file_size or end >= file_size or start > end:
            raise ValueError()
    except Exception:
        return Response(
            content=b"",
            status_code=416,
            headers={"Content-Range": f"bytes */{file_size}"}
        )

    chunk_length = end - start + 1
    with open(blob_path, "rb") as f:
        f.seek(start)
        chunk = f.read(chunk_length)

    headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    headers["Content-Length"] = str(chunk_length)
    return Response(content=chunk, status_code=206, headers=headers)

# -----------------------------------------------------------------------------
# Эндпоинты загрузки и отдачи файлов
# -----------------------------------------------------------------------------

@router.post("/upload")
def upload_file(
    request: Request,
    file: UploadFile = File(...),
    folder_id: Optional[str] = Form(None),
    class_id: Optional[int] = Form(None)
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        user = ctx.user

        data = file.file.read()
        if len(data) > settings.MAX_UPLOAD_BYTES:
            api_error(400, "INVALID_ARGUMENT", f"Файл превышает лимит {settings.MAX_UPLOAD_BYTES} байт")

        filename = file.filename or "file.bin"
        detected_mime = detect_mime_type(filename, file.content_type)
        if detected_mime not in ALLOWED_MIME_TYPES and detected_mime != "application/octet-stream":
            api_error(400, "INVALID_ARGUMENT", f"Тип файла '{detected_mime}' запрещен политикой безопасности")

        sha256_hex, rel_path, size_bytes = save_blob(data)
        file_id = f"file_{secrets.token_hex(8)}"
        now = int(time.time())

        file_kind = "BOARD" if (filename.endswith(".excalidraw") or detected_mime == "application/vnd.excalidraw+json") else "FILE"

        conn.execute("""
            INSERT INTO stored_files (
                id, folder_id, owner_user_id, file_title, mime_type,
                size_bytes, sha256_hex, disk_rel_path, file_kind,
                source_template_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
        """, (file_id, folder_id, user["id"], filename, detected_mime, size_bytes, sha256_hex, rel_path, file_kind, now, now))

        conn.execute("""
            INSERT OR REPLACE INTO file_acl (file_id, user_id, access_mode, updated_at)
            VALUES (?, ?, 'OWNER', ?)
        """, (file_id, user["id"], now))

        if class_id:
            teachers = conn.execute("""
                SELECT teacher_id FROM course_teachers WHERE class_id = ?
                UNION
                SELECT teacher_id FROM classes WHERE id = ?
            """, (class_id, class_id)).fetchall()
            for t in teachers:
                conn.execute("""
                    INSERT OR REPLACE INTO file_acl (file_id, user_id, access_mode, updated_at)
                    VALUES (?, ?, 'EDIT', ?)
                """, (file_id, t[0], now))

        return {
            "id": file_id,
            "title": filename,
            "alternateLink": f"/api/storage/files/{file_id}",
            "thumbnailUrl": f"/api/storage/files/{file_id}/thumbnail.svg",
            "mimeType": detected_mime,
            "sizeBytes": size_bytes
        }

@router.get("/files/{file_id}")
def get_file(file_id: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        user = ctx.user

        if not check_file_access(conn, file_id, user, required_mode="VIEW"):
            api_error(403, "PERMISSION_DENIED", "Нет доступа к запрашиваемому файлу")

        row = conn.execute("SELECT * FROM stored_files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Файл не найден")

        blob_path = get_blob_path(row["disk_rel_path"])
        range_header = request.headers.get("Range")
        return stream_file_with_range(
            blob_path=blob_path,
            mime_type=row["mime_type"],
            file_title=row["file_title"],
            range_header=range_header,
            is_download=False
        )

@router.get("/files/{file_id}/download")
def download_file(file_id: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        user = ctx.user

        if not check_file_access(conn, file_id, user, required_mode="VIEW"):
            api_error(403, "PERMISSION_DENIED", "Нет доступа к запрашиваемому файлу")

        row = conn.execute("SELECT * FROM stored_files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Файл не найден")

        blob_path = get_blob_path(row["disk_rel_path"])
        range_header = request.headers.get("Range")
        return stream_file_with_range(
            blob_path=blob_path,
            mime_type=row["mime_type"],
            file_title=row["file_title"],
            range_header=range_header,
            is_download=True
        )

@router.get("/files/{file_id}/thumbnail.svg")
def get_file_thumbnail(file_id: str, request: Request):
    with db_session() as conn:
        row = conn.execute("SELECT file_title, mime_type, file_kind FROM stored_files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            svg = generate_svg_thumbnail("Файл", "application/octet-stream")
        else:
            svg = generate_svg_thumbnail(row["file_title"], row["mime_type"], row["file_kind"])

        return Response(content=svg, media_type="image/svg+xml")

# -----------------------------------------------------------------------------
# SSRF-защита и Smart Link Upgrade
# -----------------------------------------------------------------------------

def is_ip_private(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private or
            ip.is_loopback or
            ip.is_link_local or
            ip.is_multicast or
            ip.is_reserved or
            ip.is_unspecified
        )
    except ValueError:
        return False

class LinkPreviewRequest(BaseModel):
    url: str

@router.post("/link-preview")
def link_preview(req: LinkPreviewRequest, request: Request):
    url_str = req.url.strip()
    if not url_str:
        api_error(400, "INVALID_ARGUMENT", "URL не может быть пустым")

    # Smart Link Upgrade для внутренних относительных ссылок
    with db_session() as conn:
        # Проверка на внутренний файл /api/storage/files/{id}
        if "/api/storage/files/" in url_str:
            parts = url_str.split("/api/storage/files/")
            fid = parts[1].split("/")[0].split("?")[0]
            row = conn.execute("SELECT * FROM stored_files WHERE id = ?", (fid,)).fetchone()
            if row:
                return {
                    "type": "DRIVE_FILE",
                    "driveFile": {
                        "id": row["id"],
                        "title": row["file_title"],
                        "alternateLink": f"/api/storage/files/{row['id']}",
                        "thumbnailUrl": f"/api/storage/files/{row['id']}/thumbnail.svg"
                    }
                }

        # Проверка на внутренний квиз /quiz/{id} или /api/classroom/quizzes/{id}
        if "/quiz/" in url_str or "/quizzes/" in url_str:
            tokens = url_str.rstrip("/").split("/")
            raw_id = tokens[-1].split("?")[0]
            try:
                qid = int(raw_id)
                q_row = conn.execute("SELECT quiz_title FROM quizzes WHERE id = ?", (qid,)).fetchone()
                if q_row:
                    return {
                        "type": "FORM",
                        "form": {
                            "formUrl": url_str,
                            "responseUrl": url_str,
                            "title": q_row["quiz_title"]
                        }
                    }
            except ValueError:
                pass

        # Проверка на доску /board/{id}
        if "/board/" in url_str:
            tokens = url_str.rstrip("/").split("/")
            raw_id = tokens[-1].split("?")[0]
            return {
                "type": "DRIVE_FILE",
                "driveFile": {
                    "id": f"board_{raw_id}",
                    "title": f"Интерактивная доска #{raw_id}",
                    "alternateLink": url_str,
                    "thumbnailUrl": f"/api/storage/files/board_{raw_id}/thumbnail.svg"
                }
            }

    # Валидация внешних URL на SSRF
    parsed = urllib.parse.urlparse(url_str)
    if parsed.scheme not in ("http", "https"):
        api_error(400, "INVALID_ARGUMENT", "Поддерживаются только URL с протоколами http и https", reason="SSRF_BLOCKED")

    hostname = parsed.hostname
    if not hostname:
        api_error(400, "INVALID_ARGUMENT", "Некорректный адрес URL", reason="SSRF_BLOCKED")

    if hostname.lower() in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        api_error(400, "INVALID_ARGUMENT", "Доступ к внутренним адресам запрещен", reason="SSRF_BLOCKED")

    try:
        addr_infos = socket.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in addr_infos:
            ip_str = sockaddr[0]
            if is_ip_private(ip_str):
                api_error(400, "INVALID_ARGUMENT", f"Доступ к внутренним IP ({ip_str}) запрещен", reason="SSRF_BLOCKED")
    except socket.gaierror:
        pass

    return {
        "type": "LINK",
        "link": {
            "url": url_str,
            "title": hostname
        }
    }

# -----------------------------------------------------------------------------
# Аннотации к файлам (file_annotations — SpeedGrader)
# -----------------------------------------------------------------------------

class AnnotationCreateRequest(BaseModel):
    page_num: int = Field(default=1, ge=1)
    rect_json: str = Field(default="{}")
    stroke_json: str = Field(default="[]")
    body_text: str = Field(default="")
    coursework_id: Optional[int] = None
    student_id: Optional[int] = None

@router.get("/files/{file_id}/annotations")
def get_file_annotations(file_id: str, request: Request, page_num: Optional[int] = None):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        user = ctx.user

        if not check_file_access(conn, file_id, user, required_mode="VIEW"):
            api_error(403, "PERMISSION_DENIED", "Нет доступа к аннотациям файла")

        if page_num:
            rows = conn.execute("""
                SELECT fa.*, u.handle AS author_handle
                FROM file_annotations fa
                JOIN users u ON fa.author_user_id = u.id
                WHERE fa.file_id = ? AND fa.page_num = ?
                ORDER BY fa.id ASC
            """, (file_id, page_num)).fetchall()
        else:
            rows = conn.execute("""
                SELECT fa.*, u.handle AS author_handle
                FROM file_annotations fa
                JOIN users u ON fa.author_user_id = u.id
                WHERE fa.file_id = ?
                ORDER BY fa.page_num ASC, fa.id ASC
            """, (file_id,)).fetchall()

        return [dict(r) for r in rows]

@router.post("/files/{file_id}/annotations")
def create_file_annotation(file_id: str, req: AnnotationCreateRequest, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        user = ctx.user

        file_row = conn.execute("SELECT * FROM stored_files WHERE id = ?", (file_id,)).fetchone()
        if not file_row:
            api_error(404, "NOT_FOUND", "Файл не найден")

        now = int(time.time())
        cursor = conn.execute("""
            INSERT INTO file_annotations (
                file_id, coursework_id, student_id, author_user_id,
                page_num, rect_json, stroke_json, body_text, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            file_id, req.coursework_id, req.student_id, user["id"],
            req.page_num, req.rect_json, req.stroke_json, req.body_text, now
        ))

        return {
            "id": cursor.lastrowid,
            "file_id": file_id,
            "coursework_id": req.coursework_id,
            "student_id": req.student_id,
            "author_user_id": user["id"],
            "page_num": req.page_num,
            "rect_json": req.rect_json,
            "stroke_json": req.stroke_json,
            "body_text": req.body_text,
            "created_at": now
        }
