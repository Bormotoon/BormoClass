import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import init_db, db_session
import app.v1.schemas as schemas_mod
from app.v1.protocol import (
    api_error,
    parse_update_mask,
    apply_fields_selector,
    encode_page_token,
    decode_page_token,
    resolve_user_id,
    resolve_class_id,
    ts_to_rfc3339,
    rfc3339_to_ts,
    GoogleAPIException
)

@pytest.fixture(scope="module")
def client():
    init_db()
    return TestClient(app)

def test_105_methods_contract_discovery():
    """Контрактная проверка: все 105 HTTP-методов из classroom_v1.json зарегистрированы в приложении."""
    disc_path = Path("docs/google_classroom/discovery/classroom_v1.json")
    assert disc_path.exists(), "Файл discovery classroom_v1.json должен существовать"
    with open(disc_path, encoding="utf-8") as f:
        disc = json.load(f)

    discovery_methods = []
    def walk(res):
        if "methods" in res:
            for m_name, m_val in res["methods"].items():
                p = m_val.get("flatPath") or m_val["path"]
                discovery_methods.append((m_val["id"], m_val["httpMethod"], p))
        if "resources" in res:
            for r_name, r_val in res["resources"].items():
                walk(r_val)
    walk(disc)

    assert len(discovery_methods) == 105, f"Ожидалось ровно 105 методов, получено {len(discovery_methods)}"

    # Сбор всех зарегистрированных эндпоинтов в приложении (включая вложенные роутеры)
    def walk_routes(r_list):
        res = []
        for r in r_list:
            if hasattr(r, "original_router"):
                res.extend(walk_routes(r.original_router.routes))
            elif hasattr(r, "routes"):
                res.extend(walk_routes(r.routes))
            else:
                res.append(r)
        return res

    all_endpoints = walk_routes(app.routes)
    app_routes = set()
    for ep in all_endpoints:
        path = getattr(ep, "path", "").lstrip("/")
        methods = getattr(ep, "methods", set())
        for m in methods:
            app_routes.add((m, path))

    missing = []
    for m_id, http_m, path in discovery_methods:
        norm_path = path.replace("{+", "{")
        if (http_m, norm_path) not in app_routes:
            missing.append((m_id, http_m, norm_path))

    assert not missing, f"Отсутствуют следующие методы ({len(missing)} шт.): {missing}"

def test_85_schemas_contract_discovery():
    """Контрактная проверка: все 85 Pydantic-схем из discovery объявлены в app/v1/schemas.py."""
    disc_path = Path("docs/google_classroom/discovery/classroom_v1.json")
    with open(disc_path, encoding="utf-8") as f:
        disc = json.load(f)

    disc_schemas = disc["schemas"]
    assert len(disc_schemas) == 85, f"В discovery должно быть 85 схем, получено {len(disc_schemas)}"

    missing = [s for s in disc_schemas if not hasattr(schemas_mod, s)]
    assert not missing, f"В schemas.py отсутствуют следующие схемы: {missing}"

def test_protocol_update_mask_validation():
    allowed = {"name", "description", "course_state", "room"}

    # Корректная маска camelCase -> snake_case
    res = parse_update_mask("name,courseState,room", allowed)
    assert res == {"name", "course_state", "room"}

    # Пустая маска вызывает 400
    with pytest.raises(GoogleAPIException) as exc1:
        parse_update_mask("", allowed)
    assert exc1.value.status_code == 400
    assert exc1.value.status_str == "INVALID_ARGUMENT"

    # Недопустимое поле вызывает 400
    with pytest.raises(GoogleAPIException) as exc2:
        parse_update_mask("name,forbiddenField", allowed)
    assert exc2.value.status_code == 400
    assert "Недопустимое поле" in exc2.value.error_message

def test_protocol_fields_selector():
    data = {
        "id": "123",
        "name": "Алгебра",
        "ownerId": "456",
        "materials": [{"title": "Учебник", "type": "pdf"}]
    }

    # Пустой или * возвращает полный объект
    assert apply_fields_selector(data, None) == data
    assert apply_fields_selector(data, "*") == data

    # Выборка id,name
    filtered = apply_fields_selector(data, "id,name")
    assert filtered == {"id": "123", "name": "Алгебра"}

    # Вложенная выборка
    nested_data = {"course": data, "nextPageToken": "tok1"}
    nested_filtered = apply_fields_selector(nested_data, "course(id,name),nextPageToken")
    assert nested_filtered == {
        "course": {"id": "123", "name": "Алгебра"},
        "nextPageToken": "tok1"
    }

def test_protocol_signed_page_token():
    fp = "course_10_students"
    token = encode_page_token(30, fp)
    assert isinstance(token, str) and len(token) > 0

    # Корректное декодирование
    offset = decode_page_token(token, fp)
    assert offset == 30

    # Нулевой токен возвращает offset 0
    assert decode_page_token(None, fp) == 0

    # Несовпадающий fingerprint фильтров вызывает 400
    with pytest.raises(GoogleAPIException) as exc:
        decode_page_token(token, "other_filter_fp")
    assert exc.value.status_code == 400
    assert "pageToken" in exc.value.error_message

    # Поддельный токен вызывает 400
    with pytest.raises(GoogleAPIException):
        decode_page_token("invalid.token.here", fp)

def test_protocol_resolvers_and_dates():
    init_db()
    with db_session() as conn:
        # Резолвинг пользователя
        user_row = conn.execute("SELECT id, handle FROM users LIMIT 1").fetchone()
        if user_row:
            uid = user_row["id"]
            handle = user_row["handle"]
            assert resolve_user_id(conn, "me", {"id": uid}) == uid
            assert resolve_user_id(conn, str(uid), {"id": 999}) == uid
            assert resolve_user_id(conn, handle, {"id": 999}) == uid
            assert resolve_user_id(conn, "-", {"id": uid}, allow_wildcard=True) == "-"

        # Резолвинг несуществующего пользователя -> 404
        with pytest.raises(GoogleAPIException) as exc:
            resolve_user_id(conn, "non_existent_999999", {"id": 1})
        assert exc.value.status_code == 404

    # Проверка RFC3339 дат
    ts = 1762512000
    rfc = ts_to_rfc3339(ts)
    assert "T" in rfc and rfc.endswith("Z")
    assert rfc3339_to_ts(rfc) == ts
