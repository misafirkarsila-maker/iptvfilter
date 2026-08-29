// IPTV Filter PWA Service Worker
const CACHE_NAME = 'iptvfilter-v1';
const STATIC_ASSETS = [
  '/',
  '/static/app.css',
  '/static/favicon/site.webmanifest',
  '/static/favicon/favicon-96x96.png',
  '/static/favicon/web-app-manifest-192x192.png',
  '/static/favicon/web-app-manifest-512x512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch(() => {});
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Canlı video veya m3u akışlarını cache'leme, direkt ağdan çek
  const url = new URL(event.request.url);
  if (
    url.pathname.endsWith('.m3u') ||
    url.pathname.endsWith('.m3u8') ||
    url.pathname.endsWith('.ts') ||
    url.pathname.startsWith('/live') ||
    url.pathname.startsWith('/movie') ||
    url.pathname.startsWith('/series')
  ) {
    return;
  }

  // Network-first stratejisi (PWA installability için)
  event.respondWith(
    fetch(event.request).catch(() => {
      return caches.match(event.request);
    })
  );
});
