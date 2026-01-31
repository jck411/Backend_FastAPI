# Echo Kiosk Initial Setup

One-time device configuration for Echo Show kiosks: boot settings, port forwarding, bloatware removal, and TTS setup.

**For memory optimization after setup**, see [ECHO_DEVICE_SETUP.md](ECHO_DEVICE_SETUP.md).

## Prereqs

- Rooted Echo device (LineageOS-based)
- ADB access enabled
- Fully Kiosk Browser installed (`de.ozerov.fully`)
- Backend running on the host
- Kiosk UI built and available:
  ```bash
  # Build frontend to src/backend/static
  ./scripts/echo/build_kiosk.sh build

  # Or run dev server on https://0.0.0.0:5174
  ./scripts/echo/build_kiosk.sh serve
  ```

## One-time device setup (per Echo)

Run the setup script for each device. If multiple devices are connected, pass the serial.

```bash
adb devices
scripts/echo/setup_echo.sh SERIAL
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
- Boot once into system and re-run `scripts/echo/setup_echo.sh`.
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

Or re-run the setup script (which includes port forwarding):
```bash
scripts/echo/setup_echo.sh SERIAL
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
