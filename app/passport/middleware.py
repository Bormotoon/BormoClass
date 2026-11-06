import time
from typing import Optional, Dict, Any
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from fastapi import HTTPException, status
from app.config import settings
from app.db import db_session
from app.passport.crypto_cookie import verify_cookie_token, sign_cookie_payload

class PassportMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        token = request.cookies.get(settings.COOKIE_NAME)
        if not token:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()

        request.state.user = verify_cookie_token(token)

        return await call_next(request)

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
