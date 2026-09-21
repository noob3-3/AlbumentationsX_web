"""
FastAPI Application Entry Point
AlbumentationsX + Ultralytics Training Platform
"""
import asyncio
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from starlette.types import Scope


def _ensure_static_mimetypes() -> None:
    """Windows 注册表常把 .js 标成 text/plain，ES module 会被浏览器拒绝。"""
    for ext, mime in (
        (".js", "application/javascript"),
        (".mjs", "application/javascript"),
        (".css", "text/css"),
        (".wasm", "application/wasm"),
        (".json", "application/json"),
        (".svg", "image/svg+xml"),
        (".map", "application/json"),
        (".woff", "font/woff"),
        (".woff2", "font/woff2"),
    ):
        mimetypes.add_type(mime, ext)


_ensure_static_mimetypes()


_ASSET_MIME = {
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".css": "text/css",
    ".wasm": "application/wasm",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".html": "text/html",
    ".map": "application/json",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".ico": "image/x-icon",
}


def _media_type(path: Path) -> str:
    return _ASSET_MIME.get(path.suffix.lower()) or mimetypes.guess_type(str(path))[0] or "application/octet-stream"


class AssetStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        guessed = _ASSET_MIME.get(Path(path).suffix.lower())
        if guessed:
            response.headers["content-type"] = guessed
        return response

from app.core.config import settings
from app.core.database import init_db
from app.core.logging import setup_logging
from app.core.websocket import ws_manager
from app.api import api_router, ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    setup_logging()
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    await init_db()
    logger.info("Database initialized")

    # Initialize WebSocket manager with Redis
    await ws_manager.initialize(settings.REDIS_URL, settings.REDIS_WS_CHANNEL)

    # Initialize training queue manager
    from app.services.training_queue import training_queue
    await training_queue.start()
    logger.info("Training queue manager started")

    # DDP 模式下 callback 不执行，轮询 results.csv 同步进度
    from app.services.training_progress_poller import run_progress_poller
    poller_task = asyncio.create_task(run_progress_poller(interval_sec=8.0))

    yield

    # 停止进度轮询
    poller_task.cancel()
    try:
        await poller_task
    except asyncio.CancelledError:
        pass

    # Shutdown training queue manager
    await training_queue.stop()
    logger.info("Training queue manager stopped")

    # Shutdown WebSocket manager
    await ws_manager.shutdown()
    logger.info("Application shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## AlbumentationsX Training Platform

Automated pipeline for:
- 📁 **Data Collection**: Upload local files or collect from URLs/remote clients
- 🔄 **Data Augmentation**: Automated augmentation using AlbumentationsX
- 🤖 **Model Training**: YOLO object detection training via Ultralytics
- 📊 **Real-time Monitoring**: WebSocket-based training progress

### Client API
Remote clients can push images using the `/api/v1/collect/` endpoints with `X-Api-Token` header.
""",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(api_router)
app.include_router(ws_router)  # WebSocket (no /api/v1 prefix)


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "version": settings.APP_VERSION}


# ── Serve built Vue frontend ───────────────────────────────────
# Activated when STATIC_DIR env var points to the Vite /dist directory.
# All non-API, non-WS requests fall through to index.html (SPA routing).
if settings.STATIC_DIR and Path(settings.STATIC_DIR).exists():
    static_path = Path(settings.STATIC_DIR)

    # Serve static assets (js/css/images) at root
    assets_dir = static_path / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", AssetStaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/", include_in_schema=False)
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(request: Request, full_path: str = ""):
        """Catch-all: serve real files with correct MIME, else index.html (SPA)."""
        if full_path.startswith(("api/", "ws/", "docs", "redoc", "openapi")):
            from fastapi import HTTPException
            raise HTTPException(status_code=404)
        root = static_path.resolve()
        if full_path:
            candidate = (static_path / full_path).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                from fastapi import HTTPException
                raise HTTPException(status_code=404)
            if candidate.is_file():
                return FileResponse(str(candidate), media_type=_media_type(candidate))
        index = static_path / "index.html"
        if index.exists():
            return FileResponse(str(index), media_type="text/html")
        return {"message": settings.APP_NAME, "docs": "/docs"}

else:
    @app.get("/", tags=["health"])
    async def root():
        return {"message": settings.APP_NAME, "docs": "/docs"}
