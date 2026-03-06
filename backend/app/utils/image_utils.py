"""
Image processing utilities
"""
import os
import uuid
import hashlib
from pathlib import Path
from typing import Optional, Tuple
import cv2
import numpy as np
from PIL import Image
from loguru import logger


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


def write_yolo_annotation(label_path: str, annotations: list) -> bool:
    """Write YOLO format annotation file"""
    try:
        with open(label_path, "w") as f:
            for ann in annotations:
                f.write(
                    f"{ann['class_id']} {ann['x_center']:.6f} "
                    f"{ann['y_center']:.6f} {ann['bbox_width']:.6f} "
                    f"{ann['bbox_height']:.6f}\n"
                )
        return True
    except Exception as e:
        logger.warning(f"Could not write annotation {label_path}: {e}")
        return False
