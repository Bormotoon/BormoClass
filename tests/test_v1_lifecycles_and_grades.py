import json
import time
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import init_db, db_session
from app.classroom.router_submissions import calculate_sou_metrics

@pytest.fixture(scope="module")
def client():
    init_db()
    return TestClient(app)

def test_course_state_machine_and_invariants(client):
    # 1. Регистрация учителя
    t_reg = client.post("/api/passport/register", json={"role": "teacher", "password": "passStateTeach1"})
    assert t_reg.status_code == 200

    # 2. Ошибка: CourseTitleCannotContainUrl при создании курса с URL в названии
    bad_res = client.post("/v1/courses", json={"name": "Курс на https://google.com"})
    assert bad_res.status_code == 400
    assert "url" in bad_res.text.lower()

    # 3. Успешное создание курса
    c_res = client.post("/v1/courses", json={
        "name": "11А Профильная Математика",
        "section": "Профиль",
        "description": "Подготовка к ЕГЭ",
        "courseState": "PROVISIONED"
    })
    assert c_res.status_code == 200
    course = c_res.json()
    course_id = course["id"]
    assert course["courseState"] == "PROVISIONED"

    # 4. Переход PROVISIONED -> ACTIVE
    act_res = client.patch(f"/v1/courses/{course_id}?updateMask=courseState", json={"courseState": "ACTIVE"})
    assert act_res.status_code == 200
    assert act_res.json()["courseState"] == "ACTIVE"

    # 5. Переход ACTIVE -> ARCHIVED
    arch_res = client.patch(f"/v1/courses/{course_id}?updateMask=courseState", json={"courseState": "ARCHIVED"})
    assert arch_res.status_code == 200
    assert arch_res.json()["courseState"] == "ARCHIVED"

    # 6. Попытка создать объявление или задание в архивном курсе блокируется (CourseNotModifiable)
    blocked_post = client.post(f"/v1/courses/{course_id}/announcements", json={"text": "Новость в архиве"})
    assert blocked_post.status_code in (400, 403)
    err_text = blocked_post.text.lower()
    assert "заархивирован" in err_text or "заморожен" in err_text or "notmodifiable" in err_text or "coursearchived" in err_text

    # 7. Возврат ARCHIVED -> ACTIVE
    unarch_res = client.patch(f"/v1/courses/{course_id}?updateMask=courseState", json={"courseState": "ACTIVE"})
    assert unarch_res.status_code == 200
    assert unarch_res.json()["courseState"] == "ACTIVE"

    # 8. Копирование курса (Copy Course)
    copy_res = client.post(f"/api/classroom/classes/{course_id}/copy")
    assert copy_res.status_code == 200
    copied = copy_res.json()
    assert copied["id"] != int(course_id)
    assert "Профильная Математика" in copied["title"]

def test_submission_lifecycle_and_acl_lock(client):
    # Учитель
    t_reg = client.post("/api/passport/register", json={"role": "teacher", "password": "passLifecycleTeach2"})
    teacher_handle = t_reg.json()["user"]["handle"]
    c_res = client.post("/v1/courses", json={"name": "10Б Информатика", "courseState": "ACTIVE"})
    course_id = c_res.json()["id"]

    # Создаем задание с maxPoints = 100
    cw_res = client.post(f"/v1/courses/{course_id}/courseWork", json={
        "title": "Практикум: Динамическое программирование",
        "workType": "ASSIGNMENT",
        "maxPoints": 100,
        "state": "PUBLISHED"
    })
    assert cw_res.status_code == 200
    cw_id = cw_res.json()["id"]

    # Ученик
    s_reg = client.post("/api/passport/register", json={"role": "student", "password": "passLifecycleStud2"})
    student_id = s_reg.json()["user"]["id"]

    # Зачисление ученика
    join_res = client.post(f"/v1/courses/{course_id}/students", json={"userId": "me"}, params={"enrollmentCode": c_res.json()["enrollmentCode"]})
    assert join_res.status_code == 200

    # Получение сдачи ученика
    sub_res = client.get(f"/v1/courses/{course_id}/courseWork/{cw_id}/studentSubmissions")
    assert sub_res.status_code == 200
    submissions = sub_res.json().get("studentSubmissions", [])
    assert len(submissions) >= 1
    sub_id = submissions[0]["id"]
    assert submissions[0]["state"] in ("NEW", "CREATED")

    # Ученик сдает работу (turnIn)
    turn_res = client.post(f"/v1/courses/{course_id}/courseWork/{cw_id}/studentSubmissions/{sub_id}:turnIn")
    assert turn_res.status_code == 200
    sub_after_turn = client.get(f"/v1/courses/{course_id}/courseWork/{cw_id}/studentSubmissions/{sub_id}").json()
    assert sub_after_turn["state"] == "TURNED_IN"

    # Учитель заходит и выставляет draftGrade
    client.post("/api/passport/login", json={"handle": teacher_handle, "password": "passLifecycleTeach2"})
    patch_grade = client.patch(
        f"/v1/courses/{course_id}/courseWork/{cw_id}/studentSubmissions/{sub_id}?updateMask=draftGrade",
        json={"draftGrade": 95}
    )
    assert patch_grade.status_code == 200
    assert patch_grade.json()["draftGrade"] == 95.0

    # Ученик снова входит и проверяет видимость: draftGrade должен быть скрыт (None), пока работа не возвращена (:return)
    client.post("/api/passport/login", json={"handle": s_reg.json()["user"]["handle"], "password": "passLifecycleStud2"})
    stud_view = client.get(f"/v1/courses/{course_id}/courseWork/{cw_id}/studentSubmissions/{sub_id}")
    assert stud_view.status_code == 200
    assert stud_view.json().get("draftGrade") is None, "Ученик не должен видеть draftGrade до момента возврата работы!"

    # Ученик отзывает работу (:reclaim)
    rec_res = client.post(f"/v1/courses/{course_id}/courseWork/{cw_id}/studentSubmissions/{sub_id}:reclaim")
    assert rec_res.status_code == 200
    sub_after_rec = client.get(f"/v1/courses/{course_id}/courseWork/{cw_id}/studentSubmissions/{sub_id}").json()
    assert sub_after_rec["state"] == "RECLAIMED_BY_STUDENT"

    # Ученик снова сдает (:turnIn)
    client.post(f"/v1/courses/{course_id}/courseWork/{cw_id}/studentSubmissions/{sub_id}:turnIn")

    # Учитель возвращает работу (:return)
    client.post("/api/passport/login", json={"handle": teacher_handle, "password": "passLifecycleTeach2"})
    ret_res = client.post(f"/v1/courses/{course_id}/courseWork/{cw_id}/studentSubmissions/{sub_id}:return")
    assert ret_res.status_code == 200

def test_rubrics_grading_periods_and_gradebook(client):
    # Создаем курс и задание
    client.post("/api/passport/register", json={"role": "teacher", "password": "teachRubricPass3"})
    c_res = client.post("/v1/courses", json={"name": "9В Геометрия", "courseState": "ACTIVE"})
    course_id = c_res.json()["id"]

    cw_res = client.post(f"/v1/courses/{course_id}/courseWork", json={
        "title": "Теорема Пифагора",
        "workType": "ASSIGNMENT",
        "maxPoints": 10,
        "state": "PUBLISHED"
    })
    cw_id = cw_res.json()["id"]

    # 1. Создание критериальной рубрики
    rubric_payload = {
        "isScored": True,
        "criteria": [
            {
                "id": "c1",
                "title": "Чертеж и условие",
                "levels": [
                    {"id": "l1", "title": "Отлично", "points": 5},
                    {"id": "l2", "title": "Удовлетворительно", "points": 3}
                ]
            },
            {
                "id": "c2",
                "title": "Логика доказательства",
                "levels": [
                    {"id": "l3", "title": "Безупречно", "points": 5},
                    {"id": "l4", "title": "С ошибками", "points": 2}
                ]
            }
        ]
    }
    rub_res = client.post(f"/v1/courses/{course_id}/courseWork/{cw_id}/rubrics", json=rubric_payload)
    assert rub_res.status_code == 200
    rubric_id = rub_res.json()["id"]
    assert len(rub_res.json()["criteria"]) == 2

    # 2. Проверка валидации GradingPeriods (непересекающиеся интервалы)
    gp_valid = {
        "gradingPeriods": [
            {"title": "1 четверть", "startDate": {"year": 2026, "month": 9, "day": 1}, "endDate": {"year": 2026, "month": 10, "day": 31}},
            {"title": "2 четверть", "startDate": {"year": 2026, "month": 11, "day": 10}, "endDate": {"year": 2026, "month": 12, "day": 30}}
        ],
        "applyToExistingCoursework": True
    }
    gp_res = client.patch(f"/v1/courses/{course_id}/gradingPeriodSettings?updateMask=gradingPeriods,applyToExistingCoursework", json=gp_valid)
    assert gp_res.status_code == 200

    # Ошибка пересечения периодов
    gp_invalid = {
        "gradingPeriods": [
            {"title": "1 четверть", "startDate": {"year": 2026, "month": 9, "day": 1}, "endDate": {"year": 2026, "month": 11, "day": 15}},
            {"title": "2 четверть", "startDate": {"year": 2026, "month": 11, "day": 1}, "endDate": {"year": 2026, "month": 12, "day": 30}}
        ]
    }
    bad_gp = client.patch(f"/v1/courses/{course_id}/gradingPeriodSettings?updateMask=gradingPeriods", json=gp_invalid)
    assert bad_gp.status_code == 400
    assert "пересека" in bad_gp.json()["detail"].lower() or "invalid" in str(bad_gp.json()).lower()

    # 3. Настройка Gradebook: WEIGHTED_CATEGORIES
    gb_res = client.patch(f"/api/classroom/classes/{course_id}/gradebook-settings", json={
        "grade_calc_type": "WEIGHTED_CATEGORIES",
        "grade_display_setting": "SHOW_OVERALL_GRADE",
        "categories": [
            {"category_title": "Контрольные", "weight_micros": 600000},
            {"category_title": "Домашние задания", "weight_micros": 400000}
        ]
    })
    assert gb_res.status_code == 200
    assert gb_res.json()["grade_calc_type"] == "WEIGHTED_CATEGORIES"
