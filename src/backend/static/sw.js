// Minimal service worker — required for PWA installability.
// Network-first: all requests go straight to the network (no offline caching).
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});
self.addEventListener("fetch", () => {
  // Let the browser handle all fetches normally (network-only).
  // This handler must exist for Chrome to consider the SW "functional".
});
