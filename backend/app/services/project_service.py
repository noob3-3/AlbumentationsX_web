"""
Project service for managing projects
"""
from typing import Optional, List
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Project, Dataset, Model, ProjectStatus


class ProjectService:
    """Service for project management"""

    @staticmethod
    async def create_project(
        db: AsyncSession,
        name: str,
        description: Optional[str] = None,
        webhook_url: Optional[str] = None,
        webhook_enabled: bool = False,
        webhook_secret: Optional[str] = None,
        webhook_events: Optional[List[str]] = None,
    ) -> Project:
        """Create a new project"""
        project = Project(
            name=name,
            description=description,
            status=ProjectStatus.ACTIVE,
            webhook_url=webhook_url,
            webhook_enabled=webhook_enabled,
            webhook_secret=webhook_secret,
            webhook_events=webhook_events,
        )
        db.add(project)
        await db.commit()
        await db.refresh(project)
        return project

    @staticmethod
    async def get_project(db: AsyncSession, project_id: str) -> Optional[Project]:
        """Get project by ID"""
        result = await db.execute(select(Project).where(Project.id == project_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_projects(
        db: AsyncSession,
        status: Optional[ProjectStatus] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[List[Project], int]:
        """List projects with filters"""
        query = select(Project)

        # Apply filters
        if status:
            query = query.where(Project.status == status)
        if search:
            query = query.where(
                or_(
                    Project.name.ilike(f"%{search}%"),
                    Project.description.ilike(f"%{search}%"),
                )
            )

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination and ordering
        query = query.order_by(Project.created_at.desc()).offset(skip).limit(limit)

        result = await db.execute(query)
        projects = result.scalars().all()

        return list(projects), total

    @staticmethod
    async def update_project(
        db: AsyncSession,
        project_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[ProjectStatus] = None,
        webhook_url: Optional[str] = None,
        webhook_enabled: Optional[bool] = None,
        webhook_secret: Optional[str] = None,
        webhook_events: Optional[List[str]] = None,
    ) -> Optional[Project]:
        """Update project"""
        project = await ProjectService.get_project(db, project_id)
        if not project:
            return None

        if name is not None:
            project.name = name
        if description is not None:
            project.description = description
        if status is not None:
            project.status = status
        if webhook_url is not None:
            project.webhook_url = webhook_url
        if webhook_enabled is not None:
            project.webhook_enabled = webhook_enabled
        if webhook_secret is not None:
            project.webhook_secret = webhook_secret
        if webhook_events is not None:
            project.webhook_events = webhook_events

        await db.commit()
        await db.refresh(project)
        return project

    @staticmethod
    async def delete_project(db: AsyncSession, project_id: str) -> bool:
        """Delete project (soft delete by setting status to DELETED)"""
        project = await ProjectService.get_project(db, project_id)
        if not project:
            return False

        project.status = ProjectStatus.DELETED
        await db.commit()
        return True

    @staticmethod
    async def update_counts(db: AsyncSession, project_id: str):
        """Update dataset and model counts for a project"""
        project = await ProjectService.get_project(db, project_id)
        if not project:
            return

        # Count datasets
        dataset_count_result = await db.execute(
            select(func.count()).select_from(Dataset).where(Dataset.project_id == project_id)
        )
        project.dataset_count = dataset_count_result.scalar() or 0

        # Count models
        model_count_result = await db.execute(
            select(func.count()).select_from(Model).where(Model.project_id == project_id)
        )
        project.model_count = model_count_result.scalar() or 0

        await db.commit()

    @staticmethod
    async def get_project_datasets(
        db: AsyncSession,
        project_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[List[Dataset], int]:
        """Get all datasets in a project"""
        query = select(Dataset).where(Dataset.project_id == project_id)

        # Get total count
        count_query = select(func.count()).select_from(Dataset).where(Dataset.project_id == project_id)
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        query = query.order_by(Dataset.created_at.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        datasets = result.scalars().all()

        return list(datasets), total

    @staticmethod
    async def get_project_models(
        db: AsyncSession,
        project_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[List[Model], int]:
        """Get all models in a project"""
        query = select(Model).where(Model.project_id == project_id)

        # Get total count
        count_query = select(func.count()).select_from(Model).where(Model.project_id == project_id)
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        query = query.order_by(Model.created_at.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        models = result.scalars().all()

        return list(models), total

