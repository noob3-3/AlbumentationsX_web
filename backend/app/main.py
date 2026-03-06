"""
FastAPI Application Entry Point
AlbumentationsX + Ultralytics Training Platform
"""
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

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

    yield

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
    app.mount("/assets", StaticFiles(directory=str(static_path / "assets")), name="assets")

    @app.get("/", include_in_schema=False)
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(request: Request, full_path: str = ""):
        """Catch-all: serve index.html for Vue Router (SPA fallback)"""
        # Skip API and WebSocket routes
        if full_path.startswith(("api/", "ws/", "docs", "redoc", "openapi")):
            from fastapi import HTTPException
            raise HTTPException(status_code=404)
        index = static_path / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"message": settings.APP_NAME, "docs": "/docs"}

else:
    @app.get("/", tags=["health"])
    async def root():
        return {"message": settings.APP_NAME, "docs": "/docs"}
