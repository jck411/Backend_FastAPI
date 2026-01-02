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
PHOTOS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "slideshow" / "photos"


def _get_photos() -> list[str]:
    """Get list of photo filenames in cache."""
    if not PHOTOS_DIR.exists():
        return []
    return [
        f.name for f in PHOTOS_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp"}
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
    
    return {"photos": photos, "count": len(photos)}


@router.get("/photo/{filename}")
async def get_photo(filename: str) -> FileResponse:
    """Serve a photo by filename."""
    # Prevent path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    photo_path = PHOTOS_DIR / filename
    
    if not photo_path.exists() or not photo_path.is_file():
        raise HTTPException(status_code=404, detail="Photo not found")
    
    return FileResponse(
        photo_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},  # Cache for 1 day
    )
