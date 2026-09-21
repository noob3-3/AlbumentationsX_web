"""License status and offline activation."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.license import (
    DEFAULT_PROJECT_NAME,
    activate,
    collect_hardware,
    current_license,
    machine_code,
)

router = APIRouter(prefix="/license", tags=["license"])


class ActivateRequest(BaseModel):
    activation_code: str = Field(..., min_length=1)


def _license_payload():
    info = current_license()
    hw = collect_hardware()
    return {
        "valid": info.valid,
        "message": info.message,
        "machine_code": info.machine_code or machine_code(),
        "expire_on": info.expire_on.isoformat() if info.expire_on else None,
        "project_name": DEFAULT_PROJECT_NAME,
        "hardware": {
            "mac": hw.display_mac() or "",
            "disk": hw.display_disk() or "",
            "guid": hw.display_guid() or "",
            "host": hw.host or "",
        },
    }


@router.get("", summary="Get license status and machine code")
async def get_license_status():
    return _license_payload()


@router.post("/activate", summary="Activate with offline code")
async def activate_license(data: ActivateRequest):
    info = activate(data.activation_code)
    if not info.valid:
        raise HTTPException(status_code=400, detail=info.message)
    return _license_payload()
