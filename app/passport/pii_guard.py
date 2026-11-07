import re
from typing import Optional
from fastapi import HTTPException

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
