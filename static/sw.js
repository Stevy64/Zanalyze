const CACHE = 'paris-v103';
const PRECACHE = [
  '/manifest.webmanifest',
  '/static/css/app.css?v=103',
  '/static/js/app.js?v=103',
  '/static/vendor/alpine.min.js?v=60',
  '/static/img/hero-accueil.jpg',
  '/static/brand/zanalyze-logo.png',
  '/static/brand/zanalyze-logo-nav.png',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/favicon-32.png',
  '/static/icons/apple-touch.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then(async (cache) => {
      await Promise.all(
        PRECACHE.map((url) => cache.add(url).catch(() => undefined))
      );
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});

function withCacheFlag(response) {
  const headers = new Headers(response.headers);
  headers.set('X-SW-Cache', '1');
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE);
  const cached = await cache.match(request);
  const network = fetch(request).then((res) => {
    if (res && res.ok) cache.put(request, res.clone());
    return res;
  }).catch(() => null);
  if (cached) {
    network.catch(() => {});
    return withCacheFlag(cached);
  }
  const fresh = await network;
  if (fresh) return fresh;
  return new Response(JSON.stringify({ detail: 'unavailable' }), {
    status: 503,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function networkFirst(request, { flagCache, timeoutMs = 3500 } = {}) {
  const cache = await caches.open(CACHE);
  const cached = await cache.match(request);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(request, { signal: controller.signal });
    clearTimeout(timer);
    if (res && res.ok) {
      try { cache.put(request, res.clone()); } catch (_) { /* quota */ }
    }
    return res;
  } catch (err) {
    clearTimeout(timer);
    if (cached) return flagCache ? withCacheFlag(cached) : cached;
    throw err;
  }
}

function isAppShell(path) {
  return (
    path === '/'
    || path === '/historique'
    || path === '/salon'
    || path === '/chat'
    || path === '/verification'
    || path === '/reglages'
    || /^\/matchs\/\d+\/?$/.test(path)
  );
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;

  const path = url.pathname;

  // Ne pas intercepter le SW (évite les mises à jour bloquées).
  if (path === '/sw.js') return;

  // Sync Engine : toujours réseau (pas de cache SW).
  if (path.startsWith('/api/v1/sync/')) {
    event.respondWith(fetch(req).catch(() => new Response(
      JSON.stringify({ ok: false, reason: 'offline' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } },
    )));
    return;
  }

  if (path.startsWith('/api/')) {
    // Listes matchs : réseau d’abord (évite de resservir un JSON vide
    // figé après un import raté). Cache seulement en secours.
    if (path.startsWith('/api/v1/matchs') && !path.includes('/resultat')) {
      event.respondWith(networkFirst(req, { flagCache: true, timeoutMs: 15000 }));
      return;
    }
    // Autres API : réseau rapide, sinon cache.
    event.respondWith(networkFirst(req, { flagCache: true, timeoutMs: 3500 }));
    return;
  }

  if (req.mode === 'navigate' || isAppShell(path)) {
    event.respondWith(networkFirst(req, { flagCache: false, timeoutMs: 6000 }));
    return;
  }

  if (path === '/manifest.webmanifest' || path.startsWith('/static/')) {
    event.respondWith(staleWhileRevalidate(req));
  }
});
