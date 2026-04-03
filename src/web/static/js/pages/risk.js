/**
 * Phantom — Risk & Portfolio Page (Phase 2 Enhanced)
 */

async function renderRisk(container) {
    container.innerHTML = '<div class="loading" style="margin:16px"></div>';

    const [metrics, portfolio, filterData, openTrades, circuitBreakers, stratHealth, filterDetail, portDetail] = await Promise.all([
        API.riskMetrics(), API.portfolio(), API.filterValidation(), API.openTrades(),
        API.circuitBreakers(), API.strategyHealth(), API.filterValidationDetail(), API.portfolioRiskDetail(),
    ]);

    container.innerHTML = `
        <div class="section" id="cbSection">
            <div class="section-header"><span class="section-title">Circuit Breakers</span></div>
            <div class="card"><div class="card-body" id="circuitBreakersPanel"></div></div>
        </div>

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
            <div class="section-header"><span class="section-title">Strategy Health</span></div>
            <div class="risk-metrics-grid" id="strategyHealthGrid"></div>
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

    // --- Circuit Breakers Panel ---
    const cbEl = document.getElementById('circuitBreakersPanel');
    if (circuitBreakers && circuitBreakers.status) {
        const st = circuitBreakers.status;
        const statusColor = st.trading_allowed ? 'var(--green)' : 'var(--red)';
        const statusText = st.trading_allowed ? 'ACTIVE' : 'HALTED';
        const multText = st.size_multiplier < 1.0 ? ` (sizing at ${(st.size_multiplier * 100).toFixed(0)}%)` : '';

        let warningsHtml = '';
        if (st.warnings && st.warnings.length > 0) {
            warningsHtml = st.warnings.map(w => `<div style="color:var(--orange);font-size:12px;margin-top:4px">&#9888; ${w}</div>`).join('');
        }
        let reasonsHtml = '';
        if (st.reasons && st.reasons.length > 0) {
            reasonsHtml = st.reasons.map(r => `<div style="color:var(--red);font-size:12px;margin-top:4px">&#10006; ${r}</div>`).join('');
        }

        let eventsHtml = '';
        if (circuitBreakers.active_events && circuitBreakers.active_events.length > 0) {
            eventsHtml = '<div style="margin-top:12px;font-size:12px;color:var(--text-tertiary)"><strong>Active Events:</strong></div>';
            eventsHtml += circuitBreakers.active_events.map(e =>
                `<div style="display:flex;align-items:center;gap:8px;margin-top:4px;font-size:12px">
                    <span style="color:var(--red)">${e.breaker_type}</span>
                    <span class="c-muted">${e.triggered_at}</span>
                    <span class="c-muted">${e.action_taken}</span>
                </div>`
            ).join('');
        }

        cbEl.innerHTML = `
            <div style="display:flex;align-items:center;gap:12px">
                <div style="width:12px;height:12px;border-radius:50%;background:${statusColor};box-shadow:0 0 6px ${statusColor}"></div>
                <div>
                    <span style="font-weight:600;color:${statusColor}">${statusText}</span>${multText}
                </div>
            </div>
            ${warningsHtml}${reasonsHtml}${eventsHtml}
        `;
    } else {
        cbEl.innerHTML = '<div class="c-muted" style="font-size:13px">Circuit breaker data unavailable</div>';
    }

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

    // Exposure section (enhanced with direction balance)
    const expEl = document.getElementById('exposureSection');
    if (portfolio) {
        const maxPos = portfolio.max_positions || 5;
        const bankroll = portfolio.bankroll || 10000;
        const exposure = portfolio.total_exposure || 0;
        const openCount = portfolio.open_positions || 0;
        const exposurePct = bankroll > 0 ? (exposure / bankroll * 100) : 0;

        let dirHtml = '';
        if (portDetail && portDetail.direction_balance) {
            const db = portDetail.direction_balance;
            const longCount = (db.LONG || {}).count || 0;
            const shortCount = (db.SHORT || {}).count || 0;
            const total = longCount + shortCount;
            const longPct = total > 0 ? (longCount / total * 100).toFixed(0) : 0;
            dirHtml = `
                <div class="exposure-bar-row" style="margin-top:8px">
                    <span class="exposure-bar-label">Direction</span>
                    <div class="exposure-bar-track">
                        <div class="exposure-bar-fill progress-green" style="width:${longPct}%"></div>
                    </div>
                    <span class="exposure-bar-value">${longCount}L / ${shortCount}S</span>
                </div>
            `;
        }

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
            ${dirHtml}
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

    // --- Strategy Health Grid ---
    const shEl = document.getElementById('strategyHealthGrid');
    if (stratHealth && stratHealth.length > 0) {
        stratHealth.forEach(s => {
            const card = el('div', { className: 'risk-metric-card' });
            const statusColor = s.health_status === 'ACTIVE' ? 'c-green' : s.health_status === 'WARNING' ? 'c-orange' : 'c-red';
            const statusDot = s.health_status === 'ACTIVE' ? 'var(--green)' : s.health_status === 'WARNING' ? 'var(--orange)' : 'var(--red)';
            card.innerHTML = `
                <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
                    <span style="width:8px;height:8px;border-radius:50%;background:${statusDot}"></span>
                    <span class="${statusColor}" style="font-size:11px;font-weight:600">${s.health_status}</span>
                </div>
                <div class="risk-metric-value" style="text-transform:capitalize;font-size:14px">${s.strategy.replace('_', ' ')}</div>
                <div class="risk-metric-label">
                    All-time: ${s.all_time_win_rate}% (${s.all_time_total})<br>
                    Rolling: ${s.rolling_win_rate}% (${s.rolling_total})<br>
                    P&L: <span class="${pnlClass(s.all_time_pnl)}">${formatMoney(s.all_time_pnl, true)}</span>
                </div>
            `;
            shEl.appendChild(card);
        });
    } else {
        shEl.innerHTML = '<div class="c-muted" style="padding:16px">Strategy health data will appear after trades are settled</div>';
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

    // Filter validation (enhanced with alpha and detail)
    const filterEl = document.getElementById('filterSection');
    const alpha = filterDetail && filterDetail.alpha ? filterDetail.alpha : null;

    if (alpha && (alpha.passed_count > 0 || alpha.filtered_count > 0)) {
        const alphaColor = alpha.filter_alpha >= 0 ? 'c-green' : 'c-red';
        const alphaLabel = alpha.filter_alpha >= 0 ? 'FILTERS WORKING' : 'FILTERS MAY BE HURTING';

        let detailHtml = '';
        if (filterDetail.detail && filterDetail.detail.by_reason && filterDetail.detail.by_reason.length > 0) {
            detailHtml = `
                <div style="margin-top:16px;font-size:12px;color:var(--text-tertiary)"><strong>Per-Filter Breakdown:</strong></div>
                <div style="margin-top:8px">
                    ${filterDetail.detail.by_reason.map(r => `
                        <div style="display:flex;justify-content:space-between;padding:4px 0;font-size:12px;border-bottom:1px solid var(--border)">
                            <span style="color:var(--text-secondary)">${r.filter_reason || 'Unknown'}</span>
                            <span>
                                <span class="${winRateClass(r.hypothetical_win_rate)}">${r.hypothetical_win_rate}%</span>
                                <span class="c-muted">(${r.total} signals)</span>
                            </span>
                        </div>
                    `).join('')}
                </div>
            `;
        }

        filterEl.innerHTML = `
            <div class="filter-grid">
                <div class="filter-stat">
                    <div class="filter-stat-value">${alpha.passed_win_rate}%</div>
                    <div class="filter-stat-label">Passed Win Rate (${alpha.passed_count})</div>
                </div>
                <div class="filter-stat">
                    <div class="filter-stat-value">${alpha.filtered_win_rate}%</div>
                    <div class="filter-stat-label">Filtered Win Rate (${alpha.filtered_count})</div>
                </div>
                <div class="filter-stat">
                    <div class="filter-stat-value ${alphaColor}">${alpha.filter_alpha > 0 ? '+' : ''}${alpha.filter_alpha}%</div>
                    <div class="filter-stat-label">Filter Alpha</div>
                </div>
            </div>
            <div style="text-align:center;padding:12px 0 4px;font-size:13px">
                <span class="${alphaColor}" style="font-weight:600">${alphaLabel}</span>
            </div>
            ${detailHtml}
        `;
    } else if (filterData && filterData.total_tracked > 0) {
        // Fallback to old filter validation data
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
        `;
    } else {
        filterEl.innerHTML = '<div style="color:var(--text-tertiary);font-size:13px;padding:8px 0">Tracking filtered signal outcomes to validate filter quality. Data will appear once filtered signals reach their take profit or stop loss.</div>';
    }
}
