#!/bin/bash
# 在Docker容器中运行数据库迁移

echo "开始运行数据库迁移..."

# 进入backend目录
cd /app

# 运行Alembic迁移
echo "运行Alembic upgrade..."
alembic upgrade head

echo "迁移完成！"

