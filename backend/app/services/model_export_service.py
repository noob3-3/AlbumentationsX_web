"""YOLO .pt → ONNX 导出（CPU），供 API 在后台线程中调用。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union


def export_pt_to_onnx(
    weights_path: Union[str, Path],
    *,
    opset: int = 18,
    dynamic: bool = False,
    batch: int = 1,
    simplify: bool = False,
    half: bool = False,
    imgsz: Optional[int] = None,
) -> Path:
    """
    加载 Ultralytics YOLO 权重并在 CPU 上导出 ONNX。
    返回生成的 .onnx 文件路径（通常与 .pt 同目录）。
    """
    weights_path = Path(weights_path).resolve()
    if not weights_path.is_file():
        raise FileNotFoundError(f"权重文件不存在: {weights_path}")

    from ultralytics import YOLO

    model = YOLO(str(weights_path))
    model.cpu()

    kwargs = {
        "format": "onnx",
        "opset": opset,
        "dynamic": dynamic,
        "batch": batch,
        "simplify": simplify,
        "half": half,
    }
    if imgsz is not None:
        kwargs["imgsz"] = imgsz

    out = model.export(**kwargs)
    if isinstance(out, (list, tuple)):
        out = out[0]
    p = Path(out)
    if not p.is_file():
        raise RuntimeError(f"ONNX 导出未生成有效文件: {out}")
    return p
