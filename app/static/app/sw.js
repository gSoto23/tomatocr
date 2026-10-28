// TOMATO's service worker, served at /sw.js (app/routers/pwa.py) so it covers the whole site.
// It doesn't cache pages (the data has to be live): it shows /offline when there's no
// connection, and it receives the phone notifications (web push, docs/NOTIFICACIONES.md).
const CACHE = "tomato-v2";
const OFFLINE = "/offline";

self.addEventListener("install", (event) => {
    event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll([OFFLINE, "/static/images/app/icon-192.png"])));
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(caches.keys()
        .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
        .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (event) => {
    if (event.request.mode !== "navigate") return;
    event.respondWith(fetch(event.request).catch(() => caches.match(OFFLINE)));
});

self.addEventListener("push", (event) => {
    let data = {};
    try { data = event.data ? event.data.json() : {}; } catch (e) { data = { title: event.data.text() }; }
    event.waitUntil(self.registration.showNotification(data.title || "TOMATO", {
        body: data.body || "",
        icon: "/static/images/app/icon-192.png",
        // Android shows the badge in the status bar as a one-color silhouette.
        badge: "/static/images/app/badge-96.png",
        tag: data.tag,
        data: { url: data.url || "/notificaciones" },
    }));
});

self.addEventListener("notificationclick", (event) => {
    event.notification.close();
    const url = new URL(event.notification.data.url, self.location.origin).href;
    event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
        const open = windows.find((w) => w.url.startsWith(self.location.origin));
        if (open) return open.navigate(url).then((w) => (w || open).focus());
        return self.clients.openWindow(url);
    }));
});
