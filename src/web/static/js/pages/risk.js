/**
 * Phantom — Risk & Portfolio Page
 */

async function renderRisk(container) {
    container.innerHTML = '<div class="loading" style="margin:16px"></div>';

    const [metrics, portfolio, filterData, openTrades] = await Promise.all([
        API.riskMetrics(), API.portfolio(), API.filterValidation(), API.openTrades(),
    ]);

    container.innerHTML = `
        <div class="section">
            <div class="section-header"><span class="section-title">Risk Metrics</span></div>
            <div class="risk-metrics-grid" id="riskMetrics"></div>
        </div>

        <div class="grid-2 section">
            <div>
                <div class="section-header"><span class="section-title">Portfolio Exposure</span></div>
                <div class="card">
                    <div class="card-body" id="exposureSection"></div>
                </div>
            </div>
            <div>
                <div class="section-header"><span class="section-title">Position Allocation</span></div>
                <div class="card">
                    <div class="chart-wrap" style="height:220px" id="allocationChartWrap">
                        <canvas id="allocationChart"></canvas>
                    </div>
                    <div id="allocationLegend" style="padding:0 24px 16px"></div>
                </div>
            </div>
        </div>

        <div class="section">
            <div class="section-header"><span class="section-title">Drawdown</span></div>
            <div class="card">
                <div class="chart-wrap" style="height:220px">
                    <canvas id="drawdownChart"></canvas>
                </div>
                <div class="chart-empty" id="drawdownEmpty" style="display:none">Drawdown data will appear after trades are settled</div>
            </div>
        </div>

        <div class="section">
            <div class="section-header"><span class="section-title">Filter Validation</span></div>
            <div class="card">
                <div class="card-body" id="filterSection"></div>
            </div>
        </div>
    `;

    // Risk metrics cards
    const metricsEl = document.getElementById('riskMetrics');
    const hasSettledTrades = metrics && (metrics.gross_profit > 0 || metrics.gross_loss > 0 || metrics.longest_win_streak > 0 || metrics.longest_loss_streak > 0);
    if (metrics && hasSettledTrades) {
        const items = [
            { label: 'Sharpe Ratio', value: metrics.sharpe_ratio.toFixed(2), color: metrics.sharpe_ratio >= 1 ? 'c-green' : metrics.sharpe_ratio >= 0 ? 'c-orange' : 'c-red' },
            { label: 'Max Drawdown', value: '-' + metrics.max_drawdown_pct.toFixed(2) + '%', color: 'c-red' },
            { label: 'Profit Factor', value: metrics.profit_factor.toFixed(2), color: metrics.profit_factor >= 1.5 ? 'c-green' : metrics.profit_factor >= 1 ? 'c-orange' : 'c-red' },
            { label: 'Avg Win', value: formatMoney(metrics.avg_win), color: 'c-green' },
            { label: 'Avg Loss', value: formatMoney(metrics.avg_loss), color: 'c-red' },
            { label: 'Win Streak', value: metrics.longest_win_streak, color: 'c-green' },
            { label: 'Loss Streak', value: metrics.longest_loss_streak, color: 'c-red' },
            { label: 'Gross Profit', value: formatMoney(metrics.gross_profit), color: 'c-green' },
        ];
        items.forEach(item => {
            const card = el('div', { className: 'risk-metric-card' });
            card.innerHTML = `
                <div class="risk-metric-value ${item.color}">${item.value}</div>
                <div class="risk-metric-label">${item.label}</div>
            `;
            metricsEl.appendChild(card);
        });
    } else {
        metricsEl.innerHTML = '<div class="c-muted" style="padding:16px">Waiting for settled trades — metrics will appear once positions are closed</div>';
    }

    // Exposure section
    const expEl = document.getElementById('exposureSection');
    if (portfolio) {
        const maxPos = portfolio.max_positions || 5;
        const bankroll = portfolio.bankroll || 10000;
        const exposure = portfolio.total_exposure || 0;
        const openCount = portfolio.open_positions || 0;
        const exposurePct = bankroll > 0 ? (exposure / bankroll * 100) : 0;

        expEl.innerHTML = `
            <div class="exposure-bar-row">
                <span class="exposure-bar-label">Positions</span>
                <div class="exposure-bar-track">
                    <div class="exposure-bar-fill ${openCount >= maxPos ? 'progress-red' : 'progress-accent'}" style="width:${openCount / maxPos * 100}%"></div>
                </div>
                <span class="exposure-bar-value">${openCount} / ${maxPos}</span>
            </div>
            <div class="exposure-bar-row">
                <span class="exposure-bar-label">Exposure</span>
                <div class="exposure-bar-track">
                    <div class="exposure-bar-fill ${exposurePct > 80 ? 'progress-orange' : 'progress-accent'}" style="width:${Math.min(exposurePct, 100)}%"></div>
                </div>
                <span class="exposure-bar-value">${formatMoney(exposure)}</span>
            </div>
            <div class="exposure-bar-row">
                <span class="exposure-bar-label">Bankroll</span>
                <div class="exposure-bar-track">
                    <div class="exposure-bar-fill progress-green" style="width:100%"></div>
                </div>
                <span class="exposure-bar-value">${formatMoney(bankroll)}</span>
            </div>
            <div style="margin-top:16px">
                <div class="stat-label">Total P&L</div>
                <div class="stat-value ${pnlClass(portfolio.total_pnl)}">${formatMoney(portfolio.total_pnl, true)}</div>
            </div>
            <div style="margin-top:12px">
                <div class="stat-label">ROI</div>
                <div class="stat-value ${pnlClass(portfolio.roi_pct)}">${formatPct(portfolio.roi_pct, true)}</div>
            </div>
        `;
    }

    // Position allocation doughnut
    if (openTrades && openTrades.length > 0) {
        const tickers = openTrades.map(t => t.ticker);
        const sizes = openTrades.map(t => t.position_size || 0);
        const ctx = document.getElementById('allocationChart').getContext('2d');
        createDoughnutChart(ctx, tickers, sizes);

        // Legend
        const legend = document.getElementById('allocationLegend');
        const colors = [ChartDefaults.colors.accent, ChartDefaults.colors.green, ChartDefaults.colors.orange, ChartDefaults.colors.purple, ChartDefaults.colors.cyan];
        legend.innerHTML = tickers.map((t, i) =>
            `<span style="display:inline-flex;align-items:center;gap:6px;margin-right:16px;font-size:12px;color:var(--text-secondary)">
                <span style="width:8px;height:8px;border-radius:50%;background:${colors[i % colors.length]}"></span>${t} (${formatMoney(sizes[i])})
            </span>`
        ).join('');
    } else {
        document.getElementById('allocationChartWrap').innerHTML = '<div class="chart-empty">No open positions to display</div>';
    }

    // Drawdown chart
    if (metrics && metrics.drawdown_series && metrics.drawdown_series.length > 0) {
        const ddCtx = document.getElementById('drawdownChart').getContext('2d');
        createDrawdownChart(
            ddCtx,
            metrics.drawdown_series.map(d => d.date),
            metrics.drawdown_series.map(d => d.drawdown_pct)
        );
    } else {
        document.getElementById('drawdownChart').style.display = 'none';
        document.getElementById('drawdownEmpty').style.display = 'flex';
    }

    // Filter validation
    const filterEl = document.getElementById('filterSection');
    if (filterData && filterData.total_tracked > 0) {
        const passedWR = metrics ? (metrics.gross_profit > 0 ? 'Higher' : 'Lower') : '--';
        filterEl.innerHTML = `
            <div class="filter-grid">
                <div class="filter-stat">
                    <div class="filter-stat-value">${filterData.total_tracked}</div>
                    <div class="filter-stat-label">Filtered Tracked</div>
                </div>
                <div class="filter-stat">
                    <div class="filter-stat-value c-green">${filterData.would_have_won}</div>
                    <div class="filter-stat-label">Would've Won</div>
                </div>
                <div class="filter-stat">
                    <div class="filter-stat-value c-red">${filterData.would_have_lost}</div>
                    <div class="filter-stat-label">Would've Lost</div>
                </div>
            </div>
            <div style="text-align:center;padding:16px 0 4px;font-size:13px;color:var(--text-tertiary)">
                Hypothetical win rate of filtered signals: <strong class="${winRateClass(filterData.hypothetical_win_rate)}">${filterData.hypothetical_win_rate}%</strong>
            </div>
            <div style="text-align:center;font-size:12px;color:var(--text-tertiary)">
                ${filterData.hypothetical_win_rate < 50 ? 'Filters are effectively blocking losing trades' : 'Some profitable trades are being filtered out'}
            </div>
        `;
    } else {
        filterEl.innerHTML = '<div style="color:var(--text-tertiary);font-size:13px;padding:8px 0">Tracking filtered signal outcomes to validate filter quality. Data will appear once filtered signals reach their take profit or stop loss.</div>';
    }
}
