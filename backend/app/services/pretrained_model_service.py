"""
Pretrained model service for downloading and managing Ultralytics official models
"""
import os
from pathlib import Path
from typing import List, Dict, Optional, Any
from loguru import logger
from ultralytics import YOLO

# Available Ultralytics pretrained models
PRETRAINED_MODELS = {
    # YOLO11 Detection models
    "yolo11n.pt": {
        "name": "YOLO11 Nano",
        "type": "detection",
        "size": "~6 MB",
        "description": "最小最快的YOLO11模型，适合快速推理",
        "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt"
    },
    "yolo11s.pt": {
        "name": "YOLO11 Small",
        "type": "detection",
        "size": "~20 MB",
        "description": "小型YOLO11模型，速度与精度平衡",
        "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s.pt"
    },
    "yolo11m.pt": {
        "name": "YOLO11 Medium",
        "type": "detection",
        "size": "~40 MB",
        "description": "中型YOLO11模型，较高精度",
        "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11m.pt"
    },
    "yolo11l.pt": {
        "name": "YOLO11 Large",
        "type": "detection",
        "size": "~50 MB",
        "description": "大型YOLO11模型，高精度",
        "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11l.pt"
    },
    "yolo11x.pt": {
        "name": "YOLO11 Extra Large",
        "type": "detection",
        "size": "~100 MB",
        "description": "超大型YOLO11模型，最高精度",
        "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11x.pt"
    },
    # YOLOv8 Detection models
    "yolov8n.pt": {
        "name": "YOLOv8 Nano",
        "type": "detection",
        "size": "~6 MB",
        "description": "YOLOv8最小模型，速度优先",
        "url": "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.pt"
    },
    "yolov8s.pt": {
        "name": "YOLOv8 Small",
        "type": "detection",
        "size": "~22 MB",
        "description": "YOLOv8小型模型，推荐使用",
        "url": "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8s.pt"
    },
    "yolov8m.pt": {
        "name": "YOLOv8 Medium",
        "type": "detection",
        "size": "~52 MB",
        "description": "YOLOv8中型模型",
        "url": "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8m.pt"
    },
}


class PretrainedModelService:
    """管理Ultralytics预训练模型"""

    @staticmethod
    def _find_model_in_cache(model_filename: str) -> Optional[Path]:
        """
        在Ultralytics缓存目录中查找模型文件

        Ultralytics默认缓存路径：
        - Linux/Mac: ~/.cache/ultralytics/
        - Windows: C:\\Users\\{user}\\.cache\\ultralytics\\ 或 AppData\\Roaming\\Ultralytics
        """
        # 可能的缓存目录
        cache_dirs = []

        # 1. 标准缓存目录 ~/.cache/ultralytics/
        home_dir = Path.home()
        cache_dirs.append(home_dir / ".cache" / "ultralytics")

        # 2. Windows AppData目录
        if os.name == 'nt':
            appdata = os.getenv('APPDATA')
            if appdata:
                cache_dirs.append(Path(appdata) / "Ultralytics")
            localappdata = os.getenv('LOCALAPPDATA')
            if localappdata:
                cache_dirs.append(Path(localappdata) / "Ultralytics")

        # 3. 环境变量指定的目录
        ultralytics_config = os.getenv('YOLO_CONFIG_DIR')
        if ultralytics_config:
            cache_dirs.append(Path(ultralytics_config))

        # 在各个可能的目录中查找
        for cache_dir in cache_dirs:
            if not cache_dir.exists():
                continue

            # 检查直接路径
            model_path = cache_dir / model_filename
            if model_path.exists() and model_path.is_file():
                logger.info(f"Found model in Ultralytics cache: {model_path}")
                return model_path

            # 检查子目录 (如 cache_dir/weights/)
            weights_dir = cache_dir / "weights"
            if weights_dir.exists():
                model_path = weights_dir / model_filename
                if model_path.exists() and model_path.is_file():
                    logger.info(f"Found model in Ultralytics cache: {model_path}")
                    return model_path

        return None

    @staticmethod
    def list_available_models() -> List[Dict]:
        """列出所有可用的预训练模型"""
        models = []
        for filename, info in PRETRAINED_MODELS.items():
            models.append({
                "filename": filename,
                "name": info["name"],
                "type": info["type"],
                "size": info["size"],
                "description": info["description"],
            })
        return models

    @staticmethod
    def list_local_models(save_dir: Path) -> Dict[str, Dict[str, Any]]:
        """
        列出本地已有的预训练模型

        返回格式：
        {
            "yolo11n.pt": {
                "location": "project",  # 或 "cache"
                "path": Path对象,
                "size": 文件大小（字节）
            }
        }
        """
        local_models = {}

        for model_filename in PRETRAINED_MODELS.keys():
            # 检查项目目录
            project_path = save_dir / model_filename
            if project_path.exists() and project_path.is_file():
                local_models[model_filename] = {
                    "location": "project",
                    "path": project_path,
                    "size": project_path.stat().st_size
                }
                continue

            # 检查缓存目录
            cached_path = PretrainedModelService._find_model_in_cache(model_filename)
            if cached_path:
                local_models[model_filename] = {
                    "location": "cache",
                    "path": cached_path,
                    "size": cached_path.stat().st_size
                }

        return local_models


    @staticmethod
    def download_model(model_filename: str, save_dir: Path) -> Path:
        """
        下载预训练模型到持久化目录

        Ultralytics会自动下载模型到缓存目录，我们将其复制到持久化的save_dir
        """
        if model_filename not in PRETRAINED_MODELS:
            raise ValueError(f"Unknown pretrained model: {model_filename}")

        save_dir.mkdir(parents=True, exist_ok=True)
        model_path = save_dir / model_filename

        # 再次检查持久化目录（可能在并发下载时已经存在）
        if model_path.exists():
            logger.info(f"Pretrained model already exists in persistent storage: {model_path}")
            return model_path

        try:
            logger.info(f"Downloading pretrained model to persistent storage: {model_filename}")

            # Ultralytics YOLO will auto-download to cache if not exists
            model = YOLO(model_filename)

            # 尝试获取Ultralytics下载的模型路径并复制到持久化目录
            import shutil
            copied = False

            # 方法1: 从ckpt_path获取
            if hasattr(model, 'ckpt_path') and model.ckpt_path:
                source_path = Path(model.ckpt_path)
                if source_path.exists():
                    shutil.copy2(source_path, model_path)
                    logger.info(f"Model copied from {source_path} to persistent storage: {model_path}")
                    copied = True

            # 方法2: 如果方法1失败，从缓存目录查找
            if not copied:
                cached_path = PretrainedModelService._find_model_in_cache(model_filename)
                if cached_path and cached_path.exists():
                    shutil.copy2(cached_path, model_path)
                    logger.info(f"Model copied from cache {cached_path} to persistent storage: {model_path}")
                    copied = True

            # 方法3: 如果都失败了，返回模型文件名让Ultralytics自己处理
            if not copied:
                logger.warning(f"Could not locate downloaded model file, Ultralytics will use cache: {model_filename}")
                # 虽然无法复制，但至少模型已经下载到缓存了
                # 下次启动容器时需要重新下载，但这是fallback方案
                return Path(model_filename)

            return model_path

        except Exception as e:
            logger.error(f"Failed to download model {model_filename}: {e}")
            raise

    @staticmethod
    def get_model_info(model_filename: str) -> Optional[Dict]:
        """获取预训练模型信息"""
        return PRETRAINED_MODELS.get(model_filename)

    @staticmethod
    def is_pretrained_model(model_filename: str) -> bool:
        """检查是否为预训练模型"""
        return model_filename in PRETRAINED_MODELS

    @staticmethod
    def ensure_model_available(model_filename: str, save_dir: Path) -> Path:
        """
        确保模型在持久化目录中可用

        查找和处理顺序：
        1. 优先检查持久化目录 (save_dir，通常是 /app/data/models)
        2. 如果在Ultralytics缓存中找到，复制到持久化目录
        3. 如果都不存在，下载并保存到持久化目录

        这样确保模型始终在持久化存储中，容器重启不会丢失
        """
        if not PretrainedModelService.is_pretrained_model(model_filename):
            raise ValueError(f"Not a pretrained model: {model_filename}")

        save_dir.mkdir(parents=True, exist_ok=True)
        model_path = save_dir / model_filename

        # 1. 优先检查持久化目录（这是最重要的）
        if model_path.exists():
            logger.info(f"✓ Using model from persistent storage: {model_path}")
            return model_path

        # 2. 检查Ultralytics缓存目录
        cached_model = PretrainedModelService._find_model_in_cache(model_filename)
        if cached_model:
            logger.info(f"✓ Found model in Ultralytics cache: {cached_model}")
            # 必须复制到持久化目录，这样容器重启后模型仍然可用
            try:
                import shutil
                shutil.copy2(cached_model, model_path)
                logger.info(f"✓ Copied model to persistent storage: {model_path}")
                return model_path
            except Exception as e:
                logger.error(f"✗ Failed to copy model to persistent storage: {e}")
                # 如果复制失败，仍然可以使用缓存路径，但会有警告
                logger.warning(f"⚠ Using cache path (not persistent): {cached_model}")
                return cached_model

        # 3. 模型不存在，需要下载到持久化目录
        logger.info(f"Model not found locally, downloading to persistent storage: {model_filename}")
        return PretrainedModelService.download_model(model_filename, save_dir)



