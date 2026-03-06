"""
WebSocket endpoint for real-time updates
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from loguru import logger

from app.core.websocket import ws_manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/training/{job_id}")
async def training_websocket(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for training job real-time progress"""
    await ws_manager.connect(websocket, job_id)
    try:
        while True:
            # Keep connection alive, wait for client messages (e.g. ping)
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, job_id)
        logger.info(f"Training WS disconnected for job {job_id}")


@router.websocket("/ws/augmentation/{job_id}")
async def augmentation_websocket(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for augmentation job real-time progress"""
    await ws_manager.connect(websocket, job_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, job_id)
        logger.info(f"Augmentation WS disconnected for job {job_id}")


@router.websocket("/ws/annotation/{job_id}")
async def annotation_websocket(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for auto-annotation job real-time progress"""
    await ws_manager.connect(websocket, job_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, job_id)
        logger.info(f"Annotation WS disconnected for job {job_id}")

