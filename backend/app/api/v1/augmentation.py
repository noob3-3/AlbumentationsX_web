"""
Augmentation API endpoints
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.schemas import AugmentationJobCreate, AugmentationJobResponse, SuccessResponse
from app.services import AugmentationService, DEFAULT_AUGMENTATION_CONFIG

router = APIRouter(prefix="/augmentation", tags=["augmentation"])


@router.post("/jobs", response_model=AugmentationJobResponse, summary="Create and start augmentation job")
async def create_augmentation_job(
    data: AugmentationJobCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    job = await AugmentationService.create_job(db, data)
    await db.commit()
    # Start background task
    background_tasks.add_task(AugmentationService.run_augmentation_job, job.id)
    return job


@router.get("/jobs", response_model=dict, summary="List augmentation jobs")
async def list_augmentation_jobs(
    dataset_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    jobs = await AugmentationService.list_jobs(db, dataset_id=dataset_id)
    return {"items": [AugmentationJobResponse.model_validate(j) for j in jobs], "total": len(jobs)}


@router.get("/jobs/{job_id}", response_model=AugmentationJobResponse, summary="Get augmentation job")
async def get_augmentation_job(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await AugmentationService.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Augmentation job not found")
    return job


@router.get("/transforms", summary="List available augmentation transforms")
async def list_transforms():
    """获取所有可用的变换及其详细信息"""
    from app.services.augmentation_transforms import TRANSFORM_INFO, TRANSFORM_CATEGORIES, get_transforms_by_category

    transforms_by_category = get_transforms_by_category()

    return {
        "transforms": TRANSFORM_INFO,
        "categories": TRANSFORM_CATEGORIES,
        "by_category": transforms_by_category,
    }


@router.get("/default-config", summary="Get default augmentation config")
async def get_default_config():
    return {"config": DEFAULT_AUGMENTATION_CONFIG}


@router.get("/recommended-configs", summary="Get recommended augmentation configs")
async def get_recommended_configs():
    """获取推荐的增强配置（轻度、中度、强度）"""
    from app.services.augmentation_transforms import RECOMMENDED_CONFIGS
    return {"configs": RECOMMENDED_CONFIGS}

