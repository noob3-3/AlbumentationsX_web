from app.services.annotation_service import AnnotationService
from app.services.augmentation_service import AugmentationService, build_pipeline, AVAILABLE_TRANSFORMS, \
    DEFAULT_AUGMENTATION_CONFIG
from app.services.collection_service import collect_from_urls, fetch_image_from_url
from app.services.dataset_service import DatasetService
from app.services.deployment_service import DeploymentService

__all__ = [
    "DatasetService",
    "collect_from_urls",
    "fetch_image_from_url",
    "AugmentationService",
    "build_pipeline",
    "AVAILABLE_TRANSFORMS",
    "DEFAULT_AUGMENTATION_CONFIG",
    "TrainingService",
    "AVAILABLE_MODELS",
    "infer_ultralytics_task_from_model_name",
    "AnnotationService",
    "DeploymentService",
]


def __getattr__(name):
    if name in ("TrainingService", "AVAILABLE_MODELS", "infer_ultralytics_task_from_model_name"):
        from app.services import training_service as _ts
        return getattr(_ts, name)
    raise AttributeError(name)
