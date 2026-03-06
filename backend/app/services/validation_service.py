"""
Model validation service for testing multiple models on single image
"""
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Model, ModelValidation, Deployment, DeploymentStatus
from app.core.logging import logger


class ModelValidationService:
    """Service for validating multiple models on a single image"""

    @staticmethod
    async def validate_models(
        db: AsyncSession,
        model_ids: List[str],
        image_path: str,
        confidence_threshold: float = 0.5,
        iou_threshold: float = 0.45,
    ) -> Dict[str, Any]:
        """
        Validate multiple models on a single image
        优先使用已部署的模型，如果模型未部署则临时加载
        """
        from ultralytics import YOLO
        from app.services.deployment_service import DeploymentService
        import cv2

        # Load image
        image_name = Path(image_path).name
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Cannot load image from {image_path}")

        height, width = img.shape[:2]

        # Read image as bytes for deployment API
        with open(image_path, 'rb') as f:
            image_data = f.read()

        results = []
        total_start = time.time()

        # Get models
        models_result = await db.execute(
            select(Model).where(Model.id.in_(model_ids))
        )
        models = models_result.scalars().all()

        for model_obj in models:
            try:
                # 检查模型是否有正在运行的部署
                deployment_result = await db.execute(
                    select(Deployment)
                    .where(Deployment.model_id == model_obj.id)
                    .where(Deployment.status == DeploymentStatus.RUNNING)
                    .limit(1)
                )
                deployment = deployment_result.scalar_one_or_none()

                if deployment:
                    # 使用已部署的模型进行推理
                    logger.info(f"Using deployed model {model_obj.name} (deployment: {deployment.id})")
                    start_time = time.time()

                    try:
                        inference_result = await DeploymentService.predict(
                            db=db,
                            deployment_id=deployment.id,
                            image_data=image_data,
                            confidence=confidence_threshold,
                            iou=iou_threshold,
                        )

                        detections = inference_result["detections"]
                        inference_time = inference_result["inference_time_ms"]

                    except Exception as e:
                        logger.error(f"Deployment prediction failed for {model_obj.name}: {e}")
                        raise
                else:
                    # 模型未部署，临时加载模型
                    logger.info(f"Model {model_obj.name} not deployed, loading temporarily")
                    start_time = time.time()

                    if not Path(model_obj.model_path).exists():
                        raise ValueError(f"Model file not found: {model_obj.model_path}")

                    yolo_model = YOLO(model_obj.model_path)

                    # Run inference
                    predictions = yolo_model.predict(
                        image_path,
                        conf=confidence_threshold,
                        iou=iou_threshold,
                        verbose=False,
                    )
                    inference_time = (time.time() - start_time) * 1000

                    # Parse detections
                    detections = []
                    if predictions and len(predictions) > 0:
                        pred = predictions[0]
                        boxes = pred.boxes

                        for i, box in enumerate(boxes):
                            # Get box coordinates (xyxy format)
                            xyxy = box.xyxy[0].cpu().numpy()
                            x1, y1, x2, y2 = xyxy

                            # Normalize coordinates
                            cx = (x1 + x2) / 2 / width
                            cy = (y1 + y2) / 2 / height
                            w = (x2 - x1) / width
                            h = (y2 - y1) / height

                            class_id = int(box.cls[0].cpu().numpy())
                            confidence = float(box.conf[0].cpu().numpy())

                            # Get class name
                            class_name = yolo_model.names.get(class_id, f"class_{class_id}")

                            detections.append({
                                "class_id": class_id,
                                "class_name": class_name,
                                "confidence": confidence,
                                "bbox": [float(x1), float(y1), float(x2), float(y2)],
                                "bbox_normalized": [float(cx), float(cy), float(w), float(h)],
                            })

                # Save validation record
                validation = ModelValidation(
                    model_id=model_obj.id,
                    image_path=image_path,
                    image_name=image_name,
                    detections=detections,
                    inference_time_ms=inference_time,
                    confidence_threshold=confidence_threshold,
                    iou_threshold=iou_threshold,
                    detection_count=len(detections),
                )
                db.add(validation)

                results.append({
                    "model_id": model_obj.id,
                    "model_name": model_obj.name,
                    "detections": detections,
                    "inference_time_ms": inference_time,
                    "detection_count": len(detections),
                    "error": None,
                    "used_deployment": deployment is not None,
                    "deployment_id": deployment.id if deployment else None,
                })

            except Exception as e:
                logger.error(f"Error validating model {model_obj.id} ({model_obj.name}): {e}", exc_info=True)
                results.append({
                    "model_id": model_obj.id,
                    "model_name": model_obj.name,
                    "detections": [],
                    "inference_time_ms": 0,
                    "detection_count": 0,
                    "error": str(e),
                    "used_deployment": False,
                    "deployment_id": None,
                })

        total_time = (time.time() - total_start) * 1000
        await db.commit()

        return {
            "image_name": image_name,
            "image_size": [width, height],
            "results": results,
            "total_time_ms": total_time,
        }

    @staticmethod
    async def get_model_validations(
        db: AsyncSession,
        model_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[ModelValidation]:
        """Get validation history for a model or all models"""
        query = select(ModelValidation)

        if model_id:
            query = query.where(ModelValidation.model_id == model_id)

        query = query.order_by(ModelValidation.created_at.desc()).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().all())

