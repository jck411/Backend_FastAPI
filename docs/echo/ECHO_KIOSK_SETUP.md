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
- IDME bootmode set to 0 (prevents recovery boot on power loss)
- Recovery boot flags cleared (prevents update/recovery loops)
- Bloatware packages disabled
- Fully Kiosk permissions granted
- Fully Kiosk set as HOME activity (best effort)
- **Production**: ADB-over-WiFi enabled, Fully Kiosk launched with LAN URL
- **Dev**: ADB reverse port forwarding, Fully Kiosk launched with localhost URL

## Boot straight into Fully Kiosk

### MT8163 recovery boot problem (Echo Show 5)

The Amazon Echo Show 5 uses a MediaTek MT8163 SoC whose bootloader (LK) boots to TWRP recovery instead of the OS on dirty shutdown (power loss, abrupt unplug).

**Root cause: IDME `bootmode=1`**

Amazon devices store configuration in IDME (Identity Manufacturing Data at End-of-life), located in the eMMC boot1 partition (`/dev/block/mmcblk0boot1`). The LK bootloader reads `bootmode` from IDME before the OS starts:
- `bootmode=0` → boot to system (normal)
- `bootmode=1` → boot to recovery (TWRP)

When the device was rooted/flashed with LineageOS, IDME `bootmode` was left at `1`. Clean reboots from the OS work because Android overrides boot routing, but on abrupt power loss the LK bootloader reads IDME directly and enters recovery.

You can check the current value: `adb shell cat /proc/idme/bootmode`

**Contributing factors** (also fixed by setup script):
- `persist.vendor.recovery_update=true` — secondary bootloader flag
- `/vendor/bin/install-recovery.sh` — vendor script that reflashes recovery on boot
- Recovery command files in `/cache/recovery/`

The setup script fixes all of these automatically, including patching IDME bootmode from 1→0 in the boot1 partition.

**This is a one-time fix per device** — IDME values persist across reboots and factory resets.

### Manual IDME bootmode fix

If the device is stuck in TWRP after power loss and you need to fix it manually:

```bash
# 1. From TWRP or the OS, get root ADB
adb root
adb wait-for-device

# 2. Check current bootmode
adb shell cat /proc/idme/bootmode   # Will show "1" if broken

# 3. Pull boot1 partition
adb shell 'dd if=/dev/block/mmcblk0boot1 of=/data/local/tmp/boot1.img bs=4096'
adb pull /data/local/tmp/boot1.img /tmp/boot1.img

# 4. Find and patch bootmode value (ASCII '1' → '0')
# The IDME structure: 16B field name + 4B size + 4B count + 4B flags + value
# "bootmode" field value is 28 bytes after the field name
python3 -c "
data = open('/tmp/boot1.img', 'rb').read()
idx = data.find(b'bootmode')
print(f'bootmode at offset 0x{idx:x}, value at 0x{idx+28:x}: {chr(data[idx+28])}')
"
# Patch: change byte at value offset from 0x31 ('1') to 0x30 ('0')
OFFSET=$(($(python3 -c "print(open('/tmp/boot1.img','rb').read().find(b'bootmode')+28)")))
printf '\x30' | dd of=/tmp/boot1.img bs=1 seek=$OFFSET conv=notrunc

# 5. Write back to device
adb push /tmp/boot1.img /data/local/tmp/boot1_patched.img
adb shell 'echo 0 > /sys/block/mmcblk0boot1/force_ro'
adb shell 'dd if=/data/local/tmp/boot1_patched.img of=/dev/block/mmcblk0boot1 bs=4096 && sync'

# 6. Also set the software flags
adb shell setprop persist.vendor.recovery_update false
adb shell setprop persist.sys.recovery_update false
adb shell 'mount -o rw,remount / && mv /vendor/bin/install-recovery.sh /vendor/bin/install-recovery.sh.disabled' 2>/dev/null
adb shell 'rm -f /cache/recovery/command /data/cache/recovery/command'

# 7. Reboot and verify
adb reboot
```

### If recovery persists after the fix

- Verify IDME bootmode: `adb shell cat /proc/idme/bootmode` (must be `0`)
- Confirm `org.lineageos.updater` is disabled: `adb shell pm list packages -d | grep updater`
- Check for stuck hardware buttons (`TW_HACKED_BL_BUTTON` in TWRP log means volume buttons can trigger recovery)

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
