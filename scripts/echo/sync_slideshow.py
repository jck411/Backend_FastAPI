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


def get_album_data(url: str, landscape_only: bool = True) -> list[dict]:
    """Fetch and parse the shared album page to extract photo data.

    Returns a list of dicts with keys: url, width, height.
    If landscape_only is True, only photos wider than they are tall are returned.
    """

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
    photo_entries = []

    # Find all lh3.googleusercontent.com URLs with photo data
    # These are typically in format: ["https://lh3.googleusercontent.com/pw/...",width,height]
    pattern = r'\["(https://lh3\.googleusercontent\.com/pw/[^"]+)"(?:,(\d+),(\d+))?'
    matches = re.findall(pattern, html)

    for match in matches:
        photo_url = match[0]
        width = int(match[1]) if match[1] else 0
        height = int(match[2]) if match[2] else 0
        if photo_url and "/pw/" in photo_url:
            # Clean up the URL (remove escape characters)
            photo_url = photo_url.replace("\\u003d", "=").replace("\\u0026", "&")
            photo_entries.append({"url": photo_url, "width": width, "height": height})

    # Deduplicate while preserving order
    seen = set()
    unique_entries = []
    for entry in photo_entries:
        # Use base URL without size params for deduplication
        base = entry["url"].split("=")[0]
        if base not in seen:
            seen.add(base)
            unique_entries.append(entry)

    print(f"Found {len(unique_entries)} unique photos in album")

    # Filter to landscape-only if requested
    if landscape_only:
        landscape = [e for e in unique_entries if e["width"] > e["height"] and e["width"] > 0]
        skipped = len(unique_entries) - len(landscape)
        print(f"🖼️  Landscape filter: keeping {len(landscape)}, skipped {skipped} portrait/square/unknown")
        return landscape

    return unique_entries


def download_photo(photo_url: str, index: int) -> Path | None:
    """Download a photo and save it to the cache."""

    # Echo Show 5 screen is 960x480 (2:1 aspect) - use 1024x512 to match screen aspect
    # This matches screen aspect ratio perfectly and optimizes memory usage
    # =w1024-h512 requests exact size, Google Photos will scale/crop appropriately
    if "=" not in photo_url:
        download_url = f"{photo_url}=w1024-h512"
    else:
        # Replace any existing size params
        base = photo_url.split("=")[0]
        download_url = f"{base}=w1024-h512"

    # Generate filename from URL hash
    url_hash = hashlib.md5(photo_url.encode()).hexdigest()[:16]
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


def cleanup_all_photos():
    """Remove all existing photos from the cache before a fresh sync."""
    photos = list(CACHE_DIR.glob("photo_*.jpg"))
    if photos:
        for photo in photos:
            photo.unlink()
        print(f"  Cleared {len(photos)} old photos from cache")


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
    print(f"Mode: {'All orientations' if INCLUDE_PORTRAIT else 'Landscape only'}")
    print("=" * 50)

    # Get photo entries from the album
    try:
        photo_entries = get_album_data(
            SHARED_ALBUM_URL, landscape_only=not INCLUDE_PORTRAIT
        )
    except Exception as e:
        print(f"Error fetching album: {e}")
        sys.exit(1)

    if not photo_entries:
        print("No photos found in album!")
        sys.exit(1)

    # Clear old photos before downloading fresh set
    print("\nClearing old photo cache...")
    cleanup_all_photos()

    # Download the latest photos
    limit = min(MAX_PHOTOS, len(photo_entries))
    print(f"\nDownloading up to {limit} landscape photos...")

    downloaded = 0
    for i, entry in enumerate(photo_entries[:limit]):
        result = download_photo(entry["url"], i)
        if result:
            downloaded += 1

    # Cleanup old photos beyond limit
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
    parser.add_argument(
        "--include-portrait",
        action="store_true",
        default=False,
        help="Include portrait and square photos (default: landscape only)",
    )
    args = parser.parse_args()

    # Determine max photos: CLI arg > settings > default
    if args.max_photos is not None:
        MAX_PHOTOS = args.max_photos
    else:
        MAX_PHOTOS = get_max_photos_from_settings()

    INCLUDE_PORTRAIT = args.include_portrait

    print(f"🖼️  Limiting to {MAX_PHOTOS} photos for optimal memory usage")
    if not INCLUDE_PORTRAIT:
        print("📐 Landscape-only mode (use --include-portrait to override)")

    main()
