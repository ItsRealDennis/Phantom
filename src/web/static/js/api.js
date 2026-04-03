/**
 * Phantom — API fetch wrapper
 */
const API = {
    cache: new Map(),
    cacheTTL: 30000, // 30s

    async get(url, useCache = false) {
        if (useCache) {
            const cached = this.cache.get(url);
            if (cached && Date.now() - cached.ts < this.cacheTTL) {
                return cached.data;
            }
        }
        try {
            const res = await fetch(url);
            if (!res.ok) return null;
            const data = await res.json();
            if (useCache) {
                this.cache.set(url, { data, ts: Date.now() });
            }
            return data;
        } catch {
            return null;
        }
    },

    async post(url) {
        try {
            const res = await fetch(url, { method: 'POST' });
            return res.json();
        } catch {
            return null;
        }
    },

    clearCache() {
        this.cache.clear();
    },

    // Convenience methods
    overview()          { return this.get('/api/overview'); },
    strategies()        { return this.get('/api/strategies'); },
    strategiesDetailed(){ return this.get('/api/strategies/detailed'); },
    signals(limit = 20) { return this.get(`/api/signals?limit=${limit}`); },
    signalsPaginated(params) {
        const q = new URLSearchParams(params).toString();
        return this.get(`/api/signals/paginated?${q}`);
    },
    signalDetail(id)    { return this.get(`/api/signals/${id}`); },
    openTrades()        { return this.get('/api/open-trades'); },
    equityCurve()       { return this.get('/api/equity-curve'); },
    portfolio()         { return this.get('/api/portfolio'); },
    filterValidation()  { return this.get('/api/filter-validation'); },
    schedulerStatus()   { return this.get('/api/scheduler/status'); },
    riskMetrics()       { return this.get('/api/risk/metrics'); },
    dailyPnl(days = 7)  { return this.get(`/api/daily-pnl?days=${days}`); },
    alpacaStatus()      { return this.get('/api/alpaca/status'); },
    alpacaAccount()     { return this.get('/api/alpaca/account'); },
    alpacaPositions()   { return this.get('/api/alpaca/positions'); },
    triggerScan()       { return this.post('/api/scan/trigger'); },
    triggerSettle()     { return this.post('/api/settle/trigger'); },

    // Phase 2 endpoints
    circuitBreakers()       { return this.get('/api/circuit-breakers'); },
    resumeBreaker(id)       { return this.post(`/api/circuit-breakers/${id}/resume`); },
    portfolioRiskDetail()   { return this.get('/api/risk/portfolio-detail'); },
    strategyHealth()        { return this.get('/api/strategies/health'); },
    filterValidationDetail(){ return this.get('/api/filter-validation/detailed'); },
    openTradesLive()        { return this.get('/api/open-trades/live'); },
    snapshots(days = 30)    { return this.get(`/api/snapshots?days=${days}`); },
};
