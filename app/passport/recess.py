import sqlite3
import time
from typing import Tuple

def is_recess_locked_for_student(conn: sqlite3.Connection, student_id: int) -> bool:
    now = int(time.time())
    row = conn.execute("""
        SELECT 1 
        FROM class_members cm
        JOIN classes c ON cm.class_id = c.id
        WHERE cm.student_id = ? AND c.recess_locked_until > ?
        LIMIT 1
    """, (student_id, now)).fetchone()
    return bool(row)

def spend_recess_seconds(conn: sqlite3.Connection, user_id: int, seconds: int) -> Tuple[bool, int, str]:
    if seconds <= 0:
        return False, 0, "Количество секунд должно быть больше нуля"

    # Проверяем роль
    user = conn.execute("SELECT role, recess_seconds FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return False, 0, "Пользователь не найден"

    if user["role"] == "student" and is_recess_locked_for_student(conn, user_id):
        return False, user["recess_seconds"], "Игры заблокированы на время контрольной"

    if user["recess_seconds"] < seconds:
        return False, user["recess_seconds"], "Недостаточно секунд на балансе"

    conn.execute(
        "UPDATE users SET recess_seconds = recess_seconds - ? WHERE id = ?",
        (seconds, user_id)
    )
    new_balance = user["recess_seconds"] - seconds
    return True, new_balance, "Секунды успешно списаны"

def award_recess_seconds(conn: sqlite3.Connection, user_id: int, seconds: int) -> int:
    if seconds <= 0:
        row = conn.execute("SELECT recess_seconds FROM users WHERE id = ?", (user_id,)).fetchone()
        return row["recess_seconds"] if row else 0

    conn.execute(
        "UPDATE users SET recess_seconds = recess_seconds + ? WHERE id = ?",
        (seconds, user_id)
    )
    row = conn.execute("SELECT recess_seconds FROM users WHERE id = ?", (user_id,)).fetchone()
    return row["recess_seconds"] if row else 0
