import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
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

STATIC_DIR = Path(__file__).parent / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Инициализация базы данных и персистентных WAL-прагм
    init_db()
    # Привязка текущего event loop к SSE-хабу
    sse_hub.set_loop(asyncio.get_running_loop())
    yield

app = FastAPI(
    title="BormoClass",
    description="Автономная платформа управления школьным классом (Zero-PII, 152-ФЗ РФ)",
    version="1.0.0",
    lifespan=lifespan
)

# Подключение мидлвари Pedobraz-Passport
app.add_middleware(PassportMiddleware)

# Подключение роутеров API
app.include_router(passport_router)
app.include_router(classes_router)
app.include_router(coursework_router)
app.include_router(submissions_router)
app.include_router(global_router)
app.include_router(board_router)

# Раздача статики
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.api_route("/", methods=["GET", "HEAD"], response_class=FileResponse)
def index_page():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse("<h1>BormoClass</h1><p>Интерфейс инициализируется...</p>")

@app.api_route("/board/{class_id}", methods=["GET", "HEAD"], response_class=FileResponse)
def board_page(class_id: int):
    board_file = STATIC_DIR / "board.html"
    if board_file.exists():
        return FileResponse(board_file)
    return HTMLResponse("<h1>Интерактивная доска</h1><p>Доска загружается...</p>")
