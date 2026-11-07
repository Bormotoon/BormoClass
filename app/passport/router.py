import time
import secrets
import json
from typing import Optional, List
from fastapi import APIRouter, Request, Response, HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings
from app.db import db_session
from app.passport.dictionaries import ADJECTIVES, NOUNS, RECOVERY_WORDS
from app.passport.generator import (
    create_unique_callsign,
    generate_callsign,
    generate_recovery_words,
    hash_secret,
    verify_secret
)
from app.passport.crypto import (
    issue_ticket,
    check_ticket,
    pick_recovery_words,
    normalize_words,
    normalize_code,
    code_hash,
    RateLimiter
)
from app.passport.crypto_cookie import sign_cookie_payload, _b64url_encode
from app.passport.recess import (
    spend_recess_seconds,
    award_recess_seconds,
    is_recess_locked_for_student
)
from app.passport.middleware import require_user, require_teacher

router = APIRouter(prefix="/api/passport", tags=["passport"])

limiter = RateLimiter(clock=time.time)

# -----------------------------------------------------------------------------
# Pydantic-схемы (СТРОГО Zero-PII: 0 полей ПД)
# -----------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    role: str = Field(default="student", pattern="^(student|teacher)$")
    password: str = Field(min_length=4, max_length=128)
    handle: Optional[str] = None
    ticket: Optional[str] = None
    e2ee_public_key: Optional[str] = None
    e2ee_key_bundle_json: Optional[str] = None

class LoginRequest(BaseModel):
    handle: str = Field(min_length=3, max_length=64)
    password: Optional[str] = None
    temp_pin: Optional[str] = None
    new_password: Optional[str] = None
    ticket: Optional[str] = None
    e2ee_public_key: Optional[str] = None
    e2ee_key_bundle_json: Optional[str] = None

class RecoverRequest(BaseModel):
    handle: str = Field(min_length=3, max_length=64)
    recovery_words: Optional[List[str]] = None
    words: Optional[List[str]] = None
    new_password: str = Field(min_length=4, max_length=128)
    ticket: Optional[str] = None
    e2ee_public_key: Optional[str] = None
    e2ee_key_bundle_json: Optional[str] = None

class E2EEBundleRequest(BaseModel):
    e2ee_public_key: str = ""
    e2ee_key_bundle_json: str = "{}"

class SolveTaskRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=128)
    score: int = Field(ge=0, le=100)
    coursework_id: Optional[int] = None

class SpendRecessRequest(BaseModel):
    seconds: int = Field(gt=0)

class CodeRequest(BaseModel):
    code: str = Field(min_length=4, max_length=64)

# -----------------------------------------------------------------------------
# Вспомогательные функции
# -----------------------------------------------------------------------------

def canon_handle(raw: str) -> str:
    if not isinstance(raw, str):
        return ""
    parts = raw.strip().replace("ё", "е").replace("Ё", "Е").split("-")
    return "-".join(p[:1].upper() + p[1:].lower() for p in parts)

def is_valid_dictionary_handle(handle: str) -> bool:
    parts = canon_handle(handle).split("-")
    return (
        len(parts) == 3
        and parts[0] in ADJECTIVES
        and parts[1] in NOUNS
        and len(parts[2]) in (3, 4)
        and parts[2].isdigit()
    )

def _set_auth_cookie(response: Response, user_data: dict) -> None:
    now = int(time.time())
    ttl = 30 * 86400
    exp = now + ttl
    uid = user_data.get("user_id") or user_data.get("id")
    handle = user_data.get("handle")
    role = user_data.get("role")
    seed = user_data.get("avatar_seed") or 1
    recess_bal = user_data.get("recess_seconds") or 0
    pro = user_data.get("pro_until") or user_data.get("pro") or 0
    cid = user_data.get("class_id") or user_data.get("cid")

    payload = {
        "user_id": uid,
        "uid": uid,
        "handle": handle,
        "h": handle,
        "role": role,
        "avatar_seed": seed,
        "seed": seed,
        "pro": pro,
        "cid": cid,
        "ad_free": True,
        "adf": pro if pro > now else exp,
        "rec_exp": 0,
        "rec_bal": recess_bal,
        "exp": exp
    }
    token = sign_cookie_payload(payload, ttl_seconds=ttl)
    cookie_domain = settings.COOKIE_DOMAIN or None
    # Основная авторизационная кука с HttpOnly=True
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        domain=cookie_domain,
        max_age=ttl
    )
    # Несекретная UI-кука (HttpOnly=False) для быстрого чтения профиля клиентом
    ui_payload = {
        "id": uid,
        "uid": uid,
        "handle": handle,
        "h": handle,
        "role": role,
        "avatar_seed": seed,
        "seed": seed,
        "recess_seconds": recess_bal,
        "rec_bal": recess_bal,
        "pro": pro,
        "cid": cid,
        "exp": exp
    }
    ui_json = json.dumps(ui_payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    response.set_cookie(
        key="pb_pass_ui",
        value=_b64url_encode(ui_json),
        httponly=False,
        samesite="lax",
        secure=False,
        domain=cookie_domain,
        max_age=ttl
    )

def _clear_auth_cookie(response: Response) -> None:
    cookie_domain = settings.COOKIE_DOMAIN or None
    response.delete_cookie(
        key=settings.COOKIE_NAME,
        domain=cookie_domain,
        httponly=True,
        samesite="lax"
    )
    response.delete_cookie(
        key="pb_pass_ui",
        domain=cookie_domain,
        httponly=False,
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
# Эндпоинты API Паспорта
# -----------------------------------------------------------------------------

@router.get("/ticket")
def get_ticket():
    now = time.time()
    t = issue_ticket(settings.SECRET_KEY.encode("utf-8"), now, k="gen")
    return {"ticket": t}

@router.get("/roll-handle")
def roll_handle():
    now = time.time()
    with db_session() as conn:
        options = []
        for _ in range(20):
            if len(options) >= 5:
                break
            h = generate_callsign()
            seed = secrets.randbits(31)
            row = conn.execute("SELECT 1 FROM users WHERE handle = ?", (h,)).fetchone()
            if not row and not any(o[0] == h for o in options):
                options.append([h, seed])
        t = issue_ticket(settings.SECRET_KEY.encode("utf-8"), now, k="roll", o=options)
        return {"options": [{"handle": h, "avatar_seed": s} for h, s in options], "ticket": t}

@router.get("/me")
def get_me(request: Request):
    user_state = getattr(request.state, "user", None)
    if not user_state:
        return {"user": None}

    user_id = user_state.get("user_id") or user_state.get("uid")
    with db_session() as conn:
        row = conn.execute("""
            SELECT id, handle, role, avatar_seed, recess_seconds, streak_days, trial_used, pro_until,
                   e2ee_public_key, e2ee_key_bundle_json, created_at 
            FROM users WHERE id = ?
        """, (user_id,)).fetchone()
        if not row:
            return {"user": None}

        recess_locked = is_recess_locked_for_student(conn, row["id"]) if row["role"] == "student" else False

        # Активный класс ученика
        class_info = None
        ctx = conn.execute("""
            SELECT c.id, c.title, c.teacher_id, c.quarter_goal, m.seat_number, m.traffic_light
            FROM class_members m
            JOIN classes c ON c.id = m.class_id
            WHERE m.student_id = ?
            ORDER BY m.joined_at DESC LIMIT 1
        """, (row["id"],)).fetchone()
        if ctx:
            class_info = {
                "id": ctx["id"],
                "title": ctx["title"],
                "seat_number": ctx["seat_number"],
                "traffic_light": ctx["traffic_light"],
                "quarter_goal": ctx["quarter_goal"]
            }

        user_info = {
            "id": row["id"],
            "uid": row["id"],
            "handle": row["handle"],
            "h": row["handle"],
            "role": row["role"],
            "avatar_seed": row["avatar_seed"],
            "seed": row["avatar_seed"],
            "recess_seconds": row["recess_seconds"],
            "rec_bal": row["recess_seconds"],
            "streak_days": row["streak_days"] if "streak_days" in row.keys() else 1,
            "trial_used": bool(row["trial_used"]) if "trial_used" in row.keys() else False,
            "pro": row["pro_until"] if "pro_until" in row.keys() else 0,
            "pro_until": row["pro_until"] if "pro_until" in row.keys() else 0,
            "class_id": class_info["id"] if class_info else None,
            "cid": class_info["id"] if class_info else None,
            "class_title": class_info["title"] if class_info else None,
            "seat_number": class_info["seat_number"] if class_info else None,
            "e2ee_public_key": row["e2ee_public_key"] if "e2ee_public_key" in row.keys() else "",
            "e2ee_key_bundle_json": row["e2ee_key_bundle_json"] if "e2ee_key_bundle_json" in row.keys() else "{}",
            "created_at": row["created_at"],
            "recess_locked": recess_locked
        }
        return {"user": user_info}

@router.post("/register")
def register(req: RegisterRequest, response: Response):
    now = int(time.time())
    with db_session() as conn:
        handle = None
        if req.handle:
            candidate = canon_handle(req.handle)
            if not is_valid_dictionary_handle(candidate):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Позывной должен состоять из слов официального словаря Паспорта (Прилагательное-Существительное-Код)."
                )
            if req.ticket:
                payload, err = check_ticket(settings.SECRET_KEY.encode("utf-8"), req.ticket, time.time(), min_age=0)
                if not payload:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Талон недействителен или просрочен"
                    )
            # Проверка уникальности
            existing = conn.execute("SELECT 1 FROM users WHERE handle = ?", (candidate,)).fetchone()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Этот ник уже занят, выберите другой."
                )
            handle = candidate
        else:
            if req.ticket:
                payload, err = check_ticket(settings.SECRET_KEY.encode("utf-8"), req.ticket, time.time(), min_age=0)
                if not payload:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Талон недействителен или просрочен"
                    )
            handle = create_unique_callsign(conn)

        recovery_words = pick_recovery_words(4)
        recovery_text = " ".join(recovery_words)

        password_hash = hash_secret(req.password)
        recovery_words_hash = hash_secret(recovery_text)
        initial_recess = 300 if req.role == "student" else 0
        avatar_seed = secrets.randbits(31)

        cursor = conn.execute("""
            INSERT INTO users (
                handle, role, password_hash, recovery_words_hash,
                avatar_seed, recess_seconds, e2ee_public_key, e2ee_key_bundle_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            handle, req.role, password_hash, recovery_words_hash,
            avatar_seed, initial_recess, req.e2ee_public_key or "",
            req.e2ee_key_bundle_json or "{}", now
        ))
        
        user_id = cursor.lastrowid

        user_data = {
            "user_id": user_id,
            "id": user_id,
            "handle": handle,
            "role": req.role,
            "avatar_seed": avatar_seed,
            "recess_seconds": initial_recess,
            "e2ee_public_key": req.e2ee_public_key or "",
            "e2ee_key_bundle_json": req.e2ee_key_bundle_json or "{}",
            "pro_until": 0,
            "class_id": None
        }
        _set_auth_cookie(response, user_data)

        return {
            "user": {
                "id": user_id,
                "uid": user_id,
                "handle": handle,
                "h": handle,
                "role": req.role,
                "avatar_seed": avatar_seed,
                "seed": avatar_seed,
                "recess_seconds": initial_recess,
                "rec_bal": initial_recess,
                "e2ee_public_key": req.e2ee_public_key or "",
                "e2ee_key_bundle_json": req.e2ee_key_bundle_json or "{}"
            },
            "recovery_words": recovery_words
        }

@router.post("/login")
def login(req: LoginRequest, response: Response):
    handle = canon_handle(req.handle)
    limiter_key = f"auth:{handle}"
    if limiter.blocked(limiter_key, limit=5, window=900):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много неудачных попыток. Подождите 15 минут."
        )

    with db_session() as conn:
        row = conn.execute("""
            SELECT id, handle, role, password_hash, avatar_seed, recess_seconds, 
                   streak_days, trial_used, pro_until, temp_pin_hash, temp_pin_exp,
                   e2ee_public_key, e2ee_key_bundle_json, created_at 
            FROM users WHERE handle = ?
        """, (handle,)).fetchone()

        if not row:
            limiter.hit(limiter_key, 900)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный позывной или пароль"
            )

        ok = False
        now = int(time.time())

        # Вход по одноразовому ПИН от учителя
        if req.temp_pin:
            pin_hash = row["temp_pin_hash"] if "temp_pin_hash" in row.keys() else None
            pin_exp = row["temp_pin_exp"] if "temp_pin_exp" in row.keys() else 0
            if pin_hash and pin_exp > now and verify_secret(req.temp_pin, pin_hash):
                ok = True
                new_pw_hash = hash_secret(req.new_password) if req.new_password else None
                if new_pw_hash:
                    conn.execute("""
                        UPDATE users SET temp_pin_hash = NULL, temp_pin_exp = 0, password_hash = ? WHERE id = ?
                    """, (new_pw_hash, row["id"]))
                else:
                    conn.execute("""
                        UPDATE users SET temp_pin_hash = NULL, temp_pin_exp = 0 WHERE id = ?
                    """, (row["id"],))
        elif req.password:
            ok = verify_secret(req.password, row["password_hash"])

        if not ok:
            limiter.hit(limiter_key, 900)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный позывной или пароль"
            )

        limiter.reset(limiter_key)

        if req.e2ee_public_key or req.e2ee_key_bundle_json:
            up_cols = []
            up_params = []
            if req.e2ee_public_key is not None:
                up_cols.append("e2ee_public_key = ?")
                up_params.append(req.e2ee_public_key)
            if req.e2ee_key_bundle_json is not None:
                up_cols.append("e2ee_key_bundle_json = ?")
                up_params.append(req.e2ee_key_bundle_json)
            if up_cols:
                up_params.append(row["id"])
                conn.execute(f"UPDATE users SET {', '.join(up_cols)} WHERE id = ?", up_params)
                pub_key = req.e2ee_public_key if req.e2ee_public_key is not None else (row["e2ee_public_key"] or "")
                bundle_json = req.e2ee_key_bundle_json if req.e2ee_key_bundle_json is not None else (row["e2ee_key_bundle_json"] or "{}")
        else:
            pub_key = row["e2ee_public_key"] if "e2ee_public_key" in row.keys() else ""
            bundle_json = row["e2ee_key_bundle_json"] if "e2ee_key_bundle_json" in row.keys() else "{}"

        pro = row["pro_until"] if "pro_until" in row.keys() else 0
        user_data = {
            "user_id": row["id"],
            "id": row["id"],
            "handle": row["handle"],
            "role": row["role"],
            "avatar_seed": row["avatar_seed"],
            "recess_seconds": row["recess_seconds"],
            "e2ee_public_key": pub_key,
            "e2ee_key_bundle_json": bundle_json,
            "pro_until": pro
        }
        _set_auth_cookie(response, user_data)

        return {
            "user": {
                "id": row["id"],
                "uid": row["id"],
                "handle": handle,
                "h": handle,
                "role": row["role"],
                "avatar_seed": row["avatar_seed"],
                "seed": row["avatar_seed"],
                "recess_seconds": row["recess_seconds"],
                "rec_bal": row["recess_seconds"],
                "e2ee_public_key": pub_key,
                "e2ee_key_bundle_json": bundle_json,
                "created_at": row["created_at"]
            }
        }

@router.post("/recover")
def recover_password(req: RecoverRequest, response: Response):
    handle = canon_handle(req.handle)
    limiter_key = f"recover:{handle}"
    if limiter.blocked(limiter_key, limit=5, window=900):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много попыток восстановления. Подождите 15 минут."
        )

    words_input = req.recovery_words or req.words
    if not words_input or len(words_input) != 4:
        limiter.hit(limiter_key, 900)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Необходимо указать ровно 4 секретных слова восстановления"
        )

    norm = normalize_words(words_input)
    recovery_text = norm if norm else " ".join([w.strip().lower() for w in words_input])

    with db_session() as conn:
        row = conn.execute(
            "SELECT id, handle, role, avatar_seed, recess_seconds, recovery_words_hash, e2ee_public_key, e2ee_key_bundle_json FROM users WHERE handle = ?",
            (handle,)
        ).fetchone()

        if not row or not verify_secret(recovery_text, row["recovery_words_hash"]):
            limiter.hit(limiter_key, 900)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Неверные секретные слова восстановления"
            )

        limiter.reset(limiter_key)
        new_hash = hash_secret(req.new_password)
        up_cols = ["password_hash = ?"]
        up_params = [new_hash]
        pub_key = row["e2ee_public_key"] if "e2ee_public_key" in row.keys() else ""
        bundle_json = row["e2ee_key_bundle_json"] if "e2ee_key_bundle_json" in row.keys() else "{}"
        if req.e2ee_public_key is not None:
            up_cols.append("e2ee_public_key = ?")
            up_params.append(req.e2ee_public_key)
            pub_key = req.e2ee_public_key
        if req.e2ee_key_bundle_json is not None:
            up_cols.append("e2ee_key_bundle_json = ?")
            up_params.append(req.e2ee_key_bundle_json)
            bundle_json = req.e2ee_key_bundle_json
        up_params.append(row["id"])
        conn.execute(f"UPDATE users SET {', '.join(up_cols)} WHERE id = ?", up_params)

        user_data = {
            "user_id": row["id"],
            "id": row["id"],
            "handle": row["handle"],
            "role": row["role"],
            "avatar_seed": row["avatar_seed"],
            "recess_seconds": row["recess_seconds"],
            "e2ee_public_key": pub_key,
            "e2ee_key_bundle_json": bundle_json
        }
        _set_auth_cookie(response, user_data)

        return {"ok": True, "message": "Пароль успешно обновлён", "user": user_data}

@router.put("/e2ee-bundle")
def update_e2ee_bundle(req: E2EEBundleRequest, request: Request):
    user = require_user(request)
    uid = user.get("user_id") or user.get("uid") or user.get("id")
    with db_session() as conn:
        conn.execute(
            "UPDATE users SET e2ee_public_key = ?, e2ee_key_bundle_json = ? WHERE id = ?",
            (req.e2ee_public_key, req.e2ee_key_bundle_json, uid)
        )
    return {"ok": True, "e2ee_public_key": req.e2ee_public_key, "e2ee_key_bundle_json": req.e2ee_key_bundle_json}

@router.post("/logout")
def logout(response: Response):
    _clear_auth_cookie(response)
    return {"ok": True}

@router.post("/solve")
def solve_task(req: SolveTaskRequest, request: Request):
    user = require_user(request)
    user_id = user.get("user_id") or user.get("uid")
    now = int(time.time())
    grade_five = score_to_grade_five(req.score)

    with db_session() as conn:
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

        cursor = conn.execute("""
            INSERT OR IGNORE INTO solved_tasks (user_id, task_id, class_id, score, solved_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, req.task_id, target_class_id, req.score, now))
        
        is_first_task_solve = (cursor.rowcount == 1)
        awarded_recess = False

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

        if target_class_id:
            try:
                from app.classroom.sse_hub import sse_hub
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
    user_id = user.get("user_id") or user.get("uid")
    with db_session() as conn:
        ok, balance, msg = spend_recess_seconds(conn, user_id, req.seconds)
        if not ok:
            status_code = status.HTTP_403_FORBIDDEN if "заблокированы" in msg else status.HTTP_400_BAD_REQUEST
            raise HTTPException(status_code=status_code, detail=msg)
        return {"ok": True, "remaining_seconds": balance, "message": msg}

@router.post("/recess/unlock")
def unlock_recess(request: Request, response: Response):
    user = require_user(request)
    user_id = user.get("user_id") or user.get("uid")
    with db_session() as conn:
        row = conn.execute("SELECT recess_seconds, handle, role, avatar_seed FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row or row["recess_seconds"] < 900:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Для входа в игровую комнату нужно накопить 900 секунд перемены (3 решённые задачи)."
            )
        new_balance = row["recess_seconds"] - 900
        conn.execute("UPDATE users SET recess_seconds = ? WHERE id = ?", (new_balance, user_id))
        user_data = dict(row)
        user_data["recess_seconds"] = new_balance
        _set_auth_cookie(response, user_data)
        return {"ok": True, "unlocked": True, "recess_seconds": new_balance}

@router.post("/check-code")
def check_code_endpoint(req: CodeRequest):
    code = normalize_code(req.code)
    if not code:
        return {"ok": False, "status": "format", "message": "Неверный формат ключа"}
    with db_session() as conn:
        chash = code_hash(code)
        key_row = conn.execute("SELECT * FROM license_keys WHERE code_hash = ?", (chash,)).fetchone()
        if not key_row:
            return {"ok": False, "status": "not_found", "message": "Ключ не найден"}
        if key_row["activated_at"]:
            return {"ok": False, "status": "used", "message": "Этот ключ уже активирован"}
        return {"ok": True, "status": "valid", "duration_days": key_row["duration_days"]}

@router.post("/activate-code")
def activate_code_endpoint(req: CodeRequest, request: Request, response: Response):
    user = require_teacher(request)
    user_id = user.get("user_id") or user.get("uid")
    code = normalize_code(req.code)
    if not code:
        raise HTTPException(status_code=400, detail="Неверный формат ключа активации")
    with db_session() as conn:
        chash = code_hash(code)
        key_row = conn.execute("SELECT * FROM license_keys WHERE code_hash = ?", (chash,)).fetchone()
        if not key_row:
            raise HTTPException(status_code=404, detail="Ключ активации не найден")
        if key_row["activated_at"]:
            raise HTTPException(status_code=409, detail="Этот ключ уже был активирован ранее")

        now = int(time.time())
        u = conn.execute("SELECT pro_until FROM users WHERE id = ?", (user_id,)).fetchone()
        curr_pro = max(u["pro_until"] if u and "pro_until" in u.keys() else 0, now)
        new_pro = curr_pro + key_row["duration_days"] * 86400

        conn.execute("UPDATE license_keys SET activated_by = ?, activated_at = ? WHERE code_hash = ?", (user_id, now, chash))
        conn.execute("UPDATE users SET pro_until = ? WHERE id = ?", (new_pro, user_id))

        user_info = dict(user)
        user_info["pro_until"] = new_pro
        _set_auth_cookie(response, user_info)
        return {"ok": True, "pro_until": new_pro, "message": "PRO-подписка успешно продлена"}
