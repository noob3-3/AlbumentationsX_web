"""
System Information API
Provides hardware and system resource information
"""
import csv
import io
import subprocess
from fastapi import APIRouter
from loguru import logger
import shutil
import platform
from typing import Dict, Any, List, Optional

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/info", summary="Get system information")
async def get_system_info() -> Dict[str, Any]:
    """获取系统信息，包括GPU、磁盘等硬件信息"""

    info = {
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
        },
        "gpu": await _get_gpu_info(),
        "disk": _get_disk_info(),
        "memory": _get_memory_info(),
    }

    return info


def _get_gpu_info_from_nvidia_smi() -> Optional[Dict[str, Any]]:
    """通过 nvidia-smi 获取系统级 GPU 使用情况（含 DDP 子进程等所有进程）"""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.used,memory.total,memory.free,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None

        # index,name,memory.used,memory.total,memory.free,utilization.gpu
        devices = []
        reader = csv.reader(io.StringIO(result.stdout.strip()))
        for row in reader:
            if len(row) < 6:
                continue
            try:
                gpu_id = int(row[0].strip())
                name = row[1].strip()
                mem_used_mb = float("".join(c for c in row[2] if c.isdigit() or c == ".") or "0")
                mem_total_mb = float("".join(c for c in row[3] if c.isdigit() or c == ".") or "1")
                mem_free_mb = float("".join(c for c in row[4] if c.isdigit() or c == ".") or "0")
                util_pct = float("".join(c for c in row[5] if c.isdigit() or c == ".") or "0")
            except (ValueError, IndexError):
                continue
            mem_total_gb = mem_total_mb / 1024
            mem_used_gb = mem_used_mb / 1024
            mem_free_gb = mem_free_mb / 1024
            usage_pct = round((mem_used_gb / mem_total_gb) * 100, 1) if mem_total_gb > 0 else 0

            devices.append({
                "id": gpu_id,
                "name": name,
                "total_memory_gb": round(mem_total_gb, 2),
                "allocated_memory_gb": round(mem_used_gb, 2),
                "reserved_memory_gb": round(mem_used_gb, 2),
                "free_memory_gb": round(mem_free_gb, 2),
                "memory_usage_percent": usage_pct,
                "utilization_percent": round(util_pct, 1),
            })
        return {"devices": devices, "count": len(devices)} if devices else None
    except Exception as e:
        logger.debug(f"nvidia-smi failed: {e}")
        return None


async def _get_gpu_info() -> Dict[str, Any]:
    """获取GPU信息。优先用 nvidia-smi 显示系统级真实使用（含 DDP 训练子进程）"""
    gpu_info = {
        "available": False,
        "count": 0,
        "devices": [],
    }

    # 优先 nvidia-smi：可看到 DDP 子进程等所有进程的实际 GPU 使用
    nvidia_result = _get_gpu_info_from_nvidia_smi()
    if nvidia_result and nvidia_result["devices"]:
        gpu_info["available"] = True
        gpu_info["count"] = nvidia_result["count"]
        gpu_info["devices"] = nvidia_result["devices"]
        try:
            import torch
            gpu_info["cuda_version"] = torch.version.cuda
            gpu_info["cudnn_version"] = torch.backends.cudnn.version()
        except Exception:
            gpu_info["cuda_version"] = "unknown"
            gpu_info["cudnn_version"] = "unknown"
        logger.debug(f"GPU info from nvidia-smi: {gpu_info['count']} GPU(s)")
        return gpu_info

    # 回退到 PyTorch（仅当前进程的显存，DDP 时多为 0）
    try:
        import torch

        if torch.cuda.is_available():
            gpu_info["available"] = True
            gpu_info["count"] = torch.cuda.device_count()
            gpu_info["cuda_version"] = torch.version.cuda
            gpu_info["cudnn_version"] = torch.backends.cudnn.version()

            devices = []
            for i in range(torch.cuda.device_count()):
                try:
                    props = torch.cuda.get_device_properties(i)
                    memory_allocated = torch.cuda.memory_allocated(i) / (1024**3)
                    memory_reserved = torch.cuda.memory_reserved(i) / (1024**3)
                    memory_total = props.total_memory / (1024**3)

                    device_info = {
                        "id": i,
                        "name": props.name,
                        "compute_capability": f"{props.major}.{props.minor}",
                        "total_memory_gb": round(memory_total, 2),
                        "allocated_memory_gb": round(memory_allocated, 2),
                        "reserved_memory_gb": round(memory_reserved, 2),
                        "free_memory_gb": round(memory_total - memory_reserved, 2),
                        "memory_usage_percent": round((memory_reserved / memory_total) * 100, 1),
                        "multi_processor_count": props.multi_processor_count,
                    }
                    devices.append(device_info)
                except Exception as e:
                    logger.warning(f"Failed to get GPU {i} info: {e}")

            gpu_info["devices"] = devices
            logger.debug(f"GPU info from PyTorch: {gpu_info['count']} GPU(s)")
        else:
            logger.debug("CUDA is not available")

    except ImportError:
        logger.debug("PyTorch not installed, GPU info not available")
    except Exception as e:
        logger.error(f"Error getting GPU info: {e}")

    return gpu_info


def _get_disk_info() -> Dict[str, Any]:
    """获取磁盘空间信息"""
    disk_info = {
        "available": False,
        "partitions": [],
    }

    try:
        import psutil

        disk_info["available"] = True
        partitions = []

        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                partition_info = {
                    "device": partition.device,
                    "mountpoint": partition.mountpoint,
                    "fstype": partition.fstype,
                    "total_gb": round(usage.total / (1024**3), 2),
                    "used_gb": round(usage.used / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                    "usage_percent": usage.percent,
                }
                partitions.append(partition_info)
            except PermissionError:
                # Skip partitions we can't access
                continue
            except Exception as e:
                logger.warning(f"Failed to get info for partition {partition.device}: {e}")

        disk_info["partitions"] = partitions

    except ImportError:
        logger.debug("psutil not installed, using basic disk info")
        # Fallback to basic disk info using shutil
        try:
            usage = shutil.disk_usage("/")
            disk_info["available"] = True
            disk_info["partitions"] = [{
                "device": "root",
                "mountpoint": "/",
                "fstype": "unknown",
                "total_gb": round(usage.total / (1024**3), 2),
                "used_gb": round(usage.used / (1024**3), 2),
                "free_gb": round(usage.free / (1024**3), 2),
                "usage_percent": round((usage.used / usage.total) * 100, 1),
            }]
        except Exception as e:
            logger.error(f"Error getting disk info: {e}")
    except Exception as e:
        logger.error(f"Error getting disk info: {e}")

    return disk_info


def _get_memory_info() -> Dict[str, Any]:
    """获取内存信息"""
    memory_info = {
        "available": False,
    }

    try:
        import psutil

        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        memory_info = {
            "available": True,
            "total_gb": round(mem.total / (1024**3), 2),
            "used_gb": round(mem.used / (1024**3), 2),
            "free_gb": round(mem.available / (1024**3), 2),
            "usage_percent": mem.percent,
            "swap_total_gb": round(swap.total / (1024**3), 2),
            "swap_used_gb": round(swap.used / (1024**3), 2),
            "swap_free_gb": round(swap.free / (1024**3), 2),
            "swap_usage_percent": swap.percent,
        }

    except ImportError:
        logger.debug("psutil not installed, memory info not available")
    except Exception as e:
        logger.error(f"Error getting memory info: {e}")

    return memory_info

