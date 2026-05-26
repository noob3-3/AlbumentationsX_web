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
from app.models import ImageSource, Image, Annotation, Dataset
from app.schemas.schemas import (
    DatasetCreate, DatasetUpdate, DatasetResponse,
    ImageResponse, ImageUploadResponse, AnnotationCreate,
    APICollectionRequest, PaginatedResponse, SuccessResponse,
)
from app.services import DatasetService, collect_from_urls
from app.utils import (
    allowed_image,
    write_yolo_annotation,
    build_yolo_dataset_yaml,
    YOLOV8_POSE_NUM_KEYPOINTS,
)
from app.utils.yolo_label_import import parse_yolo_label_text, merge_label_task_from_upload
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, BackgroundTasks, Request
from fastapi.responses import FileResponse, Response
from loguru import logger
from pathlib import Path
from sqlalchemy import select, func, and_, exists
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Tuple, Any

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _merge_resolved_class_names_into_dataset(dataset, resolved: List[str]) -> None:
    """按索引合并本次导入解析出的类别名，并触发 JSON 字段更新。"""
    from sqlalchemy.orm.attributes import flag_modified

    existing = dataset.classes or []
    out = list(existing)
    for i, name in enumerate(resolved):
        if i < len(out):
            out[i] = name
        else:
            out.append(name)
    dataset.classes = out
    flag_modified(dataset, "classes")


def _resolve_image_disk_path(raw: Optional[str]) -> tuple[Optional[Path], List[str]]:
    """
    DB 中 file_path 可能仍为 static-file，实际文件在 datasets（或相反）。依次尝试互转路径。
    返回 (首个存在的文件 Path, 所有尝试过的路径字符串)。
    """
    if not raw:
        return None, []
    norm = str(raw).replace("\\", "/").strip()
    variants = [norm]
    if "data/static-file/" in norm:
        variants.append(norm.replace("data/static-file/", "data/datasets/", 1))
    if "data/datasets/" in norm:
        variants.append(norm.replace("data/datasets/", "data/static-file/", 1))
    tried: List[str] = []
    seen = set()
    for v in variants:
        if v in seen:
            continue
        seen.add(v)
        tried.append(v)
        p = Path(v)
        if p.is_file():
            if v != norm:
                logger.info("serve_image: 路径回退成功 db 原路径={} -> {}", norm, v)
            return p, tried
    return None, tried


def _find_image_in_dir_case_insensitive(images_dir: Path, filename: str) -> Optional[Path]:
    """与 training_service 一致：大小写不一致时仍能匹配文件名。"""
    if not filename or not images_dir.is_dir():
        return None
    direct = images_dir / filename
    if direct.is_file():
        return direct
    fn_low = filename.lower()
    try:
        for p in images_dir.iterdir():
            if p.is_file() and p.name.lower() == fn_low:
                return p
    except OSError as e:
        logger.debug("serve_image list dir failed {}: {}", images_dir, e)
    return None


def _resolve_serve_image_path(
        image: Image,
        dataset: Optional[Dataset],
        thumbnail: bool,
) -> tuple[Optional[Path], List[str]]:
    """
    解析标注/缩略图可读路径：DB 路径互换 + dataset.storage_path + 标准 DATA_DIR 布局 + 文件名大小写。
    缩略图文件不存在时回退为原图（避免列表首屏全 404）。
    """
    tried: List[str] = []
    seen = set()

    def add_tried(s: str) -> None:
        if s not in seen:
            seen.add(s)
            tried.append(s)

    file_path_str = image.thumbnail_path if thumbnail and image.thumbnail_path else image.file_path
    if not file_path_str:
        return None, tried

    # 1) DB 存的路径 + static-file ↔ datasets
    p, part = _resolve_image_disk_path(file_path_str)
    for x in part:
        add_tried(x)
    if p is not None:
        return p, tried

    # 1b) 与训练导出一致：路径中含 data/datasets 或 data/static-file 时，拼到 BASE_DIR（纠正盘符/前缀错误）
    norm_one = str(file_path_str).replace("\\", "/").strip()
    nl = norm_one.lower()
    for anchor in ("data/static-file/", "data/datasets/"):
        pos = nl.find(anchor)
        if pos >= 0:
            tail = norm_one[pos:]
            p = settings.BASE_DIR / tail
            add_tried(str(p))
            if p.is_file():
                logger.info("serve_image: BASE_DIR+路径后缀回退 {}", p)
                return p, tried

    name = (image.filename or "").strip()
    if not name or dataset is None:
        return None, tried

    sub = "thumbnails" if thumbnail else "images"

    def try_direct(path: Path) -> Optional[Path]:
        add_tried(str(path))
        if path.is_file():
            return path
        alt = _find_image_in_dir_case_insensitive(path.parent, name)
        if alt is not None:
            add_tried(str(alt))
            return alt
        return None

    # 2) dataset.storage_path（可能已指向 datasets 或 static-file）
    if dataset.storage_path:
        sp_raw = str(dataset.storage_path).replace("\\", "/").strip()
        sp = Path(sp_raw)
        sp_bases = [sp]
        if not sp.is_absolute():
            for base in (settings.BASE_DIR, settings.DATA_DIR, Path.cwd()):
                sp_bases.append((base / sp_raw.lstrip("/")).resolve(strict=False))
        for cbase in sp_bases:
            hit = try_direct(cbase / sub / name)
            if hit is not None:
                logger.info("serve_image: 使用 dataset.storage_path 下文件 {}", hit)
                return hit, tried

    # 3) 标准目录：DATASET_DIR、data/datasets、data/static-file
    for base in (
            settings.DATASET_DIR / dataset.id,
            settings.DATA_DIR / "datasets" / dataset.id,
            settings.DATA_DIR / "static-file" / dataset.id,
    ):
        hit = try_direct(base / sub / name)
        if hit is not None:
            logger.info("serve_image: 使用标准目录 {}", hit)
            return hit, tried

    # 4) 缩略图缺失 → 回退原图
    if thumbnail and image.file_path:
        p2, t2 = _resolve_serve_image_path(image, dataset, thumbnail=False)
        tried.extend(x for x in t2 if x not in seen)
        if p2 is not None:
            logger.info("serve_image: 缩略图缺失，回退原图 {}", p2)
            return p2, tried

    return None, tried


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
async def delete_dataset(
        dataset_id: str,
        purge_augmented_only: bool = Query(
            False,
            description="为 True 时仅删除增强生成的图片与标注，并清除数据增强任务记录，保留数据集与原图",
        ),
        db: AsyncSession = Depends(get_db),
):
    if purge_augmented_only:
        ok = await DatasetService.purge_augmented_images(db, dataset_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Dataset not found")
        await db.commit()
        return {"success": True, "message": "已清除增强数据"}
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
        pose: bool = Query(False, description="为 True 时导出 YOLOv8 pose 标签（含 kpt_shape，用于 yolov8*-pose 等）"),
        obb: bool = Query(False, description="为 True 时导出 YOLO OBB 四角点标签（用于 *-obb.pt 训练）"),
        segment: bool = Query(False, description="为 True 时导出实例分割多边形标签（用于 *-seg.pt 训练）"),
        semantic_masks: bool = Query(
            False,
            description="为 True 时按 YOLO 语义分割布局导出 images/train|val + masks/train|val；"
            "label_task=semantic 时默认启用该布局。",
        ),
        val_split: float = Query(
            0.2, ge=0.01, le=0.9,
            description="语义导出时验证集占比（剩余为训练集）；单张图时会自动复制到 train/val。",
        ),
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

    # 筛选已标注图片（若需要）：矢量任务按 Annotation；语义或显式掩膜导出按掩膜文件
    if annotated_only:
        lt0 = (getattr(dataset, "label_task", None) or "").lower()
        use_mask_criteria = lt0 == "semantic" or semantic_masks
        images_with_anns = []
        if use_mask_criteria:
            for img in images:
                mp = getattr(img, "semantic_mask_path", None) or ""
                if mp and Path(mp).is_file():
                    images_with_anns.append(img)
        else:
            for img in images:
                ann_result = await db.execute(
                    select(Annotation).where(Annotation.image_id == img.id)
                )
                if ann_result.scalars().all():
                    images_with_anns.append(img)
        images = images_with_anns
        if not images:
            raise HTTPException(
                status_code=400,
                detail="没有符合「仅已标注」条件的图片（语义任务需已保存 PNG 掩膜）。",
            )

    # 按原始/增强筛选
    if augmented_only:
        images = [img for img in images if getattr(img, "is_augmented", False)]
        if not images:
            raise HTTPException(status_code=400, detail="没有可导出的增强图片")
    elif not include_augmented:
        images = [img for img in images if not getattr(img, "is_augmented", False)]
        if not images:
            raise HTTPException(status_code=400, detail="没有可导出的原始图片")

    is_semantic_ds = (getattr(dataset, "label_task", None) or "").lower() == "semantic"
    use_semantic_zip = is_semantic_ds or semantic_masks

    modes_on = sum([bool(pose), bool(obb), bool(segment)])
    if modes_on > 1:
        raise HTTPException(
            status_code=400,
            detail="导出参数 pose、obb、segment 只能任选其一（或全 False 导出水平框）。",
        )
    if use_semantic_zip and modes_on > 0:
        raise HTTPException(
            status_code=400,
            detail="语义掩膜导出不能与 pose、obb、segment 同时使用，请关闭这些选项。",
        )

    classes = dataset.classes or []
    if not classes:
        if use_semantic_zip:
            raise HTTPException(
                status_code=400,
                detail="语义导出需要数据集预先配置类别列表（classes）。",
            )
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
        if use_semantic_zip:
            import random

            for split in ("train", "val"):
                (temp_dir / "images" / split).mkdir(parents=True, exist_ok=True)
                (temp_dir / "masks" / split).mkdir(parents=True, exist_ok=True)

            pool = list(images)
            random.shuffle(pool)
            n = len(pool)
            vs = min(max(val_split, 0.01), 0.9)
            train_count = max(1, int(n * (1 - vs)))
            if train_count >= n and n > 1:
                train_count = n - 1
            train_imgs = pool[:train_count]
            val_imgs = pool[train_count:]
            if not val_imgs:
                if n == 1:
                    val_imgs = list(pool)
                elif len(train_imgs) > 1:
                    val_imgs = [train_imgs.pop()]
                else:
                    val_imgs = list(pool)

            copied = 0
            for split_name, split_list in (("train", train_imgs), ("val", val_imgs)):
                for img in split_list:
                    mp = getattr(img, "semantic_mask_path", None) or ""
                    if not mp or not Path(mp).is_file():
                        continue
                    src_img = Path(img.file_path)
                    if not src_img.is_file():
                        continue
                    dst_name = (img.filename or "").strip() or src_img.name
                    shutil.copy2(str(src_img), str(temp_dir / "images" / split_name / dst_name))
                    shutil.copy2(
                        str(mp),
                        str(temp_dir / "masks" / split_name / (Path(dst_name).stem + ".png")),
                    )
                    copied += 1

            if copied == 0:
                raise HTTPException(
                    status_code=400,
                    detail="没有可导出的语义样本：请确认图像文件存在且已保存可读 PNG 掩膜。",
                )

            build_yolo_dataset_yaml(
                dataset_dir=str(temp_dir),
                classes=classes,
                train_path="images/train",
                val_path="images/val",
                kpt_shape=None,
                task=None,
                masks_dir="masks",
            )
        else:
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
                        **({"polygon_points": a.polygon_points} if getattr(a, "polygon_points", None) else {}),
                    }
                    for a in anns
                ]
                label_path = labels_dir / (Path(img.filename).stem + ".txt")
                write_yolo_annotation(
                    str(label_path),
                    ann_list,
                    pose=pose,
                    obb=obb and not pose,
                    segment=segment and not pose,
                    num_keypoints=YOLOV8_POSE_NUM_KEYPOINTS,
                )

            _export_task = None
            if pose:
                _export_task = "pose"
            elif obb:
                _export_task = "obb"
            elif segment:
                _export_task = "segment"

            build_yolo_dataset_yaml(
                dataset_dir=str(temp_dir),
                classes=classes,
                train_path="images",
                val_path="images",
                kpt_shape=[YOLOV8_POSE_NUM_KEYPOINTS, 3] if pose else None,
                task=_export_task,
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
        label_format: str = Query(
            "auto",
            description="detect=水平框；obb=OBB四角/多顶点规范化；segment=实例分割多边形(保留顶点)；auto=按行推断",
        ),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload images with corresponding YOLO format label files.
    Label files should have the same filename as images (except extension).

    - **detect**：`class_id x_center y_center width height`（可选第 6 个数 confidence）
    - **obb**：`class_id` 后为 **8 个数（四角）**，或 **至少 6 个数（≥3 顶点）**；非四角时用 minAreaRect 得到四角
    - **segment**：`class_id` 后 **≥6 个数偶数个顶点**，多边形顶点原样写入 polygon_points
    - **auto**：5 个数→detect；8 个数→obb；超过 8 且偶数顶点→segment；6 数三角形→obb
    """
    dataset = await DatasetService.get_dataset(db, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    fmt = (label_format or "auto").lower().strip()
    if fmt not in ("detect", "obb", "segment", "auto"):
        raise HTTPException(status_code=422, detail="label_format 必须是 detect、obb、segment 或 auto")

    # Parse classes.txt if provided
    classes_list: List[str] = []
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
            base_name = Path(label_file.filename).stem
            content = await label_file.read()
            labels_map[base_name] = content.decode('utf-8')

    # ── 先只解析标签（不读图片流），汇总类别 ID，再合并 dataset.classes，最后保存图片并写入 class_name ──
    all_class_ids: set = set()
    all_stats: list = []
    pending: List[Tuple[Any, Optional[list]]] = []

    for image_file in image_files:
        if not allowed_image(image_file.filename):
            logger.warning(f"Skipped non-image file: {image_file.filename}")
            continue

        base_name = Path(image_file.filename).stem
        anns = None
        if base_name in labels_map:
            try:
                label_content = labels_map[base_name]
                anns, stats = parse_yolo_label_text(label_content, fmt)
                all_stats.append(stats)
                for ann in anns:
                    all_class_ids.add(ann["class_id"])
            except Exception as e:
                logger.error(f"Failed to parse label for {image_file.filename}: {e}")
                anns = None

        pending.append((image_file, anns))

    max_id = max(all_class_ids) if all_class_ids else -1
    resolved: Optional[List[str]] = None
    if max_id >= 0:
        if classes_list:
            resolved = list(classes_list)
            while len(resolved) <= max_id:
                resolved.append(f"class_{len(resolved)}")
        else:
            resolved = [f"class_{i}" for i in range(max_id + 1)]

    if resolved:
        _merge_resolved_class_names_into_dataset(dataset, resolved)
        logger.info(f"导入合并类别后 dataset {dataset_id} classes: {dataset.classes}")

    class_names = dataset.classes or []

    results = []
    for image_file, anns in pending:
        if anns:
            for ann in anns:
                cid = int(ann["class_id"])
                if cid < len(class_names):
                    ann["class_name"] = class_names[cid]
                else:
                    ann["class_name"] = f"class_{cid}"

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

    if all_stats:
        dataset.label_task = merge_label_task_from_upload(fmt, all_stats, dataset.label_task)

    await db.commit()
    return {
        "success": True,
        "uploaded": len(results),
        "total_annotations": sum(r['annotations_count'] for r in results),
        "classes": dataset.classes or [],
        "label_format": fmt,
        "label_task": dataset.label_task,
        "parse_stats": all_stats,
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
    if_none_match = request.headers.get("if-none-match")

    image = await DatasetService.get_image(db, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    file_path_str = image.thumbnail_path if thumbnail and image.thumbnail_path else image.file_path
    if not file_path_str:
        logger.warning(
            "serve_image: DB 中无可用路径 image_id={} dataset_id={} thumbnail={} file_path={} thumbnail_path={}",
            image_id,
            image.dataset_id,
            thumbnail,
            image.file_path,
            image.thumbnail_path,
        )
        raise HTTPException(status_code=404, detail="File not found on disk")

    dataset = await DatasetService.get_dataset(db, image.dataset_id)
    resolved_path, tried_paths = _resolve_serve_image_path(image, dataset, thumbnail)
    on_disk = resolved_path is not None

    # 仅当磁盘上仍存在文件时才返回 304；旧逻辑不校验磁盘会导致浏览器长期显示已删除/迁移前的缓存图，
    # 与训练导出「找不到源文件」表现不一致。
    if if_none_match == etag and on_disk:
        return Response(
            status_code=304,
            headers={
                "ETag": etag,
                "Cache-Control": "public, max-age=31536000, immutable",
            }
        )

    if not on_disk:
        logger.warning(
            "serve_image: 磁盘文件不存在（已尝试路径互换、storage_path、标准目录、缩略图回退原图等） "
            "image_id={} dataset_id={} thumbnail={} db.file_path={} db.thumbnail_path={} 尝试数={}",
            image_id,
            image.dataset_id,
            thumbnail,
            image.file_path,
            image.thumbnail_path,
            len(tried_paths),
        )
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        str(resolved_path),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": etag,
        }
    )


@router.post(
    "/{dataset_id}/images/{image_id}/semantic-mask",
    response_model=ImageResponse,
    summary="上传/保存语义分割 PNG 掩膜（label_task=semantic）",
)
async def upload_semantic_mask(
    dataset_id: str,
    image_id: str,
    file: UploadFile = File(..., description="单通道 PNG，像素值为类别 id（255=忽略）"),
    db: AsyncSession = Depends(get_db),
):
    if file.content_type and file.content_type not in ("image/png", "application/octet-stream"):
        raise HTTPException(status_code=415, detail="请上传 PNG 文件")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件为空")
    try:
        image = await DatasetService.save_semantic_mask_png(db, dataset_id, image_id, data)
        await db.commit()
        await db.refresh(image)
        return image
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/{dataset_id}/images/{image_id}/semantic-mask",
    response_model=SuccessResponse,
    summary="删除语义分割掩膜文件及数据库路径",
)
async def delete_semantic_mask_route(dataset_id: str, image_id: str, db: AsyncSession = Depends(get_db)):
    ok = await DatasetService.delete_semantic_mask(db, dataset_id, image_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Image not found")
    await db.commit()
    return {"success": True, "message": "Semantic mask cleared"}


@router.get("/files/semantic-mask/{image_id}", summary="下发语义分割掩膜 PNG")
async def serve_semantic_mask(
    request: Request,
    image_id: str,
    db: AsyncSession = Depends(get_db),
):
    image = await DatasetService.get_image(db, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    p = getattr(image, "semantic_mask_path", None) or ""
    mask_path = Path(p) if p else None
    if not mask_path or not mask_path.is_file():
        raise HTTPException(status_code=404, detail="Semantic mask not found")

    #  etag 必须随磁盘文件变化而变化，否则前端保存后用同一 URL 拉掩膜会持续 304 显示旧 PNG
    try:
        st = mask_path.stat()
        etag = f'"sem-{image_id}-{st.st_mtime_ns}-{st.st_size}"'
    except OSError:
        etag = f'"sem-{image_id}"'

    inm = request.headers.get("if-none-match") or ""
    if inm == etag:
        return Response(
            status_code=304,
            headers={
                "ETag": etag,
                "Cache-Control": "private, max-age=0, must-revalidate",
            },
        )

    return FileResponse(
        str(mask_path),
        media_type="image/png",
        headers={
            "Cache-Control": "private, max-age=0, must-revalidate",
            "ETag": etag,
        },
    )
