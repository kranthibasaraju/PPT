// PPT Board — Service Worker
// WHY a service worker?  Chrome on Android requires one before it will show
// the "Add to Home Screen" install prompt.  We also get basic offline support
// for free: if the network drops briefly, the cached shell keeps the UI visible.

const CACHE = "ppt-board-v1";

// Resources to pre-cache on install (the "app shell")
const PRECACHE = ["/", "/static/manifest.json", "/static/icon-192.png"];

// ── Install: cache the shell ──────────────────────────────────────────────────
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE))
  );
  // Take over immediately — don't wait for old SW to idle out
  self.skipWaiting();
});

// ── Activate: clean up old caches ────────────────────────────────────────────
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  // Claim all open tabs immediately
  self.clients.claim();
});

// ── Fetch: network-first, fall back to cache ─────────────────────────────────
// WHY network-first?  This is a live project tracker — fresh data matters more
// than speed.  Cache only kicks in when the network genuinely fails.
self.addEventListener("fetch", (event) => {
  // Only intercept GET requests for same-origin resources
  if (event.request.method !== "GET") return;

  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Update cache with fresh response (clone because streams can only be read once)
        const clone = response.clone();
        caches.open(CACHE).then((cache) => cache.put(event.request, clone));
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
