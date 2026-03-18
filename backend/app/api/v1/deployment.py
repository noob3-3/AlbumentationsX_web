"""
Model deployment and inference API endpoints
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from app.core.database import get_db
from app.models import Model, ImageSource
from app.schemas.schemas import (
    DeploymentCreate, DeploymentResponse, InferenceResponse,
    SuccessResponse
)
from app.services import DeploymentService, DatasetService

router = APIRouter(prefix="/deployments", tags=["deployment"])


@router.post("", response_model=DeploymentResponse, summary="Create deployment")
async def create_deployment(
    data: DeploymentCreate,
    db: AsyncSession = Depends(get_db),
):
    """部署模型到服务器"""
    try:
        deployment = await DeploymentService.create_deployment(db, data)
        await db.commit()
        return deployment
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create deployment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", summary="List deployments")
async def list_deployments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """列出所有部署"""
    from sqlalchemy import select
    from app.models import Model

    skip = (page - 1) * page_size
    deployments = await DeploymentService.list_deployments(db, skip=skip, limit=page_size)

    # Enrich deployments with model names and calculated fields
    enriched_items = []
    for deployment in deployments:
        # Get model name
        model_result = await db.execute(select(Model).where(Model.id == deployment.model_id))
        model = model_result.scalar_one_or_none()

        # Convert to dict and add extra fields
        deployment_dict = {
            "id": deployment.id,
            "name": deployment.name,
            "model_id": deployment.model_id,
            "model_name": model.name if model else "Unknown",
            "status": deployment.status,
            "endpoint_url": deployment.endpoint_url,
            "port": deployment.port,
            "confidence_threshold": deployment.confidence_threshold,
            "iou_threshold": deployment.iou_threshold,
            "max_detections": deployment.max_detections,
            "device": deployment.device,
            "error_message": deployment.error_message,
            "request_count": deployment.request_count,
            "inference_count": deployment.request_count,  # Alias
            "avg_time": None,
            "avg_inference_time_ms": None,
            "created_at": deployment.created_at,
            "updated_at": deployment.updated_at,
        }

        # Calculate average inference time
        if deployment.request_count > 0 and hasattr(deployment, 'total_inference_time_ms'):
            avg_ms = deployment.total_inference_time_ms / deployment.request_count
            deployment_dict["avg_inference_time_ms"] = round(avg_ms, 2)
            deployment_dict["avg_time"] = f"{avg_ms:.1f} ms"

        enriched_items.append(deployment_dict)

    return {
        "items": enriched_items,
        "total": len(deployments),
        "page": page,
        "page_size": page_size,
    }


@router.get("/{deployment_id}", response_model=DeploymentResponse, summary="Get deployment")
async def get_deployment(
    deployment_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取部署详情"""
    from sqlalchemy import select
    from app.models import Model

    deployment = await DeploymentService.get_deployment(db, deployment_id)
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    # Get model name
    model_result = await db.execute(select(Model).where(Model.id == deployment.model_id))
    model = model_result.scalar_one_or_none()

    # Convert to dict and add extra fields
    deployment_dict = {
        "id": deployment.id,
        "name": deployment.name,
        "model_id": deployment.model_id,
        "model_name": model.name if model else "Unknown",
        "status": deployment.status,
        "endpoint_url": deployment.endpoint_url,
        "port": deployment.port,
        "confidence_threshold": deployment.confidence_threshold,
        "iou_threshold": deployment.iou_threshold,
        "max_detections": deployment.max_detections,
        "device": deployment.device,
        "error_message": deployment.error_message,
        "request_count": deployment.request_count,
        "inference_count": deployment.request_count,  # Alias
        "avg_time": None,
        "avg_inference_time_ms": None,
        "created_at": deployment.created_at,
        "updated_at": deployment.updated_at,
    }

    # Calculate average inference time
    if deployment.request_count > 0 and hasattr(deployment, 'total_inference_time_ms'):
        avg_ms = deployment.total_inference_time_ms / deployment.request_count
        deployment_dict["avg_inference_time_ms"] = round(avg_ms, 2)
        deployment_dict["avg_time"] = f"{avg_ms:.1f} ms"

    return deployment_dict


@router.post("/{deployment_id}/stop", response_model=SuccessResponse, summary="Stop deployment")
async def stop_deployment(
    deployment_id: str,
    db: AsyncSession = Depends(get_db),
):
    """停止部署"""
    success = await DeploymentService.stop_deployment(db, deployment_id)
    if not success:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return {"success": True, "message": "Deployment stopped"}


@router.post("/{deployment_id}/restart", response_model=SuccessResponse, summary="Restart deployment")
async def restart_deployment(
    deployment_id: str,
    db: AsyncSession = Depends(get_db),
):
    """重启部署"""
    success = await DeploymentService.restart_deployment(db, deployment_id)
    if not success:
        raise HTTPException(status_code=404, detail="Failed to restart deployment")
    return {"success": True, "message": "Deployment restarted"}


@router.delete("/{deployment_id}", response_model=SuccessResponse, summary="Delete deployment")
async def delete_deployment(
    deployment_id: str,
    db: AsyncSession = Depends(get_db),
):
    """删除部署"""
    success = await DeploymentService.delete_deployment(db, deployment_id)
    if not success:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return {"success": True, "message": "Deployment deleted"}


def _detections_to_annotations(detections: list) -> list:
    """将检测结果转换为 Annotation 格式 (x_center, y_center, bbox_width, bbox_height 归一化)"""
    anns = []
    for d in detections or []:
        norm = d.get("bbox_normalized") or [0.5, 0.5, 0.1, 0.1]
        if len(norm) >= 4:
            cx, cy, w, h = norm[0], norm[1], norm[2], norm[3]
        else:
            bbox = d.get("bbox", [0, 0, 10, 10])
            if len(bbox) >= 4:
                x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
                img_w = d.get("_img_width") or 1
                img_h = d.get("_img_height") or 1
                cx = (x1 + x2) / 2 / img_w
                cy = (y1 + y2) / 2 / img_h
                w = (x2 - x1) / img_w
                h = (y2 - y1) / img_h
            else:
                cx, cy, w, h = 0.5, 0.5, 0.1, 0.1
        anns.append({
            "class_id": d.get("class_id", 0),
            "class_name": d.get("class_name") or "unknown",
            "x_center": max(0, min(1, cx)),
            "y_center": max(0, min(1, cy)),
            "bbox_width": max(0.01, min(1, w)),
            "bbox_height": max(0.01, min(1, h)),
            "confidence": d.get("confidence"),
        })
    return anns


@router.post("/{deployment_id}/predict", response_model=InferenceResponse, summary="Run inference")
async def predict(
    deployment_id: str,
    file: UploadFile = File(...),
    confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
    iou: Optional[float] = Query(None, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
):
    """使用部署的模型进行推理。推理图片与结果会自动保存到项目的「API推理数据」数据集中。"""
    try:
        # Read image data
        image_data = await file.read()

        # Run inference
        result = await DeploymentService.predict(
            db=db,
            deployment_id=deployment_id,
            image_data=image_data,
            confidence=confidence,
            iou=iou,
        )

        # 自动保存推理图片和结果到数据集（不阻塞响应，失败仅记录日志）
        try:
            deployment = await DeploymentService.get_deployment(db, deployment_id)
            if deployment:
                model_res = await db.execute(select(Model).where(Model.id == deployment.model_id))
                model = model_res.scalar_one_or_none()
                if model and model.project_id:
                    dataset = await DatasetService.get_or_create_api_inference_dataset(db, model.project_id)
                    if dataset:
                        allowed_ext = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"}
                        original_filename = file.filename or "inference.jpg"
                        if "." not in original_filename or original_filename[original_filename.rfind("."):].lower() not in allowed_ext:
                            original_filename = "inference.jpg"
                        anns = _detections_to_annotations(result.get("detections", []))
                        saved = await DatasetService.save_uploaded_image(
                            db=db,
                            dataset_id=dataset.id,
                            file_data=image_data,
                            original_filename=original_filename,
                            source=ImageSource.API,
                            source_url=None,
                            annotations=anns,
                        )
                        if saved:
                            # 合并新类别到数据集
                            existing = set(dataset.classes or [])
                            for a in anns:
                                if a.get("class_name") and a["class_name"] not in existing:
                                    existing.add(a["class_name"])
                            if existing != set(dataset.classes or []):
                                dataset.classes = list(existing)
                            await db.commit()
                            logger.info(f"Saved inference image to dataset {dataset.id} ({dataset.name})")
        except Exception as save_err:
            logger.warning(f"Failed to save inference to dataset: {save_err}")

        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Inference failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/loaded-models", summary="Get loaded models")
async def get_loaded_models():
    """获取已加载到内存的模型列表"""
    models = DeploymentService.get_loaded_models()
    return {"loaded_models": models, "count": len(models)}

