// Cache only the app shell. Never cache API state, sessions, map tiles or photos.
const CACHE = 'flightdesk-shell-v3';
const SHELL = ['/', '/portal', '/portal.html', '/index.html', '/style.css', '/portal.css', '/app.js', '/portal.js', '/art-choice.js', '/art.js', '/scale.js', '/aircraft.svg', '/icon.svg', '/icon-192.png', '/icon-512.png', '/manifest.webmanifest', '/vendor/leaflet.js', '/vendor/leaflet.css'];
self.addEventListener('install', e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL))));
self.addEventListener('activate', e => e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== self.location.origin || u.pathname.startsWith('/api/')) return;
  if (e.request.mode === 'navigate') {
    e.respondWith(fetch(e.request).catch(() => caches.match('/portal')));
  } else if (SHELL.includes(u.pathname)) {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
  }
});
