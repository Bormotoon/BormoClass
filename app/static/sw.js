/**
 * BormoClass Offline Service Worker (Zero External CDN, 152-FZ)
 * Provides:
 *  - Pre-caching of local application assets
 *  - Offline fallback for static and course materials
 *  - Stale-while-revalidate strategy for UI scripts and styles
 *  - Network-first for dynamic API endpoints
 */

const CACHE_NAME = "bormoclass-shell-v1";
const MATERIALS_CACHE = "bormoclass-materials-v1";

const PRECACHE_ASSETS = [
  "/",
  "/static/css/md3-tokens.css",
  "/static/css/app.css",
  "/static/js/icons.js",
  "/static/js/webcrypto-vault.js",
  "/static/js/sanpin-timer.js",
  "/static/js/pb-passport-bridge.js",
  "/static/js/modules/speedgrader.js",
  "/static/js/modules/gradebook-periods.js",
  "/static/js/modules/global-calendar-admin.js",
  "/static/js/modules/pdf-scanner.js",
  "/static/manifest.webmanifest"
];

// Install: pre-cache application shell
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_ASSETS).catch((err) => {
        console.warn("Some precache assets could not be loaded immediately:", err);
      });
    }).then(() => self.skipWaiting())
  );
});

// Activate: clean up outdated caches
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME && key !== MATERIALS_CACHE) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: route requests
self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // Ignore non-GET requests for standard caching
  if (req.method !== "GET") {
    return;
  }

  // API calls: Network-first with cache fallback
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/v1/")) {
    event.respondWith(
      fetch(req)
        .then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(MATERIALS_CACHE).then((cache) => cache.put(req, clone));
          }
          return response;
        })
        .catch(() => {
          return caches.match(req).then((cached) => {
            if (cached) return cached;
            return new Response(JSON.stringify({ error: "OFFLINE", detail: "Вы находитесь в автономном режиме." }), {
              status: 503,
              headers: { "Content-Type": "application/json" }
            });
          });
        })
    );
    return;
  }

  // Static shell & assets: Stale-While-Revalidate
  event.respondWith(
    caches.match(req).then((cachedResponse) => {
      const fetchPromise = fetch(req).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const resClone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, resClone));
        }
        return networkResponse;
      }).catch(() => null);

      return cachedResponse || fetchPromise || caches.match("/");
    })
  );
});

// Message listener for cache management & background sync
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});
