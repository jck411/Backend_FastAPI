# Echo Kiosk Setup and Boot Notes

This document captures the Echo kiosk setup steps, how to keep the device booting into Fully Kiosk, and the kiosk TTS segmentation settings that are now exposed.

## Prereqs

- Rooted Echo device (LineageOS-based)
- ADB access enabled
- Fully Kiosk Browser installed (`de.ozerov.fully`)
- Backend running on the host
- Kiosk UI available on `https://localhost:5174`

## One-time device setup (per Echo)

Run the setup script for each device. If multiple devices are connected, pass the serial.

```bash
adb devices
scripts/setup_echo.sh SERIAL
```

What the script applies:

- Max brightness, lock screen disabled, screen timeout disabled
- Background/update services disabled
- Recovery boot flags cleared (prevents update/recovery loops)
- Bloatware packages disabled
- ADB reverse port forwarding for kiosk + backend
- Fully Kiosk permissions granted
- Fully Kiosk set as HOME activity (best effort)
- Fully Kiosk launched with the kiosk URL

## Boot straight into Fully Kiosk

If the device reboots into recovery, it is usually due to a leftover OTA/recovery command or a boot flag in the cache. The setup script now clears these flags and attempts to disable recovery scripts on rooted devices.

Manual commands (if you need to run them again):

```bash
adb -s SERIAL shell 'rm -f /cache/recovery/command /cache/recovery/last_log /cache/recovery/last_install'
adb -s SERIAL shell 'rm -f /data/cache/recovery/command /data/cache/recovery/last_log /data/cache/recovery/last_install'
```

If the device still boots into recovery:

- Confirm `org.lineageos.updater` is disabled (`adb shell pm list packages | rg updater`).
- Boot once into system and re-run `scripts/setup_echo.sh`.
- If recovery persists, the OS image may be applying updates on boot; reflash the system image or remove the update trigger if present in `/system/etc/install-recovery.sh` (root required).

Fully Kiosk should come up on boot as long as it is the HOME activity. The script attempts to set this automatically. If it does not stick, open Fully Kiosk settings on the device and enable:

- Start on boot
- Set as default launcher / HOME
- Kiosk mode (optional, locks down navigation)

## Reboots and port forwarding

ADB reverse port forwarding does not persist across reboots.

After reboot:

```bash
adb -s SERIAL reverse tcp:5174 tcp:5174
adb -s SERIAL reverse tcp:8000 tcp:8000
```

## Kiosk TTS segmentation settings

The kiosk UI now exposes the minimum first-phrase length and segmentation logging toggle. These settings live in `src/backend/data/clients/kiosk/tts.json` and are editable in the kiosk settings modal:

- **Minimum first phrase length** (`first_phrase_min_chars`): floor before the first phrase can emit.
- **Segmentation logging** (`segmentation_logging_enabled`): logs when the 0.25s fallback timer triggers.

Segmentation behavior:

- Waits until `first_phrase_min_chars` is reached.
- Tries to split on delimiters or whitespace.
- If no boundary appears within 0.25s, it emits the buffered phrase to minimize latency.

## What works

- Kiosk TTS segmentation settings in the UI (including minimum first phrase length).
- Logging toggle for segmentation fallback events.
- Echo setup via `scripts/setup_echo.sh` for brightness/lock/updates/bloatware/permissions.
- Auto-launch of Fully Kiosk and kiosk URL after setup.

