import ast
import json
import random
import re
import time
from typing import Optional, List, Dict, Any, Union
from fastapi import APIRouter, Request, HTTPException, status
from pydantic import BaseModel, Field

from app.db import db_session
from app.passport.middleware import require_user, require_teacher
from app.passport.pii_guard import assert_zero_pii_text

router = APIRouter(tags=["quizzes_and_sets"])

# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------

class QuizCreateRequest(BaseModel):
    class_id: int
    coursework_id: Optional[int] = None
    quiz_title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="")
    questions_json: str = Field(default="[]")
    shuffle_questions: int = Field(default=0, ge=0, le=1)
    time_limit_sec: int = Field(default=0, ge=0)
    lock_tab_focus: int = Field(default=0, ge=0, le=1)
    auto_import_grades: int = Field(default=1, ge=0, le=1)
    show_correct_answers: int = Field(default=1, ge=0, le=1)

class QuizUpdateRequest(BaseModel):
    quiz_title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    questions_json: Optional[str] = None
    shuffle_questions: Optional[int] = Field(default=None, ge=0, le=1)
    time_limit_sec: Optional[int] = Field(default=None, ge=0)
    lock_tab_focus: Optional[int] = Field(default=None, ge=0, le=1)
    auto_import_grades: Optional[int] = Field(default=None, ge=0, le=1)
    show_correct_answers: Optional[int] = Field(default=None, ge=0, le=1)

class QuizSubmitRequest(BaseModel):
    answers_json: Dict[str, Any] = Field(default_factory=dict)
    focus_lost_count: int = Field(default=0, ge=0)

class PracticeSetCreateRequest(BaseModel):
    class_id: int
    coursework_id: Optional[int] = None
    set_title: str = Field(min_length=1, max_length=200)
    cards_json: str = Field(default="[]")

class PracticeSetUpdateRequest(BaseModel):
    set_title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    cards_json: Optional[str] = None

class PracticeCardCheckRequest(BaseModel):
    card_id: str
    answer: Any
    used_hint: bool = False
    scratchpad_json: Optional[str] = None

class OriginalityCheckRequest(BaseModel):
    student_id: Optional[int] = None
    content_text: Optional[str] = None

class LearningGoalsRequest(BaseModel):
    standard_ids: List[str]

# -----------------------------------------------------------------------------
# 1. Quizzes: Engine and Scoring
# -----------------------------------------------------------------------------

def _score_single_question(q: dict, ans: Any) -> float:
    q_type = q.get("type", "SINGLE_CHOICE")
    max_pts = float(q.get("points", 1.0))
    if ans is None:
        return 0.0

    if q_type == "SINGLE_CHOICE":
        correct = str(q.get("correct", "")).strip()
        return max_pts if str(ans).strip() == correct else 0.0

    elif q_type == "MULTIPLE_CHOICE":
        correct_list = [str(c).strip() for c in q.get("correct", [])]
        if not isinstance(ans, list):
            return 0.0
        given_list = [str(a).strip() for a in ans]
        return max_pts if sorted(correct_list) == sorted(given_list) else 0.0

    elif q_type == "SHORT_TEXT":
        correct = str(q.get("correct", "")).strip().lower()
        return max_pts if str(ans).strip().lower() == correct else 0.0

    elif q_type == "NUMERIC_TOLERANCE":
        target = float(q.get("target", 0.0))
        tolerance = float(q.get("tolerance", 0.001))
        try:
            val = float(ans)
            return max_pts if abs(val - target) <= tolerance else 0.0
        except (ValueError, TypeError):
            return 0.0

    elif q_type == "MATCHING":
        pairs = q.get("pairs", {})  # dict: {left: right}
        if not isinstance(ans, dict) or not pairs:
            return 0.0
        correct_count = 0
        for k, v in pairs.items():
            if str(ans.get(k, "")).strip() == str(v).strip():
                correct_count += 1
        return round((correct_count / len(pairs)) * max_pts, 2)

    elif q_type == "ORDERING":
        correct_order = [str(x).strip() for x in q.get("correct_order", [])]
        if not isinstance(ans, list):
            return 0.0
        given_order = [str(x).strip() for x in ans]
        return max_pts if correct_order == given_order else 0.0

    return 0.0

@router.post("/quizzes")
def create_quiz(req: QuizCreateRequest, request: Request):
    user = require_teacher(request)
    now = int(time.time())

    try:
        qs = json.loads(req.questions_json)
        if isinstance(qs, list):
            for q in qs:
                if isinstance(q, dict) and q.get("type") == "PARAGRAPH":
                    raise HTTPException(
                        status_code=422,
                        detail="Тип вопроса PARAGRAPH (эссе в свободной форме) запрещен стандартом Zero-PII (152-ФЗ РФ)."
                    )
    except json.JSONDecodeError:
        pass

    with db_session() as conn:
        cursor = conn.execute("""
            INSERT INTO quizzes (
                class_id, coursework_id, quiz_title, description,
                questions_json, shuffle_questions, time_limit_sec,
                lock_tab_focus, auto_import_grades, show_correct_answers,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            req.class_id, req.coursework_id, req.quiz_title.strip(), req.description,
            req.questions_json, req.shuffle_questions, req.time_limit_sec,
            req.lock_tab_focus, req.auto_import_grades, req.show_correct_answers,
            now
        ))
        row = conn.execute("SELECT * FROM quizzes WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)

@router.get("/quizzes/{quiz_id}")
def get_quiz(quiz_id: int, request: Request):
    user = require_user(request)
    is_teacher = user["role"] in ("teacher", "admin")

    with db_session() as conn:
        row = conn.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Квиз не найден")

        q_dict = dict(row)
        questions = []
        try:
            questions = json.loads(q_dict["questions_json"])
        except Exception:
            pass

        attempt = conn.execute(
            "SELECT * FROM quiz_attempts WHERE quiz_id = ? AND student_id = ?",
            (quiz_id, user["user_id"])
        ).fetchone()

        if not is_teacher:
            # Если ученик ещё не завершил квиз, скрываем правильные ответы
            is_submitted = bool(attempt and attempt["submitted_at"])
            can_see_answers = bool(is_submitted and q_dict["show_correct_answers"] == 1)

            if not can_see_answers:
                clean_questions = []
                for q in questions:
                    q_copy = dict(q)
                    q_copy.pop("correct", None)
                    q_copy.pop("correct_order", None)
                    q_copy.pop("pairs", None)
                    q_copy.pop("target", None)
                    q_copy.pop("tolerance", None)
                    clean_questions.append(q_copy)
                questions = clean_questions

            if q_dict["shuffle_questions"] == 1 and not is_submitted:
                rnd = random.Random(f"{user['user_id']}_{quiz_id}")
                rnd.shuffle(questions)

        q_dict["questions"] = questions
        q_dict["my_attempt"] = dict(attempt) if attempt else None
        return q_dict

@router.patch("/quizzes/{quiz_id}")
def update_quiz(quiz_id: int, req: QuizUpdateRequest, request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        q_row = conn.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
        if not q_row:
            raise HTTPException(status_code=404, detail="Квиз не найден")

        updates = []
        params = []
        for field in ("quiz_title", "description", "questions_json", "shuffle_questions",
                      "time_limit_sec", "lock_tab_focus", "auto_import_grades", "show_correct_answers"):
            val = getattr(req, field)
            if val is not None:
                updates.append(f"{field} = ?")
                params.append(val)

        if updates:
            params.append(quiz_id)
            conn.execute(f"UPDATE quizzes SET {', '.join(updates)} WHERE id = ?", params)

        updated = conn.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
        return dict(updated)

@router.post("/quizzes/{quiz_id}/submit")
def submit_quiz(quiz_id: int, req: QuizSubmitRequest, request: Request):
    user = require_user(request)
    student_id = user["user_id"]
    now = int(time.time())

    with db_session() as conn:
        q_row = conn.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
        if not q_row:
            raise HTTPException(status_code=404, detail="Квиз не найден")

        questions = []
        try:
            questions = json.loads(q_row["questions_json"])
        except Exception:
            pass

        total_score = 0.0
        max_possible = 0.0
        for idx, q in enumerate(questions):
            q_id = str(q.get("id", idx))
            pts = float(q.get("points", 1.0))
            max_possible += pts
            ans = req.answers_json.get(q_id)
            q_type = q.get("type")
            if q_type == "SHORT_TEXT" and ans is not None:
                ans_str = str(ans).strip()
                if len(ans_str) > 64:
                    raise HTTPException(
                        status_code=422,
                        detail="Ответ типа SHORT_TEXT не может превышать 64 символа (Zero-PII)."
                    )
                assert_zero_pii_text(ans_str)
            earned = _score_single_question(q, ans)
            total_score += earned

        auto_score = round(total_score, 2)
        max_possible = round(max_possible, 2)
        answers_str = json.dumps(req.answers_json, ensure_ascii=False)

        conn.execute("""
            INSERT INTO quiz_attempts (
                quiz_id, student_id, answers_json, auto_score,
                max_score, focus_lost_count, started_at, submitted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(quiz_id, student_id) DO UPDATE SET
                answers_json = excluded.answers_json,
                auto_score = excluded.auto_score,
                max_score = excluded.max_score,
                focus_lost_count = excluded.focus_lost_count,
                submitted_at = excluded.submitted_at
        """, (quiz_id, student_id, answers_str, auto_score, max_possible, req.focus_lost_count, now, now))

        # Если включен автоимпорт оценки и квиз привязан к заданию
        cw_id = q_row["coursework_id"]
        if q_row["auto_import_grades"] == 1 and cw_id:
            # Находим max_points задания
            cw = conn.execute("SELECT max_points FROM coursework WHERE id = ?", (cw_id,)).fetchone()
            cw_max = float(cw["max_points"]) if cw and cw["max_points"] else max_possible
            scaled_grade = round((auto_score / max_possible) * cw_max, 2) if max_possible > 0 else auto_score

            conn.execute("""
                INSERT INTO submissions (
                    coursework_id, student_id, status, v1_state,
                    draft_grade, payload_json, updated_at
                ) VALUES (?, ?, 'turned_in', 'TURNED_IN', ?, ?, ?)
                ON CONFLICT(coursework_id, student_id) DO UPDATE SET
                    status = 'turned_in',
                    v1_state = 'TURNED_IN',
                    draft_grade = excluded.draft_grade,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
            """, (cw_id, student_id, scaled_grade, answers_str, now))

            conn.execute("""
                INSERT INTO submission_history (
                    coursework_id, student_id, entry_kind, state_val,
                    actor_user_id, occurred_at
                ) VALUES (?, ?, 'STATE_CHANGE', 'TURNED_IN', ?, ?)
            """, (cw_id, student_id, student_id, now))

        return {
            "ok": True,
            "auto_score": auto_score,
            "max_score": max_possible,
            "focus_lost_count": req.focus_lost_count
        }

# -----------------------------------------------------------------------------
# 2. Practice Sets
# -----------------------------------------------------------------------------

@router.post("/practice-sets")
def create_practice_set(req: PracticeSetCreateRequest, request: Request):
    user = require_teacher(request)
    now = int(time.time())
    with db_session() as conn:
        cursor = conn.execute("""
            INSERT INTO practice_sets (class_id, coursework_id, set_title, cards_json, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (req.class_id, req.coursework_id, req.set_title.strip(), req.cards_json, now))
        row = conn.execute("SELECT * FROM practice_sets WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)

@router.get("/practice-sets/{id}")
def get_practice_set(id: int, request: Request):
    user = require_user(request)
    is_teacher = user["role"] in ("teacher", "admin")

    with db_session() as conn:
        row = conn.execute("SELECT * FROM practice_sets WHERE id = ?", (id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Практикум не найден")

        ps_dict = dict(row)
        attempt = conn.execute(
            "SELECT * FROM practice_attempts WHERE practice_set_id = ? AND student_id = ?",
            (id, user["user_id"])
        ).fetchone()

        cards = []
        try:
            cards = json.loads(ps_dict["cards_json"])
        except Exception:
            pass

        if not is_teacher:
            # Скрываем правильные ответы при прохождении
            sanitized = []
            for c in cards:
                c_copy = dict(c)
                c_copy.pop("answer", None)
                sanitized.append(c_copy)
            cards = sanitized

        ps_dict["cards"] = cards
        ps_dict["my_attempt"] = dict(attempt) if attempt else None
        return ps_dict

@router.patch("/practice-sets/{id}")
def update_practice_set(id: int, req: PracticeSetUpdateRequest, request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        row = conn.execute("SELECT * FROM practice_sets WHERE id = ?", (id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Практикум не найден")

        updates = []
        params = []
        if req.set_title is not None:
            updates.append("set_title = ?")
            params.append(req.set_title.strip())
        if req.cards_json is not None:
            updates.append("cards_json = ?")
            params.append(req.cards_json)

        if updates:
            params.append(id)
            conn.execute(f"UPDATE practice_sets SET {', '.join(updates)} WHERE id = ?", params)

        updated = conn.execute("SELECT * FROM practice_sets WHERE id = ?", (id,)).fetchone()
        return dict(updated)

@router.post("/practice-sets/{id}/check-card")
def check_practice_card(id: int, req: PracticeCardCheckRequest, request: Request):
    user = require_user(request)
    student_id = user["user_id"]
    now = int(time.time())

    with db_session() as conn:
        row = conn.execute("SELECT * FROM practice_sets WHERE id = ?", (id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Практикум не найден")

        cards = []
        try:
            cards = json.loads(row["cards_json"])
        except Exception:
            pass

        target_card = None
        for c in cards:
            if str(c.get("id")) == str(req.card_id):
                target_card = c
                break

        if not target_card:
            raise HTTPException(status_code=404, detail="Карточка не найдена")

        expected = target_card.get("answer")
        is_correct = False
        if isinstance(expected, (int, float)):
            try:
                is_correct = abs(float(req.answer) - float(expected)) <= 0.001
            except Exception:
                is_correct = False
        else:
            is_correct = (str(req.answer).strip().lower() == str(expected).strip().lower())

        attempt = conn.execute(
            "SELECT * FROM practice_attempts WHERE practice_set_id = ? AND student_id = ?",
            (id, student_id)
        ).fetchone()

        progress = {}
        hints_used = 0
        scratchpads = {}
        completed = 0
        if attempt:
            try:
                progress = json.loads(attempt["progress_json"])
                hints_used = attempt["hints_used"]
                scratchpads = json.loads(attempt["scratchpad_json"])
                completed = attempt["completed_count"]
            except Exception:
                pass

        card_stat = progress.get(req.card_id, {"attempts": 0, "correct": False, "hints": 0})
        card_stat["attempts"] += 1
        if req.used_hint:
            card_stat["hints"] += 1
            hints_used += 1
        if is_correct and not card_stat.get("correct"):
            card_stat["correct"] = True
            completed += 1
        progress[req.card_id] = card_stat

        if req.scratchpad_json:
            scratchpads[req.card_id] = req.scratchpad_json

        conn.execute("""
            INSERT INTO practice_attempts (
                practice_set_id, student_id, progress_json, hints_used,
                scratchpad_json, completed_count, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(practice_set_id, student_id) DO UPDATE SET
                progress_json = excluded.progress_json,
                hints_used = excluded.hints_used,
                scratchpad_json = excluded.scratchpad_json,
                completed_count = excluded.completed_count,
                updated_at = excluded.updated_at
        """, (
            id, student_id, json.dumps(progress), hints_used,
            json.dumps(scratchpads), completed, now
        ))

        explanation = target_card.get("explanation", "") if is_correct else ""
        return {"correct": is_correct, "explanation": explanation}

@router.get("/practice-sets/{id}/insights")
def get_practice_set_insights(id: int, request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        row = conn.execute("SELECT * FROM practice_sets WHERE id = ?", (id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Практикум не найден")

        cards = []
        try:
            cards = json.loads(row["cards_json"])
        except Exception:
            pass

        attempts = conn.execute(
            "SELECT * FROM practice_attempts WHERE practice_set_id = ?",
            (id,)
        ).fetchall()

        stats_by_card = {str(c.get("id")): {"attempts_total": 0, "wrong_total": 0, "hints_total": 0, "students_struggling": 0} for c in cards}

        for att in attempts:
            prog = {}
            try:
                prog = json.loads(att["progress_json"])
            except Exception:
                pass
            for cid, stat in prog.items():
                if cid in stats_by_card:
                    stats_by_card[cid]["attempts_total"] += stat.get("attempts", 0)
                    stats_by_card[cid]["hints_total"] += stat.get("hints", 0)
                    wrong = stat.get("attempts", 0) - (1 if stat.get("correct") else 0)
                    stats_by_card[cid]["wrong_total"] += max(0, wrong)
                    if wrong >= 2 or stat.get("hints", 0) > 0:
                        stats_by_card[cid]["students_struggling"] += 1

        problem_cards = []
        for c in cards:
            cid = str(c.get("id"))
            card_info = dict(c)
            card_info.update(stats_by_card.get(cid, {}))
            problem_cards.append(card_info)

        return {
            "set_title": row["set_title"],
            "total_students": len(attempts),
            "cards": problem_cards
        }

# -----------------------------------------------------------------------------
# 3. Originality Reports (Winnowing 5-gram + AST comparison)
# -----------------------------------------------------------------------------

def _winnowing_hash(s: str) -> int:
    h = 0
    for ch in s:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h

def _get_winnowing_fingerprints(text: str, k: int = 5, w: int = 4) -> set:
    tokens = re.findall(r"\w+", text.lower())
    if len(tokens) < k:
        return set()

    k_grams = [" ".join(tokens[i:i+k]) for i in range(len(tokens) - k + 1)]
    hashes = [_winnowing_hash(kg) for kg in k_grams]

    fingerprints = set()
    for i in range(len(hashes) - w + 1):
        window = hashes[i:i+w]
        min_val = min(window)
        fingerprints.add(min_val)
    return fingerprints

def _ast_tokens(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
        tokens = []
        for node in ast.walk(tree):
            tokens.append(node.__class__.__name__)
        return tokens
    except Exception:
        return []

def _compare_texts(t1: str, t2: str) -> float:
    fp1 = _get_winnowing_fingerprints(t1)
    fp2 = _get_winnowing_fingerprints(t2)
    if not fp1 or not fp2:
        return 0.0
    intersection = fp1.intersection(fp2)
    return (len(intersection) / min(len(fp1), len(fp2))) * 100.0

def _compare_codes(c1: str, c2: str) -> float:
    tok1 = _ast_tokens(c1)
    tok2 = _ast_tokens(c2)
    if not tok1 or not tok2:
        return 0.0
    s1 = set(tok1)
    s2 = set(tok2)
    inter = len(s1.intersection(s2))
    union = len(s1.union(s2))
    return (inter / union * 100.0) if union > 0 else 0.0

@router.post("/coursework/{cw_id}/originality-check")
def run_originality_check(cw_id: int, req: OriginalityCheckRequest, request: Request):
    user = require_user(request)
    is_teacher = user["role"] in ("teacher", "admin")
    student_id = req.student_id if is_teacher and req.student_id else user["user_id"]
    role_str = "teacher" if is_teacher else "student"

    with db_session() as conn:
        cw = conn.execute("SELECT * FROM coursework WHERE id = ?", (cw_id,)).fetchone()
        if not cw:
            raise HTTPException(status_code=404, detail="Задание не найдено")

        if not is_teacher:
            # Лимит 3 проверки для ученика
            runs = conn.execute(
                "SELECT COUNT(*) as c FROM originality_reports WHERE coursework_id = ? AND student_id = ? AND run_by_role = 'student'",
                (cw_id, student_id)
            ).fetchone()["c"]
            if runs >= 3:
                raise HTTPException(status_code=400, detail="Лимит проверок (3) исчерпан")

        # Получаем текст для проверки
        text_to_check = req.content_text or ""
        if not text_to_check:
            sub = conn.execute(
                "SELECT * FROM submissions WHERE coursework_id = ? AND student_id = ?",
                (cw_id, student_id)
            ).fetchone()
            if sub:
                text_to_check = sub.get("payload_json") or ""

        if not text_to_check or len(text_to_check.strip()) < 10:
            return {"ok": True, "match_percent": 0.0, "matches": []}

        # База сравнения: другие сдачи курса и инструкции задания
        other_subs = conn.execute("""
            SELECT student_id, payload_json
            FROM submissions
            WHERE coursework_id = ? AND student_id != ?
        """, (cw_id, student_id)).fetchall()

        max_match = 0.0
        matches = []

        is_code = "def " in text_to_check or "class " in text_to_check or "import " in text_to_check

        for os in other_subs:
            other_text = os.get("payload_json") or ""
            if not other_text:
                continue

            match_pct = 0.0
            if is_code:
                match_pct = _compare_codes(text_to_check, other_text)
            else:
                match_pct = _compare_texts(text_to_check, other_text)

            if match_pct > 15.0:
                matches.append({
                    "source": f"student_{os['student_id']}",
                    "match_percent": round(match_pct, 1),
                })
                if match_pct > max_match:
                    max_match = match_pct

        # Проверка против инструкции задания
        if cw["instructions"]:
            inst_pct = _compare_texts(text_to_check, cw["instructions"])
            if inst_pct > 15.0:
                matches.append({
                    "source": "instructions",
                    "match_percent": round(inst_pct, 1)
                })
                if inst_pct > max_match:
                    max_match = inst_pct

        max_match = round(min(100.0, max_match), 1)
        now = int(time.time())

        conn.execute("""
            INSERT INTO originality_reports (
                coursework_id, student_id, run_by_role, student_runs_used,
                match_percent, matches_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            cw_id, student_id, role_str, 1,
            max_match, json.dumps(matches, ensure_ascii=False), now
        ))

        return {
            "ok": True,
            "match_percent": max_match,
            "matches": matches,
            "checked_at": now
        }

@router.get("/coursework/{cw_id}/submissions/{student_id}/originality-report")
def get_originality_report(cw_id: int, student_id: int, request: Request):
    user = require_user(request)
    if user["role"] == "student" and user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Нет доступа")

    with db_session() as conn:
        row = conn.execute("""
            SELECT * FROM originality_reports
            WHERE coursework_id = ? AND student_id = ?
            ORDER BY created_at DESC LIMIT 1
        """, (cw_id, student_id)).fetchone()

        if not row:
            return {"match_percent": 0.0, "matches": []}

        r_dict = dict(row)
        try:
            r_dict["matches"] = json.loads(r_dict["matches_json"])
        except Exception:
            r_dict["matches"] = []
        return r_dict

# -----------------------------------------------------------------------------
# 4. Standards and Learning Goals
# -----------------------------------------------------------------------------

DEMO_STANDARDS = [
    {
        "id": "CASE-CS-01",
        "set_code": "CASE-CS",
        "code_label": "CS.ALG.01",
        "description": "Понятие алгоритма, свойства алгоритмов и исполнители",
        "subject_code": "inf",
        "grade_level": 8
    },
    {
        "id": "CASE-CS-02",
        "set_code": "CASE-CS",
        "code_label": "CS.PROG.02",
        "description": "Базовые конструкции языка Python: ветвления и циклы",
        "subject_code": "inf",
        "grade_level": 8
    },
    {
        "id": "FGOS-INF-7.1",
        "set_code": "FGOS",
        "code_label": "ФГОС.ИНФ.7.1",
        "description": "Информация и информационные процессы. Кодирование данных",
        "subject_code": "inf",
        "grade_level": 7
    },
    {
        "id": "FGOS-INF-8.2",
        "set_code": "FGOS",
        "code_label": "ФГОС.ИНФ.8.2",
        "description": "Элементы математической логики. Логические операции И, ИЛИ, НЕ",
        "subject_code": "inf",
        "grade_level": 8
    },
    {
        "id": "FGOS-MAT-6.3",
        "set_code": "FGOS",
        "code_label": "ФГОС.МАТ.6.3",
        "description": "Дроби, проценты и пропорции в реальных задачах",
        "subject_code": "mat",
        "grade_level": 6
    }
]

@router.post("/standards/seed")
def seed_standards(request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        count = 0
        for s in DEMO_STANDARDS:
            conn.execute("""
                INSERT OR IGNORE INTO learning_standards (id, set_code, code_label, description, subject_code, grade_level)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (s["id"], s["set_code"], s["code_label"], s["description"], s["subject_code"], s["grade_level"]))
            count += 1
        return {"ok": True, "count": count}

@router.get("/standards")
def list_standards(request: Request, subject_code: Optional[str] = None, set_code: Optional[str] = None):
    require_user(request)
    with db_session() as conn:
        query = "SELECT * FROM learning_standards WHERE 1=1"
        params = []
        if subject_code:
            query += " AND subject_code = ?"
            params.append(subject_code)
        if set_code:
            query += " AND set_code = ?"
            params.append(set_code)

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

@router.post("/items/{item_kind}/{item_id}/learning-goals")
def link_learning_goals(item_kind: str, item_id: int, req: LearningGoalsRequest, request: Request):
    user = require_teacher(request)
    with db_session() as conn:
        conn.execute("DELETE FROM item_learning_goals WHERE item_kind = ? AND item_id = ?", (item_kind, item_id))
        for sid in req.standard_ids:
            conn.execute("""
                INSERT OR IGNORE INTO item_learning_goals (item_kind, item_id, standard_id)
                VALUES (?, ?, ?)
            """, (item_kind, item_id, sid))
        return {"ok": True, "standard_ids": req.standard_ids}

@router.get("/classes/{class_id}/standards-mastery")
def get_standards_mastery(class_id: int, request: Request):
    user = require_user(request)
    with db_session() as conn:
        # 1. Находим все стандарты, привязанные к заданиям этого класса
        linked_standards = conn.execute("""
            SELECT DISTINCT ls.id, ls.code_label, ls.description, ilg.item_id as cw_id
            FROM item_learning_goals ilg
            JOIN coursework cw ON ilg.item_id = cw.id AND ilg.item_kind = 'coursework'
            JOIN learning_standards ls ON ilg.standard_id = ls.id
            WHERE cw.class_id = ?
        """, (class_id,)).fetchall()

        # 2. Ученики класса
        members = conn.execute("""
            SELECT cm.student_id, u.handle
            FROM class_members cm
            JOIN users u ON cm.student_id = u.id
            WHERE cm.class_id = ? AND cm.enrollment_active = 1
        """, (class_id,)).fetchall()

        # 3. Сдачи
        subs = conn.execute("""
            SELECT s.coursework_id, s.student_id, s.grade_points, cw.max_points
            FROM submissions s
            JOIN coursework cw ON s.coursework_id = cw.id
            WHERE cw.class_id = ? AND s.grade_points IS NOT NULL
        """, (class_id,)).fetchall()

        scores_map = {}
        for s in subs:
            k = (s["coursework_id"], s["student_id"])
            mx = s["max_points"] or 5
            pct = (s["grade_points"] / mx) * 100.0 if mx > 0 else 0.0
            scores_map[k] = pct

        std_dict = {}
        for row in linked_standards:
            sid = row["id"]
            if sid not in std_dict:
                std_dict[sid] = {
                    "standard_id": sid,
                    "code_label": row["code_label"],
                    "description": row["description"],
                    "coursework_ids": []
                }
            std_dict[sid]["coursework_ids"].append(row["cw_id"])

        mastery_matrix = []
        for m in members:
            stu_id = m["student_id"]
            row_data = {"student_id": stu_id, "handle": m["handle"], "standards": {}}
            for sid, sinfo in std_dict.items():
                cw_list = sinfo["coursework_ids"]
                earned = [scores_map[(cwid, stu_id)] for cwid in cw_list if (cwid, stu_id) in scores_map]
                avg = round(sum(earned) / len(earned), 1) if earned else None
                row_data["standards"][sid] = avg
            mastery_matrix.append(row_data)

        return {
            "standards": list(std_dict.values()),
            "matrix": mastery_matrix
        }
