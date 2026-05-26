"""
将 Ultralytics predict 的单个 Results 解析为平台统一的 detections 列表。

检测任务使用 result.boxes；OBB 任务使用 result.obb（boxes 常为 None，不可对 None 迭代）；
语义分割使用 result.semantic_mask（单通道类别图）。
"""
from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional

import cv2
import numpy as np


def detections_from_ultralytics_result(
    yolo_model: Any,
    result: Any,
    width: int,
    height: int,
) -> List[Dict[str, Any]]:
    """
    从单张图的 ``results[0]`` 解析检测框列表。
    ``width/height`` 用于归一化 bbox_normalized。
    """
    detections: List[Dict[str, Any]] = []

    boxes = getattr(result, "boxes", None)
    if boxes is not None and len(boxes) > 0:
        for box in boxes:
            xyxy = box.xyxy[0].cpu().numpy()
            x1, y1, x2, y2 = map(float, xyxy)
            cx = (x1 + x2) / 2 / width
            cy = (y1 + y2) / 2 / height
            w = (x2 - x1) / width
            h = (y2 - y1) / height
            class_id = int(box.cls[0].cpu().numpy())
            confidence = float(box.conf[0].cpu().numpy())
            class_name = yolo_model.names.get(class_id, f"class_{class_id}")
            detections.append(
                {
                    "class_id": class_id,
                    "class_name": class_name,
                    "confidence": confidence,
                    "bbox": [x1, y1, x2, y2],
                    "bbox_normalized": [float(cx), float(cy), float(w), float(h)],
                    "task": "detect",
                }
            )
        return detections

    obb = getattr(result, "obb", None)
    if obb is None or len(obb) == 0:
        return detections

    xyxyxyxy = getattr(obb, "xyxyxyxy", None)
    confs = getattr(obb, "conf", None)
    clss = getattr(obb, "cls", None)
    if xyxyxyxy is None or confs is None or clss is None:
        return detections

    n = len(obb)
    for i in range(n):
        coords_t = xyxyxyxy[i]
        coords = coords_t.cpu().numpy().reshape(-1)
        if coords.size < 8:
            continue
        pts = coords[:8].reshape(4, 2)
        x1, y1 = float(pts[:, 0].min()), float(pts[:, 1].min())
        x2, y2 = float(pts[:, 0].max()), float(pts[:, 1].max())
        cx = ((x1 + x2) / 2) / width
        cy = ((y1 + y2) / 2) / height
        bw = (x2 - x1) / width
        bh = (y2 - y1) / height
        class_id = int(clss[i].cpu().numpy())
        confidence = float(confs[i].cpu().numpy())
        class_name = yolo_model.names.get(class_id, f"class_{class_id}")
        detections.append(
            {
                "class_id": class_id,
                "class_name": class_name,
                "confidence": confidence,
                "bbox": [x1, y1, x2, y2],
                "bbox_normalized": [float(cx), float(cy), float(bw), float(bh)],
                "task": "obb",
                "obb_xyxyxyxy": [float(x) for x in coords[:8].tolist()],
            }
        )

    return detections


def _class_name_from_model(yolo_model: Any, class_id: int) -> str:
    names = getattr(yolo_model, "names", None) or {}
    if isinstance(names, dict):
        return names.get(class_id, f"class_{class_id}")
    if isinstance(names, (list, tuple)) and 0 <= class_id < len(names):
        return str(names[class_id])
    return f"class_{class_id}"


def semantic_payload_from_ultralytics_result(
    yolo_model: Any,
    result: Any,
) -> Optional[Dict[str, Any]]:
    """语义分割：导出 PNG 掩膜（base64）与各类像素统计，供模型验证前端叠色。"""
    sem = getattr(result, "semantic_mask", None)
    if sem is None:
        return None
    data = getattr(sem, "data", None)
    if data is None:
        return None

    if hasattr(data, "cpu"):
        arr = data.cpu().numpy()
    else:
        arr = np.asarray(data)

    if arr.ndim == 3:
        if arr.shape[0] == 1:
            arr = arr[0]
        else:
            arr = np.argmax(arr, axis=0)

    arr = np.clip(arr, 0, 255).astype(np.uint8)
    h, w = int(arr.shape[0]), int(arr.shape[1])

    # 掩膜分辨率可能与原图不一致（letterbox / 推理尺寸），对齐到 orig_shape
    orig_shape = getattr(result, "orig_shape", None)
    if orig_shape and len(orig_shape) >= 2:
        target_h, target_w = int(orig_shape[0]), int(orig_shape[1])
        if (h, w) != (target_h, target_w):
            arr = cv2.resize(arr, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
            h, w = target_h, target_w

    total = h * w or 1

    class_stats: List[Dict[str, Any]] = []
    for cid in np.unique(arr):
        cid_int = int(cid)
        cnt = int(np.sum(arr == cid_int))
        if cid_int == 255:
            cname = "ignore"
        elif cid_int == 0:
            cname = _class_name_from_model(yolo_model, 0)
        else:
            cname = _class_name_from_model(yolo_model, cid_int)
        class_stats.append(
            {
                "class_id": cid_int,
                "class_name": cname,
                "pixel_count": cnt,
                "coverage": round(cnt / total, 4),
            }
        )

    ok, buf = cv2.imencode(".png", arr)
    if not ok:
        return None

    foreground = [
        s
        for s in class_stats
        if s["class_id"] not in (0, 255) and s["pixel_count"] > 0
    ]

    return {
        "mask_png_base64": base64.b64encode(buf.tobytes()).decode("ascii"),
        "width": w,
        "height": h,
        "class_stats": class_stats,
        "foreground_class_count": len(foreground),
    }


def inference_output_from_ultralytics_result(
    yolo_model: Any,
    result: Any,
    width: int,
    height: int,
) -> Dict[str, Any]:
    """
    统一推理输出：检测/OBB 走 detections；语义分割走 semantic 字段。
    """
    semantic = semantic_payload_from_ultralytics_result(yolo_model, result)
    if semantic is not None:
        return {
            "task": "semantic",
            "detections": [],
            "detection_count": semantic.get("foreground_class_count", 0),
            "semantic": semantic,
        }

    detections = detections_from_ultralytics_result(yolo_model, result, width, height)
    task = "detect"
    if detections:
        task = detections[0].get("task") or "detect"
    return {
        "task": task,
        "detections": detections,
        "detection_count": len(detections),
        "semantic": None,
    }
