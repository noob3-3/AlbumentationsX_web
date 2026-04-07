"""
Dataset API endpoints
"""
import json
import re
import shutil
import tempfile
import zipfile
from app.core.config import settings
from app.core.database import get_db
from app.models import ImageSource, Image, Annotation
from app.schemas.schemas import (
    DatasetCreate, DatasetUpdate, DatasetResponse,
    ImageResponse, ImageUploadResponse, AnnotationCreate,
    APICollectionRequest, PaginatedResponse, SuccessResponse,
)
from app.services import DatasetService, collect_from_urls
from app.utils import allowed_image, write_yolo_annotation, build_yolo_dataset_yaml
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, BackgroundTasks, Request
from fastapi.responses import FileResponse, Response
from loguru import logger
from pathlib import Path
from sqlalchemy import select, func, and_, exists
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

router = APIRouter(prefix="/datasets", tags=["datasets"])


# ─────────────────────────────────────────────
# Dataset CRUD
# ─────────────────────────────────────────────
@router.post("", response_model=DatasetResponse, summary="Create dataset")
async def create_dataset(data: DatasetCreate, db: AsyncSession = Depends(get_db)):
    dataset = await DatasetService.create_dataset(db, data)
    await db.commit()
    return dataset


@router.get("", response_model=PaginatedResponse, summary="List datasets")
async def list_datasets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    db: AsyncSession = Depends(get_db),
):
    skip = (page - 1) * page_size
    datasets, total = await DatasetService.list_datasets(
        db, skip=skip, limit=page_size, project_id=project_id
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [DatasetResponse.model_validate(d) for d in datasets],
    }


@router.get("/{dataset_id}", response_model=DatasetResponse, summary="Get dataset")
async def get_dataset(dataset_id: str, db: AsyncSession = Depends(get_db)):
    dataset = await DatasetService.get_dataset(db, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


@router.get("/{dataset_id}/stats", summary="Get dataset annotation statistics")
async def get_dataset_stats(dataset_id: str, db: AsyncSession = Depends(get_db)):
    """获取数据集的真实标注统计信息"""
    dataset = await DatasetService.get_dataset(db, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # 有标注的图片子查询
    has_annotation = (
        select(Annotation.image_id)
        .where(Annotation.image_id == Image.id)
        .correlate(Image)
        .exists()
    )

    # 总图片数
    total_images = dataset.image_count
    original_count = total_images - (dataset.augmented_count or 0)
    augmented_count = dataset.augmented_count or 0

    # 已标注的图片数（有至少一条 annotation）
    annotated_result = await db.execute(
        select(func.count()).select_from(Image).where(
            and_(Image.dataset_id == dataset_id, has_annotation)
        )
    )
    annotated_image_count = annotated_result.scalar() or 0

    # 已标注的增强图片数
    augmented_annotated_result = await db.execute(
        select(func.count()).select_from(Image).where(
            and_(Image.dataset_id == dataset_id, Image.is_augmented == True, has_annotation)
        )
    )
    augmented_annotated_count = augmented_annotated_result.scalar() or 0

    # 已标注的原始图片数
    original_annotated_result = await db.execute(
        select(func.count()).select_from(Image).where(
            and_(Image.dataset_id == dataset_id, Image.is_augmented == False, has_annotation)
        )
    )
    original_annotated_count = original_annotated_result.scalar() or 0

    return {
        "total_images": total_images,
        "original_count": original_count,
        "augmented_count": augmented_count,
        "annotated_image_count": annotated_image_count,
        "original_annotated_count": original_annotated_count,
        "augmented_annotated_count": augmented_annotated_count,
        "augmented_unannotated_count": augmented_count - augmented_annotated_count,
        "original_unannotated_count": original_count - original_annotated_count,
    }


@router.put("/{dataset_id}", response_model=DatasetResponse, summary="Update dataset")
async def update_dataset(
    dataset_id: str, data: DatasetUpdate, db: AsyncSession = Depends(get_db)
):
    dataset = await DatasetService.update_dataset(db, dataset_id, data)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    await db.commit()
    return dataset


@router.delete("/{dataset_id}", response_model=SuccessResponse, summary="Delete dataset")
async def delete_dataset(dataset_id: str, db: AsyncSession = Depends(get_db)):
    deleted = await DatasetService.delete_dataset(db, dataset_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Dataset not found")
    await db.commit()
    return {"success": True, "message": "Dataset deleted"}


@router.get("/{dataset_id}/export", summary="Export dataset as YOLO format ZIP")
async def export_dataset(
    dataset_id: str,
    annotated_only: bool = Query(False, description="仅导出已标注的图片"),
        include_augmented: bool = Query(True, description="是否包含增强生成的图片；为 False 时仅导出原始图"),
        augmented_only: bool = Query(False,
                                     description="为 True 时仅导出增强图片（与 include_augmented 同时传时以此为准）"),
    db: AsyncSession = Depends(get_db),
):
    """导出数据集为 YOLO 格式 ZIP 包（含 images/、labels/、dataset.yaml、classes.txt）"""
    dataset = await DatasetService.get_dataset(db, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # 获取图片列表
    query = select(Image).where(Image.dataset_id == dataset_id)
    result = await db.execute(query)
    images = result.scalars().all()

    if not images:
        raise HTTPException(status_code=400, detail="Dataset has no images")

    # 筛选已标注图片（若需要）
    if annotated_only:
        images_with_anns = []
        for img in images:
            ann_result = await db.execute(
                select(Annotation).where(Annotation.image_id == img.id)
            )
            if ann_result.scalars().all():
                images_with_anns.append(img)
        images = images_with_anns
        if not images:
            raise HTTPException(status_code=400, detail="Dataset has no images with annotations")

    # 按原始/增强筛选
    if augmented_only:
        images = [img for img in images if getattr(img, "is_augmented", False)]
        if not images:
            raise HTTPException(status_code=400, detail="没有可导出的增强图片")
    elif not include_augmented:
        images = [img for img in images if not getattr(img, "is_augmented", False)]
        if not images:
            raise HTTPException(status_code=400, detail="没有可导出的原始图片")

    classes = dataset.classes or []
    if not classes:
        # 从标注提取类别
        class_query = await db.execute(
            select(Annotation.class_id, Annotation.class_name)
            .join(Image, Image.id == Annotation.image_id)
            .where(Image.dataset_id == dataset_id)
            .distinct()
            .order_by(Annotation.class_id)
        )
        class_rows = class_query.all()
        if class_rows:
            max_cid = max(row.class_id for row in class_rows)
            classes = [""] * (max_cid + 1)
            for row in class_rows:
                classes[row.class_id] = row.class_name or str(row.class_id)

    temp_dir = Path(tempfile.mkdtemp())
    try:
        images_dir = temp_dir / "images"
        labels_dir = temp_dir / "labels"
        images_dir.mkdir()
        labels_dir.mkdir()

        for img in images:
            src = Path(img.file_path)
            if not src.exists():
                continue
            dst_img = images_dir / img.filename
            shutil.copy2(str(src), str(dst_img))

            ann_result = await db.execute(
                select(Annotation).where(Annotation.image_id == img.id)
            )
            anns = ann_result.scalars().all()
            ann_list = [
                {
                    "class_id": a.class_id,
                    "x_center": a.x_center,
                    "y_center": a.y_center,
                    "bbox_width": a.bbox_width,
                    "bbox_height": a.bbox_height,
                }
                for a in anns
            ]
            label_path = labels_dir / (Path(img.filename).stem + ".txt")
            write_yolo_annotation(str(label_path), ann_list)

        build_yolo_dataset_yaml(
            dataset_dir=str(temp_dir),
            classes=classes,
            train_path="images",
            val_path="images",
        )

        # classes.txt
        if classes:
            (temp_dir / "classes.txt").write_text("\n".join(classes), encoding="utf-8")

        safe_name = re.sub(r'[<>:"/\\|?*]', '_', dataset.name)
        zip_path = Path(tempfile.gettempdir()) / f"dataset_{safe_name}_{dataset_id[:8]}.zip"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in temp_dir.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(temp_dir))

        return FileResponse(
            str(zip_path),
            filename=f"{safe_name}_yolo.zip",
            media_type="application/zip",
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ─────────────────────────────────────────────
# Image management
# ─────────────────────────────────────────────
@router.post("/{dataset_id}/images/upload", response_model=list[ImageUploadResponse], summary="Upload images")
async def upload_images(
    dataset_id: str,
    files: list[UploadFile] = File(...),
    annotations_json: Optional[str] = Form(None),  # JSON: list of list of annotations
    db: AsyncSession = Depends(get_db),
):
    dataset = await DatasetService.get_dataset(db, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    annotations_list = None
    if annotations_json:
        try:
            annotations_list = json.loads(annotations_json)
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid annotations JSON")

    results = []
    for idx, file in enumerate(files):
        if not allowed_image(file.filename):
            logger.warning(f"Skipped non-image file: {file.filename}")
            continue

        anns = None
        if annotations_list and idx < len(annotations_list):
            raw = annotations_list[idx]
            if raw:
                anns = [AnnotationCreate(**a).model_dump() for a in raw]

        # 使用流式上传，避免内存溢出
        image = await DatasetService.save_uploaded_image_stream(
            db=db,
            dataset_id=dataset_id,
            file=file,
            original_filename=file.filename,
            source=ImageSource.LOCAL,
            annotations=anns,
        )
        if image:
            results.append(ImageUploadResponse(
                id=image.id,
                filename=image.filename,
                dataset_id=dataset_id,
                width=image.width,
                height=image.height,
                file_size=image.file_size,
            ))

    await db.commit()
    return results


@router.post("/{dataset_id}/images/upload-with-labels", response_model=dict, summary="Upload images with YOLO format labels")
async def upload_images_with_labels(
    dataset_id: str,
    image_files: list[UploadFile] = File(..., description="Image files"),
    label_files: list[UploadFile] = File(None, description="Label files (.txt) in YOLO format"),
    classes_file: UploadFile = File(None, description="classes.txt file with one class name per line"),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload images with corresponding YOLO format label files.
    Label files should have the same filename as images (except extension).
    YOLO format: class_id x_center y_center width height (one line per object)
    Optionally include a classes.txt file (one class name per line) to map class_id to class_name.
    """
    dataset = await DatasetService.get_dataset(db, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Parse classes.txt if provided
    classes_list = []
    if classes_file:
        try:
            content = await classes_file.read()
            classes_list = [line.strip() for line in content.decode('utf-8').strip().split('\n') if line.strip()]
            logger.info(f"Parsed {len(classes_list)} classes from classes.txt: {classes_list}")
        except Exception as e:
            logger.error(f"Failed to parse classes file: {e}")

    # Build a map of label filename (without ext) to label content
    labels_map = {}
    if label_files:
        for label_file in label_files:
            if not label_file.filename.endswith('.txt'):
                continue
            # Get base name without extension
            base_name = Path(label_file.filename).stem
            content = await label_file.read()
            labels_map[base_name] = content.decode('utf-8')

    # Collect all encountered class_ids to auto-generate classes if no classes.txt provided
    all_class_ids = set()

    results = []
    for image_file in image_files:
        if not allowed_image(image_file.filename):
            logger.warning(f"Skipped non-image file: {image_file.filename}")
            continue

        # Parse annotations from corresponding label file
        base_name = Path(image_file.filename).stem
        anns = None
        if base_name in labels_map:
            try:
                anns = []
                label_content = labels_map[base_name]
                for line in label_content.strip().split('\n'):
                    if not line.strip():
                        continue
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        class_id = int(parts[0])
                        x_center = float(parts[1])
                        y_center = float(parts[2])
                        bbox_width = float(parts[3])
                        bbox_height = float(parts[4])
                        all_class_ids.add(class_id)
                        # Map class_id to class_name if classes list is available
                        class_name = None
                        if classes_list and class_id < len(classes_list):
                            class_name = classes_list[class_id]
                        anns.append({
                            'class_id': class_id,
                            'class_name': class_name,
                            'x_center': x_center,
                            'y_center': y_center,
                            'bbox_width': bbox_width,
                            'bbox_height': bbox_height,
                        })
            except Exception as e:
                logger.error(f"Failed to parse label for {image_file.filename}: {e}")
                anns = None

        # 使用流式上传避免内存溢出
        image = await DatasetService.save_uploaded_image_stream(
            db=db,
            dataset_id=dataset_id,
            file=image_file,
            original_filename=image_file.filename,
            source=ImageSource.LOCAL,
            annotations=anns,
        )
        if image:
            results.append({
                'id': image.id,
                'filename': image.filename,
                'annotations_count': len(anns) if anns else 0,
            })

    # Update dataset classes
    if classes_list:
        # Use the provided classes.txt
        new_classes = classes_list
    elif all_class_ids:
        # Auto-generate class names from class_ids (e.g., "class_0", "class_1")
        max_id = max(all_class_ids)
        new_classes = [f"class_{i}" for i in range(max_id + 1)]
    else:
        new_classes = None

    if new_classes:
        # Merge with existing classes
        existing = dataset.classes or []
        if len(new_classes) > len(existing):
            # Extend: keep existing names, fill in new ones
            merged = list(existing)
            for i in range(len(existing), len(new_classes)):
                merged.append(new_classes[i])
            dataset.classes = merged
        elif not existing:
            dataset.classes = new_classes
        logger.info(f"Updated dataset {dataset_id} classes: {dataset.classes}")

    await db.commit()
    return {
        "success": True,
        "uploaded": len(results),
        "total_annotations": sum(r['annotations_count'] for r in results),
        "classes": dataset.classes or [],
        "details": results,
    }


@router.post("/{dataset_id}/images/collect-from-urls", summary="Collect images from URLs")
async def collect_from_urls_endpoint(
    dataset_id: str,
    data: APICollectionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    dataset = await DatasetService.get_dataset(db, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    results = await collect_from_urls(
        urls=data.urls,
        dataset_service=DatasetService,
        db=db,
        dataset_id=dataset_id,
        annotations_per_image=data.annotations,
    )
    await db.commit()
    return {
        "success": True,
        "collected": len(results["success"]),
        "failed": len(results["failed"]),
        "details": results,
    }


@router.get("/{dataset_id}/images", summary="List dataset images")
async def list_images(
    dataset_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    augmented_only: Optional[bool] = Query(None, description="None=全部, False=仅原始, True=仅增强"),
    db: AsyncSession = Depends(get_db),
):
    skip = (page - 1) * page_size
    images, total = await DatasetService.get_images(
        db, dataset_id, skip=skip, limit=page_size, augmented_only=augmented_only
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [ImageResponse.model_validate(img) for img in images],
    }


@router.get("/{dataset_id}/images/{image_id}", response_model=ImageResponse, summary="Get image details")
async def get_image(dataset_id: str, image_id: str, db: AsyncSession = Depends(get_db)):
    image = await DatasetService.get_image(db, image_id)
    if not image or image.dataset_id != dataset_id:
        raise HTTPException(status_code=404, detail="Image not found")
    return image


@router.delete("/{dataset_id}/images/{image_id}", response_model=SuccessResponse, summary="Delete image")
async def delete_image(dataset_id: str, image_id: str, db: AsyncSession = Depends(get_db)):
    image = await DatasetService.get_image(db, image_id)
    if not image or image.dataset_id != dataset_id:
        raise HTTPException(status_code=404, detail="Image not found")
    await DatasetService.delete_image(db, image_id)
    await db.commit()
    return {"success": True, "message": "Image deleted"}


@router.post("/{dataset_id}/images/{image_id}/move", summary="Move image to another dataset")
async def move_image(
    dataset_id: str,
    image_id: str,
    target_dataset_id: str = Query(..., description="目标数据集ID"),
    db: AsyncSession = Depends(get_db),
):
    """将图片及其标注移动到另一个数据集"""
    try:
        new_image = await DatasetService.move_image_to_dataset(
            db, dataset_id, image_id, target_dataset_id
        )
        await db.commit()
        return {
            "success": True,
            "message": "图片已移动",
            "new_image_id": new_image.id,
            "target_dataset_id": target_dataset_id,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{dataset_id}/classes/{class_name}", summary="Delete class and its annotations")
async def delete_class(dataset_id: str, class_name: str, db: AsyncSession = Depends(get_db)):
    """删除类别及其所有标注数据"""
    from urllib.parse import unquote
    from app.models import Annotation

    # URL decode class name
    class_name = unquote(class_name)

    # Get dataset
    dataset = await DatasetService.get_dataset(db, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Check if class exists
    if not dataset.classes or class_name not in dataset.classes:
        raise HTTPException(status_code=404, detail=f"Class '{class_name}' not found in dataset")

    # Get class_id
    class_id = dataset.classes.index(class_name)

    # Delete all annotations with this class_id for images in this dataset
    images_result = await db.execute(
        select(Image).where(Image.dataset_id == dataset_id)
    )
    image_ids = [img.id for img in images_result.scalars().all()]

    # Delete annotations
    delete_result = await db.execute(
        select(Annotation).where(
            Annotation.image_id.in_(image_ids),
            Annotation.class_id == class_id
        )
    )
    annotations_to_delete = delete_result.scalars().all()
    deleted_count = len(annotations_to_delete)

    for annotation in annotations_to_delete:
        await db.delete(annotation)

    # Remove class from dataset.classes
    new_classes = [cls for cls in dataset.classes if cls != class_name]
    dataset.classes = new_classes

    # Update class_id for remaining annotations (shift down if needed)
    for img_id in image_ids:
        anns_result = await db.execute(
            select(Annotation).where(Annotation.image_id == img_id)
        )
        for ann in anns_result.scalars().all():
            if ann.class_id > class_id:
                ann.class_id -= 1

    await db.commit()

    logger.info(f"Deleted class '{class_name}' (id={class_id}) from dataset {dataset_id}, removed {deleted_count} annotations")

    return {
        "success": True,
        "message": f"Class '{class_name}' deleted",
        "deleted_annotations_count": deleted_count
    }


# ─────────────────────────────────────────────
# Serve image files
# ─────────────────────────────────────────────
@router.get("/files/image/{image_id}", summary="Serve image file")
async def serve_image(
    request: Request,
    image_id: str,
    thumbnail: bool = Query(False),
    db: AsyncSession = Depends(get_db)
):
    # Generate ETag based on image_id
    etag = f'"{image_id}"'

    # Check If-None-Match header for cache validation
    if_none_match = request.headers.get("if-none-match")
    if if_none_match == etag:
        # Client has cached version, return 304 Not Modified
        return Response(
            status_code=304,
            headers={
                "ETag": etag,
                "Cache-Control": "public, max-age=31536000, immutable",
            }
        )

    # Cache miss or first request - fetch from database
    image = await DatasetService.get_image(db, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    file_path = image.thumbnail_path if thumbnail and image.thumbnail_path else image.file_path
    if not file_path or not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    # Return FileResponse with aggressive caching headers
    # Images don't change once uploaded, so cache for 1 year
    return FileResponse(
        file_path,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",  # 1 year cache
            "ETag": etag,  # Use image_id as ETag for cache validation
        }
    )
