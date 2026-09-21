"""未激活时拦截训练、增强、验证、部署等算力功能。"""
from fastapi import HTTPException

from app.license import LicenseInfo, current_license

LICENSE_REQUIRED_DETAIL = "未授权：{message}。请先激活后再使用训练、增强、验证、部署等功能。"


def require_license() -> LicenseInfo:
    info = current_license()
    if not info.valid:
        raise HTTPException(
            status_code=403,
            detail=LICENSE_REQUIRED_DETAIL.format(message=info.message),
        )
    return info
