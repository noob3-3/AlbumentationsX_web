"""add datasets.label_task

Revision ID: add_label_task
Revises: migrate_paths_static_to_datasets
Create Date: 2026-04-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "add_dataset_label_task"
down_revision: Union[str, None] = "migrate_paths_static_to_datasets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "datasets",
        sa.Column(
            "label_task",
            sa.String(32),
            server_default="detect",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("datasets", "label_task")
