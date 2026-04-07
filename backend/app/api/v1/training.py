"""
Training API endpoints
"""
import asyncio
import shutil
from app.core.config import settings
from app.core.database import get_db
from app.models import JobStatus, Model, ModelValidation, Dataset, Image, Annotation, TrainingJob
from app.models.models import gen_uuid
from app.schemas.schemas import TrainingJobCreate, TrainingJobResponse, SuccessResponse, ModelResponse
from app.services import TrainingService, AVAILABLE_MODELS
from app.services.model_export_service import export_pt_to_onnx
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, File, Form, UploadFile
from fastapi.responses import FileResponse
from loguru import logger
from pathlib import Path
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

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

    # Validate validation dataset if using separate validation set
    if getattr(data, 'use_validation_dataset', False) and getattr(data, 'validation_dataset_id', None):
        val_ds_result = await db.execute(
            select(Dataset).where(Dataset.id == data.validation_dataset_id)
        )
        val_ds = val_ds_result.scalar_one_or_none()
        if not val_ds:
            raise HTTPException(status_code=404, detail="Validation dataset not found")
        if data.validation_dataset_id == data.dataset_id:
            raise HTTPException(status_code=400, detail="Validation dataset cannot be the same as training dataset")

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

    # 多卡 DDP：batch_size 会被平分到每张卡，必须 >= GPU 数量
    is_multi_gpu = data.device and "," in str(data.device)
    if is_multi_gpu:
        gpu_count = len(str(data.device).split(","))
        if data.batch_size < gpu_count:
            raise HTTPException(
                status_code=400,
                detail=f"双卡(0,1)训练时 batch_size 会平分到每张卡，当前 batch_size={data.batch_size} 会导致每卡为 0。请将 batch_size 设为 ≥ {gpu_count}。",
            )

    # 显存风险校验：大尺寸 + 大 batch 易 OOM
    # 双卡(0,1)时允许 batch 2；单卡时大尺寸仅允许 batch 1
    img_w = data.img_size
    img_h = getattr(data, "img_size_2", None) or data.img_size
    img_pixels = img_w * img_h
    max_batch = 2 if is_multi_gpu else 1
    if img_pixels > 2048 * 2048 and data.batch_size > max_batch:
        raise HTTPException(
            status_code=400,
            detail=f"图片尺寸 {img_w}×{img_h} 配合 batch_size={data.batch_size} 显存压力大。"
            f"大尺寸时请将 batch_size 设为 {max_batch}，或选用双卡(0,1)后尝试 batch 2。",
        )
    if img_pixels > 1280 * 1280 and data.batch_size > 4:
        raise HTTPException(
            status_code=400,
            detail=f"图片尺寸 {img_w}×{img_h} 配合 batch_size={data.batch_size} 显存压力大。建议 batch_size 降至 2-4。",
        )

    try:
        job = await TrainingService.create_job(db, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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


@router.get("/jobs/{job_id}/download-best", summary="Download best.pt during or after training")
async def download_job_training_best(job_id: str, db: AsyncSession = Depends(get_db)):
    """下载当前训练 run 目录下的 best.pt（训练中即可下载，为截至当前的验证最佳快照）"""
    import re

    job = await TrainingService.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Training job not found")

    best_path = settings.MODEL_DIR / job_id / "train" / "weights" / "best.pt"
    if not best_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="尚未生成 best.pt。请等待至少完成一轮带验证的训练后再试。",
        )

    safe_name = re.sub(r'[<>:"/\\|?*]', "_", job.name)
    return FileResponse(
        str(best_path),
        filename=f"{safe_name}_training_best.pt",
        media_type="application/octet-stream",
    )


@router.get("/jobs/{job_id}/export-onnx", summary="Export training best.pt to ONNX (download)")
async def export_job_weights_onnx(
        job_id: str,
        opset: int = Query(18, ge=9, le=23, description="ONNX opset"),
        dynamic: bool = Query(False, description="动态输入尺寸；False 为固定尺寸，利于部分部署端"),
        batch: int = Query(1, ge=1, le=64, description="导出 batch 维度"),
        simplify: bool = Query(False, description="是否 onnxsim 简化图（需安装 onnxsim）"),
        half: bool = Query(False, description="FP16 导出"),
        imgsz: Optional[int] = Query(None, ge=32, le=8192, description="导出输入边长；不传则沿用模型默认"),
        db: AsyncSession = Depends(get_db),
):
    """将当前训练任务 run 目录下的 best.pt 在 CPU 上转为 ONNX 并下载。"""
    import re

    job = await TrainingService.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Training job not found")

    best_path = settings.MODEL_DIR / job_id / "train" / "weights" / "best.pt"
    if not best_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="尚未生成 best.pt，无法导出 ONNX。请等待至少完成一轮带验证的训练。",
        )

    try:
        onnx_path = await asyncio.to_thread(
            export_pt_to_onnx,
            str(best_path),
            opset=opset,
            dynamic=dynamic,
            batch=batch,
            simplify=simplify,
            half=half,
            imgsz=imgsz,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("ONNX export failed for job {}", job_id)
        raise HTTPException(status_code=500, detail=f"ONNX 导出失败: {e}")

    safe_name = re.sub(r'[<>:"/\\|?*]', "_", job.name)
    return FileResponse(
        str(onnx_path),
        filename=f"{safe_name}_training_best.onnx",
        media_type="application/octet-stream",
    )


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
@router.post("/models/import", response_model=ModelResponse, summary="Import model from file")
async def import_model(
    file: UploadFile = File(..., description="模型权重文件 (.pt)"),
    name: str = Form(..., min_length=1, max_length=255, description="模型名称"),
    project_id: Optional[str] = Form(None, description="所属项目ID"),
    classes_str: Optional[str] = Form(None, description="类别列表，逗号分隔"),
    classes_file: Optional[UploadFile] = File(None, description="类别文件 classes.txt，每行一个类别"),
    db: AsyncSession = Depends(get_db),
):
    """导入 YOLO 模型权重文件 (.pt) 到模型库"""
    if not file.filename or not file.filename.lower().endswith(".pt"):
        raise HTTPException(status_code=422, detail="请上传 .pt 格式的模型权重文件")

    # 解析类别
    classes = []
    if classes_str and classes_str.strip():
        classes = [c.strip() for c in classes_str.split(",") if c.strip()]
    elif classes_file and classes_file.filename:
        try:
            content = await classes_file.read()
            classes = [line.strip() for line in content.decode("utf-8").strip().split("\n") if line.strip()]
        except Exception as e:
            logger.warning(f"Failed to parse classes file: {e}")

    # 创建导入目录并保存文件
    model_id = gen_uuid()
    import_dir = settings.MODEL_DIR / "imported" / model_id
    import_dir.mkdir(parents=True, exist_ok=True)
    dest_path = import_dir / "best.pt"

    try:
        file_size = 0
        max_size = 500 * 1024 * 1024  # 500MB
        with open(dest_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                file_size += len(chunk)
                if file_size > max_size:
                    dest_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="模型文件超过 500MB 限制")
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save imported model: {e}")
        dest_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"保存文件失败: {str(e)}")

    # 尝试从模型中提取类别（如果未手动指定）
    if not classes:
        try:
            from ultralytics import YOLO
            yolo = YOLO(str(dest_path))
            if hasattr(yolo, "model") and hasattr(yolo.model, "names") and yolo.model.names:
                classes = list(yolo.model.names.values())
                logger.info(f"Extracted {len(classes)} classes from model: {classes}")
        except Exception as e:
            logger.warning(f"Could not extract classes from model: {e}")

    # 创建 Model 记录
    model = Model(
        id=model_id,
        name=name.strip(),
        project_id=project_id or None,
        training_job_id=None,
        model_path=str(dest_path),
        model_type="yolo",
        classes=classes if classes else None,
        map50=None,
        map50_95=None,
        file_size=file_size,
        is_deployed=False,
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)
    logger.info(f"Imported model: {name} (id={model_id}, classes={len(classes) if classes else 0})")
    return model


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


@router.delete("/models/{model_id}", response_model=SuccessResponse, summary="Delete model")
async def delete_model(model_id: str, db: AsyncSession = Depends(get_db)):
    """删除模型（已部署的模型不可删除）"""
    result = await db.execute(select(Model).where(Model.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    if model.is_deployed:
        raise HTTPException(status_code=400, detail="无法删除已部署的模型，请先停止部署")
    # 删除关联的验证记录（避免 model_id NOT NULL 约束冲突）
    await db.execute(delete(ModelValidation).where(ModelValidation.model_id == model_id))
    # 删除模型文件
    if model.model_path and Path(model.model_path).exists():
        try:
            model_path = Path(model.model_path)
            model_path.unlink(missing_ok=True)
            run_dir = model_path.parent
            last_pt = run_dir / "last.pt"
            if last_pt.exists():
                last_pt.unlink(missing_ok=True)
            # 导入的模型在 imported/{id}/ 目录下，删除整个目录
            if "imported" in str(run_dir):
                if run_dir.exists():
                    shutil.rmtree(run_dir, ignore_errors=True)
        except OSError as e:
            logger.warning(f"Failed to delete model file: {e}")
    await db.delete(model)
    await db.commit()
    return {"success": True, "message": "Model deleted"}


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


@router.get("/models/{model_id}/export-onnx", summary="Export model weights to ONNX (download)")
async def export_registered_model_onnx(
        model_id: str,
        opset: int = Query(18, ge=9, le=23, description="ONNX opset"),
        dynamic: bool = Query(False, description="动态输入尺寸"),
        batch: int = Query(1, ge=1, le=64, description="导出 batch"),
        simplify: bool = Query(False, description="onnxsim 简化（需安装 onnxsim）"),
        half: bool = Query(False, description="FP16 导出"),
        imgsz: Optional[int] = Query(None, ge=32, le=8192, description="导出输入边长；不传为模型默认"),
        db: AsyncSession = Depends(get_db),
):
    """将已注册模型的 .pt 在 CPU 上导出为 ONNX 并下载。"""
    import re

    result = await db.execute(select(Model).where(Model.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    if not Path(model.model_path).exists():
        raise HTTPException(status_code=404, detail="Model file not found on disk")

    try:
        onnx_path = await asyncio.to_thread(
            export_pt_to_onnx,
            str(Path(model.model_path).resolve()),
            opset=opset,
            dynamic=dynamic,
            batch=batch,
            simplify=simplify,
            half=half,
            imgsz=imgsz,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("ONNX export failed for model {}", model_id)
        raise HTTPException(status_code=500, detail=f"ONNX 导出失败: {e}")

    safe_name = re.sub(r'[<>:"/\\|?*]', "_", model.name)
    return FileResponse(
        str(onnx_path),
        filename=f"{safe_name}.onnx",
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


