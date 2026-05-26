"""
从 YOLO 文本标签导入为平台 Annotation 字典（detect / OBB / segment / 自动推断）。

- detect: class cx cy w h
- OBB（旋转框）: Ultralytics 训练文件每实例为 **4 个角点（8 个坐标）**；导入时亦支持 **至少 3 个顶点**（6 个坐标，三角形），
  内部用 minAreaRect 规范为 4 角再写入 polygon_points。
- segment（实例分割）: class x1 y1 x2 y2 ... **保留全部顶点**（≥3 点，偶数个坐标），polygon_points 存储原多边形。
- auto: 在 detect / OBB / segment 间按列数推断；**超过 4 个顶点（>8 个数）的行**按segment 解析以保留轮廓。
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple

import cv2
import numpy as np
from loguru import logger

FormatMode = Literal["detect", "obb", "segment", "auto"]


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _axis_bbox_from_points(pts: List[List[float]]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    w = max(float(xmax - xmin), 1e-9)
    h = max(float(ymax - ymin), 1e-9)
    cx = float((xmin + xmax) / 2.0)
    cy = float((ymin + ymax) / 2.0)
    return cx, cy, w, h


def points_to_four_corners(pts: List[List[float]]) -> List[List[float]]:
    """将 **至少 3 个** 顶点规范为 4 个角点（cv2.minAreaRect）；已为 4 点时原样返回。"""
    if len(pts) < 3:
        raise ValueError(f"OBB 至少需要 3 个顶点，当前 {len(pts)} 个")
    if len(pts) == 4:
        return [[_clamp01(p[0]), _clamp01(p[1])] for p in pts]
    arr = np.array(pts, dtype=np.float32).reshape((-1, 1, 2))
    rect = cv2.minAreaRect(arr)
    box = cv2.boxPoints(rect)
    out: List[List[float]] = []
    for i in range(4):
        out.append([_clamp01(float(box[i][0])), _clamp01(float(box[i][1]))])
    return out


def parse_yolo_label_line(
    parts: List[str],
    mode: FormatMode,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    解析单行 YOLO 文本。
    返回 (annotation_dict, inferred_tag) inferred_tag 为 'detect' | 'obb' | 'segment' | None（失败）
    """
    if not parts or len(parts) < 2:
        return None, None
    try:
        class_id = int(parts[0])
    except ValueError:
        return None, None

    floats = []
    try:
        for x in parts[1:]:
            floats.append(float(x))
    except ValueError:
        return None, None

    n = len(floats)
    def detect_dict() -> Optional[Dict[str, Any]]:
        if n < 4:
            return None
        return {
            "class_id": class_id,
            "x_center": _clamp01(floats[0]),
            "y_center": _clamp01(floats[1]),
            "bbox_width": max(1e-9, min(1.0, floats[2])),
            "bbox_height": max(1e-9, min(1.0, floats[3])),
            "polygon_points": None,
            "confidence": float(floats[4]) if n > 4 else None,
        }

    def obb_from_pairs(pair_count: int) -> Optional[Dict[str, Any]]:
        if n != pair_count * 2:
            return None
        pts = [[floats[i], floats[i + 1]] for i in range(0, n, 2)]
        four = points_to_four_corners(pts)
        cx, cy, bw, bh = _axis_bbox_from_points(four)
        return {
            "class_id": class_id,
            "x_center": _clamp01(cx),
            "y_center": _clamp01(cy),
            "bbox_width": max(1e-9, min(1.0, bw)),
            "bbox_height": max(1e-9, min(1.0, bh)),
            "polygon_points": four,
            "confidence": None,
        }

    def segment_from_pairs() -> Optional[Dict[str, Any]]:
        if n < 6 or n % 2 != 0:
            return None
        pairs = n // 2
        if pairs < 3:
            return None
        pts = [[_clamp01(floats[i]), _clamp01(floats[i + 1])] for i in range(0, n, 2)]
        cx, cy, bw, bh = _axis_bbox_from_points(pts)
        return {
            "class_id": class_id,
            "x_center": _clamp01(cx),
            "y_center": _clamp01(cy),
            "bbox_width": max(1e-9, min(1.0, bw)),
            "bbox_height": max(1e-9, min(1.0, bh)),
            "polygon_points": pts,
            "confidence": None,
        }

    if mode == "detect":
        d = detect_dict()
        return (d, "detect") if d else (None, None)

    if mode == "segment":
        d = segment_from_pairs()
        return (d, "segment") if d else (None, None)

    if mode == "obb":
        if n == 8:
            d = obb_from_pairs(4)
            return (d, "obb") if d else (None, None)
        if n >= 6 and n % 2 == 0:
            pairs = n // 2
            if pairs >= 3:
                d = obb_from_pairs(pairs)
                return (d, "obb") if d else (None, None)
        logger.warning(
            "OBB 模式下行列数不合法: 需要 class + 8 个数(四角) 或 class + 至少 6 个数(≥3 顶点)，当前 class 后 {} 个数",
            n,
        )
        return None, None

    # auto（detect 常为 class + 4 数；带 confidence 时为 5 个数）
    if n in (4, 5):
        d = detect_dict()
        return (d, "detect") if d else (None, None)
    if n == 8:
        d = obb_from_pairs(4)
        return (d, "obb") if d else (None, None)
    if n >= 6 and n % 2 == 0:
        pairs = n // 2
        if pairs >= 3:
            # 多于 4 个顶点：按实例分割多边形保留（避免 minAreaRect 破坏轮廓）
            if pairs > 4:
                d = segment_from_pairs()
                return (d, "segment") if d else (None, None)
            d = obb_from_pairs(pairs)
            return (d, "obb") if d else (None, None)
    return None, None


def parse_yolo_label_text(
    label_content: str,
    mode: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    解析整个标签文件。
    返回 annotations 列表与 stats: inferred, detect_lines, obb_lines, segment_lines, skipped_lines
    """
    mode_norm = mode if mode in ("detect", "obb", "segment", "auto") else "auto"
    anns: List[Dict[str, Any]] = []
    tags: List[str] = []
    skipped = 0
    for line in label_content.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        ann, tag = parse_yolo_label_line(parts, mode_norm)  # type: ignore[arg-type]
        if ann is None:
            skipped += 1
            continue
        anns.append(ann)
        if tag:
            tags.append(tag)

    inferred = "detect"
    if mode_norm == "obb":
        inferred = "obb"
    elif mode_norm == "segment":
        inferred = "segment"
    elif mode_norm == "auto":
        if tags and all(t == "obb" for t in tags):
            inferred = "obb"
        elif tags and all(t == "segment" for t in tags):
            inferred = "segment"
        elif tags and all(t == "detect" for t in tags):
            inferred = "detect"
        elif tags:
            inferred = "mixed"

    stats = {
        "inferred": inferred,
        "detect_lines": sum(1 for t in tags if t == "detect"),
        "obb_lines": sum(1 for t in tags if t == "obb"),
        "segment_lines": sum(1 for t in tags if t == "segment"),
        "skipped_lines": skipped,
        "total_objects": len(anns),
    }
    return anns, stats


def merge_label_task_from_upload(
    format_mode: FormatMode,
    all_file_stats: List[Dict[str, Any]],
    dataset_current: Optional[str],
) -> str:
    """根据本次批量上传的解析结果更新数据集的 label_task。"""
    if format_mode == "detect":
        return "detect"
    if format_mode == "obb":
        return "obb"
    if format_mode == "segment":
        return "segment"
    any_obb = any(s.get("obb_lines", 0) > 0 for s in all_file_stats)
    any_seg = any(s.get("segment_lines", 0) > 0 for s in all_file_stats)
    any_det = any(s.get("detect_lines", 0) > 0 for s in all_file_stats)
    if any_seg and not any_obb and not any_det:
        return "segment"
    if any_obb and not any_seg and not any_det:
        return "obb"
    if any_det and not any_obb and not any_seg:
        return "detect"
    if any_seg:
        return "segment"
    if any_obb:
        return "obb"
    return dataset_current or "detect"
