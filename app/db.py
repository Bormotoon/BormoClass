import sqlite3
from contextlib import contextmanager
from pathlib import Path
from app.config import settings

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DB_PATH, timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    return conn

@contextmanager
def db_session():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def _ensure_columns(conn: sqlite3.Connection, table: str, col_defs: dict[str, str]) -> None:
    existing_cols = {
        row["name"].lower()
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    for col_name, col_def in col_defs.items():
        if col_name.lower() not in existing_cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def};")

def run_migrations(conn: sqlite3.Connection) -> None:
    _ensure_columns(conn, "users", {
        "verified_teacher": "INTEGER NOT NULL DEFAULT 0",
        "account_disabled": "INTEGER NOT NULL DEFAULT 0",
        "org_unit_id": "INTEGER",
        "streak_days": "INTEGER NOT NULL DEFAULT 1",
        "last_active_day": "TEXT",
        "trial_used": "INTEGER NOT NULL DEFAULT 0",
        "pro_until": "INTEGER NOT NULL DEFAULT 0",
        "temp_pin_hash": "TEXT",
        "temp_pin_exp": "INTEGER DEFAULT 0",
    })

    _ensure_columns(conn, "classes", {
        "section": "TEXT NOT NULL DEFAULT ''",
        "description_heading": "TEXT NOT NULL DEFAULT ''",
        "description": "TEXT NOT NULL DEFAULT ''",
        "room": "TEXT NOT NULL DEFAULT ''",
        "levels": "TEXT NOT NULL DEFAULT ''",
        "course_state": "TEXT NOT NULL DEFAULT 'ACTIVE'",
        "enrollment_enabled": "INTEGER NOT NULL DEFAULT 1",
        "calendar_token": "TEXT NOT NULL DEFAULT ''",
        "teacher_folder_id": "TEXT",
        "theme_color": "TEXT NOT NULL DEFAULT '#f57300'",
        "banner_preset": "TEXT NOT NULL DEFAULT 'default'",
        "stream_post_mode": "TEXT NOT NULL DEFAULT 'STUDENTS_CAN_POST_AND_COMMENT'",
        "stream_work_mode": "TEXT NOT NULL DEFAULT 'SHOW_ATTACHMENTS_AND_DETAILS'",
        "show_deleted_items": "INTEGER NOT NULL DEFAULT 0",
        "grade_calc_type": "TEXT NOT NULL DEFAULT 'TOTAL_POINTS'",
        "grade_display_setting": "TEXT NOT NULL DEFAULT 'SHOW_OVERALL_GRADE'",
        "apply_periods_to_existing": "INTEGER NOT NULL DEFAULT 0",
        "updated_at": "INTEGER NOT NULL DEFAULT 0",
    })

    _ensure_columns(conn, "class_members", {
        "is_muted": "INTEGER NOT NULL DEFAULT 0",
        "enrollment_active": "INTEGER NOT NULL DEFAULT 1",
        "student_folder_id": "TEXT",
    })

    # Гарантия 152-ФЗ РФ и Zero-PII: удаление любых следов шифротекста заметок
    existing_cm_cols = {
        row["name"].lower()
        for row in conn.execute("PRAGMA table_info(class_members)").fetchall()
    }
    if "encrypted_note" in existing_cm_cols:
        conn.execute("ALTER TABLE class_members DROP COLUMN encrypted_note;")

    _ensure_columns(conn, "class_topics", {
        "updated_at": "INTEGER NOT NULL DEFAULT 0",
    })

    _ensure_columns(conn, "coursework", {
        "creator_user_id": "INTEGER",
        "creator_client_id": "TEXT NOT NULL DEFAULT 'first_party'",
        "work_type": "TEXT NOT NULL DEFAULT 'ASSIGNMENT'",
        "assignee_mode": "TEXT NOT NULL DEFAULT 'ALL_STUDENTS'",
        "modification_mode": "TEXT NOT NULL DEFAULT 'MODIFIABLE_UNTIL_TURNED_IN'",
        "grade_category_id": "INTEGER",
        "grading_period_id": "INTEGER",
        "choices_json": "TEXT NOT NULL DEFAULT '[]'",
        "peer_replies_enabled": "INTEGER NOT NULL DEFAULT 0",
        "show_class_summary": "INTEGER NOT NULL DEFAULT 1",
        "close_after_due": "INTEGER NOT NULL DEFAULT 0",
        "originality_enabled": "INTEGER NOT NULL DEFAULT 0",
        "reviewed_by_teacher": "INTEGER NOT NULL DEFAULT 0",
        "sort_order": "INTEGER NOT NULL DEFAULT 0",
        "updated_at": "INTEGER NOT NULL DEFAULT 0",
    })

    _ensure_columns(conn, "submissions", {
        "id": "INTEGER",
        "v1_state": "TEXT NOT NULL DEFAULT 'NEW'",
        "is_late": "INTEGER NOT NULL DEFAULT 0",
        "draft_grade": "REAL",
        "assigned_grade": "REAL",
        "draft_rubric_json": "TEXT NOT NULL DEFAULT '{}'",
        "assigned_rubric_json": "TEXT NOT NULL DEFAULT '{}'",
        "is_excused": "INTEGER NOT NULL DEFAULT 0",
        "mc_answer_text": "TEXT NOT NULL DEFAULT ''",
        "created_at": "INTEGER NOT NULL DEFAULT 0",
    })

def init_db() -> None:
    Path(settings.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with db_session() as conn:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA mmap_size = 268435456;")
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        run_migrations(conn)
