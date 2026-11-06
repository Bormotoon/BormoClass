import time
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from app.db import init_db, db_session
from app.passport.router import router as passport_router
from app.passport.middleware import PassportMiddleware
from app.passport.generator import (
    create_unique_callsign,
    generate_recovery_words,
    hash_secret,
    verify_secret
)
from app.passport.crypto_cookie import (
    sign_cookie_payload,
    verify_cookie_token,
    compute_user_ad_free
)

@pytest.fixture(scope="module")
def app():
    init_db()
    test_app = FastAPI()
    test_app.add_middleware(PassportMiddleware)
    test_app.include_router(passport_router)
    return test_app

@pytest.fixture(scope="module")
def client(app):
    return TestClient(app)

def test_generator_callsign_and_secrets():
    init_db()
    with db_session() as conn:
        callsign1 = create_unique_callsign(conn)
        callsign2 = create_unique_callsign(conn)
        assert callsign1 != ""
        assert "-" in callsign1
        assert len(callsign1.split("-")) == 3

    words = generate_recovery_words(4)
    assert len(words) == 4
    for w in words:
        assert isinstance(w, str) and len(w) > 0

    secret = "MyP@ssword123"
    hashed = hash_secret(secret)
    assert "$" in hashed
    salt, hex_hash = hashed.split("$", 1)
    assert len(salt) == 32  # 16 bytes hex
    assert len(hex_hash) == 64  # sha256 hex
    assert verify_secret(secret, hashed)
    assert not verify_secret("WrongPassword", hashed)

def test_cookie_signing_and_verification():
    payload = {"user_id": 42, "role": "teacher", "handle": "Смелый-Барс-777", "ad_free": True}
    token = sign_cookie_payload(payload)
    assert "." in token
    decoded = verify_cookie_token(token)
    assert decoded is not None
    assert decoded["user_id"] == 42
    assert decoded["role"] == "teacher"
    assert decoded["handle"] == "Смелый-Барс-777"
    assert decoded["ad_free"] is True

    # Tampered token
    tampered = token[:-4] + "abcd"
    assert verify_cookie_token(tampered) is None

def test_register_login_recover_flow(client):
    # 1. Register student
    reg_resp = client.post("/api/passport/register", json={"role": "student", "password": "supersecretpassword"})
    assert reg_resp.status_code == 200, reg_resp.text
    data = reg_resp.json()
    assert "user" in data
    assert "recovery_words" in data
    assert len(data["recovery_words"]) == 4
    student_handle = data["user"]["handle"]
    student_id = data["user"]["id"]
    recovery_words = data["recovery_words"]

    # Cookie must be set
    assert "pb_pass" in reg_resp.cookies

    # 2. Check /me
    me_resp = client.get("/api/passport/me")
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["user"]["handle"] == student_handle
    assert me_data["user"]["role"] == "student"

    # 3. Logout
    logout_resp = client.post("/api/passport/logout")
    assert logout_resp.status_code == 200

    # 4. Login with correct password
    login_resp = client.post("/api/passport/login", json={"handle": student_handle, "password": "supersecretpassword"})
    assert login_resp.status_code == 200
    assert login_resp.json()["user"]["id"] == student_id

    # 5. Login with wrong password
    bad_login = client.post("/api/passport/login", json={"handle": student_handle, "password": "wrong"})
    assert bad_login.status_code == 401

    # 6. Password recovery using 4 words
    rec_resp = client.post("/api/passport/recover", json={
        "handle": student_handle,
        "recovery_words": recovery_words,
        "new_password": "brandnewpassword99"
    })
    assert rec_resp.status_code == 200

    # 7. Login with new password
    new_login = client.post("/api/passport/login", json={"handle": student_handle, "password": "brandnewpassword99"})
    assert new_login.status_code == 200

def test_idempotent_solve_and_anti_farm(client):
    # Register a new student
    reg = client.post("/api/passport/register", json={"role": "student", "password": "password123"})
    assert reg.status_code == 200
    initial_recess = reg.json()["user"]["recess_seconds"]

    # First solve of task "task-abc-1"
    solve1 = client.post("/api/passport/solve", json={"task_id": "task-abc-1", "score": 90})
    assert solve1.status_code == 200
    d1 = solve1.json()
    assert d1["ok"] is True
    assert d1["awarded_recess"] is True
    assert d1["recess_seconds"] == initial_recess + 300
    assert d1["grade_five"] == 5

    # Second solve of same task (anti-farm check)
    solve2 = client.post("/api/passport/solve", json={"task_id": "task-abc-1", "score": 100})
    assert solve2.status_code == 200
    d2 = solve2.json()
    assert d2["ok"] is True
    assert d2["awarded_recess"] is False  # Must NOT be awarded again!
    assert d2["recess_seconds"] == initial_recess + 300  # Balance remains unchanged

def test_teacher_trial_and_license_code(client):
    # Register teacher
    reg = client.post("/api/passport/register", json={"role": "teacher", "password": "teacherpass123"})
    assert reg.status_code == 200
    assert reg.json()["ad_free"] is False

    # Activate trial
    trial_resp = client.post("/api/passport/trial")
    assert trial_resp.status_code == 200
    assert trial_resp.json()["ad_free"] is True
    assert trial_resp.json()["trial_used"] == 1
    assert "X-Passport-Trial-Started" in trial_resp.headers

    # Second trial attempt should fail
    trial2 = client.post("/api/passport/trial")
    assert trial2.status_code == 400

    # Test license code activation
    from manage_codes import generate_code_string
    test_code = generate_code_string()
    now = int(time.time())
    with db_session() as conn:
        conn.execute(
            "INSERT INTO license_keys (code, tariff, duration_days, created_at) VALUES (?, 'month', 30, ?)",
            (test_code, now)
        )

    act_resp = client.post("/api/passport/activate-code", json={"code": test_code})
    assert act_resp.status_code == 200
    assert act_resp.json()["ad_free"] is True

    # Reusing the same code should fail
    act_resp2 = client.post("/api/passport/activate-code", json={"code": test_code})
    assert act_resp2.status_code == 400
