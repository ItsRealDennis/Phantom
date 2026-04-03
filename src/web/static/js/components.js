/**
 * Phantom — Reusable DOM component builders
 */

function buildTable(headers, rows, options = {}) {
    const table = document.createElement('table');

    // Thead
    const thead = document.createElement('thead');
    const tr = document.createElement('tr');
    headers.forEach((h, i) => {
        const th = document.createElement('th');
        th.textContent = h.label || h;
        if (options.sortable && h.key) {
            th.classList.add('sortable');
            th.dataset.key = h.key;
            if (options.currentSort === h.key) {
                th.classList.add(options.sortDir === 'asc' ? 'sort-asc' : 'sort-desc');
            }
            th.addEventListener('click', () => {
                if (options.onSort) options.onSort(h.key);
            });
        }
        tr.appendChild(th);
    });
    thead.appendChild(tr);
    table.appendChild(thead);

    // Tbody
    const tbody = document.createElement('tbody');
    if (rows.length === 0) {
        const emptyTr = document.createElement('tr');
        const emptyTd = document.createElement('td');
        emptyTd.colSpan = headers.length;
        emptyTd.className = 'empty';
        emptyTd.style.textAlign = 'center';
        emptyTd.textContent = options.emptyText || 'No data';
        emptyTr.appendChild(emptyTd);
        tbody.appendChild(emptyTr);
    } else {
        rows.forEach(row => {
            const rowTr = document.createElement('tr');
            if (options.onRowClick) {
                rowTr.classList.add('clickable');
                rowTr.addEventListener('click', () => options.onRowClick(row));
            }
            row.cells.forEach(cell => {
                const td = document.createElement('td');
                if (typeof cell === 'object' && cell.html) {
                    td.innerHTML = cell.html;
                    if (cell.className) td.className = cell.className;
                } else {
                    td.textContent = cell;
                }
                rowTr.appendChild(td);
            });
            tbody.appendChild(rowTr);
        });
    }
    table.appendChild(tbody);
    return table;
}

function buildEmptyState(icon, title, subtitle, actionBtn) {
    const div = el('div', { className: 'empty' },
        el('div', { className: 'empty-icon', textContent: icon }),
        el('div', { className: 'empty-title', textContent: title }),
        el('div', { className: 'c-muted', textContent: subtitle || '' }),
    );
    if (actionBtn) {
        const btnDiv = el('div', { className: 'empty-action' });
        btnDiv.appendChild(actionBtn);
        div.appendChild(btnDiv);
    }
    return div;
}

function buildPriceBar(entry, stop, target, exit) {
    const container = el('div', { className: 'price-bar-container' });

    const prices = [stop, entry, target];
    if (exit) prices.push(exit);
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const range = max - min || 1;
    const pct = v => ((v - min) / range * 100);

    // Stop zone
    const stopLeft = Math.min(pct(stop), pct(entry));
    const stopWidth = Math.abs(pct(entry) - pct(stop));
    const stopZone = el('div', { className: 'price-bar-zone price-bar-stop' });
    stopZone.style.left = stopLeft + '%';
    stopZone.style.width = stopWidth + '%';
    container.appendChild(stopZone);

    // Target zone
    const tgtLeft = Math.min(pct(entry), pct(target));
    const tgtWidth = Math.abs(pct(target) - pct(entry));
    const tgtZone = el('div', { className: 'price-bar-zone price-bar-target' });
    tgtZone.style.left = tgtLeft + '%';
    tgtZone.style.width = tgtWidth + '%';
    container.appendChild(tgtZone);

    // Entry marker
    const entryMarker = el('div', { className: 'price-bar-marker price-bar-marker-entry' });
    entryMarker.style.left = pct(entry) + '%';
    container.appendChild(entryMarker);

    // Labels
    const stopLabel = el('span', { className: 'price-bar-label c-red', textContent: '$' + stop.toFixed(2) });
    stopLabel.style.left = pct(stop) + '%';
    container.appendChild(stopLabel);

    const entryLabel = el('span', { className: 'price-bar-label c-primary', textContent: '$' + entry.toFixed(2) });
    entryLabel.style.left = pct(entry) + '%';
    entryLabel.style.bottom = '-36px';
    container.appendChild(entryLabel);

    const tgtLabel = el('span', { className: 'price-bar-label c-green', textContent: '$' + target.toFixed(2) });
    tgtLabel.style.left = pct(target) + '%';
    container.appendChild(tgtLabel);

    // Exit marker if exists
    if (exit) {
        const exitMarker = el('div', { className: 'price-bar-marker price-bar-marker-exit' });
        exitMarker.style.left = pct(exit) + '%';
        container.appendChild(exitMarker);

        const exitLabel = el('span', { className: 'price-bar-label c-orange', textContent: '$' + exit.toFixed(2) });
        exitLabel.style.left = pct(exit) + '%';
        exitLabel.style.bottom = '-36px';
        container.appendChild(exitLabel);
    }

    return container;
}

function buildTimeline(steps) {
    const container = el('div', { className: 'timeline' });
    steps.forEach((step, i) => {
        if (i > 0) {
            const line = el('div', { className: 'timeline-line' + (step.active ? ' active' : '') });
            container.appendChild(line);
        }
        const dotWrap = el('div', { style: { textAlign: 'center', flexShrink: '0' } });
        const dot = el('div', { className: 'timeline-dot' + (step.done ? ' success' : step.error ? ' error' : step.active ? ' active' : '') });
        const label = el('div', { className: 'timeline-label' });
        label.innerHTML = `<strong>${step.label}</strong><br>${step.value || ''}`;
        dotWrap.appendChild(dot);
        dotWrap.appendChild(label);
        container.appendChild(dotWrap);
    });
    return container;
}

function buildProgressBar(value, max, colorClass = 'progress-accent') {
    const pct = max > 0 ? Math.min(value / max * 100, 100) : 0;
    const bar = el('div', { className: 'progress-bar' },
        el('div', { className: 'progress-fill ' + colorClass, style: { width: pct + '%' } })
    );
    return bar;
}
