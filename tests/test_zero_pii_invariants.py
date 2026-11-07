from pathlib import Path
from app.db import init_db, db_session

FORBIDDEN_COLUMNS = {
    "full_name", "first_name", "last_name", "middle_name", "patronymic",
    "fio", "name", "email", "mail", "phone", "tel", "birth_year",
    "birth_date", "birthday", "gender", "sex", "ip", "ip_address", "passport",
    "encrypted_note"
}

FORBIDDEN_CDN_HOSTS = (
    "googleapis.com", "gstatic.com", "jsdelivr.net", "unpkg.com",
    "cdnjs.cloudflare.com", "stackpath.bootstrapcdn.com", "code.jquery.com"
)

def test_sqlite_schema_has_zero_pii_columns():
    init_db()
    with db_session() as conn:
        tables = [
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if not row["name"].startswith("sqlite_")
        ]
        assert len(tables) >= 9, "Должны быть созданы все 9 таблиц BormoClass"
        for table in tables:
            cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
            col_names = {c["name"].lower() for c in cols}
            violations = col_names.intersection(FORBIDDEN_COLUMNS)
            assert not violations, f"Нарушение 152-ФЗ (Zero-PII) в таблице {table}: найдены поля {violations}"

def test_static_files_have_zero_external_cdns():
    static_dir = Path(__file__).parent.parent / "app" / "static"
    if not static_dir.exists():
        return
    for path in static_dir.rglob("*"):
        if path.suffix in {".html", ".css", ".js"}:
            content = path.read_text(encoding="utf-8").lower()
            for host in FORBIDDEN_CDN_HOSTS:
                assert host not in content, f"Нарушение 152-ФЗ: внешний CDN {host} найден в {path.name}"

def test_zero_external_links_in_app():
    """Сканирование всех файлов app/ на отсутствие строк http:// и https:// (кроме http://www.w3.org/2000/svg для инлайновых SVG)."""
    app_dir = Path(__file__).parent.parent / "app"
    allowed_substring = "http://www.w3.org/2000/svg"

    for path in app_dir.rglob("*"):
        if not path.is_file():
            continue
        # Игнорируем кэш Python и прекомпилированные бандлы сторонних библиотек
        if "__pycache__" in path.parts or "assets" in path.parts or path.suffix in {".pyc", ".png", ".jpg", ".ico", ".woff2", ".ttf"}:
            continue
        if path.suffix in {".py", ".html", ".css", ".js", ".sql", ".sh", ".json", ".xml", ".webmanifest"}:
            content = path.read_text(encoding="utf-8", errors="ignore")
            sanitized = content.replace(allowed_substring, "")
            assert "http://" not in sanitized, f"Нарушение инварианта автономности: http:// найден в {path.relative_to(app_dir)}"
            assert "https://" not in sanitized, f"Нарушение инварианта автономности: https:// найден в {path.relative_to(app_dir)}"

def test_zero_pii_guards_and_filename_hashing():
    """
    Тест pii_guard.py, проверяющий, что попытка передать ФИО, телефон или email в задание,
    комментарий или импорт CSV блокируется кодом 422, а при загрузке файла с именем
    Иванов_Иван_8А.pdf в БД сохраняется только обезличенный хэш.
    """
    import pytest
    from fastapi.testclient import TestClient
    from fastapi import HTTPException
    from app.main import app
    from app.passport.pii_guard import assert_zero_pii_text

    # 1. Прямая проверка pii_guard.assert_zero_pii_text
    with pytest.raises(HTTPException) as exc:
        assert_zero_pii_text("Мой email: student@school.ru")
    assert exc.value.status_code == 422

    with pytest.raises(HTTPException) as exc:
        assert_zero_pii_text("Звоните +7 (999) 123-45-67")
    assert exc.value.status_code == 422

    with pytest.raises(HTTPException) as exc:
        assert_zero_pii_text("СНИЛС 123-456-789 00")
    assert exc.value.status_code == 422

    with pytest.raises(HTTPException) as exc:
        assert_zero_pii_text("Работу сдал Иванов Иван Иванович")
    assert exc.value.status_code == 422

    with pytest.raises(HTTPException) as exc:
        assert_zero_pii_text("Петров П.П.")
    assert exc.value.status_code == 422

    with pytest.raises(HTTPException) as exc:
        assert_zero_pii_text("Смирнов Дмитрий")
    assert exc.value.status_code == 422

    with pytest.raises(HTTPException) as exc:
        assert_zero_pii_text("Дмитрий Смирнов")
    assert exc.value.status_code == 422

    # 2. Интеграционная проверка через API
    client = TestClient(app)
    init_db()

    # Регистрация учителя
    t_reg = client.post("/api/passport/register", json={"role": "teacher", "password": "guardTestPass1"}).json()["user"]
    t_handle = t_reg["handle"]

    # Создание курса
    c_res = client.post("/api/classroom/classes", json={"title": "9А Алгебра", "subject_code": "mat", "grade_level": 9})
    class_id = c_res.json()["id"]

    # Попытка создать задание с ФИО -> 422
    cw_bad_fio = client.post(f"/api/classroom/classes/{class_id}/coursework", json={
        "title": "Домашнее задание для Иванов Иван Иванович",
        "instructions": "Сдать до пятницы",
        "max_points": 5
    })
    assert cw_bad_fio.status_code == 422

    # Попытка создать задание с телефоном -> 422
    cw_bad_tel = client.post(f"/api/classroom/classes/{class_id}/coursework", json={
        "title": "Задание",
        "instructions": "Вопросы по номеру 8-926-111-22-33",
        "max_points": 5
    })
    assert cw_bad_tel.status_code == 422

    # Попытка создать задание с email -> 422
    cw_bad_mail = client.post(f"/api/classroom/classes/{class_id}/coursework", json={
        "title": "Задание",
        "instructions": "Писать на teacher@school.edu",
        "max_points": 5
    })
    assert cw_bad_mail.status_code == 422

    # Успешное создание чистого задания
    cw_ok = client.post(f"/api/classroom/classes/{class_id}/coursework", json={
        "title": "Квадратные уравнения",
        "instructions": "Решить №12-15",
        "max_points": 5
    })
    assert cw_ok.status_code == 200
    cw_id = cw_ok.json()["id"]

    # Регистрация ученика
    s_reg = client.post("/api/passport/register", json={"role": "student", "password": "guardStudentPass2"}).json()["user"]
    s_handle = s_reg["handle"]

    # Вход учеником и добавление в класс
    join_pin = c_res.json()["join_pin"]
    client.post("/api/passport/login", json={"handle": s_handle, "password": "guardStudentPass2"})
    client.post("/api/classroom/classes/join", json={"join_pin": join_pin, "seat_number": 1})

    # Попытка ученика отправить свободный текст или ПД в комментарий -> 422
    comment_bad = client.post(f"/api/classroom/classes/{class_id}/comments", json={
        "parent_kind": "coursework",
        "parent_id": cw_id,
        "body_text": "Привет, меня зовут Петя Смирнов"
    })
    assert comment_bad.status_code == 422

    # Ученик может отправить только фразу из белого списка
    comment_ok = client.post(f"/api/classroom/classes/{class_id}/comments", json={
        "parent_kind": "coursework",
        "parent_id": cw_id,
        "body_text": "🟢 Всё понятно"
    })
    assert comment_ok.status_code == 200

    # Попытка админа импортировать CSV с ПД (ФИО или email) -> 422
    with db_session() as conn:
        conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (t_reg["id"],))
    client.post("/api/passport/login", json={"handle": t_handle, "password": "guardTestPass1"})

    csv_bad = "sourcedId,username,email,role\n101,ivanov,ivanov@school.ru,student"
    import_bad = client.post("/api/classroom/admin/import-oneroster", json={"users_csv": csv_bad})
    assert import_bad.status_code == 422

    # 3. Загрузка файла с именем Иванов_Иван_8А.pdf
    pdf_bytes = b"%PDF-1.4 mock pdf file content"
    files = {"file": ("Иванов_Иван_8А.pdf", pdf_bytes, "application/pdf")}
    upload_res = client.post("/api/storage/upload", files=files)
    assert upload_res.status_code == 200
    file_info = upload_res.json()
    file_id = file_info["id"]

    # Проверяем, что в БД сохранено ТОЛЬКО обезличенное имя вида Вложение #{sha256[:8]}.pdf
    with db_session() as conn:
        row = conn.execute("SELECT file_title FROM stored_files WHERE id = ?", (file_id,)).fetchone()
        assert row is not None
        title = row["file_title"]
        assert "Иванов" not in title
        assert "Иван" not in title
        assert "8А" not in title
        assert title.startswith("Вложение #")
        assert title.endswith(".pdf")

def test_no_client_side_vault_or_pii_storage():
    """
    Проверка полного отсутствия хранилища или сбора ПД:
    1. Файл webcrypto-vault.js удален.
    2. В исходниках app/ нет импортов TeacherZeroKnowledgeVault, plainStudentName или encrypted_note.
    """
    project_root = Path(__file__).parent.parent
    vault_file = project_root / "app" / "static" / "js" / "webcrypto-vault.js"
    assert not vault_file.exists(), f"Файл {vault_file} не должен существовать!"

    forbidden_tokens = ["TeacherZeroKnowledgeVault", "plainStudentName", "encrypted_note"]
    app_dir = project_root / "app"
    for path in app_dir.rglob("*"):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or "assets" in path.parts or path.suffix in {".pyc", ".png", ".woff2", ".ico"}:
            continue
        if path == project_root / "app" / "db.py":
            continue
        if path.suffix in {".py", ".js", ".html", ".sql"}:
            content = path.read_text(encoding="utf-8", errors="ignore")
            for token in forbidden_tokens:
                assert token not in content, f"Запрещенный PII-токен '{token}' найден в {path.relative_to(project_root)}"
