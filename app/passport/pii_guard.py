import base64
import json
import os
import re
from typing import Optional, Any
from fastapi import HTTPException
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Регулярные выражения для детекции ПД (152-ФЗ РФ — Zero-PII)
EMAIL_PATTERN = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+', re.IGNORECASE)
PHONE_RU_PATTERN = re.compile(r'(?:\+7|8)[\s\(\)\-]*\d{3}[\s\(\)\-]*\d{3}[\s\(\)\-]*\d{2}[\s\(\)\-]*\d{2}')
SNILS_PATTERN = re.compile(r'\b\d{3}[-\s]\d{3}[-\s]\d{3}[-\s]?\d{2}\b')

# Паттерны ФИО: "Иванов И.И.", "И.И. Иванов"
FIO_INITIALS_PATTERN_1 = re.compile(r'\b[А-ЯЁ][а-яё]{1,}\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.')
FIO_INITIALS_PATTERN_2 = re.compile(r'\b[А-ЯЁ]\.\s*[А-ЯЁ]\.\s+[А-ЯЁ][а-яё]{1,}')

# Три слова с заглавной буквы с отчеством: "Иванов Иван Иванович" или "Иван Иванович Иванов"
PATRONYMIC_SUFFIXES = r'(?:ович|евич|овна|евна|ич|ична)'
FIO_THREE_WORDS_1 = re.compile(rf'\b[А-ЯЁ][а-яё]+[\s_]+[А-ЯЁ][а-яё]+[\s_]+[А-ЯЁ][а-яё]*{PATRONYMIC_SUFFIXES}\b')
FIO_THREE_WORDS_2 = re.compile(rf'\b[А-ЯЁ][а-яё]+[\s_]+[А-ЯЁ][а-яё]*{PATRONYMIC_SUFFIXES}[\s_]+[А-ЯЁ][а-яё]+\b')

# Двусловные имена/фамилии: "Смирнов Дмитрий", "Дмитрий Смирнов"
SURNAME_SUFFIXES = r'(?:ов|ев|ин|ын|ский|цкий|ова|ева|ина|ына|ская|цкая)'
FIO_TWO_WORDS_1 = re.compile(rf'\b[А-ЯЁ][а-яё]*{SURNAME_SUFFIXES}\s+[А-ЯЁ][а-яё]+\b')
FIO_TWO_WORDS_2 = re.compile(rf'\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]*{SURNAME_SUFFIXES}\b')

def assert_zero_pii_text(text: Optional[str]) -> None:
    """
    Проверяет строку на отсутствие персональных данных (email, телефоны РФ, СНИЛС, ФИО).
    При обнаружении любого признака ПД выбрасывает HTTPException(422).
    """
    if not text or not isinstance(text, str):
        return

    # 1. Email
    if EMAIL_PATTERN.search(text):
        raise HTTPException(
            status_code=422,
            detail="Обнаружены персональные данные (Email). По закону 152-ФЗ РФ и стандарту Zero-PII ввод контактных данных запрещен."
        )

    # 2. Номер телефона РФ (+7 / 8 ...)
    if PHONE_RU_PATTERN.search(text):
        raise HTTPException(
            status_code=422,
            detail="Обнаружены персональные данные (Номер телефона). По закону 152-ФЗ РФ и стандарту Zero-PII ввод номеров телефонов запрещен."
        )

    # 3. СНИЛС
    if SNILS_PATTERN.search(text):
        raise HTTPException(
            status_code=422,
            detail="Обнаружены персональные данные (СНИЛС). По закону 152-ФЗ РФ и стандарту Zero-PII ввод документов запрещен."
        )

    # 4. ФИО (Инициалы, полное тройное имя с отчеством или пара Фамилия/Имя)
    if (
        FIO_INITIALS_PATTERN_1.search(text)
        or FIO_INITIALS_PATTERN_2.search(text)
        or FIO_THREE_WORDS_1.search(text)
        or FIO_THREE_WORDS_2.search(text)
        or FIO_TWO_WORDS_1.search(text)
        or FIO_TWO_WORDS_2.search(text)
    ):
        raise HTTPException(
            status_code=422,
            detail="Обнаружены персональные данные (ФИО). По закону 152-ФЗ РФ и стандарту Zero-PII хранение реальных имен запрещено. Используйте обезличенные позывные."
        )

# Константы формата E2EE (Zero-Knowledge)
E2EE_TEXT_PREFIX = "BORMO_E2EE_V1:"
E2EE_BLOB_MAGIC = b"BC_E2EE_BLOB_V1\x00"

def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

def _unb64u(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)

def is_e2ee_envelope(text: Any) -> bool:
    """
    Проверяет, что строка имеет формат:
    BORMO_E2EE_V1:<base64url_iv_12bytes>:<base64url_ciphertext_with_tag>
    """
    if not isinstance(text, str) or not text.startswith(E2EE_TEXT_PREFIX):
        return False
    parts = text.split(":")
    if len(parts) != 3:
        return False
    try:
        iv = _unb64u(parts[1])
        if len(iv) != 12:
            return False
        ct = _unb64u(parts[2])
        if len(ct) < 16:
            return False
        return True
    except Exception:
        return False

def assert_e2ee_text(text: Optional[str], field_label: str = "Данные", allow_empty: bool = True) -> None:
    """
    Проверяет строковое поле на наличие клиентского шифрования BORMO_E2EE_V1.
    Если строка пустая и allow_empty=True, пропускает.
    Если строка НЕ начинается с BORMO_E2EE_V1:
      1. Сначала вызывает assert_zero_pii_text(text) для точной диагностики по 152-ФЗ.
      2. Затем выбрасывает 422: Все пользовательские данные должны быть зашифрованы на клиенте (BORMO_E2EE_V1).
    """
    if text is None:
        if allow_empty:
            return
        raise HTTPException(status_code=422, detail="Все пользовательские данные должны быть зашифрованы на клиенте (BORMO_E2EE_V1)")
    if not isinstance(text, str):
        return
    s = text.strip()
    if s == "" or s in ("{}", "[]"):
        if allow_empty:
            return
        raise HTTPException(status_code=422, detail="Все пользовательские данные должны быть зашифрованы на клиенте (BORMO_E2EE_V1)")
    if is_e2ee_envelope(text):
        return
    # Невалидный конверт шифротекста:
    # 1. Проверка на ПД (152-ФЗ)
    assert_zero_pii_text(text)
    # 2. Требование E2EE-шифрования
    raise HTTPException(
        status_code=422,
        detail="Все пользовательские данные должны быть зашифрованы на клиенте (BORMO_E2EE_V1)"
    )

def assert_e2ee_blob(data: bytes) -> None:
    """
    Проверяет бинарные данные файла или холста на наличие E2EE-заголовка BC_E2EE_BLOB_V1\\x00.
    Длина должна быть не менее: 16 (magic) + 12 (IV) + 16 (GCM tag) = 44 байта.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise HTTPException(
            status_code=422,
            detail="Загружаемый файл или холст должен быть зашифрован в браузере (BC_E2EE_BLOB_V1). Хранение незашифрованных файлов на сервере запрещено."
        )
    if not data.startswith(E2EE_BLOB_MAGIC) or len(data) < 16 + 12 + 16:
        raise HTTPException(
            status_code=422,
            detail="Загружаемый файл или холст должен быть зашифрован в браузере (BC_E2EE_BLOB_V1). Хранение незашифрованных файлов на сервере запрещено."
        )

def e2ee_encrypt_text_helper(plaintext: str, key: bytes) -> str:
    """Вспомогательная функция (для тестов и SDK) шифрования строки в BORMO_E2EE_V1."""
    if len(key) != 32:
        key = (key * 32)[:32]
    aesgcm = AESGCM(key)
    iv = os.urandom(12)
    ct = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)
    return f"{E2EE_TEXT_PREFIX}{_b64u(iv)}:{_b64u(ct)}"

def e2ee_decrypt_text_helper(envelope: str, key: bytes) -> str:
    """Вспомогательная функция (для тестов и SDK) дешифрования строки из BORMO_E2EE_V1."""
    if not isinstance(envelope, str) or not envelope.startswith(E2EE_TEXT_PREFIX):
        return envelope
    parts = envelope.split(":")
    if len(parts) != 3:
        return envelope
    if len(key) != 32:
        key = (key * 32)[:32]
    aesgcm = AESGCM(key)
    iv = _unb64u(parts[1])
    ct = _unb64u(parts[2])
    return aesgcm.decrypt(iv, ct, None).decode("utf-8")

def e2ee_encrypt_blob_helper(data: bytes, key: bytes) -> bytes:
    """Вспомогательная функция (для тестов и SDK) шифрования файла в BC_E2EE_BLOB_V1."""
    if len(key) != 32:
        key = (key * 32)[:32]
    aesgcm = AESGCM(key)
    iv = os.urandom(12)
    ct = aesgcm.encrypt(iv, data, None)
    return E2EE_BLOB_MAGIC + iv + ct

def e2ee_decrypt_blob_helper(blob: bytes, key: bytes) -> bytes:
    """Вспомогательная функция (для тестов и SDK) дешифрования файла из BC_E2EE_BLOB_V1."""
    if not isinstance(blob, (bytes, bytearray)) or not blob.startswith(E2EE_BLOB_MAGIC):
        return blob
    if len(key) != 32:
        key = (key * 32)[:32]
    aesgcm = AESGCM(key)
    iv = blob[16:28]
    ct = blob[28:]
    return aesgcm.decrypt(iv, ct, None)
