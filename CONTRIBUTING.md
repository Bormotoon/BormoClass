# Contributing to BormoClass

Thank you for your interest in contributing to **BormoClass** — the self-hosted, open-source alternative to Google Classroom with an integrated offline whiteboard and autonomous Zero-PII privacy architecture! We welcome bug reports, feature suggestions, architectural improvements, and code contributions from educators, developers, and security researchers worldwide.

---

## 🧭 Core Principles & Constraints

When contributing to BormoClass, all changes must strictly adhere to our non-negotiable architectural invariants:

1. **Strict Zero-PII (152-FZ RF & International Privacy Standards):**
   - The server, databases, cookies, and server logs must **never** store, process, or transmit personally identifiable information (Full Name, email, phone numbers, SNILS, birth dates, physical addresses, or raw IP addresses).
   - Any student identification must strictly use the procedural callsign system (`Adjective-Noun-Code`) and 4-word recovery phrases.
   - Any sensitive freeform teacher or student content must be client-side encrypted via WebCrypto (`BORMO_E2EE_V1:` or `BC_E2EE_BLOB_V1`).
   - Server-side regex filters in `app/passport/pii_guard.py` must never be weakened or bypassed.

2. **Zero External CDN & Zero-Bloat:**
   - 100% of frontend assets, fonts, stylesheets (Material Design 3 *Ember Newsroom* palette), and scripts must be served locally.
   - External CDN links (`unpkg.com`, `cdnjs.com`, `fonts.googleapis.com`, etc.) are strictly prohibited.
   - The interactive whiteboard (`board-src/` and `app/static/board/`) must remain 100% offline-capable with zero outbound tracking calls.

3. **High Reliability & Minimal Footprint:**
   - Single-process Python 3.12+ FastAPI backend with non-blocking SQLite in WAL (`Write-Ahead Logging`) mode.
   - CAS (Content-Addressable Storage) blob storage with SHA-256 deduplication.

---

## 🛠️ Development Setup

### Prerequisites
- Python 3.12+ (or 3.13)
- Node.js 20+ (only required if rebuilding the Excalidraw whiteboard bundle in `board-src/`)
- Git

### 1. Clone & Setup Virtual Environment
```bash
git clone https://github.com/Bormotoon/BormoClass.git
cd BormoClass

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest pytest-asyncio httpx
```

### 2. Run the Development Server
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```
Navigate to `http://127.0.0.1:8010/` in your browser.

### 3. Run Test Suite
```bash
pytest -v
```

---

## 📐 Pull Request Workflow

1. Fork the repository and create your feature branch from `main`:
   ```bash
   git checkout -b feature/my-new-feature
   ```
2. Write clean, self-documenting code with Python type annotations.
3. Ensure existing tests pass and write new tests covering your additions in `tests/`.
4. Run the Zero-PII verification check: ensure your changes introduce no PII logging or storage.
5. Commit your changes with clear, descriptive commit messages:
   ```bash
   git commit -m "feat(classroom): add multi-group assignment filtering"
   ```
6. Push to your branch and submit a Pull Request to `main`.

---

## 📜 Code of Conduct
Please be respectful, collaborative, and considerate of students, teachers, and developers of all backgrounds. Discriminatory, abusive, or exclusionary behavior will not be tolerated.

---

## 📄 License
By contributing to BormoClass, you agree that your contributions will be licensed under the **Apache License 2.0**.
