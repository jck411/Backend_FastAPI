# Echo Show Scripts

Scripts for managing Echo Show devices running LineageOS with Fully Kiosk Browser.

## Setup & Configuration

### `setup_echo.sh`
Initial device setup including brightness, bloatware removal, permissions, port forwarding, and Fully Kiosk launch.

```bash
./scripts/echo/setup_echo.sh SERIAL
```

**Run once per device** or when reconfiguring. See [ECHO_KIOSK_SETUP.md](../../docs/echo/ECHO_KIOSK_SETUP.md).

## Memory Optimization

### `apply_echo_optimizations.sh`
Comprehensive memory optimization including kernel parameters, GPU settings, and package disabling.

```bash
# First run (triggers reboot)
./scripts/echo/apply_echo_optimizations.sh --reboot

# After reboot (applies kernel params)
./scripts/echo/apply_echo_optimizations.sh
```

**Run after each device reboot** as kernel parameters reset. See [ECHO_DEVICE_SETUP.md](../../docs/echo/ECHO_DEVICE_SETUP.md).

### `disable_unused_features.sh`
Disable unnecessary Android packages to free memory.

### `optimize_webview_cache.sh`
Clear and optimize WebView cache memory usage.

### `optimize_photo_memory.py`
Optimize slideshow photo memory usage (part of sync pipeline).

### `optimize_echo_local_when_home.sh`
Additional optimizations for local network operation (disables location services, Google services, background sync).

## Memory Monitoring

### `check_echo_memory.sh`
Quick memory snapshot showing free, available, swap usage, and top processes.

```bash
./scripts/echo/check_echo_memory.sh
```

### `monitor_echo_memory.sh`
Continuous real-time memory monitoring (refreshes every 5 seconds).

```bash
./scripts/echo/monitor_echo_memory.sh
```

## Slideshow Management

### `sync_slideshow.py`
Download and sync photos from Google Photos album for kiosk slideshow.

```bash
# Use configured max photos from ui.json
./scripts/echo/sync_slideshow.py

# Override max photos
./scripts/echo/sync_slideshow.py --max-photos 20
```

### `sync_slideshow.sh`
Shell wrapper for cron/systemd automation of slideshow sync.

## Quick Reference

| Task | Command |
|------|---------|
| Initial setup | `./scripts/echo/setup_echo.sh SERIAL` |
| Memory optimization | `./scripts/echo/apply_echo_optimizations.sh` |
| Check memory | `./scripts/echo/check_echo_memory.sh` |
| Monitor memory | `./scripts/echo/monitor_echo_memory.sh` |
| Sync photos | `./scripts/echo/sync_slideshow.py` |

## Documentation

- [ECHO_DEVICE_SETUP.md](../../docs/echo/ECHO_DEVICE_SETUP.md) - Memory optimization guide
- [ECHO_KIOSK_SETUP.md](../../docs/echo/ECHO_KIOSK_SETUP.md) - Initial device configuration
- [README.md](../../docs/echo/README.md) - Echo documentation overview
