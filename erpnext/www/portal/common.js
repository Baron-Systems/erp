// Customer Portal Common Functions

const API_BASE = '/api/method/erpnext.www.portal.api.';

// ============== Token Management ==============
// IMPORTANT:
// Token cookie is HttpOnly (server-set). JS cannot read it.
// So auth checks must call the backend.

async function checkAuth() {
    const res = await apiCall('portal_me', {}, false);
    if (res && res.success) {
        // Ensure currency is set for all protected pages (once)
        await ensurePortalSettings();
        return true;
    }
    window.location.href = '/portal/verify';
    return false;
}

function clearToken() {
    // Best-effort clear (server cookie is HttpOnly, so this may not remove it).
    // Try multiple variations to ensure the cookie is cleared
    const cookies = [
        'customer_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT',
        'customer_token=; path=/; domain=; expires=Thu, 01 Jan 1970 00:00:00 GMT',
        'customer_token=; path=/; domain=localhost; expires=Thu, 01 Jan 1970 00:00:00 GMT',
        'customer_token=; path=/; domain=.localhost; expires=Thu, 01 Jan 1970 00:00:00 GMT'
    ];
    
    cookies.forEach(cookie => {
        document.cookie = cookie;
    });
}

// ============== API Calls ==============

let portalCsrfToken = null;
let portalSettingsLoaded = false;

async function ensurePortalSettings() {
    if (portalSettingsLoaded) return true;
    try {
        const settings = await apiCall('get_portal_settings', {}, false);
        if (settings && settings.success && settings.currency) {
            setCurrency(settings.currency);
        }
        portalSettingsLoaded = true;
        return true;
    } catch (e) {
        return false;
    }
}

async function ensureCsrfToken() {
    if (portalCsrfToken) return portalCsrfToken;

    // 1) Try cookie (if present)
    const fromCookie = getCsrfToken();
    console.log('CSRF from cookie:', fromCookie ? 'found' : 'not found');
    if (fromCookie) {
        portalCsrfToken = fromCookie;
        return portalCsrfToken;
    }

    // 2) Try portal CSRF endpoint (allows guest)
    try {
        console.log('Trying portal CSRF endpoint...');
        const r = await fetch('/api/method/erpnext.www.portal.api.portal_get_csrf_token', {
            method: 'GET',
            credentials: 'same-origin'
        });
        console.log('Portal CSRF response status:', r.status);
        if (r.ok) {
            const j = await r.json();
            console.log('Portal CSRF response:', j);
            // Frappe wraps return in message
            if (j && j.message) {
                portalCsrfToken = j.message;
                console.log('Got CSRF token from portal endpoint');
                return portalCsrfToken;
            }
        }
    } catch (e) {
        console.log('Portal CSRF endpoint failed:', e);
    }

    // 3) Fallback: try standard endpoint
    try {
        console.log('Trying standard CSRF endpoint...');
        const r = await fetch('/api/method/frappe.sessions.get_csrf_token', {
            method: 'GET',
            credentials: 'same-origin'
        });
        console.log('Standard CSRF response status:', r.status);
        if (r.ok) {
            const j = await r.json();
            console.log('Standard CSRF response:', j);
            if (j && j.message) {
                portalCsrfToken = j.message;
                return portalCsrfToken;
            }
        }
    } catch (e) {
        console.log('Standard CSRF endpoint failed:', e);
    }

    console.warn('Could not get CSRF token from any source');
    return '';
}

async function apiCall(method, data = {}, useAuth = false) {
    let url = `${API_BASE}${method}`;
    
    // Use GET for verify (avoids CSRF issues entirely)
    const forceGet = (method === 'verify_customer');

    const headers = {
        'Content-Type': 'application/json',
        'X-Frappe-CSRF-Token': ''
    };

    // We rely on HttpOnly cookie; no Authorization header required.
    
    try {
        if (!forceGet) {
            headers['X-Frappe-CSRF-Token'] = await ensureCsrfToken();
        }

        // If GET, append params to URL (Frappe expects args in querystring for GET)
        if (forceGet && data && typeof data === 'object') {
            const params = new URLSearchParams();
            Object.keys(data).forEach((k) => {
                const v = data[k];
                if (v === undefined || v === null) return;
                params.set(k, String(v));
            });
            const qs = params.toString();
            if (qs) url = `${url}?${qs}`;
        }

        const response = await fetch(url, {
            method: forceGet ? 'GET' : 'POST',
            headers: headers,
            credentials: 'same-origin',
            body: forceGet ? undefined : JSON.stringify(data)
        });

        if (!response.ok) {
            console.error('HTTP Error:', response.status, response.statusText);
            return {
                success: false,
                message: 'خطأ في الاتصال بالخادم: ' + response.status
            };
        }

        const result = await response.json();
        console.log('API Response:', url, result);

        if (result.message) {
            return result.message;
        }

        return result;
        
    } catch (error) {
        console.error('API Error:', error);
        return {
            success: false,
            message: 'حدث خطأ في الاتصال'
        };
    }
}

function getCsrfToken() {
    // Try to get CSRF token from frappe object or cookie
    if (typeof frappe !== 'undefined' && frappe.csrf_token) {
        return frappe.csrf_token;
    }

    // Check all possible CSRF cookie names
    const patterns = [
        /csrf_token=([^;]+)/,
        /CSRF Token=([^;]+)/i,
        /X-Frappe-CSRF-Token=([^;]+)/i
    ];

    for (const pattern of patterns) {
        const match = document.cookie.match(pattern);
        if (match && match[1]) {
            return decodeURIComponent(match[1]);
        }
    }

    // Debug: log all cookies
    console.log('All cookies:', document.cookie);
    return '';
}

// ============== Loading States ==============

function showLoading(container) {
    if (typeof container === 'string') {
        container = document.querySelector(container);
    }
    
    if (!container) return;
    
    container.innerHTML = `
        <div class="loading-overlay">
            <div class="spinner"></div>
        </div>
    `;
}

function hideLoading(container) {
    if (typeof container === 'string') {
        container = document.querySelector(container);
    }
    
    if (!container) return;
    
    const overlay = container.querySelector('.loading-overlay');
    if (overlay) {
        overlay.remove();
    }
}

function showSkeleton(container, count = 3) {
    if (typeof container === 'string') {
        container = document.querySelector(container);
    }
    
    if (!container) return;
    
    let skeletonHTML = '';
    for (let i = 0; i < count; i++) {
        skeletonHTML += `
            <div class="card">
                <div class="skeleton skeleton-image"></div>
                <div class="skeleton skeleton-text"></div>
                <div class="skeleton skeleton-text" style="width: 60%;"></div>
            </div>
        `;
    }
    
    container.innerHTML = skeletonHTML;
}

// ============== Alert Messages ==============

function ensureToastContainer() {
    let c = document.querySelector('.toast-container');
    if (c) return c;
    c = document.createElement('div');
    c.className = 'toast-container';
    document.body.appendChild(c);
    return c;
}

function showToast(message, type = 'info', timeoutMs = 3500) {
    const container = ensureToastContainer();
    const toast = document.createElement('div');
    const icon = type === 'success' ? '✓' : type === 'error' ? '!' : 'i';
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <div class="toast-icon">${icon}</div>
        <div class="toast-text"></div>
        <button class="toast-close" aria-label="إغلاق">×</button>
    `;
    toast.querySelector('.toast-text').textContent = String(message || '');
    toast.querySelector('.toast-close').addEventListener('click', () => toast.remove());
    container.appendChild(toast);

    window.setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-6px)';
        toast.style.transition = 'opacity .18s ease, transform .18s ease';
        window.setTimeout(() => toast.remove(), 200);
    }, timeoutMs);
}

// Toast notification system
function showToast(message, type = 'info', duration = 3000) {
    const toastContainer = document.getElementById('toastContainer') || createToastContainer();
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const icons = {
        success: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20,6 9,17 4,12"></polyline></svg>',
        error: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>',
        warning: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>',
        info: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>'
    };
    
    const titles = {
        success: 'نجاح',
        error: 'خطأ',
        warning: 'تنبيه',
        info: 'معلومة'
    };
    
    toast.innerHTML = `
        <div class="toast-icon">${icons[type] || icons.info}</div>
        <div class="toast-content">
            <div class="toast-title">${titles[type] || 'معلومة'}</div>
            <div class="toast-message">${message}</div>
        </div>
    `;
    
    toastContainer.appendChild(toast);
    
    // Remove after duration
    setTimeout(() => {
        toast.classList.add('hiding');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container';
    document.body.appendChild(container);
    return container;
}

function showSuccess(message) { showToast(message, 'success'); }
function showError(message) { showToast(message, 'error'); }
function showInfo(message) { showToast(message, 'info'); }

// ============== Modal Management ==============

function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('open');
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('open');
    }
}

// Close modal on outside click
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal')) {
        e.target.classList.remove('open');
    }
});

// ============== Format Helpers ==============

// Global currency variable (will be set from API)
let portalCurrency = 'SAR';
// Arabic UI with Latin digits (English numbers)
const PORTAL_LOCALE = 'ar-SA-u-nu-latn';

function setCurrency(currency) {
    // Use provided currency, fallback to SAR
    portalCurrency = currency || 'SAR';
}

function formatCurrency(amount, currency = null) {
    const curr = currency || portalCurrency || 'SAR';
    const num = (amount || 0).toFixed(2);
    
    // Currency symbols mapping
    const currencySymbols = {
        'SAR': 'ر.س',
        'USD': '$',
        'EUR': '€',
        'GBP': '£',
        'AED': 'د.إ',
        'QAR': 'ر.ق',
        'KWD': 'د.ك',
        'BHD': 'د.ب',
        'OMR': 'ر.ع',
        'EGP': 'ج.م',
        'ILS': '₪'
    };
    
    const symbol = currencySymbols[curr] || curr;
    
    // For Arabic/Hebrew, place symbol after number (like ERPNext)
    if (curr === 'SAR' || curr === 'AED' || curr === 'QAR' || curr === 'KWD' || curr === 'BHD' || curr === 'OMR' || curr === 'EGP' || curr === 'ILS') {
        return `${num} ${symbol}`;
    }
    
    // For Western currencies, place symbol before number
    if (curr === 'USD' || curr === 'EUR' || curr === 'GBP') {
        return `${symbol}${num}`;
    }
    
    // Default: symbol after number
    return `${num} ${symbol}`;
}

function formatDate(dateStr) {
    // If dateStr is already in YYYY-MM-DD format, return it as is
    if (typeof dateStr === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
        return dateStr;
    }
    
    // Handle date objects or other formats
    const date = new Date(dateStr);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function formatDateTime(dateStr) {
    const date = new Date(dateStr);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day} ${hours}:${minutes}`;
}

// ============== Empty State ==============

function showEmptyState(container, message, icon = '📦') {
    if (typeof container === 'string') {
        container = document.querySelector(container);
    }
    
    if (!container) return;
    
    container.innerHTML = `
        <div class="empty-state">
            <div class="empty-state-icon">${icon}</div>
            <div class="empty-state-text">${message}</div>
        </div>
    `;
}

// ============== Status Badge ==============

function getStatusBadge(status) {
    const statusMap = {
        'Paid': { class: 'badge-success', text: 'مدفوعة' },
        'Unpaid': { class: 'badge-danger', text: 'غير مدفوعة' },
        'Overdue': { class: 'badge-danger', text: 'متأخرة' },
        'Partly Paid': { class: 'badge-warning', text: 'مدفوعة جزئياً' },
        'Draft': { class: 'badge-info', text: 'مسودة' },
        'Submitted': { class: 'badge-info', text: 'مقدم' },
        'Completed': { class: 'badge-success', text: 'مكتمل' },
        'Cancelled': { class: 'badge-danger', text: 'ملغي' },
        'To Deliver and Bill': { class: 'badge-warning', text: 'للتسليم والفوترة' },
        'To Bill': { class: 'badge-warning', text: 'للفوترة' },
        'To Deliver': { class: 'badge-warning', text: 'للتسليم' }
    };
    
    const statusInfo = statusMap[status] || { class: 'badge-info', text: status };
    return `<span class="badge ${statusInfo.class}">${statusInfo.text}</span>`;
}

// ============== Image Placeholder ==============

function getImageSrc(image) {
    if (!image) {
        return 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="200" height="200"%3E%3Crect fill="%23e2e8f0" width="200" height="200"/%3E%3Ctext fill="%2364748b" font-size="20" x="50%25" y="50%25" text-anchor="middle" dominant-baseline="middle"%3Eلا توجد صورة%3C/text%3E%3C/svg%3E';
    }
    
    // If it's already a full URL, return it
    if (image.startsWith('http')) {
        return image;
    }
    
    // Otherwise, prepend the site URL
    return image;
}

// ============== Mobile Menu Toggle ==============

function initMobileMenu() {
    const menuBtn = document.querySelector('.mobile-menu-btn');
    const menu = document.querySelector('.navbar-menu');
    
    if (menuBtn && menu) {
        menuBtn.addEventListener('click', () => {
            menu.classList.toggle('open');
        });
    }
}

// ============== Bottom Sheet ==============

function openSheet(sheetId) {
    const sheet = document.getElementById(sheetId);
    if (!sheet) return;
    sheet.classList.add('open');
    document.body.style.overflow = 'hidden';
}

function closeSheet(sheetId) {
    const sheet = document.getElementById(sheetId);
    if (!sheet) return;
    sheet.classList.remove('open');
    document.body.style.overflow = '';
}

function bindSheet(sheetId) {
    const sheet = document.getElementById(sheetId);
    if (!sheet) return;
    const backdrop = sheet.querySelector('.sheet-backdrop');
    if (backdrop) backdrop.addEventListener('click', () => closeSheet(sheetId));
    sheet.querySelectorAll('[data-sheet-close]').forEach((btn) => {
        btn.addEventListener('click', () => closeSheet(sheetId));
    });
}

// ============== Search Debounce ==============

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// ============== Local Storage Cart ==============

function getCart() {
    const cart = localStorage.getItem('customer_cart');
    return cart ? JSON.parse(cart) : [];
}

function saveCart(cart) {
    localStorage.setItem('customer_cart', JSON.stringify(cart));
}

function addToCart(item) {
    const cart = getCart();
    
    // Check if item exists
    const existingIndex = cart.findIndex(i => i.item_code === item.item_code);
    
    if (existingIndex >= 0) {
        cart[existingIndex].qty += item.qty || 1;
    } else {
        cart.push({
            item_code: item.item_code,
            item_name: item.item_name,
            rate: item.rate,
            qty: item.qty || 1,
            image: item.image
        });
    }
    
    saveCart(cart);
    updateCartBadge();
    showSuccess('تم إضافة المنتج إلى السلة');
}

function removeFromCart(item_code) {
    let cart = getCart();
    cart = cart.filter(i => i.item_code !== item_code);
    saveCart(cart);
    updateCartBadge();
}

function updateCartItem(item_code, qty) {
    const cart = getCart();
    const item = cart.find(i => i.item_code === item_code);
    
    if (item) {
        if (qty <= 0) {
            removeFromCart(item_code);
        } else {
            item.qty = qty;
            saveCart(cart);
        }
    }
}

function clearCart() {
    localStorage.removeItem('customer_cart');
    updateCartBadge();
}

function getCartTotal() {
    const cart = getCart();
    return cart.reduce((total, item) => total + (item.rate * item.qty), 0);
}

function getCartCount() {
    const cart = getCart();
    return cart.reduce((total, item) => total + item.qty, 0);
}

function updateCartBadge() {
    const badge = document.querySelector('.cart-badge');
    if (badge) {
        const count = getCartCount();
        badge.textContent = count;
        badge.style.display = count > 0 ? 'inline-block' : 'none';
    }
}

// ============== Initialize ==============

document.addEventListener('DOMContentLoaded', () => {
    initMobileMenu();
    updateCartBadge();
});

