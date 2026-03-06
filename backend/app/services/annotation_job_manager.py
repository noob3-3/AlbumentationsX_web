"""
Auto-annotation job state management
Store active annotation jobs in memory for reconnection after page refresh
"""
from typing import Dict, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
from loguru import logger


@dataclass
class AnnotationJobState:
    """自动标注任务状态"""
    job_id: str
    dataset_id: str
    status: str  # 'running', 'completed', 'failed'
    current: int
    total: int
    success_count: int
    failed_count: int
    start_time: datetime
    last_update: datetime
    model_name: Optional[str] = None
    use_pretrained: bool = False


class AnnotationJobManager:
    """管理活动的自动标注任务"""

    def __init__(self):
        # job_id -> AnnotationJobState
        self.active_jobs: Dict[str, AnnotationJobState] = {}
        # dataset_id -> job_id (便于通过数据集ID查找任务)
        self.dataset_jobs: Dict[str, str] = {}

    def create_job(self, job_id: str, dataset_id: str, total: int,
                   model_name: Optional[str] = None, use_pretrained: bool = False):
        """创建新任务"""
        job_state = AnnotationJobState(
            job_id=job_id,
            dataset_id=dataset_id,
            status='running',
            current=0,
            total=total,
            success_count=0,
            failed_count=0,
            start_time=datetime.utcnow(),
            last_update=datetime.utcnow(),
            model_name=model_name,
            use_pretrained=use_pretrained
        )
        self.active_jobs[job_id] = job_state
        self.dataset_jobs[dataset_id] = job_id
        logger.info(f"📝 Created job state: {job_id} for dataset {dataset_id}")

    def update_progress(self, job_id: str, current: int, success_count: int, failed_count: int):
        """更新任务进度"""
        if job_id in self.active_jobs:
            job = self.active_jobs[job_id]
            job.current = current
            job.success_count = success_count
            job.failed_count = failed_count
            job.last_update = datetime.utcnow()

    def complete_job(self, job_id: str, success: bool = True):
        """标记任务完成"""
        if job_id in self.active_jobs:
            job = self.active_jobs[job_id]
            job.status = 'completed' if success else 'failed'
            job.current = job.total  # 确保进度显示100%
            job.last_update = datetime.utcnow()
            logger.info(f"✅ Job {job_id} completed with status: {job.status}")

            # 5分钟后自动清理
            # TODO: 添加定时清理逻辑

    def get_job(self, job_id: str) -> Optional[AnnotationJobState]:
        """获取任务状态"""
        return self.active_jobs.get(job_id)

    def get_job_by_dataset(self, dataset_id: str) -> Optional[AnnotationJobState]:
        """通过数据集ID获取活动任务（包括最近完成的任务）"""
        job_id = self.dataset_jobs.get(dataset_id)
        if job_id:
            job = self.active_jobs.get(job_id)
            if job:
                # 返回运行中的任务，或者最近5分钟内完成的任务
                if job.status == 'running':
                    return job
                elif job.status in ('completed', 'failed'):
                    time_since_completion = (datetime.utcnow() - job.last_update).total_seconds()
                    if time_since_completion < 300:  # 5分钟内
                        return job
        return None

    def remove_job(self, job_id: str):
        """移除任务"""
        if job_id in self.active_jobs:
            job = self.active_jobs[job_id]
            del self.active_jobs[job_id]
            if job.dataset_id in self.dataset_jobs:
                del self.dataset_jobs[job.dataset_id]
            logger.info(f"🗑️ Removed job: {job_id}")

    def get_job_dict(self, job_id: str) -> Optional[dict]:
        """获取任务状态的字典形式"""
        job = self.get_job(job_id)
        if job:
            data = asdict(job)
            data['start_time'] = job.start_time.isoformat()
            data['last_update'] = job.last_update.isoformat()
            data['percent'] = round((job.current / job.total * 100) if job.total > 0 else 0, 1)
            return data
        return None

    def cleanup_old_jobs(self, max_age_seconds: int = 300):
        """清理超过指定时间的已完成任务"""
        now = datetime.utcnow()
        jobs_to_remove = []

        for job_id, job in self.active_jobs.items():
            if job.status in ('completed', 'failed'):
                age = (now - job.last_update).total_seconds()
                if age > max_age_seconds:
                    jobs_to_remove.append(job_id)

        for job_id in jobs_to_remove:
            self.remove_job(job_id)
            logger.info(f"🧹 Cleaned up old job: {job_id}")

        return len(jobs_to_remove)


# 全局实例
annotation_job_manager = AnnotationJobManager()

