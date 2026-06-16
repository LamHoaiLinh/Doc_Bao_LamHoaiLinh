const CACHE = "news-radar-pro-v2-clean";
const ASSETS = ["./", "./index.html", "./styles.css", "./app.js", "./config.js", "./manifest.json"];
self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)));
});
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))));
});
self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);
  if (url.pathname.includes("/api/")) return;
  event.respondWith(caches.match(event.request).then(res => res || fetch(event.request)));
});
