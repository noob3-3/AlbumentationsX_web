"""
Model deployment and inference service
"""
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from PIL import Image as PILImage
import numpy as np

from app.models import Model, Deployment, DeploymentStatus
from app.schemas.schemas import DeploymentCreate

# Global model cache
_model_cache: Dict[str, Any] = {}


class DeploymentService:

    @staticmethod
    async def create_deployment(db: AsyncSession, data: DeploymentCreate) -> Deployment:
        """创建部署"""
        # Verify model exists
        model_result = await db.execute(select(Model).where(Model.id == data.model_id))
        model = model_result.scalar_one_or_none()
        if not model:
            raise ValueError(f"Model {data.model_id} not found")

        if not Path(model.model_path).exists():
            raise ValueError(f"Model file not found: {model.model_path}")

        deployment = Deployment(
            name=data.name,
            model_id=data.model_id,
            confidence_threshold=data.confidence_threshold,
            iou_threshold=data.iou_threshold,
            max_detections=data.max_detections,
            device=data.device,
            status=DeploymentStatus.DEPLOYING,
        )
        db.add(deployment)
        await db.flush()
        await db.refresh(deployment)

        # Try to load model
        try:
            from ultralytics import YOLO
            yolo_model = YOLO(model.model_path)
            _model_cache[deployment.id] = yolo_model

            deployment.status = DeploymentStatus.RUNNING
            deployment.endpoint_url = f"/api/v1/deployments/{deployment.id}/predict"

            # Mark model as deployed
            model.is_deployed = True

        except Exception as e:
            logger.error(f"Failed to load model for deployment {deployment.id}: {e}")
            deployment.status = DeploymentStatus.FAILED
            deployment.error_message = str(e)

        await db.flush()
        await db.refresh(deployment)
        return deployment

    @staticmethod
    async def get_deployment(db: AsyncSession, deployment_id: str) -> Optional[Deployment]:
        """获取部署"""
        result = await db.execute(select(Deployment).where(Deployment.id == deployment_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_deployments(db: AsyncSession, skip: int = 0, limit: int = 20) -> List[Deployment]:
        """列出所有部署"""
        result = await db.execute(
            select(Deployment)
            .order_by(Deployment.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def stop_deployment(db: AsyncSession, deployment_id: str) -> bool:
        """停止部署"""
        deployment = await DeploymentService.get_deployment(db, deployment_id)
        if not deployment:
            return False

        deployment.status = DeploymentStatus.STOPPED

        # Remove from cache
        if deployment_id in _model_cache:
            del _model_cache[deployment_id]

        # Update model deployment status if no other deployments
        model_result = await db.execute(
            select(Deployment)
            .where(Deployment.model_id == deployment.model_id)
            .where(Deployment.status == DeploymentStatus.RUNNING)
        )
        running_deployments = model_result.scalars().all()
        if len(running_deployments) == 0:
            model_result = await db.execute(select(Model).where(Model.id == deployment.model_id))
            model = model_result.scalar_one_or_none()
            if model:
                model.is_deployed = False

        await db.commit()
        return True

    @staticmethod
    async def restart_deployment(db: AsyncSession, deployment_id: str) -> bool:
        """重启部署"""
        deployment = await DeploymentService.get_deployment(db, deployment_id)
        if not deployment:
            return False

        # Get model
        model_result = await db.execute(select(Model).where(Model.id == deployment.model_id))
        model = model_result.scalar_one_or_none()
        if not model:
            return False

        try:
            from ultralytics import YOLO
            yolo_model = YOLO(model.model_path)
            _model_cache[deployment_id] = yolo_model

            deployment.status = DeploymentStatus.RUNNING
            deployment.error_message = None
            model.is_deployed = True

            await db.commit()
            return True

        except Exception as e:
            logger.error(f"Failed to restart deployment {deployment_id}: {e}")
            deployment.status = DeploymentStatus.FAILED
            deployment.error_message = str(e)
            await db.commit()
            return False

    @staticmethod
    async def delete_deployment(db: AsyncSession, deployment_id: str) -> bool:
        """删除部署"""
        deployment = await DeploymentService.get_deployment(db, deployment_id)
        if not deployment:
            return False

        # Remove from cache
        if deployment_id in _model_cache:
            del _model_cache[deployment_id]

        await db.delete(deployment)
        await db.commit()
        return True

    @staticmethod
    async def predict(
        db: AsyncSession,
        deployment_id: str,
        image_data: bytes,
        confidence: Optional[float] = None,
        iou: Optional[float] = None
    ) -> dict:
        """使用部署进行推理"""
        deployment = await DeploymentService.get_deployment(db, deployment_id)
        if not deployment:
            raise ValueError(f"Deployment {deployment_id} not found")

        if deployment.status != DeploymentStatus.RUNNING:
            raise ValueError(f"Deployment {deployment_id} is not running")

        # Get model from cache or load it
        if deployment_id not in _model_cache:
            model_result = await db.execute(select(Model).where(Model.id == deployment.model_id))
            model = model_result.scalar_one_or_none()
            if not model:
                raise ValueError(f"Model {deployment.model_id} not found")

            from ultralytics import YOLO
            yolo_model = YOLO(model.model_path)
            _model_cache[deployment_id] = yolo_model
        else:
            yolo_model = _model_cache[deployment_id]

        # Use deployment settings or override
        conf = confidence if confidence is not None else deployment.confidence_threshold
        iou_thresh = iou if iou is not None else deployment.iou_threshold

        # Load image
        from io import BytesIO
        pil_image = PILImage.open(BytesIO(image_data))
        image_size = pil_image.size  # (width, height)

        # Run inference
        start_time = time.time()
        results = yolo_model.predict(
            pil_image,
            conf=conf,
            iou=iou_thresh,
            max_det=deployment.max_detections,
            verbose=False
        )
        inference_time = (time.time() - start_time) * 1000  # ms

        # Parse results
        detections = []
        if results and len(results) > 0:
            result = results[0]
            if result.boxes is not None and len(result.boxes) > 0:
                boxes = result.boxes
                for box in boxes:
                    # Get xyxy format (absolute coordinates)
                    xyxy = box.xyxy[0].cpu().numpy()
                    # Get xywhn format (normalized)
                    xywhn = box.xywhn[0].cpu().numpy()

                    cls_id = int(box.cls[0].cpu().numpy())
                    conf_val = float(box.conf[0].cpu().numpy())
                    class_name = yolo_model.names.get(cls_id, f"class_{cls_id}")

                    detections.append({
                        "class_id": cls_id,
                        "class_name": class_name,
                        "confidence": conf_val,
                        "bbox": [float(x) for x in xyxy],  # [x1, y1, x2, y2]
                        "bbox_normalized": [float(x) for x in xywhn],  # [x_center, y_center, w, h]
                    })

        # Generate image with bounding boxes
        import cv2
        import base64

        # Convert PIL image to numpy array
        image_np = np.array(pil_image)
        if image_np.ndim == 2:  # Grayscale
            image_np = cv2.cvtColor(image_np, cv2.COLOR_GRAY2BGR)
        elif image_np.ndim == 3:
            if image_np.shape[2] == 4:  # RGBA
                image_np = cv2.cvtColor(image_np, cv2.COLOR_RGBA2BGR)
            elif image_np.shape[2] == 3:  # RGB
                image_np = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)

        # Draw bounding boxes
        for detection in detections:
            bbox = detection["bbox"]
            x1, y1, x2, y2 = map(int, bbox)
            class_name = detection["class_name"]
            confidence = detection["confidence"]

            # Draw rectangle
            cv2.rectangle(image_np, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # Draw label background
            label = f"{class_name}: {confidence:.2f}"
            (label_width, label_height), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(image_np, (x1, y1 - label_height - 10), (x1 + label_width, y1), (0, 255, 0), -1)

            # Draw label text
            cv2.putText(image_np, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

        # Encode image to base64
        _, buffer = cv2.imencode('.jpg', image_np)
        image_base64 = base64.b64encode(buffer).decode('utf-8')
        image_with_boxes = f"data:image/jpeg;base64,{image_base64}"

        # Update request count and total inference time
        deployment.request_count += 1
        deployment.total_inference_time_ms += inference_time
        await db.commit()

        return {
            "detections": detections,
            "inference_time": round(inference_time / 1000, 3),  # Convert to seconds
            "inference_time_ms": round(inference_time, 2),
            "image_size": list(image_size),
            "image_with_boxes": image_with_boxes,
        }

    @staticmethod
    def get_loaded_models() -> List[str]:
        """获取已加载的模型列表"""
        return list(_model_cache.keys())

