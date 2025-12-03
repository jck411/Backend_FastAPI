# Shell Control Server - Issue Tracker

## ✅ 1. Missing State Update Tool (RESOLVED)

**Problem:** `_save_state()` helper existed but no MCP tool exposed it. State was read-only.

**Solution Implemented:**
- Added `host_update_state` tool - merges updates into state with timestamp
- Added `host_update_profile` tool - merges updates into profile
- Added `_deep_merge()` - recursive merge with `None` = delete key
- Added `_append_delta()` - audit log to `deltas.log` (fixes issue #2)
- Added `_save_profile()` - atomic write for profile.json
- **Auto-snapshot system**: After package/service/default changes, state auto-updates with:
  - `packages`: Tracked apps by category (browsers, editors, terminals, etc.)
  - `defaults`: XDG defaults (browser, file_manager, text_editor, etc.)
  - `enabled_services`: Tracked systemd services

**Token cost:** ~114 tokens per snapshot

---

## ✅ 2. Unused `_get_deltas_path` (RESOLVED)

**Problem:** `_get_deltas_path()` returned `deltas.log` path but was never used.

**Solution Implemented:**
- `_append_delta()` now writes to `deltas.log` on every profile/state update
- Each entry is JSONL with: `ts`, `type`, `changes`, `reason`

---

## ✅ 3. No Atomic Profile/State Operations (RESOLVED)

**Problem:** TOCTOU race condition - file could change between `exists()` check and `read_text()`.

**Solution Implemented:**
- Changed `_load_profile()` and `_load_state()` to use EAFP pattern
- Removed `if not path.exists()` checks
- Now uses `try/except FileNotFoundError` directly on `read_text()`
- Eliminates the time gap between check and use

---

## ❌ 4. Missing Input Validation for host_id (NOT STARTED)

**Problem:** `_get_host_dir()` accepts any string. A malicious `host_id` like `../../../etc` could cause path traversal.

```python
# Current vulnerable code:
def _get_host_dir(host_id: str | None = None) -> Path:
    resolved_id = host_id or _get_host_id()
    host_dir = _get_host_root() / resolved_id  # No validation!
    host_dir.mkdir(parents=True, exist_ok=True)
    return host_dir
```

**Proposed Fix:**
```python
import re

_VALID_HOST_ID = re.compile(r"^[a-zA-Z0-9_-]+$")

def _get_host_dir(host_id: str | None = None) -> Path:
    resolved_id = host_id or _get_host_id()

    # Validate host_id to prevent path traversal
    if not _VALID_HOST_ID.match(resolved_id):
        raise ValueError(f"Invalid host_id: {resolved_id!r}. Must be alphanumeric with - or _")

    host_dir = _get_host_root() / resolved_id
    host_dir.mkdir(parents=True, exist_ok=True)
    return host_dir
```

---

## ✅ 5. No Tool to List Available Hosts (RESOLVED)

**Problem:** Users can't discover what hosts exist - only work with the one from `HOST_PROFILE_ENV`.

**Solution Implemented:**
- Added `host_list` tool - lists all hosts in host root directory
- Added `HOST_ROOT_PATH` env var to override default host location (e.g., GDrive sync folder)
- Returns: `active_host`, `host_root` path, and list of hosts with `has_profile`, `has_state`, `has_deltas` flags

---

## Summary

| Issue | Status | Priority |
|-------|--------|----------|
| 1. Missing State Update Tool | ✅ Resolved | - |
| 2. Unused `_get_deltas_path` | ✅ Resolved | - |
| 3. TOCTOU Race Condition | ✅ Resolved | - |
| 4. Path Traversal Vulnerability | ❌ Not Started | **High** |
| 5. No Host Listing Tool | ✅ Resolved | - |
