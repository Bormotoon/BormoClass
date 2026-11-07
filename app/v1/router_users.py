import uuid
import time
import json
import hashlib
from typing import Optional
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.db import db_session
from app.v1.protocol import api_error, resolve_user_id
from app.v1.rbac import (
    resolve_auth_context,
    require_scopes,
    can_create_course,
    SCOPE_PROFILE_EMAILS,
    SCOPE_PROFILE_PHOTOS,
    ALL_24_SCOPES
)
from app.v1.schemas import UserProfile, Name, GlobalPermission

router = APIRouter(tags=["userProfiles"])

class OAuthClientCreateRequest(BaseModel):
    client_title: str
    scopes: Optional[list[str]] = None

class OAuthTokenRequest(BaseModel):
    client_id: str
    client_secret: str
    scopes: Optional[list[str]] = None

@router.get("/v1/userProfiles/{userId}", response_model=UserProfile)
def get_user_profile(userId: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        target_uid = resolve_user_id(conn, userId, ctx.user, allow_wildcard=False)

        # Проверка видимости профиля
        is_self = (target_uid == ctx.user["id"])
        is_admin = (ctx.user.get("role") == "admin")

        if not is_self and not is_admin:
            # Проверяем, есть ли общий курс или отношение опекун-ученик
            common = conn.execute(
                """
                SELECT 1 FROM class_members cm1
                JOIN class_members cm2 ON cm1.class_id = cm2.class_id
                WHERE cm1.student_id = ? AND cm2.student_id = ? AND cm1.enrollment_active = 1 AND cm2.enrollment_active = 1
                UNION
                SELECT 1 FROM classes c
                JOIN class_members cm ON c.id = cm.class_id
                WHERE (c.teacher_id = ? AND cm.student_id = ?) OR (c.teacher_id = ? AND cm.student_id = ?)
                UNION
                SELECT 1 FROM guardians g
                WHERE (g.student_id = ? AND g.guardian_user_id = ?) OR (g.student_id = ? AND g.guardian_user_id = ?)
                LIMIT 1
                """,
                (ctx.user["id"], target_uid, ctx.user["id"], target_uid, target_uid, ctx.user["id"], target_uid, ctx.user["id"], ctx.user["id"], target_uid)
            ).fetchone()
            if not common:
                api_error(404, "NOT_FOUND", "Профиль пользователя не найден")

        row = conn.execute("SELECT * FROM users WHERE id = ?", (target_uid,)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Профиль пользователя не найден")

        u = dict(row)
        permissions = []
        if can_create_course(u):
            permissions.append(GlobalPermission(permission="CREATE_COURSE"))

        email_address = None
        if SCOPE_PROFILE_EMAILS in ctx.scopes or ctx.is_first_party:
            email_address = f"{u['handle']}@bormoclass.local"

        photo_url = None
        if SCOPE_PROFILE_PHOTOS in ctx.scopes or ctx.is_first_party:
            seed = u.get("avatar_seed", 1)
            photo_url = f"/api/v1-avatar/{seed}.svg"

        return UserProfile(
            id=str(u["id"]),
            name=Name(
                givenName=u["handle"],
                familyName="",
                fullName=u["handle"]
            ),
            emailAddress=email_address,
            photoUrl=photo_url,
            permissions=permissions,
            verifiedTeacher=bool(u.get("verified_teacher", 0))
        )

@router.post("/api/v1-oauth/clients")
def create_oauth_client(req: OAuthClientCreateRequest, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        client_id = f"client_{uuid.uuid4().hex[:16]}"
        client_secret = f"sec_{uuid.uuid4().hex}"
        secret_hash = hashlib.sha256(client_secret.encode("utf-8")).hexdigest()
        scopes_json = json.dumps(req.scopes or list(ALL_24_SCOPES))

        conn.execute(
            """INSERT INTO oauth_clients (client_id, client_secret_hash, client_title, scopes_json, owner_user_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (client_id, secret_hash, req.client_title, scopes_json, ctx.user["id"], int(time.time()))
        )
        return {
            "client_id": client_id,
            "client_secret": client_secret,
            "client_title": req.client_title
        }

@router.post("/api/v1-oauth/token")
def issue_oauth_token(req: OAuthTokenRequest, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        client_row = conn.execute(
            "SELECT * FROM oauth_clients WHERE client_id = ?",
            (req.client_id,)
        ).fetchone()
        if not client_row:
            api_error(401, "UNAUTHENTICATED", "Недействительный client_id")

        secret_hash = hashlib.sha256(req.client_secret.encode("utf-8")).hexdigest()
        if not hashlib.sha256(req.client_secret.encode("utf-8")).hexdigest() == client_row["client_secret_hash"]:
            api_error(401, "UNAUTHENTICATED", "Неверный client_secret")

        allowed_scopes = set(json.loads(client_row["scopes_json"]))
        requested_scopes = set(req.scopes) if req.scopes else allowed_scopes
        final_scopes = list(requested_scopes.intersection(allowed_scopes))

        token_raw = f"ya29.bormo_{uuid.uuid4().hex}{uuid.uuid4().hex}"
        token_hash = hashlib.sha256(token_raw.encode("utf-8")).hexdigest()
        ttl = 7 * 86400
        expires_at = int(time.time()) + ttl

        conn.execute(
            """INSERT INTO oauth_tokens (token_hash, client_id, user_id, scopes_json, expires_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (token_hash, req.client_id, ctx.user["id"], json.dumps(final_scopes), expires_at, int(time.time()))
        )

        return {
            "access_token": token_raw,
            "token_type": "bearer",
            "expires_in": ttl,
            "scope": " ".join(final_scopes)
        }

@router.get("/api/v1-avatar/{seed}.svg")
def generate_avatar_svg(seed: str):
    try:
        val = int(seed)
    except ValueError:
        val = sum(ord(c) for c in seed)

    colors = [
        "#1a73e8", "#1e8e3e", "#d93025", "#f9ab00", "#e37400",
        "#9334e6", "#12b5cb", "#fa7b17", "#007b83", "#e8710a"
    ]
    bg = colors[val % len(colors)]
    fg = colors[(val * 3 + 1) % len(colors)]
    shape_kind = val % 4

    if shape_kind == 0:
        shape = f'<circle cx="50" cy="50" r="30" fill="{fg}" />'
    elif shape_kind == 1:
        shape = f'<rect x="25" y="25" width="50" height="50" rx="10" fill="{fg}" />'
    elif shape_kind == 2:
        shape = f'<polygon points="50,20 80,75 20,75" fill="{fg}" />'
    else:
        shape = f'<path d="M50 20 L75 50 L50 80 L25 50 Z" fill="{fg}" />'

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">
  <rect width="100" height="100" rx="50" fill="{bg}" />
  {shape}
</svg>'''
    return Response(content=svg, media_type="image/svg+xml")
