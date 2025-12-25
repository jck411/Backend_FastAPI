#!/usr/bin/env python3
"""Migrate existing profile.json to separate profile.json (lean) and inventory.json.

Extracts software details (packages, services, defaults) to inventory.json
while keeping profile.json lean with only shell-control context.

Usage:
    uv run python scripts/migrate_profile_inventory.py /path/to/host_profiles/xps13
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def migrate_profile(host_dir: Path) -> None:
    """Migrate a single host profile directory."""
    profile_path = host_dir / "profile.json"
    inventory_path = host_dir / "inventory.json"

    if not profile_path.exists():
        print(f"  Skipping {host_dir.name}: no profile.json")
        return

    # Backup original
    backup_path = profile_path.with_suffix(".json.backup")
    if not backup_path.exists():
        shutil.copy2(profile_path, backup_path)
        print(f"  Created backup: {backup_path.name}")

    # Load current profile
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    software = profile.get("software", {})

    # Fields to move to inventory
    inventory_fields = ["packages", "enabled_services", "defaults", "snapshot_ts",
                        "kernel", "package_manager", "aur_helper", "os_base"]

    # Build inventory from software section
    inventory: dict = {}
    system_info: dict = {}
    for field in inventory_fields:
        if field in software:
            if field in ("kernel", "package_manager", "aur_helper", "os_base"):
                system_info[field] = software[field]
            else:
                inventory[field] = software[field]

    if system_info:
        inventory["system"] = system_info

    # Remove inventory fields from profile.software
    for field in inventory_fields:
        software.pop(field, None)

    # Flatten lean profile structure
    lean_profile: dict = {}

    # Copy hardware.host_id to top level
    if "hardware" in profile:
        hw = profile["hardware"]
        if "host_id" in hw:
            lean_profile["host_id"] = hw["host_id"]

    # Copy lean software fields to top level
    if "os" in software:
        lean_profile["os"] = software["os"]
    if "desktop" in software:
        lean_profile["desktop"] = software["desktop"]
    if "display_server" in software:
        lean_profile["display"] = software["display_server"]
    if "sudo" in software:
        lean_profile["sudo"] = software["sudo"]

    # Keep tools sections
    for key in ("wayland_tools", "apps", "waybar_toggles", "bookmarks"):
        if key in profile:
            lean_profile["tools" if key == "wayland_tools" else key] = profile[key]

    # Keep quirks/notes if present
    if "quirks" in profile:
        lean_profile["quirks"] = profile["quirks"]
    if "notes" in profile:
        lean_profile["quirks"] = profile["notes"]  # Rename notes -> quirks

    lean_profile["updated_at"] = profile.get("updated_at", "")

    # Save inventory.json
    if inventory:
        inventory_path.write_text(
            json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  Created inventory.json with {len(inventory)} fields")

    # Save lean profile.json
    profile_path.write_text(
        json.dumps(lean_profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  Updated profile.json ({len(json.dumps(lean_profile))} bytes)")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python migrate_profile_inventory.py <host_dir>")
        print("Example: python migrate_profile_inventory.py ~/GoogleDrive/host_profiles/xps13")
        sys.exit(1)

    host_dir = Path(sys.argv[1]).expanduser()
    if not host_dir.is_dir():
        print(f"Error: {host_dir} is not a directory")
        sys.exit(1)

    print(f"Migrating {host_dir}...")
    migrate_profile(host_dir)
    print("Done!")


if __name__ == "__main__":
    main()
