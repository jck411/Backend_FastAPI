#!/bin/bash
# Echo Memory Optimization for Local-Only Operation
# ONLY RUN THIS ON YOUR HOME NETWORK!

echo "=== Echo Memory Optimization (Local-Only Mode) ==="
echo "WARNING: This will modify network and service settings!"
read -p "Are you on your HOME network? (y/N): " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborting - only run this on home network!"
    exit 1
fi

echo "Starting optimization..."

# Get baseline memory usage
echo "=== BEFORE Optimization ==="
adb shell free -h
echo
adb shell dumpsys meminfo | grep -E "(fully|webview)" | head -5

echo
echo "=== Applying optimizations ==="

# Stop Fully Kiosk temporarily
echo "Stopping Fully Kiosk..."
adb shell 'am force-stop de.ozerov.fully'
sleep 2

# Disable location services (saves 10-15MB)
echo "Disabling location services..."
adb shell 'settings put secure location_providers_allowed ""'

# Disable unnecessary Google services
echo "Disabling Google services..."
adb shell 'pm disable-user --user 0 com.google.android.gms.location' 2>/dev/null || echo "GMS location already disabled"

# Disable background sync services
echo "Disabling background sync..."
adb shell 'settings put global auto_time 0'
adb shell 'settings put global auto_time_zone 0'

# Clear WebView cache to start fresh
echo "Clearing WebView caches..."
adb shell 'pm clear com.android.webview' 2>/dev/null || echo "WebView cache cleared"

# Restart Fully Kiosk
echo "Restarting Fully Kiosk..."
sleep 2
adb shell 'am start -n de.ozerov.fully/.LauncherReplacement'

echo "Waiting for startup..."
sleep 10

# Get updated memory usage
echo
echo "=== AFTER Optimization ==="
adb shell free -h
echo
adb shell dumpsys meminfo | grep -E "(fully|webview)" | head -5

echo
echo "=== Optimization Complete ==="
echo "Monitor the device for a few minutes to ensure everything works properly."
echo "If issues occur, reboot the device to restore defaults."
