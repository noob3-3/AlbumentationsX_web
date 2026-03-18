"""
WebSocket connection manager for real-time training updates
Supports multi-process deployment using Redis pub/sub
"""
import json
import asyncio
from typing import Dict, Set, Optional
from fastapi import WebSocket
from loguru import logger
import redis
import redis.asyncio as aioredis


class ConnectionManager:
    """Manage WebSocket connections grouped by training job

    In multi-process deployment (e.g., Gunicorn with multiple workers):
    - Each worker process has its own ConnectionManager instance
    - WebSocket connections are stored locally in each worker
    - Messages are broadcast via Redis pub/sub to all workers
    - Each worker forwards messages to its local connections
    """

    def __init__(self):
        # job_id -> set of websocket connections (local to this worker process)
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # Redis client for pub/sub (async)
        self.redis: Optional[aioredis.Redis] = None
        self.pubsub: Optional[aioredis.client.PubSub] = None
        self.listener_task: Optional[asyncio.Task] = None
        # Sync Redis for publishing from worker threads (avoids "Future attached to different loop")
        self._redis_url: Optional[str] = None
        self._sync_redis: Optional[redis.Redis] = None
        self._initialized = False

    async def initialize(self, redis_url: str, channel: str = "websocket:messages"):
        """Initialize Redis connection for pub/sub"""
        if self._initialized:
            return

        try:
            self._redis_url = redis_url
            self.redis = await aioredis.from_url(redis_url, decode_responses=True)
            self.pubsub = self.redis.pubsub()
            await self.pubsub.subscribe(channel)
            self.channel = channel

            # Start listener task
            self.listener_task = asyncio.create_task(self._redis_listener())
            self._initialized = True
            logger.info(f"✅ WebSocket manager initialized with Redis pub/sub on channel '{channel}'")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Redis for WebSocket: {e}")
            logger.warning("⚠️ Falling back to single-process mode (messages won't reach other workers)")
            self.redis = None
            self.pubsub = None

    async def shutdown(self):
        """Shutdown Redis connection"""
        if self.listener_task:
            self.listener_task.cancel()
            try:
                await self.listener_task
            except asyncio.CancelledError:
                pass

        if self.pubsub:
            await self.pubsub.unsubscribe()
            await self.pubsub.close()

        if self.redis:
            await self.redis.close()

        if self._sync_redis:
            self._sync_redis.close()
            self._sync_redis = None

        logger.info("🔌 WebSocket manager shutdown complete")

    def publish_sync(self, job_id: str, message: dict) -> bool:
        """Publish message via Redis synchronously. Safe to call from any thread.

        Use this from worker threads (e.g. training callbacks) to avoid
        'Future attached to different loop' errors when publishing via async redis.
        """
        if not self._redis_url or not hasattr(self, "channel"):
            return False
        try:
            if self._sync_redis is None:
                self._sync_redis = redis.from_url(
                    self._redis_url, decode_responses=True
                )
            payload = json.dumps({"job_id": job_id, "message": message})
            self._sync_redis.publish(self.channel, payload)
            logger.debug(
                f"📡 Published '{message.get('type', 'unknown')}' to Redis for job {job_id}"
            )
            return True
        except Exception as e:
            logger.error(f"❌ Failed to publish to Redis (sync): {e}")
            return False

    async def _redis_listener(self):
        """Listen for messages from Redis and forward to local connections"""
        try:
            async for message in self.pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        job_id = data.get("job_id")
                        msg = data.get("message")

                        if job_id and msg:
                            # Forward to local connections only
                            await self._send_to_local_connections(job_id, msg)
                    except Exception as e:
                        logger.error(f"❌ Error processing Redis message: {e}")
        except asyncio.CancelledError:
            logger.info("🛑 Redis listener task cancelled")
        except Exception as e:
            logger.error(f"❌ Redis listener error: {e}")

    async def _send_to_local_connections(self, job_id: str, message: dict):
        """Send message to local WebSocket connections (same worker process)"""
        message_type = message.get('type', 'unknown')

        if job_id not in self.active_connections:
            # This worker doesn't have connections for this job, skip
            return

        if not self.active_connections[job_id]:
            return

        dead_connections = set()
        sent_count = 0
        connections_snapshot = list(self.active_connections[job_id])

        for connection in connections_snapshot:
            try:
                message_str = json.dumps(message)
                await connection.send_text(message_str)
                sent_count += 1
            except Exception as e:
                logger.error(f"❌ Failed to send WS message to job {job_id}: {e}")
                dead_connections.add(connection)

        # Clean up dead connections
        for conn in dead_connections:
            self.active_connections[job_id].discard(conn)

        if sent_count > 0:
            logger.info(f"📤 Sent '{message_type}' to {sent_count} local connection(s) for job {job_id}")

    async def connect(self, websocket: WebSocket, job_id: str):
        await websocket.accept()
        if job_id not in self.active_connections:
            self.active_connections[job_id] = set()
        self.active_connections[job_id].add(websocket)
        logger.info(f"✅ WebSocket connected for job {job_id} (local: {len(self.active_connections[job_id])} connections)")

    def disconnect(self, websocket: WebSocket, job_id: str):
        if job_id in self.active_connections:
            self.active_connections[job_id].discard(websocket)
            remaining = len(self.active_connections[job_id])
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]
                logger.info(f"🔌 WebSocket disconnected for job {job_id} (all local connections closed)")
            else:
                logger.info(f"🔌 WebSocket disconnected for job {job_id} ({remaining} local connections remaining)")
        else:
            logger.warning(f"⚠️ Tried to disconnect unknown job {job_id}")

    async def send_message(self, job_id: str, message: dict):
        """Send message to all connections for a job across all worker processes

        This publishes the message to Redis, which broadcasts it to all workers.
        Each worker will then forward the message to its local connections.
        """
        message_type = message.get('type', 'unknown')

        # Publish to Redis for all workers to receive
        if self.redis:
            try:
                payload = json.dumps({
                    "job_id": job_id,
                    "message": message
                })
                await self.redis.publish(self.channel, payload)
                logger.debug(f"📡 Published '{message_type}' to Redis for job {job_id}")
                return True
            except Exception as e:
                logger.error(f"❌ Failed to publish to Redis: {e}")
                # Fall back to local delivery

        # Fallback: send to local connections only (single-process mode)
        if job_id not in self.active_connections:
            logger.warning(f"⚠️ No WebSocket connections for job {job_id}, message '{message_type}' not sent")
            return False

        if not self.active_connections[job_id]:
            logger.warning(f"⚠️ Empty connection set for job {job_id}, message '{message_type}' not sent")
            return False

        await self._send_to_local_connections(job_id, message)
        return True

    async def broadcast(self, message: dict):
        """Broadcast to all connected clients across all workers"""
        if self.redis:
            try:
                payload = json.dumps({
                    "job_id": "*",  # Broadcast to all
                    "message": message
                })
                await self.redis.publish(self.channel, payload)
                return True
            except Exception as e:
                logger.error(f"❌ Failed to broadcast to Redis: {e}")

        # Fallback: local broadcast only
        for job_id in list(self.active_connections.keys()):
            await self._send_to_local_connections(job_id, message)

    def has_connections(self, job_id: str) -> bool:
        """Check if there are active connections for a job (local only)"""
        return job_id in self.active_connections and len(self.active_connections[job_id]) > 0

    def get_connection_count(self, job_id: str) -> int:
        """Get the number of active connections for a job (local only)"""
        if job_id in self.active_connections:
            return len(self.active_connections[job_id])
        return 0

    def get_active_jobs(self) -> list:
        """Get list of job IDs with active connections (local only)"""
        return list(self.active_connections.keys())


# Global instance
ws_manager = ConnectionManager()
