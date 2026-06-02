#!/usr/bin/env python3
"""
本地推理测试：加载多个 .pt 权重，对多张图片推理，输出 JSON + 渲染图。

用法（在 backend 目录或项目根目录执行均可）:

  python scripts/local_inference_test.py ^
    --models path/to/a.pt path/to/b-seg.pt ^
    --images path/to/img1.jpg path/to/img2.png ^
    --output ./inference_out ^
    --conf 0.5 --iou 0.45

输出目录结构:
  inference_out/
    results.json          # 全量推理结果（语义 mask 不写入 base64，见 mask 文件）
    renders/
      {model名}__{图片名}.jpg
    semantic_masks/       # 仅语义分割时有 PNG
      {model名}__{图片名}_mask.png
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

# 将 backend 加入 path，复用平台解析逻辑
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.utils.yolo_result_parse import inference_output_from_ultralytics_result  # noqa: E402

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}

# BGR 调色板（与前端验证页接近）
PALETTE = [
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


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def collect_images(paths: List[str], image_dir: Optional[str]) -> List[Path]:
    found: List[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
            found.append(path.resolve())
    if image_dir:
        d = Path(image_dir)
        if d.is_dir():
            for ext in IMAGE_EXTS:
                found.extend(sorted(d.glob(f"*{ext}")))
                found.extend(sorted(d.glob(f"*{ext.upper()}")))
    # 去重保序
    seen = set()
    unique: List[Path] = []
    for p in found:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def collect_models(paths: List[str], model_dir: Optional[str]) -> List[Path]:
    found: List[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_file() and path.suffix.lower() == ".pt":
            found.append(path.resolve())
    if model_dir:
        d = Path(model_dir)
        if d.is_dir():
            found.extend(sorted(d.glob("*.pt")))
    seen = set()
    unique: List[Path] = []
    for p in found:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def json_safe_parsed(parsed: Dict[str, Any], mask_rel_path: Optional[str] = None) -> Dict[str, Any]:
    """JSON 可序列化；语义 mask 的 base64 过大，改为文件路径。"""
    out = {
        "task": parsed.get("task", "detect"),
        "detection_count": parsed.get("detection_count", 0),
        "detections": parsed.get("detections") or [],
        "semantic": None,
    }
    sem = parsed.get("semantic")
    if sem:
        out["semantic"] = {
            "width": sem.get("width"),
            "height": sem.get("height"),
            "class_stats": sem.get("class_stats"),
            "foreground_class_count": sem.get("foreground_class_count"),
            "mask_png_path": mask_rel_path,
        }
    return out


def draw_label_bar(
    image: np.ndarray,
    label: str,
    lx: int,
    top_y: int,
    color: Tuple[int, int, int],
) -> None:
    h_img, w_img = image.shape[:2]
    pad = 4
    (label_width, label_height), baseline = cv2.getTextSize(
        label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
    )
    box_h = label_height + baseline + pad * 2
    lx = max(0, min(lx, w_img - label_width - pad * 2))
    ty_out = int(top_y) - box_h
    ty = ty_out if ty_out >= 0 else max(0, min(int(top_y), h_img - box_h))
    ty = max(0, min(ty, h_img - box_h))
    cv2.rectangle(
        image,
        (lx, ty),
        (lx + label_width + pad * 2, ty + box_h),
        color,
        -1,
    )
    cv2.putText(
        image,
        label,
        (lx + pad, ty + label_height + pad),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (0, 0, 0),
        1,
    )


def render_detections(
    image_bgr: np.ndarray,
    detections: List[Dict[str, Any]],
    task: str,
) -> np.ndarray:
    """在 BGR 图上绘制检测框 / OBB / 实例分割（掩膜+框）。"""
    from app.utils.inference_render import (
        color_for_index,
        draw_segment_mask_and_box,
        is_segment_detection,
    )

    out = image_bgr.copy()

    for idx, det in enumerate(detections):
        color = color_for_index(idx)
        class_name = det.get("class_name", "?")
        confidence = det.get("confidence", 0.0)
        label = f"{class_name}: {confidence:.2f}"

        if is_segment_detection(det):
            lx, top_y = draw_segment_mask_and_box(out, det, color)
            draw_label_bar(out, label, lx, top_y, color)
            continue

        if det.get("task") == "obb" and det.get("obb_xyxyxyxy"):
            coords = det["obb_xyxyxyxy"]
            pts = np.array(coords, dtype=np.float32).reshape(-1, 2).astype(np.int32)
            cv2.polylines(out, [pts], True, color, 2)
            top_y = float(np.min(pts[:, 1]))
            cx = float(np.mean(pts[:, 0]))
            draw_label_bar(out, label, int(cx - 40), int(top_y), color)
            continue

        bbox = det.get("bbox")
        if bbox and len(bbox) >= 4:
            x1, y1, x2, y2 = map(int, bbox)
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
            draw_label_bar(out, label, x1, y1, color)

    return out


def render_semantic_overlay(
    image_bgr: np.ndarray,
    mask_png_path: Path,
) -> np.ndarray:
    """语义分割：伪彩色叠在原图上。"""
    mask = cv2.imread(str(mask_png_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return image_bgr
    h, w = image_bgr.shape[:2]
    if mask.shape[:2] != (h, w):
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)

    overlay = image_bgr.copy().astype(np.float32)
    for cid in np.unique(mask):
        cid_int = int(cid)
        if cid_int in (0, 255):
            continue
        color = np.array(PALETTE[cid_int % len(PALETTE)], dtype=np.float32)
        region = mask == cid_int
        overlay[region] = overlay[region] * 0.45 + color * 0.55
    return overlay.astype(np.uint8)


def run_inference(
    model_paths: List[Path],
    image_paths: List[Path],
    output_dir: Path,
    conf: float,
    iou: float,
    device: Optional[str],
) -> Dict[str, Any]:
    from ultralytics import YOLO

    output_dir.mkdir(parents=True, exist_ok=True)
    render_dir = output_dir / "renders"
    render_dir.mkdir(exist_ok=True)
    mask_dir = output_dir / "semantic_masks"
    mask_dir.mkdir(exist_ok=True)

    models_cache: Dict[str, Any] = {}
    report: Dict[str, Any] = {
        "conf": conf,
        "iou": iou,
        "models": [str(p) for p in model_paths],
        "images": [],
    }

    for img_path in image_paths:
        img_bgr = cv2.imread(str(img_path))
        if img_bgr is None:
            print(f"[跳过] 无法读取图片: {img_path}")
            continue

        h, w = img_bgr.shape[:2]
        img_entry: Dict[str, Any] = {
            "image_path": str(img_path),
            "image_name": img_path.name,
            "image_size": [w, h],
            "results": [],
        }

        for model_path in model_paths:
            model_key = str(model_path)
            model_stem = model_path.stem
            if model_key not in models_cache:
                print(f"[加载模型] {model_path}")
                kwargs = {}
                if device:
                    kwargs["device"] = device
                models_cache[model_key] = YOLO(str(model_path), **kwargs)

            yolo_model = models_cache[model_key]
            t0 = time.time()
            predictions = yolo_model.predict(
                str(img_path),
                conf=conf,
                iou=iou,
                verbose=False,
            )
            infer_ms = (time.time() - t0) * 1000

            parsed = {
                "task": "detect",
                "detections": [],
                "detection_count": 0,
                "semantic": None,
            }
            if predictions and len(predictions) > 0:
                parsed = inference_output_from_ultralytics_result(
                    yolo_model, predictions[0], w, h
                )

            mask_rel: Optional[str] = None
            render_img = img_bgr

            if parsed.get("task") == "semantic" and parsed.get("semantic"):
                import base64

                sem = parsed["semantic"]
                b64 = sem.get("mask_png_base64")
                if b64:
                    mask_name = f"{model_stem}__{img_path.stem}_mask.png"
                    mask_path = mask_dir / mask_name
                    mask_path.write_bytes(base64.b64decode(b64))
                    mask_rel = str(Path("semantic_masks") / mask_name)
                    render_img = render_semantic_overlay(img_bgr, mask_path)
            else:
                render_img = render_detections(
                    img_bgr,
                    parsed.get("detections") or [],
                    parsed.get("task", "detect"),
                )

            render_name = f"{model_stem}__{img_path.stem}.jpg"
            render_path = render_dir / render_name
            cv2.imwrite(str(render_path), render_img)

            result_entry = {
                "model_path": model_key,
                "model_name": model_stem,
                "inference_time_ms": round(infer_ms, 2),
                "render_path": str(Path("renders") / render_name),
                **json_safe_parsed(parsed, mask_rel),
            }
            img_entry["results"].append(result_entry)
            print(
                f"  [{model_stem}] {img_path.name} "
                f"task={result_entry['task']} count={result_entry['detection_count']} "
                f"{infer_ms:.0f}ms -> {render_name}"
            )

        report["images"].append(img_entry)

    json_path = output_dir / "results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n[完成] JSON: {json_path}")
    print(f"[完成] 渲染图目录: {render_dir}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="本地 YOLO .pt 多模型 × 多图推理，输出 JSON 与渲染图",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=[],
        help="一个或多个 .pt 权重路径",
    )
    parser.add_argument(
        "--model-dir",
        default=None,
        help="扫描目录下所有 .pt（与 --models 合并）",
    )
    parser.add_argument(
        "--images",
        nargs="+",
        default=[],
        help="一张或多张测试图片",
    )
    parser.add_argument(
        "--image-dir",
        default=None,
        help="扫描目录下所有图片（与 --images 合并）",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="./inference_out",
        help="输出目录（默认 ./inference_out）",
    )
    parser.add_argument("--conf", type=float, default=0.5, help="置信度阈值")
    parser.add_argument("--iou", type=float, default=0.45, help="IOU 阈值")
    parser.add_argument(
        "--device",
        default=None,
        help="推理设备，如 cpu / 0 / cuda:0，默认由 Ultralytics 自动选择",
    )
    args = parser.parse_args()

    model_paths = collect_models(args.models, args.model_dir)
    image_paths = collect_images(args.images, args.image_dir)

    if not model_paths:
        parser.error("未找到 .pt 模型，请指定 --models 或 --model-dir")
    if not image_paths:
        parser.error("未找到图片，请指定 --images 或 --image-dir")

    print(f"模型数: {len(model_paths)}, 图片数: {len(image_paths)}")
    run_inference(
        model_paths=model_paths,
        image_paths=image_paths,
        output_dir=Path(args.output).resolve(),
        conf=args.conf,
        iou=args.iou,
        device=args.device,
    )


if __name__ == "__main__":
    main()
