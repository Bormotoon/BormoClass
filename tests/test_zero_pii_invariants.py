from pathlib import Path
from app.db import init_db, db_session

FORBIDDEN_COLUMNS = {
    "full_name", "first_name", "last_name", "middle_name", "patronymic",
    "fio", "name", "email", "mail", "phone", "tel", "birth_year",
    "birth_date", "birthday", "gender", "sex", "ip", "ip_address", "passport"
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
