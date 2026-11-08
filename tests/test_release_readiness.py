import json
import time
import secrets
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import init_db, db_session
from app.passport.pii_guard import (
    E2EE_TEXT_PREFIX,
    e2ee_encrypt_text_helper
)
from app.storage.engine import save_blob, ensure_teacher_folder, ensure_student_copy
from app.classroom.router_submissions import calculate_sou_metrics

TEST_KEY = b"BORMO_TEST_AES_256_GCM_KEY_32B_!"

FORBIDDEN_COLUMNS = {
    "full_name", "first_name", "last_name", "middle_name", "patronymic",
    "fio", "name", "email", "mail", "phone", "tel", "birth_year",
    "birth_date", "birthday", "gender", "sex", "ip", "ip_address", "passport",
    "encrypted_note"
}

@pytest.fixture
def client():
    init_db()
    return TestClient(app)

def test_1_zero_pii_and_airgap_invariants(client):
    """
    1. Инварианты Zero-PII и Airgap:
       - Сканирование SQLite-файлов на отсутствие столбцов с ПД (email, phone, ip, snils, real_name).
       - Проверка заголовков ответа на CSP default-src 'self'.
    """
    violations = []
    with db_session() as conn:
        tables = [
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if not row["name"].startswith("sqlite_")
        ]
        assert len(tables) >= 9, "Все таблицы BormoClass должны быть инициализированы"
        for table in tables:
            cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
            col_names = {c["name"].lower() for c in cols}
            found = col_names.intersection(FORBIDDEN_COLUMNS)
            if found:
                violations.append(f"Table '{table}' has forbidden PII columns: {found}")

    assert len(violations) == 0, f"Found Zero-PII column violations: {violations}"

    # Проверка Airgap CSP заголовка
    resp = client.get("/")
    assert resp.status_code == 200
    csp = resp.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp, f"Strict Airgap CSP default-src 'self' missing: {csp}"

def test_2_passport_dictionary_and_rate_limit(client):
    """
    2. Паспорт:
       - Регистрация учителя и ученика с валидацией словарных позывных (принятие правильных, отказ на несловарных).
       - Rate-limit на восстановление пароля (5 попыток на IP).
    """
    # Попытка зарегистрироваться с несловарным позывным
    bad_reg = client.post("/api/passport/register", json={
        "role": "student",
        "password": "Password123!",
        "candidate_handle": "vasya_pupkin_123"
    })
    assert bad_reg.status_code == 422
    assert "официального словаря" in bad_reg.json()["detail"]

    # Успешная регистрация с официальным словарным позывным
    with db_session() as conn:
        for _ in range(1000):
            code = secrets.randbelow(9000) + 1000
            candidate = f"Бодрый-Енот-{code}"
            if not conn.execute("SELECT 1 FROM users WHERE handle = ?", (candidate,)).fetchone():
                good_handle = candidate
                break
        else:
            good_handle = f"Бодрый-Енот-9999"
    good_reg = client.post("/api/passport/register", json={
        "role": "student",
        "password": "Password123!",
        "candidate_handle": good_handle
    })
    assert good_reg.status_code == 200
    assert good_reg.json()["user"]["handle"] == good_handle

    # Rate-limit на восстановление пароля (5 попыток)
    for _ in range(5):
        client.post("/api/passport/recover", json={
            "handle": good_handle,
            "recovery_words": ["неверное", "слово", "раз", "два"],
            "new_password": "NewPassword123!"
        })

    # 6-я попытка должна быть заблокирована с HTTP 429
    blocked_resp = client.post("/api/passport/recover", json={
        "handle": good_handle,
        "recovery_words": ["неверное", "слово", "раз", "два"],
        "new_password": "NewPassword123!"
    })
    assert blocked_resp.status_code == 429
    assert "Слишком много попыток" in blocked_resp.json()["detail"]

def test_3_comment_bank_and_e2ee(client):
    """
    3. Банк комментариев и E2EE:
       - Удаление комментария учителем по DELETE /comments/{id}.
       - Сохранение шифрованных комментариев без утечки plaintext на сервер.
    """
    # Регистрируем учителя и создаем класс
    t_reg = client.post("/api/passport/register", json={"role": "teacher", "password": "TeacherPass123!"}).json()["user"]
    c_res = client.post("/api/classroom/classes", json={"title": "Физика 9", "subject_code": "fiz", "grade_level": 9})
    class_id = c_res.json()["id"]

    # Создаем объявление в курсе
    ann_res = client.post(f"/api/classroom/classes/{class_id}/coursework", json={
        "title": "Инструктаж к уроку",
        "instructions": "Ознакомьтесь с техникой безопасности",
        "kind": "announcement"
    })
    ann_id = ann_res.json()["id"]

    secret_comment = "Замечательное решение задачи №4!"
    enc_comment = e2ee_encrypt_text_helper(secret_comment, TEST_KEY)

    # Публикуем комментарий с явным шифрованием (X-Skip-E2EE, чтобы проверить контракт)
    post_res = client.post(
        f"/api/classroom/classes/{class_id}/comments",
        json={"body_text": enc_comment, "parent_kind": "announcement", "parent_id": ann_id},
        headers={"X-Skip-E2EE": "1"}
    )
    assert post_res.status_code == 200
    comment_id = post_res.json()["id"]

    # Проверяем, что в БД хранится BORMO_E2EE_V1: и 0 байт открытого текста
    with db_session() as conn:
        row = conn.execute("SELECT body_text FROM class_comments WHERE id = ?", (comment_id,)).fetchone()
        assert row is not None
        assert row["body_text"].startswith(E2EE_TEXT_PREFIX)
        assert secret_comment not in row["body_text"]

    # Учитель удаляет комментарий
    del_res = client.delete(f"/api/classroom/classes/{class_id}/comments/{comment_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # Проверяем, что комментарий помечен удаленным в БД (is_deleted = 1)
    with db_session() as conn:
        deleted_row = conn.execute("SELECT is_deleted FROM class_comments WHERE id = ?", (comment_id,)).fetchone()
        assert deleted_row is not None
        assert deleted_row["is_deleted"] == 1

def test_4_student_copy_materialization(client):
    """
    4. Материализация копии ученика:
       - ensure_student_copy создает независимый student_copy с валидным new_file_id.
    """
    # Регистрируем учителя, ученика и класс
    t_reg = client.post("/api/passport/register", json={"role": "teacher", "password": "TeacherPass123!"}).json()["user"]
    c_res = client.post("/api/classroom/classes", json={"title": "Информатика 8", "subject_code": "inf", "grade_level": 8})
    class_id = c_res.json()["id"]

    s_reg = client.post("/api/passport/register", json={"role": "student", "password": "StudentPass123!"}).json()["user"]
    student_id = s_reg["id"]

    with db_session() as conn:
        # Создаем папку учителя для курса
        t_folder = ensure_teacher_folder(conn, class_id, t_reg["id"])

        # Создаем шаблонный файл
        sha256, rel_path, size = save_blob(b"TEMPLATE_CONTENT_BORMO")
        tmpl_file_id = f"file_{secrets.token_hex(8)}"
        now = int(time.time())
        conn.execute("""
            INSERT INTO stored_files (
                id, folder_id, owner_user_id, file_title, mime_type,
                size_bytes, sha256_hex, disk_rel_path, file_kind,
                source_template_id, created_at, updated_at
            ) VALUES (?, ?, ?, 'Шаблон.pdf', 'application/pdf', ?, ?, ?, 'DOCUMENT', NULL, ?, ?)
        """, (tmpl_file_id, t_folder["id"], t_reg["id"], size, sha256, rel_path, now, now))

        # Создаем задание с материалом STUDENT_COPY
        materials_json = json.dumps([{
            "driveFile": {
                "driveFile": {"id": tmpl_file_id, "title": "Шаблон.pdf"},
                "shareMode": "STUDENT_COPY"
            }
        }])
        cursor = conn.execute("""
            INSERT INTO coursework (
                class_id, title, instructions, max_points, recess_reward,
                attachments_json, state, created_at, updated_at
            ) VALUES (?, 'Лабораторная 1', 'Выполнить по шаблону', 5, 300, ?, 'PUBLISHED', ?, ?)
        """, (class_id, materials_json, now, now))
        cw_id = cursor.lastrowid

        cw_row = {
            "id": cw_id,
            "class_id": class_id,
            "materials_json": materials_json
        }

        # Вызываем материализацию копии ученика
        ensure_student_copy(conn, cw_row, student_id)

        # Проверяем, что в submission_attachments появилась копия
        att = conn.execute("""
            SELECT attachment_json FROM submission_attachments
            WHERE coursework_id = ? AND student_id = ? AND created_by_template = 1
        """, (cw_id, student_id)).fetchone()
        assert att is not None
        data = json.loads(att["attachment_json"])
        assert data.get("source_template_id") == tmpl_file_id
        new_file_id = data.get("file_id")
        assert new_file_id is not None
        assert new_file_id != tmpl_file_id

        # Проверяем, что файл существует в stored_files и выдан EDIT доступ ученику
        copied_file = conn.execute("SELECT * FROM stored_files WHERE id = ?", (new_file_id,)).fetchone()
        assert copied_file is not None
        assert copied_file["source_template_id"] == tmpl_file_id
        assert copied_file["owner_user_id"] == student_id

        acl = conn.execute("SELECT access_mode FROM file_acl WHERE file_id = ? AND user_id = ?", (new_file_id, student_id)).fetchone()
        assert acl is not None
        assert acl["access_mode"] == "EDIT"

def test_5_quiz_autocheck_and_practice_set(client):
    """
    5. Квизы и Practice Sets:
       - Сдача квиза с автопроверкой и вычислением СОУ.
       - Проверка карточки Practice Set через /api/classroom/practice-sets/{id}/check-card.
    """
    # Регистрируем учителя и класс
    t_reg = client.post("/api/passport/register", json={"role": "teacher", "password": "TeacherPass123!"}).json()["user"]
    c_res = client.post("/api/classroom/classes", json={"title": "Геометрия 7", "subject_code": "geo", "grade_level": 7})
    class_id = c_res.json()["id"]

    # Создаем квиз
    questions = [
        {
            "id": "q1",
            "type": "SINGLE_CHOICE",
            "prompt": "Сколько градусов сумма углов треугольника?",
            "options": ["180", "90", "360"],
            "correct": "180",
            "points": 5
        },
        {
            "id": "q2",
            "type": "SINGLE_CHOICE",
            "prompt": "Прямой угол равен 90 градусов?",
            "options": ["true", "false"],
            "correct": "true",
            "points": 5
        }
    ]
    quiz_res = client.post("/api/classroom/quizzes", json={
        "class_id": class_id,
        "quiz_title": "Экспресс-тест 1",
        "shuffle_questions": 0,
        "questions_json": json.dumps(questions)
    })
    assert quiz_res.status_code == 200
    quiz_id = quiz_res.json()["id"]

    # Регистрируем ученика и зачисляем в класс
    s_reg = client.post("/api/passport/register", json={"role": "student", "password": "StudentPass123!"}).json()["user"]
    student_id = s_reg["id"]
    join_res = client.post("/api/classroom/classes/join", json={"join_pin": c_res.json()["join_pin"], "seat_number": 5})
    assert join_res.status_code == 200

    # Ученик сдает квиз с идеальными ответами
    submit_res = client.post(f"/api/classroom/quizzes/{quiz_id}/submit", json={
        "answers_json": {"q1": "180", "q2": "true"},
        "focus_lost_count": 0
    })
    assert submit_res.status_code == 200
    sub_data = submit_res.json()
    assert sub_data["auto_score"] == 10
    assert sub_data["max_score"] == 10

    # Проверяем расчет метрик СОУ по Симонову
    mock_subs = [{"grade_five": 5}, {"grade_five": 4}, {"grade_five": 3}]
    metrics = calculate_sou_metrics(mock_subs)
    assert metrics["usp"] == 100.0  # 100% успеваемость
    assert metrics["kz"] == 66.7    # 2 из 3 на 4 и 5
    assert metrics["sou"] == 66.7   # (100*1 + 64*1 + 36*1)/3 = 66.67%

    # Учитель создает интерактивный Practice Set
    client.post("/api/passport/login", json={"handle": t_reg["handle"], "password": "TeacherPass123!"})
    cards = [
        {
            "card_id": "card_01",
            "prompt": "2 + 2 * 2 = ?",
            "answer": "6",
            "hints": ["Сначала умножение"]
        }
    ]
    set_res = client.post("/api/classroom/practice-sets", json={
        "class_id": class_id,
        "set_title": "Тренировка формул",
        "cards_json": json.dumps(cards)
    })
    assert set_res.status_code == 200
    set_id = set_res.json()["id"]

    # Ученик проверяет карточку задания через /check-card
    client.post("/api/passport/login", json={"handle": s_reg["handle"], "password": "StudentPass123!"})
    chk_correct = client.post(f"/api/classroom/practice-sets/{set_id}/check-card", json={
        "card_id": "card_01",
        "answer": "6"
    })
    assert chk_correct.status_code == 200
    assert chk_correct.json()["correct"] is True

    chk_wrong = client.post(f"/api/classroom/practice-sets/{set_id}/check-card", json={
        "card_id": "card_01",
        "answer": "8"
    })
    assert chk_wrong.status_code == 200
    assert chk_wrong.json()["correct"] is False

def test_6_rbac_and_idor_isolation(client):
    """
    6. RBAC и IDOR:
       - Попытка ученика получить матрицу или аналитику чужого класса (ожидается 403 Forbidden).
       - Попытка не-админа скачать takeout.zip домена (ожидается 403 Forbidden).
    """
    # Учитель 1 создает Класс 1
    t1 = client.post("/api/passport/register", json={"role": "teacher", "password": "TeacherPass123!"}).json()["user"]
    c1 = client.post("/api/classroom/classes", json={"title": "Секретный класс", "subject_code": "sec", "grade_level": 11}).json()
    c1_id = c1["id"]

    # Ученик 2 (НЕ состоит в Классе 1)
    s2 = client.post("/api/passport/register", json={"role": "student", "password": "StudentPass123!"}).json()["user"]

    # Ученик 2 пытается получить чужую матрицу оценок -> 403
    matrix_resp = client.get(f"/api/classroom/classes/{c1_id}/matrix")
    assert matrix_resp.status_code == 403
    assert "Нет доступа" in matrix_resp.json()["detail"]

    # Ученик 2 пытается получить чужую аналитику -> 403
    analytics_resp = client.get(f"/api/classroom/classes/{c1_id}/analytics")
    assert analytics_resp.status_code == 403
    assert "Нет доступа" in analytics_resp.json()["detail"]

    # Ученик 2 пытается скачать доменный Takeout архива -> 403
    takeout_s = client.get("/api/classroom/admin/takeout.zip")
    assert takeout_s.status_code == 403

    # Учитель 1 (не админ) пытается скачать доменный Takeout архива -> 403
    client.post("/api/passport/login", json={"handle": t1["handle"], "password": "TeacherPass123!"})
    takeout_t = client.get("/api/classroom/admin/takeout.zip")
    assert takeout_t.status_code == 403

    # Но учитель может скачать свой личный Takeout архива курсов -> 200
    teacher_takeout = client.get("/api/classroom/teacher/takeout.zip")
    assert teacher_takeout.status_code == 200
    assert teacher_takeout.headers["content-type"] == "application/zip"
