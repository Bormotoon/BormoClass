import json
import time
import zipfile
import io
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import init_db, db_session
from app.v1.rbac import (
    SCOPE_ROSTERS,
    SCOPE_ROSTERS_READONLY,
    SCOPE_COURSES,
    SCOPE_COURSEWORK_STUDENTS
)

@pytest.fixture(scope="module")
def client():
    init_db()
    return TestClient(app)

def test_oauth_scopes_and_developer_isolation(client):
    # Регистрируем учителя
    t_reg = client.post("/api/passport/register", json={"role": "teacher", "password": "passOAuthTeach1"})
    assert t_reg.status_code == 200
    t_handle = t_reg.json()["user"]["handle"]

    # Создаем курс
    c_res = client.post("/v1/courses", json={"name": "8А Алгебра", "courseState": "ACTIVE"})
    assert c_res.status_code == 200
    course_id = c_res.json()["id"]

    # Регистрируем OAuth клиент A
    cl_a = client.post("/api/v1-oauth/clients", json={"client_title": "App A", "scopes": [SCOPE_ROSTERS_READONLY]})
    assert cl_a.status_code == 200
    cl_a_data = cl_a.json()

    # Получаем токен A с правами ТОЛЬКО ROSTERS_READONLY
    tok_a_res = client.post("/api/v1-oauth/token", json={
        "client_id": cl_a_data["client_id"],
        "client_secret": cl_a_data["client_secret"],
        "scopes": [SCOPE_ROSTERS_READONLY]
    })
    assert tok_a_res.status_code == 200
    token_a = tok_a_res.json()["access_token"]

    # Регистрируем нового пользователя
    stud_user = client.post("/api/passport/register", json={"role": "teacher", "password": "passNewTeach2"}).json()["user"]

    # Попытка добавить учителя через токен A (write операция с readonly скоупом) -> 403 ACCESS_TOKEN_SCOPE_INSUFFICIENT
    h_a = {"Authorization": f"Bearer {token_a}"}
    write_res = client.post(f"/v1/courses/{course_id}/teachers", json={"userId": str(stud_user["id"])}, headers=h_a)
    assert write_res.status_code == 403
    assert "scope" in write_res.text.lower() or "insufficient" in write_res.text.lower()

    # Входим обратно как владелец курса
    client.post("/api/passport/login", json={"handle": t_handle, "password": "passOAuthTeach1"})

    # Регистрируем OAuth клиент B с полным скоупом SCOPE_ROSTERS
    cl_b = client.post("/api/v1-oauth/clients", json={"client_title": "App B", "scopes": [SCOPE_ROSTERS]})
    cl_b_data = cl_b.json()
    tok_b_res = client.post("/api/v1-oauth/token", json={
        "client_id": cl_b_data["client_id"],
        "client_secret": cl_b_data["client_secret"],
        "scopes": [SCOPE_ROSTERS]
    })
    token_b = tok_b_res.json()["access_token"]
    h_b = {"Authorization": f"Bearer {token_b}"}

    # Теперь добавление со-учителя через токен B успешно
    add_t = client.post(f"/v1/courses/{course_id}/teachers", json={"userId": str(stud_user["id"])}, headers=h_b)
    assert add_t.status_code == 200

    # Проверка инварианта CannotDeleteCourseOwner: удаление владельца курса запрещено
    owner_id = c_res.json()["ownerId"]
    del_owner = client.delete(f"/v1/courses/{course_id}/teachers/{owner_id}")
    assert del_owner.status_code == 403
    assert "cannotdeletecourseowner" in del_owner.text.lower() or "владельца" in del_owner.text.lower()

def test_invitations_and_student_groups(client):
    # Создаем курс
    t_reg = client.post("/api/passport/register", json={"role": "teacher", "password": "teachGroupsPass4"})
    t_handle = t_reg.json()["user"]["handle"]
    c_res = client.post("/v1/courses", json={"name": "7Б Биология", "courseState": "ACTIVE"})
    course_id = c_res.json()["id"]

    # Регистрируем нового учителя для приглашения
    new_t = client.post("/api/passport/register", json={"role": "teacher", "password": "invitedTeachPass5"}).json()["user"]

    # Входим обратно как учитель курса для отправки инвайта
    client.post("/api/passport/login", json={"handle": t_handle, "password": "teachGroupsPass4"})

    # 1. Приглашение со-учителя
    inv_res = client.post("/v1/invitations", json={
        "courseId": str(course_id),
        "userId": str(new_t["id"]),
        "role": "TEACHER"
    })
    assert inv_res.status_code == 200
    inv_id = inv_res.json()["id"]

    # Приглашенный учитель логинится и принимает приглашение (:accept)
    client.post("/api/passport/login", json={"handle": new_t["handle"], "password": "invitedTeachPass5"})
    acc_res = client.post(f"/v1/invitations/{inv_id}:accept")
    assert acc_res.status_code == 200

    # Проверяем, что учитель появился в курсе
    t_list = client.get(f"/v1/courses/{course_id}/teachers").json().get("teachers", [])
    assert any(t["userId"] == str(new_t["id"]) for t in t_list)

    # 2. Учебные подгруппы (studentGroups)
    client.post("/api/passport/login", json={"handle": t_handle, "password": "teachGroupsPass4"})
    grp_res = client.post(f"/v1/courses/{course_id}/studentGroups", json={"title": "Группа олимпиадников"})
    assert grp_res.status_code == 200
    grp_id = grp_res.json()["id"]

    # Зачисляем ученика
    s_user = client.post("/api/passport/register", json={"role": "student", "password": "grpStudPass6"}).json()["user"]
    # Входим как учитель и зачисляем ученика в курс
    client.post("/api/passport/login", json={"handle": t_handle, "password": "teachGroupsPass4"})
    client.post(f"/v1/courses/{course_id}/students", json={"userId": str(s_user["id"])})

    # Добавляем ученика в подгруппу учителем
    gm_res = client.post(f"/v1/courses/{course_id}/studentGroups/{grp_id}/studentGroupMembers", json={"userId": str(s_user["id"])})
    assert gm_res.status_code == 200

    # Проверяем список подгруппы
    members_res = client.get(f"/v1/courses/{course_id}/studentGroups/{grp_id}/studentGroupMembers")
    assert members_res.status_code == 200
    assert len(members_res.json().get("studentGroupMembers", [])) == 1

def test_calendar_and_admin_takeout(client):
    # 1. Создаем курс
    t_reg = client.post("/api/passport/register", json={"role": "teacher", "password": "teachRegPass12"})
    t_handle = t_reg.json()["user"]["handle"]
    c_res = client.post("/v1/courses", json={"name": "7А Химия", "courseState": "ACTIVE"})
    course_id = c_res.json()["id"]

    # 2. Экспорт Календаря в формате RFC 5545 iCalendar (.ics)
    with db_session() as conn:
        row = conn.execute("SELECT calendar_token FROM classes WHERE id = ?", (course_id,)).fetchone()
        cal_token = row["calendar_token"]
    ics_res = client.get(f"/api/classroom/calendar/{cal_token}.ics")
    assert ics_res.status_code == 200
    assert "BEGIN:VCALENDAR" in ics_res.text
    assert "END:VCALENDAR" in ics_res.text

    # 3. Админ-консоль: Data Takeout ZIP экспорт (чистый локальный JSON-бэкап)
    admin_reg = client.post("/api/passport/register", json={"role": "teacher", "password": "adminSecretPass13"}).json()["user"]
    with db_session() as conn:
        conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (admin_reg["id"],))
    client.post("/api/passport/login", json={"handle": admin_reg["handle"], "password": "adminSecretPass13"})

    takeout_res = client.get("/api/classroom/takeout.zip")
    assert takeout_res.status_code == 200
    assert takeout_res.headers["content-type"] in ("application/zip", "application/x-zip-compressed")

    with zipfile.ZipFile(io.BytesIO(takeout_res.content)) as zf:
        namelist = zf.namelist()
        assert "courses.json" in namelist
        assert "coursework.json" in namelist
        assert "imsmanifest.xml" not in namelist
