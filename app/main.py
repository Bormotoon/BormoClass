import asyncio
from typing import Optional
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import init_db
from app.classroom.sse_hub import sse_hub
from app.passport.middleware import PassportMiddleware
from app.passport.router import router as passport_router
from app.classroom.router_classes import router as classes_router
from app.classroom.router_coursework import router as coursework_router
from app.classroom.router_submissions import router as submissions_router
from app.classroom.router_global import router as global_router
from app.classroom.router_board import router as board_router
from app.classroom.router_comments import router as comments_router
from app.classroom.router_quizzes_and_sets import router as quizzes_router
from app.classroom.router_notifications_admin import router as notif_admin_router
from app.storage import storage_router
from app.worker.scheduler import run_background_scheduler
from app.v1 import v1_router
from app.v1.protocol import GoogleAPIException

STATIC_DIR = Path(__file__).parent / "static"

FIELD_LABELS = {
    "join_pin": "Пин-код класса",
    "seat_number": "Номер парты",
    "password": "Пароль",
    "handle": "Позывной",
    "title": "Название",
    "subject_code": "Предмет",
    "grade_level": "Класс (параллель)",
    "quarter_goal": "Цель на четверть",
    "recovery_words": "Слова восстановления",
    "new_password": "Новый пароль",
    "score": "Баллы",
    "seconds": "Секунды перемены",
    "duration_minutes": "Длительность блокировки",
    "kind": "Тип задания",
    "instructions": "Инструкция к заданию",
    "max_points": "Максимальный балл",
    "recess_reward": "Награда секундами",
    "topic_id": "Тема",
    "encrypted_note": "Заметка",
    "is_present": "Присутствие",
    "traffic_light": "Светофор понимания",
    "payload_json": "Ответ ученика",
    "grade_five": "Оценка",
    "teacher_comment": "Комментарий учителя",
}

def _format_validation_error(err: dict) -> str:
    loc = err.get("loc", [])
    field_name = loc[-1] if loc else "Поле"
    human_field = FIELD_LABELS.get(field_name, str(field_name))
    err_type = err.get("type", "")
    ctx = err.get("ctx", {})

    if field_name == "join_pin":
        return "Пин-код класса должен содержать от 4 до 10 символов (например, 5-значный номер с доски: 42819)."
    if field_name == "seat_number":
        return "Номер парты должен быть числом от 1 до 40."
    if field_name == "password":
        return "Пароль должен содержать от 4 до 128 символов."
    if field_name == "handle":
        return "Позывной должен быть указан корректно (например, «Бодрый-Енот-428»)."
    if field_name == "grade_level":
        return "Параллель класса должна быть числом от 1 до 11."
    if field_name == "title":
        return "Название должно содержать от 2 до 100 символов."
    if field_name == "grade_five":
        return "Школьная оценка должна быть от 2 до 5."
    if field_name == "recovery_words":
        return "Необходимо указать ровно 4 секретных слова восстановления."

    if "too_short" in err_type:
        min_len = ctx.get("min_length", "")
        return f"Поле «{human_field}»: значение слишком короткое (минимум {min_len} симв.)."
    if "too_long" in err_type:
        max_len = ctx.get("max_length", "")
        return f"Поле «{human_field}»: значение слишком длинное (максимум {max_len} симв.)."
    if "greater_than_equal" in err_type:
        ge = ctx.get("ge", "")
        return f"Поле «{human_field}»: значение должно быть не меньше {ge}."
    if "less_than_equal" in err_type:
        le = ctx.get("le", "")
        return f"Поле «{human_field}»: значение должно быть не больше {le}."
    if "missing" in err_type:
        return f"Обязательное поле «{human_field}» не заполнено."

    return f"Поле «{human_field}»: {err.get('msg', 'некорректный формат')}."

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Инициализация базы данных и персистентных WAL-прагм
    init_db()
    # Привязка текущего event loop к SSE-хабу
    sse_hub.set_loop(asyncio.get_running_loop())
    # Запуск фонового планировщика
    scheduler_task = asyncio.create_task(run_background_scheduler())
    try:
        yield
    finally:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass

app = FastAPI(
    title="BormoClass",
    description="Автономная платформа управления школьным классом (Zero-PII, 152-ФЗ РФ)",
    version="1.0.0",
    lifespan=lifespan
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    messages = [_format_validation_error(e) for e in errors]
    detail_msg = " \n".join(messages) if messages else "Неверный формат переданных данных."
    return JSONResponse(
        status_code=422,
        content={"detail": detail_msg, "errors": [e.get("msg", "") for e in errors]}
    )

@app.exception_handler(GoogleAPIException)
async def google_api_exception_handler(request: Request, exc: GoogleAPIException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.error_message, "error": exc.error_payload}
    )

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "frame-ancestors 'self'; base-uri 'self'; form-action 'self';"
    )
    return response

# Подключение мидлвари Pedobraz-Passport
app.add_middleware(PassportMiddleware)

# Подключение роутеров API
app.include_router(passport_router)
app.include_router(classes_router)
app.include_router(coursework_router)
app.include_router(submissions_router)
app.include_router(global_router)
app.include_router(board_router)
app.include_router(comments_router)
app.include_router(quizzes_router)
app.include_router(notif_admin_router)
app.include_router(storage_router)
app.include_router(v1_router)

# Раздача статики
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Раздача портретов персонажей Паспорта
PORTRAITS_DIR = STATIC_DIR / "passport" / "portraits"
if PORTRAITS_DIR.exists():
    app.mount("/passport/portraits", StaticFiles(directory=str(PORTRAITS_DIR)), name="passport_portraits")

@app.api_route("/favicon.ico", methods=["GET", "HEAD"])
def favicon():
    return Response(status_code=204)

@app.api_route("/pb-passport.js", methods=["GET", "HEAD"], response_class=FileResponse)
def pb_passport_script():
    script_file = STATIC_DIR / "js" / "pb-passport.js"
    if script_file.exists():
        return FileResponse(script_file, media_type="application/javascript")
    return HTMLResponse("", status_code=404)

@app.api_route("/passport", methods=["GET", "HEAD"], response_class=FileResponse)
@app.api_route("/passport/", methods=["GET", "HEAD"], response_class=FileResponse)
def passport_page():
    passport_file = STATIC_DIR / "passport" / "index.html"
    if passport_file.exists():
        return FileResponse(passport_file)
    return HTMLResponse("<h1>Паспорт BormoClass</h1><p>Генератор карточек инициализируется...</p>")

@app.api_route("/", methods=["GET", "HEAD"], response_class=FileResponse)
def index_page():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse("<h1>BormoClass</h1><p>Интерфейс инициализируется...</p>")

@app.api_route("/board", methods=["GET", "HEAD"], response_class=FileResponse)
@app.api_route("/board/{class_id}", methods=["GET", "HEAD"], response_class=FileResponse)
def board_page(class_id: Optional[int] = None):
    board_file = STATIC_DIR / "board" / "index.html"
    if not board_file.exists():
        board_file = STATIC_DIR / "board.html"
    if board_file.exists():
        return FileResponse(board_file)
    return HTMLResponse("<h1>Интерактивная доска</h1><p>Доска загружается...</p>")
