"""
Model management API endpoints
"""
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.schemas.schemas import ModelResponse
from app.models import Model

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

