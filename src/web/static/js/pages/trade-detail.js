/**
 * Phantom — Trade Detail Page
 */

async function renderTradeDetail(container, params) {
    const id = params.id;
    container.innerHTML = '<div class="loading" style="margin:16px"></div>';

    const signal = await API.signalDetail(id);
    if (!signal) {
        container.innerHTML = '';
        container.appendChild(buildEmptyState('?', 'Signal not found', `Signal #${id} does not exist`));
        return;
    }

    const confluences = parseJSON(signal.confluences);
    const warnings = parseJSON(signal.warnings);
    const isSettled = ['won', 'lost', 'stopped', 'expired'].includes(signal.status);

    container.innerHTML = `
        <div class="back-link" onclick="Router.navigate('#/trades')">
            <svg viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"/></svg>
            Back to Journal
        </div>

        <div class="trade-header">
            <span class="trade-ticker">${signal.ticker}</span>
            <div class="trade-badges">
                ${directionBadge(signal.direction)}
                <span class="badge badge-${signal.status}">${signal.status.toUpperCase()}</span>
                <span class="pill pill-blue" style="text-transform:capitalize">${signal.strategy.replace('_', ' ')}</span>
                ${signal.execution_mode === 'alpaca' ? '<span class="badge badge-open">ALPACA</span>' : '<span class="badge badge-skip">PAPER</span>'}
            </div>
            ${isSettled && signal.real_pnl !== null ? `
                <div class="trade-pnl">
                    <div class="trade-pnl-value ${pnlClass(signal.real_pnl)}">${formatMoney(signal.real_pnl, true)}</div>
                    <div class="trade-pnl-label">Realized P&L</div>
                </div>
            ` : ''}
        </div>

        <!-- Price Levels -->
        <div class="analysis-card">
            <div class="analysis-card-title">Price Levels</div>
            <div id="priceLevels"></div>
            <div style="height: 32px"></div>
            <div class="stats-grid" style="margin-top:16px">
                <div>
                    <div class="stat-label">Entry</div>
                    <div class="stat-value cell-mono">$${signal.entry_price.toFixed(2)}</div>
                </div>
                <div>
                    <div class="stat-label">Stop Loss</div>
                    <div class="stat-value cell-mono c-red">$${signal.stop_loss.toFixed(2)}</div>
                </div>
                <div>
                    <div class="stat-label">Take Profit</div>
                    <div class="stat-value cell-mono c-green">$${signal.take_profit.toFixed(2)}</div>
                </div>
                <div>
                    <div class="stat-label">Risk : Reward</div>
                    <div class="stat-value">${signal.rr_ratio.toFixed(2)}</div>
                </div>
            </div>
        </div>

        <!-- Claude's Analysis -->
        ${signal.reasoning ? `
        <div class="analysis-card">
            <div class="analysis-card-title">Claude's Analysis</div>
            <div class="analysis-reasoning">${signal.reasoning}</div>
        </div>
        ` : ''}

        <!-- Confluences & Warnings -->
        ${confluences.length > 0 || warnings.length > 0 ? `
        <div class="grid-2 section">
            ${confluences.length > 0 ? `
            <div class="analysis-card" style="margin-bottom:0">
                <div class="analysis-card-title">Confluences</div>
                <div class="analysis-pills">
                    ${confluences.map(c => `<span class="pill pill-green">${c}</span>`).join('')}
                </div>
            </div>
            ` : ''}
            ${warnings.length > 0 ? `
            <div class="analysis-card" style="margin-bottom:0">
                <div class="analysis-card-title">Warnings</div>
                <div class="analysis-pills">
                    ${warnings.map(w => `<span class="pill pill-orange">${w}</span>`).join('')}
                </div>
            </div>
            ` : ''}
        </div>
        ` : ''}

        <!-- Key Risks -->
        ${signal.key_risks ? `
        <div class="risk-card" style="margin-bottom:24px">
            <div class="risk-card-title">Key Risks</div>
            <div class="risk-card-text">${signal.key_risks}</div>
        </div>
        ` : ''}

        <!-- Trade Metadata -->
        <div class="analysis-card">
            <div class="analysis-card-title">Trade Details</div>
            <div class="metadata-grid">
                <div class="metadata-item">
                    <div class="metadata-label">Signal ID</div>
                    <div class="metadata-value">#${signal.id}</div>
                </div>
                <div class="metadata-item">
                    <div class="metadata-label">Created</div>
                    <div class="metadata-value">${formatDateTime(signal.created_at)}</div>
                </div>
                <div class="metadata-item">
                    <div class="metadata-label">Timeframe</div>
                    <div class="metadata-value">${signal.timeframe}</div>
                </div>
                <div class="metadata-item">
                    <div class="metadata-label">Confidence</div>
                    <div class="metadata-value">${signal.confidence}%</div>
                </div>
                <div class="metadata-item">
                    <div class="metadata-label">Kelly %</div>
                    <div class="metadata-value">${signal.kelly_pct ? signal.kelly_pct.toFixed(2) + '%' : '--'}</div>
                </div>
                <div class="metadata-item">
                    <div class="metadata-label">Position Size</div>
                    <div class="metadata-value">${signal.position_size ? formatMoney(signal.position_size) : '--'}</div>
                </div>
                <div class="metadata-item">
                    <div class="metadata-label">Shares</div>
                    <div class="metadata-value">${signal.shares || '--'}</div>
                </div>
                <div class="metadata-item">
                    <div class="metadata-label">Filter</div>
                    <div class="metadata-value">${signal.passed_filter ? '<span class="c-green">Passed</span>' : '<span class="c-red">Filtered</span>'}</div>
                </div>
                ${signal.filter_reason ? `
                <div class="metadata-item">
                    <div class="metadata-label">Filter Reason</div>
                    <div class="metadata-value" style="font-size:13px">${signal.filter_reason}</div>
                </div>
                ` : ''}
                ${signal.fill_price ? `
                <div class="metadata-item">
                    <div class="metadata-label">Fill Price</div>
                    <div class="metadata-value cell-mono">$${signal.fill_price.toFixed(2)}</div>
                </div>
                ` : ''}
                ${signal.exit_price ? `
                <div class="metadata-item">
                    <div class="metadata-label">Exit Price</div>
                    <div class="metadata-value cell-mono">$${signal.exit_price.toFixed(2)}</div>
                </div>
                ` : ''}
                ${signal.execution_mode === 'alpaca' && signal.alpaca_order_id ? `
                <div class="metadata-item">
                    <div class="metadata-label">Alpaca Order</div>
                    <div class="metadata-value" style="font-size:11px;font-family:monospace">${signal.alpaca_order_id.slice(0, 12)}...</div>
                </div>
                ` : ''}
            </div>
        </div>

        <!-- Timeline -->
        <div class="analysis-card">
            <div class="analysis-card-title">Timeline</div>
            <div id="tradeTimeline"></div>
        </div>

        ${signal.notes ? `
        <div class="analysis-card">
            <div class="analysis-card-title">Notes</div>
            <div class="analysis-reasoning">${signal.notes}</div>
        </div>
        ` : ''}
    `;

    // Render price bar
    const priceLevelsEl = document.getElementById('priceLevels');
    priceLevelsEl.appendChild(buildPriceBar(
        signal.entry_price,
        signal.stop_loss,
        signal.take_profit,
        signal.exit_price || null
    ));

    // Render timeline
    const timelineEl = document.getElementById('tradeTimeline');
    const steps = [
        { label: 'Created', value: formatDateTime(signal.created_at), done: true, active: true },
    ];
    if (signal.passed_filter) {
        steps.push({ label: 'Passed Filter', value: '', done: true, active: true });
    } else {
        steps.push({ label: 'Filtered', value: signal.filter_reason || '', error: true, active: true });
    }
    if (signal.fill_price) {
        steps.push({ label: 'Filled', value: '$' + signal.fill_price.toFixed(2), done: true, active: true });
    }
    if (isSettled) {
        const isWin = signal.status === 'won';
        steps.push({
            label: 'Settled',
            value: formatDateTime(signal.settled_at) + (signal.real_pnl !== null ? ` (${formatMoney(signal.real_pnl, true)})` : ''),
            done: isWin,
            error: !isWin && signal.status !== 'expired',
            active: true,
        });
    } else if (signal.status === 'open') {
        steps.push({ label: 'Awaiting', value: 'Position open', active: false });
    }
    timelineEl.appendChild(buildTimeline(steps));
}
