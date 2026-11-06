import time
from typing import Optional, Dict, Any
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from fastapi import HTTPException, status
from app.config import settings
from app.db import db_session
from app.passport.crypto_cookie import verify_cookie_token, sign_cookie_payload, compute_user_ad_free

class PassportMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        token = request.cookies.get(settings.COOKIE_NAME)
        if not token:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()

        user_data = verify_cookie_token(token)
        request.state.user = user_data
        trial_started = False

        if user_data:
            user_id = user_data.get("user_id")
            role = user_data.get("role")
            now = int(time.time())

            # Проверяем триал для учителя при мутирующем учительском запросе к классам/заданиям
            if not request.url.path.startswith("/api/passport/") and role in ("teacher", "admin") and request.method in ("POST", "PUT", "PATCH", "DELETE"):
                with db_session() as conn:
                    user_row = conn.execute("SELECT pro_until, trial_used FROM users WHERE id = ?", (user_id,)).fetchone()
                    if user_row and user_row["trial_used"] == 0 and user_row["pro_until"] < now:
                        new_pro = now + 7 * 86400
                        conn.execute(
                            "UPDATE users SET pro_until = ?, trial_used = 1 WHERE id = ?",
                            (new_pro, user_id)
                        )
                        user_data["ad_free"] = True
                        trial_started = True

        response = await call_next(request)

        if trial_started and user_data:
            response.headers["X-Passport-Trial-Started"] = "1"
            new_token = sign_cookie_payload(user_data)
            cookie_domain = settings.COOKIE_DOMAIN or None
            response.set_cookie(
                key=settings.COOKIE_NAME,
                value=new_token,
                httponly=True,
                samesite="lax",
                secure=False,
                domain=cookie_domain,
                max_age=30 * 86400
            )

        return response

def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    return getattr(request.state, "user", None)

def require_user(request: Request) -> Dict[str, Any]:
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация"
        )
    return user

def require_teacher(request: Request) -> Dict[str, Any]:
    user = require_user(request)
    if user.get("role") not in ("teacher", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только учителям"
        )
    return user

def require_student(request: Request) -> Dict[str, Any]:
    user = require_user(request)
    if user.get("role") != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только ученикам"
        )
    return user
