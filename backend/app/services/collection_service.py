"""
Data collection service - handles local file uploads and URL-based API collection
"""
import asyncio
import httpx
from pathlib import Path
from typing import List, Optional
from loguru import logger

from app.core.config import settings
from app.models import ImageSource
from app.schemas.schemas import AnnotationCreate


async def fetch_image_from_url(url: str, timeout: int = 30) -> Optional[bytes]:
    """Fetch image bytes from a URL"""
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if not any(t in content_type for t in ["image/", "application/octet-stream"]):
                logger.warning(f"URL {url} returned non-image content-type: {content_type}")
                # Still try to save it
            return response.content
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching {url}: {e.response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        return None


def extract_filename_from_url(url: str) -> str:
    """Extract a filename from a URL"""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    path = parsed.path
    filename = Path(path).name
    if not filename or "." not in filename:
        filename = "image.jpg"
    return filename


async def collect_from_urls(
    urls: List[str],
    dataset_service,
    db,
    dataset_id: str,
    annotations_per_image: Optional[List[Optional[List[AnnotationCreate]]]] = None,
) -> dict:
    """Collect images from a list of URLs concurrently"""
    results = {"success": [], "failed": []}

    async def fetch_and_save(url: str, idx: int):
        img_bytes = await fetch_image_from_url(url)
        if img_bytes is None:
            results["failed"].append({"url": url, "reason": "fetch_failed"})
            return

        filename = extract_filename_from_url(url)
        anns = None
        if annotations_per_image and idx < len(annotations_per_image):
            anns = annotations_per_image[idx]
            if anns:
                anns = [a.model_dump() for a in anns]

        try:
            image = await dataset_service.save_uploaded_image(
                db=db,
                dataset_id=dataset_id,
                file_data=img_bytes,
                original_filename=filename,
                source=ImageSource.API,
                source_url=url,
                annotations=anns,
            )
            if image:
                results["success"].append({"url": url, "image_id": image.id})
            else:
                results["failed"].append({"url": url, "reason": "save_failed"})
        except Exception as e:
            results["failed"].append({"url": url, "reason": str(e)})

    # Collect concurrently (limit concurrency to avoid overloading)
    semaphore = asyncio.Semaphore(5)

    async def limited_fetch(url, idx):
        async with semaphore:
            await fetch_and_save(url, idx)

    tasks = [limited_fetch(url, i) for i, url in enumerate(urls)]
    await asyncio.gather(*tasks)

    return results
