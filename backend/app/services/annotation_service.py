"""
Annotation service for manual and automatic annotation
"""
from pathlib import Path
from typing import Optional, List
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, exists
from sqlalchemy.orm import selectinload
from PIL import Image as PILImage
import numpy as np

from app.models import Image, Annotation, Dataset, Model, AnnotationStatus
from app.schemas.schemas import AnnotationCreate


class AnnotationService:

    @staticmethod
    async def update_image_annotations(
        db: AsyncSession,
        image_id: str,
        annotations: List[AnnotationCreate],
        status: AnnotationStatus = AnnotationStatus.MANUALLY_ANNOTATED
    ) -> Image:
        """更新图片的标注"""
        # Get image
        result = await db.execute(select(Image).where(Image.id == image_id))
        image = result.scalar_one_or_none()
        if not image:
            raise ValueError(f"Image {image_id} not found")

        # Delete existing annotations
        existing = await db.execute(select(Annotation).where(Annotation.image_id == image_id))
        for ann in existing.scalars().all():
            await db.delete(ann)

        # Add new annotations
        for ann_data in annotations:
            ann = Annotation(
                image_id=image_id,
                class_id=ann_data.class_id,
                class_name=ann_data.class_name,
                x_center=ann_data.x_center,
                y_center=ann_data.y_center,
                bbox_width=ann_data.bbox_width,
                bbox_height=ann_data.bbox_height,
                confidence=ann_data.confidence,
            )
            db.add(ann)

        # Update image annotation status
        image.annotation_status = status

        # Update dataset classes
        await AnnotationService._update_dataset_classes(db, image.dataset_id)

        await db.flush()

        # Reload image with annotations eagerly loaded
        result = await db.execute(
            select(Image)
            .where(Image.id == image_id)
            .options(selectinload(Image.annotations))
        )
        image = result.scalar_one()
        return image

    @staticmethod
    async def auto_annotate_images(
        db: AsyncSession,
        dataset_id: str,
        model_id: str,
        confidence_threshold: float = 0.5,
        image_ids: Optional[List[str]] = None,
        use_pretrained: bool = False,
        pretrained_model_name: Optional[str] = None,
        job_id: Optional[str] = None,  # 用于WebSocket通信
        annotate_all: bool = False,  # 是否标注所有图片（包括已标注的）
        include_augmented: bool = False,  # 是否包含增强数据
    ) -> dict:
        """使用模型自动标注图片"""
        from ultralytics import YOLO
        from app.services.pretrained_model_service import PretrainedModelService
        from app.core.config import settings
        from app.core.websocket import ws_manager
        from app.services.annotation_job_manager import annotation_job_manager

        # Determine which model to use
        if use_pretrained and pretrained_model_name:
            # Use pretrained model
            if not PretrainedModelService.is_pretrained_model(pretrained_model_name):
                raise ValueError(f"Unknown pretrained model: {pretrained_model_name}")

            logger.info(f"Using pretrained model: {pretrained_model_name}")

            # 发送开始消息
            if job_id:
                await ws_manager.send_message(job_id, {
                    "type": "model_loading",
                    "message": f"正在加载预训练模型: {pretrained_model_name}",
                    "status": "loading"
                })

            # Ensure model is available (download if needed)
            try:
                model_path = PretrainedModelService.ensure_model_available(
                    pretrained_model_name,
                    settings.MODEL_DIR
                )
                model = YOLO(str(model_path))
            except Exception as e:
                # If local download fails, let Ultralytics handle it
                logger.warning(f"Local download failed, using Ultralytics auto-download: {e}")
                model = YOLO(pretrained_model_name)
        else:
            # Use custom trained model
            if job_id:
                await ws_manager.send_message(job_id, {
                    "type": "model_loading",
                    "message": "正在加载自定义模型...",
                    "status": "loading"
                })

            model_result = await db.execute(select(Model).where(Model.id == model_id))
            model_obj = model_result.scalar_one_or_none()
            if not model_obj:
                raise ValueError(f"Model {model_id} not found")

            if not Path(model_obj.model_path).exists():
                raise ValueError(f"Model file not found: {model_obj.model_path}")

            model = YOLO(model_obj.model_path)

        # 检测并选择设备（GPU优先）
        device = 'cpu'
        try:
            import torch
            if torch.cuda.is_available():
                device = '0'  # 使用第一个GPU
                gpu_name = torch.cuda.get_device_name(0)
                logger.info(f"🚀 GPU detected: {gpu_name}, using CUDA for inference")
                if job_id:
                    await ws_manager.send_message(job_id, {
                        "type": "device_info",
                        "message": f"使用 GPU 加速推理: {gpu_name}",
                        "device": "cuda",
                        "gpu_name": gpu_name,
                        "status": "info"
                    })
            else:
                logger.info("ℹ️ No GPU available, using CPU for inference")
                if job_id:
                    await ws_manager.send_message(job_id, {
                        "type": "device_info",
                        "message": "使用 CPU 进行推理",
                        "device": "cpu",
                        "status": "info"
                    })
        except ImportError:
            logger.warning("PyTorch not available, using CPU")

        # Get images to annotate
        query = select(Image).where(Image.dataset_id == dataset_id)

        # Filter by specific image IDs if provided
        if image_ids:
            query = query.where(Image.id.in_(image_ids))
        else:
            # Filter by annotation status
            if not annotate_all:
                # 未标注范围：包含 UNANNOTATED，以及「已标注但无标注框」的图片
                # （上次自动标注未检测到目标时会被标为 AUTO_ANNOTATED，用户仍视为未标注）
                has_annotations = exists().where(Annotation.image_id == Image.id)
                query = query.where(
                    or_(
                        Image.annotation_status == AnnotationStatus.UNANNOTATED,
                        and_(
                            Image.annotation_status.in_([
                                AnnotationStatus.AUTO_ANNOTATED,
                                AnnotationStatus.MANUALLY_ANNOTATED,
                            ]),
                            ~has_annotations,  # 无标注框
                        ),
                    )
                )
            # If annotate_all is True, don't filter by annotation status

            # Filter augmented images
            if not include_augmented:
                # Only annotate original (non-augmented) images
                query = query.where(Image.is_augmented == False)

        result = await db.execute(query)
        images = result.scalars().all()
        total_images = len(images)

        if total_images == 0:
            # 调试：统计各类图片数量，便于排查为何为 0
            from sqlalchemy import func
            debug_query = (
                select(Image.annotation_status, func.count(Image.id))
                .where(Image.dataset_id == dataset_id)
            )
            if not include_augmented:
                debug_query = debug_query.where(Image.is_augmented == False)
            debug_query = debug_query.group_by(Image.annotation_status)
            count_result = await db.execute(debug_query)
            stats = dict(count_result.all())
            logger.warning(
                f"⚠️ Auto-annotation found 0 images for dataset {dataset_id}. "
                f"Status counts (include_augmented={include_augmented}): {stats}"
            )
        success_count = 0
        failed_count = 0

        # 创建任务状态（用于页面刷新后重连）
        if job_id:
            model_name = pretrained_model_name if use_pretrained else (model_obj.name if not use_pretrained and model_obj else None)
            annotation_job_manager.create_job(
                job_id=job_id,
                dataset_id=dataset_id,
                total=total_images,
                model_name=model_name,
                use_pretrained=use_pretrained
            )

        # 发送开始标注消息
        if job_id:
            logger.info(f"Starting auto-annotation for job {job_id}, {total_images} images")
            await ws_manager.send_message(job_id, {
                "type": "annotation_started",
                "message": f"开始标注 {total_images} 张图片",
                "total": total_images,
                "status": "processing"
            })

        for idx, img in enumerate(images, 1):
            try:
                # 更新任务状态
                if job_id:
                    annotation_job_manager.update_progress(
                        job_id=job_id,
                        current=idx,
                        success_count=success_count,
                        failed_count=failed_count
                    )

                # 发送处理进度
                if job_id:
                    await ws_manager.send_message(job_id, {
                        "type": "annotation_progress",
                        "current": idx,
                        "total": total_images,
                        "image_name": img.filename,
                        "success_count": success_count,
                        "failed_count": failed_count,
                        "percent": round((idx - 1) / total_images * 100, 1),
                        "status": "processing"
                    })

                logger.info(f"Processing image {idx}/{total_images}: {img.filename}")

                # Run inference (使用检测到的设备)
                results = model.predict(
                    img.file_path,
                    conf=confidence_threshold,
                    device=device,
                    verbose=False
                )

                if not results or len(results) == 0:
                    continue

                result = results[0]
                if result.boxes is None or len(result.boxes) == 0:
                    # No detections, mark as auto-annotated with empty annotations
                    img.annotation_status = AnnotationStatus.AUTO_ANNOTATED
                    await db.commit()  # 立即提交
                    success_count += 1

                    # 发送单张完成消息
                    if job_id:
                        await ws_manager.send_message(job_id, {
                            "type": "image_completed",
                            "image_name": img.filename,
                            "detections": 0,
                            "status": "success"
                        })
                    continue

                # Delete existing annotations
                existing = await db.execute(select(Annotation).where(Annotation.image_id == img.id))
                for ann in existing.scalars().all():
                    await db.delete(ann)

                # Add new annotations
                boxes = result.boxes
                detection_count = len(boxes)

                for box in boxes:
                    # Get YOLO normalized format
                    xywhn = box.xywhn[0].cpu().numpy()  # [x_center, y_center, width, height]
                    cls_id = int(box.cls[0].cpu().numpy())
                    conf = float(box.conf[0].cpu().numpy())

                    # Get class name
                    class_name = model.names.get(cls_id, f"class_{cls_id}")

                    ann = Annotation(
                        image_id=img.id,
                        class_id=cls_id,
                        class_name=class_name,
                        x_center=float(xywhn[0]),
                        y_center=float(xywhn[1]),
                        bbox_width=float(xywhn[2]),
                        bbox_height=float(xywhn[3]),
                        confidence=conf,
                    )
                    db.add(ann)

                img.annotation_status = AnnotationStatus.AUTO_ANNOTATED

                # 每处理完一张图片就提交，避免SQLite锁定
                await db.commit()
                success_count += 1

                # 发送单张完成消息
                if job_id:
                    await ws_manager.send_message(job_id, {
                        "type": "image_completed",
                        "image_name": img.filename,
                        "detections": detection_count,
                        "status": "success"
                    })


            except Exception as e:
                logger.error(f"Failed to auto-annotate image {img.id}: {e}")
                # 回滚当前图片的更改
                await db.rollback()
                failed_count += 1

                # 发送失败消息
                if job_id:
                    await ws_manager.send_message(job_id, {
                        "type": "image_failed",
                        "image_name": img.filename,
                        "error": str(e),
                        "status": "error"
                    })

        # Update dataset classes (最后统一更新)
        try:
            await AnnotationService._update_dataset_classes(db, dataset_id)
            await db.commit()
        except Exception as e:
            logger.warning(f"Failed to update dataset classes: {e}")
            await db.rollback()

        # 发送完成消息
        if job_id:
            logger.info(f"Auto-annotation completed for job {job_id}: success={success_count}, failed={failed_count}")

            # 标记任务完成
            annotation_job_manager.complete_job(job_id, success=True)

            await ws_manager.send_message(job_id, {
                "type": "annotation_completed",
                "message": "自动标注完成",
                "success_count": success_count,
                "failed_count": failed_count,
                "total": total_images,
                "percent": 100,
                "status": "completed"
            })

        return {
            "success": True,
            "success_count": success_count,
            "failed_count": failed_count,
            "total": len(images),
        }

    @staticmethod
    async def _update_dataset_classes(db: AsyncSession, dataset_id: str):
        """从标注中更新数据集的类别列表"""
        result = await db.execute(
            select(Annotation.class_name)
            .join(Image, Annotation.image_id == Image.id)
            .where(Image.dataset_id == dataset_id)
            .distinct()
        )
        class_names = [row[0] for row in result.all() if row[0]]

        dataset_result = await db.execute(select(Dataset).where(Dataset.id == dataset_id))
        dataset = dataset_result.scalar_one_or_none()
        if dataset:
            dataset.classes = sorted(class_names)
            await db.flush()

    @staticmethod
    async def get_image_with_annotations(db: AsyncSession, image_id: str) -> Optional[Image]:
        """获取图片及其标注"""
        result = await db.execute(
            select(Image)
            .where(Image.id == image_id)
            .options(selectinload(Image.annotations))
        )
        image = result.scalar_one_or_none()
        return image

    @staticmethod
    async def delete_annotations(db: AsyncSession, image_id: str):
        """删除图片的所有标注"""
        result = await db.execute(select(Annotation).where(Annotation.image_id == image_id))
        for ann in result.scalars().all():
            await db.delete(ann)

        # Update image status
        img_result = await db.execute(select(Image).where(Image.id == image_id))
        img = img_result.scalar_one_or_none()
        if img:
            img.annotation_status = AnnotationStatus.UNANNOTATED
            await AnnotationService._update_dataset_classes(db, img.dataset_id)

        await db.commit()

    @staticmethod
    async def batch_replace_classes(
        db: AsyncSession,
        dataset_id: str,
        class_mapping: dict
    ) -> dict:
        """
        批量替换数据集中的类别名称

        Args:
            dataset_id: 数据集ID
            class_mapping: 类别映射 {"old_name": "new_name"}

        Returns:
            {"updated_count": int, "message": str}
        """
        logger.info(f"Batch replacing classes for dataset {dataset_id}: {class_mapping}")

        # 获取数据集的所有图片
        images_result = await db.execute(
            select(Image).where(Image.dataset_id == dataset_id)
        )
        images = images_result.scalars().all()

        updated_count = 0

        for image in images:
            # 获取该图片的所有标注
            annotations_result = await db.execute(
                select(Annotation).where(Annotation.image_id == image.id)
            )
            annotations = annotations_result.scalars().all()

            for annotation in annotations:
                # 如果标注的类别在映射中，则替换
                if annotation.class_name in class_mapping:
                    old_name = annotation.class_name
                    new_name = class_mapping[old_name]
                    annotation.class_name = new_name
                    updated_count += 1
                    logger.debug(f"Updated annotation {annotation.id}: {old_name} -> {new_name}")

        # 提交更改
        await db.commit()

        # 更新数据集的类别列表
        await AnnotationService._update_dataset_classes(db, dataset_id)

        logger.info(f"Batch replace completed: {updated_count} annotations updated")

        return {
            "success": True,
            "updated_count": updated_count,
            "message": f"成功替换 {updated_count} 个标注的类别"
        }
