"""add polygon_points JSON to annotations for pose / polygon labels

Revision ID: add_annotation_polygon_points
Revises: add_training_time_estimation
Create Date: 2026-04-15

"""
from alembic import op
import sqlalchemy as sa


revision = "add_annotation_polygon_points"
down_revision = "add_training_time_estimation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "annotations",
        sa.Column("polygon_points", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("annotations", "polygon_points")
