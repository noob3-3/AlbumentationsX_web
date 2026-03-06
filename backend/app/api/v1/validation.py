"""
Model validation API endpoints
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
import tempfile
import shutil
from pathlib import Path

from app.core.database import get_db
from app.schemas.schemas import (
    ModelValidationRequest,
    ModelValidationResponse,
)
from app.services.validation_service import ModelValidationService
from app.core.logging import logger

router = APIRouter(prefix="/validation", tags=["Model Validation"])


@router.post("/validate", response_model=ModelValidationResponse)
async def validate_models(
    file: UploadFile = File(...),
    model_ids: str = Form(...),  # JSON string of model IDs
    confidence: float = Form(0.5),
    iou: float = Form(0.45),
    db: AsyncSession = Depends(get_db),
):
    """
    验证多个模型在单张图片上的表现
    上传一张图片，指定多个模型ID，返回每个模型的检测结果
    """
    import json

    logger.info(f"Received validation request with model_ids: {model_ids}")

    # Parse model_ids
    try:
        model_id_list = json.loads(model_ids)
        logger.info(f"Parsed model_ids: {model_id_list}")

        if not isinstance(model_id_list, list):
            raise ValueError(f"model_ids must be a list, got {type(model_id_list)}")

        if len(model_id_list) == 0:
            raise ValueError("model_ids list is empty")

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse model_ids JSON: {model_ids}, error: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON in model_ids: {str(e)}")
    except Exception as e:
        logger.error(f"Invalid model_ids: {model_ids}, error: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid model_ids: {str(e)}")

    # Save uploaded file to temp location
    temp_dir = Path(tempfile.gettempdir()) / "ax_validation"
    temp_dir.mkdir(exist_ok=True, parents=True)
    temp_file = temp_dir / file.filename

    try:
        with temp_file.open("wb") as f:
            shutil.copyfileobj(file.file, f)

        logger.info(f"Validating {len(model_id_list)} models on image: {file.filename}")

        # Validate models
        result = await ModelValidationService.validate_models(
            db=db,
            model_ids=model_id_list,
            image_path=str(temp_file),
            confidence_threshold=confidence,
            iou_threshold=iou,
        )

        logger.info(f"Validation completed successfully")
        return result

    except Exception as e:
        logger.error(f"Model validation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean up temp file
        if temp_file.exists():
            temp_file.unlink()


@router.get("/history/{model_id}")
async def get_validation_history(
    model_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """获取模型的验证历史"""
    validations = await ModelValidationService.get_model_validations(
        db=db,
        model_id=model_id,
        limit=limit,
    )
    return validations

