/**
 * Phantom — Chart.js helpers
 */

const ChartDefaults = {
    colors: {
        green: '#30d158',
        red: '#ff453a',
        accent: '#0a84ff',
        orange: '#ff9f0a',
        purple: '#bf5af2',
        cyan: '#64d2ff',
        gridLine: 'rgba(255,255,255,0.03)',
        tickColor: 'rgba(255,255,255,0.2)',
    },

    tooltipStyle: {
        backgroundColor: 'rgba(20,20,20,0.95)',
        titleColor: 'rgba(255,255,255,0.5)',
        bodyColor: '#f5f5f7',
        bodyFont: { weight: '600', size: 14 },
        borderColor: 'rgba(255,255,255,0.1)',
        borderWidth: 1,
        padding: 12,
        cornerRadius: 10,
        displayColors: false,
    },
};

function createEquityChart(ctx, labels, values, height = 280) {
    const isUp = values.length > 1 && values[values.length - 1] >= values[0];
    const color = isUp ? ChartDefaults.colors.green : ChartDefaults.colors.red;

    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, isUp ? 'rgba(48,209,88,0.15)' : 'rgba(255,69,58,0.15)');
    gradient.addColorStop(1, isUp ? 'rgba(48,209,88,0)' : 'rgba(255,69,58,0)');

    return new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    data: values,
                    borderColor: color,
                    backgroundColor: gradient,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHitRadius: 20,
                    borderWidth: 2,
                },
                {
                    data: Array(labels.length).fill(100000),
                    borderColor: 'rgba(255,255,255,0.08)',
                    borderDash: [4, 4],
                    borderWidth: 1,
                    pointRadius: 0,
                    fill: false,
                },
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            plugins: {
                legend: { display: false },
                tooltip: {
                    ...ChartDefaults.tooltipStyle,
                    callbacks: { label: ctx => ctx.datasetIndex === 0 ? formatMoney(ctx.raw) : null },
                    filter: item => item.datasetIndex === 0,
                },
            },
            scales: {
                x: {
                    ticks: { color: ChartDefaults.colors.tickColor, maxTicksLimit: 8, font: { size: 11 } },
                    grid: { display: false },
                    border: { display: false },
                },
                y: {
                    position: 'right',
                    ticks: {
                        color: ChartDefaults.colors.tickColor,
                        font: { size: 11 },
                        callback: v => formatMoney(v),
                        maxTicksLimit: 5,
                    },
                    grid: { color: ChartDefaults.colors.gridLine },
                    border: { display: false },
                },
            },
        },
    });
}

function createBarChart(ctx, labels, values, colors) {
    return new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                data: values,
                backgroundColor: colors || values.map(v => v >= 0 ? 'rgba(48,209,88,0.6)' : 'rgba(255,69,58,0.6)'),
                borderRadius: 4,
                borderSkipped: false,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: {
                legend: { display: false },
                tooltip: {
                    ...ChartDefaults.tooltipStyle,
                    callbacks: { label: ctx => formatMoney(ctx.raw, true) },
                },
            },
            scales: {
                x: {
                    ticks: { color: ChartDefaults.colors.tickColor, font: { size: 11 }, callback: v => formatMoney(v) },
                    grid: { color: ChartDefaults.colors.gridLine },
                    border: { display: false },
                },
                y: {
                    ticks: { color: '#f5f5f7', font: { size: 13, weight: '500' } },
                    grid: { display: false },
                    border: { display: false },
                },
            },
        },
    });
}

function createDoughnutChart(ctx, labels, values, colors) {
    return new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{
                data: values,
                backgroundColor: colors || [
                    ChartDefaults.colors.accent,
                    ChartDefaults.colors.green,
                    ChartDefaults.colors.orange,
                    ChartDefaults.colors.purple,
                    ChartDefaults.colors.cyan,
                ],
                borderWidth: 0,
                spacing: 2,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '70%',
            plugins: {
                legend: { display: false },
                tooltip: {
                    ...ChartDefaults.tooltipStyle,
                    callbacks: { label: ctx => `${ctx.label}: ${formatMoney(ctx.raw)}` },
                },
            },
        },
    });
}

function createDrawdownChart(ctx, labels, values) {
    const gradient = ctx.createLinearGradient(0, 0, 0, 200);
    gradient.addColorStop(0, 'rgba(255,69,58,0.2)');
    gradient.addColorStop(1, 'rgba(255,69,58,0)');

    return new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                data: values,
                borderColor: ChartDefaults.colors.red,
                backgroundColor: gradient,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
                pointHitRadius: 20,
                borderWidth: 2,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            plugins: {
                legend: { display: false },
                tooltip: {
                    ...ChartDefaults.tooltipStyle,
                    callbacks: { label: ctx => '-' + ctx.raw.toFixed(2) + '%' },
                },
            },
            scales: {
                x: {
                    ticks: { color: ChartDefaults.colors.tickColor, maxTicksLimit: 8, font: { size: 11 } },
                    grid: { display: false },
                    border: { display: false },
                },
                y: {
                    reverse: true,
                    ticks: {
                        color: ChartDefaults.colors.tickColor,
                        font: { size: 11 },
                        callback: v => '-' + v.toFixed(1) + '%',
                    },
                    grid: { color: ChartDefaults.colors.gridLine },
                    border: { display: false },
                },
            },
        },
    });
}

function createSparkline(container, values) {
    const canvas = document.createElement('canvas');
    canvas.width = 80;
    canvas.height = 24;
    container.appendChild(canvas);

    const isUp = values.length > 1 && values[values.length - 1] >= 0;
    const color = isUp ? ChartDefaults.colors.green : ChartDefaults.colors.red;

    new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
            labels: values.map((_, i) => i),
            datasets: [{
                data: values,
                borderColor: color,
                borderWidth: 1.5,
                pointRadius: 0,
                tension: 0.4,
                fill: false,
            }],
        },
        options: {
            responsive: false,
            animation: false,
            plugins: { legend: { display: false }, tooltip: { enabled: false } },
            scales: {
                x: { display: false },
                y: { display: false },
            },
        },
    });
}
