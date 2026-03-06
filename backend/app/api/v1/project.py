"""
Project management API endpoints
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.schemas import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    PaginatedResponse,
    DatasetResponse,
    ModelResponse,
    SuccessResponse,
)
from app.services.project_service import ProjectService
from app.models.models import ProjectStatus

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建新项目"""
    project = await ProjectService.create_project(
        db=db,
        name=data.name,
        description=data.description,
        webhook_url=data.webhook_url,
        webhook_enabled=data.webhook_enabled,
        webhook_secret=data.webhook_secret,
        webhook_events=data.webhook_events,
    )
    return project


@router.get("", response_model=PaginatedResponse)
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[ProjectStatus] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """列出所有项目"""
    skip = (page - 1) * page_size
    projects, total = await ProjectService.list_projects(
        db=db,
        status=status,
        search=search,
        skip=skip,
        limit=page_size,
    )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [ProjectResponse.model_validate(p) for p in projects],
    }


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取项目详情"""
    project = await ProjectService.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新项目"""
    project = await ProjectService.update_project(
        db=db,
        project_id=project_id,
        name=data.name,
        description=data.description,
        status=data.status,
        webhook_url=data.webhook_url,
        webhook_enabled=data.webhook_enabled,
        webhook_secret=data.webhook_secret,
        webhook_events=data.webhook_events,
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/{project_id}", response_model=SuccessResponse)
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """删除项目（软删除）"""
    success = await ProjectService.delete_project(db, project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Project not found")
    return SuccessResponse(success=True, message="Project deleted successfully")


@router.get("/{project_id}/datasets", response_model=PaginatedResponse)
async def get_project_datasets(
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取项目的所有数据集"""
    skip = (page - 1) * page_size
    datasets, total = await ProjectService.get_project_datasets(
        db=db,
        project_id=project_id,
        skip=skip,
        limit=page_size,
    )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [DatasetResponse.model_validate(d) for d in datasets],
    }


@router.get("/{project_id}/models", response_model=PaginatedResponse)
async def get_project_models(
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取项目的所有模型"""
    skip = (page - 1) * page_size
    models, total = await ProjectService.get_project_models(
        db=db,
        project_id=project_id,
        skip=skip,
        limit=page_size,
    )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [ModelResponse.model_validate(m) for m in models],
    }


@router.post("/{project_id}/update-counts", response_model=SuccessResponse)
async def update_project_counts(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """更新项目的数据集和模型计数"""
    await ProjectService.update_counts(db, project_id)
    return SuccessResponse(success=True, message="Counts updated successfully")


@router.post("/{project_id}/test-webhook", response_model=SuccessResponse)
async def test_webhook(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """测试项目的 Webhook 配置"""
    project = await ProjectService.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.webhook_enabled or not project.webhook_url:
        raise HTTPException(status_code=400, detail="Webhook not configured")

    # 发送测试消息
    from app.services.webhook_service import WebhookService

    success = await WebhookService.send_webhook(
        url=project.webhook_url,
        event_type="test",
        data={
            "message": "This is a test webhook from AlbumentationsX",
            "project_id": project.id,
            "project_name": project.name,
            "timestamp": "test"
        },
        secret=project.webhook_secret
    )

    if success:
        return SuccessResponse(success=True, message="Webhook test successful")
    else:
        raise HTTPException(status_code=500, detail="Webhook test failed")


