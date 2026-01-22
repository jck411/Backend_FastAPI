#!/usr/bin/env python3

"""
Optimize photo count for Echo device memory constraints
"""

import os
import sys
import json
from pathlib import Path

def get_photo_count():
    """Get current photo count from slideshow directory"""
    slideshow_dir = Path("/home/human/REPOS/Backend_FastAPI/data/slideshow")
    if slideshow_dir.exists():
        photos = list(slideshow_dir.glob("*.jpg")) + list(slideshow_dir.glob("*.jpeg")) + list(slideshow_dir.glob("*.png"))
        return len(photos)
    return 0

def recommend_photo_count():
    """Recommend optimal photo count based on memory constraints"""
    # Current state: 54MB free, need some buffer
    available_memory = 54  # MB
    safety_buffer = 20     # MB for system stability
    usable_memory = available_memory - safety_buffer
    
    # Average photo size in memory (compressed JPEG in browser)
    avg_photo_size = 0.8  # MB per photo
    
    recommended_count = int(usable_memory / avg_photo_size)
    return max(10, recommended_count)  # Minimum 10 photos

def main():
    current_count = get_photo_count()
    recommended = recommend_photo_count()
    
    print("📊 Echo Memory Optimization Analysis")
    print("=" * 40)
    print(f"Current photos: {current_count}")
    print(f"Recommended max: {recommended} photos")
    print(f"Memory needed: {recommended * 0.8:.1f}MB")
    print(f"Memory available: 34MB (with safety buffer)")
    
    if current_count > recommended:
        print(f"\n⚠️  RECOMMENDATION: Reduce to {recommended} photos")
        print("Options:")
        print("1. Keep only recent photos")
        print("2. Reduce photo resolution/quality")
        print("3. Use fewer photos in rotation")
    else:
        print(f"\n✅ Photo count is within memory limits")
    
    print(f"\nCurrent allocation:")
    print(f"• System: ~600MB")
    print(f"• WebView: 117MB") 
    print(f"• Photos (current): ~{current_count * 0.8:.1f}MB")
    print(f"• Free: 54MB")
    print(f"• Buffer needed: 20MB")

if __name__ == "__main__":
    main()