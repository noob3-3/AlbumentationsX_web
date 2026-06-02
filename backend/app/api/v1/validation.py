"""
Model validation API endpoints
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import tempfile
import shutil
from pathlib import Path

from app.core.database import get_db
from app.schemas.schemas import (
    ModelValidationRequest,
    ModelValidationResponse,
)
from app.services.validation_service import ModelValidationService
from app.core.logging import logger

router = APIRouter(prefix="/validation", tags=["Model Validation"])


@router.post("/validate")
async def validate_models(
    files: List[UploadFile] = File(..., description="测试图片，支持多选"),
    model_ids: str = Form(...),  # JSON string of model IDs
    confidence: float = Form(0.5),
    iou: float = Form(0.45),
    db: AsyncSession = Depends(get_db),
):
    """
    验证多个模型在多张图片上的表现
    上传多张图片，指定多个模型ID，返回每张图片每个模型的检测结果
    """
    import json

    logger.info(f"Received validation request with model_ids: {model_ids}, files: {len(files)}")

    # Parse model_ids
    try:
        model_id_list = json.loads(model_ids)
        logger.info(f"Parsed model_ids: {model_id_list}")

        if not isinstance(model_id_list, list):
            raise ValueError(f"model_ids must be a list, got {type(model_id_list)}")

        if len(model_id_list) == 0:
            raise ValueError("model_ids list is empty")

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse model_ids JSON: {model_ids}, error: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON in model_ids: {str(e)}")
    except Exception as e:
        logger.error(f"Invalid model_ids: {model_ids}, error: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid model_ids: {str(e)}")

    if not files:
        raise HTTPException(status_code=400, detail="请至少上传一张图片")

    # Save uploaded files to temp location
    temp_dir = Path(tempfile.gettempdir()) / "ax_validation"
    temp_dir.mkdir(exist_ok=True, parents=True)
    temp_files = []

    try:
        for i, file in enumerate(files):
            safe_name = f"{i}_{Path(file.filename or 'image').name}"
            temp_file = temp_dir / safe_name
            with temp_file.open("wb") as f:
                shutil.copyfileobj(file.file, f)
            temp_files.append((file.filename, str(temp_file)))

        logger.info(f"Validating {len(model_id_list)} models on {len(temp_files)} images")

        # Validate each image
        all_results = []
        total_time_ms = 0
        for orig_name, temp_path in temp_files:
            result = await ModelValidationService.validate_models(
                db=db,
                model_ids=model_id_list,
                image_path=temp_path,
                confidence_threshold=confidence,
                iou_threshold=iou,
            )
            all_results.append({
                "image_name": orig_name,
                "image_size": result.get("image_size", [0, 0]),
                "total_time_ms": result.get("total_time_ms", 0),
                "results": result.get("results", []),
            })
            total_time_ms += result.get("total_time_ms", 0)

        logger.info("Validation completed successfully")
        return {
            "images": all_results,
            "total_time_ms": total_time_ms,
        }

    except Exception as e:
        logger.error(f"Model validation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        for _, temp_path in temp_files:
            p = Path(temp_path)
            if p.exists():
                p.unlink()


@router.post("/save-to-dataset")
async def save_validation_to_dataset(
    files: List[UploadFile] = File(..., description="测试图片"),
    project_id: str = Form(...),
    dataset_id: Optional[str] = Form(None),
    dataset_name: str = Form(None),
    detections_json: str = Form(..., description="每张图片的检测结果，JSON 数组与 files 顺序对应"),
    db: AsyncSession = Depends(get_db),
):
    """将验证结果保存到数据集，图片和推理标注一并保存"""
    import json
    from app.models import Dataset, ImageSource
    from app.services.dataset_service import DatasetService
    from app.schemas.schemas import DatasetCreate

    if not files:
        raise HTTPException(status_code=400, detail="请上传图片")

    try:
        detections_list = json.loads(detections_json)
        if not isinstance(detections_list, list):
            raise ValueError("detections_json 必须是数组")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"detections_json 格式错误: {e}")

    # 解析检测结果为标注格式 (x_center, y_center, bbox_width, bbox_height 归一化)
    def to_annotation(det):
        norm = det.get("bbox_normalized") or [0.5, 0.5, 0.1, 0.1]
        if len(norm) >= 4:
            cx, cy, w, h = norm[0], norm[1], norm[2], norm[3]
        else:
            bbox = det.get("bbox", [0, 0, 10, 10])
            if len(bbox) >= 4:
                x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                w, h = x2 - x1, y2 - y1
                img_w = det.get("_img_width") or 1
                img_h = det.get("_img_height") or 1
                cx, cy, w, h = cx / img_w, cy / img_h, w / img_w, h / img_h
            else:
                cx, cy, w, h = 0.5, 0.5, 0.1, 0.1
        ann = {
            "class_id": det.get("class_id", 0),
            "class_name": det.get("class_name") or "unknown",
            "x_center": max(0, min(1, cx)),
            "y_center": max(0, min(1, cy)),
            "bbox_width": max(0.01, min(1, w)),
            "bbox_height": max(0.01, min(1, h)),
            "confidence": det.get("confidence"),
        }
        poly = det.get("polygon_points")
        if poly and len(poly) >= 3:
            ann["polygon_points"] = [
                [max(0, min(1, float(p[0]))), max(0, min(1, float(p[1])))] for p in poly
            ]
        return ann

    # 确定目标数据集
    if dataset_id:
        dataset = await DatasetService.get_dataset(db, dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="数据集不存在")
    else:
        if not dataset_name or not project_id:
            raise HTTPException(status_code=400, detail="请指定 dataset_id 或 (dataset_name + project_id) 以创建新数据集")
        dataset = await DatasetService.create_dataset(db, DatasetCreate(name=dataset_name, project_id=project_id))
        await db.commit()
        await db.refresh(dataset)
        dataset_id = dataset.id

    # 收集所有类别
    all_classes = set()
    saved = 0
    total_anns = 0

    for idx, file in enumerate(files):
        if not file.filename or not any(file.filename.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".bmp", ".webp"]):
            continue
        dets = detections_list[idx] if idx < len(detections_list) else []
        anns = [to_annotation(d) for d in dets]
        for a in anns:
            if a.get("class_name"):
                all_classes.add(a["class_name"])

        file.file.seek(0)
        img = await DatasetService.save_uploaded_image_stream(
            db=db,
            dataset_id=dataset_id,
            file=file,
            original_filename=file.filename,
            source=ImageSource.LOCAL,
            annotations=anns,
        )
        if img:
            saved += 1
            total_anns += len(anns)

    if all_classes:
        ds = await DatasetService.get_dataset(db, dataset_id)
        if ds:
            existing = set(ds.classes or [])
            merged = list(existing)
            for c in sorted(all_classes):
                if c not in existing:
                    merged.append(c)
            ds.classes = merged

    await db.commit()
    return {
        "success": True,
        "message": f"已保存 {saved} 张图片、{total_anns} 个标注到数据集",
        "dataset_id": dataset_id,
        "dataset_name": dataset.name,
        "images_saved": saved,
        "annotations_saved": total_anns,
    }


@router.delete("/clean")
async def clean_validation_data(
    project_id: str = Query(..., description="项目ID，清除该项目下所有模型的验证记录"),
    db: AsyncSession = Depends(get_db),
):
    """清除当前项目的模型验证测试数据（验证记录 + 临时测试图片）"""
    from sqlalchemy import delete
    from app.models import ModelValidation, Model

    # 1. 删除验证记录
    subq = select(Model.id).where(Model.project_id == project_id)
    stmt = delete(ModelValidation).where(ModelValidation.model_id.in_(subq))
    result = await db.execute(stmt)
    await db.commit()
    deleted_records = result.rowcount

    # 2. 清除临时测试图片目录
    temp_dir = Path(tempfile.gettempdir()) / "ax_validation"
    temp_deleted = 0
    if temp_dir.exists():
        try:
            for f in temp_dir.iterdir():
                if f.is_file():
                    f.unlink()
                    temp_deleted += 1
        except OSError as e:
            logger.warning(f"Failed to clean temp dir {temp_dir}: {e}")

    msg = f"已清除 {deleted_records} 条验证记录"
    if temp_deleted > 0:
        msg += f"，{temp_deleted} 个临时图片文件"
    logger.info(f"Cleaned validation: {deleted_records} records, {temp_deleted} temp files for project {project_id}")
    return {"success": True, "message": msg, "deleted_records": deleted_records, "deleted_temp_files": temp_deleted}


@router.get("/history/{model_id}")
async def get_validation_history(
    model_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """获取模型的验证历史"""
    validations = await ModelValidationService.get_model_validations(
        db=db,
        model_id=model_id,
        limit=limit,
    )
    return validations

