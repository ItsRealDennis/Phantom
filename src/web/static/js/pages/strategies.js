/**
 * Phantom — Strategy Lab Page
 */

async function renderStrategies(container) {
    container.innerHTML = '<div class="loading" style="margin:16px"></div>';

    const data = await API.strategiesDetailed();
    if (!data || data.length === 0) {
        container.innerHTML = '';
        container.appendChild(buildEmptyState('', 'No strategy data yet', 'Run a scan to generate signals across strategies'));
        return;
    }

    container.innerHTML = `
        <div class="section">
            <div class="section-header"><span class="section-title">P&L by Strategy</span></div>
            <div class="card">
                <div class="chart-wrap" style="height:${Math.max(200, data.length * 60)}px">
                    <canvas id="strategyPnlChart"></canvas>
                </div>
            </div>
        </div>

        <div class="section">
            <div class="section-header"><span class="section-title">Strategy Breakdown</span></div>
            <div class="strategy-cards" id="strategyCards"></div>
        </div>

        <div class="section">
            <div class="section-header"><span class="section-title">P&L Distribution</span></div>
            <div class="card">
                <div class="chart-wrap" style="height:250px">
                    <canvas id="pnlDistChart"></canvas>
                </div>
            </div>
        </div>
    `;

    // P&L bar chart
    const pnlCtx = document.getElementById('strategyPnlChart').getContext('2d');
    const labels = data.map(s => s.strategy.replace('_', ' '));
    const values = data.map(s => s.pnl);
    const barChart = createBarChart(pnlCtx, labels, values);

    // Strategy cards
    const cardsContainer = document.getElementById('strategyCards');
    data.forEach(s => {
        const wr = s.settled > 0 ? s.win_rate : 0;
        const wrColor = winRateClass(wr);

        const card = el('div', { className: 'strategy-card' });
        card.innerHTML = `
            <div class="strategy-card-header">
                <span class="strategy-card-name">${s.strategy.replace('_', ' ')}</span>
                <span class="strategy-card-pnl ${pnlClass(s.pnl)}">${formatMoney(s.pnl, true)}</span>
            </div>
            <div style="display:flex;align-items:center;gap:20px;margin-bottom:20px">
                <div style="position:relative;width:72px;height:72px;flex-shrink:0">
                    <canvas id="donut_${s.strategy}" width="72" height="72"></canvas>
                    <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:14px;font-weight:600" class="${wrColor}">
                        ${s.settled > 0 ? s.win_rate + '%' : '--'}
                    </div>
                </div>
                <div style="flex:1">
                    <div style="display:flex;gap:16px;margin-bottom:8px">
                        <span class="c-green" style="font-size:14px;font-weight:500">${s.wins}W</span>
                        <span class="c-red" style="font-size:14px;font-weight:500">${s.losses}L</span>
                        <span class="c-muted" style="font-size:14px">${s.total} total</span>
                    </div>
                    <div class="progress-bar" style="margin-bottom:4px">
                        <div class="progress-fill progress-green" style="width:${s.total > 0 ? s.passed / s.total * 100 : 0}%"></div>
                    </div>
                    <div style="font-size:11px;color:var(--text-tertiary)">${s.passed} / ${s.total} passed filter</div>
                </div>
            </div>
            <div class="strategy-card-stats">
                <div>
                    <div class="strategy-card-stat-label">Avg Confidence</div>
                    <div class="strategy-card-stat-value">${s.avg_confidence}%</div>
                </div>
                <div>
                    <div class="strategy-card-stat-label">Avg R:R</div>
                    <div class="strategy-card-stat-value">${s.avg_rr}</div>
                </div>
                <div>
                    <div class="strategy-card-stat-label">Settled</div>
                    <div class="strategy-card-stat-value">${s.settled}</div>
                </div>
                <div>
                    <div class="strategy-card-stat-label">Passed</div>
                    <div class="strategy-card-stat-value">${s.passed}</div>
                </div>
            </div>
        `;
        cardsContainer.appendChild(card);

        // Mini donut for win rate
        const donutCanvas = document.getElementById(`donut_${s.strategy}`);
        if (donutCanvas && s.settled > 0) {
            new Chart(donutCanvas.getContext('2d'), {
                type: 'doughnut',
                data: {
                    datasets: [{
                        data: [s.wins, s.losses],
                        backgroundColor: ['rgba(48,209,88,0.7)', 'rgba(255,69,58,0.4)'],
                        borderWidth: 0,
                    }]
                },
                options: {
                    responsive: false,
                    cutout: '72%',
                    plugins: { legend: { display: false }, tooltip: { enabled: false } },
                    animation: { animateRotate: true, duration: 800 },
                },
            });
        }
    });

    // P&L Distribution scatter
    const allPnl = data.flatMap(s =>
        (s.pnl_values || []).map(v => ({ strategy: s.strategy, pnl: v }))
    );
    if (allPnl.length > 0) {
        const strategyColors = {
            mean_reversion: ChartDefaults.colors.accent,
            breakout: ChartDefaults.colors.green,
            momentum: ChartDefaults.colors.orange,
            earnings_play: ChartDefaults.colors.purple,
        };
        const datasets = data.map(s => ({
            label: s.strategy.replace('_', ' '),
            data: (s.pnl_values || []).map((v, i) => ({ x: i + 1, y: v })),
            backgroundColor: (strategyColors[s.strategy] || ChartDefaults.colors.cyan) + '99',
            pointRadius: 6,
            pointHoverRadius: 8,
        }));

        const distCtx = document.getElementById('pnlDistChart').getContext('2d');
        new Chart(distCtx, {
            type: 'scatter',
            data: { datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: { color: 'rgba(255,255,255,0.5)', font: { size: 11 }, boxWidth: 8, padding: 16 },
                    },
                    tooltip: {
                        ...ChartDefaults.tooltipStyle,
                        callbacks: { label: ctx => `${ctx.dataset.label}: ${formatMoney(ctx.raw.y, true)}` },
                    },
                },
                scales: {
                    x: {
                        title: { display: true, text: 'Trade #', color: 'rgba(255,255,255,0.3)', font: { size: 11 } },
                        ticks: { color: ChartDefaults.colors.tickColor, font: { size: 11 } },
                        grid: { display: false },
                        border: { display: false },
                    },
                    y: {
                        title: { display: true, text: 'P&L', color: 'rgba(255,255,255,0.3)', font: { size: 11 } },
                        ticks: { color: ChartDefaults.colors.tickColor, font: { size: 11 }, callback: v => formatMoney(v) },
                        grid: { color: ChartDefaults.colors.gridLine },
                        border: { display: false },
                    },
                },
            },
        });
    }

    return () => {
        if (barChart) barChart.destroy();
    };
}
