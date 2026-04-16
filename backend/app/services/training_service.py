"""
Training service using Ultralytics YOLO
"""
import asyncio
import os
import shutil
import socket
from app.core.config import settings
from app.core.database import AsyncSessionLocal, create_background_session_maker
from app.core.websocket import ws_manager
from app.models import Dataset, Image, Annotation, TrainingJob, Model, JobStatus, Project
from app.schemas.schemas import TrainingJobCreate
from app.services.pretrained_model_service import PretrainedModelService
from app.services.webhook_service import webhook_service
from app.utils import build_yolo_dataset_yaml, write_yolo_annotation, YOLOV8_POSE_NUM_KEYPOINTS
from datetime import datetime, timedelta
from loguru import logger
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from typing import Optional, Dict, Any, List, Tuple

AVAILABLE_MODELS = [
    # YOLO11 检测
    "yolo11n.pt", "yolo11s.pt", "yolo11m.pt", "yolo11l.pt", "yolo11x.pt",
    # YOLO11 OBB / 姿态（官方文件名：yolo11n-obb / yolo11n-pose，勿写成 yolov11n-*）
    "yolo11n-obb.pt", "yolo11n-pose.pt",
    # YOLOv8 检测
    "yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt", "yolov8x.pt",
    # YOLOv8 OBB / 姿态
    "yolov8n-obb.pt", "yolov8n-pose.pt",
    # 其它
    "yolo11n-det.pt", "yolo11s-det.pt",
]


def _yolo_train_image_suffixes() -> frozenset:
    """与 Ultralytics get_img_files 支持的图片后缀对齐（用于导出目录校验）。统一为小写，避免版本差异导致计数为 0。"""
    fallback = frozenset({
        ".bmp", ".jpg", ".jpeg", ".jp2", ".j2k", ".png", ".tif", ".tiff", ".webp",
        ".heic", ".heif", ".avif", ".dng", ".mpo", ".gif",
    })
    try:
        from ultralytics.data.base import IMG_FORMATS

        extra: set = set()
        for x in IMG_FORMATS:
            s = str(x).strip().lower()
            if not s or s.startswith("*"):
                continue
            if not s.startswith("."):
                s = "." + s
            extra.add(s)
        return frozenset(fallback | extra)
    except Exception:
        return fallback


def _log_dataset_storage_diagnostics(dataset: Dataset) -> None:
    """找不到源文件时打印存储目录是否存在，便于排查 Docker 空目录挂载等问题。"""
    logger.error("—— 数据集存储诊断 dataset_id={} hostname={} ——", dataset.id, socket.gethostname())
    sp = dataset.storage_path
    logger.error("  dataset.storage_path={}", sp)
    if sp:
        p = Path(str(sp).replace("\\", "/"))
        logger.error("  storage_path.exists={} is_dir={}", p.exists(), p.is_dir() if p.exists() else None)
        for sub in ("images", "thumbnails", "labels"):
            subp = p / sub
            n = -1
            if subp.is_dir():
                try:
                    n = len(list(subp.iterdir()))
                except OSError as e:
                    n = -2
                    logger.error("  列出 {} 失败: {}", subp, e)
            logger.error("  {}/ exists={} 条目数={}", sub, subp.exists(), n)

    root = settings.DATASET_DIR
    logger.error("  DATASET_DIR={} exists={}", root, root.exists())
    if root.exists() and root.is_dir():
        try:
            names = [x.name for x in root.iterdir()]
            logger.error("  DATASET_DIR 下子目录/文件(最多40): {}", names[:40])
            if dataset.id and names and dataset.id not in names:
                logger.error(
                    "  【常见原因】数据库中的数据集目录在磁盘上不存在：若 compose 将「空的」宿主机目录挂载到 "
                    "/app/data/datasets 或 static-file 的空目录挂载会覆盖容器内原有上传文件。"
                    "请确认 compose 中 ./data/datasets 与 DATASET_DIR 一致，或重新上传图片。"
                )
        except OSError as e:
            logger.error("  列出 DATASET_DIR 失败: {}", e)

    logger.error("  DATA_DIR={} exists={}", settings.DATA_DIR, settings.DATA_DIR.exists())


def _find_image_in_dir_case_insensitive(images_dir: Path, filename: str) -> Optional[Path]:
    """Linux 区分大小写时，DB 中文件名与实际磁盘不一致（如 .JPG vs .jpg）时仍能找到文件。"""
    if not filename or not images_dir.is_dir():
        return None
    direct = images_dir / filename
    if direct.is_file():
        return direct
    fn_low = filename.lower()
    try:
        for p in images_dir.iterdir():
            if p.is_file() and p.name.lower() == fn_low:
                return p
    except OSError as e:
        logger.debug("list images dir failed {}: {}", images_dir, e)
    return None


def _resolve_training_image_path(img: Image, dataset: Dataset) -> Tuple[Optional[Path], List[str]]:
    """
    解析训练导出时要复制的源图片路径。
    DB 中的 file_path 在 Docker / 跨机迁移 / Windows→Linux 后常失效；按多种规则回退。
    """
    name = (img.filename or "").strip()
    candidates: List[Path] = []
    seen: set = set()

    def add(p: Optional[Path]) -> None:
        if p is None:
            return
        try:
            q = Path(str(p).replace("\\", "/"))
        except Exception:
            return
        key = str(q)
        if key in seen:
            return
        seen.add(key)
        candidates.append(q)

    # ── file_path：原样、相对路径、以及从任意盘符路径中截取 data/static-file 或 data/datasets 后缀 ──
    if img.file_path:
        norm = str(img.file_path).replace("\\", "/").strip()
        fp = Path(norm)
        add(fp)
        if not fp.is_absolute():
            add(settings.BASE_DIR / fp)
            add(settings.DATA_DIR / fp)
            add(Path.cwd() / fp)
        # 迁移库常见：Windows 全路径或含重复前缀，截取从 data/static-file 或 data/datasets 起的一段拼到当前 BASE_DIR
        norm_lower = norm.lower()
        for anchor in ("data/static-file/", "data/datasets/", "data/augmented/"):
            pos = norm_lower.find(anchor)
            if pos >= 0:
                tail = norm[pos:]
                add(settings.BASE_DIR / tail)
        # 相对路径且以 static-file/ 开头（缺省 data/ 前缀）
        rel = norm.lstrip("/")
        if not fp.is_absolute() and rel.lower().startswith("static-file/"):
            add(settings.DATA_DIR / rel)

    # ── storage_path：可能是相对路径（相对仓库 data 或工作目录）──
    if dataset.storage_path:
        sp_raw = str(dataset.storage_path).replace("\\", "/").strip()
        sp = Path(sp_raw)
        if name:
            if sp.is_absolute():
                add(sp / "images" / name)
                if not (sp / "images" / name).is_file():
                    ci = _find_image_in_dir_case_insensitive(sp / "images", name)
                    if ci is not None:
                        add(ci)
            else:
                for base in (settings.BASE_DIR, settings.DATA_DIR, Path.cwd()):
                    add((base / sp / "images" / name).resolve(strict=False))
                # sp 形如 static-file/<uuid> 而 BASE_DIR 下已有 data 目录
                if not str(sp).startswith("data/"):
                    add((settings.DATA_DIR / sp / "images" / name).resolve(strict=False))

    # ── 标准数据集目录（与创建数据集时 DATASET_DIR / id 一致）──
    if name:
        sid_dir = settings.DATASET_DIR / dataset.id / "images"
        p_sid = sid_dir / name
        add(p_sid)
        if not p_sid.is_file():
            ci2 = _find_image_in_dir_case_insensitive(sid_dir, name)
            if ci2 is not None:
                add(ci2)
        add(settings.DATA_DIR / "datasets" / dataset.id / "images" / name)
        ddir = settings.DATA_DIR / "datasets" / dataset.id / "images"
        if not (ddir / name).is_file():
            ci3 = _find_image_in_dir_case_insensitive(ddir, name)
            if ci3 is not None:
                add(ci3)

    if not candidates:
        logger.warning(
            "训练导出源图无候选路径（请检查 DB 中 file_path、filename、dataset.storage_path）: "
            "image_id={} filename={} file_path={} storage_path={}",
            img.id,
            name or "(空)",
            img.file_path,
            dataset.storage_path,
        )
        return None, []

    tried: List[str] = []
    tried_detail: List[str] = []
    for i, p in enumerate(candidates, start=1):
        tried.append(str(p))
        try:
            rp = p.resolve(strict=False)
        except Exception as ex:
            rp = p
            tried_detail.append(f"[{i}] {p} | resolve_err={ex}")
            continue
        exists = rp.exists()
        is_f = rp.is_file() if exists else False
        par = rp.parent
        par_ok = par.exists()
        par_is_dir = par.is_dir() if par_ok else False
        tried_detail.append(
            f"[{i}] {rp} | exists={exists} is_file={is_f} parent={par} parent_exists={par_ok} parent_is_dir={par_is_dir}"
        )
        if is_f:
            logger.info(
                "训练导出源图解析成功: image_id={} filename={} -> {} (第 {}/{} 个候选)",
                img.id,
                name or "(空)",
                rp,
                i,
                len(candidates),
            )
            return rp, tried

    raw_fp = Path(str(img.file_path).replace("\\", "/")) if img.file_path else None
    raw_exists = raw_fp.is_file() if raw_fp else False
    th_fp = Path(str(img.thumbnail_path).replace("\\", "/")) if img.thumbnail_path else None
    th_exists = th_fp.is_file() if th_fp else False
    logger.warning(
        "训练导出源图解析失败: image_id={} dataset_id={} filename={}\n"
        "  db.file_path={}\n"
        "  dataset.storage_path={}\n"
        "  【与标注 API 对齐】/datasets/files/image 仅使用 db 路径直读磁盘: file_path.exists={} thumbnail_path.exists={}\n"
        "    （若此前标注能看图而此处 file_path.exists=False，多为旧版 304 未校验磁盘导致浏览器缓存假象；已修复）\n"
        "  BASE_DIR={} DATA_DIR={} DATASET_DIR={} cwd={} hostname={}\n"
        "  共 {} 个候选路径:\n  {}",
        img.id,
        dataset.id,
        name or "(空)",
        img.file_path,
        dataset.storage_path,
        raw_exists,
        th_exists,
        settings.BASE_DIR,
        settings.DATA_DIR,
        settings.DATASET_DIR,
        Path.cwd(),
        socket.gethostname(),
        len(candidates),
        "\n  ".join(tried_detail) if tried_detail else "(无候选)",
    )
    return None, tried


def infer_ultralytics_task_from_model_name(model_name: str) -> str:
    """
    从权重文件名推断 Ultralytics 任务类型，用于与平台标注能力匹配校验。
    返回: detect | pose | obb | segment
    """
    m = (model_name or "").lower()
    if "-pose" in m:
        return "pose"
    if "-obb" in m:
        return "obb"
    if "-seg" in m:
        return "segment"
    return "detect"


def _patch_nms_max_time_img(seconds_per_img: float = 2.0):
    """Patch Ultralytics NMS：当未显式传入 max_time_img 时使用更大值，避免 time limit exceeded"""
    try:
        from ultralytics.utils import nms as nms_mod

        _original_nms = nms_mod.non_max_suppression

        def _patched_nms(*args, **kwargs):
            if 'max_time_img' not in kwargs:
                kwargs['max_time_img'] = seconds_per_img
            return _original_nms(*args, **kwargs)

        nms_mod.non_max_suppression = _patched_nms
        logger.info(f"Patched NMS max_time_img default to {seconds_per_img}s")
    except Exception as e:
        logger.debug(f"Could not patch NMS max_time_img: {e}")


async def _cleanup_gpu_memory(gpu_id: Optional[int] = None):
    """清理GPU显存，释放缓存

    Args:
        gpu_id: 要清理的GPU ID，None表示清理所有GPU
    """
    try:
        import torch
        if torch.cuda.is_available():
            if gpu_id is not None:
                # 清理指定GPU
                with torch.cuda.device(gpu_id):
                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()
                logger.info(f"GPU {gpu_id} memory cleaned up")
            else:
                # 清空所有GPU的缓存
                torch.cuda.empty_cache()

                # 同步所有GPU设备
                for device_id in range(torch.cuda.device_count()):
                    with torch.cuda.device(device_id):
                        torch.cuda.synchronize()

                logger.info("GPU memory cache cleared successfully")
    except ImportError:
        logger.debug("PyTorch not available, skipping GPU cleanup")
    except Exception as e:
        logger.warning(f"Failed to cleanup GPU memory: {e}")


async def _gc_and_empty_cuda() -> None:
    """强制 GC 并清空 CUDA 缓存（须在调用方已 del model 之后调用）。"""
    import gc

    gc.collect()
    await _cleanup_gpu_memory()


class TrainingService:

    @staticmethod
    async def create_job(db: AsyncSession, data: TrainingJobCreate) -> TrainingJob:
        # 如果是继续训练，必须提供且验证基础模型存在
        if data.resume_training:
            if not data.base_model_id or not str(data.base_model_id).strip():
                raise ValueError("继续训练时必须选择基础模型")
            base_model_result = await db.execute(
                select(Model).where(Model.id == data.base_model_id)
            )
            base_model = base_model_result.scalar_one_or_none()
            if not base_model:
                raise ValueError(f"Base model {data.base_model_id} not found")
            if not Path(base_model.model_path).exists():
                raise ValueError(f"Base model file not found: {base_model.model_path}")

        job = TrainingJob(
            name=data.name,
            dataset_id=data.dataset_id,
            model_name=data.model_name,
            epochs=data.epochs,
            batch_size=data.batch_size,
            img_size=data.img_size,
            learning_rate=data.learning_rate,
            val_split=data.val_split,
            device=data.device,
            use_augmented_data=data.use_augmented_data,
            extra_params=data.extra_params or {},
            status=JobStatus.PENDING,
        )

        # 保存继续训练和类别增强参数（仅当 base_model_id 有效时保存）
        if data.resume_training and data.base_model_id:
            job.extra_params['resume_training'] = True
            job.extra_params['base_model_id'] = str(data.base_model_id).strip()

        if data.class_weights:
            job.extra_params['class_weights'] = data.class_weights

        if data.focus_classes:
            job.extra_params['focus_classes'] = data.focus_classes

        # 保存独立验证集参数
        if getattr(data, 'use_validation_dataset', False) and getattr(data, 'validation_dataset_id', None):
            job.extra_params['use_validation_dataset'] = True
            job.extra_params['validation_dataset_id'] = data.validation_dataset_id

        # 保存早停参数
        if data.patience is not None:
            job.extra_params['patience'] = data.patience

        if data.save_period is not None:
            job.extra_params['save_period'] = data.save_period

        # 保存 Webhook 推送配置
        if hasattr(data, 'enable_webhook'):
            job.extra_params['enable_webhook'] = data.enable_webhook

        # 保存所有YOLO训练超参数到extra_params
        yolo_params = {}

        # 图片尺寸：支持非方形
        if data.img_size_2 and data.img_size_2 != data.img_size:
            yolo_params['imgsz'] = [data.img_size, data.img_size_2]

        # 训练控制
        yolo_params['save'] = data.save
        yolo_params['val'] = data.val

        # 数据增强
        yolo_params['augment'] = data.augment
        yolo_params['hsv_h'] = data.hsv_h
        yolo_params['hsv_s'] = data.hsv_s
        yolo_params['hsv_v'] = data.hsv_v
        yolo_params['degrees'] = data.degrees
        yolo_params['translate'] = data.translate
        yolo_params['scale'] = data.scale
        yolo_params['shear'] = data.shear
        yolo_params['perspective'] = data.perspective
        yolo_params['flipud'] = data.flipud
        yolo_params['fliplr'] = data.fliplr
        yolo_params['mosaic'] = data.mosaic
        yolo_params['mixup'] = data.mixup

        # 正则化
        yolo_params['dropout'] = data.dropout
        yolo_params['weight_decay'] = data.weight_decay

        # 学习率策略
        yolo_params['lrf'] = data.lrf
        yolo_params['warmup_epochs'] = data.warmup_epochs

        # 损失函数权重
        yolo_params['box'] = data.box
        yolo_params['cls'] = data.cls
        yolo_params['dfl'] = data.dfl

        # 高级优化
        yolo_params['close_mosaic'] = data.close_mosaic
        yolo_params['overlap_mask'] = data.overlap_mask
        yolo_params['single_cls'] = data.single_cls
        yolo_params['nbs'] = data.nbs

        for k, v in yolo_params.items():
            job.extra_params[k] = v

        db.add(job)
        await db.flush()
        await db.refresh(job)
        return job

    @staticmethod
    async def get_job(db: AsyncSession, job_id: str) -> Optional[TrainingJob]:
        result = await db.execute(
            select(TrainingJob).where(TrainingJob.id == job_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_jobs(db: AsyncSession, skip: int = 0, limit: int = 20, project_id: Optional[str] = None):
        query = select(TrainingJob).order_by(TrainingJob.created_at.desc())
        if project_id:
            query = query.join(Dataset, TrainingJob.dataset_id == Dataset.id).where(Dataset.project_id == project_id)
        result = await db.execute(query.offset(skip).limit(limit))
        return result.scalars().all()

    @staticmethod
    async def cancel_job(db: AsyncSession, job_id: str) -> bool:
        job = await TrainingService.get_job(db, job_id)
        if not job or job.status not in [JobStatus.PENDING, JobStatus.RUNNING]:
            return False
        job.status = JobStatus.CANCELLED
        # Clear time estimation fields
        job.avg_epoch_time = None
        job.estimated_remaining_time = None
        job.estimated_completion_time = None
        await db.commit()
        return True

    @staticmethod
    async def stop_job(db: AsyncSession, job_id: str) -> bool:
        """停止训练任务，标记为需要在当前epoch完成后停止并保存模型"""
        job = await TrainingService.get_job(db, job_id)
        if not job or job.status not in [JobStatus.RUNNING]:
            return False

        params = dict(job.extra_params or {})
        params['stop_requested'] = True
        job.extra_params = params
        flag_modified(job, 'extra_params')
        await db.commit()

        logger.info(f"Stop requested for job {job_id}, training will finish current epoch and save model")
        return True

    @staticmethod
    async def run_training_job(job_id: str, allocated_device: Optional[str] = None):
        """Run training in a thread pool (YOLO training is synchronous)

        Args:
            job_id: Training job ID
            allocated_device: GPU device string from queue (e.g. "0" or "0,1")
        """
        loop = asyncio.get_event_loop()
        # Pass the main event loop and allocated device string (e.g. "0" or "0,1") to the training function
        await loop.run_in_executor(None, _run_training_sync, job_id, loop, allocated_device)

    @staticmethod
    async def prepare_yolo_dataset(db: AsyncSession, job: TrainingJob) -> str:
        """Export dataset to YOLO directory format for training"""
        import random

        dataset_result = await db.execute(
            select(Dataset).where(Dataset.id == job.dataset_id)
        )
        dataset = dataset_result.scalar_one_or_none()
        if not dataset:
            raise ValueError(f"Dataset {job.dataset_id} not found")

        # Get images - filter by augmentation flag if needed
        query = select(Image).where(Image.dataset_id == job.dataset_id)

        # Check if use_augmented_data is set
        use_augmented = job.use_augmented_data if hasattr(job, 'use_augmented_data') else True

        all_images_result = await db.execute(query)
        all_dataset_images = all_images_result.scalars().all()

        # Statistics
        original_images = [img for img in all_dataset_images if not img.is_augmented]
        augmented_images = [img for img in all_dataset_images if img.is_augmented]

        logger.info(f"Dataset statistics: {len(original_images)} original, {len(augmented_images)} augmented images")

        if not use_augmented:
            # Only use non-augmented images
            images = original_images
            logger.info(f"Training with ORIGINAL data only: {len(images)} images")
            await ws_manager.send_message(job.id, {
                "type": "info",
                "message": f"使用原始数据训练：{len(images)} 张图片（跳过 {len(augmented_images)} 张增强图片）",
            })
        else:
            # Use all images
            images = all_dataset_images
            logger.info(f"Training with ALL data (original + augmented): {len(images)} images")
            await ws_manager.send_message(job.id, {
                "type": "info",
                "message": f"使用全部数据训练：{len(original_images)} 张原始 + {len(augmented_images)} 张增强 = {len(images)} 张图片",
            })

        if not images:
            raise ValueError(f"Dataset has no images. Cannot start training.")

        # Validate that images have annotations
        images_with_annotations = []
        images_without_annotations = []
        augmented_without_annotations = []

        for img in images:
            anns_result = await db.execute(
                select(Annotation).where(Annotation.image_id == img.id)
            )
            anns = anns_result.scalars().all()
            if anns:
                images_with_annotations.append(img)
            else:
                images_without_annotations.append(img)
                if img.is_augmented:
                    augmented_without_annotations.append(img)

        if not images_with_annotations:
            raise ValueError(
                f"Dataset has {len(images)} images but none have annotations. "
                f"Cannot train without labeled data. Please add annotations to at least some images."
            )

        is_pose = bool(job.model_name and "-pose" in job.model_name.lower())
        is_obb = bool(job.model_name and "-obb" in job.model_name.lower())
        if is_pose and is_obb:
            is_obb = False

        # 警告：增强数据未标注
        if use_augmented and len(augmented_without_annotations) > 0:
            warning_msg = (
                f"⚠️ 警告：{len(augmented_images)} 张增强图片中，"
                f"{len(augmented_without_annotations)} 张未标注，将不参与训练"
            )
            logger.warning(warning_msg)
            await ws_manager.send_message(job.id, {
                "type": "warning",
                "message": warning_msg,
            })

        if len(images_with_annotations) < len(images) * 0.5:
            logger.warning(
                f"Dataset: Only {len(images_with_annotations)}/{len(images)} images have annotations. "
                f"Training with partially labeled data may result in poor model performance."
            )

        # Use only images with annotations for training
        all_images = images_with_annotations
        random.shuffle(all_images)

        extra = job.extra_params or {}
        use_validation_dataset = extra.get("use_validation_dataset") and extra.get("validation_dataset_id")

        if use_validation_dataset:
            # 使用独立验证集：训练集=全部训练数据，验证集=从指定数据集加载
            train_images = all_images
            val_dataset_id = extra["validation_dataset_id"]

            # 加载验证集数据集
            val_dataset_result = await db.execute(
                select(Dataset).where(Dataset.id == val_dataset_id)
            )
            val_dataset = val_dataset_result.scalar_one_or_none()
            if not val_dataset:
                raise ValueError(f"Validation dataset {val_dataset_id} not found")

            # 获取验证集中有标注的图片（仅原始图，增强图可选；这里先用全部）
            val_images_result = await db.execute(
                select(Image).where(Image.dataset_id == val_dataset_id)
            )
            val_all = val_images_result.scalars().all()
            val_images = []
            for img in val_all:
                anns_result = await db.execute(
                    select(Annotation).where(Annotation.image_id == img.id)
                )
                if anns_result.scalars().all():
                    val_images.append(img)

            if not val_images:
                raise ValueError(
                    f"Validation dataset '{val_dataset.name}' has no images with annotations. "
                    f"Please add annotations to the validation dataset."
                )

            logger.info(
                f"Dataset split: {len(train_images)} training (from train dataset), "
                f"{len(val_images)} validation (from dataset '{val_dataset.name}')"
            )
            await ws_manager.send_message(job.id, {
                "type": "info",
                "message": f"使用独立验证集: 训练 {len(train_images)} 张，验证 {len(val_images)} 张（来自 {val_dataset.name}）",
            })
        else:
            # 按比例从训练集划分（保证 val 非空，避免导出后 images/val 为空或 Ultralytics 异常）
            val_split = min(job.val_split, 0.9)  # Cap at 90% validation max
            n = len(all_images)
            train_count = max(1, int(n * (1 - val_split)))
            if train_count >= n and n > 1:
                train_count = n - 1
            train_images = all_images[:train_count]
            val_images = all_images[train_count:]
            if not val_images:
                if n == 1:
                    val_images = list(all_images)
                    logger.info(
                        "Dataset split: 仅 1 张已标注图片，train/val 使用同一张以避免验证集为空"
                    )
                elif len(train_images) > 1:
                    val_images = [train_images.pop()]
                    logger.info(
                        "Dataset split: 验证集为空，已从训练集自动挪 1 张到验证集"
                    )
                else:
                    val_images = list(all_images)
                    logger.info(
                        "Dataset split: 验证集仍为空，train/val 使用相同图片集"
                    )

            logger.info(
                f"Dataset split: {len(train_images)} training, {len(val_images)} validation "
                f"(split ratio: {1-val_split:.1%} train, {val_split:.1%} val)"
            )

        # Output structure
        output_dir = settings.EXPORT_DIR / f"train_{job.id}"
        for split in ["train", "val"]:
            (output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
            (output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

        # 当使用独立验证集时，验证集可能有不同的类别顺序，需要建立 class_name -> train_class_id 的映射
        val_class_map = None  # {class_name: train_class_id}
        if use_validation_dataset:
            train_classes = dataset.classes or []
            val_class_map = {}
            # 验证集类别可能在不同顺序，按名称映射
            if val_dataset.classes:
                for name in val_dataset.classes:
                    if name in train_classes:
                        val_class_map[name] = train_classes.index(name)
                    else:
                        logger.warning(f"Validation dataset has class '{name}' not in training dataset, such annotations will be skipped")

        logger.info(
            "训练导出环境: job_id={} dataset_id={} BASE_DIR={} DATA_DIR={} DATASET_DIR={} EXPORT_DIR={} "
            "dataset.storage_path={} cwd={} hostname={}",
            job.id,
            dataset.id,
            settings.BASE_DIR,
            settings.DATA_DIR,
            settings.DATASET_DIR,
            settings.EXPORT_DIR,
            dataset.storage_path,
            Path.cwd(),
            socket.gethostname(),
        )

        missing_src_count = 0
        for split_name, split_images in [("train", train_images), ("val", val_images)]:
            is_val_from_separate = split_name == "val" and use_validation_dataset
            for img in split_images:
                src, tried_paths = _resolve_training_image_path(img, dataset)
                if src is None:
                    missing_src_count += 1
                    # 详情已在 _resolve_training_image_path 中打印 WARNING（含每路径 exists/parent）
                    continue
                # 导出文件名与磁盘上一致（避免 DB 中 filename 为空或与实际大小写不一致导致 YOLO 不识别）
                dst_name = (img.filename or "").strip() or src.name
                dst_img = output_dir / "images" / split_name / dst_name
                shutil.copy2(str(src), str(dst_img))
                logger.debug(
                    "训练导出复制: split={} image_id={} {} -> {}",
                    split_name,
                    img.id,
                    src,
                    dst_img,
                )

                # Write annotations
                anns_result = await db.execute(
                    select(Annotation).where(Annotation.image_id == img.id)
                )
                anns = anns_result.scalars().all()

                # 验证集来自独立数据集时，映射 class_id 到训练集类别
                if is_val_from_separate:
                    train_classes = dataset.classes or []
                    mapped_anns = []
                    for a in anns:
                        name = a.class_name or (val_dataset.classes[a.class_id] if val_dataset.classes and a.class_id < len(val_dataset.classes) else None)
                        if val_class_map and name is not None and name in val_class_map:
                            train_cid = val_class_map[name]
                        elif name is not None and name in train_classes:
                            train_cid = train_classes.index(name)
                        elif not val_class_map and train_classes and a.class_id < len(train_classes):
                            # 验证集无 classes 时假定顺序一致
                            train_cid = a.class_id
                        else:
                            continue
                        m = {
                            "class_id": train_cid,
                            "x_center": a.x_center, "y_center": a.y_center,
                            "bbox_width": a.bbox_width, "bbox_height": a.bbox_height,
                        }
                        if getattr(a, "polygon_points", None):
                            m["polygon_points"] = a.polygon_points
                        mapped_anns.append(m)
                    ann_list = mapped_anns
                else:
                    ann_list = [
                        {
                            "class_id": a.class_id,
                            "x_center": a.x_center,
                            "y_center": a.y_center,
                            "bbox_width": a.bbox_width,
                            "bbox_height": a.bbox_height,
                            **({"polygon_points": a.polygon_points} if getattr(a, "polygon_points", None) else {}),
                        }
                        for a in anns
                    ]

                label_filename = Path(dst_name).stem + ".txt"
                label_path = output_dir / "labels" / split_name / label_filename
                write_yolo_annotation(
                    str(label_path),
                    ann_list,
                    pose=is_pose,
                    obb=is_obb,
                    num_keypoints=YOLOV8_POSE_NUM_KEYPOINTS,
                )

        # Build dataset.yaml
        classes = dataset.classes or []

        # 如果数据集没有注册类别，从标注数据中自动提取
        if not classes:
            logger.warning("Dataset has no classes defined, extracting from annotations...")
            class_query = await db.execute(
                select(Annotation.class_id, Annotation.class_name)
                .join(Image, Image.id == Annotation.image_id)
                .where(Image.dataset_id == job.dataset_id)
                .distinct()
                .order_by(Annotation.class_id)
            )
            class_rows = class_query.all()

            if class_rows:
                max_class_id = max(row.class_id for row in class_rows)
                classes = [""] * (max_class_id + 1)
                for row in class_rows:
                    classes[row.class_id] = row.class_name or str(row.class_id)

                # 回写到数据集记录，避免下次再提取
                dataset.classes = classes
                flag_modified(dataset, "classes")
                await db.commit()
                logger.info(f"Extracted {len(class_rows)} classes from annotations: {classes}")
            else:
                raise ValueError("Dataset has no classes and no annotations found. Cannot start training.")

        # task 由 model.train(task=...) 传入更可靠；yaml 内 task 部分版本与 OBB 数据加载器不兼容
        yaml_path = build_yolo_dataset_yaml(
            dataset_dir=str(output_dir),
            classes=classes,
            train_path="images/train",
            val_path="images/val",
            kpt_shape=[YOLOV8_POSE_NUM_KEYPOINTS, 3] if is_pose else None,
            task=None,
        )

        if missing_src_count:
            logger.error(
                "训练导出共有 {} 张图片在服务器上找不到源文件。",
                missing_src_count,
            )
            _log_dataset_storage_diagnostics(dataset)

        _train_img_dir = output_dir / "images" / "train"
        _val_img_dir = output_dir / "images" / "val"
        _img_ext = _yolo_train_image_suffixes()

        def _count_images(split_dir: Path) -> int:
            if not split_dir.is_dir():
                return 0
            return sum(
                1 for p in split_dir.iterdir()
                if p.suffix.lower() in _img_ext and p.is_file()
            )

        _nt, _nv = _count_images(_train_img_dir), _count_images(_val_img_dir)
        logger.info(
            "训练导出目录校验: job_id={} output_dir={} images/train 有效图={} images/val 有效图={} "
            "missing_src={} YOLO后缀规则数量={}",
            job.id,
            output_dir,
            _nt,
            _nv,
            missing_src_count,
            len(_img_ext),
        )
        if _nt == 0:
            dbg_files = ""
            if _train_img_dir.is_dir():
                found = [p for p in _train_img_dir.iterdir() if p.is_file()]
                if found:
                    dbg_files = (
                        " 目录内已有文件但后缀未匹配 YOLO 图片列表，请检查扩展名；"
                        f"示例: {[p.name for p in found[:8]]}"
                    )
                elif missing_src_count > 0:
                    dbg_files = f" 本次导出因找不到源文件已跳过 {missing_src_count} 张图。"
            raise ValueError(
                "导出后 images/train 下没有有效图片。"
                "若 parent_exists=False：容器内无该路径。请确认 DATASET_DIR 与 compose 挂载一致（默认 data/datasets），"
                "且宿主机 ./data/datasets/<数据集ID>/images 下有图片。旧库若仍指向 static-file，请把文件迁到 datasets 下同名 UUID 或新建数据集重传。"
                "（.bmp 等格式在支持列表内，问题通常是文件路径/挂载而非扩展名。）"
                + dbg_files
            )
        if _nv == 0:
            raise ValueError(
                "验证集为空（images/val 无图片）。请增加数据、减小 val_split，或关闭独立验证集。"
            )

        data_stats = {
            "total_images": len(all_images),
            "train_images": len(train_images),
            "val_images": len(val_images),
            "use_augmented": use_augmented,
            "original_count": len(original_images),
            "augmented_count": len(augmented_images),
            "labeled_count": len(images_with_annotations),
        }
        return yaml_path, data_stats


def _run_training_sync(job_id: str, main_loop, allocated_device: Optional[str] = None):
    """Synchronous training function (runs in thread pool)

    Args:
        job_id: Training job ID
        main_loop: Main event loop
        allocated_device: GPU device string from queue (e.g. "0" or "0,1" for multi-GPU)
    """
    import asyncio
    import nest_asyncio

    # 设置 CUDA_VISIBLE_DEVICES，单卡如 "0"，多卡如 "0,1"
    original_cuda_visible_devices = None
    if allocated_device:
        original_cuda_visible_devices = os.environ.get('CUDA_VISIBLE_DEVICES')
        os.environ['CUDA_VISIBLE_DEVICES'] = allocated_device
        logger.info(f"Job {job_id}: Set CUDA_VISIBLE_DEVICES={allocated_device} (original: {original_cuda_visible_devices})")

    # Allow nested event loops (needed for Ultralytics callbacks)
    try:
        nest_asyncio.apply()
    except:
        pass

    async def _async_wrapper():
        # Create a new session maker for this background thread's event loop
        BackgroundSessionLocal = create_background_session_maker()

        # Create a new session within this event loop context
        async with BackgroundSessionLocal() as db:
            try:
                # Pass the main loop to the execution function
                await _execute_training(db, job_id, main_loop)
            except Exception as e:
                logger.exception(f"Training job {job_id} failed: {e}")

                # 清理GPU显存
                try:
                    await _cleanup_gpu_memory()
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup GPU memory: {cleanup_error}")

                # Use a new session for error handling
                try:
                    async with BackgroundSessionLocal() as db2:
                        result = await db2.execute(
                            select(TrainingJob).where(TrainingJob.id == job_id)
                        )
                        job = result.scalar_one_or_none()
                        if job:
                            job.status = JobStatus.FAILED
                            # 处理CUDA OOM错误信息
                            error_message = str(e)
                            if "CUDA out of memory" in error_message or "OutOfMemoryError" in error_message:
                                error_message = (
                                    "GPU 显存不足 (OOM)。建议：1) 图片尺寸改为 640×640 或 1280×1280；"
                                    "2) batch_size 降至 2-4；3) 等待其他训练任务释放显存。"
                                )
                            job.error_message = error_message
                            # Clear time estimation fields
                            job.avg_epoch_time = None
                            job.estimated_remaining_time = None
                            job.estimated_completion_time = None
                            await db2.commit()
                except Exception as db_error:
                    logger.error(f"Failed to update job status: {db_error}")

                try:
                    await ws_manager.send_message(job_id, {
                        "type": "training_error",
                        "job_id": job_id,
                        "error": job.error_message if 'job' in locals() else str(e),
                    })
                except Exception as ws_error:
                    logger.error(f"Failed to send error message: {ws_error}")

    # Create a fresh event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_async_wrapper())
    finally:
        # Clean up pending tasks before closing
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()

        # 恢复原来的CUDA_VISIBLE_DEVICES环境变量
        if allocated_device:
            if original_cuda_visible_devices is not None:
                os.environ['CUDA_VISIBLE_DEVICES'] = original_cuda_visible_devices
                logger.debug(f"Job {job_id}: Restored CUDA_VISIBLE_DEVICES={original_cuda_visible_devices}")
            else:
                os.environ.pop('CUDA_VISIBLE_DEVICES', None)
                logger.debug(f"Job {job_id}: Removed CUDA_VISIBLE_DEVICES")


async def _execute_training(db: AsyncSession, job_id: str, main_loop):
    """Execute YOLO training"""
    from ultralytics import YOLO

    job = await TrainingService.get_job(db, job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")

    # Check if cancelled
    if job.status == JobStatus.CANCELLED:
        return

    # Prepare dataset
    yaml_path, data_stats = await TrainingService.prepare_yolo_dataset(db, job)

    # Update job status
    job.status = JobStatus.RUNNING
    job.started_at = datetime.utcnow()
    job.metrics_history = []
    await db.commit()

    # 获取项目的 Webhook 配置
    webhook_config = await _get_webhook_config(db, job)

    # 发送训练开始 Webhook
    if webhook_config:
        try:
            await webhook_service.send_training_webhook(
                webhook_url=webhook_config['url'],
                event_type='started',
                job_data=webhook_service.format_training_data(job),
                secret=webhook_config.get('secret')
            )
        except Exception as e:
            logger.warning(f"Failed to send training started webhook: {e}")

    # Resolve device
    device = job.device
    if device == "auto":
        try:
            import torch
            device = "0" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"

    # Output directory
    output_dir = settings.MODEL_DIR / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # 确定初始模型
    initial_model = job.model_name
    resume_from_artifact_name: Optional[str] = None

    # 如果是继续训练，使用基础模型
    if job.extra_params.get('resume_training') and job.extra_params.get('base_model_id'):
        base_model_id = job.extra_params['base_model_id']
        base_model_result = await db.execute(
            select(Model).where(Model.id == base_model_id)
        )
        base_model = base_model_result.scalar_one_or_none()
        if base_model and Path(base_model.model_path).exists():
            initial_model = base_model.model_path
            resume_from_artifact_name = base_model.name
            logger.info(f"Resume training from model: {base_model.name} ({initial_model})")
        else:
            logger.warning(f"Base model not found, using default: {job.model_name}")
    else:
        # 检查是否为预训练模型，如果是则确保本地可用（避免重复下载）
        if PretrainedModelService.is_pretrained_model(job.model_name):
            try:
                logger.info(f"Checking for pretrained model: {job.model_name}")
                model_path = PretrainedModelService.ensure_model_available(
                    job.model_name,
                    settings.MODEL_DIR
                )
                initial_model = str(model_path)
                logger.info(f"Using pretrained model from: {initial_model}")
            except Exception as e:
                logger.warning(f"Failed to locate pretrained model locally, will let Ultralytics download: {e}")
                # 使用官方文件名（含 yolov11n-* -> yolo11n-* 别名），避免无效相对路径
                initial_model = PretrainedModelService.resolve_model_filename(job.model_name)

    # 供前端展示：任务配置名 vs 实际加载的权重
    _im_str = str(initial_model)
    weights_basename = Path(_im_str).name
    if resume_from_artifact_name:
        effective_label = f"{resume_from_artifact_name}（{weights_basename}）"
    else:
        effective_label = weights_basename
    ep = dict(job.extra_params or {})
    ep["effective_model_label"] = effective_label
    ep["effective_model_path"] = _im_str[:900]
    ep["configured_model_name"] = job.model_name
    job.extra_params = ep
    flag_modified(job, "extra_params")
    await db.commit()

    await ws_manager.send_message(job_id, {
        "type": "training_started",
        "job_id": job_id,
        "message": "Training started",
        "data_info": data_stats,
        "effective_model_label": effective_label,
        "effective_model_path": _im_str[:900],
        "configured_model_name": job.model_name,
    })

    # Load model
    model = YOLO(initial_model)


    # Custom callback for progress updates
    metrics_history = []
    epoch_start_time = None
    training_start_time = datetime.utcnow()
    epoch_times = []  # 记录每个epoch的耗时

    def on_train_epoch_end(trainer):
        nonlocal epoch_start_time

        epoch = trainer.epoch + 1
        current_time = datetime.utcnow()

        # 计算本轮耗时
        if epoch_start_time:
            epoch_duration = (current_time - epoch_start_time).total_seconds()
            epoch_times.append(epoch_duration)

        # 重置下一轮的开始时间
        epoch_start_time = current_time

        # 收集完整的训练指标
        metrics = {
            "epoch": epoch,
            "timestamp": current_time.isoformat(),
        }

        # 训练损失
        if hasattr(trainer, 'loss_items') and trainer.loss_items is not None:
            if len(trainer.loss_items) >= 3:
                metrics["train/box_loss"] = float(trainer.loss_items[0])
                metrics["train/cls_loss"] = float(trainer.loss_items[1])
                metrics["train/dfl_loss"] = float(trainer.loss_items[2])
            elif len(trainer.loss_items) >= 2:
                metrics["train/box_loss"] = float(trainer.loss_items[0])
                metrics["train/cls_loss"] = float(trainer.loss_items[1])

        metrics_history.append(metrics)

        # 计算时间预估
        elapsed_time = (current_time - training_start_time).total_seconds()
        avg_epoch_time = sum(epoch_times) / len(epoch_times) if epoch_times else 0
        remaining_epochs = job.epochs - epoch
        estimated_remaining_time = avg_epoch_time * remaining_epochs if avg_epoch_time > 0 else 0
        estimated_completion_time = current_time + timedelta(seconds=estimated_remaining_time)

        # Update job in DB and check stop flag synchronously
        async def _update_db_and_check_stop():
            try:
                async with AsyncSessionLocal() as db2:
                    result = await db2.execute(
                        select(TrainingJob).where(TrainingJob.id == job_id)
                    )
                    j = result.scalar_one_or_none()
                    if j:
                        j.current_epoch = epoch
                        j.metrics_history = metrics_history.copy()
                        await db2.commit()
                        if j.status == JobStatus.CANCELLED:
                            return True
                        return bool(j.extra_params and j.extra_params.get('stop_requested'))
            except Exception as e:
                logger.warning(f"Failed to update training job progress: {e}")
            return False

        try:
            future = asyncio.run_coroutine_threadsafe(_update_db_and_check_stop(), main_loop)
            stop_requested = future.result(timeout=10)
            if stop_requested:
                logger.info(f"Job {job_id}: Stop or cancel requested, terminating training after this epoch")
                trainer.stop = True
        except Exception as e:
            logger.debug(f"Failed to schedule progress update: {e}")

        # Send websocket update (use sync publish to avoid "Future attached to different loop")
        try:
            ws_manager.publish_sync(job_id, {
                "type": "training_progress",
                "job_id": job_id,
                "epoch": epoch,
                "total_epochs": job.epochs,
                "metrics": metrics,
                "metrics_history": metrics_history.copy(),  # 完整历史数据
                "percent": round(epoch / job.epochs * 100, 1),

                # 时间信息
                "elapsed_time": elapsed_time,
                "avg_epoch_time": avg_epoch_time,
                "estimated_remaining_time": estimated_remaining_time,
                "estimated_completion_time": estimated_completion_time.isoformat() if estimated_remaining_time > 0 else None,
            })
        except Exception as e:
            logger.debug(f"Failed to send websocket update: {e}")

    def on_val_end(validator):
        if hasattr(validator, 'metrics'):
            m = validator.metrics
            map50 = float(m.box.map50) if hasattr(m, 'box') else 0
            map50_95 = float(m.box.map) if hasattr(m, 'box') else 0

            # 更新最后一个epoch的验证指标
            if metrics_history:
                metrics_history[-1].update({
                    "val/map50": map50,
                    "val/map50_95": map50_95
                })

                # 通过WebSocket发送验证指标更新 (use sync publish to avoid loop error)
                try:
                    ws_manager.publish_sync(job_id, {
                        "type": "validation_metrics",
                        "job_id": job_id,
                        "epoch": metrics_history[-1].get("epoch"),
                        "map50": map50,
                        "map50_95": map50_95,
                        "metrics_history": metrics_history.copy(),
                    })
                except Exception as e:
                    logger.debug(f"Failed to send validation metrics: {e}")

    model.add_callback("on_train_epoch_end", on_train_epoch_end)
    model.add_callback("on_val_end", on_val_end)

    # 自动计算最优 data loading workers 数量
    import os
    cpu_count = os.cpu_count() or 4

    if job.batch_size <= 8:
        max_workers_by_batch = 8
    elif job.batch_size <= 16:
        max_workers_by_batch = 6
    else:
        max_workers_by_batch = 4

    final_workers = min(
        cpu_count - 1,
        max_workers_by_batch,
        8
    )

    shm_size_gb = float(os.environ.get('SHM_SIZE_GB', '4'))
    if shm_size_gb < 2:
        final_workers = min(final_workers, 2)
        logger.warning(f"Shared memory is small ({shm_size_gb}GB), limiting workers to {final_workers}")

    logger.info(f"Using {final_workers} data loading workers (CPU cores: {cpu_count}, batch size: {job.batch_size})")

    # 构建图片尺寸参数：优先使用 extra_params 中的列表格式
    imgsz_param = job.extra_params.get('imgsz', job.img_size)

    # 显存风险校验：避免 imgsz 过大导致 CUDA OOM（10-11GB 显卡常见）
    def _effective_imgsz(p):
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            return int(p[0]), int(p[1])
        x = int(p)
        return x, x

    imgsz_w, imgsz_h = _effective_imgsz(imgsz_param)
    img_pixels = imgsz_w * imgsz_h
    is_multi_gpu = "," in str(device)
    gpu_count = len(str(device).split(",")) if is_multi_gpu else 1

    # DDP 时 batch_size 平分到每卡，必须 >= GPU 数量
    if is_multi_gpu and job.batch_size < gpu_count:
        raise ValueError(
            f"双卡训练时 batch_size 会平分到每张卡，当前 batch_size={job.batch_size} 会导致每卡为 0。"
            f"请将 batch_size 设为 ≥ {gpu_count}。"
        )
    max_batch_for_large = 2 if is_multi_gpu else 1  # 双卡时允许 batch 2
    # batch 超限时拒绝；双卡(0,1)可适当放宽
    if img_pixels > 2048 * 2048 and job.batch_size > max_batch_for_large:
        raise ValueError(
            f"图片尺寸 {imgsz_w}x{imgsz_h} 配合 batch_size={job.batch_size} 显存压力大。"
            f"大尺寸时请将 batch_size 设为 {max_batch_for_large}，或选用双卡(0,1)后尝试 batch 2。"
        )
    if img_pixels > 1280 * 1280 and job.batch_size > 4:
        raise ValueError(
            f"图片尺寸 {imgsz_w}x{imgsz_h} 配合 batch_size={job.batch_size} 显存压力大。"
            f"建议将 batch_size 降至 2-4 或减小图片尺寸至 1280×1280。"
        )
    if img_pixels > 2048 * 2048 and job.batch_size == 1:
        logger.warning(
            f"⚠️ 大尺寸 {imgsz_w}x{imgsz_h} batch=1：建议 16GB+ 显存，10-11GB 显卡可能 OOM"
        )

    # Train
    train_args = {
        "data": yaml_path,
        "epochs": job.epochs,
        "batch": job.batch_size,
        "imgsz": imgsz_param,
        "lr0": job.learning_rate,
        "device": device,
        "project": str(output_dir),
        "name": "train",
        "exist_ok": True,
        "verbose": True,
        "plots": True,
        "cache": False,
        "workers": final_workers,
        # patience=0 在 Ultralytics 中并不能禁用早停，需传入极大值（如 99999）
        "patience": 99999 if (job.extra_params.get('patience') or 100) == 0 else job.extra_params.get('patience', 100),
        "save_period": job.extra_params.get('save_period', -1),
        # 训练控制
        "save": job.extra_params.get('save', True),
        "val": job.extra_params.get('val', True),
        # 数据增强
        "augment": job.extra_params.get('augment', True),
        "hsv_h": job.extra_params.get('hsv_h', 0.015),
        "hsv_s": job.extra_params.get('hsv_s', 0.7),
        "hsv_v": job.extra_params.get('hsv_v', 0.4),
        "degrees": job.extra_params.get('degrees', 0.0),
        "translate": job.extra_params.get('translate', 0.1),
        "scale": job.extra_params.get('scale', 0.5),
        "shear": job.extra_params.get('shear', 0.0),
        "perspective": job.extra_params.get('perspective', 0.0),
        "flipud": job.extra_params.get('flipud', 0.0),
        "fliplr": job.extra_params.get('fliplr', 0.5),
        "mosaic": job.extra_params.get('mosaic', 1.0),
        "mixup": job.extra_params.get('mixup', 0.0),
        # 正则化
        "dropout": job.extra_params.get('dropout', 0.0),
        "weight_decay": job.extra_params.get('weight_decay', 0.0005),
        # 学习率策略
        "lrf": job.extra_params.get('lrf', 0.01),
        "warmup_epochs": job.extra_params.get('warmup_epochs', 3.0),
        # 损失函数权重
        "box": job.extra_params.get('box', 7.5),
        "cls": job.extra_params.get('cls', 0.5),
        "dfl": job.extra_params.get('dfl', 1.5),
        # 高级参数
        "close_mosaic": job.extra_params.get('close_mosaic', 10),
        "overlap_mask": job.extra_params.get('overlap_mask', True),
        "single_cls": job.extra_params.get('single_cls', False),
        "nbs": job.extra_params.get('nbs', 64),
    }

    # 注意：我们的「继续训练」= 从已有模型权重开始新训练，不是 Ultralytics 的 resume
    # resume=True 仅用于从中断的同一 run 恢复；若 base_model 是已训练完成的 checkpoint（如 best.pt），
    # Ultralytics 会尝试 resume 并因 "nothing to resume" 断言失败。显式传 resume=False 强制从权重开始新训练。
    train_args["resume"] = False

    # 默认关闭 AMP：Ultralytics 8.4.x 的 check_amp 会忽略用户选择的模型，强制下载 yolo26n.pt 做校验
    # 见 https://github.com/ultralytics/ultralytics/issues/10325
    # 用户选了 yolov8n 却下载 yolo26n，国内 GitHub 又慢。amp=False 可避免该下载
    use_amp = job.extra_params.get("amp") is True
    train_args["amp"] = use_amp
    if not use_amp:
        logger.info("amp=False to avoid check_amp downloading yolo26n.pt")

    # 类别权重：对特定类别加强训练
    if job.extra_params.get('class_weights'):
        class_weights = job.extra_params['class_weights']
        logger.info(f"Using class weights: {class_weights}")
        # Ultralytics 通过 loss weights 参数控制
        # class_weights 是字典 {"class_name": weight}
        # 需要转换为列表形式 [weight1, weight2, ...]
        # 这里记录到日志，实际应用需要在数据层面调整采样

    # 重点类别：增加这些类别的训练样本
    if job.extra_params.get('focus_classes'):
        focus_classes = job.extra_params['focus_classes']
        logger.info(f"Focus on classes: {focus_classes}")
        # 可以通过 mosaic, copy_paste 等增强参数提升效果
        train_args['mosaic'] = 1.0  # 启用 mosaic 增强
        train_args['copy_paste'] = 0.5  # 启用 copy-paste 增强

    if job.extra_params:
        # 已在 train_args 中显式处理的参数，不再从 extra_params 覆盖
        skip_keys = {
            'resume_training', 'base_model_id', 'class_weights', 'focus_classes',
            'stop_requested',  # 前端停止训练标记，非 YOLO 参数
            'effective_model_label', 'effective_model_path', 'configured_model_name',  # 仅用于 API/前端展示
            'use_validation_dataset', 'validation_dataset_id',  # 数据集准备阶段已消费，非 train() 参数
            'resume',  # 始终由我们显式设为 False，避免 extra_params 覆盖
            'amp',    # 继续训练时设为 False 避免 check_amp 下载
            'task',  # 由模型类型与下方逻辑显式设置（OBB/pose）
            'overlap_mask',  # 非分割任务须关闭，见下方
            'patience', 'save_period', 'enable_webhook', 'workers',
            # 新增的 YOLO 参数已在 train_args 中直接设置
            'imgsz', 'augment', 'hsv_h', 'hsv_s', 'hsv_v',
            'degrees', 'translate', 'scale', 'shear', 'perspective',
            'flipud', 'fliplr', 'mosaic', 'mixup',
            'dropout', 'weight_decay', 'lrf', 'warmup_epochs',
            'box', 'cls', 'dfl',
            'close_mosaic', 'single_cls', 'nbs',
            'save', 'val',
        }
        for key, value in job.extra_params.items():
            if key not in skip_keys:
                train_args[key] = value

    # OBB / 姿态：显式 task；overlap_mask 仅分割有效，否则易在加载 OBB 数据时报错
    _ul_task = infer_ultralytics_task_from_model_name(job.model_name)
    if _ul_task == "obb":
        train_args["task"] = "obb"
    elif _ul_task == "pose":
        train_args["task"] = "pose"
    if _ul_task != "segment":
        train_args["overlap_mask"] = False

    # 打印最终训练参数，便于排查
    log_args = {k: v for k, v in train_args.items() if k not in ['data', 'project']}
    logger.info(f"Final train_args: {log_args}")

    # 训练前清理显存
    await _cleanup_gpu_memory()

    # 增大 NMS max_time_img 默认值，避免 "NMS time limit exceeded" 导致验证 mAP 异常低下
    _patch_nms_max_time_img(2.0)

    try:
        logger.info("Calling model.train() ...")
        results = model.train(**train_args)
        logger.info("model.train() completed successfully")
    except Exception as train_error:
        logger.error(f"Training failed: {train_error}")
        try:
            del model
        except Exception:
            pass
        await _gc_and_empty_cuda()
        raise

    try:
        del model
    except Exception:
        pass
    await _gc_and_empty_cuda()

    # Get best model path
    # best.pt: 验证集上表现最好的模型（推荐使用）
    # last.pt: 最后一个epoch的模型（可能过拟合）
    best_model_path = output_dir / "train" / "weights" / "best.pt"
    last_model_path = output_dir / "train" / "weights" / "last.pt"

    # 优先使用best.pt，如果不存在则使用last.pt
    final_model = str(best_model_path) if best_model_path.exists() else str(last_model_path)
    logger.info(f"Final model path: {final_model} (best.pt preferred)")

    # Extract final metrics
    map50 = None
    map50_95 = None
    try:
        if hasattr(results, 'box'):
            map50 = float(results.box.map50)
            map50_95 = float(results.box.map)
        elif metrics_history:
            last = metrics_history[-1]
            map50 = last.get("val/map50")
            map50_95 = last.get("val/map50_95")
    except Exception:
        pass

    # Update job record
    job.status = JobStatus.COMPLETED
    job.completed_at = datetime.utcnow()
    job.model_path = final_model
    job.output_dir = str(output_dir)
    job.best_map50 = map50
    job.best_map50_95 = map50_95
    job.metrics_history = metrics_history
    job.current_epoch = job.epochs

    # Register model artifact
    file_size = None
    if best_model_path.exists():
        file_size = best_model_path.stat().st_size

    dataset_result = await db.execute(
        select(Dataset).where(Dataset.id == job.dataset_id)
    )
    dataset = dataset_result.scalar_one_or_none()

    model_artifact = Model(
        name=f"{job.name}_best",
        project_id=dataset.project_id if dataset else None,
        training_job_id=job.id,
        model_path=final_model,
        model_type="yolo",
        classes=dataset.classes if dataset else [],
        map50=map50,
        map50_95=map50_95,
        file_size=file_size,
    )
    db.add(model_artifact)
    await db.commit()

    await ws_manager.send_message(job_id, {
        "type": "training_complete",
        "job_id": job_id,
        "map50": map50,
        "map50_95": map50_95,
        "model_path": final_model,
        "model_id": model_artifact.id,
    })

    # 发送训练完成 Webhook
    if webhook_config:
        try:
            # 刷新job以获取最新数据
            await db.refresh(job)
            await webhook_service.send_training_webhook(
                webhook_url=webhook_config['url'],
                event_type='completed',
                job_data=webhook_service.format_training_data(job),
                secret=webhook_config.get('secret')
            )
        except Exception as e:
            logger.warning(f"Failed to send training completed webhook: {e}")

    logger.info(f"Training job {job_id} completed. mAP50={map50}, model={final_model}")


async def _get_webhook_config(db: AsyncSession, job: TrainingJob) -> Optional[Dict[str, Any]]:
    """获取任务的 Webhook 配置"""
    # 获取数据集关联的项目
    dataset_result = await db.execute(
        select(Dataset).where(Dataset.id == job.dataset_id)
    )
    dataset = dataset_result.scalar_one_or_none()

    if not dataset or not dataset.project_id:
        logger.debug(f"Job {job.id}: No project associated with dataset")
        return None

    # 获取项目的 Webhook 配置
    project_result = await db.execute(
        select(Project).where(Project.id == dataset.project_id)
    )
    project = project_result.scalar_one_or_none()

    if not project:
        logger.debug(f"Job {job.id}: Project not found")
        return None

    if not project.webhook_enabled:
        logger.debug(f"Job {job.id}: Project webhook not enabled")
        return None

    if not project.webhook_url:
        logger.warning(f"Job {job.id}: Project webhook enabled but no URL configured")
        return None

    # 检查事件是否订阅
    webhook_events = project.webhook_events or []
    if 'training' not in webhook_events and '*' not in webhook_events:
        logger.debug(f"Job {job.id}: 'training' event not subscribed in project webhooks: {webhook_events}")
        return None

    logger.info(f"Job {job.id}: Webhook enabled for events {webhook_events}")
    return {
        'url': project.webhook_url,
        'secret': project.webhook_secret,
        'events': webhook_events
    }
