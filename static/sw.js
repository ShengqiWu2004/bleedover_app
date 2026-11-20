// Service worker: caches the app shell so the window opens instantly; data (/api/*) always comes from the server.

const CACHE = "bleedover-shell-v30";
const SHELL = [
  "/", "/static/app.css", "/static/js/main.js", "/static/js/util.js", "/static/js/tabs.js", "/static/js/experiment.js",
  "/static/js/runconfig.js", "/static/js/overview.js", "/static/js/results.js", "/static/js/viewer.js",
  "/static/js/status.js", "/static/js/system.js", "/static/js/cleanup.js", "/static/js/library.js", "/static/icons/icon.svg", "/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// Network first (the app is local, so it's fast); the cache is only a fallback.
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.pathname.startsWith("/api/")) return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        return response;
      })
      .catch(() => caches.match(event.request)),
  );
});
