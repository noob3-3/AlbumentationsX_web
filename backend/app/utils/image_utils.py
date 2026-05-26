"""
Image processing utilities
"""
import cv2
import hashlib
import math
import numpy as np
import os
import uuid
from PIL import Image
from loguru import logger
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


def generate_filename(original_filename: str, prefix: str = "") -> str:
    """Generate a unique filename preserving extension"""
    ext = Path(original_filename).suffix.lower()
    unique_id = str(uuid.uuid4())[:8]
    base = Path(original_filename).stem[:32]
    if prefix:
        return f"{prefix}_{base}_{unique_id}{ext}"
    return f"{base}_{unique_id}{ext}"


def get_image_info(file_path: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """Return (width, height, file_size) of an image"""
    try:
        file_size = os.path.getsize(file_path)
        with Image.open(file_path) as img:
            width, height = img.size
        return width, height, file_size
    except Exception as e:
        logger.warning(f"Could not read image info for {file_path}: {e}")
        return None, None, None


def create_thumbnail(src_path: str, dst_path: str, size: Tuple[int, int] = (256, 256)) -> bool:
    """Create a thumbnail of the given image"""
    try:
        with Image.open(src_path) as img:
            img.thumbnail(size, Image.LANCZOS)
            img.save(dst_path, optimize=True, quality=85)
        return True
    except Exception as e:
        logger.warning(f"Could not create thumbnail for {src_path}: {e}")
        return False


def ensure_rgb(image_path: str) -> Optional[np.ndarray]:
    """Load image as RGB numpy array"""
    try:
        img = cv2.imread(image_path)
        if img is None:
            return None
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    except Exception as e:
        logger.warning(f"Could not load image {image_path}: {e}")
        return None


def save_image(image: np.ndarray, path: str) -> bool:
    """Save RGB numpy array as image"""
    try:
        bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        cv2.imwrite(path, bgr)
        return True
    except Exception as e:
        logger.warning(f"Could not save image to {path}: {e}")
        return False


# YOLOv8 pose 预训练（如 yolov8n-pose.pt）默认 COCO 17 关键点
YOLOV8_POSE_NUM_KEYPOINTS = 17


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def sample_polygon_perimeter_keypoints(
        polygon_norm: Sequence[Sequence[float]],
        num_keypoints: int = YOLOV8_POSE_NUM_KEYPOINTS,
) -> List[Tuple[float, float, float]]:
    """沿闭合多边形周长均匀采样 num_keypoints 个 (x,y,v)，坐标为相对整图归一化，v=2 可见。"""
    pts = [(float(p[0]), float(p[1])) for p in polygon_norm]
    if len(pts) < 3:
        raise ValueError("polygon must have at least 3 points")
    ring = pts + [pts[0]]
    seg_lens: List[float] = []
    for i in range(len(ring) - 1):
        dx = ring[i + 1][0] - ring[i][0]
        dy = ring[i + 1][1] - ring[i][1]
        seg_lens.append(math.hypot(dx, dy))
    total = sum(seg_lens)
    if total < 1e-12:
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        return [(cx, cy, 2.0)] * num_keypoints

    out: List[Tuple[float, float, float]] = []
    for k in range(num_keypoints):
        dist = (k + 0.5) / num_keypoints * total
        acc = 0.0
        placed = False
        for i, slen in enumerate(seg_lens):
            if acc + slen >= dist - 1e-15:
                t = (dist - acc) / slen if slen > 1e-12 else 0.0
                x = ring[i][0] + t * (ring[i + 1][0] - ring[i][0])
                y = ring[i][1] + t * (ring[i + 1][1] - ring[i][1])
                out.append((_clamp01(x), _clamp01(y), 2.0))
                placed = True
                break
            acc += slen
        if not placed:
            out.append((_clamp01(pts[-1][0]), _clamp01(pts[-1][1]), 2.0))
    return out


def bbox_perimeter_keypoints(
        cx: float,
        cy: float,
        bw: float,
        bh: float,
        num_keypoints: int = YOLOV8_POSE_NUM_KEYPOINTS,
) -> List[Tuple[float, float, float]]:
    """无多边形时，沿检测框四边均匀采样关键点（用于纯框 pose 标签）。"""
    x1 = cx - bw / 2
    y1 = cy - bh / 2
    x2 = cx + bw / 2
    y2 = cy + bh / 2
    corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    return sample_polygon_perimeter_keypoints(corners, num_keypoints)


def annotation_to_obb_corners(
        ann: dict,
) -> Tuple[float, float, float, float, float, float, float, float]:
    """
    Ultralytics YOLO OBB 标签：每行 class x1 y1 x2 y2 x3 y3 x4 y4（归一化）。
    四点多边形按顶点顺序输出；否则由水平框生成轴对齐四角（左上→右上→右下→左下）。
    """
    poly = ann.get("polygon_points")
    if poly and len(poly) == 4:
        pts = [(_clamp01(float(p[0])), _clamp01(float(p[1]))) for p in poly]
        return (
            pts[0][0], pts[0][1],
            pts[1][0], pts[1][1],
            pts[2][0], pts[2][1],
            pts[3][0], pts[3][1],
        )
    cx = float(ann["x_center"])
    cy = float(ann["y_center"])
    w = float(ann["bbox_width"])
    h = float(ann["bbox_height"])
    hw, hh = w / 2.0, h / 2.0
    x1, y1 = _clamp01(cx - hw), _clamp01(cy - hh)
    x2, y2 = _clamp01(cx + hw), _clamp01(cy - hh)
    x3, y3 = _clamp01(cx + hw), _clamp01(cy + hh)
    x4, y4 = _clamp01(cx - hw), _clamp01(cy + hh)
    return (x1, y1, x2, y2, x3, y3, x4, y4)


def annotation_polygon_normalized_for_segment(ann: dict) -> List[Tuple[float, float]]:
    """
    YOLO 实例分割标签：一行 class x1 y1 x2 y2 ...（归一化）。
    优先 polygon_points（≥3 点）；否则用水平框四角。
    """
    poly = ann.get("polygon_points")
    if poly and len(poly) >= 3:
        return [(_clamp01(float(p[0])), _clamp01(float(p[1]))) for p in poly]
    cx = float(ann["x_center"])
    cy = float(ann["y_center"])
    w = float(ann["bbox_width"])
    h = float(ann["bbox_height"])
    hw, hh = w / 2.0, h / 2.0
    x1, y1 = _clamp01(cx - hw), _clamp01(cy - hh)
    x2, y2 = _clamp01(cx + hw), _clamp01(cy - hh)
    x3, y3 = _clamp01(cx + hw), _clamp01(cy + hh)
    x4, y4 = _clamp01(cx - hw), _clamp01(cy + hh)
    return [(x1, y1), (x2, y2), (x3, y3), (x4, y4)]


def annotation_to_pose_keypoints(
        ann: dict,
        num_keypoints: int = YOLOV8_POSE_NUM_KEYPOINTS,
) -> List[Tuple[float, float, float]]:
    poly = ann.get("polygon_points")
    if poly and len(poly) >= 3:
        return sample_polygon_perimeter_keypoints(poly, num_keypoints)
    return bbox_perimeter_keypoints(
        ann["x_center"], ann["y_center"], ann["bbox_width"], ann["bbox_height"], num_keypoints
    )


def read_yolo_annotation(label_path: str) -> list:
    """Read YOLO format annotation file"""
    annotations = []
    if not os.path.exists(label_path):
        return annotations
    try:
        with open(label_path, "r") as f:
            for line in f.readlines():
                parts = line.strip().split()
                if len(parts) >= 5:
                    class_id = int(parts[0])
                    cx, cy, w, h = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                    conf = float(parts[5]) if len(parts) > 5 else None
                    annotations.append({
                        "class_id": class_id,
                        "x_center": cx,
                        "y_center": cy,
                        "bbox_width": w,
                        "bbox_height": h,
                        "confidence": conf,
                    })
    except Exception as e:
        logger.warning(f"Could not read annotation {label_path}: {e}")
    return annotations


def write_yolo_annotation(
        label_path: str,
        annotations: list,
        *,
        pose: bool = False,
        obb: bool = False,
        segment: bool = False,
        num_keypoints: int = YOLOV8_POSE_NUM_KEYPOINTS,
) -> bool:
    """Write YOLO 标签：detect / pose / obb / segment 四选一（按优先级 pose > obb > segment > detect）。"""
    modes = sum([bool(pose), bool(obb), bool(segment)])
    if modes > 1:
        logger.warning(
            "write_yolo_annotation: 多个导出模式同时为 True（pose/obb/segment），"
            "使用优先级 pose > obb > segment > detect",
        )
    if pose:
        obb = False
        segment = False
    elif obb:
        segment = False
    try:
        with open(label_path, "w") as f:
            for ann in annotations:
                if pose:
                    kpts = annotation_to_pose_keypoints(ann, num_keypoints)
                    parts = [
                        str(ann["class_id"]),
                        f"{ann['x_center']:.6f}",
                        f"{ann['y_center']:.6f}",
                        f"{ann['bbox_width']:.6f}",
                        f"{ann['bbox_height']:.6f}",
                    ]
                    for x, y, v in kpts:
                        parts.append(f"{x:.6f}")
                        parts.append(f"{y:.6f}")
                        parts.append(str(int(v)))
                    f.write(" ".join(parts) + "\n")
                elif obb:
                    c = annotation_to_obb_corners(ann)
                    f.write(
                        f"{ann['class_id']} {c[0]:.6f} {c[1]:.6f} {c[2]:.6f} {c[3]:.6f} "
                        f"{c[4]:.6f} {c[5]:.6f} {c[6]:.6f} {c[7]:.6f}\n"
                    )
                elif segment:
                    pts = annotation_polygon_normalized_for_segment(ann)
                    parts = [str(ann["class_id"])] + [
                        cx
                        for xy in pts
                        for cx in (f"{xy[0]:.6f}", f"{xy[1]:.6f}")
                    ]
                    f.write(" ".join(parts) + "\n")
                else:
                    f.write(
                        f"{ann['class_id']} {ann['x_center']:.6f} "
                        f"{ann['y_center']:.6f} {ann['bbox_width']:.6f} "
                        f"{ann['bbox_height']:.6f}\n"
                    )
        return True
    except Exception as e:
        logger.warning(f"Could not write annotation {label_path}: {e}")
        return False
