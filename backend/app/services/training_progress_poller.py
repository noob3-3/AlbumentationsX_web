"""
DDP 训练进度轮询：Ultralytics 双卡 DDP 模式下自定义 callback 不执行，
通过轮询 results.csv 更新 DB 和 WebSocket，让前端能正确显示训练进度。
"""
import csv
import asyncio
from pathlib import Path
from datetime import datetime
from loguru import logger
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.websocket import ws_manager
from app.models import TrainingJob, JobStatus

from app.utils.metrics_pg_json import sanitize_metrics_for_pg_json, sanitize_metrics_history


# results.csv 列名映射（不同 Ultralytics 版本可能略有差异）
# 检测模型用 metrics/mAP50(B)、metrics/mAP50-95(B)
CSV_COLUMN_MAP = {
    "epoch": "epoch",
    "train/box_loss": "train/box_loss",
    "train/cls_loss": "train/cls_loss",
    "train/dfl_loss": "train/dfl_loss",
    "metrics/mAP50(B)": "val/map50",
    "metrics/mAP50-95(B)": "val/map50_95",
    "metrics/mAP50": "val/map50",      # 兼容无 (B) 后缀
    "metrics/mAP50-95": "val/map50_95",
}


def _parse_results_csv(csv_path: Path) -> list[dict]:
    """解析 Ultralytics results.csv，返回 metrics_history 列表"""
    if not csv_path.exists():
        return []
    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except Exception as e:
        logger.debug(f"Failed to parse {csv_path}: {e}")
        return []

    result = []
    for row in rows:
        metrics = {}
        for csv_col, our_key in CSV_COLUMN_MAP.items():
            if csv_col in row and row[csv_col].strip():
                try:
                    val = float(row[csv_col])
                    metrics[our_key] = val
                except (ValueError, TypeError):
                    pass
        if "epoch" in metrics:
            metrics["epoch"] = int(metrics["epoch"])
            result.append(metrics)
    return result


async def _poll_once():
    """轮询一次：检查所有 running 任务的 results.csv 并更新"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TrainingJob)
            .where(TrainingJob.status == JobStatus.RUNNING)
            .order_by(TrainingJob.started_at.desc())
        )
        jobs = result.scalars().all()

    for job in jobs:
        # Ultralytics project=output_dir, name="train" -> output_dir/train/results.csv
        results_path = settings.MODEL_DIR / job.id / "train" / "results.csv"
        metrics_list = _parse_results_csv(results_path)
        if not metrics_list:
            continue

        # 若 DB 中已有相同或更多 epoch，跳过（避免覆盖 callback 更新的更全数据）
        current_count = len(job.metrics_history or [])
        new_count = len(metrics_list)
        if new_count <= current_count:
            continue

        # 构建 metrics_history 格式（与 callback 一致）
        metrics_history = []
        for m in metrics_list:
            entry = {
                "epoch": m.get("epoch"),
                "timestamp": datetime.utcnow().isoformat(),
            }
            if "train/box_loss" in m:
                entry["train/box_loss"] = m["train/box_loss"]
            if "train/cls_loss" in m:
                entry["train/cls_loss"] = m["train/cls_loss"]
            if "train/dfl_loss" in m:
                entry["train/dfl_loss"] = m["train/dfl_loss"]
            if "val/map50" in m:
                entry["val/map50"] = m["val/map50"]
            if "val/map50_95" in m:
                entry["val/map50_95"] = m["val/map50_95"]
            metrics_history.append(entry)

        latest = metrics_history[-1]
        epoch = latest.get("epoch", new_count)
        elapsed = 0.0
        avg_epoch_time = 0.0
        estimated_remaining = 0.0
        estimated_completion = None
        started_at = job.started_at
        if started_at and len(metrics_history) >= 1:
            _started = started_at.replace(tzinfo=None) if getattr(started_at, "tzinfo", None) else started_at
            elapsed = (datetime.utcnow() - _started).total_seconds()
            avg_epoch_time = elapsed / len(metrics_history)
            remaining = job.epochs - epoch
            estimated_remaining = avg_epoch_time * max(0, remaining)
            if estimated_remaining > 0:
                from datetime import timedelta
                estimated_completion = datetime.utcnow() + timedelta(seconds=estimated_remaining)

        async with AsyncSessionLocal() as db2:
            r = await db2.execute(
                select(TrainingJob).where(TrainingJob.id == job.id)
            )
            j = r.scalar_one_or_none()
            if j and j.status == JobStatus.RUNNING:
                j.current_epoch = epoch
                j.metrics_history = sanitize_metrics_history(metrics_history)
                j.avg_epoch_time = avg_epoch_time
                j.estimated_remaining_time = estimated_remaining
                j.estimated_completion_time = estimated_completion
                await db2.commit()

        ws_manager.publish_sync(job.id, {
            "type": "training_progress",
            "job_id": job.id,
            "epoch": epoch,
            "total_epochs": job.epochs,
            "metrics": sanitize_metrics_for_pg_json(latest),
            "metrics_history": sanitize_metrics_history(metrics_history),
            "percent": round(epoch / job.epochs * 100, 1),
            "elapsed_time": elapsed,
            "avg_epoch_time": avg_epoch_time,
            "estimated_remaining_time": estimated_remaining,
            "estimated_completion_time": (
                estimated_completion.isoformat() if estimated_completion else None
            ),
        })
        logger.debug(f"DDP poller: updated job {job.id} epoch {epoch}/{job.epochs}")


async def run_progress_poller(interval_sec: float = 8.0):
    """后台轮询任务，用于 DDP 模式下同步 results.csv 进度"""
    logger.info("DDP progress poller started (interval=%.1fs)", interval_sec)
    while True:
        try:
            await asyncio.sleep(interval_sec)
            await _poll_once()
        except asyncio.CancelledError:
            logger.info("DDP progress poller stopped")
            break
        except Exception as e:
            logger.warning(f"DDP progress poller error: {e}")
