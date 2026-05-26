"""
Dataset management service
"""
import os
import shutil
from app.core.config import settings
from app.models import (
    Dataset,
    Image,
    Annotation,
    DatasetStatus,
    ImageSource,
    AnnotationStatus,
    AugmentationJob,
    TrainingJob,
)
from app.schemas.schemas import DatasetCreate, DatasetUpdate
from app.utils import generate_filename, get_image_info, create_thumbnail, allowed_image
from app.utils.semantic_mask_utils import save_semantic_mask_png, validate_and_load_semantic_mask_png
from loguru import logger
from pathlib import Path
from sqlalchemy import select, func, update, delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified
from typing import List, Optional


class DatasetService:

    @staticmethod
    async def create_dataset(db: AsyncSession, data: DatasetCreate) -> Dataset:
        lt = getattr(data, "label_task", None) or "detect"
        dataset = Dataset(
            name=data.name,
            description=data.description,
            project_id=data.project_id,
            classes=data.classes or [],
            label_task=lt,
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
        (storage_path / "semantic_masks").mkdir(exist_ok=True)
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
    async def get_or_create_api_inference_dataset(db: AsyncSession, project_id: Optional[str]) -> Optional[Dataset]:
        """获取或创建项目的 API 推理数据集（用于自动保存部署推理的图片和结果）"""
        if not project_id:
            return None
        # 查找名称固定的数据集
        result = await db.execute(
            select(Dataset)
            .where(Dataset.project_id == project_id)
            .where(Dataset.name == "API推理数据")
        )
        dataset = result.scalar_one_or_none()
        if dataset:
            return dataset
        # 不存在则创建
        dataset = await DatasetService.create_dataset(
            db, DatasetCreate(name="API推理数据", project_id=project_id, description="部署 API 推理自动保存的图片与检测结果")
        )
        await db.flush()
        await db.refresh(dataset)
        return dataset

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
    async def _sync_annotation_class_names_from_list(
        db: AsyncSession,
        dataset_id: str,
        classes: List[str],
    ) -> None:
        """按 class_id 将标注的 class_name 与数据集类别表对齐（用于类别管理保存）。"""
        from app.models import Annotation

        img_result = await db.execute(select(Image.id).where(Image.dataset_id == dataset_id))
        image_ids = [r[0] for r in img_result.all()]
        if not image_ids:
            return
        ann_result = await db.execute(
            select(Annotation).where(Annotation.image_id.in_(image_ids))
        )
        for ann in ann_result.scalars().all():
            cid = ann.class_id
            if cid is None or cid < 0:
                continue
            if cid < len(classes) and classes[cid]:
                ann.class_name = classes[cid]

    @staticmethod
    async def update_dataset(db: AsyncSession, dataset_id: str, data: DatasetUpdate) -> Optional[Dataset]:
        dataset = await DatasetService.get_dataset(db, dataset_id)
        if not dataset:
            return None
        dump = data.model_dump(exclude_none=True)
        classes_val = dump.pop("classes", None)
        for field, value in dump.items():
            setattr(dataset, field, value)
        if classes_val is not None:
            dataset.classes = list(classes_val)
            flag_modified(dataset, "classes")
            await DatasetService._sync_annotation_class_names_from_list(db, dataset_id, dataset.classes)
        await db.flush()
        await db.refresh(dataset)
        return dataset

    @staticmethod
    async def purge_augmented_images(db: AsyncSession, dataset_id: str) -> bool:
        """仅删除增强生成的图片与标注，并清理数据增强任务记录；保留数据集与原图。"""
        dataset = await DatasetService.get_dataset(db, dataset_id)
        if not dataset:
            return False
        result = await db.execute(
            select(Image)
            .where(Image.dataset_id == dataset_id, Image.is_augmented == True)
            .options(selectinload(Image.annotations))
        )
        aug_images = result.scalars().all()
        ann_removed = sum(len(img.annotations) for img in aug_images)
        for img in aug_images:
            for path in [img.file_path, img.thumbnail_path]:
                if path and Path(path).exists():
                    Path(path).unlink(missing_ok=True)
            await db.delete(img)
        if aug_images:
            dataset.image_count = max(0, (dataset.image_count or 0) - len(aug_images))
            dataset.annotation_count = max(0, (dataset.annotation_count or 0) - ann_removed)
        dataset.augmented_count = 0
        await db.execute(delete(AugmentationJob).where(AugmentationJob.dataset_id == dataset_id))
        return True

    @staticmethod
    async def delete_dataset(db: AsyncSession, dataset_id: str) -> bool:
        """
        删除数据集。使用显式 SQL 顺序删子表，避免 ORM delete 时懒加载 relationship 在已中止事务上报错；
        annotation_jobs 等可选表放在 savepoint 中，失败不污染外层事务（PostgreSQL）。
        """
        r = await db.execute(select(Dataset.storage_path).where(Dataset.id == dataset_id))
        storage_path = r.scalar_one_or_none()
        if storage_path is None:
            return False

        await db.execute(delete(AugmentationJob).where(AugmentationJob.dataset_id == dataset_id))
        await db.execute(delete(TrainingJob).where(TrainingJob.dataset_id == dataset_id))

        for stmt, msg in (
                (
                        text("DELETE FROM annotation_jobs WHERE dataset_id = :did"),
                        "annotation_jobs",
                ),
                (
                        text(
                            "DELETE FROM collection_images WHERE image_id IN "
                            "(SELECT id FROM images WHERE dataset_id = :did)"
                        ),
                        "collection_images",
                ),
        ):
            try:
                async with db.begin_nested():
                    await db.execute(stmt, {"did": dataset_id})
            except Exception as e:
                logger.debug("{} 清理跳过: {}", msg, e)

        await db.execute(
            text(
                "DELETE FROM annotations WHERE image_id IN "
                "(SELECT id FROM images WHERE dataset_id = :did)"
            ),
            {"did": dataset_id},
        )
        # 增强图 parent_id 指向原图：先删增强行再删其余
        await db.execute(
            text("DELETE FROM images WHERE dataset_id = :did AND is_augmented = true"),
            {"did": dataset_id},
        )
        await db.execute(
            text("DELETE FROM images WHERE dataset_id = :did"),
            {"did": dataset_id},
        )

        await db.execute(delete(Dataset).where(Dataset.id == dataset_id))

        sp = storage_path
        if sp and Path(sp).exists():
            shutil.rmtree(sp, ignore_errors=True)
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
        dataset.image_count += 1
        if annotations:
            dataset.annotation_count += len(annotations)

        await db.flush()
        await db.refresh(image)
        return image

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
        for path in [image.file_path, image.thumbnail_path, image.semantic_mask_path]:
            if path and Path(path).exists():
                Path(path).unlink(missing_ok=True)
        # Update dataset
        dataset = await DatasetService.get_dataset(db, image.dataset_id)
        if dataset:
            dataset.image_count = max(0, dataset.image_count - 1)
            dataset.annotation_count = max(0, dataset.annotation_count - len(image.annotations))
        await db.delete(image)
        return True

    @staticmethod
    async def save_semantic_mask_png(
        db: AsyncSession,
        dataset_id: str,
        image_id: str,
        png_bytes: bytes,
    ) -> Image:
        """保存语义分割掩膜（数据集须 label_task=semantic）。"""
        dataset = await DatasetService.get_dataset(db, dataset_id)
        if not dataset:
            raise ValueError("数据集不存在")
        if (getattr(dataset, "label_task", None) or "detect").lower() != "semantic":
            raise ValueError("只有「标注任务=语义分割」的数据集可保存 PNG 掩膜")

        image = await DatasetService.get_image(db, image_id)
        if not image or image.dataset_id != dataset_id:
            raise ValueError("图片不存在")
        if not image.width or not image.height:
            raise ValueError("图片缺少宽高信息")

        classes = dataset.classes or []
        arr, err = validate_and_load_semantic_mask_png(
            png_bytes,
            img_width=image.width,
            img_height=image.height,
            classes=classes,
        )
        if arr is None:
            raise ValueError(err)

        if not dataset.storage_path:
            raise ValueError("数据集存储路径未配置")
        masks_dir = Path(dataset.storage_path) / "semantic_masks"
        masks_dir.mkdir(parents=True, exist_ok=True)
        mask_name = Path(image.filename).stem + ".png"
        dest = masks_dir / mask_name

        save_semantic_mask_png(dest, arr)

        if image.semantic_mask_path and image.semantic_mask_path != str(dest):
            old = Path(image.semantic_mask_path)
            if old.is_file():
                old.unlink(missing_ok=True)

        image.semantic_mask_path = str(dest)
        image.annotation_status = AnnotationStatus.MANUALLY_ANNOTATED
        await db.flush()
        await db.refresh(image)
        return image

    @staticmethod
    async def delete_semantic_mask(db: AsyncSession, dataset_id: str, image_id: str) -> bool:
        image = await DatasetService.get_image(db, image_id)
        if not image or image.dataset_id != dataset_id:
            return False
        p = getattr(image, "semantic_mask_path", None)
        if p and Path(p).is_file():
            Path(p).unlink(missing_ok=True)
        image.semantic_mask_path = None
        await db.flush()
        return True

    @staticmethod
    async def move_image_to_dataset(
        db: AsyncSession,
        source_dataset_id: str,
        image_id: str,
        target_dataset_id: str,
    ) -> Optional[Image]:
        """将图片（含标注）移动到另一个数据集"""
        if source_dataset_id == target_dataset_id:
            raise ValueError("目标数据集不能与源数据集相同")

        image = await DatasetService.get_image(db, image_id)
        if not image:
            return None
        if image.dataset_id != source_dataset_id:
            raise ValueError("图片不属于指定源数据集")

        target_dataset = await DatasetService.get_dataset(db, target_dataset_id)
        if not target_dataset:
            raise ValueError("目标数据集不存在")
        if not target_dataset.storage_path:
            raise ValueError("目标数据集存储路径未配置")

        src_path = Path(image.file_path)
        if not src_path.exists():
            raise ValueError("图片文件不存在")

        # 目标存储目录
        target_images_dir = Path(target_dataset.storage_path) / "images"
        target_thumbs_dir = Path(target_dataset.storage_path) / "thumbnails"
        target_masks_dir = Path(target_dataset.storage_path) / "semantic_masks"
        target_images_dir.mkdir(parents=True, exist_ok=True)
        target_thumbs_dir.mkdir(parents=True, exist_ok=True)
        target_masks_dir.mkdir(parents=True, exist_ok=True)

        # 复制图片文件到目标数据集（新文件名避免冲突）
        new_filename = generate_filename(image.original_filename)
        dst_img_path = target_images_dir / new_filename
        dst_thumb_path = target_thumbs_dir / new_filename
        shutil.copy2(str(src_path), str(dst_img_path))
        create_thumbnail(str(dst_img_path), str(dst_thumb_path))

        # 合并类别：目标数据集已有 + 源图片标注中的新类别
        source_dataset = await DatasetService.get_dataset(db, source_dataset_id)
        target_classes = list(target_dataset.classes or [])
        source_classes = source_dataset.classes or []
        class_name_to_target_id = {c: i for i, c in enumerate(target_classes)}

        for ann in image.annotations:
            name = ann.class_name or (source_classes[ann.class_id] if ann.class_id < len(source_classes) else f"class_{ann.class_id}")
            if name not in class_name_to_target_id:
                class_name_to_target_id[name] = len(target_classes)
                target_classes.append(name)

        target_dataset.classes = target_classes

        # 复制语义掩膜（若存在）
        new_mask_path_str = None
        if image.semantic_mask_path and Path(image.semantic_mask_path).is_file():
            mask_name = Path(new_filename).stem + ".png"
            dst_mask = target_masks_dir / mask_name
            shutil.copy2(image.semantic_mask_path, str(dst_mask))
            new_mask_path_str = str(dst_mask)

        # 创建新 Image 记录
        width, height, file_size = get_image_info(str(dst_img_path))
        new_image = Image(
            dataset_id=target_dataset_id,
            filename=new_filename,
            original_filename=image.original_filename,
            file_path=str(dst_img_path),
            thumbnail_path=str(dst_thumb_path),
            semantic_mask_path=new_mask_path_str,
            width=width,
            height=height,
            file_size=file_size,
            source=image.source,
            source_url=image.source_url,
            is_augmented=image.is_augmented,
            parent_id=None,  # 移动后不再关联原增强链
            annotation_status=image.annotation_status,
        )
        db.add(new_image)
        await db.flush()

        # 复制标注并映射 class_id
        for ann in image.annotations:
            name = ann.class_name or (source_classes[ann.class_id] if ann.class_id < len(source_classes) else f"class_{ann.class_id}")
            target_cid = class_name_to_target_id.get(name, 0)
            new_ann = Annotation(
                image_id=new_image.id,
                class_id=target_cid,
                class_name=name,
                x_center=ann.x_center,
                y_center=ann.y_center,
                bbox_width=ann.bbox_width,
                bbox_height=ann.bbox_height,
                confidence=ann.confidence,
                polygon_points=getattr(ann, "polygon_points", None),
            )
            db.add(new_ann)

        ann_count = len(image.annotations)
        target_dataset.image_count = (target_dataset.image_count or 0) + 1
        target_dataset.annotation_count = (target_dataset.annotation_count or 0) + ann_count
        if new_image.is_augmented:
            target_dataset.augmented_count = (target_dataset.augmented_count or 0) + 1

        # 删除源图片
        for path in [image.file_path, image.thumbnail_path, image.semantic_mask_path]:
            if path and Path(path).exists():
                Path(path).unlink(missing_ok=True)
        source_dataset.image_count = max(0, source_dataset.image_count - 1)
        source_dataset.annotation_count = max(0, source_dataset.annotation_count - ann_count)
        if image.is_augmented:
            source_dataset.augmented_count = max(0, (source_dataset.augmented_count or 0) - 1)
        await db.delete(image)

        await db.flush()
        await db.refresh(new_image)
        return new_image
