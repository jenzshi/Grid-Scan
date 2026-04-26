/* Live view — current conditions + fingerprint match */

async function renderLiveView(container) {
    const guard = guardedFetch('live');

    /* Use cached data instantly, fetch fresh in background */
    if (state.liveData) {
        container.innerHTML = buildLiveHTML(state.liveData);
        drawLiveCharts(state.liveData);
    } else {
        container.innerHTML = '<div class="loading">Connecting to ERCOT grid...</div>';
    }

    const data = await fetchJSON('/live');
    if (guard.isStale()) return;

    if (!data) {
        if (!state.liveData) {
            container.innerHTML = '<div class="loading">Unable to reach ERCOT. Retrying...</div>';
        }
        return;
    }

    state.liveData = data;
    container.innerHTML = buildLiveHTML(data);
    drawLiveCharts(data);
}

async function refreshLiveData() {
    const data = await fetchJSON('/live');
    if (state.currentView !== 'live' || !data) return;

    state.liveData = data;
    const app = document.getElementById('app');
    app.innerHTML = buildLiveHTML(data);
    drawLiveCharts(data);
}

function buildLiveHTML(data) {
    const score = data.stress_score || 0;
    const statusLabel = getStatusLabel(score);
    const statusColor = getStatusColor(score);
    const now = new Date(data.timestamp);
    const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    let html = '';

    /* Top section: score + summary side by side */
    html += `
        <div class="live-hero">
            <div class="live-hero-score">
                <div class="stress-score-number" style="color: ${statusColor}">${Math.round(score)}</div>
                <div class="stress-score-label" style="color: ${statusColor}">${statusLabel}</div>
            </div>
            <div class="live-hero-summary">
                <div class="live-hero-title">ERCOT Grid Status</div>
                <div class="live-hero-time">Last updated ${timeStr} CT</div>
                <div class="live-hero-description">${buildStatusSummary(data)}</div>
            </div>
        </div>
    `;

    /* Alert banner for fingerprint match */
    if (data.fingerprint_match && data.fingerprint_similarity >= 0.4) {
        html += renderAlertBanner(data.fingerprint_match, data.fingerprint_similarity, data.fingerprint_detail);
    }

    /* Metric strip */
    html += renderMetricStrip(data);

    /* Cause line */
    if (data.cause_description) {
        html += `<div class="cause-line">${data.cause_description}</div>`;
    }

    /* Stress score line chart — full width */
    const ts = data.score_timeseries || {};
    const tsCount = Object.keys(ts).length;
    if (tsCount > 1) {
        html += `
            <div class="chart-section" style="border-top: 2px solid var(--ink); margin-top: 1.5rem">
                <div class="chart-headline">Stress Score — Today</div>
                <div class="chart-note">${tsCount} snapshots collected · updates every poll cycle</div>
                <div class="chart-canvas-wrapper" style="height: 200px">
                    <canvas id="live-score-chart"></canvas>
                </div>
            </div>
        `;
    }

    /* Two-column: sparkline + grid snapshot */
    html += `
        <div class="live-grid">
            <div class="live-grid-chart">
                <div class="section-heading" style="margin-top: 1.5rem">Forecast Error Trend</div>
                <div class="sparkline-container">
                    <canvas id="sparkline-canvas"></canvas>
                </div>
                <div class="sparkline-legend">
                    <span class="sparkline-legend-item"><span class="sparkline-dot dot-score"></span> Stress Score</span>
                    <span class="sparkline-legend-item"><span class="sparkline-dot dot-error"></span> Forecast Error %</span>
                </div>
            </div>
            <div class="live-grid-snapshot">
                <div class="section-heading" style="margin-top: 1.5rem">Current Readings</div>
                ${buildReadingsTable(data)}
            </div>
        </div>
    `;

    /* Historical context panel */
    html += buildHistoricalContextSection(data);

    /* Bottom context bar */
    html += `
        <div class="live-context-bar">
            <div class="live-context-item">
                <span class="live-context-label">System Demand</span>
                <span class="live-context-value">${formatNum(data.actual_mw)} MW</span>
            </div>
            <div class="live-context-item">
                <span class="live-context-label">Forecasted</span>
                <span class="live-context-value">${formatNum(data.forecast_mw)} MW</span>
            </div>
            <div class="live-context-item">
                <span class="live-context-label">Temperature</span>
                <span class="live-context-value">${data.weather_temp_f || '—'}°F</span>
            </div>
            <div class="live-context-item">
                <span class="live-context-label">Season</span>
                <span class="live-context-value">${getSeason()}</span>
            </div>
            <div class="live-context-item">
                <span class="live-context-label">Data Source</span>
                <span class="live-context-value">ERCOT Real-Time</span>
            </div>
        </div>
    `;

    return html;
}

function drawLiveCharts(data) {
    if (data.recent_scores && data.recent_scores.length > 0) {
        const canvas = document.getElementById('sparkline-canvas');
        if (canvas) drawSparkline(canvas, data.recent_scores, data.recent_errors);
    }
    const ts = data.score_timeseries || {};
    if (Object.keys(ts).length > 1) {
        drawLineChart('live-score-chart', ts, 'Score');
    }
}

function buildStatusSummary(data) {
    const score = data.stress_score || 0;
    const errorMW = Math.abs(data.error_mw || 0);
    const errorPct = Math.abs(data.error_pct || 0);
    const prc = data.prc_mw || 0;
    const outages = data.thermal_outage_mw || 0;

    if (score >= 75) {
        return `Grid under critical stress. Forecast error at ${formatNum(errorMW)} MW (${(errorPct * 100).toFixed(1)}%) with ${formatNum(outages)} MW offline. Immediate attention required.`;
    }
    if (score >= 50) {
        return `Elevated grid stress detected. Error growth rate and outage levels warrant close monitoring. PRC at ${formatNum(prc)} MW.`;
    }
    if (score >= 25) {
        return `Grid operating with elevated indicators. Forecast deviation of ${(errorPct * 100).toFixed(1)}% is above normal but within manageable range.`;
    }
    return `Grid operating normally. Forecast error within tolerance at ${(errorPct * 100).toFixed(1)}%. Reserves healthy at ${formatNum(prc)} MW PRC.`;
}

function buildReadingsTable(data) {
    const rows = [
        ['Actual Demand', `${formatNum(data.actual_mw)} MW`],
        ['Forecast Demand', `${formatNum(data.forecast_mw)} MW`],
        ['Forecast Error', `${formatNum(Math.abs(data.error_mw || 0))} MW (${(Math.abs(data.error_pct || 0) * 100).toFixed(1)}%)`],
        ['Reserve Margin', `${formatNum(data.reserve_margin_mw)} MW (${((data.reserve_margin_pct || 0) * 100).toFixed(1)}%)`],
        ['PRC', `${formatNum(data.prc_mw)} MW`],
        ['Thermal Outages', `${formatNum(data.thermal_outage_mw)} MW`],
        ['Price Adder', `$${(data.reserve_price_adder || 0).toFixed(2)}/MWh`],
        ['Temperature', `${data.weather_temp_f || '—'}°F`],
    ];

    let html = '<table class="readings-table">';
    for (const [label, value] of rows) {
        html += `<tr><td class="readings-label">${label}</td><td class="readings-value">${value}</td></tr>`;
    }
    html += '</table>';
    return html;
}

function getSeason() {
    const month = new Date().getMonth();
    if (month >= 5 && month <= 8) return 'Summer';
    if (month >= 11 || month <= 1) return 'Winter';
    if (month >= 2 && month <= 4) return 'Spring';
    return 'Fall';
}

function getStatusLabel(score) {
    if (score >= 75) return 'CRITICAL';
    if (score >= 50) return 'ELEVATED';
    if (score >= 25) return 'WATCH';
    return 'NORMAL';
}

function getStatusColor(score) {
    if (score >= 75) return 'var(--red)';
    if (score >= 50) return 'var(--amber)';
    if (score >= 25) return 'var(--amber)';
    return 'var(--green)';
}

function formatNum(n) {
    if (n == null) return '—';
    return Math.round(n).toLocaleString();
}

function buildHistoricalContextSection(data) {
    const detail = data.fingerprint_detail;
    if (!detail) return '';

    const fpKey = data.fingerprint_key || '';
    const isWinterChain = ['uri_feb_2021', 'groundhog_day_2011', 'freeze_1989'].includes(fpKey);

    let html = '<div class="historical-context">';
    html += '<div class="context-match">';
    html += '<div class="context-match-title">Historical Pattern Match</div>';

    const firstSentence = detail.notes ? detail.notes.split('. ')[0] + '.' : '';
    html += `<div class="context-match-narrative">${firstSentence}</div>`;

    html += '<div class="context-match-outcome">';
    html += `<span>Outcome: <strong class="outcome-${detail.outcome}">${formatOutcomeLive(detail.outcome)}</strong></span>`;
    if (detail.load_shed_mw) {
        html += `<span>Load Shed: <strong>${formatNum(detail.load_shed_mw)} MW</strong></span>`;
    }
    if (detail.customers_affected) {
        html += `<span>Affected: <strong>${formatNum(detail.customers_affected)} customers</strong></span>`;
    }
    if (detail.eea_level_reached != null) {
        html += `<span>EEA Level: <strong>${detail.eea_level_reached}</strong></span>`;
    }
    html += '</div>';

    if (isWinterChain) {
        html += `
            <div class="pattern-thread" style="margin-top: 1rem">
                <div class="pattern-thread-title">The Winterization Thread: 1989 \u2192 2011 \u2192 2021</div>
                <div class="pattern-thread-narrative">
                    Three catastrophic failures spanning 32 years — same root cause each time:
                    unprotected generators freezing under extreme cold. Regulators issued
                    winterization recommendations after each event. Each time, those
                    recommendations were ignored. Uri was the predictable consequence.
                </div>
            </div>
        `;
    }

    html += `<a class="context-match-link" href="#history" onclick="window.location.hash='history'">View full historical analysis \u2192</a>`;
    html += '</div></div>';
    return html;
}

function formatOutcomeLive(outcome) {
    if (!outcome) return '\u2014';
    return outcome.replace('_', ' ');
}
