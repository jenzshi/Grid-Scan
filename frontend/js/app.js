/* Router, state, polling loop, view dispatch */

const API_BASE = '/api/ercot';

const state = {
    currentView: 'live',
    liveData: null,
    eventsData: null,
    trendsData: null,
    historyData: null,
    pollTimer: null,
    pollInterval: 15000,
    renderGeneration: 0,
};

function getViewFromHash() {
    const hash = window.location.hash.replace('#', '');
    const valid = ['live', 'history', 'trends', 'events'];
    return valid.includes(hash) ? hash : 'live';
}

function setActiveTab(view) {
    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.view === view);
    });
}

function renderView(view) {
    const app = document.getElementById('app');
    state.currentView = view;
    state.renderGeneration++;
    setActiveTab(view);

    switch (view) {
        case 'live':
            renderLiveView(app);
            break;
        case 'history':
            renderHistoryView(app);
            break;
        case 'trends':
            renderTrendsView(app);
            break;
        case 'events':
            renderEventsView(app);
            break;
    }
}

async function fetchJSON(path) {
    try {
        const response = await fetch(`${API_BASE}${path}`);
        if (!response.ok) return null;
        return await response.json();
    } catch {
        return null;
    }
}

function guardedFetch(view) {
    const gen = state.renderGeneration;
    return {
        gen,
        isStale: () => state.renderGeneration !== gen || state.currentView !== view,
    };
}

function startPolling() {
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollTimer = setInterval(() => {
        if (state.currentView === 'live') {
            refreshLiveData();
        }
    }, state.pollInterval);
}

function capitalize(str) {
    if (!str) return '';
    return str.charAt(0).toUpperCase() + str.slice(1);
}

/* Initialize */
document.addEventListener('DOMContentLoaded', () => {
    const view = getViewFromHash();
    renderView(view);
    startPolling();
});

window.addEventListener('hashchange', () => {
    renderView(getViewFromHash());
});
