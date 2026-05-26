# 共享内存不足问题修复

## 问题描述

训练时出现以下错误：

```
ERROR: Unexpected bus error encountered in worker. This might be caused by insufficient shared memory (shm).
RuntimeError: unable to write to file </torch_287_2714559211_8>: No space left on device (28)
```

这是由于 **Docker 容器的共享内存（/dev/shm）不足** 导致的。PyTorch 的 DataLoader 使用多进程加载数据时需要共享内存来传递数据，默认的 64MB 通常不够用。

## 根本原因

1. **Docker 默认共享内存太小**：Docker 容器默认只有 64MB 的 `/dev/shm`
2. **PyTorch DataLoader 使用多进程**：`workers > 0` 时需要共享内存
3. **训练数据加载**：YOLO 训练时使用多个 worker 并行加载图像数据

## 解决方案

### 方案 1：增加 Docker 共享内存（推荐）

在 `docker-compose.gpu.yml` 中为 backend-gpu 服务添加 `shm_size` 配置：

```yaml
services:
  backend-gpu:
    # ... 其他配置 ...
    shm_size: '2gb'  # 或 '4gb'、'8gb' 等
```

**推荐值**：
- 小数据集（< 1000 张图片）：2GB
- 中等数据集（1000-5000 张）：4GB
- 大数据集（> 5000 张）：8GB

### 方案 2：使用文件系统存储（备选）

如果无法增加共享内存，可以修改 DataLoader 配置：

在 `backend/app/services/training_service.py` 中修改训练参数：

```python
train_args = {
    # ... 其他参数 ...
    "workers": 0,  # 禁用多进程数据加载
    # 或者
    "workers": 2,  # 减少 worker 数量
}
```

**注意**：这会降低训练速度，但可以避免共享内存问题。

### 方案 3：修改 YOLO 训练配置

在训练参数中添加共享内存相关配置：

```python
train_args = {
    # ... 其他参数 ...
    "workers": 4,  # 根据实际情况调整
    "persistent_workers": False,  # 不持久化 workers
}
```

## 完整修复步骤

### 步骤 1：修改 docker-compose.gpu.yml

```yaml
services:
  backend-gpu:
    build:
      context: .
      dockerfile: backend/Dockerfile.gpu
      args:
        - BUILDKIT_INLINE_CACHE=1
    container_name: axweb-backend-gpu
    
    # 添加共享内存配置
    shm_size: '4gb'  # ← 添加这一行
    
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
    # ... 其他配置 ...
```

### 步骤 2：优化训练参数（可选）

在 `backend/app/services/training_service.py` 中优化 worker 配置：

```python
# 根据共享内存大小动态调整 workers
def get_optimal_workers(shm_size_gb: float, batch_size: int) -> int:
    """计算最优 worker 数量"""
    # 经验公式：每个 worker 大约需要 batch_size * 50MB
    estimated_memory_per_worker = batch_size * 50  # MB
    max_workers = int((shm_size_gb * 1024) / estimated_memory_per_worker)
    return min(max_workers, 8)  # 最多 8 个 workers

# 在训练配置中使用
train_args = {
    # ... 其他参数 ...
    "workers": get_optimal_workers(shm_size_gb=4, batch_size=job.batch_size),
    "persistent_workers": False,
}
```

### 步骤 3：重启容器

```bash
# 停止容器
docker-compose -f docker-compose.gpu.yml down

# 重新构建并启动
docker-compose -f docker-compose.gpu.yml up -d --build
```

## 验证修复

### 1. 检查共享内存大小

```bash
# 进入容器
docker exec -it axweb-backend-gpu bash

# 检查 /dev/shm 大小
df -h /dev/shm
```

应该看到类似：
```
Filesystem      Size  Used Avail Use% Mounted on
shm             4.0G     0  4.0G   0% /dev/shm
```

### 2. 查看训练日志

```bash
docker logs -f axweb-backend-gpu
```

不应再出现 "bus error" 或 "No space left on device" 错误。

## 其他相关错误

### 标签类别超出范围错误

```
train: /app/data/exports/.../aug0_Acura_010.jpg: ignoring corrupt image/label: 
Label class 62 exceeds dataset class count 15. Possible class labels are 0-14
```

这是 **数据集标注错误**，与共享内存无关。需要检查：

1. **数据增强问题**：增强过程可能没有正确更新标签类别
2. **标注数据错误**：原始标注文件包含了不在当前数据集中的类别
3. **类别映射问题**：导出时类别 ID 映射不正确

**修复方法**：
- 检查增强服务中的标签处理逻辑
- 验证数据集导出时的类别映射
- 清理或重新标注问题图片

## 性能优化建议

### 1. Worker 数量选择

```python
# 根据 CPU 核心数和共享内存动态调整
import os
cpu_count = os.cpu_count() or 4
shm_gb = 4  # 你设置的共享内存大小

optimal_workers = min(
    cpu_count - 1,  # 留一个核心给主进程
    int(shm_gb * 2),  # 每个 worker 约需 500MB
    8  # 最大值
)

train_args["workers"] = optimal_workers
```

### 2. Batch Size 调整

如果仍然遇到内存问题，尝试：

```python
# 减小 batch size
train_args["batch"] = -1  # 自动选择最优 batch size
# 或
train_args["batch"] = 8   # 手动设置较小的值
```

### 3. 缓存策略

```python
train_args["cache"] = False  # 禁用缓存以节省内存
# 或
train_args["cache"] = "disk"  # 使用磁盘缓存而非内存缓存
```

## 总结

**最简单有效的解决方案**：在 `docker-compose.gpu.yml` 中添加 `shm_size: '4gb'`

这个配置会为容器分配足够的共享内存，彻底解决 PyTorch DataLoader 的多进程数据加载问题。

## 相关文档

- [Docker Shared Memory Configuration](https://docs.docker.com/compose/compose-file/#shm_size)
- [PyTorch DataLoader Workers](https://pytorch.org/docs/stable/data.html#torch.utils.data.DataLoader)
- [Ultralytics Training Arguments](https://docs.ultralytics.com/modes/train/#arguments)

