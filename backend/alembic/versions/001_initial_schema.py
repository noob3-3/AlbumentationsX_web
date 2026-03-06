"""Initial schema - create all tables

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-03-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create projects table
    op.create_table(
        'projects',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('dataset_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('model_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('webhook_url', sa.String(500), nullable=True),
        sa.Column('webhook_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('webhook_secret', sa.String(100), nullable=True),
        sa.Column('webhook_events', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # Create datasets table
    op.create_table(
        'datasets',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('classes', sa.JSON(), nullable=True),
        sa.Column('image_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('annotated_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('storage_path', sa.String(1024), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # Create images table
    op.create_table(
        'images',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('dataset_id', sa.String(36), sa.ForeignKey('datasets.id'), nullable=False),
        sa.Column('filename', sa.String(512), nullable=False),
        sa.Column('original_filename', sa.String(512), nullable=True),
        sa.Column('file_path', sa.String(1024), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(20), nullable=False, server_default='local'),
        sa.Column('annotation_status', sa.String(30), nullable=False, server_default='unannotated'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # Create annotations table
    op.create_table(
        'annotations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('image_id', sa.String(36), sa.ForeignKey('images.id'), nullable=False),
        sa.Column('class_id', sa.Integer(), nullable=False),
        sa.Column('class_name', sa.String(128), nullable=False),
        sa.Column('bbox', sa.JSON(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # Create augmentation_jobs table
    op.create_table(
        'augmentation_jobs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('dataset_id', sa.String(36), sa.ForeignKey('datasets.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('target_count', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('processed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('transforms', sa.JSON(), nullable=True),
        sa.Column('output_dir', sa.String(1024), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # Create training_jobs table
    op.create_table(
        'training_jobs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('dataset_id', sa.String(36), sa.ForeignKey('datasets.id'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('model_name', sa.String(128), nullable=False, server_default='yolo11n.pt'),
        sa.Column('epochs', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('batch_size', sa.Integer(), nullable=False, server_default='16'),
        sa.Column('img_size', sa.Integer(), nullable=False, server_default='640'),
        sa.Column('learning_rate', sa.Float(), nullable=False, server_default='0.01'),
        sa.Column('val_split', sa.Float(), nullable=False, server_default='0.2'),
        sa.Column('device', sa.String(32), nullable=False, server_default='auto'),
        sa.Column('use_augmented_data', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('extra_params', sa.JSON(), nullable=True),
        sa.Column('current_epoch', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('best_map50', sa.Float(), nullable=True),
        sa.Column('best_map50_95', sa.Float(), nullable=True),
        sa.Column('metrics_history', sa.JSON(), nullable=True),
        sa.Column('model_path', sa.String(1024), nullable=True),
        sa.Column('output_dir', sa.String(1024), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        # Time estimation fields
        sa.Column('avg_epoch_time', sa.Float(), nullable=True),
        sa.Column('estimated_remaining_time', sa.Float(), nullable=True),
        sa.Column('estimated_completion_time', sa.DateTime(), nullable=True),
    )

    # Create models table
    op.create_table(
        'models',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('training_job_id', sa.String(36), nullable=True),
        sa.Column('model_path', sa.String(1024), nullable=False),
        sa.Column('model_type', sa.String(64), nullable=False, server_default='yolo'),
        sa.Column('classes', sa.JSON(), nullable=True),
        sa.Column('map50', sa.Float(), nullable=True),
        sa.Column('map50_95', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # Create deployments table
    op.create_table(
        'deployments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('model_id', sa.String(36), sa.ForeignKey('models.id'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='inactive'),
        sa.Column('endpoint_url', sa.String(512), nullable=True),
        sa.Column('device', sa.String(32), nullable=False, server_default='cpu'),
        sa.Column('batch_size', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('confidence_threshold', sa.Float(), nullable=False, server_default='0.25'),
        sa.Column('iou_threshold', sa.Float(), nullable=False, server_default='0.45'),
        sa.Column('total_inference_time_ms', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # Create inference_results table
    op.create_table(
        'inference_results',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('deployment_id', sa.String(36), sa.ForeignKey('deployments.id'), nullable=False),
        sa.Column('image_path', sa.String(1024), nullable=False),
        sa.Column('detections', sa.JSON(), nullable=True),
        sa.Column('inference_time', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # Create annotation_jobs table
    op.create_table(
        'annotation_jobs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('dataset_id', sa.String(36), sa.ForeignKey('datasets.id'), nullable=False),
        sa.Column('model_id', sa.String(36), sa.ForeignKey('models.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('total_images', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('processed_images', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('confidence_threshold', sa.Float(), nullable=False, server_default='0.25'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # Create collections table
    op.create_table(
        'collections',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('query_filters', sa.JSON(), nullable=True),
        sa.Column('image_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # Create collection_images junction table
    op.create_table(
        'collection_images',
        sa.Column('collection_id', sa.String(36), sa.ForeignKey('collections.id'), nullable=False),
        sa.Column('image_id', sa.String(36), sa.ForeignKey('images.id'), nullable=False),
        sa.Column('added_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('collection_id', 'image_id'),
    )


def downgrade() -> None:
    op.drop_table('collection_images')
    op.drop_table('collections')
    op.drop_table('annotation_jobs')
    op.drop_table('inference_results')
    op.drop_table('deployments')
    op.drop_table('models')
    op.drop_table('training_jobs')
    op.drop_table('augmentation_jobs')
    op.drop_table('annotations')
    op.drop_table('images')
    op.drop_table('datasets')
    op.drop_table('projects')

