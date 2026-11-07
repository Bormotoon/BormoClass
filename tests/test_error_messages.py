import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import init_db

@pytest.fixture(scope="module")
def client():
    init_db()
    return TestClient(app)

def test_join_class_error_messages(client):
    # 1. Регистрация ученика
    reg_res = client.post("/api/passport/register", json={
        "role": "student",
        "password": "Password123"
    })
    assert reg_res.status_code == 200

    # 2. Передача слишком короткого пин-кода (3 символа)
    # Ожидаем 422 с понятным текстом на русском языке, без утечки [object Object]
    short_res = client.post("/api/classroom/classes/join", json={
        "join_pin": "123",
        "seat_number": 5
    })
    assert short_res.status_code == 422
    data_short = short_res.json()
    assert isinstance(data_short["detail"], str)
    assert "Пин-код класса должен содержать от 4 до 10 символов" in data_short["detail"]

    # 3. Передача несуществующего пин-кода (5 символов)
    # Ожидаем 404 с понятным информативным текстом
    not_found_res = client.post("/api/classroom/classes/join", json={
        "join_pin": "99999",
        "seat_number": 5
    })
    assert not_found_res.status_code == 404
    data_nf = not_found_res.json()
    assert isinstance(data_nf["detail"], str)
    assert "Класс с кодом подключения «99999» не найден" in data_nf["detail"]
    assert "интерактивной доске" in data_nf["detail"]

    # 4. Передача неверного номера парты (> 40)
    seat_res = client.post("/api/classroom/classes/join", json={
        "join_pin": "12345",
        "seat_number": 99
    })
    assert seat_res.status_code == 422
    data_seat = seat_res.json()
    assert isinstance(data_seat["detail"], str)
    assert "Номер парты должен быть числом от 1 до 40" in data_seat["detail"]
