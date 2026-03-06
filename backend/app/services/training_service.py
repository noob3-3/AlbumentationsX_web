"""
Training service using Ultralytics YOLO
"""
import os
import shutil
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.core.database import AsyncSessionLocal, create_background_session_maker
from app.core.websocket import ws_manager
from app.models import Dataset, Image, Annotation, TrainingJob, Model, JobStatus, Project
from app.schemas.schemas import TrainingJobCreate
from app.utils import build_yolo_dataset_yaml, write_yolo_annotation
from app.services.webhook_service import webhook_service
from app.services.pretrained_model_service import PretrainedModelService

AVAILABLE_MODELS = [
    "yolo11n.pt", "yolo11s.pt", "yolo11m.pt", "yolo11l.pt", "yolo11x.pt",
    "yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt", "yolov8x.pt",
    "yolo11n-det.pt", "yolo11s-det.pt",
]


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


class TrainingService:

    @staticmethod
    async def create_job(db: AsyncSession, data: TrainingJobCreate) -> TrainingJob:
        # 如果是继续训练，验证基础模型存在
        if data.resume_training and data.base_model_id:
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

        # 保存继续训练和类别增强参数
        if data.resume_training:
            job.extra_params['resume_training'] = True
            job.extra_params['base_model_id'] = data.base_model_id

        if data.class_weights:
            job.extra_params['class_weights'] = data.class_weights

        if data.focus_classes:
            job.extra_params['focus_classes'] = data.focus_classes

        # 保存早停参数
        if data.patience is not None:
            job.extra_params['patience'] = data.patience

        if data.save_period is not None:
            job.extra_params['save_period'] = data.save_period

        # 保存 Webhook 推送配置
        if hasattr(data, 'enable_webhook'):
            job.extra_params['enable_webhook'] = data.enable_webhook

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
    async def run_training_job(job_id: str, allocated_gpu_id: Optional[int] = None):
        """Run training in a thread pool (YOLO training is synchronous)

        Args:
            job_id: Training job ID
            allocated_gpu_id: GPU ID allocated by queue manager (for CUDA_VISIBLE_DEVICES)
        """
        loop = asyncio.get_event_loop()
        # Pass the main event loop and allocated GPU ID to the training function
        await loop.run_in_executor(None, _run_training_sync, job_id, loop, allocated_gpu_id)

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

        # Calculate split - ensure at least 10% for training
        val_split = min(job.val_split, 0.9)  # Cap at 90% validation max
        train_count = max(1, int(len(all_images) * (1 - val_split)))

        # Split: train first, then val
        train_images = all_images[:train_count]
        val_images = all_images[train_count:]

        logger.info(
            f"Dataset split: {len(train_images)} training, {len(val_images)} validation "
            f"(split ratio: {1-val_split:.1%} train, {val_split:.1%} val)"
        )

        # Output structure
        output_dir = settings.EXPORT_DIR / f"train_{job.id}"
        for split in ["train", "val"]:
            (output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
            (output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

        for split_name, split_images in [("train", train_images), ("val", val_images)]:
            for img in split_images:
                # Copy image
                src = Path(img.file_path)
                if not src.exists():
                    continue
                dst_img = output_dir / "images" / split_name / img.filename
                shutil.copy2(str(src), str(dst_img))

                # Write annotations
                anns_result = await db.execute(
                    select(Annotation).where(Annotation.image_id == img.id)
                )
                anns = anns_result.scalars().all()

                label_filename = Path(img.filename).stem + ".txt"
                label_path = output_dir / "labels" / split_name / label_filename
                ann_list = [
                    {
                        "class_id": a.class_id,
                        "x_center": a.x_center,
                        "y_center": a.y_center,
                        "bbox_width": a.bbox_width,
                        "bbox_height": a.bbox_height,
                    }
                    for a in anns
                ]
                write_yolo_annotation(str(label_path), ann_list)

        # Build dataset.yaml
        classes = dataset.classes or []
        yaml_path = build_yolo_dataset_yaml(
            dataset_dir=str(output_dir),
            classes=classes,
            train_path="images/train",
            val_path="images/val",
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


def _run_training_sync(job_id: str, main_loop, allocated_gpu_id: Optional[int] = None):
    """Synchronous training function (runs in thread pool)

    Args:
        job_id: Training job ID
        main_loop: Main event loop
        allocated_gpu_id: GPU ID allocated by queue manager (for CUDA_VISIBLE_DEVICES)
    """
    import asyncio
    import nest_asyncio

    # **关键修复**: 设置 CUDA_VISIBLE_DEVICES 环境变量
    # 这样PyTorch只能看到分配给它的那个GPU，不会在其他GPU上初始化CUDA上下文
    original_cuda_visible_devices = None
    if allocated_gpu_id is not None:
        original_cuda_visible_devices = os.environ.get('CUDA_VISIBLE_DEVICES')
        os.environ['CUDA_VISIBLE_DEVICES'] = str(allocated_gpu_id)
        logger.info(f"Job {job_id}: Set CUDA_VISIBLE_DEVICES={allocated_gpu_id} (original: {original_cuda_visible_devices})")

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
                                error_message = "GPU显存不足，训练失败。建议：1) 减小batch size 2) 减小图片尺寸 3) 等待其他训练任务完成"
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
        if allocated_gpu_id is not None:
            if original_cuda_visible_devices is not None:
                os.environ['CUDA_VISIBLE_DEVICES'] = original_cuda_visible_devices
                logger.debug(f"Job {job_id}: Restored CUDA_VISIBLE_DEVICES={original_cuda_visible_devices}")
            else:
                # 如果原来没有设置，则删除
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

    await ws_manager.send_message(job_id, {
        "type": "training_started",
        "job_id": job_id,
        "message": "Training started",
        "data_info": data_stats
    })

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

    # 如果是继续训练，使用基础模型
    if job.extra_params.get('resume_training') and job.extra_params.get('base_model_id'):
        base_model_id = job.extra_params['base_model_id']
        base_model_result = await db.execute(
            select(Model).where(Model.id == base_model_id)
        )
        base_model = base_model_result.scalar_one_or_none()
        if base_model and Path(base_model.model_path).exists():
            initial_model = base_model.model_path
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
                # 如果获取失败，仍然使用原始模型名，让Ultralytics自己处理
                initial_model = job.model_name

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
                        return bool(j.extra_params and j.extra_params.get('stop_requested'))
            except Exception as e:
                logger.warning(f"Failed to update training job progress: {e}")
            return False

        try:
            future = asyncio.run_coroutine_threadsafe(_update_db_and_check_stop(), main_loop)
            stop_requested = future.result(timeout=10)
            if stop_requested:
                logger.info(f"Job {job_id}: Stop requested, terminating training after this epoch")
                trainer.stop = True
        except Exception as e:
            logger.debug(f"Failed to schedule progress update: {e}")

        # Send websocket update
        async def _send_ws():
            try:
                await ws_manager.send_message(job_id, {
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
                logger.warning(f"Failed to send websocket message: {e}")

        try:
            asyncio.run_coroutine_threadsafe(_send_ws(), main_loop)
        except Exception as e:
            logger.debug(f"Failed to schedule websocket update: {e}")

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

                # 通过WebSocket发送验证指标更新
                async def _send_val_ws():
                    try:
                        await ws_manager.send_message(job_id, {
                            "type": "validation_metrics",
                            "job_id": job_id,
                            "epoch": metrics_history[-1].get("epoch"),
                            "map50": map50,
                            "map50_95": map50_95,
                            "metrics_history": metrics_history.copy(),
                        })
                    except Exception as e:
                        logger.warning(f"Failed to send validation metrics: {e}")

                try:
                    asyncio.run_coroutine_threadsafe(_send_val_ws(), main_loop)
                except Exception as e:
                    logger.debug(f"Failed to schedule validation update: {e}")

    model.add_callback("on_train_epoch_end", on_train_epoch_end)
    model.add_callback("on_val_end", on_val_end)

    # 动态计算最优 worker 数量
    # 考虑因素：CPU 核心数、batch size、共享内存
    import os
    cpu_count = os.cpu_count() or 4

    # 根据 batch size 估算每个 worker 需要的内存（经验值）
    # 较小的 batch size 可以支持更多 workers
    if job.batch_size <= 8:
        max_workers_by_batch = 8
    elif job.batch_size <= 16:
        max_workers_by_batch = 6
    else:
        max_workers_by_batch = 4

    # 综合考虑 CPU 和 batch size
    optimal_workers = min(
        cpu_count - 1,  # 留一个核心给主进程
        max_workers_by_batch,
        8  # 最大不超过 8
    )

    # 如果设置了共享内存小于 2GB，减少 workers 以避免内存不足
    # 可以通过环境变量 SHM_SIZE_GB 传入
    shm_size_gb = float(os.environ.get('SHM_SIZE_GB', '4'))
    if shm_size_gb < 2:
        optimal_workers = min(optimal_workers, 2)
        logger.warning(f"Shared memory is small ({shm_size_gb}GB), limiting workers to {optimal_workers}")

    logger.info(f"Using {optimal_workers} data loading workers (CPU cores: {cpu_count}, batch size: {job.batch_size})")

    # Train
    train_args = {
        "data": yaml_path,
        "epochs": job.epochs,
        "batch": job.batch_size,
        "imgsz": job.img_size,
        "lr0": job.learning_rate,
        "device": device,
        "project": str(output_dir),
        "name": "train",
        "exist_ok": True,
        "verbose": True,
        "plots": True,
        "save": True,
        "cache": False,  # 禁用内存缓存以节省共享内存
        "workers": optimal_workers,  # 动态调整的 worker 数量
        "patience": job.extra_params.get('patience', 50),  # 早停耐心值
        "save_period": job.extra_params.get('save_period', -1),  # 保存周期
    }

    # 继续训练：从已有模型恢复
    if job.extra_params.get('resume_training'):
        train_args['resume'] = True
        logger.info("Resuming training from existing model")

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
        # 合并用户自定义参数
        for key, value in job.extra_params.items():
            if key not in ['resume_training', 'base_model_id', 'class_weights', 'focus_classes', 'patience', 'save_period', 'enable_webhook']:
                train_args[key] = value

    logger.info(f"Starting training with args: patience={train_args.get('patience')}, save_period={train_args.get('save_period')}")

    # 训练前清理显存
    await _cleanup_gpu_memory()

    try:
        results = model.train(**train_args)
    except Exception as train_error:
        # 训练失败时清理显存
        logger.error(f"Training failed: {train_error}")
        await _cleanup_gpu_memory()

        # 重新抛出异常以便外层捕获
        raise

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
