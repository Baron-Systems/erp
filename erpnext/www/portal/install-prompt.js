/**
 * PWA Install Prompt Handler - Simple Version
 * Shows install button always, with manual fallback
 */

(function() {
    'use strict';

    let deferredPrompt = null;

    // Platform detection
    const isAndroid = /Android/i.test(navigator.userAgent);
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;

    // DOM elements
    const installSection = document.getElementById('installSection');
    const installBtn = document.getElementById('installBtn');

    /**
     * Initialize - show button always
     */
    function init() {
        if (!installSection || !installBtn) return;

        // Show section and button always
        installSection.style.display = 'block';
        installBtn.style.display = 'flex';

        // Listen for install prompt (Chrome only)
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            deferredPrompt = e;
        });
    }

    /**
     * Handle install button click
     */
    async function handleInstallClick() {
        // If automatic install available (Chrome)
        if (deferredPrompt) {
            deferredPrompt.prompt();
            const { outcome } = await deferredPrompt.userChoice;
            if (outcome === 'accepted') {
                alert('✅ تم تثبيت التطبيق!');
            }
            deferredPrompt = null;
            return;
        }

        // Show manual instructions
        let message = '';
        if (isIOS) {
            message = '📱 iPhone:\n\n' +
                     '1. اضغط زر المشاركة ⎋ في أسفل Safari\n' +
                     '2. اختر "إضافة إلى الشاشة الرئيسية"\n' +
                     '3. اضغط "إضافة"';
        } else if (isAndroid) {
            message = '📱 Android:\n\n' +
                     '1. اضغط النقاط الثلاث ⋮ في Chrome\n' +
                     '2. اختر "إضافة إلى الشاشة الرئيسية"\n' +
                     'أو "Install app"';
        } else {
            message = '📱 أي جهاز:\n\n' +
                     '1. افتح قائمة المتصفح\n' +
                     '2. ابحث عن "Add to Home Screen"\n' +
                     '3. اضغط "إضافة"';
        }

        alert(message);
    }

    // Setup
    if (installBtn) {
        installBtn.addEventListener('click', handleInstallClick);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
