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

## ❌ 3. No Atomic Profile/State Operations (NOT STARTED)

**Problem:** TOCTOU race condition - file could change between `exists()` check and `read_text()`.

```python
# Current vulnerable pattern:
if not path.exists():        # Check
    raise FileNotFoundError
payload = path.read_text()   # Use - file could have changed!
```

**Proposed Fix:**
```python
def _load_profile() -> dict:
    path = _get_profile_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(f"Host profile not found for id '{_get_host_id()}'")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Host profile is not valid JSON") from exc
    # ...
```

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

## ❌ 5. No Tool to List Available Hosts (NOT STARTED)

**Problem:** Users can't discover what hosts exist - only work with the one from `HOST_PROFILE_ENV`.

**Proposed Fix:**
```python
@mcp.tool("host_list")
async def host_list() -> str:
    """List all available host profiles."""

    host_root = _get_host_root()
    hosts = []

    for entry in host_root.iterdir():
        if entry.is_dir() and (entry / "profile.json").exists():
            hosts.append({
                "id": entry.name,
                "has_state": (entry / "state.json").exists(),
                "has_deltas": (entry / "deltas.log").exists(),
            })

    return json.dumps({
        "status": "ok",
        "active_host": _get_host_id(),
        "hosts": hosts,
    })
```

---

## Summary

| Issue | Status | Priority |
|-------|--------|----------|
| 1. Missing State Update Tool | ✅ Resolved | - |
| 2. Unused `_get_deltas_path` | ✅ Resolved | - |
| 3. TOCTOU Race Condition | ❌ Not Started | Low |
| 4. Path Traversal Vulnerability | ❌ Not Started | **High** |
| 5. No Host Listing Tool | ❌ Not Started | Medium |
