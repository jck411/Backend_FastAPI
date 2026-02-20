# Echo Kiosk Initial Setup

One-time device configuration for Echo Show kiosks: boot settings, bloatware removal, network mode, and TTS setup.

**For memory optimization after setup**, see [ECHO_DEVICE_SETUP.md](ECHO_DEVICE_SETUP.md).

## Prereqs

- Rooted Echo device (LineageOS-based)
- ADB access enabled (USB for initial setup)
- Fully Kiosk Browser installed (`de.ozerov.fully`)
- Backend running on server (LXC 111 at `192.168.1.111:8000`)
- Kiosk UI built and deployed to `src/backend/static/kiosk/`:
  ```bash
  scripts/echo/build_kiosk.sh build
  ```

## Network Modes

The setup script supports two modes:

| Mode | URL | Connection | Use Case |
|------|-----|------------|----------|
| **Production** (default) | `https://192.168.1.111:8000/kiosk/` | Direct LAN, no USB needed | Normal operation |
| **Development** (`--dev`) | `https://localhost:5174` | ADB reverse port forwarding | Local dev/testing |

Production mode enables ADB-over-WiFi so the USB cable can be removed after setup.

## One-time device setup (per Echo)

Run the setup script for each device. If multiple devices are connected, pass the serial.

```bash
adb devices

# Production mode (default) — connects to server on LAN
scripts/echo/setup_echo.sh [SERIAL]

# Development mode — uses ADB reverse port forwarding
scripts/echo/setup_echo.sh --dev [SERIAL]
```

What the script applies:

- Max brightness, lock screen disabled, screen timeout disabled
- Background/update services disabled
- Recovery boot flags cleared (prevents update/recovery loops)
- Bloatware packages disabled
- Fully Kiosk permissions granted
- Fully Kiosk set as HOME activity (best effort)
- **Production**: ADB-over-WiFi enabled, Fully Kiosk launched with LAN URL
- **Dev**: ADB reverse port forwarding, Fully Kiosk launched with localhost URL

## Boot straight into Fully Kiosk

### MT8163 recovery boot problem (Echo Show 5)

The Amazon Echo Show 5 uses a MediaTek MT8163 SoC whose bootloader (LK) defaults to TWRP recovery on dirty shutdown (power loss, abrupt unplug). Three things cause this:

1. **`persist.vendor.recovery_update=true`** — Tells the bootloader to prefer recovery. On a clean reboot the OS handles it, but on power loss the bootloader reads this flag before the OS starts and routes to TWRP.
2. **`/vendor/bin/install-recovery.sh`** — A vendor script that reflashes the stock recovery image on every boot (part of the recovery update mechanism).
3. **MT8163 boot_reason=4 behavior** — On watchdog/power-loss, the bootloader checks the recovery_update flag and if true, enters recovery instead of system.

The setup script now fixes all three automatically:
- Sets `persist.vendor.recovery_update=false`
- Renames `/vendor/bin/install-recovery.sh` to `.disabled` (requires root)
- Clears recovery command files in `/cache/recovery/` and `/data/cache/recovery/`

**This is a one-time fix per device** — the persist property and renamed file survive reboots.

### Manual fix (if needed)

```bash
adb root
adb shell setprop persist.vendor.recovery_update false
adb shell setprop persist.sys.recovery_update false
adb shell 'mount -o rw,remount / && mv /vendor/bin/install-recovery.sh /vendor/bin/install-recovery.sh.disabled'
adb shell 'rm -f /cache/recovery/command /data/cache/recovery/command'
```

### If recovery persists after the fix

- Confirm `org.lineageos.updater` is disabled: `adb shell pm list packages -d | grep updater`
- Check for stuck hardware buttons (`TW_HACKED_BL_BUTTON` in TWRP log means volume buttons can trigger recovery)
- As a last resort, reflash the boot image

Fully Kiosk should come up on boot as long as it is the HOME activity. The script attempts to set this automatically. If it does not stick, open Fully Kiosk settings on the device and enable:

- Start on boot
- Set as default launcher / HOME
- Kiosk mode (optional, locks down navigation)

## Reboots and reconnection

### Production mode

After a reboot, Fully Kiosk will auto-launch and connect to the server on LAN — no intervention needed as long as:
- Fully Kiosk is set as the default launcher/HOME
- WiFi reconnects automatically
- The backend is running at `192.168.1.111:8000`

To reconnect ADB after USB is removed:
```bash
adb connect <device-wifi-ip>:5555
```

### Development mode

ADB reverse port forwarding does not persist across reboots.

After reboot:
```bash
adb -s SERIAL reverse tcp:5174 tcp:5174
adb -s SERIAL reverse tcp:8000 tcp:8000
```

Or re-run the setup script:
```bash
scripts/echo/setup_echo.sh --dev SERIAL
```

## Memory optimization

After initial setup, run memory optimizations. See [ECHO_DEVICE_SETUP.md](ECHO_DEVICE_SETUP.md) for full details.

## Kiosk TTS segmentation settings

The kiosk UI now exposes the minimum first-phrase length and segmentation logging toggle. These settings live in `src/backend/data/clients/kiosk/tts.json` and are editable in the kiosk settings modal:

- **Minimum first phrase length** (`first_phrase_min_chars`): floor before the first phrase can emit.
- **Segmentation logging** (`segmentation_logging_enabled`): logs when the minimum is met and the segmenter is waiting for a delimiter.

Segmentation behavior:

- Waits until `first_phrase_min_chars` is reached.
- Splits on the first delimiter after the minimum is met.
- If no delimiter arrives, it emits everything at the end as a single phrase.

## What works

- Kiosk TTS segmentation settings in the UI (including minimum first phrase length).
- Logging toggle for waiting-on-delimiter events.
- Echo setup via `scripts/echo/setup_echo.sh` for brightness/lock/updates/bloatware/permissions.
- Auto-launch of Fully Kiosk and kiosk URL after setup.
