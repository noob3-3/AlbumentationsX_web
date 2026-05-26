"""将 datasets / images 表中的 static-file 路径改为 datasets（与 DATASET_DIR 默认一致）

Revision ID: migrate_paths_static_to_datasets
Revises: add_annotation_polygon_points
Create Date: 2026-04-15

说明：仅更新数据库中的路径字符串。若文件仍在宿主机 ./data/static-file/<uuid>/ 下，
请手动复制到 ./data/datasets/<uuid>/（保持同名 UUID 目录），再执行训练。
"""
from alembic import op
from sqlalchemy import text


revision = "migrate_paths_static_to_datasets"
down_revision = "add_annotation_polygon_points"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 统一将 /data/static-file/ 替换为 /data/datasets/（适用于 /app/data/... 等前缀）
    for stmt in (
        """
        UPDATE datasets SET storage_path = REPLACE(storage_path, '/data/static-file/', '/data/datasets/')
        WHERE storage_path IS NOT NULL AND storage_path LIKE '%/data/static-file/%'
        """,
        """
        UPDATE images SET file_path = REPLACE(file_path, '/data/static-file/', '/data/datasets/')
        WHERE file_path LIKE '%/data/static-file/%'
        """,
        """
        UPDATE images SET thumbnail_path = REPLACE(thumbnail_path, '/data/static-file/', '/data/datasets/')
        WHERE thumbnail_path IS NOT NULL AND thumbnail_path LIKE '%/data/static-file/%'
        """,
    ):
        op.execute(text(stmt))


def downgrade() -> None:
    for stmt in (
        """
        UPDATE datasets SET storage_path = REPLACE(storage_path, '/data/datasets/', '/data/static-file/')
        WHERE storage_path IS NOT NULL AND storage_path LIKE '%/data/datasets/%'
        """,
        """
        UPDATE images SET file_path = REPLACE(file_path, '/data/datasets/', '/data/static-file/')
        WHERE file_path LIKE '%/data/datasets/%'
        """,
        """
        UPDATE images SET thumbnail_path = REPLACE(thumbnail_path, '/data/datasets/', '/data/static-file/')
        WHERE thumbnail_path IS NOT NULL AND thumbnail_path LIKE '%/data/datasets/%'
        """,
    ):
        op.execute(text(stmt))
