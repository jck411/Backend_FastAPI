#!/usr/bin/env python3
"""Test Cloudflare API to see the actual error"""

import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent / "scripts"))

from cloudflare_manager import CloudflareManager

try:
    cf = CloudflareManager()
    print("✅ CloudflareManager initialized")

    # Show which auth method is being used
    if hasattr(cf, "api_token") and cf.api_token:
        print("Auth method: API Token")
        print(f"Token ending: ...{cf.api_token[-10:]}")
    elif hasattr(cf, "api_key") and cf.api_key:
        print("Auth method: Global API Key")
        print(f"Email: {cf.email}")
        print(f"Key ending: ...{cf.api_key[-10:]}")

    print("\nAttempting to list zones...")
    zones = cf.list_zones()
    print(f"✅ Success! Found {len(zones)} zones")
    for zone in zones:
        print(f"  - {zone['name']}")
except Exception as e:
    print(f"\n❌ Error occurred: {e}")
    import traceback

    traceback.print_exc()
