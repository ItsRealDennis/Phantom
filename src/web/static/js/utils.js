/**
 * Phantom — Utility functions
 */

function pnlClass(val) {
    if (val > 0) return 'c-green';
    if (val < 0) return 'c-red';
    return 'c-muted';
}

function formatMoney(val, showSign = false) {
    if (val === null || val === undefined) return '--';
    const abs = Math.abs(val);
    let str;
    if (abs >= 1e6) str = '$' + (abs / 1e6).toFixed(2) + 'M';
    else if (abs >= 1e3) str = '$' + abs.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    else str = '$' + abs.toFixed(2);
    if (showSign) return (val >= 0 ? '+' : '-') + str;
    if (val < 0) return '-' + str;
    return str;
}

function formatPct(val, showSign = false) {
    if (val === null || val === undefined) return '--';
    const prefix = showSign && val >= 0 ? '+' : '';
    return prefix + val.toFixed(1) + '%';
}

function formatDate(dateStr) {
    if (!dateStr) return '--';
    return dateStr.slice(0, 10);
}

function formatDateTime(dateStr) {
    if (!dateStr) return '--';
    try {
        const d = new Date(dateStr);
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' +
               d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    } catch { return dateStr.slice(0, 16); }
}

function directionBadge(dir) {
    return dir === 'LONG'
        ? '<span class="badge badge-long">LONG</span>'
        : '<span class="badge badge-short">SHORT</span>';
}

function statusBadge(status) {
    return `<span class="badge badge-${status}">${status.toUpperCase()}</span>`;
}

function filterBadge(passed) {
    return passed
        ? '<span class="badge badge-pass">PASS</span>'
        : '<span class="badge badge-skip">SKIP</span>';
}

function winRateClass(rate) {
    if (rate >= 55) return 'c-green';
    if (rate >= 50) return 'c-orange';
    if (rate > 0) return 'c-red';
    return 'c-muted';
}

function el(tag, attrs = {}, ...children) {
    const element = document.createElement(tag);
    for (const [key, val] of Object.entries(attrs)) {
        if (key === 'className') element.className = val;
        else if (key === 'innerHTML') element.innerHTML = val;
        else if (key === 'textContent') element.textContent = val;
        else if (key.startsWith('on')) element.addEventListener(key.slice(2).toLowerCase(), val);
        else if (key === 'style' && typeof val === 'object') Object.assign(element.style, val);
        else element.setAttribute(key, val);
    }
    for (const child of children) {
        if (typeof child === 'string') element.appendChild(document.createTextNode(child));
        else if (child) element.appendChild(child);
    }
    return element;
}

// Toast system
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const icons = { success: '\u2713', info: '\u2139', error: '\u2717' };
    const toast = el('div', { className: `toast toast-${type}` },
        el('span', { className: 'toast-icon', textContent: icons[type] || '' }),
        el('span', { textContent: message }),
        el('div', { className: 'toast-progress' })
    );
    container.appendChild(toast);
    setTimeout(() => {
        toast.classList.add('removing');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function parseJSON(str) {
    if (!str) return [];
    try { return JSON.parse(str); } catch { return []; }
}
