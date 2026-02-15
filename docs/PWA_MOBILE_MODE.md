# PWA & Mobile Mode — How It Works and How to Deploy

**Last Updated:** February 2026

---

## Overview

The main frontend (`frontend/`) has two UI modes:

| Mode | Where | Detection | Layout |
|------|-------|-----------|--------|
| **Browser mode** | Laptop/desktop browser | Wide screen or no touch | Full desktop controls: Explorer, Model picker, Web Search, Model settings, System settings, MCP, Kiosk, CLI, Clear |
| **Mobile/PWA mode** | Phone (any browser or home screen) | Touch device + screen ≤ 768px, OR installed PWA standalone | Simplified: hamburger menu hides Kiosk/CLI buttons, `[+] [mic] [send]` in one bottom row, mobile-optimized layout |

Both modes serve from the same codebase — no separate builds.

---

## How Mobile Detection Works

**File:** `frontend/src/App.svelte` (inside `onMount`)

```typescript
pwaMode =
  (window.matchMedia("(pointer: coarse)").matches && window.innerWidth <= 768) ||
  window.matchMedia("(display-mode: standalone)").matches ||
  window.matchMedia("(display-mode: minimal-ui)").matches ||
  ("standalone" in navigator && navigator.standalone === true);
```

**Why this approach (and not just `display-mode: standalone`):**

- Chrome Android will NOT grant true PWA install on self-signed certs (dev environment). The `beforeinstallprompt` event never fires, and "Add to Home Screen" creates a browser shortcut, not a standalone app.
- On production (`chat.jackshome.com` via Cloudflare Tunnel), the cert is trusted and true PWA install works. Then `display-mode: standalone` matches.
- The `pointer: coarse` + width ≤ 768 check catches ALL phones regardless of how the user opened the page (bookmark, home screen shortcut, browser tab).
- On a laptop, even with a touchscreen, the width is > 768px so it stays in browser mode.

### What gets hidden in mobile/PWA mode

- **Kiosk settings button** — not useful on phone
- **CLI settings button** — not useful on phone
- **Desktop Clear button** in the icon row (mobile-bar "Clear" button stays visible)
- **Composer layout** changes: `[+]` attachment button moves to the bottom row alongside mic and send

---

## Key Files Modified for PWA/Mobile Support

### `frontend/index.html`
```html
<meta name="viewport" content="width=device-width, initial-scale=1.0,
  maximum-scale=1.0, user-scalable=no, viewport-fit=cover,
  interactive-widget=resizes-content" />
```
- `interactive-widget=resizes-content` — **critical for virtual keyboard behavior** (Chrome 108+). Tells the browser to resize the layout viewport when the keyboard opens, so `100dvh` shrinks and the input stays visible above the keyboard. Without this, the keyboard overlaps the input.
- `maximum-scale=1.0, user-scalable=no` — prevents accidental zoom on double-tap
- `viewport-fit=cover` — fills area behind notch/status bar

### `frontend/src/main.ts`
```typescript
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}
```
Registers the service worker for PWA installability on production.

### `frontend/public/sw.js`
Minimal no-op service worker. Network-only (no caching). Must have a `fetch` event listener for Chrome to consider it "functional":
```javascript
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});
self.addEventListener("fetch", () => {});
```

### `frontend/public/manifest.webmanifest`
Standard PWA manifest with `"display": "standalone"`. Icons at 192px and 512px (separate `any` and `maskable` entries — Chrome requires these split, not combined as `"any maskable"`).

### `frontend/vite.config.ts`
HTTPS enabled for local dev using self-signed certs:
```typescript
https: {
  key: fs.readFileSync(path.resolve(__dirname, '../certs/server.key')),
  cert: fs.readFileSync(path.resolve(__dirname, '../certs/server.crt')),
},
```
Required because microphone access and service workers need a secure context.

### `src/backend/app.py`
Middleware adds `Permissions-Policy: microphone=(self)` header to all responses. Required for mic access in the PWA/embedded context.

### `frontend/src/lib/components/chat/ChatHeader.svelte`
- Receives `pwaMode` prop
- Kiosk button, CLI button, and desktop Clear button wrapped in `{#if !pwaMode}`
- Mobile-bar Clear button always visible

### `frontend/src/lib/components/chat/Composer.svelte`
- Receives `pwaMode` prop
- In PWA mode: `[+]` button moves from above the textarea to the bottom action row
- CSS: `.input-shell.pwa-layout` gives `flex-wrap: wrap` with textarea on its own line, buttons in a single row below

---

## Local Development (Away from Home LAN)

### Current working setup
```
Laptop (10.235.x.x)
├── Backend: uvicorn on :8000 (HTTPS, self-signed cert)
└── Frontend: Vite dev on :5173 (HTTPS, self-signed cert, proxies /api → :8000)

Phone → https://LAPTOP_IP:5173/  (accept cert warning once)
Laptop browser → https://localhost:5173/  or  https://LAPTOP_IP:5173/
```

### How to start
```bash
./start.sh
# Starts backend on :8000 and Vite on :5173
```

### Phone access
1. Phone and laptop must be on the same Wi-Fi network
2. Find laptop IP: `ip addr` or `hostname -I` (e.g. `10.235.43.158`)
3. On phone, open Chrome → `https://10.235.43.158:5173/`
4. Accept the self-signed certificate warning (Advanced → Proceed)
5. Mobile mode activates automatically (touch + narrow screen)

### Gotcha: true PWA install does NOT work on self-signed certs
- Chrome Android refuses to register service workers on untrusted HTTPS
- "Add to Home Screen" creates a browser shortcut, NOT a standalone PWA app
- This is fine — mobile detection uses screen size + touch, not display-mode
- **Workaround if you really need standalone:** On phone, go to `chrome://flags` → "Unsafely treat insecure origin as secure" → add your dev URL → Relaunch

### Vite HMR
Vite hot-reloads on file save. Phone refreshes automatically. No rebuilds needed during development.

---

## Production Deployment (Home LAN — Proxmox)

### Architecture
```
Phone/Browser → chat.jackshome.com → Cloudflare Tunnel → LXC 111 (:8000)
```
Cloudflare provides a trusted TLS cert, so true PWA install works in production.

### Deploy steps after frontend changes
```bash
# 1. Rebuild the frontend
cd frontend && npm run build && cd ..
# Output → src/backend/static/

# 2. Commit source + built output
git add frontend/ src/backend/static/
git commit -m "feat: PWA mobile mode improvements"
git push

# 3. Pull on server
ssh root@192.168.1.111 "cd /opt/backend-fastapi && git pull"
```

Backend Python changes auto-reload (dev service). No restart needed unless dependencies changed.

### What works differently in production
| Feature | Local dev | Production |
|---------|-----------|------------|
| HTTPS | Self-signed cert (browser warning) | Cloudflare trusted cert |
| SW registration | May fail on phone (untrusted cert) | Works → enables true PWA install |
| `beforeinstallprompt` | Usually doesn't fire | Fires → shows install banner |
| `display-mode: standalone` | Rarely matches | Matches when installed from banner |
| Mobile detection fallback | `pointer: coarse` + width ≤ 768 | Same, plus standalone match |
| Mic permission | Works after accepting cert | Works natively |

### Production PWA install flow (for users)
1. Visit `https://chat.jackshome.com` on phone
2. In-app banner appears: "Install this app for a better experience" → tap Install
3. Or: Chrome menu → "Install app"
4. App appears on home screen, opens in standalone mode (no browser chrome)

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Phone shows desktop layout | `pwaMode` false — screen too wide or no touch detected | Check `window.innerWidth` in console; should be ≤ 768 |
| Kiosk/CLI buttons visible on phone | `pwaMode` not propagated to ChatHeader | Ensure `{pwaMode}` prop is passed in App.svelte |
| Keyboard covers input on mobile | Missing `interactive-widget=resizes-content` | Check `frontend/index.html` viewport meta tag |
| Keyboard causes layout jump | JS viewport tracking conflicting with CSS | Use pure `height: 100dvh`, no JS viewport hacks |
| Mic not working | Missing `Permissions-Policy` header or not HTTPS | Check backend middleware + ensure HTTPS |
| "Install app" not in Chrome menu | Self-signed cert (dev) or SW not registered | Expected in dev; works in production with Cloudflare cert |
| Install banner doesn't appear | `beforeinstallprompt` not fired | Same as above — cert must be trusted |
| Page blank on phone | Vite not serving HTTPS or wrong IP | Check `vite.config.ts` has `https` block; verify IP with `ip addr` |
| SW caching stale files | Old SW with caching logic | Current `sw.js` is network-only (no caching) |

---

## Component Implementation Details

These are the specific patterns used. Read the actual files for full context, but this summary should orient a new session.

### App.svelte — Root component
- `pwaMode` is a `let` variable set in `onMount`, passed as prop to `ChatHeader` and `Composer`
- Layout uses `height: 100dvh` (no JS viewport tracking — all previous attempts with `window.innerHeight`, `visualViewport`, `--app-vh` custom properties, and `translateY` hacks were removed because they caused layout hops)
- Mobile drawer state: `mobileDrawerOpen` variable, two-way bound to ChatHeader via `bind:controlsOpen={mobileDrawerOpen}`
- Drawer auto-closes on input focus: `on:inputFocus={() => (mobileDrawerOpen = false)}` on Composer

### ChatHeader.svelte — Top bar + mobile drawer
- `export let pwaMode = false` and `export let controlsOpen = false` (bindable)
- Mobile (≤768px): thin bar with hamburger + model name + Clear button; drawer slides from left
- Hamburger icon toggles to **left-arrow chevron** (not X) when open
- Kiosk, CLI, and desktop Clear buttons wrapped in `{#if !pwaMode}` inside the `.icon-row`
- Mobile-bar Clear button is always visible (not behind `{#if !pwaMode}`)

### Composer.svelte — Input + action buttons
- `export let pwaMode = false`
- Dispatches `inputFocus` event on textarea focus (so App can close the drawer)
- In PWA mode: `+` (attachment) button hidden from its original position above textarea, duplicated inside `.composer-actions` div
- CSS class `.input-shell.pwa-layout` applies when `pwaMode` is true:
  - `flex-wrap: wrap` — textarea takes full width (order 0), action buttons wrap to next line (order 1)
  - `.composer-actions` forced to `flex-wrap: nowrap; justify-content: flex-start` so `[+] [mic] [send]` stay in one row
  - Children forced to `flex: 0 0 auto; width: auto` to prevent 480px media query from stretching buttons
- `.icon-button.leading` (the `+` button) has same background as `.icon-button` (mic) for consistent styling

---

## History of Issues Solved (Feb 2026)

For future reference — these are the problems we hit and their solutions:

1. **Google keyboard mic "not permitted" in PWA** → Added `Permissions-Policy: microphone=(self)` middleware to FastAPI backend
2. **`display-mode: standalone` never matches on dev** → Self-signed certs prevent true PWA install on Android. Switched to touch + width detection as primary method
3. **Service worker was self-destructing** → Old `sw.js` called `self.registration.unregister()`. Replaced with minimal no-op SW that stays registered
4. **Manifest `"purpose": "any maskable"` blocked install** → Chrome requires separate icon entries for `any` and `maskable`
5. **Virtual keyboard covering input** → Added `interactive-widget=resizes-content` to viewport meta tag (Chrome 108+ feature). Use `100dvh` for height — it dynamically adjusts when keyboard opens
6. **JS viewport tracking (`innerHeight`, `visualViewport`) caused layout hops** → Removed all manual JS viewport tracking. Pure CSS `100dvh` + the meta tag is sufficient
7. **`scrollIntoView` on input focus conflicted with drawer transform** → Removed `ensureComposerVisible()` call; let the browser handle scroll naturally
8. **Vite dev server was HTTP-only** → Phone couldn't use service worker or mic. Added HTTPS to `vite.config.ts` using existing self-signed certs
