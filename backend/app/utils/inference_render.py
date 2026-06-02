"""
推理结果可视化：实例分割采用「半透明掩膜 + 轮廓 + 外接框」，对齐 Ultralytics result.plot() 风格。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import cv2
import numpy as np

# BGR，与前端验证页调色板对应
PALETTE_BGR: List[Tuple[int, int, int]] = [
    (107, 107, 255),
    (209, 206, 78),
    (209, 183, 69),
    (161, 230, 150),
    (221, 160, 221),
    (111, 198, 247),
    (113, 224, 130),
    (138, 148, 248),
    (180, 143, 187),
    (138, 194, 240),
]

MASK_FILL_ALPHA = 0.45


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def polygon_pixels(
    polygon_points: List[List[float]],
    width: int,
    height: int,
) -> np.ndarray:
    pts = np.array(
        [
            [int(_clamp01(p[0]) * width), int(_clamp01(p[1]) * height)]
            for p in polygon_points
        ],
        dtype=np.int32,
    )
    return pts.reshape(-1, 1, 2)


def draw_segment_mask_and_box(
    image_bgr: np.ndarray,
    detection: Dict[str, Any],
    color: Tuple[int, int, int],
    alpha: float = MASK_FILL_ALPHA,
) -> Tuple[int, int]:
    """
    绘制单实例：半透明填充 + 多边形边线 + 水平外接框。
    返回标签锚点 (lx, top_y)。
    """
    h_img, w_img = image_bgr.shape[:2]
    poly_norm = detection.get("polygon_points") or []
    if len(poly_norm) < 3:
        bbox = detection.get("bbox") or [0, 0, 10, 10]
        x1, y1, x2, y2 = map(int, bbox[:4])
        cv2.rectangle(image_bgr, (x1, y1), (x2, y2), color, 2)
        return x1, y1

    pts = polygon_pixels(poly_norm, w_img, h_img)
    overlay = image_bgr.copy()
    cv2.fillPoly(overlay, [pts], color)
    cv2.addWeighted(overlay, alpha, image_bgr, 1.0 - alpha, 0, image_bgr)
    cv2.polylines(image_bgr, [pts], True, color, 2)

    bbox = detection.get("bbox")
    if bbox and len(bbox) >= 4:
        x1, y1, x2, y2 = map(int, bbox[:4])
        cv2.rectangle(image_bgr, (x1, y1), (x2, y2), color, 2)
        return x1, y1

    flat = pts.reshape(-1, 2)
    return int(np.mean(flat[:, 0])), int(np.min(flat[:, 1]))


def is_segment_detection(detection: Dict[str, Any]) -> bool:
    if detection.get("task") == "segment":
        return True
    poly = detection.get("polygon_points")
    return bool(poly and len(poly) >= 3 and not detection.get("obb_xyxyxyxy"))


def color_for_index(index: int) -> Tuple[int, int, int]:
    return PALETTE_BGR[index % len(PALETTE_BGR)]
