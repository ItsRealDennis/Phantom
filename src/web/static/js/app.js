/**
 * Phantom — App Entry Point
 */

// Register routes
Router
    .on('/', renderOverview)
    .on('/trades', renderTrades)
    .on('/trade/:id', renderTradeDetail)
    .on('/strategies', renderStrategies)
    .on('/risk', renderRisk)
    .on('/settings', renderSettings);

// Initialize
Router.init('app');

// Load Alpaca status in topbar
async function loadAlpacaStatus() {
    const d = await API.alpacaStatus();
    const el = document.getElementById('alpacaStatus');
    if (!el) return;
    if (!d || !d.enabled) {
        el.innerHTML = '<span style="color:var(--text-tertiary)">Paper</span>';
    } else if (d.connected) {
        el.innerHTML = '<span style="color:var(--green)">Alpaca</span>';
    } else {
        el.innerHTML = '<span style="color:var(--orange)">Disconnected</span>';
    }
}
loadAlpacaStatus();

// Update refresh timestamp
function updateTimestamp() {
    const el = document.getElementById('lastRefresh');
    if (el) {
        el.textContent = new Date().toLocaleTimeString('en-US', {
            hour: 'numeric', minute: '2-digit', second: '2-digit'
        });
    }
}
updateTimestamp();

// Global refresh handler
function handleRefresh() {
    API.clearCache();
    Router.resolve();
    updateTimestamp();
    loadAlpacaStatus();
}

// Global scan/settle handlers
async function handleScan() {
    const btn = document.getElementById('scanBtn');
    if (btn) { btn.disabled = true; btn.textContent = 'Scanning...'; }
    showToast('Scan cycle started...', 'info');
    await API.triggerScan();
    setTimeout(() => {
        if (btn) { btn.disabled = false; btn.innerHTML = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" style="width:14px;height:14px"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5L14 14"/></svg> Scan'; }
        showToast('Scan complete', 'success');
        handleRefresh();
    }, 8000);
}

async function handleSettle() {
    const btn = document.getElementById('settleBtn');
    if (btn) { btn.disabled = true; btn.textContent = 'Settling...'; }
    showToast('Settlement started...', 'info');
    await API.triggerSettle();
    setTimeout(() => {
        if (btn) { btn.disabled = false; btn.innerHTML = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" style="width:14px;height:14px"><path d="M2 8h12M8 2v12"/></svg> Settle'; }
        showToast('Settlement complete', 'success');
        handleRefresh();
    }, 4000);
}

// Auto-refresh every 60s
setInterval(() => {
    handleRefresh();
}, 60000);
