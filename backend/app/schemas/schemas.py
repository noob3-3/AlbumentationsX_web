"""
Pydantic schemas for request/response validation
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, HttpUrl, ConfigDict

from app.models.models import DatasetStatus, JobStatus, ImageSource, AnnotationStatus, DeploymentStatus, ProjectStatus


# ─────────────────────────────────────────────
# Common
# ─────────────────────────────────────────────
class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[Any]


# ─────────────────────────────────────────────
# Project
# ─────────────────────────────────────────────
class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None

    # Webhook 配置
    webhook_url: Optional[str] = Field(None, max_length=500)
    webhook_enabled: bool = False
    webhook_secret: Optional[str] = Field(None, max_length=100)
    webhook_events: Optional[List[str]] = None  # 例如: ["training", "augmentation", "annotation"]


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[ProjectStatus] = None

    # Webhook 配置
    webhook_url: Optional[str] = Field(None, max_length=500)
    webhook_enabled: Optional[bool] = None
    webhook_secret: Optional[str] = Field(None, max_length=100)
    webhook_events: Optional[List[str]] = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    status: ProjectStatus
    dataset_count: int
    model_count: int

    # Webhook 配置
    webhook_url: Optional[str] = None
    webhook_enabled: bool = False
    webhook_secret: Optional[str] = None
    webhook_events: Optional[List[str]] = None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────
# Annotation
# ─────────────────────────────────────────────
class AnnotationCreate(BaseModel):
    class_id: int
    class_name: Optional[str] = None
    x_center: float = Field(..., ge=0.0, le=1.0)
    y_center: float = Field(..., ge=0.0, le=1.0)
    bbox_width: float = Field(..., ge=0.0, le=1.0)
    bbox_height: float = Field(..., ge=0.0, le=1.0)
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class AnnotationResponse(AnnotationCreate):
    id: str
    image_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────
# Image
# ─────────────────────────────────────────────
class ImageResponse(BaseModel):
    id: str
    dataset_id: str
    filename: str
    original_filename: str
    file_path: str
    thumbnail_path: Optional[str]
    width: Optional[int]
    height: Optional[int]
    file_size: Optional[int]
    source: ImageSource
    source_url: Optional[str]
    is_augmented: bool
    parent_id: Optional[str]
    annotation_status: AnnotationStatus
    created_at: datetime
    annotations: List[AnnotationResponse] = []

    model_config = ConfigDict(from_attributes=True)


class ImageUploadResponse(BaseModel):
    id: str
    filename: str
    dataset_id: str
    width: Optional[int]
    height: Optional[int]
    file_size: Optional[int]


# ─────────────────────────────────────────────
# Dataset
# ─────────────────────────────────────────────
class DatasetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    project_id: Optional[str] = None
    classes: Optional[List[str]] = None


class DatasetUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    project_id: Optional[str] = None
    status: Optional[DatasetStatus] = None


class DatasetResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    project_id: Optional[str]
    status: DatasetStatus
    classes: Optional[List[str]]  # 从标注中自动生成
    image_count: int
    annotation_count: int
    augmented_count: int  # 增强数据数量
    storage_path: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────
# API Collection (pull images from URL)
# ─────────────────────────────────────────────
class APICollectionRequest(BaseModel):
    dataset_id: str
    urls: List[str] = Field(..., min_length=1)
    annotations: Optional[List[Optional[List[AnnotationCreate]]]] = None  # per-image annotations


# ─────────────────────────────────────────────
# Client Collection (remote client pushes images)
# ─────────────────────────────────────────────
class ClientImageUpload(BaseModel):
    dataset_id: str
    source_url: Optional[str] = None
    annotations: Optional[List[AnnotationCreate]] = None


# ─────────────────────────────────────────────
# Augmentation
# ─────────────────────────────────────────────
class AugmentationTransform(BaseModel):
    name: str  # e.g. "HorizontalFlip", "RandomBrightnessContrast"
    params: Dict[str, Any] = {}


class AugmentationConfig(BaseModel):
    transforms: List[AugmentationTransform]
    bbox_params: Optional[Dict[str, Any]] = {
        "format": "yolo",
        "min_visibility": 0.3,
        "label_fields": ["class_labels"],
    }


class AugmentationJobCreate(BaseModel):
    dataset_id: str
    config: Optional[AugmentationConfig] = None  # None = use default config
    multiplier: int = Field(3, ge=1, le=20)


class AugmentationJobResponse(BaseModel):
    id: str
    dataset_id: str
    status: JobStatus
    config: Optional[Dict[str, Any]]
    multiplier: int
    total_images: int
    processed_images: int
    generated_images: int  # 生成的增强图片数量
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────
# Training
# ─────────────────────────────────────────────


class TrainingJobResponse(BaseModel):
    id: str
    name: str
    dataset_id: str
    status: JobStatus
    model_name: str
    epochs: int
    batch_size: int
    img_size: int
    learning_rate: float
    val_split: float
    device: str
    extra_params: Optional[Dict[str, Any]]
    current_epoch: int
    best_map50: Optional[float]
    best_map50_95: Optional[float]
    metrics_history: Optional[List[Dict[str, Any]]]
    model_path: Optional[str]
    output_dir: Optional[str]
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    # Time estimation fields
    avg_epoch_time: Optional[float] = None
    estimated_remaining_time: Optional[float] = None
    estimated_completion_time: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TrainingProgressUpdate(BaseModel):
    job_id: str
    epoch: int
    total_epochs: int
    metrics: Dict[str, float]
    status: str


# ─────────────────────────────────────────────
# Model
# ─────────────────────────────────────────────
class ModelResponse(BaseModel):
    id: str
    name: str
    project_id: Optional[str]
    training_job_id: Optional[str]
    model_path: str
    model_type: str
    classes: Optional[List[str]]
    map50: Optional[float]
    map50_95: Optional[float]
    file_size: Optional[int]
    is_deployed: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────
# Manual Annotation
# ─────────────────────────────────────────────
class AnnotationUpdate(BaseModel):
    """批量更新图片的标注"""
    annotations: List[AnnotationCreate]


class AutoAnnotationRequest(BaseModel):
    """自动标注请求"""
    dataset_id: str
    model_id: Optional[str] = None  # 自定义模型ID（当use_pretrained=False时必填）
    confidence_threshold: float = Field(0.5, ge=0.0, le=1.0)
    image_ids: Optional[List[str]] = None  # 如果为空则根据annotate_all决定
    use_pretrained: bool = False  # 是否使用预训练模型
    pretrained_model_name: Optional[str] = None  # 预训练模型名称（当use_pretrained=True时必填）
    annotate_all: bool = False  # 是否标注所有图片（包括已标注的），默认只标注未标注的
    include_augmented: bool = False  # 是否包含增强数据，默认只标注原始图片


class BatchReplaceClassesRequest(BaseModel):
    """批量替换类别请求"""
    dataset_id: str
    class_mapping: Dict[str, str]  # {"old_class": "new_class"}


class LabelCreate(BaseModel):
    """创建标签（类别）"""
    name: str = Field(..., min_length=1, max_length=128)
    color: Optional[str] = None  # 十六进制颜色


# ─────────────────────────────────────────────
# Training with augmentation control
# ─────────────────────────────────────────────
class TrainingJobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    dataset_id: str
    model_name: str = "yolo11n.pt"
    epochs: int = Field(100, ge=1, le=1000)
    batch_size: int = Field(16, ge=1, le=512)
    img_size: int = Field(640, ge=32, le=1920)
    learning_rate: float = Field(0.01, gt=0, le=1.0)
    val_split: float = Field(0.2, gt=0, lt=1.0)
    device: str = "auto"
    use_augmented_data: bool = True  # 是否使用增强数据
    extra_params: Optional[Dict[str, Any]] = {}

    # 继续训练相关参数
    resume_training: bool = False  # 是否继续训练
    base_model_id: Optional[str] = None  # 基础模型ID（继续训练时使用）

    # 类别增强训练参数
    class_weights: Optional[Dict[str, float]] = None  # 类别权重，例如 {"cat": 2.0, "dog": 1.5}
    focus_classes: Optional[List[str]] = None  # 重点训练的类别列表

    # 早停参数
    patience: int = Field(50, ge=0, le=200, description="早停耐心值，连续N轮验证指标不改善则停止，0表示不启用")
    save_period: int = Field(-1, ge=-1, le=100, description="每N轮保存一次模型，-1表示只保存最佳和最后")

    # Webhook 推送
    enable_webhook: bool = False  # 是否为本次任务启用 Webhook 推送


# ─────────────────────────────────────────────
# Deployment
# ─────────────────────────────────────────────
class DeploymentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    model_id: str
    confidence_threshold: float = Field(0.5, ge=0.0, le=1.0)
    iou_threshold: float = Field(0.45, ge=0.0, le=1.0)
    max_detections: int = Field(100, ge=1, le=1000)
    device: str = "cpu"


class DeploymentResponse(BaseModel):
    id: str
    name: str
    model_id: str
    model_name: Optional[str] = None  # 模型名称
    status: DeploymentStatus
    endpoint_url: Optional[str]
    port: Optional[int]
    confidence_threshold: float
    iou_threshold: float
    max_detections: int
    device: str
    error_message: Optional[str]
    request_count: int
    inference_count: Optional[int] = None  # 别名字段，与request_count相同
    avg_time: Optional[str] = None  # 平均耗时（格式化字符串）
    avg_inference_time_ms: Optional[float] = None  # 平均耗时（毫秒）
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InferenceRequest(BaseModel):
    """推理请求"""
    deployment_id: Optional[str] = None  # 如果不指定则使用 model_id
    model_id: Optional[str] = None
    confidence: Optional[float] = None
    iou: Optional[float] = None


class DetectionResult(BaseModel):
    """单个检测结果"""
    class_id: int
    class_name: str
    confidence: float
    bbox: List[float]  # [x1, y1, x2, y2]
    bbox_normalized: List[float]  # [x_center, y_center, width, height] normalized


class InferenceResponse(BaseModel):
    """推理响应"""
    detections: List[DetectionResult]
    inference_time: float  # seconds
    inference_time_ms: float  # milliseconds
    image_size: List[int]  # [width, height]
    image_with_boxes: str  # base64 encoded image


# ─────────────────────────────────────────────
# Generic responses
# ─────────────────────────────────────────────
class SuccessResponse(BaseModel):
    success: bool = True
    message: str


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    detail: Optional[str] = None


# ─────────────────────────────────────────────
# Model Validation
# ─────────────────────────────────────────────
class ModelValidationRequest(BaseModel):
    """多模型验证请求"""
    model_ids: List[str] = Field(..., min_length=1)
    confidence_threshold: float = Field(0.5, ge=0.0, le=1.0)
    iou_threshold: float = Field(0.45, ge=0.0, le=1.0)


class ModelValidationResult(BaseModel):
    """单个模型的验证结果"""
    model_id: str
    model_name: str
    detections: List[DetectionResult]
    inference_time_ms: float
    detection_count: int
    error: Optional[str] = None
    used_deployment: bool = False  # 是否使用了已部署的模型
    deployment_id: Optional[str] = None  # 使用的部署ID


class ModelValidationResponse(BaseModel):
    """多模型验证响应"""
    image_name: str
    image_size: List[int]  # [width, height]
    results: List[ModelValidationResult]
    total_time_ms: float

