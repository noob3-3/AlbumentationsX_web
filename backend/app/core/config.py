"""
Application configuration settings
"""
import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AlbumentationsX Training Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS - 内网使用，允许所有源
    ALLOWED_ORIGINS: List[str] = ["*"]

    # Paths
    BASE_DIR: Path = Path(__file__).parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    UPLOAD_DIR: Path = DATA_DIR / "uploads"
    DATASET_DIR: Path = DATA_DIR / "datasets"
    AUGMENTED_DIR: Path = DATA_DIR / "augmented"
    MODEL_DIR: Path = DATA_DIR / "models"
    EXPORT_DIR: Path = DATA_DIR / "exports"
    LOG_DIR: Path = BASE_DIR / "logs"

    # Upload
    MAX_UPLOAD_SIZE: int = 100 * 1024 * 1024  # 100MB per file
    ALLOWED_IMAGE_EXTENSIONS: List[str] = [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"]

    # Request limits
    MAX_REQUEST_SIZE: int = 2 * 1024 * 1024 * 1024  # 2GB total request size for batch upload
    UPLOAD_TIMEOUT: int = 600  # 10 minutes timeout for upload operations

    # Database
    DATABASE_URL: str = "sqlite:///./data/app.db"

    # Training defaults
    DEFAULT_EPOCHS: int = 100
    DEFAULT_BATCH_SIZE: int = 16
    DEFAULT_IMG_SIZE: int = 640
    DEFAULT_MODEL: str = "yolo11n.pt"

    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30

    # Redis (for multi-process WebSocket message broadcasting)
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_WS_CHANNEL: str = "websocket:messages"

    # Static frontend files (set to /app/static in Docker)
    STATIC_DIR: str = ""

    # Client API token (for remote data collection client)
    CLIENT_API_TOKEN: str = "your-secret-token-change-this"

    class Config:
        env_file = ".env"
        extra = "allow"

    def create_dirs(self):
        """Create all required directories"""
        for d in [
            self.UPLOAD_DIR,
            self.DATASET_DIR,
            self.AUGMENTED_DIR,
            self.MODEL_DIR,
            self.EXPORT_DIR,
            self.LOG_DIR,
        ]:
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.create_dirs()

# 配置 Ultralytics 使用持久化目录作为缓存
# 这样可以避免每次容器重启都重新下载模型
os.environ['YOLO_CONFIG_DIR'] = str(settings.MODEL_DIR)
# 设置 Ultralytics 的权重下载目录
os.environ['TORCH_HOME'] = str(settings.MODEL_DIR / '.torch')

# 初始化 Ultralytics Settings.yaml 配置文件
# 这会在 MODEL_DIR 下创建 settings.yaml 文件来配置 Ultralytics 行为
try:
    from app.utils.ultralytics_config import setup_ultralytics_config
    setup_ultralytics_config(
        model_dir=settings.MODEL_DIR,
        dataset_dir=settings.DATASET_DIR,
        enable_integrations=False  # 关闭第三方集成以避免不必要的网络请求
    )
except Exception as e:
    # 如果设置失败，不影响应用启动（非关键功能）
    import warnings
    warnings.warn(f"Failed to initialize Ultralytics config: {e}")


