from fastapi import APIRouter

from app.api.v1 import datasets, augmentation, training, websockets, collection, annotation, deployment, project, validation, system, models

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(project.router)
api_router.include_router(datasets.router)
api_router.include_router(augmentation.router)
api_router.include_router(training.router)
api_router.include_router(models.router)
api_router.include_router(collection.router)
api_router.include_router(annotation.router)
api_router.include_router(deployment.router)
api_router.include_router(validation.router)
api_router.include_router(system.router)

# WebSocket routes (no prefix)
ws_router = APIRouter()
ws_router.include_router(websockets.router)
