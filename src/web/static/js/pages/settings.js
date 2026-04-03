/**
 * Phantom — System/Settings Page
 */

async function renderSettings(container) {
    container.innerHTML = '<div class="loading" style="margin:16px"></div>';

    const [scheduler, alpaca, alpacaAccount, portfolio] = await Promise.all([
        API.schedulerStatus(), API.alpacaStatus(), API.alpacaAccount(), API.portfolio(),
    ]);

    container.innerHTML = `
        <div class="grid-2 section">
            <div>
                <div class="section-header"><span class="section-title">Actions</span></div>
                <div class="card">
                    <div class="card-body" style="display:flex;flex-direction:column;gap:16px">
                        <div style="display:flex;align-items:center;justify-content:space-between">
                            <div>
                                <div style="font-size:15px;font-weight:500;margin-bottom:4px">Scan Now</div>
                                <div style="font-size:12px;color:var(--text-tertiary)">Run all screeners and analyze top setups with Claude</div>
                            </div>
                            <button class="btn btn-accent" id="scanBtn" onclick="handleScan()">
                                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" style="width:14px;height:14px"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5L14 14"/></svg>
                                Scan
                            </button>
                        </div>
                        <div style="border-top:1px solid var(--border)"></div>
                        <div style="display:flex;align-items:center;justify-content:space-between">
                            <div>
                                <div style="font-size:15px;font-weight:500;margin-bottom:4px">Settle Trades</div>
                                <div style="font-size:12px;color:var(--text-tertiary)">Check open positions against current prices and settle</div>
                            </div>
                            <button class="btn" id="settleBtn" onclick="handleSettle()">
                                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" style="width:14px;height:14px"><path d="M2 8h12M8 2v12"/></svg>
                                Settle
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            <div>
                <div class="section-header"><span class="section-title">Connection</span></div>
                <div class="card">
                    <div class="card-body" id="connectionCard"></div>
                </div>
            </div>
        </div>

        <div class="section">
            <div class="section-header"><span class="section-title">Scheduler</span></div>
            <div class="card">
                <div id="schedulerSection"><div class="loading" style="margin:16px"></div></div>
            </div>
        </div>

        <div class="section">
            <div class="section-header"><span class="section-title">Configuration</span></div>
            <div class="card">
                <div class="card-body">
                    <div class="config-grid" id="configGrid"></div>
                </div>
            </div>
        </div>
    `;

    // Connection
    const connEl = document.getElementById('connectionCard');
    if (alpaca && alpaca.enabled && alpaca.connected && alpacaAccount) {
        connEl.innerHTML = `
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">
                <span style="width:10px;height:10px;border-radius:50%;background:var(--green)"></span>
                <span style="font-size:15px;font-weight:500;color:var(--green)">Alpaca Connected</span>
            </div>
            <div class="stats-grid">
                <div><div class="stat-label">Equity</div><div class="stat-value">${formatMoney(alpacaAccount.equity)}</div></div>
                <div><div class="stat-label">Cash</div><div class="stat-value">${formatMoney(alpacaAccount.cash)}</div></div>
                <div><div class="stat-label">Buying Power</div><div class="stat-value">${formatMoney(alpacaAccount.buying_power)}</div></div>
                <div><div class="stat-label">Day P&L</div><div class="stat-value ${pnlClass(alpacaAccount.day_pnl)}">${formatMoney(alpacaAccount.day_pnl, true)}</div></div>
            </div>
        `;
    } else {
        connEl.innerHTML = `
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
                <span style="width:10px;height:10px;border-radius:50%;background:var(--text-tertiary)"></span>
                <span style="font-size:15px;font-weight:500;color:var(--text-tertiary)">Paper Trading Mode</span>
            </div>
            <div style="font-size:13px;color:var(--text-tertiary);line-height:1.5">
                Set <code style="background:rgba(255,255,255,0.06);padding:2px 6px;border-radius:4px">ALPACA_API_KEY</code> and
                <code style="background:rgba(255,255,255,0.06);padding:2px 6px;border-radius:4px">ALPACA_SECRET_KEY</code>
                environment variables to enable live trading.
            </div>
            ${portfolio ? `
            <div style="margin-top:16px">
                <div class="stat-label">Paper Bankroll</div>
                <div class="stat-value">${formatMoney(portfolio.bankroll || 10000)}</div>
            </div>
            ` : ''}
        `;
    }

    // Scheduler
    const schedEl = document.getElementById('schedulerSection');
    if (scheduler && scheduler.length > 0) {
        let html = '<div class="scheduler-grid">';
        for (const j of scheduler) {
            const nextStr = j.next_run
                ? new Date(j.next_run).toLocaleString('en-US', { weekday: 'short', hour: 'numeric', minute: '2-digit', hour12: true, timeZoneName: 'short' })
                : 'Not scheduled';
            html += `<div class="sched-pill">
                <div class="sched-dot"></div>
                <div class="sched-info">
                    <div class="sched-name">${j.name}</div>
                    <div class="sched-next">Next: ${nextStr}</div>
                </div>
            </div>`;
        }
        html += '</div>';
        schedEl.innerHTML = html;
    } else {
        schedEl.innerHTML = '<div class="empty">Scheduler not running</div>';
    }

    // Configuration
    const configEl = document.getElementById('configGrid');
    const configs = [
        { key: 'Min Confidence', value: '55%' },
        { key: 'Min R:R Ratio', value: '1.5' },
        { key: 'Max Position %', value: '1.5%' },
        { key: 'Max Open Positions', value: '5' },
        { key: 'Max Sector Exposure', value: '30%' },
        { key: 'Max Daily Loss', value: '3%' },
        { key: 'Edge Shrinkage', value: '50%' },
        { key: 'Starting Bankroll', value: '$10,000' },
        { key: 'Strategies', value: 'MR, BO, MOM' },
        { key: 'Timeframes', value: '5m-1d' },
        { key: 'AI Model', value: 'Claude Sonnet 4' },
        { key: 'Trade Expiry', value: '5 days' },
    ];
    configs.forEach(c => {
        const item = el('div', { className: 'config-item' });
        item.innerHTML = `<span class="config-key">${c.key}</span><span class="config-value">${c.value}</span>`;
        configEl.appendChild(item);
    });
}
