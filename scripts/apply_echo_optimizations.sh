#!/bin/bash
# Apply memory optimizations to Echo device via ADB
# Run this after device boot or when setting up a new Echo
#
# Usage: ./scripts/apply_echo_optimizations.sh [--reboot]

set -e

DEVICE_SERIAL="${ECHO_DEVICE_SERIAL:-}"

# Helper for ADB commands
adb_cmd() {
    if [ -n "$DEVICE_SERIAL" ]; then
        adb -s "$DEVICE_SERIAL" "$@"
    else
        adb "$@"
    fi
}

echo "=============================================="
echo "Echo Kiosk Memory Optimization Script"
echo "=============================================="

# Check ADB connection
echo ""
echo "Checking ADB connection..."
if ! adb_cmd get-state &>/dev/null; then
    echo "ERROR: No device connected. Connect via USB and enable USB debugging."
    exit 1
fi

DEVICE=$(adb_cmd shell getprop ro.product.model 2>/dev/null | tr -d '\r')
echo "Connected to: $DEVICE"

# Restart ADB as root
echo ""
echo "Requesting root access..."
adb_cmd root 2>/dev/null || true
sleep 2
adb_cmd wait-for-device

WHOAMI=$(adb_cmd shell whoami | tr -d '\r')
if [ "$WHOAMI" != "root" ]; then
    echo "WARNING: Not running as root ($WHOAMI). Some optimizations may fail."
    echo "Enable 'Rooted debugging' in Developer Options."
fi

# ============================================
# 1. Disable unnecessary packages
# ============================================
echo ""
echo "=== Disabling unnecessary packages ==="

PACKAGES_TO_DISABLE=(
    "org.lineageos.audiofx"           # Audio equalizer - not needed
    "com.android.providers.calendar"   # Calendar provider
    "com.android.camera2"              # Camera app
    "com.android.contacts"             # Contacts app
    "com.android.gallery3d"            # Gallery app
    "org.lineageos.jelly"              # Browser (using Fully Kiosk)
    "org.lineageos.eleven"             # Music player
    "org.lineageos.etar"               # Calendar app
    "org.lineageos.recorder"           # Voice recorder
    "com.android.bluetooth"            # Bluetooth
    "com.android.phone"                # Phone/dialer
    "com.android.mms.service"          # MMS
    "com.android.calculator2"          # Calculator
    "com.android.deskclock"            # Alarm/clock app
    "com.android.launcher3"            # Default launcher
)

for pkg in "${PACKAGES_TO_DISABLE[@]}"; do
    if adb_cmd shell pm list packages -e | grep -q "$pkg"; then
        echo "  Disabling: $pkg"
        adb_cmd shell pm disable-user --user 0 "$pkg" 2>/dev/null || true
    fi
done

# ============================================
# 2. Developer Options - Animation & Memory
# ============================================
echo ""
echo "=== Configuring Developer Options ==="

# Disable all animations
adb_cmd shell settings put global window_animation_scale 0
adb_cmd shell settings put global transition_animation_scale 0
adb_cmd shell settings put global animator_duration_scale 0
echo "  Animations: disabled"

# Limit background processes
adb_cmd shell settings put global background_process_limit 2
echo "  Background process limit: 2"

# Aggressively reclaim activity memory
adb_cmd shell settings put global always_finish_activities 1
echo "  Don't keep activities: enabled"

# Disable force MSAA (GPU memory savings)
adb_cmd shell settings put global force_msaa 0
echo "  Force 4x MSAA: disabled"

# ============================================
# 3. Display Settings
# ============================================
echo ""
echo "=== Configuring Display ==="

# Set brightness to 100% and disable auto-brightness
adb_cmd shell settings put system screen_brightness_mode 0
adb_cmd shell settings put system screen_brightness 255
echo "  Brightness: 100% (255/255)"
echo "  Auto-brightness: disabled"

# ============================================
# 4. GPU Rendering
# ============================================
echo ""
echo "=== Configuring GPU Rendering ==="

adb_cmd shell setprop debug.hwui.renderer skiagl
adb_cmd shell setprop debug.hwui.profile false
echo "  GPU renderer: skiagl"
echo "  GPU profiling: disabled"

# ============================================
# 4. Kernel Memory Parameters (requires root)
# ============================================
echo ""
echo "=== Tuning Kernel Memory Parameters ==="

if [ "$WHOAMI" = "root" ]; then
    # Reduce swap aggressiveness (default 60, lower = less swapping)
    adb_cmd shell "echo 40 > /proc/sys/vm/swappiness"
    echo "  Swappiness: 40 (was 60)"

    # Increase cache reclaim pressure (default 100, higher = more aggressive)
    adb_cmd shell "echo 150 > /proc/sys/vm/vfs_cache_pressure"
    echo "  VFS cache pressure: 150 (was 100)"

    # Lower dirty ratio for faster writeback
    adb_cmd shell "echo 10 > /proc/sys/vm/dirty_ratio"
    echo "  Dirty ratio: 10"
else
    echo "  SKIPPED: Requires root access"
fi

# ============================================
# 5. Force stop disabled packages
# ============================================
echo ""
echo "=== Force stopping disabled packages ==="

for pkg in "${PACKAGES_TO_DISABLE[@]}"; do
    adb_cmd shell am force-stop "$pkg" 2>/dev/null || true
done
echo "  Done"

# ============================================
# 6. Clear system caches
# ============================================
echo ""
echo "=== Clearing caches ==="

if [ "$WHOAMI" = "root" ]; then
    adb_cmd shell "sync && echo 3 > /proc/sys/vm/drop_caches"
    echo "  Dropped filesystem caches"
fi

# ============================================
# Report current state
# ============================================
echo ""
echo "=== Current Memory Status ==="
adb_cmd shell "cat /proc/meminfo | head -6"

echo ""
echo "=== Top Memory Consumers ==="
adb_cmd shell "ps -A -o RSS,NAME --sort=-rss | head -10"

# ============================================
# Optional reboot
# ============================================
if [ "$1" = "--reboot" ]; then
    echo ""
    echo "Rebooting device to apply all changes..."
    adb_cmd reboot
    echo "Device will restart. Run this script again after boot for kernel params."
else
    echo ""
    echo "=============================================="
    echo "Optimizations applied!"
    echo ""
    echo "NOTE: Some changes require a reboot to fully take effect."
    echo "Run with --reboot flag to reboot now, or manually reboot later."
    echo ""
    echo "IMPORTANT: Kernel params (swappiness, cache pressure) reset on reboot."
    echo "Run this script after each reboot, or add to Fully Kiosk's 'Run on Start'."
    echo "=============================================="
fi
