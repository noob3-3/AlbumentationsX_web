"""
SQLAlchemy ORM Models
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, Text,
    ForeignKey, JSON, Enum as SAEnum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.core.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class ProjectStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class DatasetStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    AUGMENTING = "augmenting"
    READY = "ready"
    ERROR = "error"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ImageSource(str, enum.Enum):
    LOCAL = "local"
    API = "api"
    CLIENT = "client"


class AnnotationStatus(str, enum.Enum):
    UNANNOTATED = "unannotated"  # 未标注
    AUTO_ANNOTATED = "auto_annotated"  # 自动标注
    MANUALLY_ANNOTATED = "manually_annotated"  # 手动标注
    REVIEWED = "reviewed"  # 已审核


# ─────────────────────────────────────────────
# Project (top-level organization)
# ─────────────────────────────────────────────
class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[ProjectStatus] = mapped_column(
        SAEnum(ProjectStatus, native_enum=False), default=ProjectStatus.ACTIVE
    )
    dataset_count: Mapped[int] = mapped_column(Integer, default=0)
    model_count: Mapped[int] = mapped_column(Integer, default=0)

    # Webhook 配置
    webhook_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    webhook_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # 用于签名验证
    webhook_events: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)  # 订阅的事件类型列表

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    datasets: Mapped[list["Dataset"]] = relationship("Dataset", back_populates="project_rel", cascade="all, delete-orphan")
    models: Mapped[list["Model"]] = relationship("Model", back_populates="project_rel")


# ─────────────────────────────────────────────
# Dataset
# ─────────────────────────────────────────────
class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id"))
    status: Mapped[DatasetStatus] = mapped_column(
        SAEnum(DatasetStatus, native_enum=False), default=DatasetStatus.PENDING
    )
    classes: Mapped[Optional[dict]] = mapped_column(JSON, default=list)  # 标注时自动生成的类别列表
    image_count: Mapped[int] = mapped_column(Integer, default=0)
    annotation_count: Mapped[int] = mapped_column(Integer, default=0)
    augmented_count: Mapped[int] = mapped_column(Integer, default=0)  # 增强数据数量
    storage_path: Mapped[Optional[str]] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    project_rel: Mapped[Optional["Project"]] = relationship("Project", back_populates="datasets")
    images: Mapped[list["Image"]] = relationship("Image", back_populates="dataset", cascade="all, delete-orphan")
    augmentation_jobs: Mapped[list["AugmentationJob"]] = relationship("AugmentationJob", viewonly=True)
    training_jobs: Mapped[list["TrainingJob"]] = relationship("TrainingJob", viewonly=True)


# ─────────────────────────────────────────────
# Image
# ─────────────────────────────────────────────
class Image(Base):
    __tablename__ = "images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(1024))
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    source: Mapped[ImageSource] = mapped_column(SAEnum(ImageSource, native_enum=False), default=ImageSource.LOCAL)
    source_url: Mapped[Optional[str]] = mapped_column(String(1024))
    is_augmented: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否为增强数据
    parent_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("images.id"))  # 增强数据的原始图片ID
    annotation_status: Mapped[AnnotationStatus] = mapped_column(
        SAEnum(AnnotationStatus, native_enum=False), default=AnnotationStatus.UNANNOTATED
    )  # 标注状态
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="images")
    annotations: Mapped[list["Annotation"]] = relationship(
        "Annotation", back_populates="image", cascade="all, delete-orphan"
    )


# ─────────────────────────────────────────────
# Annotation (YOLO format bounding boxes)
# ─────────────────────────────────────────────
class Annotation(Base):
    __tablename__ = "annotations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    image_id: Mapped[str] = mapped_column(String(36), ForeignKey("images.id"), nullable=False)
    class_id: Mapped[int] = mapped_column(Integer, nullable=False)
    class_name: Mapped[Optional[str]] = mapped_column(String(128))
    # YOLO normalized format: cx, cy, w, h (0-1)
    x_center: Mapped[float] = mapped_column(Float, nullable=False)
    y_center: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_width: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_height: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationship
    image: Mapped["Image"] = relationship("Image", back_populates="annotations")


# ─────────────────────────────────────────────
# Augmentation Job
# ─────────────────────────────────────────────
class AugmentationJob(Base):
    __tablename__ = "augmentation_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.id"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(SAEnum(JobStatus, native_enum=False), default=JobStatus.PENDING)
    config: Mapped[Optional[dict]] = mapped_column(JSON)  # albumentations pipeline config
    multiplier: Mapped[int] = mapped_column(Integer, default=3)  # augment N times per image
    total_images: Mapped[int] = mapped_column(Integer, default=0)
    processed_images: Mapped[int] = mapped_column(Integer, default=0)
    generated_images: Mapped[int] = mapped_column(Integer, default=0)  # 生成的增强图片数量
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationship (viewonly to prevent ORM from syncing dataset_id via relationship)
    dataset: Mapped["Dataset"] = relationship("Dataset", viewonly=True)


# ─────────────────────────────────────────────
# Training Job
# ─────────────────────────────────────────────
class TrainingJob(Base):
    __tablename__ = "training_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey("datasets.id"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(SAEnum(JobStatus, native_enum=False), default=JobStatus.PENDING)

    # Training hyperparameters
    model_name: Mapped[str] = mapped_column(String(128), default="yolo11n.pt")
    epochs: Mapped[int] = mapped_column(Integer, default=100)
    batch_size: Mapped[int] = mapped_column(Integer, default=16)
    img_size: Mapped[int] = mapped_column(Integer, default=640)
    learning_rate: Mapped[float] = mapped_column(Float, default=0.01)
    val_split: Mapped[float] = mapped_column(Float, default=0.2)
    device: Mapped[str] = mapped_column(String(32), default="auto")
    use_augmented_data: Mapped[bool] = mapped_column(Boolean, default=True)  # 是否使用增强数据
    extra_params: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Results
    current_epoch: Mapped[int] = mapped_column(Integer, default=0)
    best_map50: Mapped[Optional[float]] = mapped_column(Float)
    best_map50_95: Mapped[Optional[float]] = mapped_column(Float)
    metrics_history: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    model_path: Mapped[Optional[str]] = mapped_column(String(1024))
    output_dir: Mapped[Optional[str]] = mapped_column(String(1024))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Time estimation (for running jobs)
    avg_epoch_time: Mapped[Optional[float]] = mapped_column(Float)  # 平均每轮训练时间（秒）
    estimated_remaining_time: Mapped[Optional[float]] = mapped_column(Float)  # 预计剩余时间（秒）
    estimated_completion_time: Mapped[Optional[datetime]] = mapped_column(DateTime)  # 预计完成时间

    # Relationship (viewonly to prevent ORM from syncing dataset_id via relationship)
    dataset: Mapped["Dataset"] = relationship("Dataset", viewonly=True)


# ─────────────────────────────────────────────
# Model (trained model artifact)
# ─────────────────────────────────────────────
class Model(Base):
    __tablename__ = "models"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id"))
    training_job_id: Mapped[Optional[str]] = mapped_column(String(36))
    model_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    model_type: Mapped[str] = mapped_column(String(64), default="yolo")
    classes: Mapped[Optional[dict]] = mapped_column(JSON)
    map50: Mapped[Optional[float]] = mapped_column(Float)
    map50_95: Mapped[Optional[float]] = mapped_column(Float)
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    is_deployed: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否已部署
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    project_rel: Mapped[Optional["Project"]] = relationship("Project", back_populates="models")
    deployments: Mapped[list["Deployment"]] = relationship("Deployment", back_populates="model")
    validations: Mapped[list["ModelValidation"]] = relationship(
        "ModelValidation", back_populates="model", cascade="all, delete-orphan"
    )


# ─────────────────────────────────────────────
# Deployment (deployed model service)
# ─────────────────────────────────────────────
class DeploymentStatus(str, enum.Enum):
    DEPLOYING = "deploying"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_id: Mapped[str] = mapped_column(String(36), ForeignKey("models.id"), nullable=False)
    status: Mapped[DeploymentStatus] = mapped_column(
        SAEnum(DeploymentStatus, native_enum=False), default=DeploymentStatus.DEPLOYING
    )
    endpoint_url: Mapped[Optional[str]] = mapped_column(String(512))  # API端点
    port: Mapped[Optional[int]] = mapped_column(Integer)
    confidence_threshold: Mapped[float] = mapped_column(Float, default=0.5)
    iou_threshold: Mapped[float] = mapped_column(Float, default=0.45)
    max_detections: Mapped[int] = mapped_column(Integer, default=100)
    device: Mapped[str] = mapped_column(String(32), default="cpu")
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    request_count: Mapped[int] = mapped_column(Integer, default=0)  # 请求次数
    total_inference_time_ms: Mapped[float] = mapped_column(Float, default=0.0)  # 总推理时间（毫秒）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    model: Mapped["Model"] = relationship("Model", back_populates="deployments")


# ─────────────────────────────────────────────
# Model Validation (test multiple models on single image)
# ─────────────────────────────────────────────
class ModelValidation(Base):
    __tablename__ = "model_validations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    model_id: Mapped[str] = mapped_column(String(36), ForeignKey("models.id"), nullable=False)
    image_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    image_name: Mapped[str] = mapped_column(String(512), nullable=False)
    detections: Mapped[Optional[dict]] = mapped_column(JSON)  # 检测结果
    inference_time_ms: Mapped[Optional[float]] = mapped_column(Float)
    confidence_threshold: Mapped[float] = mapped_column(Float, default=0.5)
    iou_threshold: Mapped[float] = mapped_column(Float, default=0.45)
    detection_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    model: Mapped["Model"] = relationship("Model", back_populates="validations")


