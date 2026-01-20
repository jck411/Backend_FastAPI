#!/bin/bash
# ============================================
# Echo Kiosk Device Setup Script
# ============================================
# Run this script after rooting an Amazon Echo
# to configure it for dedicated kiosk mode.
#
# Usage: ./setup_echo.sh [DEVICE_SERIAL]
#        If no serial provided, uses first connected device
#
# This script:
#   - Sets display to max brightness
#   - Disables lock screen and screen timeout
#   - Disables bloatware and unnecessary apps
#   - Disables system updates
#   - Optimizes for performance
#   - Sets up ADB port forwarding
#   - Launches Fully Kiosk
# ============================================

set -e

DEVICE_SERIAL="${1:-}"
ADB_CMD="adb"

if [ -n "$DEVICE_SERIAL" ]; then
    ADB_CMD="adb -s $DEVICE_SERIAL"
fi

echo "============================================"
echo "Echo Kiosk Setup Script (Dedicated Mode)"
echo "============================================"

# Check device connection
echo ""
echo "Checking device connection..."
if ! $ADB_CMD get-state &>/dev/null; then
    echo "❌ No device connected. Please connect via USB and enable ADB."
    exit 1
fi

SERIAL=$($ADB_CMD get-serialno)
echo "✅ Connected to device: $SERIAL"

# ============================================
# DISPLAY SETTINGS
# ============================================
echo ""
echo "[1/8] Setting display brightness to 100%..."
$ADB_CMD shell settings put system screen_brightness 255
$ADB_CMD shell settings put system screen_brightness_mode 0  # Disable auto-brightness
echo "✅ Brightness set to maximum (255)"

# ============================================
# DISABLE LOCK SCREEN
# ============================================
echo ""
echo "[2/8] Disabling lock screen..."
$ADB_CMD shell settings put secure lockscreen.disabled 1
$ADB_CMD shell settings put global device_provisioned 1
echo "✅ Lock screen disabled"

# ============================================
# KEEP SCREEN ON FOREVER
# ============================================
echo ""
echo "[3/8] Disabling screen timeout..."
# Stay awake while charging (USB + AC + Wireless = 7)
$ADB_CMD shell settings put global stay_on_while_plugged_in 7
# Set screen timeout to max (won't matter if stay_on is set, but just in case)
$ADB_CMD shell settings put system screen_off_timeout 2147483647
echo "✅ Screen will stay on indefinitely"

# ============================================
# DISABLE UPDATES & BACKGROUND SERVICES
# ============================================
echo ""
echo "[4/8] Disabling updates and background services..."

# Disable package verifier (speeds up installs, no Google checks)
$ADB_CMD shell settings put global package_verifier_enable 0
$ADB_CMD shell settings put global verifier_verify_adb_installs 0

# Disable usage stats collection
$ADB_CMD shell settings put global netstats_enabled 0

# Disable always-on WiFi scanning
$ADB_CMD shell settings put global wifi_scan_always_enabled 0

# Reduce animations for performance (0 = off)
$ADB_CMD shell settings put global window_animation_scale 0.5
$ADB_CMD shell settings put global transition_animation_scale 0.5
$ADB_CMD shell settings put global animator_duration_scale 0.5

echo "✅ Background services and updates disabled"

# ============================================
# DISABLE BLOATWARE APPS
# ============================================
echo ""
echo "[5/8] Disabling unnecessary apps..."

# Apps to disable - these waste RAM and CPU
BLOATWARE=(
    # LineageOS extras
    "org.lineageos.updater"          # System updater
    "org.lineageos.recorder"         # Screen recorder
    "org.lineageos.eleven"           # Music player
    "org.lineageos.etar"             # Calendar app
    "org.lineageos.jelly"            # Browser (we use Fully Kiosk)
    "org.lineageos.audiofx"          # Audio effects
    "org.lineageos.backgrounds"      # Wallpapers
    "org.lineageos.setupwizard"      # Setup wizard

    # Android apps we don't need
    "com.android.camera2"            # Camera
    "com.android.gallery3d"          # Gallery
    "com.android.calculator2"        # Calculator
    "com.android.deskclock"          # Clock/alarms
    "com.android.contacts"           # Contacts
    "com.android.calendar"           # Calendar
    "com.android.email"              # Email
    "com.android.launcher3"          # Default launcher
    "com.android.documentsui"        # File manager
    "com.android.dreams.basic"       # Screensaver
    "com.android.dreams.phototable"  # Photo screensaver
    "com.android.wallpaper.livepicker" # Live wallpaper
    "com.android.wallpapercropper"   # Wallpaper tools
    "com.android.printspooler"       # Printing
    "com.android.bips"               # Print service
    "com.android.printservice.recommendation" # Print recommendations
    "com.android.egg"                # Easter egg
    "com.android.traceur"            # System tracing
    "com.android.soundpicker"        # Sound picker
    "com.android.storagemanager"     # Storage manager
    "com.android.bookmarkprovider"   # Bookmarks

    # Backup services (not needed for kiosk)
    "com.stevesoltys.seedvault"      # Backup app
    "com.android.wallpaperbackup"    # Wallpaper backup
    "org.calyxos.backup.contacts"    # Contact backup

    # Communication we don't need
    "com.android.mms.service"        # MMS
    "com.android.smspush"            # SMS push
    "com.android.phone"              # Phone app
    "com.android.providers.telephony" # Telephony
    "com.android.server.telecom"     # Telecom
    "com.android.simappdialog"       # SIM dialog
    "com.android.companiondevicemanager" # Companion devices
)

DISABLED_COUNT=0
for app in "${BLOATWARE[@]}"; do
    if $ADB_CMD shell pm disable-user --user 0 "$app" 2>/dev/null | grep -q "disabled"; then
        DISABLED_COUNT=$((DISABLED_COUNT + 1))
    fi
done
echo "✅ Disabled $DISABLED_COUNT bloatware apps"

# ============================================
# KILL BACKGROUND PROCESSES
# ============================================
echo ""
echo "[6/8] Killing unnecessary background processes..."

# Force stop apps that might be running
PROCESSES_TO_KILL=(
    "org.lineageos.updater"
    "com.android.launcher3"
    "com.android.systemui.plugin.globalactions.wallet"
)

for proc in "${PROCESSES_TO_KILL[@]}"; do
    $ADB_CMD shell am force-stop "$proc" 2>/dev/null || true
done
echo "✅ Background processes terminated"

# ============================================
# ADB REVERSE PORT FORWARDING
# ============================================
echo ""
echo "[7/8] Setting up ADB reverse port forwarding..."
$ADB_CMD reverse tcp:5174 tcp:5174  # Kiosk UI
$ADB_CMD reverse tcp:8000 tcp:8000  # Backend API
echo "✅ Port forwarding established:"
echo "   - localhost:5174 → Kiosk UI"
echo "   - localhost:8000 → Backend API"

# ============================================
# GRANT FULLY KIOSK PERMISSIONS
# ============================================
echo ""
echo "[8/9] Granting Fully Kiosk permissions..."
$ADB_CMD shell pm grant de.ozerov.fully android.permission.RECORD_AUDIO
$ADB_CMD shell pm grant de.ozerov.fully android.permission.CAMERA 2>/dev/null || true
$ADB_CMD shell pm grant de.ozerov.fully android.permission.ACCESS_FINE_LOCATION 2>/dev/null || true
echo "✅ Microphone and other permissions granted"

# ============================================
# LAUNCH FULLY KIOSK
# ============================================
echo ""
echo "[9/9] Launching Fully Kiosk Browser..."
$ADB_CMD shell am start -n de.ozerov.fully/.MainActivity \
    -a android.intent.action.VIEW \
    -d "https://localhost:5174"
echo "✅ Fully Kiosk launched with kiosk URL"

# ============================================
# SUMMARY
# ============================================
echo ""
echo "============================================"
echo "✅ Setup Complete!"
echo "============================================"
echo ""
echo "Device: $SERIAL"
echo ""
echo "Settings applied:"
echo "  • Brightness: 100% (auto-brightness OFF)"
echo "  • Lock screen: Disabled"
echo "  • Screen timeout: Disabled (stays on forever)"
echo "  • System updates: Disabled"
echo "  • Bloatware: $DISABLED_COUNT apps disabled"
echo "  • Animations: Reduced for performance"
echo "  • Microphone: Permission granted"
echo "  • ADB reverse: 5174, 8000"
echo "  • Fully Kiosk: https://localhost:5174"
echo ""
echo "NOTE: Port forwarding resets on device reboot."
echo "      Re-run this script after reboot."
echo "============================================"
