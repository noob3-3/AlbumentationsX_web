"""
Logging configuration
"""
import logging
import sys
from pathlib import Path
from loguru import logger

from app.core.config import settings


def setup_logging():
    """Configure loguru logger"""
    log_file = settings.LOG_DIR / "app.log"

    # Remove default handler
    logger.remove()

    # Console handler
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="DEBUG" if settings.DEBUG else "INFO",
        colorize=True,
    )

    # File handler：按日切割，超过 2 个月自动删除
    logger.add(
        str(settings.LOG_DIR / "app_{time:YYYY-MM-DD}.log"),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="INFO",
        rotation="00:00",
        retention="2 months",
        compression="zip",
        encoding="utf-8",
    )

    return logger
