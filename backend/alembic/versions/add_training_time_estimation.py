"""add time estimation fields to training_jobs

Revision ID: add_training_time_estimation
Revises: add_total_inference_time
Create Date: 2026-03-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_training_time_estimation'
down_revision = 'add_total_inference_time'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add time estimation columns to training_jobs table
    op.add_column('training_jobs', sa.Column('avg_epoch_time', sa.Float(), nullable=True))
    op.add_column('training_jobs', sa.Column('estimated_remaining_time', sa.Float(), nullable=True))
    op.add_column('training_jobs', sa.Column('estimated_completion_time', sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Remove time estimation columns
    op.drop_column('training_jobs', 'estimated_completion_time')
    op.drop_column('training_jobs', 'estimated_remaining_time')
    op.drop_column('training_jobs', 'avg_epoch_time')

