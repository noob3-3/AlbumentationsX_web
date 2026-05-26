"""
Pretrained model service for downloading and managing Ultralytics official models
"""
import os
import ssl
import urllib.request
import zipfile
from loguru import logger
from pathlib import Path
from typing import List, Dict, Optional, Any
from ultralytics import YOLO

# 过小多为下载中断；PyTorch 2 存盘多为 ZIP，损坏时常报 PytorchStreamReader / central directory
_MIN_PT_BYTES = 16 * 1024


def _github_asset_download_urls(canonical_github_url: str) -> List[str]:
    """
    依次尝试的直链列表：镜像（可多个）→ 官方 GitHub。
    离线/无 DNS 时不要走 Ultralytics 的 YOLO(name) 下载：其会请求 api.github.com。

    未设置 ULTRALYTICS_GITHUB_MIRROR 时：自动使用 gh.llkk.cc，失败再试 gh.felicity.ac.cn，最后直连 github.com。
    """
    u = (canonical_github_url or "").strip()
    out: List[str] = []
    if not u:
        return out
    custom = os.getenv("ULTRALYTICS_GITHUB_MIRROR", "").strip()
    if custom:
        mirror = custom if custom.endswith("/") else custom + "/"
        if u.startswith("https://github.com/") or u.startswith("http://github.com/"):
            cand = mirror + u
            if cand not in out:
                out.append(cand)
    else:
        for prefix in ("https://gh.llkk.cc/", "https://gh.felicity.ac.cn/"):
            if not (u.startswith("https://github.com/") or u.startswith("http://github.com/")):
                break
            cand = prefix + u
            if cand not in out:
                out.append(cand)
    if u not in out:
        out.append(u)
    return out


def _mirrored_github_asset_url(canonical_github_url: str) -> str:
    """
    将 GitHub Release 直链转为镜像 URL（用于列表展示的首选下载地址）。
    环境变量 ULTRALYTICS_GITHUB_MIRROR：
      未设置时默认 https://gh.llkk.cc/（前缀 + 完整 GitHub URL）
      设为空则直连 github.com
    """
    u = (canonical_github_url or "").strip()
    if not u:
        return u
    mirror = os.getenv("ULTRALYTICS_GITHUB_MIRROR", "https://gh.llkk.cc/").strip()
    if not mirror:
        return u
    if not (u.startswith("https://github.com/") or u.startswith("http://github.com/")):
        return u
    if not mirror.endswith("/"):
        mirror += "/"
    return mirror + u


def _download_http_to_file(url: str, dest: Path, timeout: int = 600) -> None:
    """HTTP(S) 下载到 dest，先写 .part 再替换。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AlbumentationsX-Pretrained/1.0"},
        )
        total = 0
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            with open(part, "wb") as f:
                while True:
                    chunk = resp.read(512 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    total += len(chunk)
        if total < _MIN_PT_BYTES:
            raise RuntimeError(f"response too small ({total} B)")
        part.replace(dest)
    except Exception:
        if part.exists():
            part.unlink(missing_ok=True)
        raise


# 曾误写为 yolov11n-*，Ultralytics 官方为 yolo11n-*
_PRETRAINED_NAME_ALIASES = {
    "yolov11n-obb.pt": "yolo11n-obb.pt",
    "yolov11n-pose.pt": "yolo11n-pose.pt",
}


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
    # YOLO11 OBB / Pose（Ultralytics 官方名称为 yolo11n-*，不是 yolov11n-*）
    "yolo11n-obb.pt": {
        "name": "YOLO11 Nano OBB",
        "type": "obb",
        "size": "~6 MB",
        "description": "旋转框检测（Oriented Bounding Box）",
        "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n-obb.pt",
    },
    "yolo11n-pose.pt": {
        "name": "YOLO11 Nano Pose",
        "type": "pose",
        "size": "~6 MB",
        "description": "人体关键点 / 姿态估计",
        "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n-pose.pt",
    },
    "yolo26n-seg.pt": {
        "name": "YOLO26 Nano Segment",
        "type": "segment",
        "size": "~7 MB",
        "description": "YOLO26 实例分割（nano），需多边形标注",
        "url": "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n-seg.pt",
    },
    "yolo26n-sem.pt": {
        "name": "YOLO26 Nano Semantic",
        "type": "semantic",
        "size": "~4 MB",
        "description": "YOLO26 语义分割（nano），数据集需 PNG 掩膜与 masks_dir",
        "url": "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n-sem.pt",
    },
    # YOLOv8 OBB / Pose
    "yolov8n-obb.pt": {
        "name": "YOLOv8 Nano OBB",
        "type": "obb",
        "size": "~6 MB",
        "description": "旋转框检测（Oriented Bounding Box）",
        "url": "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n-obb.pt",
    },
    "yolov8n-pose.pt": {
        "name": "YOLOv8 Nano Pose",
        "type": "pose",
        "size": "~6 MB",
        "description": "人体关键点 / 姿态估计",
        "url": "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n-pose.pt",
    },
}


def _unlink_silent(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as e:
        logger.warning(f"Could not remove invalid checkpoint {path}: {e}")


def checkpoint_file_is_valid(path: Path) -> bool:
    """
    粗校验权重文件是否可读，避免损坏/HTML 占位页触发
    PytorchStreamReader failed reading zip archive: failed finding central directory
    """
    try:
        if not path.is_file():
            return False
        size = path.stat().st_size
        if size < _MIN_PT_BYTES:
            logger.warning(f"Checkpoint too small ({size} B), likely incomplete: {path}")
            return False
        with open(path, "rb") as f:
            head = f.read(256)
        h = head.lstrip()
        if h.startswith(b"<") or h.startswith(b"<!") or h.startswith(b"<?xml"):
            logger.warning(f"Checkpoint looks like HTML/XML, not weights: {path}")
            return False
        # PyTorch 2.x 默认 torch.save 为 ZIP 包裹
        if head[:2] == b"PK":
            try:
                with zipfile.ZipFile(path, "r") as zf:
                    bad = zf.testzip()
                    if bad is not None:
                        logger.warning(f"ZIP member corrupt in checkpoint: {bad} ({path})")
                        return False
                return True
            except zipfile.BadZipFile:
                logger.warning(f"BadZipFile (truncated download?): {path}")
                return False
        # 旧版纯 pickle 的 .pt：只做体积与非文本启发式
        return size >= 8192
    except OSError as e:
        logger.warning(f"Could not validate checkpoint {path}: {e}")
        return False


class PretrainedModelService:
    """管理Ultralytics预训练模型"""

    @staticmethod
    def resolve_model_filename(model_filename: str) -> str:
        """将历史别名解析为 Ultralytics 官方权重文件名。"""
        return _PRETRAINED_NAME_ALIASES.get(model_filename, model_filename)

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
            src = (info.get("url") or "").strip()
            row = {
                "filename": filename,
                "name": info["name"],
                "type": info["type"],
                "size": info["size"],
                "description": info["description"],
                "url": src,
                "download_url": _mirrored_github_asset_url(src) if src else "",
            }
            models.append(row)
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
        model_filename = PretrainedModelService.resolve_model_filename(model_filename)
        if model_filename not in PRETRAINED_MODELS:
            raise ValueError(f"Unknown pretrained model: {model_filename}")

        save_dir.mkdir(parents=True, exist_ok=True)
        model_path = save_dir / model_filename

        # 再次检查持久化目录（可能在并发下载时已经存在）
        if model_path.exists() and checkpoint_file_is_valid(model_path):
            logger.info(f"Pretrained model already exists in persistent storage: {model_path}")
            return model_path
        if model_path.exists():
            logger.warning(f"Removing corrupt checkpoint in persistent storage: {model_path}")
            _unlink_silent(model_path)

        try:
            logger.info(f"Downloading pretrained model to persistent storage: {model_filename}")

            # 避免 Ultralytics 复用已损坏的缓存导致 PytorchStreamReader 报错
            bad_cache = PretrainedModelService._find_model_in_cache(model_filename)
            if bad_cache and bad_cache.exists() and not checkpoint_file_is_valid(bad_cache):
                logger.warning(f"Removing corrupt cache before YOLO download: {bad_cache}")
                _unlink_silent(bad_cache)

            info = PRETRAINED_MODELS[model_filename]
            canonical = (info.get("url") or "").strip()
            if canonical:
                for fetch_url in _github_asset_download_urls(canonical):
                    logger.info(f"Trying HTTP download ({fetch_url[:120]}...)")
                    try:
                        _download_http_to_file(fetch_url, model_path)
                        if checkpoint_file_is_valid(model_path):
                            logger.info(f"HTTP download OK -> {model_path}")
                            return model_path
                        logger.warning("Downloaded file failed integrity check, retrying next URL if any")
                        _unlink_silent(model_path)
                    except Exception as http_err:
                        logger.warning(f"HTTP download failed: {http_err}")
                        _unlink_silent(model_path)
                raise RuntimeError(
                    f"无法下载预训练权重「{model_filename}」。当前环境可能无法访问 GitHub。"
                    f"请将权重文件手动放入 {save_dir}，或设置可访问的 ULTRALYTICS_GITHUB_MIRROR（将完整 GitHub Release 直链作为前缀拼接），"
                    f"官方直链参考：{canonical}"
                )

            # 无配置直链的旧模型名：才交由 Ultralytics 拉取（可能访问 api.github.com）
            model = YOLO(model_filename)

            # 尝试获取Ultralytics下载的模型路径并复制到持久化目录
            import shutil
            copied = False

            # 方法1: 从ckpt_path获取
            if hasattr(model, 'ckpt_path') and model.ckpt_path:
                source_path = Path(model.ckpt_path)
                if source_path.exists() and checkpoint_file_is_valid(source_path):
                    shutil.copy2(source_path, model_path)
                    logger.info(f"Model copied from {source_path} to persistent storage: {model_path}")
                    copied = True
                elif source_path.exists():
                    logger.warning(f"Source ckpt appears corrupt, not copying: {source_path}")
                    _unlink_silent(source_path)

            # 方法2: 如果方法1失败，从缓存目录查找
            if not copied:
                cached_path = PretrainedModelService._find_model_in_cache(model_filename)
                if cached_path and cached_path.exists() and checkpoint_file_is_valid(cached_path):
                    shutil.copy2(cached_path, model_path)
                    logger.info(f"Model copied from cache {cached_path} to persistent storage: {model_path}")
                    copied = True
                elif cached_path and cached_path.exists():
                    logger.warning(f"Removing corrupt cached weights: {cached_path}")
                    _unlink_silent(cached_path)

            # 方法3: 再尝试从缓存取绝对路径（避免返回相对路径导致 open 失败）
            if not copied:
                cached_again = PretrainedModelService._find_model_in_cache(model_filename)
                if cached_again and cached_again.exists() and checkpoint_file_is_valid(cached_again):
                    logger.warning(
                        f"Could not copy to {model_path}, using cache path: {cached_again}"
                    )
                    return cached_again
                if cached_again and cached_again.exists():
                    _unlink_silent(cached_again)
                logger.warning(
                    f"Could not locate downloaded model file on disk for: {model_filename}"
                )
                return Path(model_filename)

            if not checkpoint_file_is_valid(model_path):
                logger.error(f"Downloaded file failed validation, removing: {model_path}")
                _unlink_silent(model_path)
                raise RuntimeError(
                    f"Downloaded weights failed integrity check: {model_filename}. "
                    "Delete any partial .pt in MODEL_DIR and cache, then retry."
                )

            return model_path

        except Exception as e:
            logger.error(f"Failed to download model {model_filename}: {e}")
            raise

    @staticmethod
    def get_model_info(model_filename: str) -> Optional[Dict]:
        """获取预训练模型信息"""
        return PRETRAINED_MODELS.get(
            PretrainedModelService.resolve_model_filename(model_filename)
        )

    @staticmethod
    def is_pretrained_model(model_filename: str) -> bool:
        """检查是否为预训练模型"""
        return PretrainedModelService.resolve_model_filename(model_filename) in PRETRAINED_MODELS

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

        model_filename = PretrainedModelService.resolve_model_filename(model_filename)
        save_dir.mkdir(parents=True, exist_ok=True)
        model_path = save_dir / model_filename

        # 1. 优先检查持久化目录（这是最重要的）
        if model_path.exists():
            if checkpoint_file_is_valid(model_path):
                logger.info(f"✓ Using model from persistent storage: {model_path}")
                return model_path
            logger.warning(f"✗ Corrupt checkpoint in persistent storage, will re-download: {model_path}")
            _unlink_silent(model_path)

        # 2. 检查Ultralytics缓存目录
        cached_model = PretrainedModelService._find_model_in_cache(model_filename)
        if cached_model and cached_model.exists():
            if not checkpoint_file_is_valid(cached_model):
                logger.warning(f"✗ Corrupt file in cache, removing: {cached_model}")
                _unlink_silent(cached_model)
                cached_model = None
        if cached_model:
            logger.info(f"✓ Found model in Ultralytics cache: {cached_model}")
            # 必须复制到持久化目录，这样容器重启后模型仍然可用
            try:
                import shutil
                shutil.copy2(cached_model, model_path)
                if checkpoint_file_is_valid(model_path):
                    logger.info(f"✓ Copied model to persistent storage: {model_path}")
                    return model_path
                logger.warning(f"✗ Copy result invalid, removing: {model_path}")
                _unlink_silent(model_path)
            except Exception as e:
                logger.error(f"✗ Failed to copy model to persistent storage: {e}")
            if cached_model.exists() and checkpoint_file_is_valid(cached_model):
                logger.warning(f"⚠ Using cache path (not persistent): {cached_model}")
                return cached_model

        # 3. 模型不存在，需要下载到持久化目录
        logger.info(f"Model not found locally, downloading to persistent storage: {model_filename}")
        return PretrainedModelService.download_model(model_filename, save_dir)



