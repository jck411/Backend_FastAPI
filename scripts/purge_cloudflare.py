#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

from cloudflare_manager import CloudflareManager
from dotenv import load_dotenv


def resolve_zone_name(args: argparse.Namespace) -> str | None:
    return args.zone or os.getenv("CLOUDFLARE_ZONE")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Purge Cloudflare cache for a zone.",
    )
    parser.add_argument(
        "--zone",
        help="Cloudflare zone name (e.g. chat.jackshome.com). Falls back to CLOUDFLARE_ZONE.",
    )
    parser.add_argument(
        "--urls",
        nargs="+",
        help="Optional list of full URLs to purge. If omitted, purges everything.",
    )
    args = parser.parse_args()

    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)

    zone_name = resolve_zone_name(args)

    try:
        cf = CloudflareManager()
        zones = cf.list_zones()
        if not zones:
            print("❌ No Cloudflare zones found for this account.")
            return 1

        if zone_name:
            zone = cf.get_zone(zone_name)
        elif len(zones) == 1:
            zone = zones[0]
            zone_name = zone["name"]
            print(f"ℹ️ Using only available zone: {zone_name}")
        else:
            print(
                "❌ Multiple zones found. Provide --zone or set CLOUDFLARE_ZONE in .env"
            )
            print("Available zones:")
            for item in zones:
                print(f"  - {item['name']}")
            return 1

        zone_id = zone["id"]
        zone_name = zone["name"]

        if args.urls:
            cf.purge_cache_urls(zone_id, args.urls)
            print(f"✅ Purged {len(args.urls)} URL(s) for {zone_name}")
        else:
            cf.purge_cache(zone_id, purge_everything=True)
            print(f"✅ Purged all cache for {zone_name}")

        return 0
    except Exception as error:
        print(f"❌ Cloudflare purge failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
