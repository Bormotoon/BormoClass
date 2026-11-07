import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import init_db
from app.passport.crypto import issue_ticket, check_ticket, normalize_code, format_code, code_checksum
from app.passport.dictionaries import ADJECTIVES, NOUNS, RECOVERY_WORDS

@pytest.fixture(scope="module")
def client():
    init_db()
    return TestClient(app)

def test_passport_static_and_cardgen_pages(client):
    # 1. Страница-генератор карточек /passport/
    resp = client.get("/passport")
    assert resp.status_code == 200
    assert "Создать Паспорт" in resp.text
    assert "cardFront" in resp.text
    assert "cardBack" in resp.text
    assert "exportPassCanvas" in resp.text

    resp_slash = client.get("/passport/")
    assert resp_slash.status_code == 200

    # 2. Раздача клиентской библиотеки /pb-passport.js
    resp_js = client.get("/pb-passport.js")
    assert resp_js.status_code == 200
    assert "application/javascript" in resp_js.headers.get("content-type", "")
    assert "heroOf" in resp_js.text
    assert "avatarSvg" in resp_js.text

    # 3. Раздача портретов и индекса рас /passport/portraits/index.json
    resp_portraits = client.get("/passport/portraits/index.json")
    assert resp_portraits.status_code == 200
    pdata = resp_portraits.json()
    assert "races" in pdata
    assert "human" in pdata["races"]
    assert "elf" in pdata["races"]

def test_passport_tickets_and_roll_handle(client):
    # 1. Получение криптографического талона без капчи
    t_resp = client.get("/api/passport/ticket")
    assert t_resp.status_code == 200
    ticket = t_resp.json().get("ticket")
    assert ticket and "." in ticket

    # 2. Барабан вариантов позывного
    r_resp = client.get("/api/passport/roll-handle")
    assert r_resp.status_code == 200
    r_data = r_resp.json()
    assert "options" in r_data
    assert len(r_data["options"]) == 5
    for opt in r_data["options"]:
        assert "handle" in opt
        assert "avatar_seed" in opt
        parts = opt["handle"].split("-")
        assert len(parts) == 3
        assert parts[0] in ADJECTIVES
        assert parts[1] in NOUNS

def test_passport_registration_with_cardgen_handle(client):
    # Регистрация с позывным, собранным барабаном страницы /passport/
    roll_resp = client.get("/api/passport/roll-handle").json()
    chosen_handle = roll_resp["options"][0]["handle"]
    ticket = roll_resp["ticket"]

    reg_resp = client.post("/api/passport/register", json={
        "handle": chosen_handle,
        "role": "student",
        "password": "validCardGenPass123",
        "ticket": ticket
    })
    assert reg_resp.status_code == 200
    data = reg_resp.json()
    assert data["user"]["handle"] == chosen_handle
    assert len(data["recovery_words"]) == 4
    for w in data["recovery_words"]:
        assert w in RECOVERY_WORDS

    # Повторная попытка зарегистрировать тот же позывной -> 409
    dup_resp = client.post("/api/passport/register", json={
        "handle": chosen_handle,
        "role": "student",
        "password": "anotherPassword999"
    })
    assert dup_resp.status_code == 409

def test_passport_activation_codes():
    body = "PED-26-ABCD-EFGH"
    cs = code_checksum(body)
    assert len(cs) == 2
    full = f"{body}-{cs}"
    norm = normalize_code(full)
    assert norm == full
    assert normalize_code("invalid-code") is None
