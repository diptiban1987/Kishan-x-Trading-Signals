// Main utility functions
(function() {
    'use strict';

    // Global error handler
    window.onerror = function(msg, url, lineNo, columnNo, error) {
        console.error('Error: ' + msg + '\nURL: ' + url + '\nLine: ' + lineNo);
        return false;
    };

    // Currency formatting
    window.formatCurrency = function(value, currency) {
        currency = currency || 'USD';
        return new Intl.NumberFormat('en-US', { style: 'currency', currency: currency, minimumFractionDigits: 2 }).format(value || 0);
    };

    // Number formatting with decimals
    window.formatNumber = function(value, decimals) {
        decimals = decimals || 2;
        return Number(value || 0).toFixed(decimals);
    };

    // Date formatting
    window.formatDate = function(date) {
        if (!date) return 'N/A';
        return new Date(date).toLocaleDateString('en-IN', { year: 'numeric', month: 'short', day: 'numeric' });
    };

    // Time formatting
    window.formatTime = function(date) {
        if (!date) return 'N/A';
        return new Date(date).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
    };

    // Copy to clipboard
    window.copyToClipboard = function(text) {
        if (navigator.clipboard) {
            navigator.clipboard.writeText(text).then(function() {
                if (typeof showToast === 'function') showToast('Copied to clipboard', 'success');
            }).catch(function() {
                fallbackCopy(text);
            });
        } else {
            fallbackCopy(text);
        }
    };

    function fallbackCopy(text) {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        try {
            document.execCommand('copy');
            if (typeof showToast === 'function') showToast('Copied to clipboard', 'success');
        } catch (e) {
            if (typeof showToast === 'function') showToast('Failed to copy', 'error');
        }
        document.body.removeChild(ta);
    }

    console.log('Main utilities loaded');
})();
