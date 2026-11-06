import inspect
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import init_db, db_session
from app.classroom.router_submissions import calculate_sou_metrics
import app.classroom.router_classes as r_classes
import app.classroom.router_coursework as r_cw
import app.classroom.router_submissions as r_sub
import app.classroom.router_global as r_glob
import app.classroom.router_board as r_brd

@pytest.fixture(scope="module")
def client():
    init_db()
    return TestClient(app)

def test_sync_routes_invariant():
    """Проверка инварианта неблокирующего FastAPI + SQLite:
    Все обычные обработчики маршрутов должны быть объявлены через def (синхронные),
    и только SSE-стримы (/api/board/{class_id}/stream, /api/classroom/{class_id}/stream) могут быть async def.
    """
    for module in (r_classes, r_cw, r_sub, r_glob, r_brd):
        router = module.router
        for route in router.routes:
            endpoint = route.endpoint
            path = route.path
            is_async = inspect.iscoroutinefunction(endpoint)
            if "/stream" in path:
                assert is_async, f"SSE-роут {path} обязан быть async def"
            else:
                assert not is_async, f"Синхронный DB-роут {path} ({endpoint.__name__}) обязан быть def (не async def)"

def test_sou_simonov_metrics_accuracy():
    # Тест 1: все пятёрки
    m1 = calculate_sou_metrics([5, 5, 5, 5])
    assert m1["usp"] == 100.0
    assert m1["kz"] == 100.0
    assert m1["sou"] == 100.0

    # Тест 2: 1 пятерка, 1 четверка, 1 тройка, 1 двойка (всего 4)
    # Усп = (1 + 1 + 1)/4 = 75.0%
    # КЗ = (1 + 1)/4 = 50.0%
    # СОУ = (100*1 + 64*1 + 36*1 + 16*1)/4 = 216 / 4 = 54.0%
    m2 = calculate_sou_metrics([5, 4, 3, 2])
    assert m2["usp"] == 75.0
    assert m2["kz"] == 50.0
    assert m2["sou"] == 54.0

    # Тест 3: типичный школьный класс из 20 учеников:
    # 4 пятерки, 8 четверок, 6 троек, 2 двойки
    # Усп = (4 + 8 + 6) / 20 * 100% = 18 / 20 = 90.0%
    # КЗ = (4 + 8) / 20 * 100% = 12 / 20 = 60.0%
    # СОУ = (100*4 + 64*8 + 36*6 + 16*2) / 20 = (400 + 512 + 216 + 32) / 20 = 1160 / 20 = 58.0%
    grades = [5]*4 + [4]*8 + [3]*6 + [2]*2
    m3 = calculate_sou_metrics(grades)
    assert m3["usp"] == 90.0
    assert m3["kz"] == 60.0
    assert m3["sou"] == 58.0

def test_first_grade_homework_forbidden(client):
    # 1. Регистрируем учителя
    reg = client.post("/api/passport/register", json={"role": "teacher", "password": "teachpassword1"})
    assert reg.status_code == 200

    # 2. Создаем 1 класс (grade_level = 1)
    class_resp = client.post("/api/classroom/classes", json={
        "title": "1А Начальная школа",
        "subject_code": "lit",
        "grade_level": 1,
        "quarter_goal": "Научиться читать"
    })
    assert class_resp.status_code == 200
    class_1_id = class_resp.json()["id"]

    # 3. Попытка выдать домашнее задание в 1 класс ОБЯЗАНА вернуть 400 Bad Request
    hw_resp = client.post(f"/api/classroom/classes/{class_1_id}/coursework", json={
        "title": "Прочитать букварь стр 10-15",
        "kind": "assignment",
        "is_homework": 1
    })
    assert hw_resp.status_code == 400
    assert "запрещены" in hw_resp.json()["detail"]

    # 4. Классная работа или объявление (is_homework = 0) должны успешно создаваться
    cw_resp = client.post(f"/api/classroom/classes/{class_1_id}/coursework", json={
        "title": "Урок письма: палочки и крючочки",
        "kind": "assignment",
        "is_homework": 0
    })
    assert cw_resp.status_code == 200
    assert cw_resp.json()["id"] > 0

    # 5. Для 8 класса ДЗ разрешено
    class_8 = client.post("/api/classroom/classes", json={
        "title": "8Б Информатика",
        "grade_level": 8
    })
    class_8_id = class_8.json()["id"]

    hw_8 = client.post(f"/api/classroom/classes/{class_8_id}/coursework", json={
        "title": "Параграф 3: Системы счисления",
        "kind": "assignment",
        "is_homework": 1
    })
    assert hw_8.status_code == 200

def test_classroom_membership_and_grading_flow(client):
    # Регистрируем учителя и создаем класс
    t_reg = client.post("/api/passport/register", json={"role": "teacher", "password": "teacherpass2"})
    c_res = client.post("/api/classroom/classes", json={"title": "9А Алгебра", "grade_level": 9})
    class_id = c_res.json()["id"]
    join_pin = c_res.json()["join_pin"]

    # Создаем задание
    cw_res = client.post(f"/api/classroom/classes/{class_id}/coursework", json={
        "title": "Квадратные уравнения",
        "kind": "assignment",
        "max_points": 5,
        "recess_reward": 300
    })
    cw_id = cw_res.json()["id"]

    # Регистрируем ученика
    s_reg = client.post("/api/passport/register", json={"role": "student", "password": "studentpass2"})
    student_id = s_reg.json()["user"]["id"]

    # Ученик входит в класс по пин-коду и выбирает парту №7
    join_res = client.post("/api/classroom/classes/join", json={
        "join_pin": join_pin,
        "seat_number": 7
    })
    assert join_res.status_code == 200

    # Проверяем светофор понимания ученика
    tl_res = client.post(f"/api/classroom/classes/{class_id}/traffic-light", json={"traffic_light": "yellow"})
    assert tl_res.status_code == 200
    assert tl_res.json()["traffic_light"] == "yellow"

    # Ученик сдает работу
    turnin_res = client.post(f"/api/classroom/coursework/{cw_id}/turn-in", json={
        "payload_json": '{"answer": "x1=2, x2=3"}'
    })
    assert turnin_res.status_code == 200
    assert turnin_res.json()["awarded_recess"] is True

    # Учитель входит снова
    client.post("/api/passport/login", json={"handle": t_reg.json()["user"]["handle"], "password": "teacherpass2"})

    # Учитель видит работу в to-review
    review_res = client.get("/api/classroom/global/to-review")
    assert review_res.status_code == 200
    assert any(item["coursework_id"] == cw_id for item in review_res.json())

    # Учитель оценивает работу на 5
    grade_res = client.post(f"/api/classroom/submissions/{cw_id}/{student_id}/grade", json={
        "grade_five": 5,
        "teacher_comment": "Отличное решение!"
    })
    assert grade_res.status_code == 200
    assert grade_res.json()["grade_five"] == 5

    # Проверяем матрицу класса
    matrix_res = client.get(f"/api/classroom/classes/{class_id}/matrix")
    assert matrix_res.status_code == 200
    m_data = matrix_res.json()
    assert len(m_data["students"]) == 1
    assert m_data["students"][0]["seat_number"] == 7
    assert m_data["analytics"]["n5"] == 1
    assert m_data["analytics"]["sou"] == 100.0
