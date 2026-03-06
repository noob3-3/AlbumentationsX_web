"""
Training Queue Manager
Manages training job queue to prevent concurrent training and GPU memory conflicts
支持多GPU并行训练，每个GPU运行一个训练任务
"""
import asyncio
from typing import Optional, Dict, Set, List
from datetime import datetime
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import TrainingJob, JobStatus
from app.core.database import AsyncSessionLocal


class TrainingQueueManager:
    """
    单例模式的训练队列管理器
    支持多GPU并行训练：每个GPU可以运行一个训练任务
    """
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True

        # 检测可用GPU数量
        self._gpu_count = self._detect_gpu_count()

        # 使用信号量控制并发训练数量（每个GPU一个训练）
        self._training_semaphore = asyncio.Semaphore(max(1, self._gpu_count))

        # 跟踪当前正在使用的GPU和对应的任务ID
        self._gpu_allocations: Dict[int, str] = {}  # {gpu_id: job_id}
        self._allocation_lock = asyncio.Lock()

        # 训练队列
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_tasks: List[asyncio.Task] = []
        self._running = False

        logger.info(f"Training Queue Manager initialized: {self._gpu_count} GPU(s) detected, max {self._gpu_count} concurrent training(s)")

    def _detect_gpu_count(self) -> int:
        """检测可用GPU数量"""
        try:
            import torch
            if torch.cuda.is_available():
                count = torch.cuda.device_count()
                logger.info(f"Detected {count} GPU(s)")
                return count
        except ImportError:
            logger.warning("PyTorch not available, running in CPU mode")
        except Exception as e:
            logger.warning(f"Failed to detect GPU: {e}")
        return 1  # 默认返回1，允许一个训练任务

    async def start(self):
        """启动队列工作线程，每个GPU一个worker"""
        if self._running:
            return

        self._running = True

        # 启动多个worker，数量等于GPU数量
        worker_count = max(1, self._gpu_count)
        for i in range(worker_count):
            worker_task = asyncio.create_task(self._worker(i))
            self._worker_tasks.append(worker_task)

        logger.info(f"Training queue started: {worker_count} worker(s)")

    async def stop(self):
        """停止所有队列工作线程"""
        self._running = False

        # 取消所有worker任务
        for task in self._worker_tasks:
            task.cancel()

        # 等待所有任务完成
        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)

        self._worker_tasks.clear()
        logger.info("Training queue stopped")

    async def enqueue(self, job_id: str):
        """将训练任务加入队列"""
        await self._queue.put(job_id)
        queue_size = self._queue.qsize()
        logger.info(f"Training job {job_id} added to queue. Queue size: {queue_size}")

        # 更新任务状态为排队中
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(TrainingJob).where(TrainingJob.id == job_id)
            )
            job = result.scalar_one_or_none()
            if job and job.status == JobStatus.PENDING:
                job.status = JobStatus.PENDING
                await db.commit()
                logger.info(f"Job {job_id} status updated to PENDING")

    async def _allocate_gpu(self, job_id: str) -> Optional[int]:
        """为训练任务分配一个空闲GPU"""
        async with self._allocation_lock:
            # 查找空闲的GPU
            used_gpus = set(self._gpu_allocations.keys())
            available_gpus = set(range(self._gpu_count)) - used_gpus

            if available_gpus:
                gpu_id = min(available_gpus)  # 选择编号最小的空闲GPU
                self._gpu_allocations[gpu_id] = job_id
                logger.info(f"Allocated GPU {gpu_id} to job {job_id}")
                return gpu_id

            logger.warning(f"No available GPU for job {job_id}, all {self._gpu_count} GPUs are in use")
            return None

    async def _release_gpu(self, gpu_id: int):
        """释放GPU"""
        async with self._allocation_lock:
            if gpu_id in self._gpu_allocations:
                job_id = self._gpu_allocations[gpu_id]
                del self._gpu_allocations[gpu_id]
                logger.info(f"Released GPU {gpu_id} from job {job_id}")

    def is_training(self) -> bool:
        """检查是否有训练任务正在执行"""
        return len(self._gpu_allocations) > 0

    def get_current_jobs(self) -> Dict[int, str]:
        """获取当前所有正在执行的任务"""
        return self._gpu_allocations.copy()

    def get_queue_size(self) -> int:
        """获取队列中等待的任务数量"""
        return self._queue.qsize()

    def get_active_training_count(self) -> int:
        """获取当前正在训练的任务数量"""
        return len(self._gpu_allocations)

    async def _worker(self, worker_id: int):
        """队列工作线程，循环处理训练任务"""
        logger.info(f"Training queue worker #{worker_id} started")

        while self._running:
            job_id = None
            gpu_id = None

            try:
                # 等待队列中的任务（带超时，以便可以响应停止信号）
                try:
                    job_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                # 获取信号量（控制并发数量）
                async with self._training_semaphore:
                    # 分配GPU
                    gpu_id = await self._allocate_gpu(job_id)

                    if gpu_id is None:
                        # 理论上不应该发生，因为信号量已经控制了并发数
                        logger.error(f"Failed to allocate GPU for job {job_id}")
                        self._queue.task_done()
                        continue

                    logger.info(f"Worker #{worker_id}: Starting training job {job_id} on GPU {gpu_id}")

                    try:
                        # 更新任务，指定使用的GPU
                        async with AsyncSessionLocal() as db:
                            result = await db.execute(
                                select(TrainingJob).where(TrainingJob.id == job_id)
                            )
                            job = result.scalar_one_or_none()
                            if job:
                                # 如果任务设置为auto，则自动分配GPU
                                if job.device == "auto":
                                    job.device = str(gpu_id)
                                    await db.commit()
                                    logger.info(f"Job {job_id} device set to GPU {gpu_id}")

                        # 执行训练，传递GPU ID以便设置环境变量
                        from app.services.training_service import TrainingService
                        await TrainingService.run_training_job(job_id, allocated_gpu_id=gpu_id)
                        logger.info(f"Worker #{worker_id}: Training job {job_id} completed on GPU {gpu_id}")

                    except Exception as e:
                        logger.error(f"Worker #{worker_id}: Training job {job_id} failed on GPU {gpu_id}: {e}")

                    finally:
                        # 释放GPU
                        if gpu_id is not None:
                            await self._release_gpu(gpu_id)

                        self._queue.task_done()

                        # 清理该GPU的显存
                        await self._cleanup_gpu_memory(gpu_id)

                        # 等待一小段时间，确保资源完全释放
                        await asyncio.sleep(2)

            except asyncio.CancelledError:
                logger.info(f"Training queue worker #{worker_id} cancelled")
                break
            except Exception as e:
                logger.error(f"Error in training queue worker #{worker_id}: {e}")
                if job_id:
                    self._queue.task_done()
                await asyncio.sleep(1)

    async def _cleanup_gpu_memory(self, gpu_id: Optional[int] = None):
        """清理GPU显存

        Args:
            gpu_id: 要清理的GPU ID，None表示清理所有GPU
        """
        try:
            import torch
            if torch.cuda.is_available():
                if gpu_id is not None:
                    # 清理指定GPU
                    with torch.cuda.device(gpu_id):
                        torch.cuda.empty_cache()
                        torch.cuda.synchronize()
                    logger.info(f"GPU {gpu_id} memory cleaned up")
                else:
                    # 清理所有GPU
                    torch.cuda.empty_cache()
                    for i in range(torch.cuda.device_count()):
                        torch.cuda.synchronize(i)
                    logger.info("All GPU memory cleaned up")
        except Exception as e:
            logger.warning(f"Failed to cleanup GPU memory: {e}")

    async def get_queue_status(self) -> Dict:
        """获取队列状态信息"""
        current_jobs = self.get_current_jobs()
        return {
            "is_training": self.is_training(),
            "active_training_count": self.get_active_training_count(),
            "current_jobs": current_jobs,  # {gpu_id: job_id}
            "queue_size": self.get_queue_size(),
            "gpu_count": self._gpu_count,
            "running": self._running,
        }


# 全局单例
training_queue = TrainingQueueManager()

