"""
Dataset management service
"""
import os
import shutil
from pathlib import Path
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete
from sqlalchemy.orm import selectinload
from loguru import logger

from app.core.config import settings
from app.models import Dataset, Image, Annotation, DatasetStatus, ImageSource, AnnotationStatus
from app.schemas.schemas import DatasetCreate, DatasetUpdate
from app.utils import generate_filename, get_image_info, create_thumbnail, allowed_image


class DatasetService:

    @staticmethod
    async def create_dataset(db: AsyncSession, data: DatasetCreate) -> Dataset:
        dataset = Dataset(
            name=data.name,
            description=data.description,
            project_id=data.project_id,
            classes=data.classes or [],
            status=DatasetStatus.ACTIVE,
        )

        db.add(dataset)
        await db.flush()  # Get dataset.id
        # Create storage directory
        storage_path = settings.DATASET_DIR / dataset.id
        storage_path.mkdir(parents=True, exist_ok=True)
        (storage_path / "images").mkdir(exist_ok=True)
        (storage_path / "labels").mkdir(exist_ok=True)
        (storage_path / "thumbnails").mkdir(exist_ok=True)
        dataset.storage_path = str(storage_path)

        db.add(dataset)
        await db.flush()
        await db.refresh(dataset)
        return dataset

    @staticmethod
    async def get_dataset(db: AsyncSession, dataset_id: str) -> Optional[Dataset]:
        result = await db.execute(
            select(Dataset).where(Dataset.id == dataset_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_datasets(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 20,
        project_id: Optional[str] = None
    ):
        query = select(Dataset).order_by(Dataset.created_at.desc())

        # Filter by project_id if provided
        if project_id:
            query = query.where(Dataset.project_id == project_id)

        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        datasets = result.scalars().all()

        # Count total with same filter
        count_query = select(func.count()).select_from(Dataset)
        if project_id:
            count_query = count_query.where(Dataset.project_id == project_id)

        count_result = await db.execute(count_query)
        total = count_result.scalar()
        return datasets, total

    @staticmethod
    async def update_dataset(db: AsyncSession, dataset_id: str, data: DatasetUpdate) -> Optional[Dataset]:
        dataset = await DatasetService.get_dataset(db, dataset_id)
        if not dataset:
            return None
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(dataset, field, value)
        await db.flush()
        await db.refresh(dataset)
        return dataset

    @staticmethod
    async def delete_dataset(db: AsyncSession, dataset_id: str) -> bool:
        dataset = await DatasetService.get_dataset(db, dataset_id)
        if not dataset:
            return False
        # Remove storage directory
        if dataset.storage_path and Path(dataset.storage_path).exists():
            shutil.rmtree(dataset.storage_path, ignore_errors=True)
        await db.delete(dataset)
        return True

    @staticmethod
    async def save_uploaded_image(
        db: AsyncSession,
        dataset_id: str,
        file_data: bytes,
        original_filename: str,
        source: ImageSource = ImageSource.LOCAL,
        source_url: Optional[str] = None,
        annotations: Optional[list] = None,
    ) -> Optional[Image]:
        dataset = await DatasetService.get_dataset(db, dataset_id)
        if not dataset:
            return None

        if not allowed_image(original_filename):
            raise ValueError(f"File type not allowed: {original_filename}")

        filename = generate_filename(original_filename)
        images_dir = Path(dataset.storage_path) / "images"
        thumbs_dir = Path(dataset.storage_path) / "thumbnails"
        file_path = images_dir / filename
        thumb_path = thumbs_dir / filename

        # Write file
        with open(file_path, "wb") as f:
            f.write(file_data)

        # Get metadata
        width, height, file_size = get_image_info(str(file_path))

        # Create thumbnail
        create_thumbnail(str(file_path), str(thumb_path))

        # Create image record
        image = Image(
            dataset_id=dataset_id,
            filename=filename,
            original_filename=original_filename,
            file_path=str(file_path),
            thumbnail_path=str(thumb_path),
            width=width,
            height=height,
            file_size=file_size,
            source=source,
            source_url=source_url,
            annotation_status=AnnotationStatus.MANUALLY_ANNOTATED if annotations else AnnotationStatus.UNANNOTATED,
        )
        db.add(image)
        await db.flush()

        # Save annotations
        if annotations:
            for ann_data in annotations:
                ann = Annotation(
                    image_id=image.id,
                    **ann_data if isinstance(ann_data, dict) else ann_data.model_dump(),
                )
                db.add(ann)

        # Update dataset counts

    @staticmethod
    async def save_uploaded_image_stream(
        db: AsyncSession,
        dataset_id: str,
        file,  # UploadFile object
        original_filename: str,
        source: ImageSource = ImageSource.LOCAL,
        source_url: Optional[str] = None,
        annotations: Optional[list] = None,
    ) -> Optional[Image]:
        """
        流式上传图片文件，避免内存溢出
        分块读取文件并直接写入磁盘，而不是一次性加载到内存
        """
        dataset = await DatasetService.get_dataset(db, dataset_id)
        if not dataset:
            return None

        if not allowed_image(original_filename):
            raise ValueError(f"File type not allowed: {original_filename}")

        filename = generate_filename(original_filename)
        images_dir = Path(dataset.storage_path) / "images"
        thumbs_dir = Path(dataset.storage_path) / "thumbnails"
        file_path = images_dir / filename
        thumb_path = thumbs_dir / filename

        # 流式写入文件到磁盘 (分块读取，避免内存溢出)
        CHUNK_SIZE = 1024 * 1024  # 1MB per chunk
        file_size = 0
        try:
            with open(file_path, "wb") as f:
                while chunk := await file.read(CHUNK_SIZE):
                    file_size += len(chunk)
                    # 检查文件大小限制
                    if file_size > settings.MAX_UPLOAD_SIZE:
                        # 删除已写入的文件
                        f.close()
                        if file_path.exists():
                            file_path.unlink()
                        raise ValueError(f"File too large: {original_filename} (max {settings.MAX_UPLOAD_SIZE / 1024 / 1024}MB)")
                    f.write(chunk)
        except Exception as e:
            logger.error(f"Failed to write file {original_filename}: {e}")
            if file_path.exists():
                file_path.unlink()
            raise

        # Get metadata
        width, height, file_size = get_image_info(str(file_path))

        # Create thumbnail
        create_thumbnail(str(file_path), str(thumb_path))

        # Create image record
        image = Image(
            dataset_id=dataset_id,
            filename=filename,
            original_filename=original_filename,
            file_path=str(file_path),
            thumbnail_path=str(thumb_path),
            width=width,
            height=height,
            file_size=file_size,
            source=source,
            source_url=source_url,
            annotation_status=AnnotationStatus.MANUALLY_ANNOTATED if annotations else AnnotationStatus.UNANNOTATED,
        )
        db.add(image)
        await db.flush()

        # Save annotations
        if annotations:
            for ann_data in annotations:
                ann = Annotation(
                    image_id=image.id,
                    **ann_data if isinstance(ann_data, dict) else ann_data.model_dump(),
                )
                db.add(ann)

        # Update dataset counts
        dataset.image_count += 1
        if annotations:
            dataset.annotation_count += len(annotations)

        await db.flush()
        await db.refresh(image)
        return image

    @staticmethod
    async def get_images(
        db: AsyncSession,
        dataset_id: str,
        skip: int = 0,
        limit: int = 50,
        augmented_only: Optional[bool] = None,
    ):
        query = (
            select(Image)
            .where(Image.dataset_id == dataset_id)
            .options(selectinload(Image.annotations))
            .order_by(Image.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        # augmented_only 参数的含义：
        # False: 只显示原始数据（is_augmented = False）
        # True: 只显示增强数据（is_augmented = True）
        # None: 显示所有数据（不过滤）
        if augmented_only == True:
            query = query.where(Image.is_augmented == True)
        elif augmented_only == False:
            query = query.where(Image.is_augmented == False)
        # 如果是None，不添加过滤条件

        result = await db.execute(query)
        images = result.scalars().all()

        # 计算总数时也要应用相同的过滤
        count_query = select(func.count()).select_from(Image).where(Image.dataset_id == dataset_id)
        if augmented_only == True:
            count_query = count_query.where(Image.is_augmented == True)
        elif augmented_only == False:
            count_query = count_query.where(Image.is_augmented == False)

        count_result = await db.execute(count_query)
        total = count_result.scalar()
        return images, total

    @staticmethod
    async def get_image(db: AsyncSession, image_id: str) -> Optional[Image]:
        result = await db.execute(
            select(Image)
            .where(Image.id == image_id)
            .options(selectinload(Image.annotations))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def delete_image(db: AsyncSession, image_id: str) -> bool:
        image = await DatasetService.get_image(db, image_id)
        if not image:
            return False
        # Remove files
        for path in [image.file_path, image.thumbnail_path]:
            if path and Path(path).exists():
                Path(path).unlink(missing_ok=True)
        # Update dataset
        dataset = await DatasetService.get_dataset(db, image.dataset_id)
        if dataset:
            dataset.image_count = max(0, dataset.image_count - 1)
            dataset.annotation_count = max(0, dataset.annotation_count - len(image.annotations))
        await db.delete(image)
        return True
