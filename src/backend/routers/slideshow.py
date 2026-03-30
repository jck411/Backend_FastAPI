"""Slideshow router — proxies Immich API for landscape photos with people/pets."""

from __future__ import annotations

import hashlib
import logging
import os
import random
from datetime import date

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/slideshow", tags=["slideshow"])

IMMICH_URL = os.getenv("IMMICH_URL", "http://192.168.1.113:2283")
IMMICH_API_KEY = os.getenv("IMMICH_API_KEY", "")

# In-memory cache: refreshed once per day
_cache: dict = {"date": None, "assets": []}


def _immich_headers() -> dict[str, str]:
    return {"x-api-key": IMMICH_API_KEY, "Accept": "application/json"}


async def _fetch_landscape_assets(max_photos: int = 30) -> list[dict]:
    """Fetch landscape photos with people/pets from Immich using smart search."""
    fetch_size = max_photos * 2
    body = {
        "query": "people faces pets animals",
        "type": "IMAGE",
        "size": fetch_size,
        "withExif": True,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{IMMICH_URL}/api/search/smart",
            json=body,
            headers=_immich_headers(),
        )
        resp.raise_for_status()
        data = resp.json()

    items = data.get("assets", {}).get("items", [])

    # Filter landscape: width > height
    landscape = [
        {"id": a["id"]}
        for a in items
        if (a.get("exifInfo", {}).get("exifImageWidth") or a.get("width", 0))
        > (a.get("exifInfo", {}).get("exifImageHeight") or a.get("height", 0))
    ]

    return landscape[:max_photos]


async def _get_daily_assets() -> list[dict]:
    """Return cached asset list, refreshing once per day."""
    today = date.today()
    if _cache["date"] != today or not _cache["assets"]:
        try:
            _cache["assets"] = await _fetch_landscape_assets()
            _cache["date"] = today
            logger.info(
                "Refreshed Immich slideshow cache: %d photos", len(_cache["assets"])
            )
        except Exception:
            logger.exception("Failed to fetch photos from Immich")
            # Return stale cache if available
            if not _cache["assets"]:
                raise
    return _cache["assets"]


@router.get("/photos")
async def list_photos(daily_seed: bool = False) -> dict:
    """List available landscape photo asset IDs from Immich."""
    assets = await _get_daily_assets()
    ids = [a["id"] for a in assets]

    if daily_seed and ids:
        seed = int(hashlib.md5(str(date.today()).encode()).hexdigest(), 16)
        rng = random.Random(seed)
        rng.shuffle(ids)

    return {"photos": ids, "count": len(ids)}


@router.get("/status")
async def slideshow_status() -> dict:
    """Get slideshow status."""
    assets = await _get_daily_assets()
    return {
        "photo_count": len(assets),
        "source": IMMICH_URL,
    }


@router.get("/photo/{asset_id}")
async def get_photo(asset_id: str) -> Response:
    """Proxy an Immich asset thumbnail (preview size)."""
    # Validate asset_id is a UUID-like string
    if not asset_id or "/" in asset_id or "\\" in asset_id or ".." in asset_id:
        raise HTTPException(status_code=400, detail="Invalid asset ID")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{IMMICH_URL}/api/assets/{asset_id}/thumbnail",
            params={"size": "preview"},
            headers=_immich_headers(),
        )
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Photo not found")
        resp.raise_for_status()

    return Response(
        content=resp.content,
        media_type=resp.headers.get("content-type", "image/jpeg"),
        headers={
            "Cache-Control": "public, max-age=86400",
            "ETag": resp.headers.get("etag", ""),
        },
    )
