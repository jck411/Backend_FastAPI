// Self-destruct: unregister this service worker and clear all caches.
// This file exists only so browsers that cached the old SW will pick up
// this version, clean up, and never intercept requests again.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
      .then(() => self.registration.unregister())
  );
});
