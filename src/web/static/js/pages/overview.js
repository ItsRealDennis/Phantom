/**
 * Phantom — Overview Page
 */

async function renderOverview(container) {
    container.innerHTML = `
        <div class="hero" id="heroSection">
            <div class="hero-card"><div class="hero-label">Bankroll</div><div class="hero-value" id="heroBankroll">--</div><div class="hero-sub" id="heroBankrollSub"></div></div>
            <div class="hero-card"><div class="hero-label">Total P&L</div><div class="hero-value" id="heroPnl">--</div><div class="hero-sub" id="heroPnlSub"></div></div>
            <div class="hero-card"><div class="hero-label">Win Rate</div><div class="hero-value" id="heroWinRate">--</div><div class="hero-sub" id="heroWinRateSub"></div></div>
            <div class="hero-card"><div class="hero-label">Signals</div><div class="hero-value" id="heroSignals">--</div><div class="hero-sub" id="heroSignalsSub"></div></div>
            <div class="hero-card"><div class="hero-label">ROI</div><div class="hero-value" id="heroRoi">--</div><div class="hero-sub" id="heroRoiSub"></div></div>
            <div class="hero-card"><div class="hero-label">Daily P&L</div><div class="hero-value" id="heroDailyPnl">--</div><div class="hero-sub" id="heroDailySpark"></div></div>
        </div>

        <div class="section">
            <div class="section-header">
                <span class="section-title">Performance</span>
                <div class="equity-controls" id="equityControls">
                    <button class="equity-range-btn" data-range="7">1W</button>
                    <button class="equity-range-btn" data-range="30">1M</button>
                    <button class="equity-range-btn" data-range="90">3M</button>
                    <button class="equity-range-btn active" data-range="0">ALL</button>
                </div>
            </div>
            <div class="card">
                <div class="chart-wrap"><canvas id="equityChart"></canvas></div>
                <div class="chart-empty" id="chartEmpty" style="display:none">Equity curve will appear after trades are settled</div>
            </div>
        </div>

        <div class="quick-glance" id="quickGlance">
            <div class="quick-glance-card">
                <div class="quick-glance-icon" style="background:var(--accent-soft);color:var(--accent)">
                    <svg viewBox="0 0 24 24"><path d="M20 12V8H6a2 2 0 0 1-2-2c0-1.1.9-2 2-2h12v4"/><path d="M4 6v12c0 1.1.9 2 2 2h14v-4"/><path d="M18 12a2 2 0 0 0 0 4h4v-4h-4z"/></svg>
                </div>
                <div class="quick-glance-text">
                    <div class="quick-glance-label">Open Positions</div>
                    <div class="quick-glance-value" id="qgPositions">--</div>
                </div>
            </div>
            <div class="quick-glance-card">
                <div class="quick-glance-icon" id="qgCBIcon" style="background:var(--green-soft);color:var(--green)">
                    <svg viewBox="0 0 24 24"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                </div>
                <div class="quick-glance-text">
                    <div class="quick-glance-label">Circuit Breakers</div>
                    <div class="quick-glance-value" id="qgCircuitBreaker">--</div>
                </div>
            </div>
            <div class="quick-glance-card">
                <div class="quick-glance-icon" style="background:var(--green-soft);color:var(--green)">
                    <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                </div>
                <div class="quick-glance-text">
                    <div class="quick-glance-label">Next Scan</div>
                    <div class="quick-glance-value" id="qgNextScan">--</div>
                </div>
            </div>
            <div class="quick-glance-card">
                <div class="quick-glance-icon" style="background:var(--purple-soft);color:var(--purple)">
                    <svg viewBox="0 0 24 24"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                </div>
                <div class="quick-glance-text">
                    <div class="quick-glance-label">Connection</div>
                    <div class="quick-glance-value" id="qgConnection">--</div>
                </div>
            </div>
        </div>

        <div class="grid-2 section">
            <div>
                <div class="section-header"><span class="section-title">Strategies</span></div>
                <div class="card" id="strategiesCard"><div class="loading" style="margin:16px"></div></div>
            </div>
            <div>
                <div class="section-header"><span class="section-title">Open Trades</span><span class="section-title c-muted" id="openCount"></span></div>
                <div class="card" id="openTradesCard"><div class="loading" style="margin:16px"></div></div>
            </div>
        </div>
    `;

    let equityChart = null;
    let fullEquityData = null;

    // Load all data
    const [overview, equity, strategies, openTrades, portfolio, scheduler, alpaca, dailyPnl, circuitBreakers] = await Promise.all([
        API.overview(), API.equityCurve(), API.strategies(), API.openTrades(),
        API.portfolio(), API.schedulerStatus(), API.alpacaStatus(), API.dailyPnl(7),
        API.circuitBreakers(),
    ]);

    // Hero KPIs
    if (overview) {
        document.getElementById('heroBankroll').textContent = formatMoney(overview.bankroll);
        document.getElementById('heroBankrollSub').innerHTML = `<span class="${pnlClass(overview.total_pnl)}">${formatMoney(overview.total_pnl, true)}</span> from ${formatMoney(overview.starting_bankroll || 10000)}`;

        document.getElementById('heroPnl').className = `hero-value ${pnlClass(overview.total_pnl)}`;
        document.getElementById('heroPnl').textContent = formatMoney(overview.total_pnl, true);
        document.getElementById('heroPnlSub').textContent = `${overview.settled} settled trades`;

        const wrClass = winRateClass(overview.win_rate);
        document.getElementById('heroWinRate').className = `hero-value ${wrClass}`;
        document.getElementById('heroWinRate').textContent = overview.settled > 0 ? overview.win_rate + '%' : '--';
        document.getElementById('heroWinRateSub').textContent = overview.settled > 0 ? `${overview.wins}W / ${overview.losses}L` : 'No settled trades';

        document.getElementById('heroSignals').textContent = overview.total_signals;
        document.getElementById('heroSignalsSub').textContent = `${overview.passed_filter} passed / ${overview.filtered_out} filtered`;

        document.getElementById('heroRoi').className = `hero-value ${pnlClass(overview.roi)}`;
        document.getElementById('heroRoi').textContent = overview.roi ? formatPct(overview.roi, true) : '--';
        document.getElementById('heroRoiSub').textContent = 'Return on investment';
    }

    // Daily P&L sparkline
    if (dailyPnl && dailyPnl.length > 0) {
        const todayPnl = dailyPnl[dailyPnl.length - 1]?.pnl || 0;
        document.getElementById('heroDailyPnl').className = `hero-value ${pnlClass(todayPnl)}`;
        document.getElementById('heroDailyPnl').textContent = formatMoney(todayPnl, true);
        const sparkContainer = document.getElementById('heroDailySpark');
        sparkContainer.innerHTML = '<span class="sparkline-container" id="dailySparkline"></span> last 7 days';
        createSparkline(document.getElementById('dailySparkline'), dailyPnl.map(d => d.pnl));
    }

    // Equity curve
    fullEquityData = equity;
    function renderEquityChart(range) {
        const canvas = document.getElementById('equityChart');
        const emptyEl = document.getElementById('chartEmpty');
        if (!fullEquityData || fullEquityData.length < 2) {
            canvas.style.display = 'none';
            emptyEl.style.display = 'flex';
            return;
        }
        canvas.style.display = 'block';
        emptyEl.style.display = 'none';

        let data = fullEquityData;
        if (range > 0) {
            const cutoff = new Date();
            cutoff.setDate(cutoff.getDate() - range);
            const cutoffStr = cutoff.toISOString().slice(0, 10);
            data = fullEquityData.filter(d => d[0] >= cutoffStr);
            if (data.length < 2) data = fullEquityData;
        }

        if (equityChart) equityChart.destroy();
        equityChart = createEquityChart(canvas.getContext('2d'), data.map(d => d[0]), data.map(d => d[1]));
    }
    renderEquityChart(0);

    // Equity range buttons
    document.querySelectorAll('.equity-range-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.equity-range-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            renderEquityChart(parseInt(btn.dataset.range));
        });
    });

    // Quick glance
    if (portfolio) {
        document.getElementById('qgPositions').textContent = `${portfolio.open_positions} / ${portfolio.max_positions}`;
    }
    if (scheduler && scheduler.length > 0) {
        const scanJob = scheduler.find(j => j.name.includes('scan'));
        if (scanJob && scanJob.next_run) {
            const next = new Date(scanJob.next_run);
            document.getElementById('qgNextScan').textContent = next.toLocaleString('en-US', { weekday: 'short', hour: 'numeric', minute: '2-digit', hour12: true });
        }
    }
    // Circuit breaker status
    if (circuitBreakers && circuitBreakers.status) {
        const cb = circuitBreakers.status;
        const qgCB = document.getElementById('qgCircuitBreaker');
        const qgCBIcon = document.getElementById('qgCBIcon');
        if (cb.trading_allowed) {
            if (cb.size_multiplier < 1.0) {
                qgCB.textContent = `Active (${(cb.size_multiplier * 100).toFixed(0)}%)`;
                qgCB.style.color = 'var(--orange)';
                qgCBIcon.style.background = 'var(--orange-soft)';
                qgCBIcon.style.color = 'var(--orange)';
            } else {
                qgCB.textContent = 'All Clear';
                qgCB.style.color = 'var(--green)';
            }
        } else {
            qgCB.textContent = 'HALTED';
            qgCB.style.color = 'var(--red)';
            qgCBIcon.style.background = 'var(--red-soft)';
            qgCBIcon.style.color = 'var(--red)';
        }
    }

    if (alpaca) {
        const qgConn = document.getElementById('qgConnection');
        if (!alpaca.enabled) { qgConn.textContent = 'Paper Mode'; qgConn.style.color = 'var(--text-tertiary)'; }
        else if (alpaca.connected) { qgConn.textContent = 'Alpaca Live'; qgConn.style.color = 'var(--green)'; }
        else { qgConn.textContent = 'Disconnected'; qgConn.style.color = 'var(--orange)'; }
    }

    // Strategies table
    const stratEl = document.getElementById('strategiesCard');
    if (strategies && strategies.length > 0) {
        const table = buildTable(
            ['Strategy', 'Signals', 'W', 'L', 'Win %', 'P&L'],
            strategies.map(s => ({
                cells: [
                    { html: `<span class="cell-ticker" style="text-transform:capitalize">${s.strategy.replace('_', ' ')}</span>` },
                    s.total,
                    s.wins,
                    s.losses,
                    { html: `<span class="${winRateClass(s.win_rate)}">${s.settled > 0 ? s.win_rate + '%' : '--'}</span>` },
                    { html: `<span class="${pnlClass(s.pnl)}">${formatMoney(s.pnl, true)}</span>` },
                ]
            }))
        );
        stratEl.innerHTML = '';
        stratEl.appendChild(table);
    } else {
        stratEl.innerHTML = '';
        stratEl.appendChild(buildEmptyState('', 'No strategy data', 'Run a scan to generate signals'));
    }

    // Open Trades
    const openEl = document.getElementById('openTradesCard');
    document.getElementById('openCount').textContent = openTrades?.length || '';
    if (openTrades && openTrades.length > 0) {
        const table = buildTable(
            ['Ticker', 'Strategy', 'Dir', 'Conf', 'Entry', 'R:R', 'Risk'],
            openTrades.map(t => ({
                cells: [
                    { html: `<span class="cell-ticker">${t.ticker}</span>` },
                    { html: `<span style="text-transform:capitalize">${t.strategy.replace('_', ' ')}</span>` },
                    { html: directionBadge(t.direction) },
                    t.confidence + '%',
                    { html: `<span class="cell-mono">$${t.entry_price.toFixed(2)}</span>` },
                    t.rr_ratio.toFixed(2),
                    { html: `<span>${t.position_size ? formatMoney(t.position_size) : '--'}</span>` },
                ]
            })),
            { onRowClick: (row) => Router.navigate('#/trade/' + openTrades[openTrades.indexOf(row)]) }
        );
        openEl.innerHTML = '';
        openEl.appendChild(table);

        // Make rows clickable to trade detail
        const rows = openEl.querySelectorAll('tbody tr');
        rows.forEach((tr, i) => {
            tr.classList.add('clickable');
            tr.addEventListener('click', () => Router.navigate('#/trade/' + openTrades[i].id));
        });
    } else {
        openEl.innerHTML = '';
        openEl.appendChild(buildEmptyState('', 'No open positions', 'Signals that pass filters become open trades'));
    }

    // Auto-refresh — full re-render every 30s
    const refreshInterval = setInterval(async () => {
        const [ov, ot, strats, port] = await Promise.all([
            API.overview(), API.openTrades(), API.strategies(), API.portfolio(),
        ]);
        if (ov) {
            document.getElementById('heroBankroll').textContent = formatMoney(ov.bankroll);
            document.getElementById('heroBankrollSub').innerHTML = `<span class="${pnlClass(ov.total_pnl)}">${formatMoney(ov.total_pnl, true)}</span> from ${formatMoney(ov.starting_bankroll || 10000)}`;
            document.getElementById('heroPnl').className = `hero-value ${pnlClass(ov.total_pnl)}`;
            document.getElementById('heroPnl').textContent = formatMoney(ov.total_pnl, true);
            document.getElementById('heroPnlSub').textContent = `${ov.settled} settled trades`;
            const wrClass = winRateClass(ov.win_rate);
            document.getElementById('heroWinRate').className = `hero-value ${wrClass}`;
            document.getElementById('heroWinRate').textContent = ov.settled > 0 ? ov.win_rate + '%' : '--';
            document.getElementById('heroWinRateSub').textContent = ov.settled > 0 ? `${ov.wins}W / ${ov.losses}L` : 'No settled trades';
            document.getElementById('heroSignals').textContent = ov.total_signals;
            document.getElementById('heroSignalsSub').textContent = `${ov.passed_filter} passed / ${ov.filtered_out} filtered`;
            document.getElementById('heroRoi').className = `hero-value ${pnlClass(ov.roi)}`;
            document.getElementById('heroRoi').textContent = ov.roi ? formatPct(ov.roi, true) : '--';
        }
        if (port) {
            document.getElementById('qgPositions').textContent = `${port.open_positions} / ${port.max_positions}`;
        }
        // Re-render strategies
        const stratEl = document.getElementById('strategiesCard');
        if (stratEl && strats && strats.length > 0) {
            const table = buildTable(
                ['Strategy', 'Signals', 'W', 'L', 'Win %', 'P&L'],
                strats.map(s => ({
                    cells: [
                        { html: `<span class="cell-ticker" style="text-transform:capitalize">${s.strategy.replace('_', ' ')}</span>` },
                        s.total, s.wins, s.losses,
                        { html: `<span class="${winRateClass(s.win_rate)}">${s.settled > 0 ? s.win_rate + '%' : '--'}</span>` },
                        { html: `<span class="${pnlClass(s.pnl)}">${formatMoney(s.pnl, true)}</span>` },
                    ]
                }))
            );
            stratEl.innerHTML = '';
            stratEl.appendChild(table);
        }
        // Re-render open trades
        const openEl = document.getElementById('openTradesCard');
        if (openEl && ot) {
            document.getElementById('openCount').textContent = ot.length || '';
            if (ot.length > 0) {
                const table = buildTable(
                    ['Ticker', 'Strategy', 'Dir', 'Conf', 'Entry', 'R:R', 'Risk'],
                    ot.map(t => ({
                        cells: [
                            { html: `<span class="cell-ticker">${t.ticker}</span>` },
                            { html: `<span style="text-transform:capitalize">${t.strategy.replace('_', ' ')}</span>` },
                            { html: directionBadge(t.direction) },
                            t.confidence + '%',
                            { html: `<span class="cell-mono">$${t.entry_price.toFixed(2)}</span>` },
                            t.rr_ratio.toFixed(2),
                            { html: `<span>${t.position_size ? formatMoney(t.position_size) : '--'}</span>` },
                        ]
                    }))
                );
                openEl.innerHTML = '';
                openEl.appendChild(table);
                openEl.querySelectorAll('tbody tr').forEach((tr, i) => {
                    tr.classList.add('clickable');
                    tr.addEventListener('click', () => Router.navigate('#/trade/' + ot[i].id));
                });
            } else {
                openEl.innerHTML = '';
                openEl.appendChild(buildEmptyState('', 'No open positions', 'Signals that pass filters become open trades'));
            }
        }
    }, 30000);

    return () => {
        clearInterval(refreshInterval);
        if (equityChart) equityChart.destroy();
    };
}
