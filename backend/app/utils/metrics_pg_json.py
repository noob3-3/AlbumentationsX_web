"""
训练指标存入 PostgreSQL 的 JSON/JSONB 时需符合标准 JSON；
Python/Ultralytics 中 float('nan') 若被序列化会为裸 NaN（Postgres 报 invalid input syntax）。
"""
from __future__ import annotations

import math
from numbers import Integral
from typing import Any, Dict, List, Union


def sanitize_metrics_for_pg_json(obj: Any) -> Any:
    """递归将 NaN / ±Inf 转为 None，并对 dict/list 深拷贝结构化（适合 metrics_history）。"""
    if obj is None:
        return None
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, Integral) and type(obj) is not bool:  # 排除 numpy.bool_
        try:
            return int(obj)
        except (OverflowError, ValueError, TypeError):
            return obj
    if isinstance(obj, str):
        return obj
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {str(k): sanitize_metrics_for_pg_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_metrics_for_pg_json(v) for v in obj]
    # numpy / torch 标量等
    try:
        xf = float(obj)
        if math.isnan(xf) or math.isinf(xf):
            return None
        # 尽量不破坏整型语义：原值若为整型且不丢精度则返回 int

        if isinstance(obj, Integral) and xf == int(xf):
            return int(xf)
        return float(xf)
    except (TypeError, ValueError, OverflowError):
        return obj


def sanitize_metrics_history(history: Union[List[Any], None]) -> List[Dict[str, Any]]:
    """对整段 metrics_history 做兜底清洗。"""
    if not history:
        return []
    out = sanitize_metrics_for_pg_json(history)
    return list(out) if isinstance(out, list) else []
