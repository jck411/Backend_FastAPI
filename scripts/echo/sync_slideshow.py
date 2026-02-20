#!/usr/bin/env python3
"""
Sync photos from a public Google Photos shared album.
Downloads the latest N photos directly from the share link.
"""

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import httpx

# Configuration
SHARED_ALBUM_URL = "https://photos.app.goo.gl/n1VAf2qghCxX3FEr8"
DEFAULT_MAX_PHOTOS = 30  # Default for Echo device memory constraints
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / "slideshow" / "photos"
KIOSK_UI_SETTINGS_PATH = (
    PROJECT_ROOT / "src" / "backend" / "data" / "clients" / "kiosk" / "ui.json"
)

# Ensure cache directory exists
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_max_photos_from_settings() -> int:
    """Read slideshow_max_photos from kiosk UI settings, fallback to default."""
    try:
        if KIOSK_UI_SETTINGS_PATH.exists():
            data = json.loads(KIOSK_UI_SETTINGS_PATH.read_text())
            return data.get("slideshow_max_photos", DEFAULT_MAX_PHOTOS)
    except Exception as e:
        print(f"  Note: Could not read settings ({e}), using default")
    return DEFAULT_MAX_PHOTOS


def get_album_data(url: str) -> list[dict]:
    """Fetch and parse the shared album page to extract photo data."""

    print(f"Fetching album from: {url}")

    # Follow redirects to get the actual album page
    with httpx.Client(follow_redirects=True, timeout=30.0) as client:
        response = client.get(url)
        response.raise_for_status()
        html = response.text

    # Google Photos embeds photo data in a JavaScript array
    # Look for the data array in the page

    # Pattern to find image URLs in the page
    # Google Photos uses URLs like lh3.googleusercontent.com/...
    photo_urls = []

    # Find all lh3.googleusercontent.com URLs with photo data
    # These are typically in format: ["https://lh3.googleusercontent.com/pw/...",width,height]
    pattern = r'\["(https://lh3\.googleusercontent\.com/pw/[^"]+)"(?:,(\d+),(\d+))?'
    matches = re.findall(pattern, html)

    for match in matches:
        url = match[0]
        if url and "/pw/" in url:
            # Clean up the URL (remove escape characters)
            url = url.replace("\\u003d", "=").replace("\\u0026", "&")
            photo_urls.append(url)

    # Deduplicate while preserving order
    seen = set()
    unique_urls = []
    for url in photo_urls:
        # Use base URL without size params for deduplication
        base = url.split("=")[0]
        if base not in seen:
            seen.add(base)
            unique_urls.append(url)

    print(f"Found {len(unique_urls)} unique photos")
    return unique_urls


def download_photo(url: str, index: int) -> Path | None:
    """Download a photo and save it to the cache."""

    # Echo Show 5 screen is 960x480 (2:1 aspect) - use 1024x512 to match screen aspect
    # This matches screen aspect ratio perfectly and optimizes memory usage
    # =w1024-h512 requests exact size, Google Photos will scale/crop appropriately
    if "=" not in url:
        download_url = f"{url}=w1024-h512"
    else:
        # Replace any existing size params
        base = url.split("=")[0]
        download_url = f"{base}=w1024-h512"

    # Generate filename from URL hash
    url_hash = hashlib.md5(url.encode()).hexdigest()[:16]
    filename = f"photo_{index:03d}_{url_hash}.jpg"
    filepath = CACHE_DIR / filename

    # Skip if already exists
    if filepath.exists():
        return filepath

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.get(download_url)
            response.raise_for_status()

            # Save the image
            filepath.write_bytes(response.content)
            print(f"  Downloaded: {filename} ({len(response.content) // 1024}KB)")
            return filepath

    except Exception as e:
        print(f"  Failed to download: {e}")
        return None


def cleanup_old_photos(keep_count: int):
    """Remove old photos beyond the keep count."""
    photos = sorted(CACHE_DIR.glob("photo_*.jpg"))

    if len(photos) > keep_count:
        for photo in photos[keep_count:]:
            photo.unlink()
            print(f"  Removed old: {photo.name}")


def trigger_frontend_preload():
    """Notify frontend to preload the new photos."""
    print("\nTriggering frontend preload...")

    # Create a timestamp file to signal frontend refresh
    timestamp_file = PROJECT_ROOT / "data" / "slideshow_updated.txt"
    timestamp_file.write_text(f"{int(time.time())}\n")

    print("✅ Frontend will preload photos on next load")
    print("📱 Restart kiosk frontend or navigate to force preload")


def main():
    print("=" * 50)
    print("Google Photos Shared Album Sync")
    print("=" * 50)

    # Get photo URLs from the album
    try:
        photo_urls = get_album_data(SHARED_ALBUM_URL)
    except Exception as e:
        print(f"Error fetching album: {e}")
        sys.exit(1)

    if not photo_urls:
        print("No photos found in album!")
        sys.exit(1)

    # Download the latest photos
    limit = min(MAX_PHOTOS, len(photo_urls))
    print(f"\nDownloading up to {limit} photos...")

    downloaded = 0
    for i, url in enumerate(photo_urls[:limit]):
        result = download_photo(url, i)
        if result:
            downloaded += 1

    # Cleanup old photos
    print(f"\nCleaning up old photos (keeping {MAX_PHOTOS})...")
    cleanup_old_photos(MAX_PHOTOS)

    # Count total
    total = len(list(CACHE_DIR.glob("*.jpg")))
    print(f"\n✅ Sync complete! {total} photos in cache.")

    # Signal frontend to preload
    trigger_frontend_preload()

    # Memory optimization tip
    print("\n💾 Memory Impact:")
    print(f"   Photos cached: {total}")
    print(f"   Estimated memory when preloaded: ~{total * 0.8:.0f}MB (decoded bitmaps)")
    print("   Trade-off: Predictable memory usage for smooth slideshow")


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Sync photos from Google Photos shared album"
    )
    parser.add_argument(
        "--max-photos",
        type=int,
        default=None,
        help=f"Maximum number of photos to sync (default: from settings or {DEFAULT_MAX_PHOTOS})",
    )
    args = parser.parse_args()

    # Determine max photos: CLI arg > settings > default
    if args.max_photos is not None:
        MAX_PHOTOS = args.max_photos
    else:
        MAX_PHOTOS = get_max_photos_from_settings()

    print(f"🖼️  Limiting to {MAX_PHOTOS} photos for optimal memory usage")

    main()
