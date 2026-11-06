#!/usr/bin/env python3
"""CLI-утилита генерации и управления ключами активации BormoClass (Zero-PII)."""

import argparse
import secrets
import string
import time
from app.db import init_db, db_session

DEV_CODES = [
    ("PED-26-DEV0-0001-1M", "month", 30),
    ("PED-26-DEV0-0002-1M", "month", 30),
    ("PED-26-DEV0-0003-1Y", "year", 365),
    ("PED-26-DEV0-0004-1Y", "year", 365),
    ("PED-26-TEST-PRO1-OK", "month", 30),
]

def generate_code_string() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # Без 0, 1, I, O для удобства чтения
    p1 = "".join(secrets.choice(alphabet) for _ in range(4))
    p2 = "".join(secrets.choice(alphabet) for _ in range(4))
    p3 = "".join(secrets.choice(alphabet) for _ in range(2))
    return f"PED-26-{p1}-{p2}-{p3}"

def seed_dev_codes() -> None:
    init_db()
    now = int(time.time())
    with db_session() as conn:
        for code, tariff, days in DEV_CODES:
            conn.execute("""
                INSERT OR IGNORE INTO license_keys (code, tariff, duration_days, created_at)
                VALUES (?, ?, ?, ?)
            """, (code, tariff, days, now))
    print("Dev-коды успешно добавлены в базу:")
    for code, tariff, days in DEV_CODES:
        print(f"  * {code} ({tariff}, {days} дн.)")

def generate_codes(count: int, tariff: str) -> None:
    init_db()
    days = 365 if tariff == "year" else 30
    now = int(time.time())
    created = []
    with db_session() as conn:
        for _ in range(count):
            while True:
                code = generate_code_string()
                row = conn.execute("SELECT 1 FROM license_keys WHERE code = ?", (code,)).fetchone()
                if not row:
                    break
            conn.execute("""
                INSERT INTO license_keys (code, tariff, duration_days, created_at)
                VALUES (?, ?, ?, ?)
            """, (code, tariff, days, now))
            created.append(code)
    print(f"Сгенерировано {count} кодов ({tariff}, {days} дн.):")
    for c in created:
        print(f"  {c}")

def list_codes() -> None:
    init_db()
    with db_session() as conn:
        rows = conn.execute("SELECT code, tariff, duration_days, used_by, used_at FROM license_keys").fetchall()
        if not rows:
            print("В базе нет ключей активации.")
            return
        print(f"{'Код':<24} | {'Тариф':<6} | {'Дней':<4} | {'Статус':<10}")
        print("-" * 55)
        for r in rows:
            status = f"Использован (User {r['used_by']})" if r["used_by"] else "Активен"
            print(f"{r['code']:<24} | {r['tariff']:<6} | {r['duration_days']:<4} | {status}")

def main():
    parser = argparse.ArgumentParser(description="Управление ключами активации BormoClass")
    parser.add_argument("--seed-dev-codes", action="store_true", help="Засеять тестовые dev-коды")
    parser.add_argument("--generate", type=int, default=0, help="Количество генерируемых кодов")
    parser.add_argument("--tariff", choices=["month", "year"], default="month", help="Тариф (month/year)")
    parser.add_argument("--list", action="store_true", help="Вывести все ключи")

    args = parser.parse_args()

    if args.seed_dev_codes:
        seed_dev_codes()
    elif args.generate > 0:
        generate_codes(args.generate, args.tariff)
    elif args.list:
        list_codes()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
