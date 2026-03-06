"""
Data collection API endpoint (for remote clients)
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.core.database import get_db
from app.core.config import settings
from app.models import ImageSource
from app.schemas.schemas import AnnotationCreate, ImageUploadResponse, ClientImageUpload
from app.services import DatasetService
from app.utils import allowed_image
import json

router = APIRouter(prefix="/collect", tags=["data-collection"])


def verify_client_token(x_api_token: Optional[str] = Header(None)):
    """Verify client API token for remote data collection"""
    if not x_api_token or x_api_token != settings.CLIENT_API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing API token")
    return x_api_token


@router.post("/upload", response_model=ImageUploadResponse, summary="Client image upload with token auth")
async def client_upload_image(
    dataset_id: str = Form(...),
    file: UploadFile = File(...),
    annotations_json: Optional[str] = Form(None),
    source_url: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    _token: str = Depends(verify_client_token),
):
    """
    Remote client uploads a single image to the specified dataset.
    Requires X-Api-Token header.
    """
    dataset = await DatasetService.get_dataset(db, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if not allowed_image(file.filename):
        raise HTTPException(status_code=422, detail=f"File type not allowed: {file.filename}")

    file_data = await file.read()
    if len(file_data) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File too large")

    anns = None
    if annotations_json:
        try:
            raw = json.loads(annotations_json)
            anns = [AnnotationCreate(**a).model_dump() for a in raw]
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid annotations JSON")

    image = await DatasetService.save_uploaded_image(
        db=db,
        dataset_id=dataset_id,
        file_data=file_data,
        original_filename=file.filename,
        source=ImageSource.CLIENT,
        source_url=source_url,
        annotations=anns,
    )

    if not image:
        raise HTTPException(status_code=500, detail="Failed to save image")

    await db.commit()
    return ImageUploadResponse(
        id=image.id,
        filename=image.filename,
        dataset_id=dataset_id,
        width=image.width,
        height=image.height,
        file_size=image.file_size,
    )


@router.post("/batch-upload", summary="Client batch image upload")
async def client_batch_upload(
    dataset_id: str = Form(...),
    files: List[UploadFile] = File(...),
    annotations_json: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    _token: str = Depends(verify_client_token),
):
    """
    Remote client uploads multiple images. annotations_json is a JSON array
    where each element is a list of annotations for the corresponding image.
    """
    dataset = await DatasetService.get_dataset(db, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    annotations_list = None
    if annotations_json:
        try:
            annotations_list = json.loads(annotations_json)
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid annotations JSON")

    results = []
    errors = []

    for idx, file in enumerate(files):
        if not allowed_image(file.filename):
            errors.append({"filename": file.filename, "error": "not allowed file type"})
            continue
        file_data = await file.read()
        anns = None
        if annotations_list and idx < len(annotations_list):
            raw = annotations_list[idx]
            if raw:
                anns = [AnnotationCreate(**a).model_dump() for a in raw]
        try:
            image = await DatasetService.save_uploaded_image(
                db=db,
                dataset_id=dataset_id,
                file_data=file_data,
                original_filename=file.filename,
                source=ImageSource.CLIENT,
                annotations=anns,
            )
            if image:
                results.append({"id": image.id, "filename": image.filename})
        except Exception as e:
            errors.append({"filename": file.filename, "error": str(e)})

    await db.commit()
    return {
        "success": True,
        "uploaded": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors,
    }


@router.get("/datasets", summary="List datasets (for client to choose)")
async def list_datasets_for_client(
    db: AsyncSession = Depends(get_db),
    _token: str = Depends(verify_client_token),
):
    """Returns minimal dataset list for clients to select target dataset"""
    from app.services import DatasetService
    datasets, total = await DatasetService.list_datasets(db, skip=0, limit=100)
    return {
        "datasets": [{"id": d.id, "name": d.name, "classes": d.classes} for d in datasets]
    }
