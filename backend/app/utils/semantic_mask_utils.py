"""
语义分割（-sem）单通道 PNG 掩膜工具：像素为 class_id ∈ [0, nc-1]，255 = ignore。
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Optional, Tuple, Union

import numpy as np
from loguru import logger
from PIL import Image


def num_classes_allowed_for_mask(classes: Optional[list]) -> int:
    """与数据集类别表长度一致（下标即 class id）"""
    return len(classes) if classes else 0


def load_png_to_semantic_gray(data: Union[bytes, Path]) -> np.ndarray:
    """读取为二维 uint8 数组 (H,W)。"""
    if isinstance(data, Path):
        with open(data, "rb") as f:
            blob = f.read()
    else:
        blob = data
    img = Image.open(io.BytesIO(blob))
    img = img.convert("L")  # 单通道（含调色板会先转灰度）
    return np.asarray(img, dtype=np.uint8)


def validate_semantic_mask_array(
        arr: np.ndarray,
        img_width: int,
        img_height: int,
        num_classes: int,
) -> Tuple[bool, str]:
    if num_classes <= 0:
        return False, "数据集未定义类别（classes 为空）"
    if arr.ndim != 2:
        return False, "掩膜须为单通道 PNG"
    h, w = arr.shape[:2]
    if w != img_width or h != img_height:
        return False, f"掩膜尺寸 {w}x{h} 与原图 {img_width}x{img_height} 不一致"
    allowed = set(range(num_classes)) | {255}
    bad = None
    for v in np.unique(arr):
        if int(v) not in allowed:
            bad = int(v)
            break
    if bad is not None:
        return False, f"掩膜含非法像素值 {bad}，允许范围为 0..{num_classes - 1} 与 255(忽略)"
    return True, ""


def validate_and_load_semantic_mask_png(
        data: Union[bytes, Path],
        *,
        img_width: int,
        img_height: int,
        classes: Optional[list],
) -> Tuple[Optional[np.ndarray], str]:
    num_classes = num_classes_allowed_for_mask(classes)
    try:
        arr = load_png_to_semantic_gray(data)
    except Exception as e:
        logger.warning("读取语义掩膜失败: {}", e)
        return None, f"无法解析 PNG: {e}"
    ok, msg = validate_semantic_mask_array(arr, img_width, img_height, num_classes)
    if not ok:
        return None, msg
    return arr, ""


def save_semantic_mask_png(path: Path, arr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.fromarray(arr.astype(np.uint8), mode="L")
    im.save(str(path), format="PNG", optimize=True)
