/* =========================================================================
   MessForecast — service worker
   -------------------------------------------------------------------------
   Strategy, by request type:

     navigations (HTML)  network-first, fall back to the cached page, then to
                         the offline notice. Fresh data wins when there is a
                         connection; the kitchen still works when there is not.
     static assets       cache-first against a versioned cache. Assets are
                         fingerprinted by name, so a new version is a new URL.
     API reads          network only. Caching attendance numbers would be
                         actively misleading.
     API writes         never intercepted. The IndexedDB queue owns those.
   ========================================================================= */
'use strict';

var VERSION = 'v3';
var SHELL_CACHE = 'messforecast-shell-' + VERSION;
var PAGE_CACHE = 'messforecast-pages-' + VERSION;

var SHELL_ASSETS = [
  '/static/css/app.css',
  '/static/css/tokens.css',
  '/static/css/base.css',
  '/static/css/fonts.css',
  '/static/css/kitchen.css',
  '/static/css/landing.css',
  '/static/fonts/WixMadeforDisplay-latin.woff2',
  '/static/fonts/WixMadeforDisplay-latin-ext.woff2',
  '/static/fonts/WixMadeforText-400-latin.woff2',
  '/static/fonts/WixMadeforText-500-latin.woff2',
  '/static/fonts/WixMadeforText-600-latin.woff2',
  '/static/fonts/WixMadeforText-400-latin-ext.woff2',
  '/static/fonts/WixMadeforText-500-latin-ext.woff2',
  '/static/fonts/WixMadeforText-600-latin-ext.woff2',
  '/static/js/app.js',
  '/static/js/kitchen.js',
  '/static/js/scan.js',
  '/static/js/landing.js',
  '/static/js/vendor/gsap.min.js',
  '/static/js/vendor/ScrollTrigger.min.js',
  '/static/img/landing/kitchen.png',
  '/static/img/landing/scan.png',
  '/static/img/landing/dough.jpg',
  '/static/pwa/offline-queue.js',
  '/static/pwa/manifest.webmanifest',
  '/static/pwa/icon.svg',
  '/static/pwa/offline.html'
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      .then(function (cache) { return cache.addAll(SHELL_ASSETS); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (key) {
        if (key !== SHELL_CACHE && key !== PAGE_CACHE) { return caches.delete(key); }
        return null;
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('message', function (event) {
  if (event.data && event.data.type === 'SKIP_WAITING') { self.skipWaiting(); }
});

function isStaticAsset(url) {
  return url.pathname.indexOf('/static/') === 0;
}

function isApiRequest(url) {
  return url.pathname.indexOf('/api/') === 0 ||
         url.pathname.indexOf('/scan/') === 0 ||
         url.pathname.indexOf('/kitchen/guidance') === 0;
}

self.addEventListener('fetch', function (event) {
  var request = event.request;

  // Only GET is ever intercepted. Writes belong to the offline queue.
  if (request.method !== 'GET') { return; }

  var url = new URL(request.url);
  if (url.origin !== self.location.origin) { return; }

  // --- API reads: straight to the network, never cached ---------------
  if (isApiRequest(url)) {
    event.respondWith(
      fetch(request).catch(function () {
        return new Response(
          JSON.stringify({ detail: 'You are offline. This value could not be refreshed.' }),
          { status: 503, headers: { 'Content-Type': 'application/json' } }
        );
      })
    );
    return;
  }

  // --- Static assets: cache-first against the versioned cache ----------
  if (isStaticAsset(url)) {
    event.respondWith(
      caches.match(request).then(function (cached) {
        if (cached) { return cached; }
        return fetch(request).then(function (response) {
          if (response && response.ok) {
            var copy = response.clone();
            caches.open(SHELL_CACHE).then(function (cache) { cache.put(request, copy); });
          }
          return response;
        });
      })
    );
    return;
  }

  // --- Navigations: network-first, then the cached page ----------------
  if (request.mode === 'navigate' || (request.headers.get('accept') || '').indexOf('text/html') !== -1) {
    event.respondWith(
      fetch(request)
        .then(function (response) {
          if (response && response.ok) {
            var copy = response.clone();
            caches.open(PAGE_CACHE).then(function (cache) { cache.put(request, copy); });
          }
          return response;
        })
        .catch(function () {
          return caches.match(request).then(function (cached) {
            if (cached) { return cached; }
            return caches.match('/static/pwa/offline.html').then(function (fallback) {
              if (fallback) { return fallback; }
              return new Response(
                '<!doctype html><meta charset="utf-8"><title>Offline</title>' +
                '<body style="font-family:system-ui;padding:40px"><h1>Offline</h1>' +
                '<p>This screen has not been cached yet. Reconnect once and it will work offline afterwards.</p>',
                { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
              );
            });
          });
        })
    );
  }
});
