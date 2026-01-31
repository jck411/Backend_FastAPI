# Echo Show 5 Memory Optimization - Experimental Improvements

Experimental and future optimizations to further reduce memory usage. For current baseline configuration and monitoring, see [ECHO_DEVICE_SETUP.md](ECHO_DEVICE_SETUP.md).

---

## Priority 1: Quick Wins (No Code Changes)

### 1.1 Disable Android Animations (~5-10MB GPU savings)
```bash
adb shell settings put global window_animation_scale 0
adb shell settings put global transition_animation_scale 0
adb shell settings put global animator_duration_scale 0
```
**Impact**: Reduces GPU memory allocation and rendering overhead.

### 1.2 Force GPU Rendering Mode
```bash
adb shell setprop debug.hwui.renderer skiagl
```
**Impact**: More efficient GPU memory usage on constrained devices.

### 1.3 Fully Kiosk Settings (Remote Access)
- **Settings > Web Content Settings**:
  - Disable "Enable JavaScript Alerts" (reduces JS heap)
  - Enable "Clear Cache on Reload" for manual cleanup option
  - Set "Zoom Mode" to "Disabled" (removes pinch-zoom handlers)

- **Settings > Advanced Web Settings**:
  - Disable "Enable Geolocation" (if not needed)
  - Disable "Enable Web SQL Database"
  - Disable "Enable App Cache" (we use HTTP cache instead)
  - Set "WebView Cache Mode" to "LOAD_CACHE_ELSE_NETWORK"

### 1.4 Aggressive Local-Only Optimizations (Home Network)
**Experimental** - Disables location services and Google services:
```bash
./scripts/echo/optimize_echo_local_when_home.sh
```
**Warning**: Only for home network use. Disables location, Google services, and background sync.

---

## Priority 2: Photo Optimization (~10-15MB savings)

### 2.1 Reduce Photo Resolution
Current: 1024x576 (16:9) → Echo screen: 960×480 (2:1 aspect)
Recommended: **1024×512** (2:1 aspect, matches screen, ~2x resolution for quality)

```python
# In sync_slideshow.py, change:
download_url = f"{base}=w1024-h576"
# To:
download_url = f"{base}=w1024-h512"
```

**Impact**: ~10% memory reduction per photo + eliminates letterboxing/cropping from aspect mismatch.

### 2.2 Reduce Photo Count Further
Current: 30 photos (confirmed in ui.json)
If memory is still tight after 2.1:
```bash
./scripts/echo/sync_slideshow.py --max-photos 20
```

Memory formula: `(photo_count * avg_bitmap_size)` where avg_bitmap_size ≈ 0.8 MB decoded.

### 2.3 JPEG Quality Optimization
Add compression during sync (requires pillow):
```python
from PIL import Image
# After download, recompress:
img = Image.open(filepath)
img.save(filepath, "JPEG", quality=80, optimize=True)
```

---

## Priority 3: Frontend Code Optimization

### 3.1 Remove Unused React Dependencies
Check if `react-use-websocket` can be replaced with native WebSocket (saves ~20KB).

### 3.2 Lazy Load Voice Components
Move voice-related code to dynamic imports:
```javascript
// Instead of importing at top level:
const VoiceModule = React.lazy(() => import('./voice/VoiceHandler'));
```

### 3.3 Remove Console Logs in Production
Already in vite.config.js, but ensure it's applied:
```javascript
terserOptions: {
  compress: {
    drop_console: true,
    drop_debugger: true,
  }
}
```

### 3.4 Reduce State Updates
Batch React state updates in preload hook:
```javascript
// Instead of updating state per photo:
setPreloadedImages(new Map(imageMap));

// Batch at end of each batch:
if (i % 5 === 0) setPreloadedImages(new Map(imageMap));
```

---

## Priority 4: WebView Memory Management

### 4.1 Periodic WebView Cleanup (Aggressive)
Add a manual cleanup button or schedule:
```bash
# Force garbage collection via Fully Kiosk URL command
http://localhost:2323/?cmd=clearWebViewCache&password=YOUR_PASSWORD
```

### 4.2 Reduce DOM Complexity
The Clock.jsx has:
- Weather icons (emoji - OK)
- 5-day forecast strip
- Alarm overlays
- Transitions

Consider removing or simplifying:
- Reduce forecast from 5 days to 3
- Simplify alarm overlay DOM structure

### 4.3 CSS Hardware Acceleration
Ensure transforms use GPU:
```css
.photo-slide {
  transform: translateZ(0);
  will-change: opacity;
  backface-visibility: hidden;
}
```

---

## Priority 5: Backend/Network Optimization

### 5.1 HTTP/2 for Multiplexing
Ensure backend uses HTTP/2 to reduce connection overhead.

### 5.2 Gzip/Brotli Compression
Add response compression for API responses:
```python
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=500)
```

### 5.3 Reduce Weather Poll Frequency
Current: 15 minutes. Consider: 30 minutes (weather doesn't change that fast).

---

## Priority 6: Nuclear Options (If Still Tight)

### 6.1 Single Photo Mode
Remove slideshow, show one random photo per hour.

### 6.2 CSS-Only Clock
Replace React with pure HTML/CSS clock (no JS framework overhead).

### 6.3 Static Page Generation
Pre-render the clock page server-side, serve as static HTML.

---

## Testing & Monitoring

For monitoring commands and memory baselines, see [ECHO_DEVICE_SETUP.md](ECHO_DEVICE_SETUP.md#memory-monitoring).

---

## Recommended Implementation Order

1. **Immediate** (5 min): Disable animations via ADB
2. **Today** (15 min): Reduce photo resolution in sync script
3. **This week**: Fully Kiosk settings optimization
4. **Later**: Frontend code optimizations if still needed


