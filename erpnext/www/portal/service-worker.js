/**
 * Service Worker for ABS Portal
 * Provides offline support and advanced caching
 * Version 3.0 - Modern Caching Strategy
 */

const CACHE_VERSION = 'v4';
const STATIC_CACHE = `abs-static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `abs-dynamic-${CACHE_VERSION}`;
const IMAGE_CACHE = `abs-images-${CACHE_VERSION}`;

// Static assets to cache on install
const STATIC_ASSETS = [
  '/portal/',
  '/portal/verify.html',
  '/portal/index.html',
  '/portal/style.css',
  '/portal/common.js',
  '/portal/install-prompt.js',
  '/portal/icon-192.png',
  '/portal/favicon.ico',
  '/portal/manifest.json'
];

// Cache strategies
const CACHE_STRATEGIES = {
  static: 'cache-first',
  dynamic: 'network-first',
  api: 'network-only',
  images: 'cache-first'
};

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

// Activate event - clean up old caches and claim clients
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating...');
  
  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter((name) => {
              return name.startsWith('abs-') && 
                     !name.includes(CACHE_VERSION);
            })
            .map((name) => {
              console.log('[SW] Deleting old cache:', name);
              return caches.delete(name);
            })
        );
      })
      .then(() => self.clients.claim())
      .then(() => {
        // Notify all clients that SW is active
        return self.clients.matchAll({ type: 'window' }).then(clients => {
          clients.forEach(client => {
            client.postMessage({ type: 'SW_ACTIVATED', version: CACHE_VERSION });
          });
        });
      })
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
  // Image cache strategy
  else if (isImageAsset(url)) {
    event.respondWith(imageCacheStrategy(request));
  }
  // Network First for dynamic content
  else if (isDynamicContent(url)) {
    event.respondWith(networkFirst(request));
  }
  // Handle missing assets gracefully
  else if (url.pathname.includes('icon') || url.pathname.includes('favicon')) {
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
  const staticExtensions = ['.css', '.js', '.woff', '.woff2', '.ttf', '.otf'];
  return staticExtensions.some(ext => url.pathname.endsWith(ext));
}

/**
 * Check if URL is an image asset
 */
function isImageAsset(url) {
  const imageExtensions = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico'];
  return imageExtensions.some(ext => url.pathname.endsWith(ext));
}

/**
 * Check if URL is dynamic content
 */
function isDynamicContent(url) {
  return url.pathname.startsWith('/portal/') && url.pathname.endsWith('.html');
}

/**
 * Image cache strategy - stale while revalidate
 */
async function imageCacheStrategy(request) {
  const cache = await caches.open(IMAGE_CACHE);
  const cached = await cache.match(request);
  
  // Return cached immediately if available
  if (cached) {
    // Update cache in background
    fetch(request).then(response => {
      if (response.ok) {
        cache.put(request, response.clone());
      }
    }).catch(() => {});
    
    return cached;
  }
  
  // Otherwise fetch and cache
  try {
    const response = await fetch(request);
    if (response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    console.error('[SW] Image fetch failed:', error);
    return new Response('', { status: 503 });
  }
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
