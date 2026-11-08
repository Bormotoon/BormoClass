# Security Policy

## 🛡️ Zero-PII & Threat Model Commitments

**BormoClass** is a self-hosted, open-source alternative to Google Classroom architected around a Zero-Trust, Zero-PII threat model designed to comply with Russian Federal Law **152-FZ** (Personal Data Protection) and strict international data privacy standards.

The core security invariants are:
1. **0 Bytes of PII on Server**: The backend database (SQLite WAL), server logs, caching layers, and HTTP headers never store real student names, emails, phone numbers, Russian national IDs (SNILS, Passport numbers), or location data.
2. **Client-Side End-to-End Encryption (E2EE)**: Sensitive texts, annotations, student assignment files, and whiteboard canvas payloads are encrypted in the user's browser using standard WebCrypto **AES-256-GCM + ECDH P-256** before hitting the server.
3. **No External CDN or Remote Code Execution**: All JavaScript libraries, CSS, fonts, and SVG icons are strictly self-hosted to prevent supply-chain attacks and CDN-based tracking.
4. **Rate Limiting & Anti-Bruteforce**: Password verification, callsign lookups, and session issuance are guarded with PBKDF2/scrypt, tokenized anti-bot tickets, and strict sliding-window rate limiters.

---

## 🔒 Supported Versions

Only the latest release on the `main` branch is actively supported with security updates.

| Version | Supported |
| :--- | :--- |
| `main` (v1.x) | :white_check_mark: |
| `< 1.0` | :x: |

---

## 🚨 Reporting a Vulnerability

If you discover a security vulnerability or a violation of our Zero-PII invariants (e.g., unintended PII leakage, cryptographic flaws, IDOR vulnerabilities, or authentication bypasses):

1. **Do NOT report the issue publicly on GitHub Issues or Discussions.**
2. Send a detailed report via encrypted email or GitHub Security Advisory:
   - **Email:** `security@pedobraz.ru` (or maintainer contact at `bormotoon@gmail.com`)
   - Include a step-by-step reproduction guide, sample payloads, and an assessment of the impact.
3. Maintainers will acknowledge receipt within 48 hours and provide a timeline for triage and remediation.
4. Coordinated disclosure: We ask you to allow up to 30 days for a fix to be tested and deployed before publishing details.
