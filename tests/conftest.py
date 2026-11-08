import json
from typing import Any
import pytest
from fastapi.testclient import TestClient

from app.passport.pii_guard import (
    EMAIL_PATTERN,
    PHONE_RU_PATTERN,
    SNILS_PATTERN,
    FIO_INITIALS_PATTERN_1,
    FIO_INITIALS_PATTERN_2,
    FIO_THREE_WORDS_1,
    FIO_THREE_WORDS_2,
    FIO_TWO_WORDS_1,
    FIO_TWO_WORDS_2,
    E2EE_TEXT_PREFIX,
    E2EE_BLOB_MAGIC,
    e2ee_encrypt_text_helper,
    e2ee_decrypt_text_helper,
    e2ee_encrypt_blob_helper,
    e2ee_decrypt_blob_helper
)

TEST_E2EE_KEY = b"BORMO_TEST_AES_256_GCM_KEY_32B_!"

ENCRYPT_FIELDS = {
    "title", "instructions", "teacher_comment", "comment_text",
    "quiz_title", "set_title", "description", "classroom_state_json",
    "elements_json", "rect_json", "stroke_json", "scratchpad_json"
}

def has_pii(text: str) -> bool:
    if not isinstance(text, str):
        return False
    return bool(
        EMAIL_PATTERN.search(text) or
        PHONE_RU_PATTERN.search(text) or
        SNILS_PATTERN.search(text) or
        FIO_INITIALS_PATTERN_1.search(text) or
        FIO_INITIALS_PATTERN_2.search(text) or
        FIO_THREE_WORDS_1.search(text) or
        FIO_THREE_WORDS_2.search(text) or
        FIO_TWO_WORDS_1.search(text) or
        FIO_TWO_WORDS_2.search(text)
    )

def encrypt_payload(data: Any) -> Any:
    if isinstance(data, dict):
        new_d = {}
        for k, v in data.items():
            if isinstance(v, str):
                if k in ENCRYPT_FIELDS or (k == "payload_json" and v.strip() not in ("{}", "[]")):
                    if has_pii(v) or v.startswith(E2EE_TEXT_PREFIX) or v.strip() == "":
                        new_d[k] = v
                    else:
                        new_d[k] = e2ee_encrypt_text_helper(v, TEST_E2EE_KEY)
                elif k == "body_text" and not has_pii(v) and not v.startswith(E2EE_TEXT_PREFIX) and not v.startswith("🟢") and not v.startswith("🟡") and not v.startswith("🔴") and not v.startswith("✅"):
                    new_d[k] = e2ee_encrypt_text_helper(v, TEST_E2EE_KEY)
                else:
                    new_d[k] = v
            elif isinstance(v, (dict, list)):
                new_d[k] = encrypt_payload(v)
            else:
                new_d[k] = v
        return new_d
    elif isinstance(data, list):
        return [encrypt_payload(item) for item in data]
    return data

def decrypt_payload(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: decrypt_payload(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [decrypt_payload(item) for item in data]
    elif isinstance(data, str) and data.startswith(E2EE_TEXT_PREFIX):
        return e2ee_decrypt_text_helper(data, TEST_E2EE_KEY)
    return data

# Monkeypatch TestClient.request for transparent E2EE testing
_orig_request = TestClient.request

def _e2ee_request(self, method: str, url: str, **kwargs):
    headers = kwargs.get("headers") or {}
    skip_e2ee = headers.get("X-Skip-E2EE") == "1"

    if not skip_e2ee:
        # 1. Шифрование JSON
        if "json" in kwargs and kwargs["json"] is not None:
            kwargs["json"] = encrypt_payload(kwargs["json"])

        # 2. Шифрование файлов
        if "files" in kwargs and kwargs["files"] is not None:
            files = kwargs["files"]
            if isinstance(files, dict):
                new_files = {}
                for fk, fval in files.items():
                    if isinstance(fval, tuple) and len(fval) >= 2:
                        fname, fcontent = fval[0], fval[1]
                        mtype = fval[2] if len(fval) > 2 else "application/octet-stream"
                        if isinstance(fcontent, bytes) and not fcontent.startswith(E2EE_BLOB_MAGIC):
                            enc_content = e2ee_encrypt_blob_helper(fcontent, TEST_E2EE_KEY)
                            new_files[fk] = (fname, enc_content, mtype)
                        else:
                            new_files[fk] = fval
                    else:
                        new_files[fk] = fval
                kwargs["files"] = new_files

    response = _orig_request(self, method, url, **kwargs)

    if not skip_e2ee:
        orig_json = response.json
        def _decrypted_json(**jkwargs):
            raw = orig_json(**jkwargs)
            return decrypt_payload(raw)
        response.json = _decrypted_json

    return response

TestClient.request = _e2ee_request
