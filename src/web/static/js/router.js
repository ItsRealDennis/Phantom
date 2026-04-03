/**
 * Phantom — Minimal hash router
 */
const Router = {
    routes: [],
    container: null,
    currentCleanup: null,

    init(containerId) {
        this.container = document.getElementById(containerId);
        window.addEventListener('hashchange', () => this.resolve());
        this.resolve();
    },

    on(pattern, handler) {
        this.routes.push({ pattern, handler });
        return this;
    },

    navigate(hash) {
        window.location.hash = hash;
    },

    resolve() {
        const hash = window.location.hash.slice(1) || '/';

        // Cleanup previous page
        if (this.currentCleanup) {
            this.currentCleanup();
            this.currentCleanup = null;
        }

        for (const route of this.routes) {
            const match = this._match(route.pattern, hash);
            if (match !== null) {
                this.container.innerHTML = '';
                this.container.className = 'page-enter';

                // Update nav active states
                document.querySelectorAll('.sidebar-link, .bottom-tab').forEach(el => {
                    const href = el.dataset.route || '';
                    if (href === route.pattern || (route.pattern === '/' && href === '/')) {
                        el.classList.add('active');
                    } else {
                        el.classList.remove('active');
                    }
                });

                // Update topbar title
                const titleEl = document.getElementById('pageTitle');
                if (titleEl) {
                    const titles = { '/': 'Overview', '/trades': 'Trade Journal', '/strategies': 'Strategy Lab', '/risk': 'Risk & Portfolio', '/settings': 'System' };
                    titleEl.textContent = titles[route.pattern] || 'Phantom';
                }

                const cleanup = route.handler(this.container, match);
                if (typeof cleanup === 'function') {
                    this.currentCleanup = cleanup;
                }
                return;
            }
        }

        // 404 fallback
        this.container.innerHTML = '<div class="empty"><div class="empty-icon">?</div><div class="empty-title">Page not found</div></div>';
    },

    _match(pattern, hash) {
        // Handle parameterized routes like /trade/:id
        const patternParts = pattern.split('/');
        const hashParts = hash.split('/');

        if (patternParts.length !== hashParts.length) return null;

        const params = {};
        for (let i = 0; i < patternParts.length; i++) {
            if (patternParts[i].startsWith(':')) {
                params[patternParts[i].slice(1)] = hashParts[i];
            } else if (patternParts[i] !== hashParts[i]) {
                return null;
            }
        }
        return params;
    }
};
