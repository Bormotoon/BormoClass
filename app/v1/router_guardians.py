import time
import secrets
import hashlib
from typing import Optional, List
from fastapi import APIRouter, Request, Query
from pydantic import BaseModel

from app.db import db_session
from app.v1.protocol import (
    api_error,
    parse_update_mask,
    encode_page_token,
    decode_page_token,
    resolve_user_id,
    ts_to_rfc3339
)
from app.v1.rbac import (
    resolve_auth_context,
    require_scopes,
    SCOPE_GUARDIANLINKS_STUDENTS,
    SCOPE_GUARDIANLINKS_STUDENTS_READONLY,
    SCOPE_GUARDIANLINKS_ME_READONLY,
    SCOPE_PROFILE_EMAILS,
    SCOPE_PROFILE_PHOTOS
)
from app.v1.schemas import (
    Guardian,
    GuardianInvitation,
    UserProfile,
    Name,
    ListGuardiansResponse,
    ListGuardianInvitationsResponse,
    Empty
)

router = APIRouter(tags=["guardians"])

class AcceptCodeRequest(BaseModel):
    code: str
    digest_frequency: Optional[str] = "WEEKLY"

def _build_guardian_profile(u: dict, ctx) -> UserProfile:
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
        verifiedTeacher=bool(u.get("verified_teacher", 0))
    )

def build_guardian_digest(conn, guardian_user_id: int, period_days: int = 7) -> dict:
    now = int(time.time())
    period_start = now - (period_days * 86400)
    period_end = now + (period_days * 86400)

    wards = conn.execute(
        """SELECT g.student_id, u.handle FROM guardians g
           JOIN users u ON g.student_id = u.id
           WHERE g.guardian_user_id = ?""",
        (guardian_user_id,)
    ).fetchall()

    ward_summaries = []
    for w in wards:
        student_id = w["student_id"]
        handle = w["handle"]

        courses = conn.execute(
            """SELECT c.id, c.title FROM classes c
               JOIN class_members cm ON c.id = cm.class_id
               WHERE cm.student_id = ? AND cm.enrollment_active = 1 AND c.guardians_enabled = 1 AND c.course_state = 'ACTIVE'""",
            (student_id,)
        ).fetchall()

        missing_work = []
        upcoming_work = []
        class_activity = []

        for c in courses:
            cid = c["id"]
            ctitle = c["title"]

            cw_rows = conn.execute(
                """SELECT cw.id, cw.title, cw.due_at, cw.max_points, s.v1_state, s.assigned_grade, s.updated_at
                   FROM coursework cw
                   LEFT JOIN submissions s ON cw.id = s.coursework_id AND s.student_id = ?
                   WHERE cw.class_id = ? AND cw.state IN ('published', 'PUBLISHED')""",
                (student_id, cid)
            ).fetchall()

            for cw in cw_rows:
                due = cw["due_at"]
                v1_state = cw["v1_state"] or "NEW"
                is_done = v1_state in ("TURNED_IN", "RETURNED")

                if due and due < now and not is_done:
                    missing_work.append({
                        "courseTitle": ctitle,
                        "title": cw["title"],
                        "dueAt": ts_to_rfc3339(due)
                    })

                if due and now <= due <= period_end:
                    upcoming_work.append({
                        "courseTitle": ctitle,
                        "title": cw["title"],
                        "dueAt": ts_to_rfc3339(due)
                    })

                if v1_state == "RETURNED" and cw["updated_at"] and cw["updated_at"] >= period_start:
                    class_activity.append({
                        "type": "GRADE_RETURNED",
                        "courseTitle": ctitle,
                        "title": cw["title"],
                        "assignedGrade": cw["assigned_grade"],
                        "maxPoints": cw["max_points"],
                        "date": ts_to_rfc3339(cw["updated_at"])
                    })

            # Недавние объявления курса
            ann_rows = conn.execute(
                """SELECT body_text, created_at FROM announcements
                   WHERE class_id = ? AND state = 'PUBLISHED' AND created_at >= ?
                   ORDER BY created_at DESC""",
                (cid, period_start)
            ).fetchall()
            for ann in ann_rows:
                class_activity.append({
                    "type": "ANNOUNCEMENT",
                    "courseTitle": ctitle,
                    "text": ann["body_text"][:200],
                    "date": ts_to_rfc3339(ann["created_at"])
                })

        ward_summaries.append({
            "studentId": str(student_id),
            "studentHandle": handle,
            "missingWork": missing_work,
            "upcomingWork": upcoming_work,
            "classActivity": class_activity
        })

    return {
        "generatedAt": ts_to_rfc3339(now),
        "guardianUserId": str(guardian_user_id),
        "wardSummaries": ward_summaries
    }

# ============================================================================
# userProfiles.guardianInvitations
# ============================================================================

@router.post("/v1/userProfiles/{studentId}/guardianInvitations")
def create_guardian_invitation(studentId: str, req: GuardianInvitation, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_GUARDIANLINKS_STUDENTS,))

        target_student_id = resolve_user_id(conn, studentId, ctx.user)
        is_admin = (ctx.user.get("role") == "admin")

        if not is_admin:
            # Учитель должен преподавать хотя бы в одном курсе этого ученика
            is_teacher = conn.execute(
                """SELECT 1 FROM class_members cm
                   JOIN classes c ON cm.class_id = c.id
                   WHERE cm.student_id = ? AND (c.teacher_id = ? OR EXISTS (
                       SELECT 1 FROM course_teachers ct WHERE ct.class_id = c.id AND ct.teacher_id = ?
                   )) AND cm.enrollment_active = 1 LIMIT 1""",
                (target_student_id, ctx.user["id"], ctx.user["id"])
            ).fetchone()
            if not is_teacher:
                api_error(403, "PERMISSION_DENIED", "Приглашать опекунов могут только учителя ученика или администраторы")

        invite_target = (req.invitedEmailAddress or "").strip()
        if not invite_target:
            api_error(400, "INVALID_ARGUMENT", "Необходимо указать email или контакт опекуна (invitedEmailAddress)")

        # Генерируем 8-значный код подтверждения
        code = secrets.token_hex(4).upper()
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        now = int(time.time())

        cursor = conn.execute(
            """INSERT INTO guardian_invitations (student_id, invite_target, invite_code_hash, state, inviter_user_id, created_at)
               VALUES (?, ?, ?, 'PENDING', ?, ?)""",
            (target_student_id, invite_target, code_hash, ctx.user["id"], now)
        )
        new_id = cursor.lastrowid

        resp = GuardianInvitation(
            invitationId=str(new_id),
            studentId=str(target_student_id),
            invitedEmailAddress=invite_target,
            state="PENDING",
            creationTime=ts_to_rfc3339(now)
        )
        res_dict = resp.model_dump(by_alias=True, exclude_none=True)
        res_dict["invitationCode"] = code  # Локальный код для передачи родителю
        return res_dict

@router.get("/v1/userProfiles/{studentId}/guardianInvitations/{invitationId}")
def get_guardian_invitation(studentId: str, invitationId: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (
            SCOPE_GUARDIANLINKS_STUDENTS,
            SCOPE_GUARDIANLINKS_STUDENTS_READONLY,
            SCOPE_GUARDIANLINKS_ME_READONLY
        ))

        row = conn.execute("SELECT * FROM guardian_invitations WHERE id = ?", (invitationId,)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Приглашение опекуна не найдено")

        if studentId != "-":
            target_sid = resolve_user_id(conn, studentId, ctx.user)
            if row["student_id"] != target_sid:
                api_error(404, "NOT_FOUND", "Приглашение опекуна не найдено для данного ученика")

        return GuardianInvitation(
            invitationId=str(row["id"]),
            studentId=str(row["student_id"]),
            invitedEmailAddress=row["invite_target"],
            state=row["state"],
            creationTime=ts_to_rfc3339(row["created_at"])
        )

@router.get("/v1/userProfiles/{studentId}/guardianInvitations")
def list_guardian_invitations(
    studentId: str,
    request: Request,
    invitedEmailAddress: Optional[str] = Query(None),
    states: Optional[List[str]] = Query(None),
    pageSize: int = Query(100, ge=1, le=100),
    pageToken: Optional[str] = Query(None)
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (
            SCOPE_GUARDIANLINKS_STUDENTS,
            SCOPE_GUARDIANLINKS_STUDENTS_READONLY,
            SCOPE_GUARDIANLINKS_ME_READONLY
        ))

        conditions = []
        params = []

        if studentId != "-":
            target_sid = resolve_user_id(conn, studentId, ctx.user)
            conditions.append("student_id = ?")
            params.append(target_sid)

        if invitedEmailAddress:
            conditions.append("invite_target = ?")
            params.append(invitedEmailAddress.strip())

        if states:
            effective_states = [s for s in states if s]
            if effective_states:
                placeholders = ", ".join("?" for _ in effective_states)
                conditions.append(f"state IN ({placeholders})")
                params.extend(effective_states)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        fingerprint = f"gi:{studentId}:{invitedEmailAddress or ''}:{','.join(sorted(states or []))}"
        offset = decode_page_token(pageToken, fingerprint)

        rows = conn.execute(
            f"SELECT * FROM guardian_invitations {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [pageSize + 1, offset]
        ).fetchall()

        has_next = len(rows) > pageSize
        items = rows[:pageSize]

        inv_list = [
            GuardianInvitation(
                invitationId=str(r["id"]),
                studentId=str(r["student_id"]),
                invitedEmailAddress=r["invite_target"],
                state=r["state"],
                creationTime=ts_to_rfc3339(r["created_at"])
            )
            for r in items
        ]

        next_token = encode_page_token(offset + pageSize, fingerprint) if has_next else None
        return ListGuardianInvitationsResponse(
            guardianInvitations=inv_list if inv_list else None,
            nextPageToken=next_token
        )

@router.patch("/v1/userProfiles/{studentId}/guardianInvitations/{invitationId}")
def patch_guardian_invitation(
    studentId: str,
    invitationId: str,
    req: GuardianInvitation,
    request: Request,
    updateMask: Optional[str] = Query(None)
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_GUARDIANLINKS_STUDENTS,))

        mask = parse_update_mask(updateMask, {"state"})
        row = conn.execute("SELECT * FROM guardian_invitations WHERE id = ?", (invitationId,)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Приглашение опекуна не найдено")

        if studentId != "-":
            target_sid = resolve_user_id(conn, studentId, ctx.user)
            if row["student_id"] != target_sid:
                api_error(404, "NOT_FOUND", "Приглашение не соответствует ученику")

        if "state" in mask:
            new_state = req.state or row["state"]
            if new_state not in ("PENDING", "COMPLETE", "CANCELLED"):
                api_error(400, "INVALID_ARGUMENT", f"Недопустимое состояние: {new_state}")
            conn.execute("UPDATE guardian_invitations SET state = ? WHERE id = ?", (new_state, invitationId))

        updated_row = conn.execute("SELECT * FROM guardian_invitations WHERE id = ?", (invitationId,)).fetchone()
        return GuardianInvitation(
            invitationId=str(updated_row["id"]),
            studentId=str(updated_row["student_id"]),
            invitedEmailAddress=updated_row["invite_target"],
            state=updated_row["state"],
            creationTime=ts_to_rfc3339(updated_row["created_at"])
        )

# ============================================================================
# userProfiles.guardians
# ============================================================================

@router.get("/v1/userProfiles/{studentId}/guardians/{guardianId}")
def get_guardian(studentId: str, guardianId: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (
            SCOPE_GUARDIANLINKS_STUDENTS,
            SCOPE_GUARDIANLINKS_STUDENTS_READONLY,
            SCOPE_GUARDIANLINKS_ME_READONLY
        ))

        row = conn.execute(
            """SELECT g.*, u.* FROM guardians g
               JOIN users u ON g.guardian_user_id = u.id
               WHERE g.id = ?""",
            (guardianId,)
        ).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Опекун не найден")

        if studentId != "-":
            target_sid = resolve_user_id(conn, studentId, ctx.user)
            if row["student_id"] != target_sid:
                api_error(404, "NOT_FOUND", "Опекун не привязан к данному ученику")

        profile = _build_guardian_profile(dict(row), ctx)
        return Guardian(
            guardianId=str(row["id"]),
            studentId=str(row["student_id"]),
            invitedEmailAddress=row["invite_target"],
            guardianProfile=profile
        )

@router.get("/v1/userProfiles/{studentId}/guardians")
def list_guardians(
    studentId: str,
    request: Request,
    invitedEmailAddress: Optional[str] = Query(None),
    pageSize: int = Query(100, ge=1, le=100),
    pageToken: Optional[str] = Query(None)
):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (
            SCOPE_GUARDIANLINKS_STUDENTS,
            SCOPE_GUARDIANLINKS_STUDENTS_READONLY,
            SCOPE_GUARDIANLINKS_ME_READONLY
        ))

        conditions = []
        params = []

        if studentId != "-":
            target_sid = resolve_user_id(conn, studentId, ctx.user)
            conditions.append("g.student_id = ?")
            params.append(target_sid)
        else:
            # Если '-' и не админ/учитель, опекун видит только свои записи
            is_admin = (ctx.user.get("role") == "admin")
            is_teacher = (ctx.user.get("role") == "teacher")
            if not is_admin and not is_teacher:
                conditions.append("g.guardian_user_id = ?")
                params.append(ctx.user["id"])

        if invitedEmailAddress:
            conditions.append("g.invite_target = ?")
            params.append(invitedEmailAddress.strip())

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        fingerprint = f"g:{studentId}:{invitedEmailAddress or ''}"
        offset = decode_page_token(pageToken, fingerprint)

        rows = conn.execute(
            f"""SELECT g.id as gid, g.student_id, g.invite_target, u.* FROM guardians g
                JOIN users u ON g.guardian_user_id = u.id
                {where_clause}
                ORDER BY g.created_at DESC
                LIMIT ? OFFSET ?""",
            params + [pageSize + 1, offset]
        ).fetchall()

        has_next = len(rows) > pageSize
        items = rows[:pageSize]

        g_list = [
            Guardian(
                guardianId=str(r["gid"]),
                studentId=str(r["student_id"]),
                invitedEmailAddress=r["invite_target"],
                guardianProfile=_build_guardian_profile(dict(r), ctx)
            )
            for r in items
        ]

        next_token = encode_page_token(offset + pageSize, fingerprint) if has_next else None
        return ListGuardiansResponse(
            guardians=g_list if g_list else None,
            nextPageToken=next_token
        )

@router.delete("/v1/userProfiles/{studentId}/guardians/{guardianId}")
def delete_guardian(studentId: str, guardianId: str, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        require_scopes(ctx, (SCOPE_GUARDIANLINKS_STUDENTS,))

        row = conn.execute("SELECT * FROM guardians WHERE id = ?", (guardianId,)).fetchone()
        if not row:
            api_error(404, "NOT_FOUND", "Опекун не найден")

        is_self = (row["guardian_user_id"] == ctx.user["id"])
        is_admin = (ctx.user.get("role") == "admin")

        if not is_self and not is_admin:
            # Учитель курса может отвязать опекуна своего ученика
            is_teacher = conn.execute(
                """SELECT 1 FROM class_members cm
                   JOIN classes c ON cm.class_id = c.id
                   WHERE cm.student_id = ? AND (c.teacher_id = ? OR EXISTS (
                       SELECT 1 FROM course_teachers ct WHERE ct.class_id = c.id AND ct.teacher_id = ?
                   )) LIMIT 1""",
                (row["student_id"], ctx.user["id"], ctx.user["id"])
            ).fetchone()
            if not is_teacher:
                api_error(403, "PERMISSION_DENIED", "Недостаточно прав для отвязки опекуна")

        conn.execute("DELETE FROM guardians WHERE id = ?", (guardianId,))
        return Empty()

# ============================================================================
# UI-эндпоинты и сводки успеваемости (my-digest, accept-code)
# ============================================================================

@router.post("/api/classroom/guardians/accept-code")
def accept_guardian_code(req: AcceptCodeRequest, request: Request):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        raw_code = req.code.strip()
        code_hash = hashlib.sha256(raw_code.encode()).hexdigest()

        inv = conn.execute(
            "SELECT * FROM guardian_invitations WHERE invite_code_hash = ? AND state = 'PENDING'",
            (code_hash,)
        ).fetchone()
        if not inv:
            api_error(404, "NOT_FOUND", "Код приглашения опекуна не найден или уже использован")

        now = int(time.time())
        conn.execute("UPDATE guardian_invitations SET state = 'COMPLETE' WHERE id = ?", (inv["id"],))

        conn.execute(
            """INSERT INTO guardians (student_id, guardian_user_id, invite_target, digest_frequency, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(student_id, guardian_user_id) DO UPDATE SET digest_frequency = excluded.digest_frequency""",
            (inv["student_id"], ctx.user["id"], inv["invite_target"], req.digest_frequency or "WEEKLY", now)
        )

        return {"ok": True, "student_id": inv["student_id"]}

@router.get("/api/classroom/guardians/my-digest")
def get_my_guardian_digest(request: Request, period_days: int = Query(7, ge=1, le=30)):
    with db_session() as conn:
        ctx = resolve_auth_context(request, conn)
        return build_guardian_digest(conn, ctx.user["id"], period_days=period_days)
