"""
Annotation API endpoints
"""
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.core.database import get_db, AsyncSessionLocal
from app.schemas.schemas import (
    AnnotationCreate, AnnotationUpdate, AutoAnnotationRequest,
    ImageResponse, SuccessResponse, BatchReplaceClassesRequest
)
from app.services import AnnotationService
from app.services.pretrained_model_service import PretrainedModelService

router = APIRouter(prefix="/annotation", tags=["annotation"])


@router.put("/images/{image_id}", response_model=ImageResponse, summary="Update image annotations")
async def update_image_annotations(
    image_id: str,
    data: AnnotationUpdate,
    db: AsyncSession = Depends(get_db),
):
    """手动标注或修改图片的标注"""
    try:
        image = await AnnotationService.update_image_annotations(
            db=db,
            image_id=image_id,
            annotations=data.annotations,
        )
        await db.commit()
        return image
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update annotations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auto-annotate", summary="Auto-annotate images using a model")
async def auto_annotate_images(
    data: AutoAnnotationRequest,
    db: AsyncSession = Depends(get_db),
):
    """使用已训练的模型或预训练模型自动标注图片"""
    import asyncio

    # 生成唯一的job_id用于WebSocket通信
    job_id = str(uuid.uuid4())

    logger.info(f"📝 Created auto-annotation job: {job_id}")
    logger.info(f"   Dataset: {data.dataset_id}")
    logger.info(f"   Confidence: {data.confidence_threshold}")

    # 使用 asyncio.create_task 在当前事件循环中启动任务
    # 这样可以确保 WebSocket 消息能正确发送
    asyncio.create_task(
        run_auto_annotation(
            job_id=job_id,
            dataset_id=data.dataset_id,
            model_id=data.model_id,
            confidence_threshold=data.confidence_threshold,
            image_ids=data.image_ids,
            use_pretrained=data.use_pretrained if hasattr(data, 'use_pretrained') else False,
            pretrained_model_name=data.pretrained_model_name if hasattr(data, 'pretrained_model_name') else None,
            annotate_all=data.annotate_all if hasattr(data, 'annotate_all') else False,
            include_augmented=data.include_augmented if hasattr(data, 'include_augmented') else False,
        )
    )

    # 立即返回job_id，客户端用它连接WebSocket
    logger.info(f"✅ Job {job_id} queued, returning to client")
    return {
        "success": True,
        "job_id": job_id,
        "message": "自动标注任务已启动，请通过WebSocket监听进度"
    }


async def run_auto_annotation(
    job_id: str,
    dataset_id: str,
    model_id: str,
    confidence_threshold: float,
    image_ids: Optional[List[str]],
    use_pretrained: bool,
    pretrained_model_name: Optional[str],
    annotate_all: bool,
    include_augmented: bool,
):
    """后台执行自动标注任务"""
    from app.core.websocket import ws_manager
    import asyncio

    logger.info(f"🚀 Starting auto-annotation background task for job {job_id}")
    logger.info(f"   Dataset: {dataset_id}")
    logger.info(f"   Use pretrained: {use_pretrained}")
    logger.info(f"   Model: {pretrained_model_name if use_pretrained else model_id}")

    # 等待一小段时间，让客户端有时间连接WebSocket
    # 增加等待时间以确保前端有足够时间建立连接（前端延迟500ms）
    await asyncio.sleep(1.5)

    # 检查WebSocket连接状态
    connection_count = ws_manager.get_connection_count(job_id)
    logger.info(f"🔌 WebSocket connections for job {job_id}: {connection_count}")

    # 发送任务开始消息
    sent = await ws_manager.send_message(job_id, {
        "type": "task_started",
        "message": "后台任务已启动",
        "job_id": job_id,
        "status": "running"
    })

    if not sent:
        logger.warning(f"⚠️ Failed to send task_started message - no WebSocket connections for job {job_id}")

    async with AsyncSessionLocal() as db:
        try:
            result = await AnnotationService.auto_annotate_images(
                db=db,
                dataset_id=dataset_id,
                model_id=model_id,
                confidence_threshold=confidence_threshold,
                image_ids=image_ids,
                use_pretrained=use_pretrained,
                pretrained_model_name=pretrained_model_name,
                job_id=job_id,
                annotate_all=annotate_all,
                include_augmented=include_augmented,
            )
            logger.info(f"✅ Auto-annotation job {job_id} completed: {result}")
        except ValueError as e:
            logger.error(f"❌ Auto-annotation job {job_id} failed (ValueError): {e}")
            await ws_manager.send_message(job_id, {
                "type": "annotation_error",
                "message": str(e),
                "status": "error"
            })
        except Exception as e:
            logger.error(f"❌ Auto-annotation job {job_id} failed (Exception): {e}")
            await ws_manager.send_message(job_id, {
                "type": "annotation_error",
                "message": f"自动标注失败: {str(e)}",
                "status": "error"
            })


@router.get("/pretrained-models", summary="List available pretrained models")
async def list_pretrained_models():
    """列出所有可用的Ultralytics预训练模型"""
    try:
        models = PretrainedModelService.list_available_models()
        return {"models": models}
    except Exception as e:
        logger.error(f"Failed to list pretrained models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/active-job/{dataset_id}", summary="Get active annotation job for dataset")
async def get_active_annotation_job(dataset_id: str):
    """获取数据集的活动标注任务"""
    from app.services.annotation_job_manager import annotation_job_manager

    try:
        job = annotation_job_manager.get_job_by_dataset(dataset_id)
        if job:
            job_dict = annotation_job_manager.get_job_dict(job.job_id)
            logger.debug(f"📊 Active job query for dataset {dataset_id}: job={job.job_id}, status={job.status}, progress={job.current}/{job.total}")
            return {
                "has_active_job": True,
                "job": job_dict
            }
        else:
            logger.debug(f"📊 Active job query for dataset {dataset_id}: no active job found")
            return {
                "has_active_job": False,
                "job": None
            }
    except Exception as e:
        logger.error(f"Failed to get active job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-replace-classes", summary="Batch replace class names in dataset")
async def batch_replace_classes(
    data: BatchReplaceClassesRequest,
    db: AsyncSession = Depends(get_db),
):
    """批量替换数据集中的类别名称"""
    try:
        result = await AnnotationService.batch_replace_classes(
            db=db,
            dataset_id=data.dataset_id,
            class_mapping=data.class_mapping,
        )
        return result
    except Exception as e:
        logger.error(f"Batch replace classes failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/images/{image_id}", response_model=ImageResponse, summary="Get image with annotations")
async def get_image_annotations(
    image_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取图片及其标注信息"""
    image = await AnnotationService.get_image_with_annotations(db, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    return image


@router.delete("/images/{image_id}", response_model=SuccessResponse, summary="Delete image annotations")
async def delete_image_annotations(
    image_id: str,
    db: AsyncSession = Depends(get_db),
):
    """删除图片的所有标注"""
    try:
        await AnnotationService.delete_annotations(db, image_id)
        return {"success": True, "message": "Annotations deleted"}
    except Exception as e:
        logger.error(f"Failed to delete annotations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

