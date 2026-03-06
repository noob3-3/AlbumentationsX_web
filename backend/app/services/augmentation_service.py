"""
Augmentation service using AlbumentationsX
"""
import os
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import numpy as np
import albumentations as A
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.websocket import ws_manager
from app.models import Dataset, Image, Annotation, AugmentationJob, DatasetStatus, JobStatus, ImageSource, Project
from app.schemas.schemas import AugmentationJobCreate, AugmentationConfig
from app.utils import (
    ensure_rgb, save_image, generate_filename,
    get_image_info, create_thumbnail
)
from app.services.webhook_service import webhook_service


# ─────────────────────────────────────────────
# Default augmentation pipeline for object detection
# ─────────────────────────────────────────────
DEFAULT_AUGMENTATION_CONFIG = {
    "transforms": [
        {"name": "HorizontalFlip", "params": {"p": 0.5}},
        {"name": "VerticalFlip", "params": {"p": 0.2}},
        {"name": "RandomRotate90", "params": {"p": 0.3}},
        {"name": "Affine", "params": {"translate_percent": {"x": (-0.1, 0.1), "y": (-0.1, 0.1)}, "scale": (0.8, 1.2), "rotate": (-15, 15), "p": 0.5}},
        {"name": "RandomBrightnessContrast", "params": {"brightness_limit": 0.3, "contrast_limit": 0.3, "p": 0.5}},
        {"name": "HueSaturationValue", "params": {"hue_shift_limit": 20, "sat_shift_limit": 30, "val_shift_limit": 20, "p": 0.4}},
        {"name": "GaussianBlur", "params": {"blur_limit": (3, 7), "p": 0.3}},
        {"name": "GaussNoise", "params": {"p": 0.3}},
        {"name": "CLAHE", "params": {"p": 0.3}},
        {"name": "RandomShadow", "params": {"p": 0.2}},
        {"name": "RandomFog", "params": {"p": 0.1}},
        {"name": "Perspective", "params": {"p": 0.3}},
        {"name": "CoarseDropout", "params": {"num_holes_range": (1, 8), "hole_height_range": (8, 32), "hole_width_range": (8, 32), "p": 0.3}},
        {"name": "RandomResizedCrop", "params": {"size": [640, 640], "scale": [0.7, 1.0], "p": 0.4}},
    ]
}

AVAILABLE_TRANSFORMS = {
    # Geometric
    "HorizontalFlip": A.HorizontalFlip,
    "VerticalFlip": A.VerticalFlip,
    "RandomRotate90": A.RandomRotate90,
    "Rotate": A.Rotate,
    "Affine": A.Affine,
    "Perspective": A.Perspective,
    "ElasticTransform": A.ElasticTransform,
    "GridDistortion": A.GridDistortion,
    "OpticalDistortion": A.OpticalDistortion,
    "Transpose": A.Transpose,

    # Crop & Resize
    "RandomResizedCrop": A.RandomResizedCrop,
    "RandomCrop": A.RandomCrop,
    "CenterCrop": A.CenterCrop,

    # Color
    "RandomBrightnessContrast": A.RandomBrightnessContrast,
    "HueSaturationValue": A.HueSaturationValue,
    "RGBShift": A.RGBShift,
    "ChannelShuffle": A.ChannelShuffle,
    "ToGray": A.ToGray,
    "ColorJitter": A.ColorJitter,

    # Quality
    "CLAHE": A.CLAHE,
    "Equalize": A.Equalize,
    "Sharpen": A.Sharpen,
    "Posterize": A.Posterize,
    "Solarize": A.Solarize,
    "Emboss": A.Emboss,

    # Blur
    "GaussianBlur": A.GaussianBlur,
    "MotionBlur": A.MotionBlur,
    "MedianBlur": A.MedianBlur,
    "Defocus": A.Defocus,

    # Noise
    "GaussNoise": A.GaussNoise,
    "ISONoise": A.ISONoise,
    "MultiplicativeNoise": A.MultiplicativeNoise,

    # Weather
    "RandomShadow": A.RandomShadow,
    "RandomFog": A.RandomFog,
    "RandomRain": A.RandomRain,
    "RandomSnow": A.RandomSnow,
    "RandomSunFlare": A.RandomSunFlare,

    # Pixel
    "CoarseDropout": A.CoarseDropout,
    "Superpixels": A.Superpixels,
}


def build_pipeline(config: Optional[Dict[str, Any]] = None) -> A.Compose:
    """Build an albumentations pipeline from config dict"""
    if config is None:
        config = DEFAULT_AUGMENTATION_CONFIG

    transforms_list = []
    for t in config.get("transforms", []):
        name = t.get("name")
        params = t.get("params", {}).copy()  # 创建副本避免修改原始配置
        if name in AVAILABLE_TRANSFORMS:
            try:
                # Handle size parameter for RandomResizedCrop
                if name == "RandomResizedCrop" and "size" in params:
                    params["size"] = tuple(params["size"])

                # Handle Affine translate_percent parameter
                if name == "Affine" and "translate_percent" in params:
                    tp = params["translate_percent"]
                    if isinstance(tp, dict):
                        # 确保格式正确：{"x": (min, max), "y": (min, max)}
                        if "x" in tp and isinstance(tp["x"], list):
                            tp["x"] = tuple(tp["x"])
                        if "y" in tp and isinstance(tp["y"], list):
                            tp["y"] = tuple(tp["y"])

                # Handle tuple parameters (convert lists to tuples)
                for key, value in params.items():
                    if isinstance(value, list) and len(value) == 2:
                        # 检查是否应该是tuple（如范围参数）
                        if key in ['scale', 'rotate', 'blur_limit', 'num_holes_range',
                                   'hole_height_range', 'hole_width_range']:
                            params[key] = tuple(value)

                transforms_list.append(AVAILABLE_TRANSFORMS[name](**params))
            except Exception as e:
                logger.warning(f"Could not create transform {name} with params {params}: {e}")
        else:
            logger.warning(f"Unknown transform: {name}")

    bbox_params = A.BboxParams(
        format="yolo",
        min_visibility=0.3,
        label_fields=["class_labels"],
    )

    return A.Compose(transforms_list, bbox_params=bbox_params)


class AugmentationService:

    @staticmethod
    async def create_job(db: AsyncSession, data: AugmentationJobCreate) -> AugmentationJob:
        config_dict = data.config.model_dump() if data.config else None
        job = AugmentationJob(
            dataset_id=data.dataset_id,
            config=config_dict,
            multiplier=data.multiplier,
            status=JobStatus.PENDING,
        )
        db.add(job)
        await db.flush()
        await db.refresh(job)
        return job

    @staticmethod
    async def get_job(db: AsyncSession, job_id: str) -> Optional[AugmentationJob]:
        result = await db.execute(
            select(AugmentationJob).where(AugmentationJob.id == job_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_jobs(db: AsyncSession, dataset_id: Optional[str] = None):
        query = select(AugmentationJob).order_by(AugmentationJob.created_at.desc())
        if dataset_id:
            query = query.where(AugmentationJob.dataset_id == dataset_id)
        result = await db.execute(query)
        return result.scalars().all()

    @staticmethod
    async def run_augmentation_job(job_id: str):
        """Run augmentation job in background (called from background task)"""
        async with AsyncSessionLocal() as db:
            try:
                await AugmentationService._execute_job(db, job_id)
            except Exception as e:
                logger.exception(f"Augmentation job {job_id} failed: {e}")
                async with AsyncSessionLocal() as db2:
                    job = await AugmentationService.get_job(db2, job_id)
                    if job:
                        job.status = JobStatus.FAILED
                        job.error_message = str(e)
                        await db2.commit()

                        # 发送失败 Webhook
                        webhook_config = await _get_augmentation_webhook_config(db2, job)
                        if webhook_config:
                            try:
                                await webhook_service.send_augmentation_webhook(
                                    webhook_url=webhook_config['url'],
                                    event_type='failed',
                                    job_data=webhook_service.format_augmentation_data(job),
                                    secret=webhook_config.get('secret')
                                )
                            except Exception as webhook_error:
                                logger.warning(f"Failed to send augmentation failed webhook: {webhook_error}")

    @staticmethod
    async def _execute_job(db: AsyncSession, job_id: str):
        job = await AugmentationService.get_job(db, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Pin dataset_id to prevent ORM relationship sync from clearing it
        pinned_dataset_id = job.dataset_id

        # Get source dataset
        dataset_result = await db.execute(
            select(Dataset).where(Dataset.id == pinned_dataset_id)
        )
        dataset = dataset_result.scalar_one_or_none()
        if not dataset:
            raise ValueError(f"Dataset {pinned_dataset_id} not found")

        # Get non-augmented images (only augment original images)
        images_result = await db.execute(
            select(Image)
            .where(Image.dataset_id == pinned_dataset_id, Image.is_augmented == False)
        )
        images = images_result.scalars().all()

        # Update job
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        job.total_images = len(images) * job.multiplier
        job.dataset_id = pinned_dataset_id
        dataset.status = DatasetStatus.AUGMENTING
        await db.commit()

        # 获取项目的 Webhook 配置
        webhook_config = await _get_augmentation_webhook_config(db, job, pinned_dataset_id)

        # 发送数据增强开始 Webhook
        if webhook_config:
            try:
                await webhook_service.send_augmentation_webhook(
                    webhook_url=webhook_config['url'],
                    event_type='started',
                    job_data=webhook_service.format_augmentation_data(job),
                    secret=webhook_config.get('secret')
                )
            except Exception as e:
                logger.warning(f"Failed to send augmentation started webhook: {e}")

        # Build augmentation pipeline
        pipeline = build_pipeline(job.config)

        # Save augmented images to the SAME dataset
        output_images_dir = Path(dataset.storage_path) / "images"
        output_labels_dir = Path(dataset.storage_path) / "labels"
        output_thumbs_dir = Path(dataset.storage_path) / "thumbnails"
        output_images_dir.mkdir(parents=True, exist_ok=True)
        output_labels_dir.mkdir(parents=True, exist_ok=True)
        output_thumbs_dir.mkdir(parents=True, exist_ok=True)

        processed = 0
        for image in images:
            img_array = ensure_rgb(image.file_path)
            if img_array is None:
                logger.warning(f"Skipping image {image.id}: cannot read")
                continue

            # Load annotations
            img_annotations_result = await db.execute(
                select(Annotation).where(Annotation.image_id == image.id)
            )
            img_annotations = img_annotations_result.scalars().all()
            bboxes = [
                [a.x_center, a.y_center, a.bbox_width, a.bbox_height]
                for a in img_annotations
            ]
            class_labels = [a.class_id for a in img_annotations]

            for i in range(job.multiplier):
                try:
                    if bboxes:
                        result = pipeline(image=img_array, bboxes=bboxes, class_labels=class_labels)
                        aug_image = result["image"]
                        aug_bboxes = result["bboxes"]
                        aug_labels = result["class_labels"]
                    else:
                        result = pipeline(image=img_array, bboxes=[], class_labels=[])
                        aug_image = result["image"]
                        aug_bboxes = []
                        aug_labels = []

                    # Save augmented image
                    aug_filename = generate_filename(image.filename, prefix=f"aug{i}")
                    aug_file_path = output_images_dir / aug_filename
                    aug_thumb_path = output_thumbs_dir / aug_filename

                    save_image(aug_image, str(aug_file_path))
                    create_thumbnail(str(aug_file_path), str(aug_thumb_path))
                    width, height, file_size = get_image_info(str(aug_file_path))

                    aug_image_record = Image(
                        dataset_id=dataset.id,  # Same dataset, not output_dataset
                        filename=aug_filename,
                        original_filename=image.filename,
                        file_path=str(aug_file_path),
                        thumbnail_path=str(aug_thumb_path),
                        width=width,
                        height=height,
                        file_size=file_size,
                        source=ImageSource.LOCAL,
                        is_augmented=True,  # Mark as augmented
                        parent_id=image.id,  # Track original image
                    )
                    db.add(aug_image_record)
                    await db.flush()

                    for bbox, label in zip(aug_bboxes, aug_labels):
                        # Handle both 4-element and 5-element bbox (with conf)
                        cx, cy, bw, bh = bbox[0], bbox[1], bbox[2], bbox[3]

                        # Convert label to int (albumentations may return float)
                        label_int = int(label)

                        class_name = None
                        if dataset.classes and label_int < len(dataset.classes):
                            class_name = dataset.classes[label_int]

                        ann = Annotation(
                            image_id=aug_image_record.id,
                            class_id=label_int,
                            class_name=class_name,
                            x_center=float(cx),
                            y_center=float(cy),
                            bbox_width=float(bw),
                            bbox_height=float(bh),
                        )
                        db.add(ann)

                    processed += 1
                    job.processed_images = processed
                    job.generated_images = processed  # Track generated count
                    dataset.image_count += 1
                    dataset.augmented_count += 1  # Track augmented images separately
                    dataset.annotation_count += len(aug_bboxes)

                    # Send progress via WebSocket
                    await ws_manager.send_message(job_id, {
                        "type": "augmentation_progress",
                        "job_id": job_id,
                        "processed": processed,
                        "total": job.total_images,
                        "percent": round(processed / job.total_images * 100, 1),
                    })

                    if processed % 10 == 0:
                        job.dataset_id = pinned_dataset_id
                        await db.commit()

                except Exception as e:
                    logger.warning(f"Augmentation failed for image {image.id} iter {i}: {e}")

        # Finalize
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.utcnow()
        job.dataset_id = pinned_dataset_id
        dataset.status = DatasetStatus.READY
        await db.commit()

        # 发送数据增强完成 Webhook
        if webhook_config:
            try:
                await db.refresh(job)
                await webhook_service.send_augmentation_webhook(
                    webhook_url=webhook_config['url'],
                    event_type='completed',
                    job_data=webhook_service.format_augmentation_data(job),
                    secret=webhook_config.get('secret')
                )
            except Exception as e:
                logger.warning(f"Failed to send augmentation completed webhook: {e}")

        await ws_manager.send_message(job_id, {
            "type": "augmentation_complete",
            "job_id": job_id,
            "dataset_id": dataset.id,
            "total_generated": processed,
        })
        logger.info(f"Augmentation job {job_id} completed: {processed} images generated in dataset {dataset.id}")

    @staticmethod
    def get_available_transforms() -> List[Dict[str, Any]]:
        """Return list of available transform names with metadata"""
        return [{"name": name} for name in AVAILABLE_TRANSFORMS.keys()]

    @staticmethod
    def get_default_config() -> Dict[str, Any]:
        return DEFAULT_AUGMENTATION_CONFIG


async def _get_augmentation_webhook_config(db: AsyncSession, job: AugmentationJob, dataset_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """获取数据增强任务的 Webhook 配置"""
    ds_id = dataset_id or job.dataset_id
    dataset_result = await db.execute(
        select(Dataset).where(Dataset.id == ds_id)
    )
    dataset = dataset_result.scalar_one_or_none()

    if not dataset or not dataset.project_id:
        logger.debug(f"Augmentation job {job.id}: No project associated with dataset")
        return None

    # 获取项目的 Webhook 配置
    project_result = await db.execute(
        select(Project).where(Project.id == dataset.project_id)
    )
    project = project_result.scalar_one_or_none()

    if not project:
        logger.debug(f"Augmentation job {job.id}: Project not found")
        return None

    if not project.webhook_enabled:
        logger.debug(f"Augmentation job {job.id}: Project webhook not enabled")
        return None

    if not project.webhook_url:
        logger.warning(f"Augmentation job {job.id}: Project webhook enabled but no URL configured")
        return None

    # 检查事件是否订阅
    webhook_events = project.webhook_events or []
    if 'augmentation' not in webhook_events and '*' not in webhook_events:
        logger.debug(f"Augmentation job {job.id}: 'augmentation' event not subscribed in project webhooks: {webhook_events}")
        return None

    logger.info(f"Augmentation job {job.id}: Webhook enabled for events {webhook_events}")
    return {
        'url': project.webhook_url,
        'secret': project.webhook_secret,
        'events': webhook_events
    }

