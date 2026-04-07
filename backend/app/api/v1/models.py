"""
Model management API endpoints
"""
import asyncio
from app.core.database import get_db
from app.models import Model
from app.schemas.schemas import ModelResponse
from app.services.model_export_service import export_pt_to_onnx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from loguru import logger
from pathlib import Path
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", summary="List trained models")
async def list_models(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    project_id: str = Query(None, description="Filter by project ID"),
    db: AsyncSession = Depends(get_db)
):
    """List all trained models with pagination"""
    skip = (page - 1) * page_size

    # Build query with optional project filter
    query = select(Model).order_by(Model.created_at.desc())
    count_query = select(func.count()).select_from(Model)

    if project_id:
        query = query.where(Model.project_id == project_id)
        count_query = count_query.where(Model.project_id == project_id)

    # Get total count
    count_result = await db.execute(count_query)
    total = count_result.scalar()

    # Get paginated models
    result = await db.execute(query.offset(skip).limit(page_size))
    models = result.scalars().all()

    return {
        "items": [ModelResponse.model_validate(m) for m in models],
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get("/{model_id}", response_model=ModelResponse, summary="Get model info")
async def get_model(model_id: str, db: AsyncSession = Depends(get_db)):
    """Get detailed information about a specific model"""
    result = await db.execute(select(Model).where(Model.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return model


@router.get("/{model_id}/download", summary="Download model weights")
async def download_model(model_id: str, db: AsyncSession = Depends(get_db)):
    """Download the model weights file"""
    result = await db.execute(select(Model).where(Model.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    if not Path(model.model_path).exists():
        raise HTTPException(status_code=404, detail="Model file not found on disk")
    return FileResponse(
        model.model_path,
        filename=Path(model.model_path).name,
        media_type="application/octet-stream",
    )


@router.get("/{model_id}/export-onnx", summary="Export model to ONNX (download)")
async def export_model_onnx(
        model_id: str,
        opset: int = Query(18, ge=9, le=23),
        dynamic: bool = Query(False),
        batch: int = Query(1, ge=1, le=64),
        simplify: bool = Query(False),
        half: bool = Query(False),
        imgsz: Optional[int] = Query(None, ge=32, le=8192),
        db: AsyncSession = Depends(get_db),
):
    """与 /training/models/{id}/export-onnx 相同逻辑，便于使用 /api/v1/models 前缀的客户端。"""
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
