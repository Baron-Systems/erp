/**
 * Service Worker for ABS Portal
 * Provides offline support and caching
 */

const CACHE_NAME = 'abs-portal-v1';
const STATIC_CACHE = 'abs-static-v1';
const DYNAMIC_CACHE = 'abs-dynamic-v1';

// Static assets to cache on install
const STATIC_ASSETS = [
  '/portal/',
  '/portal/verify.html',
  '/portal/index.html',
  '/portal/invoices.html',
  '/portal/offers.html',
  '/portal/account.html',
  '/portal/new-order.html',
  '/assets/erpnext/css/portal/style.css',
  '/assets/erpnext/js/portal/common.js',
  '/portal/icon-192.png',
  '/portal/favicon.ico',
  '/portal/manifest.json',
  '/api/method/erpnext.www.portal.api.get_manifest'
];

// Install event - cache static assets
self.addEventListener('install', (event) => {
  console.log('[SW] Installing...');
  
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => {
        console.log('[SW] Caching static assets');
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => self.skipWaiting())
      .catch((err) => console.error('[SW] Cache failed:', err))
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating...');
  
  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter((name) => {
              return name.startsWith('abs-') && 
                     name !== STATIC_CACHE && 
                     name !== DYNAMIC_CACHE;
            })
            .map((name) => {
              console.log('[SW] Deleting old cache:', name);
              return caches.delete(name);
            })
        );
      })
      .then(() => self.clients.claim())
  );
});

// Fetch event - serve from cache or network
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  
  // Skip non-GET requests
  if (request.method !== 'GET') {
    return;
  }
  
  // Skip API calls - always go to network
  if (url.pathname.includes('/api/') || url.pathname.includes('portal.py')) {
    return;
  }
  
  // Cache strategy: Cache First for static assets
  if (isStaticAsset(url)) {
    event.respondWith(cacheFirst(request));
  }
  // Network First for dynamic content
  else if (isDynamicContent(url)) {
    event.respondWith(networkFirst(request));
  }
  // Handle missing assets gracefully
  else if (url.pathname.includes('icon-192.png') || url.pathname.includes('favicon.ico')) {
    event.respondWith(
      caches.match(request).then(cached => {
        if (cached) {
          return cached;
        }
        // Return empty response for missing icons
        return new Response('', { 
          status: 200, 
          headers: { 'Content-Type': 'image/png' }
        });
      })
    );
  }
});

/**
 * Check if URL is a static asset
 */
function isStaticAsset(url) {
  const staticExtensions = ['.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.woff', '.woff2', '.ttf'];
  return staticExtensions.some(ext => url.pathname.endsWith(ext));
}

/**
 * Check if URL is dynamic content
 */
function isDynamicContent(url) {
  return url.pathname.startsWith('/portal/') && url.pathname.endsWith('.html');
}

/**
 * Cache First strategy
 */
async function cacheFirst(request) {
  const cached = await caches.match(request);
  
  if (cached) {
    return cached;
  }
  
  try {
    const response = await fetch(request);
    const cache = await caches.open(STATIC_CACHE);
    cache.put(request, response.clone());
    return response;
  } catch (error) {
    console.error('[SW] Fetch failed:', error);
    return new Response('Offline', { status: 503 });
  }
}

/**
 * Network First strategy
 */
async function networkFirst(request) {
  try {
    const networkResponse = await fetch(request);
    const cache = await caches.open(DYNAMIC_CACHE);
    cache.put(request, networkResponse.clone());
    return networkResponse;
  } catch (error) {
    console.log('[SW] Network failed, trying cache...');
    const cached = await caches.match(request);
    
    if (cached) {
      return cached;
    }
    
    // Return offline fallback for HTML pages
    if (request.destination === 'document') {
      return caches.match('/portal/');
    }
    
    return new Response('Offline', { status: 503 });
  }
}

// Message handling from main thread
self.addEventListener('message', (event) => {
  if (event.data === 'skipWaiting') {
    self.skipWaiting();
  }
});
