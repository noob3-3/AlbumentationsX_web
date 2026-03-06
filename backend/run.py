#!/usr/bin/env python
"""
Start the FastAPI backend server
"""
import uvicorn
import sys
import os

# Add backend directory to Python path
sys.path.insert(0, os.path.dirname(__file__))

if __name__ == "__main__":
    from app.core.config import settings

    # Get worker count from environment variable (default: 4 for production, 1 for debug)
    workers = int(os.environ.get("WORKERS", 1 if settings.DEBUG else 4))

    # Note: Multiple workers are incompatible with --reload
    # WebSocket state should use Redis or external state management for multi-worker setup
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG and workers == 1,  # Only reload in debug mode with single worker
        log_level="debug" if settings.DEBUG else "info",
        workers=workers,
    )
