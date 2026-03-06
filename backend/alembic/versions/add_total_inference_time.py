"""add total_inference_time_ms to deployment

Revision ID: add_total_inference_time
Revises:
Create Date: 2026-03-05

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_total_inference_time'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add total_inference_time_ms column to deployments table as nullable first
    op.add_column('deployments', sa.Column('total_inference_time_ms', sa.Float(), nullable=True))

    # Set default value for existing records
    op.execute("UPDATE deployments SET total_inference_time_ms = 0.0 WHERE total_inference_time_ms IS NULL")

    # Make column non-nullable
    op.alter_column('deployments', 'total_inference_time_ms', nullable=False, server_default='0.0')


def downgrade() -> None:
    # Remove total_inference_time_ms column
    op.drop_column('deployments', 'total_inference_time_ms')

