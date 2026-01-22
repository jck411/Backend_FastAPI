"""Simple slideshow router - serves photos from local cache."""

from __future__ import annotations

import hashlib
import random
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/slideshow", tags=["slideshow"])

# Photo cache directory
PHOTOS_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data"
    / "slideshow"
    / "photos"
)
UPDATE_FILE = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data"
    / "slideshow_updated.txt"
)


def _get_photos() -> list[str]:
    """Get list of photo filenames in cache."""
    if not PHOTOS_DIR.exists():
        return []
    return [
        f.name
        for f in PHOTOS_DIR.iterdir()
        if f.is_file()
        and f.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    ]


@router.get("/photos")
async def list_photos(daily_seed: bool = False) -> dict:
    """
    List available photos.

    If daily_seed=True, returns a shuffled list that's consistent for the day.
    """
    photos = _get_photos()

    if daily_seed and photos:
        # Use today's date as seed for consistent daily shuffle
        seed = int(hashlib.md5(str(date.today()).encode()).hexdigest(), 16)
        rng = random.Random(seed)
        rng.shuffle(photos)

    # Include last update timestamp for cache busting
    last_updated = 0
    if UPDATE_FILE.exists():
        try:
            last_updated = int(UPDATE_FILE.read_text().strip())
        except (ValueError, IOError):
            pass

    return {"photos": photos, "count": len(photos), "last_updated": last_updated}


@router.get("/status")
async def slideshow_status() -> dict:
    """Get slideshow cache status and update information."""
    photos = _get_photos()

    last_updated = 0
    if UPDATE_FILE.exists():
        try:
            last_updated = int(UPDATE_FILE.read_text().strip())
        except (ValueError, IOError):
            pass

    # Calculate total cache size
    total_size = 0
    if PHOTOS_DIR.exists():
        for f in PHOTOS_DIR.iterdir():
            if f.is_file():
                total_size += f.stat().st_size

    return {
        "photo_count": len(photos),
        "cache_size_mb": round(total_size / (1024 * 1024), 1),
        "last_updated": last_updated,
        "cache_dir": str(PHOTOS_DIR),
        "estimated_memory_mb": f"{len(photos) * 0.8:.0f}-{len(photos) * 1.2:.0f}",
    }


@router.get("/photo/{filename}")
async def get_photo(filename: str) -> FileResponse:
    """Serve a photo by filename with aggressive caching."""
    # Prevent path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    photo_path = PHOTOS_DIR / filename

    if not photo_path.exists() or not photo_path.is_file():
        raise HTTPException(status_code=404, detail="Photo not found")

    # Get file stats for ETag
    file_stat = photo_path.stat()
    etag = hashlib.md5(
        f"{filename}-{file_stat.st_mtime}-{file_stat.st_size}".encode()
    ).hexdigest()

    return FileResponse(
        photo_path,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=3600",  # Cache for 1 hour only
            "ETag": f'"{etag}"',
        },
    )
