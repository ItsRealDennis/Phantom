/**
 * Phantom — Trade Journal Page
 */

async function renderTrades(container) {
    let currentOffset = 0;
    let currentLimit = 25;
    let currentSort = 'created_at';
    let currentSortDir = 'desc';
    let filters = { strategy: '', status: '', direction: '', ticker: '' };

    container.innerHTML = `
        <div class="section">
            <div class="section-header">
                <span class="section-title">Trade Journal</span>
                <span class="section-title c-muted" id="tradeCount"></span>
            </div>
            <div class="card">
                <div class="filter-bar">
                    <input class="filter-input" type="text" id="filterTicker" placeholder="Search ticker...">
                    <select class="filter-select" id="filterStrategy">
                        <option value="">All Strategies</option>
                        <option value="mean_reversion">Mean Reversion</option>
                        <option value="breakout">Breakout</option>
                        <option value="momentum">Momentum</option>
                    </select>
                    <select class="filter-select" id="filterStatus">
                        <option value="">All Status</option>
                        <option value="open">Open</option>
                        <option value="won">Won</option>
                        <option value="lost">Lost</option>
                        <option value="stopped">Stopped</option>
                        <option value="filtered">Filtered</option>
                        <option value="expired">Expired</option>
                        <option value="settled">Settled (W/L/S)</option>
                    </select>
                    <select class="filter-select" id="filterDirection">
                        <option value="">All Directions</option>
                        <option value="LONG">Long</option>
                        <option value="SHORT">Short</option>
                    </select>
                    <select class="filter-select" id="filterLimit">
                        <option value="25">25 per page</option>
                        <option value="50">50 per page</option>
                        <option value="100">100 per page</option>
                    </select>
                </div>
                <div id="tradesTableContainer"><div class="loading" style="margin:16px"></div></div>
                <div class="pagination" id="tradesPagination"></div>
            </div>
        </div>
    `;

    async function loadTrades() {
        const params = {
            offset: currentOffset,
            limit: currentLimit,
            sort_by: currentSort,
            sort_dir: currentSortDir,
        };
        if (filters.strategy) params.strategy = filters.strategy;
        if (filters.status) params.status = filters.status;
        if (filters.direction) params.direction = filters.direction;
        if (filters.ticker) params.ticker = filters.ticker;

        const data = await API.signalsPaginated(params);
        if (!data) return;

        const tableContainer = document.getElementById('tradesTableContainer');
        document.getElementById('tradeCount').textContent = data.total_count + ' signals';

        if (data.signals.length === 0) {
            tableContainer.innerHTML = '';
            tableContainer.appendChild(buildEmptyState(
                '', 'No signals found',
                filters.ticker || filters.strategy || filters.status ? 'Try adjusting your filters' : 'Run a scan to generate signals',
                filters.ticker || filters.strategy || filters.status
                    ? el('button', { className: 'btn btn-sm', textContent: 'Clear Filters', onClick: () => { clearFilters(); loadTrades(); } })
                    : null
            ));
            document.getElementById('tradesPagination').innerHTML = '';
            return;
        }

        const headers = [
            { label: 'Date', key: 'created_at' },
            { label: 'Ticker', key: 'ticker' },
            { label: 'Strategy', key: 'strategy' },
            { label: 'Dir' },
            { label: 'Conf', key: 'confidence' },
            { label: 'R:R', key: 'rr_ratio' },
            { label: 'Filter' },
            { label: 'Status', key: 'status' },
            { label: 'P&L', key: 'real_pnl' },
        ];

        const rows = data.signals.map(s => ({
            signal: s,
            cells: [
                { html: `<span class="c-muted">${formatDate(s.created_at)}</span>` },
                { html: `<span class="cell-ticker">${s.ticker}</span>` },
                { html: `<span style="text-transform:capitalize">${s.strategy.replace('_', ' ')}</span>` },
                { html: directionBadge(s.direction) },
                s.confidence + '%',
                s.rr_ratio.toFixed(2),
                { html: filterBadge(s.passed_filter) },
                { html: statusBadge(s.status) },
                { html: s.real_pnl !== null ? `<span class="${pnlClass(s.real_pnl)}">${formatMoney(s.real_pnl, true)}</span>` : '<span class="c-muted">--</span>' },
            ],
        }));

        const table = buildTable(headers, rows, {
            sortable: true,
            currentSort,
            sortDir: currentSortDir,
            onSort: (key) => {
                if (currentSort === key) {
                    currentSortDir = currentSortDir === 'desc' ? 'asc' : 'desc';
                } else {
                    currentSort = key;
                    currentSortDir = 'desc';
                }
                currentOffset = 0;
                loadTrades();
            },
        });

        tableContainer.innerHTML = '';
        tableContainer.appendChild(table);

        // Make rows clickable
        const tableRows = tableContainer.querySelectorAll('tbody tr');
        tableRows.forEach((tr, i) => {
            if (data.signals[i]) {
                tr.classList.add('clickable');
                tr.addEventListener('click', () => Router.navigate('#/trade/' + data.signals[i].id));
            }
        });

        // Pagination
        const totalPages = Math.ceil(data.total_count / currentLimit);
        const currentPage = Math.floor(currentOffset / currentLimit) + 1;
        const pagination = document.getElementById('tradesPagination');
        pagination.innerHTML = `
            <span>Page ${currentPage} of ${totalPages}</span>
            <div class="pagination-btns">
                <button class="btn btn-sm" ${currentPage <= 1 ? 'disabled' : ''} id="prevPage">Prev</button>
                <button class="btn btn-sm" ${currentPage >= totalPages ? 'disabled' : ''} id="nextPage">Next</button>
            </div>
        `;
        document.getElementById('prevPage')?.addEventListener('click', () => {
            currentOffset = Math.max(0, currentOffset - currentLimit);
            loadTrades();
        });
        document.getElementById('nextPage')?.addEventListener('click', () => {
            currentOffset += currentLimit;
            loadTrades();
        });
    }

    function clearFilters() {
        filters = { strategy: '', status: '', direction: '', ticker: '' };
        document.getElementById('filterTicker').value = '';
        document.getElementById('filterStrategy').value = '';
        document.getElementById('filterStatus').value = '';
        document.getElementById('filterDirection').value = '';
    }

    // Filter event listeners
    let debounceTimer;
    document.getElementById('filterTicker').addEventListener('input', (e) => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            filters.ticker = e.target.value;
            currentOffset = 0;
            loadTrades();
        }, 300);
    });
    document.getElementById('filterStrategy').addEventListener('change', (e) => {
        filters.strategy = e.target.value;
        currentOffset = 0;
        loadTrades();
    });
    document.getElementById('filterStatus').addEventListener('change', (e) => {
        filters.status = e.target.value;
        currentOffset = 0;
        loadTrades();
    });
    document.getElementById('filterDirection').addEventListener('change', (e) => {
        filters.direction = e.target.value;
        currentOffset = 0;
        loadTrades();
    });
    document.getElementById('filterLimit').addEventListener('change', (e) => {
        currentLimit = parseInt(e.target.value);
        currentOffset = 0;
        loadTrades();
    });

    loadTrades();
}
