import time
from typing import Optional, List
from fastapi import APIRouter, Request, Response, HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings
from app.db import db_session
from app.passport.generator import (
    create_unique_callsign,
    generate_recovery_words,
    hash_secret,
    verify_secret
)
from app.passport.crypto_cookie import sign_cookie_payload
from app.passport.recess import (
    spend_recess_seconds,
    award_recess_seconds,
    is_recess_locked_for_student
)
from app.passport.middleware import require_user, require_teacher

router = APIRouter(prefix="/api/passport", tags=["passport"])

# -----------------------------------------------------------------------------
# Pydantic-схемы (СТРОГО Zero-PII: 0 полей ПД)
# -----------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    role: str = Field(default="student", pattern="^(student|teacher)$")
    password: str = Field(min_length=4, max_length=128)

class LoginRequest(BaseModel):
    handle: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=128)

class RecoverRequest(BaseModel):
    handle: str = Field(min_length=3, max_length=64)
    recovery_words: List[str] = Field(min_length=4, max_length=4)
    new_password: str = Field(min_length=4, max_length=128)

class SolveTaskRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=128)
    score: int = Field(ge=0, le=100)
    coursework_id: Optional[int] = None

class SpendRecessRequest(BaseModel):
    seconds: int = Field(gt=0)

# -----------------------------------------------------------------------------
# Вспомогательные функции
# -----------------------------------------------------------------------------

def _set_auth_cookie(response: Response, user_data: dict) -> None:
    token = sign_cookie_payload(user_data)
    cookie_domain = settings.COOKIE_DOMAIN or None
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        domain=cookie_domain,
        max_age=30 * 86400
    )

def _clear_auth_cookie(response: Response) -> None:
    cookie_domain = settings.COOKIE_DOMAIN or None
    response.delete_cookie(
        key=settings.COOKIE_NAME,
        domain=cookie_domain,
        httponly=True,
        samesite="lax"
    )

def score_to_grade_five(score: int) -> int:
    if score < 50:
        return 2
    if score < 70:
        return 3
    if score < 85:
        return 4
    return 5

# -----------------------------------------------------------------------------
# Синхронные эндпоинты (def, НЕ async def для SQLite)
# -----------------------------------------------------------------------------

@router.get("/me")
def get_me(request: Request):
    user_state = getattr(request.state, "user", None)
    if not user_state:
        return {"user": None}

    user_id = user_state.get("user_id")
    with db_session() as conn:
        row = conn.execute(
            "SELECT id, handle, role, avatar_seed, recess_seconds, created_at FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        if not row:
            return {"user": None}

        recess_locked = is_recess_locked_for_student(conn, row["id"]) if row["role"] == "student" else False

        user_info = {
            "id": row["id"],
            "handle": row["handle"],
            "role": row["role"],
            "avatar_seed": row["avatar_seed"],
            "recess_seconds": row["recess_seconds"],
            "created_at": row["created_at"],
            "recess_locked": recess_locked
        }
        return {"user": user_info}

@router.post("/register")
def register(req: RegisterRequest, response: Response):
    now = int(time.time())
    with db_session() as conn:
        handle = create_unique_callsign(conn)
        recovery_words = generate_recovery_words(4)
        recovery_text = " ".join(recovery_words)

        password_hash = hash_secret(req.password)
        recovery_words_hash = hash_secret(recovery_text)
        initial_recess = 300 if req.role == "student" else 0
        avatar_seed = (abs(hash(handle)) % 999) + 1

        cursor = conn.execute("""
            INSERT INTO users (
                handle, role, password_hash, recovery_words_hash,
                avatar_seed, recess_seconds, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (handle, req.role, password_hash, recovery_words_hash, avatar_seed, initial_recess, now))
        
        user_id = cursor.lastrowid

        user_data = {
            "user_id": user_id,
            "handle": handle,
            "role": req.role,
            "avatar_seed": avatar_seed
        }
        _set_auth_cookie(response, user_data)

        return {
            "user": {
                "id": user_id,
                "handle": handle,
                "role": req.role,
                "avatar_seed": avatar_seed,
                "recess_seconds": initial_recess
            },
            "recovery_words": recovery_words
        }

@router.post("/login")
def login(req: LoginRequest, response: Response):
    with db_session() as conn:
        row = conn.execute(
            "SELECT id, handle, role, password_hash, avatar_seed, recess_seconds, created_at FROM users WHERE handle = ?",
            (req.handle.strip(),)
        ).fetchone()

        if not row or not verify_secret(req.password, row["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный позывной или пароль"
            )

        user_data = {
            "user_id": row["id"],
            "handle": row["handle"],
            "role": row["role"],
            "avatar_seed": row["avatar_seed"]
        }
        _set_auth_cookie(response, user_data)

        return {
            "user": {
                "id": row["id"],
                "handle": row["handle"],
                "role": row["role"],
                "avatar_seed": row["avatar_seed"],
                "recess_seconds": row["recess_seconds"],
                "created_at": row["created_at"]
            }
        }

@router.post("/recover")
def recover_password(req: RecoverRequest):
    recovery_text = " ".join([w.strip().lower() for w in req.recovery_words])
    with db_session() as conn:
        row = conn.execute(
            "SELECT id, recovery_words_hash FROM users WHERE handle = ?",
            (req.handle.strip(),)
        ).fetchone()

        if not row or not verify_secret(recovery_text, row["recovery_words_hash"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Неверные секретные слова восстановления"
            )

        new_hash = hash_secret(req.new_password)
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, row["id"]))
        return {"ok": True, "message": "Пароль успешно обновлён"}

@router.post("/logout")
def logout(response: Response):
    _clear_auth_cookie(response)
    return {"ok": True}

@router.post("/solve")
def solve_task(req: SolveTaskRequest, request: Request):
    user = require_user(request)
    user_id = user["user_id"]
    now = int(time.time())
    grade_five = score_to_grade_five(req.score)

    with db_session() as conn:
        # Пытаемся найти привязанный класс через coursework_id
        target_class_id = None
        recess_reward = 300
        if req.coursework_id:
            cw = conn.execute(
                "SELECT id, class_id, recess_reward FROM coursework WHERE id = ?",
                (req.coursework_id,)
            ).fetchone()
            if cw:
                target_class_id = cw["class_id"]
                recess_reward = cw["recess_reward"]

        # 1. Идемпотентная вставка в solved_tasks
        cursor = conn.execute("""
            INSERT OR IGNORE INTO solved_tasks (user_id, task_id, class_id, score, solved_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, req.task_id, target_class_id, req.score, now))
        
        is_first_task_solve = (cursor.rowcount == 1)
        awarded_recess = False

        # 2. Если передан coursework_id, обновляем submissions
        if req.coursework_id:
            existing_sub = conn.execute(
                "SELECT status FROM submissions WHERE coursework_id = ? AND student_id = ?",
                (req.coursework_id, user_id)
            ).fetchone()

            if not existing_sub:
                conn.execute("""
                    INSERT INTO submissions (
                        coursework_id, student_id, status, payload_json, grade_points, grade_five, updated_at
                    ) VALUES (?, ?, 'turned_in', ?, ?, ?, ?)
                """, (req.coursework_id, user_id, f'{{"task_id":"{req.task_id}","score":{req.score}}}', req.score, grade_five, now))
                # Переход из пустого/assigned в turned_in
                if is_first_task_solve:
                    award_recess_seconds(conn, user_id, recess_reward)
                    awarded_recess = True
            elif existing_sub["status"] == "assigned":
                conn.execute("""
                    UPDATE submissions 
                    SET status = 'turned_in',
                        payload_json = ?,
                        grade_points = ?,
                        grade_five = ?,
                        updated_at = ?
                    WHERE coursework_id = ? AND student_id = ?
                """, (f'{{"task_id":"{req.task_id}","score":{req.score}}}', req.score, grade_five, now, req.coursework_id, user_id))
                award_recess_seconds(conn, user_id, recess_reward)
                awarded_recess = True
            else:
                # Уже сдано ранее - обновляем балл, но секунды не начисляем повторно
                conn.execute("""
                    UPDATE submissions 
                    SET payload_json = ?,
                        grade_points = ?,
                        grade_five = ?,
                        updated_at = ?
                    WHERE coursework_id = ? AND student_id = ?
                """, (f'{{"task_id":"{req.task_id}","score":{req.score}}}', req.score, grade_five, now, req.coursework_id, user_id))
        else:
            if is_first_task_solve:
                award_recess_seconds(conn, user_id, recess_reward)
                awarded_recess = True

        # Уведомляем SSE-подписчиков класса, если есть
        if target_class_id:
            try:
                from app.classroom.sse_hub import sse_hub
                import asyncio
                sse_hub.notify_class(target_class_id, "submission_updated", {
                    "coursework_id": req.coursework_id,
                    "student_id": user_id,
                    "grade_five": grade_five,
                    "score": req.score
                })
            except Exception:
                pass

        user_row = conn.execute("SELECT recess_seconds FROM users WHERE id = ?", (user_id,)).fetchone()
        recess_balance = user_row["recess_seconds"] if user_row else 0

        return {
            "ok": True,
            "awarded_recess": awarded_recess,
            "recess_seconds": recess_balance,
            "grade_five": grade_five,
            "score": req.score
        }

@router.post("/recess/spend")
def spend_recess(req: SpendRecessRequest, request: Request):
    user = require_user(request)
    user_id = user["user_id"]
    with db_session() as conn:
        ok, balance, msg = spend_recess_seconds(conn, user_id, req.seconds)
        if not ok:
            status_code = status.HTTP_403_FORBIDDEN if "заблокированы" in msg else status.HTTP_400_BAD_REQUEST
            raise HTTPException(status_code=status_code, detail=msg)
        return {"ok": True, "remaining_seconds": balance, "message": msg}
