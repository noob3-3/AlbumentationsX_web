"""add semantic_mask_path to images for semantic (-sem) PNG masks

Revision ID: add_image_semantic_mask_path
Revises: add_dataset_label_task
"""

from alembic import op
import sqlalchemy as sa

revision = "add_image_semantic_mask_path"
down_revision = "add_dataset_label_task"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "images",
        sa.Column("semantic_mask_path", sa.String(length=1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("images", "semantic_mask_path")
