/**
 * Gab Event PWA — cache shell, pages visitées et médias.
 * /api/*, paiements et console restent toujours en réseau.
 */
const VERSION = "gab-event-v9";
const SHELL = VERSION + "-shell";
const PAGES = VERSION + "-pages";
const ASSETS = VERSION + "-assets";
const IMAGES = VERSION + "-images";
const IMAGE_LIMIT = 80;

const PRECACHE = [
  "/",
  "/offline/",
  "/static/css/app.css",
  "/static/js/ge-app.js",
  "/static/js/pwa.js",
  "/static/js/scanner.js",
  "https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js",
  "/static/manifest.json",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/apple-touch-icon.png",
];

function isBypass(url) {
  const p = url.pathname;
  if (p.startsWith("/api/")) return true;
  if (p.startsWith("/payments/")) return true;
  if (p.startsWith("/console/")) return true;
  if (p.startsWith("/admin/") || p.startsWith("/platform-admin/")) return true;
  if (p.includes("/webhook")) return true;
  if (/\/carte\/?$/.test(p) || /\/download\/?$/.test(p) || /\/qr\/?$/.test(p)) return true;
  if (/\/generer\/?$/.test(p) || /\/export\/?$/.test(p)) return true;
  if (/(?:^|[?&])fmt=(png|pdf|xlsx)\b/i.test(url.search)) return true;
  if (p.startsWith("/accounts/logout")) return true;
  if (p.startsWith("/brand/")) return true;
  return false;
}

function isAsset(url) {
  return (
    url.pathname.startsWith("/static/css/") ||
    url.pathname.startsWith("/static/js/") ||
    url.pathname.startsWith("/static/icons/") ||
    url.pathname === "/static/manifest.json" ||
    url.hostname === "fonts.googleapis.com" ||
    url.hostname === "fonts.gstatic.com" ||
    url.hostname === "unpkg.com"
  );
}

function isImage(url, dest) {
  if (dest === "image") return true;
  return (
    url.pathname.startsWith("/media/") ||
    url.pathname.startsWith("/static/img/") ||
    /\.(png|jpe?g|webp|gif|svg|ico)(\?|$)/i.test(url.pathname)
  );
}

function isNavigation(request) {
  const accept = request.headers.get("accept") || "";
  return request.mode === "navigate" ||
    (request.destination === "document" && accept.includes("text/html"));
}

async function trimCache(cacheName, max) {
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();
  if (keys.length <= max) return;
  await Promise.all(keys.slice(0, keys.length - max).map((key) => cache.delete(key)));
}

async function putOk(cacheName, request, response) {
  if (!response || !response.ok || response.type === "opaque") return response;
  if (response.redirected) return response;
  const cache = await caches.open(cacheName);
  cache.put(request, response.clone());
  return response;
}

async function matchAny(request) {
  return (
    (await caches.match(request)) ||
    (await caches.match(request, { ignoreSearch: true }))
  );
}

async function staleWhileRevalidate(request, cacheName) {
  const cached = await matchAny(request);
  const fetching = fetch(request)
    .then((res) => putOk(cacheName, request, res))
    .catch(() => cached);
  return cached || fetching;
}

async function cacheFirst(request, cacheName, trimTo) {
  const cached = await matchAny(request);
  if (cached) return cached;
  try {
    const res = await fetch(request);
    await putOk(cacheName, request, res);
    if (trimTo) trimCache(cacheName, trimTo);
    return res;
  } catch (err) {
    return cached;
  }
}

async function networkFirst(request, cacheName, timeoutMs) {
  const cached = await matchAny(request);
  const fetching = fetch(request)
    .then((res) => {
      if (res && res.ok && !res.redirected) putOk(cacheName, request, res);
      return res;
    });
  if (!cached) {
    return fetching.catch(() => caches.match("/offline/"));
  }
  try {
    return await Promise.race([
      fetching,
      new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), timeoutMs)),
    ]);
  } catch (err) {
    return cached;
  }
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL)
      .then((cache) =>
        Promise.all(PRECACHE.map((url) => cache.add(url).catch(() => undefined)))
      )
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => !key.startsWith(VERSION)).map((key) => caches.delete(key)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  let url;
  try {
    url = new URL(request.url);
  } catch (err) {
    return;
  }

  if (isBypass(url)) return;

  if (isAsset(url)) {
    if (url.searchParams.has("v")) {
      event.respondWith(networkFirst(request, ASSETS, 2500));
      return;
    }
    event.respondWith(staleWhileRevalidate(request, ASSETS));
    return;
  }

  if (isImage(url, request.destination)) {
    event.respondWith(cacheFirst(request, IMAGES, IMAGE_LIMIT));
    return;
  }

  if (url.origin === self.location.origin && isNavigation(request)) {
    event.respondWith(networkFirst(request, PAGES, 1800));
    return;
  }

  if (url.origin === self.location.origin) {
    event.respondWith(staleWhileRevalidate(request, PAGES));
  }
});
