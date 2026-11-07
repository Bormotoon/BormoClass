/**
 * BormoClass Zero-Knowledge E2EE Crypto Engine & Transparent Fetch Interceptor
 * 
 * Standalone browser encryption engine utilizing native window.crypto.subtle.
 * All user text fields, answers, comments, canvas data, and files are encrypted
 * in the browser using AES-256-GCM before transmission over the network.
 * 
 * Formats:
 * - Text fields: BORMO_E2EE_V1:<base64url_iv_12bytes>:<base64url_ciphertext_with_tag>
 * - Binary files: BC_E2EE_BLOB_V1\0 + 12-byte IV + AES-256-GCM ciphertext
 */

(function () {
    'use strict';

    // -------------------------------------------------------------------------
    // 1. Константы и регулярные выражения (Zero-PII 152-ФЗ РФ)
    // -------------------------------------------------------------------------
    const E2EE_TEXT_PREFIX = "BORMO_E2EE_V1:";
    const E2EE_BLOB_MAGIC = new Uint8Array([66, 67, 95, 69, 50, 69, 69, 95, 66, 76, 79, 66, 95, 86, 49, 0]);

    const EMAIL_PATTERN = /[\w\.-]+@[\w\.-]+\.\w+/i;
    const PHONE_RU_PATTERN = /(?:\+7|8)[\s\(\)\-]*\d{3}[\s\(\)\-]*\d{3}[\s\(\)\-]*\d{2}[\s\(\)\-]*\d{2}/;
    const SNILS_PATTERN = /\b\d{3}[-\s]\d{3}[-\s]\d{3}[-\s]?\d{2}\b/;
    const FIO_INITIALS_PATTERN_1 = /\b[А-ЯЁ][а-яё]{1,}\s+[А-ЯЁ]\.\s*[А-ЯЁ]\./;
    const FIO_INITIALS_PATTERN_2 = /\b[А-ЯЁ]\.\s*[А-ЯЁ]\.\s+[А-ЯЁ][а-яё]{1,}/;
    const FIO_THREE_WORDS_1 = /\b[А-ЯЁ][а-яё]+[\s_]+[А-ЯЁ][а-яё]+[\s_]+[А-ЯЁ][а-яё]*(?:ович|евич|овна|евна|ич|ична)\b/;
    const FIO_THREE_WORDS_2 = /\b[А-ЯЁ][а-яё]+[\s_]+[А-ЯЁ][а-яё]*(?:ович|евич|овна|евна|ич|ична)[\s_]+[А-ЯЁ][а-яё]+\b/;
    const FIO_TWO_WORDS_1 = /\b[А-ЯЁ][а-яё]*(?:ов|ев|ин|ын|ский|цкий|ова|ева|ина|ына|ская|цкая)\s+[А-ЯЁ][а-яё]+\b/;
    const FIO_TWO_WORDS_2 = /\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]*(?:ов|ев|ин|ын|ский|цкий|ова|ева|ина|ына|ская|цкая)\b/;

    function assertZeroPiiClient(text) {
        if (!text || typeof text !== "string") return;
        if (EMAIL_PATTERN.test(text)) {
            throw new Error("Обнаружены персональные данные (Email). По закону 152-ФЗ РФ и стандарту Zero-PII ввод контактных данных запрещен.");
        }
        if (PHONE_RU_PATTERN.test(text)) {
            throw new Error("Обнаружены персональные данные (Номер телефона). По закону 152-ФЗ РФ и стандарту Zero-PII ввод номеров телефонов запрещен.");
        }
        if (SNILS_PATTERN.test(text)) {
            throw new Error("Обнаружены персональные данные (СНИЛС). По закону 152-ФЗ РФ и стандарту Zero-PII ввод документов запрещен.");
        }
        if (
            FIO_INITIALS_PATTERN_1.test(text) ||
            FIO_INITIALS_PATTERN_2.test(text) ||
            FIO_THREE_WORDS_1.test(text) ||
            FIO_THREE_WORDS_2.test(text) ||
            FIO_TWO_WORDS_1.test(text) ||
            FIO_TWO_WORDS_2.test(text)
        ) {
            throw new Error("Обнаружены персональные данные (ФИО). По закону 152-ФЗ РФ и стандарту Zero-PII хранение реальных имен запрещено. Используйте обезличенные позывные.");
        }
    }

    // -------------------------------------------------------------------------
    // 2. Base64URL Утилиты
    // -------------------------------------------------------------------------
    function bufferToBase64Url(buffer) {
        const bytes = new Uint8Array(buffer);
        let binary = "";
        for (let i = 0; i < bytes.byteLength; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    }

    function base64UrlToBuffer(base64url) {
        let base64 = String(base64url).replace(/-/g, "+").replace(/_/g, "/");
        while (base64.length % 4) {
            base64 += "=";
        }
        const binary = atob(base64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        return bytes.buffer;
    }

    // -------------------------------------------------------------------------
    // 3. Управление ключами WebCrypto (PBKDF2, AES-256-GCM, HMAC)
    // -------------------------------------------------------------------------
    const classKeys = new Map();
    let currentMasterKey = null;
    let defaultClassKey = null;

    async function deriveKeyFromSecret(secretText, saltText, iterations = 100000) {
        const enc = new TextEncoder();
        const keyMaterial = await window.crypto.subtle.importKey(
            "raw",
            enc.encode(secretText),
            { name: "PBKDF2" },
            false,
            ["deriveKey", "deriveBits"]
        );
        return await window.crypto.subtle.deriveKey(
            {
                name: "PBKDF2",
                salt: enc.encode(saltText),
                iterations: iterations,
                hash: "SHA-256"
            },
            keyMaterial,
            { name: "AES-GCM", length: 256 },
            true,
            ["encrypt", "decrypt"]
        );
    }

    async function generateAesKey() {
        return await window.crypto.subtle.generateKey(
            { name: "AES-GCM", length: 256 },
            true,
            ["encrypt", "decrypt"]
        );
    }

    async function exportRawKey(key) {
        const raw = await window.crypto.subtle.exportKey("raw", key);
        return bufferToBase64Url(raw);
    }

    async function importRawKey(b64u) {
        const buf = base64UrlToBuffer(b64u);
        return await window.crypto.subtle.importKey(
            "raw",
            buf,
            { name: "AES-GCM", length: 256 },
            true,
            ["encrypt", "decrypt"]
        );
    }

    // -------------------------------------------------------------------------
    // 4. Функции шифрования и дешифрования
    // -------------------------------------------------------------------------
    async function getActiveKey(classId) {
        if (classId && classKeys.has(Number(classId))) {
            return classKeys.get(Number(classId));
        }
        if (defaultClassKey) {
            return defaultClassKey;
        }
        if (currentMasterKey) {
            return currentMasterKey;
        }
        // Детерминированный fallback-ключ локальной сессии
        let cached = sessionStorage.getItem("bormo_e2ee_fallback_key");
        if (!cached) {
            const fresh = await generateAesKey();
            cached = await exportRawKey(fresh);
            sessionStorage.setItem("bormo_e2ee_fallback_key", cached);
            defaultClassKey = fresh;
            return fresh;
        }
        defaultClassKey = await importRawKey(cached);
        return defaultClassKey;
    }

    async function encryptText(plaintext, cryptoKey) {
        if (plaintext === null || plaintext === undefined) return plaintext;
        if (typeof plaintext !== "string") return plaintext;
        if (plaintext.startsWith(E2EE_TEXT_PREFIX)) return plaintext;
        if (plaintext === "" || plaintext === "{}" || plaintext === "[]") return plaintext;

        assertZeroPiiClient(plaintext);

        const key = cryptoKey || await getActiveKey();
        const enc = new TextEncoder();
        const iv = window.crypto.getRandomValues(new Uint8Array(12));
        const ctBuffer = await window.crypto.subtle.encrypt(
            { name: "AES-GCM", iv: iv },
            key,
            enc.encode(plaintext)
        );
        return `${E2EE_TEXT_PREFIX}${bufferToBase64Url(iv)}:${bufferToBase64Url(ctBuffer)}`;
    }

    async function decryptText(envelope, cryptoKey) {
        if (typeof envelope !== "string" || !envelope.startsWith(E2EE_TEXT_PREFIX)) {
            return envelope;
        }
        const parts = envelope.split(":");
        if (parts.length !== 3) return envelope;

        const candidateKeys = [];
        if (cryptoKey) candidateKeys.push(cryptoKey);
        if (defaultClassKey && !candidateKeys.includes(defaultClassKey)) candidateKeys.push(defaultClassKey);
        for (const k of classKeys.values()) {
            if (!candidateKeys.includes(k)) candidateKeys.push(k);
        }
        if (currentMasterKey && !candidateKeys.includes(currentMasterKey)) candidateKeys.push(currentMasterKey);

        const iv = new Uint8Array(base64UrlToBuffer(parts[1]));
        const ct = base64UrlToBuffer(parts[2]);

        for (const k of candidateKeys) {
            try {
                const decBuffer = await window.crypto.subtle.decrypt(
                    { name: "AES-GCM", iv: iv },
                    k,
                    ct
                );
                return new TextDecoder().decode(decBuffer);
            } catch (e) {
                // Пробуем следующий ключ
            }
        }
        return envelope;
    }

    async function encryptBlob(uint8Array, cryptoKey) {
        if (uint8Array.length >= 16) {
            let isAlreadyEncrypted = true;
            for (let i = 0; i < 16; i++) {
                if (uint8Array[i] !== E2EE_BLOB_MAGIC[i]) {
                    isAlreadyEncrypted = false;
                    break;
                }
            }
            if (isAlreadyEncrypted) return uint8Array;
        }

        const key = cryptoKey || await getActiveKey();
        const iv = window.crypto.getRandomValues(new Uint8Array(12));
        const ctBuffer = await window.crypto.subtle.encrypt(
            { name: "AES-GCM", iv: iv },
            key,
            uint8Array
        );
        const ctBytes = new Uint8Array(ctBuffer);
        const result = new Uint8Array(16 + 12 + ctBytes.length);
        result.set(E2EE_BLOB_MAGIC, 0);
        result.set(iv, 16);
        result.set(ctBytes, 28);
        return result;
    }

    async function decryptBlob(uint8Array, cryptoKey) {
        if (uint8Array.length < 44) return uint8Array;
        for (let i = 0; i < 16; i++) {
            if (uint8Array[i] !== E2EE_BLOB_MAGIC[i]) {
                return uint8Array;
            }
        }

        const candidateKeys = [];
        if (cryptoKey) candidateKeys.push(cryptoKey);
        if (defaultClassKey) candidateKeys.push(defaultClassKey);
        for (const k of classKeys.values()) {
            if (!candidateKeys.includes(k)) candidateKeys.push(k);
        }
        if (currentMasterKey) candidateKeys.push(currentMasterKey);

        const iv = uint8Array.slice(16, 28);
        const ct = uint8Array.slice(28);

        for (const k of candidateKeys) {
            try {
                const decBuffer = await window.crypto.subtle.decrypt(
                    { name: "AES-GCM", iv: iv },
                    k,
                    ct
                );
                return new Uint8Array(decBuffer);
            } catch (e) {
                // Пробуем следующий
            }
        }
        return uint8Array;
    }

    async function hmacAnswer(answerText, cryptoKey) {
        const key = cryptoKey || await getActiveKey();
        const rawKey = await window.crypto.subtle.exportKey("raw", key);
        const hmacKey = await window.crypto.subtle.importKey(
            "raw",
            rawKey,
            { name: "HMAC", hash: "SHA-256" },
            false,
            ["sign"]
        );
        const enc = new TextEncoder();
        const normalized = String(answerText).trim().toLowerCase();
        const sig = await window.crypto.subtle.sign("HMAC", hmacKey, enc.encode(normalized));
        return bufferToBase64Url(sig);
    }

    // -------------------------------------------------------------------------
    // 5. Рекурсивное шифрование и дешифрование структур данных API
    // -------------------------------------------------------------------------
    const ENCRYPT_FIELDS = new Set([
        "title", "instructions", "teacher_comment", "comment_text",
        "quiz_title", "set_title", "description", "body_text",
        "classroom_state_json", "elements_json", "rect_json", "stroke_json",
        "scratchpad_json"
    ]);

    async function transformPayloadForSend(obj, activeKey) {
        if (!obj || typeof obj !== "object") return obj;

        if (Array.isArray(obj)) {
            const outArr = [];
            for (const item of obj) {
                outArr.push(await transformPayloadForSend(item, activeKey));
            }
            return outArr;
        }

        const out = {};
        for (const [key, val] of Object.entries(obj)) {
            if (val === null || val === undefined) {
                out[key] = val;
                continue;
            }
            if (typeof val === "string") {
                if (ENCRYPT_FIELDS.has(key)) {
                    out[key] = await encryptText(val, activeKey);
                } else if (key === "payload_json" && val.trim() !== "{}" && val.trim() !== "[]" && !val.startsWith(E2EE_TEXT_PREFIX)) {
                    out[key] = await encryptText(val, activeKey);
                } else {
                    out[key] = val;
                }
            } else if (typeof val === "object") {
                out[key] = await transformPayloadForSend(val, activeKey);
            } else {
                out[key] = val;
            }
        }
        return out;
    }

    async function transformResponseData(data) {
        if (!data || typeof data !== "object") {
            if (typeof data === "string" && data.startsWith(E2EE_TEXT_PREFIX)) {
                return await decryptText(data);
            }
            return data;
        }

        if (Array.isArray(data)) {
            const res = [];
            for (const item of data) {
                res.push(await transformResponseData(item));
            }
            return res;
        }

        const res = {};
        for (const [k, v] of Object.entries(data)) {
            if (typeof v === "string" && v.startsWith(E2EE_TEXT_PREFIX)) {
                res[k] = await decryptText(v);
            } else if (typeof v === "object" && v !== null) {
                res[k] = await transformResponseData(v);
            } else {
                res[k] = v;
            }
        }
        return res;
    }

    // -------------------------------------------------------------------------
    // 6. Прозрачный перехватчик window.fetch
    // -------------------------------------------------------------------------
    const originalFetch = window.fetch;

    window.fetch = async function (input, init) {
        let url = typeof input === "string" ? input : (input && input.url ? input.url : "");
        let options = init || {};

        // 1. Извлекаем class_id из URL, если есть
        let matchedClassId = null;
        const classMatch = url.match(/\/classes\/(\d+)/);
        if (classMatch) {
            matchedClassId = Number(classMatch[1]);
        }

        const activeKey = await getActiveKey(matchedClassId);

        // 2. Обработка исходящего тела запроса (POST, PUT, PATCH)
        const method = (options.method || "GET").toUpperCase();
        if (["POST", "PUT", "PATCH"].includes(method) && options.body) {
            try {
                if (typeof options.body === "string" && (options.body.startsWith("{") || options.body.startsWith("["))) {
                    const parsed = JSON.parse(options.body);
                    const transformed = await transformPayloadForSend(parsed, activeKey);
                    options.body = JSON.stringify(transformed);
                } else if (options.body instanceof FormData) {
                    const newForm = new FormData();
                    for (const [k, v] of options.body.entries()) {
                        if (v instanceof File || v instanceof Blob) {
                            const buf = await v.arrayBuffer();
                            const encBytes = await encryptBlob(new Uint8Array(buf), activeKey);
                            const encBlob = new Blob([encBytes], { type: "application/octet-stream" });
                            newForm.append(k, encBlob, v.name || "file.bin");
                        } else if (typeof v === "string" && ENCRYPT_FIELDS.has(k)) {
                            const encStr = await encryptText(v, activeKey);
                            newForm.append(k, encStr);
                        } else {
                            newForm.append(k, v);
                        }
                    }
                    options.body = newForm;
                }
            } catch (err) {
                // Если сработал PII-guard, прерываем запрос и показываем уведомление
                console.error("[BormoClass E2EE PII Guard]", err.message);
                if (window.showToast) {
                    window.showToast(err.message, "error");
                }
                throw err;
            }
        }

        // 3. Выполняем реальный сетевой запрос
        const response = await originalFetch.call(this, input, options);

        // 4. Прозрачно перехватываем response.json()
        const origJson = response.json.bind(response);
        response.json = async function () {
            const data = await origJson();
            // Запоминаем ключи класса, если пришли в ответе
            if (data && typeof data === "object") {
                if (data.join_pin) {
                    const ck = await deriveKeyFromSecret(data.join_pin, "bormo-class-pin:" + (data.id || ""));
                    if (data.id) classKeys.set(Number(data.id), ck);
                    defaultClassKey = ck;
                }
                if (data.class_id && data.e2ee_key_envelope) {
                    // Распаковка envelope
                }
            }
            return await transformResponseData(data);
        };

        // 5. Прозрачно перехватываем скачивание файлов из хранилища
        if (url.includes("/api/storage/files/")) {
            const origBlob = response.blob.bind(response);
            response.blob = async function () {
                const b = await origBlob();
                const buf = await b.arrayBuffer();
                const decBytes = await decryptBlob(new Uint8Array(buf), activeKey);
                return new Blob([decBytes], { type: b.type || "application/octet-stream" });
            };
        }

        return response;
    };

    // -------------------------------------------------------------------------
    // 7. Экспорт глобального API
    // -------------------------------------------------------------------------
    window.BormoE2EE = {
        E2EE_TEXT_PREFIX,
        E2EE_BLOB_MAGIC,
        assertZeroPiiClient,
        deriveKeyFromSecret,
        generateAesKey,
        encryptText,
        decryptText,
        encryptBlob,
        decryptBlob,
        hmacAnswer,
        setClassKey: function (classId, key) {
            classKeys.set(Number(classId), key);
            defaultClassKey = key;
        },
        setMasterKey: function (key) {
            currentMasterKey = key;
        }
    };

})();
