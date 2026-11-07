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

def test_guardians_and_digest(client):
    # Учитель и курс
    t_reg = client.post("/api/passport/register", json={"role": "teacher", "password": "guardTeachPass7"})
    t_handle = t_reg.json()["user"]["handle"]
    c_res = client.post("/v1/courses", json={"name": "6А Русский язык", "courseState": "ACTIVE"})
    course_id = c_res.json()["id"]

    # Ученик
    s_user = client.post("/api/passport/register", json={"role": "student", "password": "guardStudPass8"}).json()["user"]

    # Входим учителем для добавления ученика и инвайта опекуна
    client.post("/api/passport/login", json={"handle": t_handle, "password": "guardTeachPass7"})
    client.post(f"/v1/courses/{course_id}/students", json={"userId": str(s_user["id"])})

    # Учитель создает приглашение для опекуна (Zero-PII invite_target)
    inv_g = client.post(f"/v1/userProfiles/{s_user['id']}/guardianInvitations", json={"invitedEmailAddress": "parent_token_x42"})
    assert inv_g.status_code == 200
    inv_data = inv_g.json()
    assert inv_data["state"] == "PENDING"
    inv_id = inv_data["invitationId"]

    # Запрос сводки родителя (Zero-PII Guardian Digest)
    digest_res = client.get("/api/classroom/guardians/my-digest")
    assert digest_res.status_code == 200

def test_addons_and_grade_sync(client):
    # Учитель и курс
    t_reg = client.post("/api/passport/register", json={"role": "teacher", "password": "teachAddonPass10"})
    t_handle = t_reg.json()["user"]["handle"]
    c_res = client.post("/v1/courses", json={"name": "10А Физика", "courseState": "ACTIVE"})
    course_id = c_res.json()["id"]

    cw_res = client.post(f"/v1/courses/{course_id}/courseWork", json={
        "title": "Лабораторная: Закон Ома",
        "workType": "ASSIGNMENT",
        "maxPoints": 20,
        "state": "PUBLISHED"
    })
    cw_id = cw_res.json()["id"]

    # 1. Добавление Add-on attachment с gradeSyncEnabled = True
    addon_res = client.post(f"/v1/courses/{course_id}/courseWork/{cw_id}/addOnAttachments", json={
        "title": "Симулятор цепей PhET",
        "teacherViewUri": {"uri": "https://sim.local/teacher"},
        "studentViewUri": {"uri": "https://sim.local/student"},
        "maxPoints": 100,
        "gradeSyncEnabled": True
    })
    assert addon_res.status_code == 200
    addon_id = addon_res.json()["id"]

    # 2. Попытка добавить ВТОРОЕ вложение с gradeSyncEnabled = True отклоняется
    addon2_res = client.post(f"/v1/courses/{course_id}/courseWork/{cw_id}/addOnAttachments", json={
        "title": "Второй тренажер",
        "teacherViewUri": {"uri": "https://sim.local/teacher2"},
        "studentViewUri": {"uri": "https://sim.local/student2"},
        "maxPoints": 50,
        "gradeSyncEnabled": True
    })
    assert addon2_res.status_code in (400, 409, 412) # FAILED_PRECONDITION

    # 3. Синхронизация сдачи ученика (grade passback)
    s_user = client.post("/api/passport/register", json={"role": "student", "password": "studAddonPass11"}).json()["user"]
    # Входим как учитель и зачисляем ученика
    client.post("/api/passport/login", json={"handle": t_handle, "password": "teachAddonPass10"})
    client.post(f"/v1/courses/{course_id}/students", json={"userId": str(s_user["id"])})

    sub_list = client.get(f"/v1/courses/{course_id}/courseWork/{cw_id}/studentSubmissions").json()["studentSubmissions"]
    sub_id = sub_list[0]["id"]

    # Внешний тренажер передает 80/100 баллов -> должно смасштабироваться в (80/100)*20 = 16 баллов
    sync_res = client.patch(
        f"/v1/courses/{course_id}/courseWork/{cw_id}/addOnAttachments/{addon_id}/studentSubmissions/{sub_id}",
        json={"pointsEarned": 80}
    )
    assert sync_res.status_code == 200

def test_registrations_calendar_and_admin(client):
    # 1. Регистрация webhook push-подписки
    t_reg = client.post("/api/passport/register", json={"role": "teacher", "password": "teachRegPass12"})
    t_handle = t_reg.json()["user"]["handle"]
    c_res = client.post("/v1/courses", json={"name": "7А Химия", "courseState": "ACTIVE"})
    course_id = c_res.json()["id"]

    reg_res = client.post("/v1/registrations", json={
        "feed": {
            "feedType": "COURSE_WORK_CHANGES",
            "courseWorkChangesInfo": {"courseId": str(course_id)}
        },
        "cloudPubsubTopic": {"topicName": "https://webhook.local/push"}
    })
    assert reg_res.status_code == 200
    reg_id = reg_res.json()["registrationId"]

    # Удаление регистрации
    del_reg = client.delete(f"/v1/registrations/{reg_id}")
    assert del_reg.status_code == 200

    # 2. Экспорт Календаря в формате RFC 5545 iCalendar (.ics)
    with db_session() as conn:
        row = conn.execute("SELECT calendar_token FROM classes WHERE id = ?", (course_id,)).fetchone()
        cal_token = row["calendar_token"]
    ics_res = client.get(f"/api/classroom/calendar/{cal_token}.ics")
    assert ics_res.status_code == 200
    assert "BEGIN:VCALENDAR" in ics_res.text
    assert "END:VCALENDAR" in ics_res.text

    # 3. Админ-консоль: Data Takeout ZIP экспорт
    # Регистрируем пользователя и делаем его администратором в БД
    admin_reg = client.post("/api/passport/register", json={"role": "teacher", "password": "adminSecretPass13"}).json()["user"]
    with db_session() as conn:
        conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (admin_reg["id"],))
    client.post("/api/passport/login", json={"handle": admin_reg["handle"], "password": "adminSecretPass13"})

    takeout_res = client.get("/api/classroom/takeout.zip")
    assert takeout_res.status_code == 200
    assert takeout_res.headers["content-type"] in ("application/zip", "application/x-zip-compressed")

    # Проверяем содержимое ZIP архива на наличие манифеста IMS Common Cartridge
    with zipfile.ZipFile(io.BytesIO(takeout_res.content)) as zf:
        namelist = zf.namelist()
        assert "imsmanifest.xml" in namelist or any("course" in name for name in namelist)
