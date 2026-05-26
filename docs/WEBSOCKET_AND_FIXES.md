# WebSocket Training Progress Fix

## Problem

训练任务启动后，WebSocket只发送了 `training_started` 消息，但后续的 `training_progress` 和 `validation_metrics` 消息没有发送。

**症状:**
```
训练在执行，但是websocket就发了{"type": "training_started", "job_id": "ed304673-afaa-4c80-8090-08d658207a82", "message": "Training started"}，后面再没发过
```

日志显示训练正在进行:
```
| 2026-03-05 08:41:41 | INFO     | app.services.annotation_service:auto_annotate_images:221 - Processing image 105/270: aug2_Acura_038_e89870e7_526b2a50.jpg
| 2026-03-05 08:41:42 | INFO     | app.services.annotation_service:auto_annotate_images:221 - Processing image 106/270: aug0_Acura_039_5b026a73_13761575.jpg
```

## Root Cause

训练服务在**线程池**中执行同步的YOLO训练，使用 `asyncio.run_coroutine_threadsafe()` 来调度WebSocket消息发送。

**问题在于:**

1. 训练函数 `_execute_training` 在线程池中运行
2. 该线程创建了**自己的事件循环** (`asyncio.new_event_loop()`)
3. 回调函数中使用 `asyncio.get_event_loop()` 获取的是**线程本地的事件循环**
4. WebSocket消息被调度到**线程的事件循环**，而不是**FastAPI主事件循环**
5. 线程的事件循环在完成后立即关闭，未处理的消息丢失

**对比annotation_service（工作正常）:**
- 标注服务直接在异步上下文中运行
- WebSocket消息直接使用 `await ws_manager.send_message()` 发送
- 无需跨线程调度

## Solution

**核心修改:** 将FastAPI的**主事件循环**引用传递给训练函数，确保WebSocket消息在正确的事件循环中调度。

### Changes Made

#### 1. `TrainingService.run_training_job` - 传递主事件循环

```python
@staticmethod
async def run_training_job(job_id: str):
    """Run training in a thread pool (YOLO training is synchronous)"""
    loop = asyncio.get_event_loop()  # Get main FastAPI event loop
    # Pass the main event loop to the training function
    await loop.run_in_executor(None, _run_training_sync, job_id, loop)
```

#### 2. `_run_training_sync` - 接收并传递主事件循环

```python
def _run_training_sync(job_id: str, main_loop):
    """Synchronous training function (runs in thread pool)"""
    # ...
    async def _async_wrapper():
        BackgroundSessionLocal = create_background_session_maker()
        async with BackgroundSessionLocal() as db:
            try:
                # Pass the main loop to the execution function
                await _execute_training(db, job_id, main_loop)
            except Exception as e:
                # ...
```

#### 3. `_execute_training` - 使用主事件循环调度WebSocket消息

```python
async def _execute_training(db: AsyncSession, job_id: str, main_loop):
    """Execute YOLO training"""
    # ...
    
    # REMOVED: current_loop = asyncio.get_event_loop()
    # This was getting the thread's local event loop!
    
    def on_train_epoch_end(trainer):
        # ...
        
        # Schedule coroutines on the MAIN event loop
        asyncio.run_coroutine_threadsafe(_update_db(), main_loop)
        asyncio.run_coroutine_threadsafe(_send_ws(), main_loop)
    
    def on_val_end(validator):
        # ...
        asyncio.run_coroutine_threadsafe(_send_val_ws(), main_loop)
```

## Technical Details

### Event Loop Isolation

- **主线程 (FastAPI):** 运行主事件循环，处理HTTP请求和WebSocket连接
- **工作线程 (Training):** 在线程池中执行，创建独立的事件循环

### asyncio.run_coroutine_threadsafe()

此函数用于从**另一个线程**向**目标事件循环**调度协程:

```python
future = asyncio.run_coroutine_threadsafe(coro, target_loop)
```

- `coro`: 要执行的协程
- `target_loop`: 目标事件循环（必须是正确的循环！）
- 返回 `concurrent.futures.Future`，可以等待结果

### Why It Was Failing

```python
# OLD CODE (错误):
current_loop = asyncio.get_event_loop()  # 获取线程本地循环
asyncio.run_coroutine_threadsafe(_send_ws(), current_loop)  # 调度到错误的循环
```

线程本地循环在 `loop.close()` 时立即关闭，未执行的协程被丢弃。

```python
# NEW CODE (正确):
asyncio.run_coroutine_threadsafe(_send_ws(), main_loop)  # 调度到主循环
```

主循环持续运行，确保消息被发送。

## Testing

启动训练任务后，应该看到以下WebSocket消息:

1. ✅ `training_started` - 训练开始
2. ✅ `training_progress` - 每个epoch结束后
3. ✅ `validation_metrics` - 验证完成后
4. ✅ `training_complete` - 训练完成

## Related Files

- `backend/app/services/training_service.py` - 主要修复
- `backend/app/core/websocket.py` - WebSocket管理器
- `backend/app/api/v1/training.py` - 训练API端点
- `backend/app/api/v1/websockets.py` - WebSocket端点

## References

- [asyncio - Event Loop](https://docs.python.org/3/library/asyncio-eventloop.html)
- [asyncio.run_coroutine_threadsafe](https://docs.python.org/3/library/asyncio-task.html#asyncio.run_coroutine_threadsafe)
- [Thread Safety in asyncio](https://docs.python.org/3/library/asyncio-dev.html#concurrency-and-multithreading)

