import json
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import init_db, db_session
from app.config import settings
from app.classroom.router_submissions import calculate_sou_metrics
from app.passport.pii_guard import (
    E2EE_TEXT_PREFIX,
    E2EE_BLOB_MAGIC,
    e2ee_encrypt_text_helper,
    e2ee_decrypt_text_helper,
    e2ee_encrypt_blob_helper,
    e2ee_decrypt_blob_helper
)

TEST_KEY = b"BORMO_TEST_AES_256_GCM_KEY_32B_!"

@pytest.fixture
def client():
    init_db()
    return TestClient(app)

def test_1_rejection_of_unencrypted_data_with_422(client):
    """
    Тест 1: Попытка отправить открытый текст (без BORMO_E2EE_V1:) в задание,
    ответ ученика, комментарий учителя, доску или незашифрованный файл
    должна отклоняться сервером с HTTP 422.
    """
    # Регистрируем учителя
    t_reg = client.post("/api/passport/register", json={"role": "teacher", "password": "e2eeTeacherPass1"}).json()["user"]
    t_handle = t_reg["handle"]

    # Создаем курс
    c_res = client.post("/api/classroom/classes", json={"title": "10А Алгебра", "subject_code": "mat", "grade_level": 10})
    class_id = c_res.json()["id"]

    # 1. Попытка создать задание с открытым текстом (без шифрования BORMO_E2EE_V1)
    # Используем X-Skip-E2EE, чтобы тестовый клиент не зашифровал данные автоматически
    res_bad_cw = client.post(
        f"/api/classroom/classes/{class_id}/coursework",
        json={"title": "Теорема Пифагора", "instructions": "Доказать геометрически", "max_points": 5},
        headers={"X-Skip-E2EE": "1"}
    )
    assert res_bad_cw.status_code == 422
    assert "BORMO_E2EE_V1" in res_bad_cw.json()["detail"]

    # Создаем валидное зашифрованное задание
    enc_title = e2ee_encrypt_text_helper("Теорема Пифагора", TEST_KEY)
    enc_instr = e2ee_encrypt_text_helper("Доказать геометрически", TEST_KEY)
    cw_res = client.post(
        f"/api/classroom/classes/{class_id}/coursework",
        json={"title": enc_title, "instructions": enc_instr, "max_points": 5},
        headers={"X-Skip-E2EE": "1"}
    )
    assert cw_res.status_code == 200
    cw_id = cw_res.json()["id"]

    # 2. Попытка сдать незашифрованный ответ (turn-in)
    res_bad_sub = client.post(
        f"/api/classroom/coursework/{cw_id}/turn-in",
        json={"payload_json": "Мой открытый ответ на задание"},
        headers={"X-Skip-E2EE": "1"}
    )
    assert res_bad_sub.status_code == 422
    assert "BORMO_E2EE_V1" in res_bad_sub.json()["detail"]

    # 3. Попытка учителя выставить незашифрованный комментарий
    res_bad_grade = client.post(
        f"/api/classroom/submissions/{cw_id}/{t_reg['id']}/grade",
        json={"grade_points": 5, "teacher_comment": "Отличный ответ без шифрования"},
        headers={"X-Skip-E2EE": "1"}
    )
    assert res_bad_grade.status_code == 422
    assert "BORMO_E2EE_V1" in res_bad_grade.json()["detail"]

    # 4. Попытка сохранить незашифрованное состояние доски
    res_bad_board = client.post(
        f"/api/classroom/board/{class_id}/state",
        json={"classroom_state_json": '{"drawing": "raw plaintext elements"}'},
        headers={"X-Skip-E2EE": "1"}
    )
    assert res_bad_board.status_code == 422
    assert "BORMO_E2EE_V1" in res_bad_board.json()["detail"]

    # 5. Попытка загрузить незашифрованный файл
    raw_file = b"%PDF-1.4 raw unencrypted document stream"
    files = {"file": ("document.pdf", raw_file, "application/pdf")}
    res_bad_file = client.post("/api/storage/upload", files=files, headers={"X-Skip-E2EE": "1"})
    assert res_bad_file.status_code == 422
    assert "BC_E2EE_BLOB_V1" in res_bad_file.json()["detail"]

def test_2_rejection_of_pii_with_152_fz_message(client):
    """
    Тест 2: Попытка отправить открытый текст с ФИО, email или телефоном
    должна сначала вызывать проверку 152-ФЗ с точным текстом ошибки.
    """
    t_reg = client.post("/api/passport/register", json={"role": "teacher", "password": "e2eeTeacherPass2"}).json()["user"]
    c_res = client.post("/api/classroom/classes", json={"title": "9Б Геометрия", "subject_code": "mat", "grade_level": 9})
    class_id = c_res.json()["id"]

    # ФИО
    res_fio = client.post(
        f"/api/classroom/classes/{class_id}/coursework",
        json={"title": "Задание для Сидоров Алексей Иванович", "instructions": "", "max_points": 5},
        headers={"X-Skip-E2EE": "1"}
    )
    assert res_fio.status_code == 422
    assert "ФИО" in res_fio.json()["detail"]

    # Телефон
    res_tel = client.post(
        f"/api/classroom/classes/{class_id}/coursework",
        json={"title": "Консультации", "instructions": "Звонить +7 (903) 555-44-33", "max_points": 5},
        headers={"X-Skip-E2EE": "1"}
    )
    assert res_tel.status_code == 422
    assert "Номер телефона" in res_tel.json()["detail"]

    # Email
    res_mail = client.post(
        f"/api/classroom/classes/{class_id}/coursework",
        json={"title": "Почта", "instructions": "Пишите на math_teacher@lyceum.ru", "max_points": 5},
        headers={"X-Skip-E2EE": "1"}
    )
    assert res_mail.status_code == 422
    assert "Email" in res_mail.json()["detail"]

def test_3_full_e2ee_lifecycle(client):
    """
    Тест 3: Полный цикл с зашифрованными данными:
    Создание класса -> публикация задания (BORMO_E2EE_V1:...) ->
    загрузка файла (BC_E2EE_BLOB_V1\\0...) -> сдача работы учеником ->
    выставление оценки и комментария учителем.
    """
    # 1. Учитель
    t_res = client.post("/api/passport/register", json={"role": "teacher", "password": "cycleTeachPass1"}).json()["user"]
    c_res = client.post("/api/classroom/classes", json={"title": "10В Информатика", "subject_code": "inf", "grade_level": 10})
    class_id = c_res.json()["id"]
    join_pin = c_res.json()["join_pin"]

    # 2. Создание задания
    secret_title = "Квадратные уравнения и дискриминант"
    secret_instr = "Решить систему уравнений №41-45"
    cw_res = client.post(f"/api/classroom/classes/{class_id}/coursework", json={
        "title": secret_title,
        "instructions": secret_instr,
        "max_points": 5,
        "recess_reward": 300
    })
    assert cw_res.status_code == 200
    cw_id = cw_res.json()["id"]

    # 3. Загрузка файла учителем
    secret_file_bytes = b"TOP_SECRET_EXAM_SHEET_CONTENT_2026"
    files = {"file": ("materials.pdf", secret_file_bytes, "application/pdf")}
    up_res = client.post("/api/storage/upload", files=files)
    assert up_res.status_code == 200
    file_id = up_res.json()["id"]

    # 4. Ученик
    s_res = client.post("/api/passport/register", json={"role": "student", "password": "cycleStudPass1"}).json()["user"]
    client.post("/api/passport/login", json={"handle": s_res["handle"], "password": "cycleStudPass1"})
    join_res = client.post("/api/classroom/classes/join", json={"join_pin": join_pin, "seat_number": 3})
    assert join_res.status_code == 200

    # 5. Ученик сдает работу
    secret_student_answer = "Секретный ответ ученика: x1 = 2, x2 = -5"
    turn_in_res = client.post(f"/api/classroom/coursework/{cw_id}/turn-in", json={
        "payload_json": secret_student_answer
    })
    assert turn_in_res.status_code == 200

    # 6. Учитель проверяет работу и оставляет комментарий
    client.post("/api/passport/login", json={"handle": t_res["handle"], "password": "cycleTeachPass1"})
    secret_teacher_comment = "Замечательное решение! Оценка 5."
    grade_res = client.post(f"/api/classroom/submissions/{cw_id}/{s_res['id']}/grade", json={
        "grade_points": 5,
        "grade_five": 5,
        "teacher_comment": secret_teacher_comment
    })
    assert grade_res.status_code == 200

def test_4_server_database_and_disk_audit_zero_plaintext(client):
    """
    Тест 4: Аудит БД и диска от лица владельца сервера.
    Прямое чтение всех таблиц SQLite и файлов в data/storage/ подтверждает,
    что исходные секретные строки нигде не встречаются в БД и на диске в открытом виде (0 вхождений).
    """
    secret_tokens = [
        "Квадратные уравнения и дискриминант",
        "Решить систему уравнений №41-45",
        "TOP_SECRET_EXAM_SHEET_CONTENT_2026",
        "Секретный ответ ученика: x1 = 2, x2 = -5",
        "Замечательное решение! Оценка 5."
    ]

    with db_session() as conn:
        # Проверяем все таблицы
        tables = [
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if not row["name"].startswith("sqlite_")
        ]

        for table in tables:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            for r in rows:
                dumped_row = " ".join(str(val) for val in dict(r).values())
                for secret in secret_tokens:
                    assert secret not in dumped_row, (
                        f"Утечка секретных данных в открытом виде! Секрет '{secret}' найден в таблице {table}."
                    )

    # Проверяем все файлы в data/storage/
    storage_dir = Path(settings.STORAGE_DIR)
    if storage_dir.exists():
        for fpath in storage_dir.rglob("*"):
            if fpath.is_file():
                raw_bytes = fpath.read_bytes()
                for secret in secret_tokens:
                    assert secret.encode("utf-8") not in raw_bytes, (
                        f"Утечка секретных данных на диске! Секрет '{secret}' найден в файле {fpath}."
                    )

def test_5_quiz_autocheck_and_sou_simonov_accuracy(client):
    """
    Тест 5: Автопроверка квиза и расчет аналитики СОУ по В. П. Симонову
    при зашифрованных полях работают со 100% точностью.
    """
    # Регистрируем учителя и создаем курс
    t_res = client.post("/api/passport/register", json={"role": "teacher", "password": "quizSouPass1"}).json()["user"]
    c_res = client.post("/api/classroom/classes", json={"title": "8В Физика", "subject_code": "fiz", "grade_level": 8})
    class_id = c_res.json()["id"]

    # Создаем квиз с зашифрованными текстами вопросов
    q1_prompt = e2ee_encrypt_text_helper("Чему равна скорость света в вакууме?", TEST_KEY)
    q2_prompt = e2ee_encrypt_text_helper("Формула второго закона Ньютона", TEST_KEY)

    questions = [
        {
            "id": "1",
            "type": "SINGLE_CHOICE",
            "prompt": q1_prompt,
            "points": 2.0,
            "correct": "300000"
        },
        {
            "id": "2",
            "type": "NUMERIC_TOLERANCE",
            "prompt": q2_prompt,
            "points": 3.0,
            "target": 9.8,
            "tolerance": 0.1
        }
    ]

    quiz_res = client.post("/api/classroom/quizzes", json={
        "class_id": class_id,
        "quiz_title": "Контрольная работа по оптике и механике",
        "description": "2 вопроса",
        "questions_json": json.dumps(questions, ensure_ascii=False)
    })
    assert quiz_res.status_code == 200
    quiz_id = quiz_res.json()["id"]

    # Ученик решает квиз
    s_res = client.post("/api/passport/register", json={"role": "student", "password": "quizStudPass1"}).json()["user"]
    client.post("/api/passport/login", json={"handle": s_res["handle"], "password": "quizStudPass1"})

    submit_res = client.post(f"/api/classroom/quizzes/{quiz_id}/submit", json={
        "answers_json": {
            "1": "300000",  # правильный ответ (+2 балла)
            "2": 9.81       # правильный ответ с допуском (+3 балла)
        }
    })
    assert submit_res.status_code == 200
    sub_data = submit_res.json()
    assert sub_data["auto_score"] == 5.0
    assert sub_data["max_score"] == 5.0

    # Проверка формулы СОУ по В. П. Симонову
    # Оценки: три пятерки, две четверки, одна тройка -> [5, 5, 5, 4, 4, 3]
    # N = 6, n5 = 3, n4 = 2, n3 = 1, n2 = 0
    # Усп = 100.0%
    # КЗ = (3 + 2) / 6 = 83.33%
    # СОУ = (3*100 + 2*64 + 1*36 + 0*16) / 6 = (300 + 128 + 36) / 6 = 464 / 6 = 77.33%
    metrics = calculate_sou_metrics([5, 5, 5, 4, 4, 3])
    assert metrics["n_total"] == 6
    assert metrics["n5"] == 3
    assert metrics["n4"] == 2
    assert metrics["n3"] == 1
    assert metrics["n2"] == 0
    assert metrics["usp"] == 100.0
    assert metrics["kz"] == 83.3
    assert metrics["sou"] == 77.3
