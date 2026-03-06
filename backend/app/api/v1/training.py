"""
Training API endpoints
"""
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.schemas.schemas import TrainingJobCreate, TrainingJobResponse, SuccessResponse, ModelResponse
from app.services import TrainingService, AVAILABLE_MODELS
from app.models import JobStatus, Model, Dataset, Image, Annotation, TrainingJob
from loguru import logger

router = APIRouter(prefix="/training", tags=["training"])


@router.post("/jobs", response_model=TrainingJobResponse, summary="Create and start training job")
async def create_training_job(
    data: TrainingJobCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    # Validate dataset has annotations before creating training job
    dataset_result = await db.execute(
        select(Dataset).where(Dataset.id == data.dataset_id)
    )
    dataset = dataset_result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Check if dataset has images
    images_result = await db.execute(
        select(Image).where(Image.dataset_id == data.dataset_id)
    )
    images = images_result.scalars().all()
    if not images:
        raise HTTPException(
            status_code=400,
            detail="Dataset has no images. Please add images to the dataset before training."
        )

    # Check if at least some images have annotations
    # 使用 count 查询更高效
    from sqlalchemy import func, exists

    images_with_annotations_result = await db.execute(
        select(func.count(func.distinct(Annotation.image_id)))
        .where(Annotation.image_id.in_([img.id for img in images]))
    )
    images_with_annotations_count = images_with_annotations_result.scalar()

    if images_with_annotations_count == 0:
        raise HTTPException(
            status_code=400,
            detail=f"Dataset has {len(images)} images but none have annotations. "
                   f"Please add annotations to at least some images before training."
        )

    if images_with_annotations_count < len(images) * 0.5:
        logger.warning(
            f"Dataset {data.dataset_id}: Only {images_with_annotations_count}/{len(images)} images have annotations. "
            f"Training with partially labeled data may result in poor model performance."
        )

    job = await TrainingService.create_job(db, data)
    await db.commit()
    # Start training in background thread
    background_tasks.add_task(TrainingService.run_training_job, job.id)
    return job


@router.get("/jobs", summary="List training jobs")
async def list_training_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    db: AsyncSession = Depends(get_db),
):
    skip = (page - 1) * page_size
    jobs = await TrainingService.list_jobs(db, skip=skip, limit=page_size, project_id=project_id)
    return {"items": [TrainingJobResponse.model_validate(j) for j in jobs], "total": len(jobs), "page": page, "page_size": page_size}


@router.get("/jobs/{job_id}", response_model=TrainingJobResponse, summary="Get training job")
async def get_training_job(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await TrainingService.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Training job not found")
    return job


@router.post("/jobs/{job_id}/cancel", response_model=SuccessResponse, summary="Cancel training job")
async def cancel_training_job(job_id: str, db: AsyncSession = Depends(get_db)):
    cancelled = await TrainingService.cancel_job(db, job_id)
    if not cancelled:
        raise HTTPException(status_code=400, detail="Cannot cancel this job")
    await db.commit()
    return {"success": True, "message": "Job cancellation requested"}


@router.post("/jobs/{job_id}/stop", response_model=SuccessResponse, summary="Stop training job and save model")
async def stop_training_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """停止训练任务，保存当前最佳模型"""
    stopped = await TrainingService.stop_job(db, job_id)
    if not stopped:
        raise HTTPException(status_code=400, detail="Cannot stop this job")
    await db.commit()
    return {"success": True, "message": "Training will stop after current epoch"}


@router.get("/available-models", summary="List available base YOLO models")
async def list_available_models():
    return {"models": AVAILABLE_MODELS}


@router.get("/queue/status", summary="Get training queue status")
async def get_queue_status():
    """获取训练队列状态"""
    status = await training_queue.get_queue_status()

    # 构建消息
    if status["active_training_count"] > 0:
        gpu_info = ", ".join([f"GPU{gpu_id}:任务{job_id[:8]}" for gpu_id, job_id in status["current_jobs"].items()])
        message = f"正在训练 {status['active_training_count']}/{status['gpu_count']} 个任务 ({gpu_info})"
    else:
        message = f"空闲 (共{status['gpu_count']}个GPU)"

    if status["queue_size"] > 0:
        message += f", 队列中有 {status['queue_size']} 个任务等待"

    return {
        "is_training": status["is_training"],
        "active_training_count": status["active_training_count"],
        "current_jobs": status["current_jobs"],
        "queue_size": status["queue_size"],
        "gpu_count": status["gpu_count"],
        "message": message
    }


# ─────────────────────────────────────────────
# Model management
# ─────────────────────────────────────────────
@router.get("/models", summary="List trained models")
async def list_models(
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    db: AsyncSession = Depends(get_db),
):
    query = select(Model).order_by(Model.created_at.desc())
    if project_id:
        query = query.where(Model.project_id == project_id)
    result = await db.execute(query)
    models = result.scalars().all()
    return {"models": [ModelResponse.model_validate(m) for m in models], "total": len(models)}


@router.get("/models/{model_id}", response_model=ModelResponse, summary="Get model info")
async def get_model(model_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Model).where(Model.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return model


@router.get("/models/{model_id}/download", summary="Download model weights (best.pt)")
async def download_model(model_id: str, db: AsyncSession = Depends(get_db)):
    """下载模型权重文件（best.pt）"""
    import re

    result = await db.execute(select(Model).where(Model.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    if not Path(model.model_path).exists():
        raise HTTPException(status_code=404, detail="Model file not found on disk")

    # 清理文件名，替换非法字符
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', model.name)

    # 模型路径通常是 best.pt，这是训练中验证集表现最好的模型
    return FileResponse(
        model.model_path,
        filename=f"{safe_name}_best.pt",
        media_type="application/octet-stream",
    )


@router.get("/models/{model_id}/download-package", summary="Download model package (weights + labels)")
async def download_model_package(model_id: str, db: AsyncSession = Depends(get_db)):
    """下载模型包（包含权重文件和标签文件）"""
    import tempfile
    import zipfile
    import json
    import re

    result = await db.execute(select(Model).where(Model.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    if not Path(model.model_path).exists():
        raise HTTPException(status_code=404, detail="Model file not found on disk")

    # 清理文件名，替换非法字符
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', model.name)

    # 创建临时zip文件
    temp_dir = tempfile.mkdtemp()
    zip_path = Path(temp_dir) / f"{safe_name}_package.zip"

    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # 1. 添加模型权重文件 (best.pt)
            model_path = Path(model.model_path)
            zipf.write(model_path, f"weights/best.pt")

            # 2. 添加 last.pt（如果存在）
            last_model_path = model_path.parent / "last.pt"
            if last_model_path.exists():
                zipf.write(last_model_path, f"weights/last.pt")

            # 3. 创建标签文件（classes.txt）
            if model.classes:
                classes_content = "\n".join(model.classes)
                zipf.writestr("labels/classes.txt", classes_content)

            # 4. 创建模型信息文件（model_info.json）
            model_info = {
                "model_name": model.name,
                "model_type": model.model_type,
                "classes": model.classes,
                "num_classes": len(model.classes) if model.classes else 0,
                "map50": float(model.map50) if model.map50 else None,
                "map50_95": float(model.map50_95) if model.map50_95 else None,
                "created_at": model.created_at.isoformat() if model.created_at else None,
                "training_job_id": model.training_job_id,
                "description": "Best model weights are in weights/best.pt, class labels are in labels/classes.txt"
            }
            zipf.writestr("model_info.json", json.dumps(model_info, indent=2, ensure_ascii=False))

            # 5. 创建使用说明（README.md）
            readme_content = f"""# {model.name} - 模型包

## 文件说明

- `weights/best.pt`: 最佳模型权重（验证集上表现最好）
- `weights/last.pt`: 最后一个epoch的模型权重（如果存在）
- `labels/classes.txt`: 类别标签文件（每行一个类别）
- `model_info.json`: 模型详细信息

## 模型信息

- **类别数量**: {len(model.classes) if model.classes else 0}
- **mAP50**: {f"{model.map50*100:.2f}%" if model.map50 else "N/A"}
- **mAP50-95**: {f"{model.map50_95*100:.2f}%" if model.map50_95 else "N/A"}

## 类别列表

{chr(10).join([f"{i}. {cls}" for i, cls in enumerate(model.classes)]) if model.classes else "无"}

## 使用方法

### Python (Ultralytics)

```python
from ultralytics import YOLO

# 加载模型
model = YOLO('weights/best.pt')

# 推理
results = model.predict('your_image.jpg')

# 读取类别标签
with open('labels/classes.txt', 'r', encoding='utf-8') as f:
    classes = [line.strip() for line in f.readlines()]
```

### 命令行

```bash
# 推理单张图片
yolo predict model=weights/best.pt source=your_image.jpg

# 推理视频
yolo predict model=weights/best.pt source=your_video.mp4
```

## 注意事项

- `best.pt` 是训练过程中验证集上表现最好的模型，推荐使用
- `last.pt` 是最后一个epoch的模型，可能过拟合
- 类别标签的顺序与训练时一致，请勿修改
"""
            zipf.writestr("README.md", readme_content)

        # 返回zip文件
        return FileResponse(
            str(zip_path),
            filename=f"{safe_name}_package.zip",
            media_type="application/zip",
            background=None  # 不使用background task，确保文件传输完成
        )

    except Exception as e:
        logger.error(f"Failed to create model package: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create model package: {str(e)}")


@router.post("/models/fix-project-ids", summary="Backfill missing project_id on models")
async def fix_model_project_ids(db: AsyncSession = Depends(get_db)):
    """回填模型缺失的 project_id（通过 training_job -> dataset -> project 关联）"""
    result = await db.execute(
        select(Model).where(Model.project_id.is_(None), Model.training_job_id.isnot(None))
    )
    models = result.scalars().all()

    fixed = 0
    for model in models:
        job_result = await db.execute(
            select(TrainingJob).where(TrainingJob.id == model.training_job_id)
        )
        job = job_result.scalar_one_or_none()
        if not job:
            continue

        ds_result = await db.execute(
            select(Dataset).where(Dataset.id == job.dataset_id)
        )
        ds = ds_result.scalar_one_or_none()
        if ds and ds.project_id:
            model.project_id = ds.project_id
            fixed += 1

    await db.commit()
    logger.info(f"Fixed project_id for {fixed}/{len(models)} models")
    return {"success": True, "message": f"已修复 {fixed} 个模型的 project_id", "fixed": fixed, "total_orphans": len(models)}


