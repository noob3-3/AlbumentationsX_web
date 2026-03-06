"""
Model deployment and inference API endpoints
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.core.database import get_db
from app.schemas.schemas import (
    DeploymentCreate, DeploymentResponse, InferenceResponse,
    SuccessResponse
)
from app.services import DeploymentService

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


@router.post("/{deployment_id}/predict", response_model=InferenceResponse, summary="Run inference")
async def predict(
    deployment_id: str,
    file: UploadFile = File(...),
    confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
    iou: Optional[float] = Query(None, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
):
    """使用部署的模型进行推理"""
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

