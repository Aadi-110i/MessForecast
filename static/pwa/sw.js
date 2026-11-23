/* =========================================================================
   MessForecast — service worker
   -------------------------------------------------------------------------
   Strategy, by request type:

     navigations (HTML)  network-first, fall back to the cached page, then to
                         the offline notice. Fresh data wins when there is a
                         connection; the kitchen still works when there is not.
     stylesheets, scripts
                         network-first with a three-second cap, fall back to
                         the cached copy. A change to the stylesheet has to
                         reach the reader on the next load, not the one after
                         it, and the kitchen still gets its screen when the
                         network is slow or gone.
     images, fonts      the cached copy is served straight away, and refreshed
                         in the background. These rarely change, and the
                         tablet works without a network.
     API reads          network only. Caching attendance numbers would be
                         actively misleading.
     API writes         never intercepted. The IndexedDB queue owns those.
   ========================================================================= */
'use strict';

var VERSION = 'v9';
var SHELL_CACHE = 'messforecast-shell-' + VERSION;
var PAGE_CACHE = 'messforecast-pages-' + VERSION;

/* How long the network gets before the cached stylesheet is used instead. */
var CODE_TIMEOUT_MS = 3000;

var SHELL_ASSETS = [
  '/static/css/app.css',
  '/static/css/tokens.css',
  '/static/css/base.css',
  '/static/css/fonts.css',
  '/static/css/kitchen.css',
  '/static/css/landing.css',
  '/static/css/auth.css',
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
    })
      .then(function () { return self.clients.claim(); })
      .then(function () {
        // The page that is open is still the old one. It is told that a new
        // worker has taken over, and it reloads itself once, so the reader
        // is never left looking at a screen the platform has moved on from.
        return self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clients) {
          clients.forEach(function (client) {
            client.postMessage({ type: 'SW_ACTIVATED', version: VERSION });
          });
        });
      })
  );
});

self.addEventListener('message', function (event) {
  if (event.data && event.data.type === 'SKIP_WAITING') { self.skipWaiting(); }
});

function isStaticAsset(url) {
  return url.pathname.indexOf('/static/') === 0;
}

/* The stylesheets and the scripts. These are the files that change, and a
   reader has to see the change on the next load. */
function isCodeAsset(url) {
  return isStaticAsset(url) && /\.(css|js)$/.test(url.pathname);
}

/* The network, but not for longer than the reader will wait. The request is
   made with the HTTP cache switched off: the browser would otherwise answer
   from its own copy, and the reader would keep seeing the old screen. */
function networkWithin(request, ms) {
  return new Promise(function (resolve, reject) {
    var settled = false;
    var timer = setTimeout(function () {
      if (settled) { return; }
      settled = true;
      reject(new Error('timeout'));
    }, ms);
    fetch(request.url, { cache: 'reload', credentials: 'same-origin' })
      .then(function (response) {
        if (settled) { return; }
        settled = true;
        clearTimeout(timer);
        resolve(response);
      })
      .catch(function (error) {
        if (settled) { return; }
        settled = true;
        clearTimeout(timer);
        reject(error);
      });
  });
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

  // --- Stylesheets and scripts: the network first, the cache when there is
  //     none, and the cached copy when the network is too slow to wait for ---
  if (isCodeAsset(url)) {
    event.respondWith(
      networkWithin(request, CODE_TIMEOUT_MS)
        .then(function (response) {
          if (response && response.ok) {
            var copy = response.clone();
            caches.open(SHELL_CACHE).then(function (cache) { cache.put(request, copy); });
          }
          return response;
        })
        .catch(function () {
          return caches.match(request).then(function (cached) {
            if (cached) { return cached; }
            return new Response('', { status: 504, statusText: 'Offline' });
          });
        })
    );
    return;
  }

  // --- Images and fonts: the cached copy now, a fresh one in the background ---
  if (isStaticAsset(url)) {
    event.respondWith(
      caches.match(request).then(function (cached) {
        // The copy on the tablet is served straight away, because the kitchen
        // works without a network. The same copy is refreshed in the
        // background, so a change to the picture reaches the tablet on the
        // next load rather than waiting for someone to remember to throw the
        // cache away by hand. The refresh bypasses the browser's own cache,
        // or it would put the same old copy back.
        var refreshed = fetch(request.url, { cache: 'reload', credentials: 'same-origin' })
          .then(function (response) {
            if (response && response.ok) {
              var copy = response.clone();
              caches.open(SHELL_CACHE).then(function (cache) { cache.put(request, copy); });
            }
            return response;
          })
          .catch(function () { return cached; });

        if (cached) { return cached; }
        return refreshed.then(function (response) {
          return response || new Response('', { status: 504, statusText: 'Offline' });
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
