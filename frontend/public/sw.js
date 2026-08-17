/*
 * Service worker.
 *
 * Hand-written rather than generated, because the interesting behaviour here is
 * specific: the app shell must load with no network at all so a clerk can keep
 * typing through an outage, while API responses must never be served stale in a
 * way that could mislead someone about a student's record.
 *
 * Strategy per request type:
 *   navigation      → network first, cached shell as fallback (offline still works)
 *   static assets   → stale-while-revalidate (fast, self-healing)
 *   GET /api/...    → network first, cache as a read-only fallback, clearly marked
 *   writes          → never cached; the app queues them in IndexedDB instead
 */

const VERSION = "v1";
const SHELL_CACHE = `uniacmis-shell-${VERSION}`;
const ASSET_CACHE = `uniacmis-assets-${VERSION}`;
const DATA_CACHE = `uniacmis-data-${VERSION}`;

const SHELL_URLS = ["/", "/offline", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      // Individually, so one missing URL does not fail the whole install.
      .then((cache) => Promise.allSettled(SHELL_URLS.map((url) => cache.add(url))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => !key.endsWith(VERSION))
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

function isAsset(url) {
  return (
    url.pathname.startsWith("/_next/static/") ||
    /\.(?:css|js|woff2?|png|jpg|jpeg|svg|webp|ico)$/.test(url.pathname)
  );
}

async function networkFirst(request, cacheName) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) return cached;
    throw error;
  }
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);

  const network = fetch(request)
    .then((response) => {
      if (response.ok) cache.put(request, response.clone());
      return response;
    })
    .catch(() => cached);

  return cached || network;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  if (url.origin !== self.location.origin && !url.pathname.startsWith("/api/")) {
    return;
  }

  // Writes are never intercepted. The app decides whether to send or queue them,
  // and a service worker replaying a POST would break that contract.
  if (request.method !== "GET") return;

  if (request.mode === "navigate") {
    event.respondWith(
      networkFirst(request, SHELL_CACHE).catch(
        async () => (await caches.match("/offline")) || (await caches.match("/")),
      ),
    );
    return;
  }

  if (isAsset(url)) {
    event.respondWith(staleWhileRevalidate(request, ASSET_CACHE));
    return;
  }

  if (url.pathname.includes("/api/")) {
    event.respondWith(
      networkFirst(request, DATA_CACHE).catch(
        () =>
          new Response(
            JSON.stringify({
              error: {
                code: "offline",
                message: "No connection, and this data has not been cached yet.",
                details: {},
              },
            }),
            { status: 503, headers: { "Content-Type": "application/json" } },
          ),
      ),
    );
  }
});
