#!/usr/bin/env python3
"""Migration script: Convert mcp_servers.json to use client_enabled dict.

This script migrates the MCP server configuration from the legacy format
(separate kiosk_enabled/frontend_enabled booleans) to the new format
(client_enabled: dict[str, bool]).

Usage:
    cd /home/human/REPOS/Backend_FastAPI
    source .venv/bin/activate
    python scripts/migrate_mcp_to_client_enabled.py
"""

import json
import shutil
from datetime import datetime
from pathlib import Path


def migrate_mcp_servers(path: Path) -> bool:
    """Migrate a single mcp_servers.json file to use client_enabled.

    Returns True if migration was performed, False if already migrated.
    """
    if not path.exists():
        print(f"  File does not exist: {path}")
        return False

    content = path.read_text(encoding="utf-8")
    data = json.loads(content)

    servers = data.get("servers", [])
    if not servers:
        print(f"  No servers found in: {path}")
        return False

    # Check if already migrated (first server has client_enabled)
    if "client_enabled" in servers[0]:
        print(f"  Already migrated: {path}")
        return False

    # Create backup
    backup_path = path.with_suffix(".json.backup")
    shutil.copy2(path, backup_path)
    print(f"  Created backup: {backup_path}")

    # Migrate each server
    for server in servers:
        frontend_enabled = server.pop("frontend_enabled", True)
        kiosk_enabled = server.pop("kiosk_enabled", False)

        server["client_enabled"] = {
            "svelte": frontend_enabled,
            "kiosk": kiosk_enabled,
            "cli": frontend_enabled,  # CLI follows frontend by default
        }

    # Write migrated data
    migrated_content = json.dumps(data, indent=2, sort_keys=True) + "\n"
    path.write_text(migrated_content, encoding="utf-8")
    print(f"  Migrated: {path}")
    return True


def main():
    project_root = Path(__file__).resolve().parent.parent

    print(f"MCP Server Configuration Migration")
    print(f"{'=' * 40}")
    print(f"Project root: {project_root}")
    print(f"Time: {datetime.now().isoformat()}")
    print()

    # Main mcp_servers.json
    main_path = project_root / "data" / "mcp_servers.json"
    print(f"Processing main config:")
    migrate_mcp_servers(main_path)
    print()

    # Client-specific mcp_servers.json files (if any exist)
    clients_dir = project_root / "src" / "backend" / "data" / "clients"
    if clients_dir.exists():
        print(f"Processing client configs:")
        for client_dir in clients_dir.iterdir():
            if client_dir.is_dir():
                client_mcp_path = client_dir / "mcp_servers.json"
                if client_mcp_path.exists():
                    migrate_mcp_servers(client_mcp_path)

    print()
    print("Migration complete!")
    print()
    print("Next steps:")
    print("  1. Restart the backend server")
    print("  2. Test preset save/apply functionality")


if __name__ == "__main__":
    main()
