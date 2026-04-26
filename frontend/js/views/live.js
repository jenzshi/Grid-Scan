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

    /* ── 1. Hero: score + summary ── */
    html += `
        <div class="live-hero">
            <div class="live-hero-score">
                <div class="stress-score-number" style="color: ${statusColor}">${Math.round(score)}</div>
                <div class="stress-score-label" style="color: ${statusColor}">${statusLabel}</div>
            </div>
            <div class="live-hero-summary">
                <div class="live-hero-title">ERCOT Grid Status</div>
                <div class="live-hero-time">Last updated ${timeStr} CT · ${getSeason()} · ${data.weather_temp_f || '—'}°F</div>
                <div class="live-hero-description">${buildStatusSummary(data)}</div>
            </div>
        </div>
    `;

    /* ── 2. Alert banner (fingerprint match) ── */
    if (data.fingerprint_match && data.fingerprint_similarity >= 0.4) {
        html += renderAlertBanner(data.fingerprint_match, data.fingerprint_similarity, data.fingerprint_detail);
    }

    /* ── 3. Metric strip ── */
    html += renderMetricStrip(data);

    /* ── 4. Cause line ── */
    if (data.cause_description) {
        html += `<div class="cause-line">${data.cause_description}</div>`;
    }

    /* ── 5. Two-column: error decomposition + fuel mix ── */
    const hasDecomp = data.error_decomposition && data.error_decomposition.components && data.error_decomposition.components.length > 0;
    const hasFuel = data.fuel_mix;

    if (hasDecomp || hasFuel) {
        html += '<div class="live-dual-bars">';
        html += hasDecomp ? buildErrorDecomposition(data) : '';
        html += hasFuel ? buildFuelMixBar(data) : '';
        html += '</div>';
    }

    /* ── 6. Stress Score line chart — full width ── */
    const ts = data.score_timeseries || {};
    const tsCount = Object.keys(ts).length;
    if (tsCount > 1) {
        html += `
            <div class="chart-section" style="border-top: 2px solid var(--ink); margin-top: 1.5rem">
                <div class="live-chart-header">Stress Score Timeline</div>
                <div class="live-chart-sub">${tsCount} snapshots · updates every poll cycle</div>
                <div class="chart-canvas-wrapper" style="height: 220px">
                    <canvas id="live-score-chart"></canvas>
                </div>
            </div>
        `;
    }

    /* ── 7. Two-column: sparkline + grid detail ── */
    html += `
        <div class="live-detail-section">
            <div class="live-detail-left">
                <div class="live-chart-block">
                    <div class="live-chart-header">Forecast Error & Score Trend</div>
                    <div class="live-chart-sub">Dual-axis: stress score and forecast error over recent polls</div>
                    <div class="sparkline-container">
                        <canvas id="sparkline-canvas"></canvas>
                    </div>
                    <div class="sparkline-legend">
                        <span class="sparkline-legend-item"><span class="sparkline-legend-line" style="background: var(--ink)"></span>Stress Score (left axis)</span>
                        <span class="sparkline-legend-item"><span class="sparkline-legend-line dashed" style="background: var(--amber)"></span>Forecast Error % (right axis)</span>
                    </div>
                </div>
            </div>
            <div class="live-detail-right">
                <div class="live-chart-header">Grid Detail</div>
                ${buildReadingsTable(data)}
            </div>
        </div>
    `;

    /* ── 8. Historical context panel ── */
    html += buildHistoricalContextSection(data);

    /* ── 9. Signal harvesting (compact) ── */
    html += '<div id="signal-harvest-panel"></div>';

    return html;
}

function drawLiveCharts(data) {
    if (data.recent_scores && data.recent_scores.length > 0) {
        const canvas = document.getElementById('sparkline-canvas');
        if (canvas) drawSparkline(canvas, data.recent_scores, data.recent_errors, data.recent_timestamps);
    }
    const ts = data.score_timeseries || {};
    if (Object.keys(ts).length > 1) {
        drawLineChart('live-score-chart', ts, 'Score');
    }
    attachBarInteractivity();
    loadSignalHarvestPanel();
}

function attachBarInteractivity() {
    _attachSegmentHover('.error-decomposition', '.decomp-segment', 'data-components');
    _attachSegmentHover('.fuel-mix-section', '.fuel-mix-segment', 'data-fuels');
}

function _attachSegmentHover(containerSel, segmentSel, dataAttr) {
    const container = document.querySelector(containerSel);
    if (!container || container._hasHover) return;
    container._hasHover = true;

    let items = [];
    try { items = JSON.parse(container.getAttribute(dataAttr) || '[]'); } catch { return; }

    const segments = container.querySelectorAll(segmentSel);
    const legendItems = container.querySelectorAll('[data-idx]');

    segments.forEach((seg) => {
        const idx = parseInt(seg.dataset.idx);
        const item = items[idx];
        if (!item) return;

        seg.style.cursor = 'pointer';
        seg.style.transition = 'opacity 0.15s, transform 0.15s';

        seg.addEventListener('mouseenter', (e) => {
            /* Dim other segments */
            segments.forEach(s => { if (s !== seg) s.style.opacity = '0.4'; });
            seg.style.transform = 'scaleY(1.15)';
            /* Highlight matching legend */
            legendItems.forEach(li => {
                if (li.classList.contains('decomp-segment') || li.classList.contains('fuel-mix-segment')) return;
                li.style.opacity = li.dataset.idx === seg.dataset.idx ? '1' : '0.35';
            });
            showTooltip(e, `<strong>${item.label}</strong><br>${formatNum(item.mw)} MW · ${item.pct.toFixed(1)}%`);
        });

        seg.addEventListener('mousemove', (e) => {
            showTooltip(e, `<strong>${item.label}</strong><br>${formatNum(item.mw)} MW · ${item.pct.toFixed(1)}%`);
        });

        seg.addEventListener('mouseleave', () => {
            segments.forEach(s => { s.style.opacity = '1'; });
            seg.style.transform = '';
            legendItems.forEach(li => { li.style.opacity = '1'; });
            hideTooltip();
        });
    });
}

async function loadSignalHarvestPanel() {
    const panel = document.getElementById('signal-harvest-panel');
    if (!panel) return;

    let stats = null;
    try {
        const resp = await fetch('/api/export/stats');
        if (resp.ok) stats = await resp.json();
    } catch { /* ignore */ }
    if (!stats || !panel.isConnected) return;

    panel.innerHTML = buildSignalHarvestHTML(stats);
}

function buildSignalHarvestHTML(stats) {
    const r = stats.readiness || {};
    const level = r.level || 'insufficient';
    const milestones = r.milestones || [];
    const maxMilestone = milestones.length > 0 ? milestones[0].count : 105120;
    const fillPct = Math.min((stats.snapshot_count / maxMilestone) * 100, 100);

    let dots = '';
    for (const m of milestones) {
        const cls = m.reached ? 'reached' : '';
        dots += `<span class="milestone-label ${cls}"><span class="milestone-dot"></span>${m.label}</span>`;
    }

    return `
        <div class="signal-harvest">
            <div class="signal-harvest-row">
                <div class="signal-harvest-left">
                    <span class="signal-harvest-title">Signal Harvesting</span>
                    <span class="signal-harvest-badge ${level}">${r.description || level}</span>
                </div>
                <div class="signal-harvest-nums">
                    <span><strong>${formatNum(stats.snapshot_count)}</strong> snapshots</span>
                    <span><strong>${stats.fields_per_row || 0}</strong> features/row</span>
                    <span><strong>${stats.days_collected != null ? stats.days_collected.toFixed(1) : '0'}</strong> days</span>
                </div>
            </div>
            <div class="milestone-track"><div class="milestone-fill" style="width: ${fillPct}%"></div></div>
            <div class="milestone-labels">${dots}</div>
        </div>
    `;
}

/* ── Helpers ── */

function buildStatusSummary(data) {
    const score = data.stress_score || 0;
    const errorMW = Math.abs(data.error_mw || 0);
    const errorPct = Math.abs(data.error_pct || 0);
    const prc = data.prc_mw || 0;
    const outages = data.thermal_outage_mw || 0;

    if (score >= 75) {
        return `Grid under critical stress. Forecast error at ${formatNum(errorMW)} MW (${(errorPct * 100).toFixed(1)}%) with ${formatNum(outages)} MW offline.`;
    }
    if (score >= 50) {
        return `Elevated grid stress. Error growth rate and outage levels warrant close monitoring. PRC at ${formatNum(prc)} MW.`;
    }
    if (score >= 25) {
        return `Elevated indicators. Forecast deviation of ${(errorPct * 100).toFixed(1)}% is above normal but within manageable range.`;
    }
    return `Grid operating normally. Forecast error at ${(errorPct * 100).toFixed(1)}%. Reserves healthy at ${formatNum(prc)} MW PRC.`;
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
    if (n == null) return '\u2014';
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
                    Three catastrophic failures spanning 32 years \u2014 same root cause each time:
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

function buildReadingsTable(data) {
    const rows = [
        ['Actual Demand', `${formatNum(data.actual_mw)} MW`],
        ['Forecast Demand', `${formatNum(data.forecast_mw)} MW`],
        ['Forecast Error', `${formatNum(Math.abs(data.error_mw || 0))} MW (${(Math.abs(data.error_pct || 0) * 100).toFixed(1)}%)`],
        ['Error Growth', `${Math.round(data.growth_rate_mw_per_hour || 0)} MW/hr`],
        ['Reserve Margin', `${formatNum(data.reserve_margin_mw)} MW (${((data.reserve_margin_pct || 0) * 100).toFixed(1)}%)`],
        ['PRC', `${formatNum(data.prc_mw)} MW`],
        ['Thermal Outages', `${formatNum(data.thermal_outage_mw)} MW`],
        ['Wind', `${formatNum(data.wind_actual_mw)} / ${formatNum(data.wind_forecast_mw)} MW`],
        ['Solar', `${formatNum(data.solar_actual_mw)} / ${formatNum(data.solar_forecast_mw)} MW`],
        ['Price Adder', `$${(data.reserve_price_adder || 0).toFixed(2)}/MWh`],
        ['Temperature', `${data.weather_temp_f || '\u2014'}\u00b0F`],
    ];

    let html = '<table class="readings-table">';
    for (const [label, value] of rows) {
        html += `<tr><td class="readings-label">${label}</td><td class="readings-value">${value}</td></tr>`;
    }
    html += '</table>';
    return html;
}

function formatOutcomeLive(outcome) {
    if (!outcome) return '\u2014';
    return outcome.replace('_', ' ');
}

function buildErrorDecomposition(data) {
    const decomp = data.error_decomposition;
    if (!decomp || !decomp.components || decomp.components.length === 0) {
        return '';
    }

    let barSegments = '';
    let legendItems = '';

    for (let i = 0; i < decomp.components.length; i++) {
        const comp = decomp.components[i];
        barSegments += `<div class="decomp-segment" data-idx="${i}" style="width: ${comp.pct}%; background: ${comp.color}"></div>`;

        legendItems += `
            <div class="decomp-legend-item" data-idx="${i}">
                <span class="decomp-legend-swatch" style="background: ${comp.color}"></span>
                <span class="decomp-legend-label">${comp.label}</span>
                <span class="decomp-legend-mw">${formatNum(comp.mw)} MW</span>
                <span class="decomp-legend-pct">${comp.pct.toFixed(0)}%</span>
            </div>
        `;
    }

    return `
        <div class="error-decomposition" data-components='${JSON.stringify(decomp.components.map(c => ({ label: c.label, mw: c.mw, pct: c.pct })))}'>
            <div class="decomp-title">Why the Forecast Is Wrong</div>
            <div class="decomp-bar">${barSegments}</div>
            <div class="decomp-legend">${legendItems}</div>
        </div>
    `;
}

function buildFuelMixBar(data) {
    const mix = data.fuel_mix;
    if (!mix) return '';

    const total = (mix.gas_mw || 0) + (mix.coal_mw || 0) + (mix.nuclear_mw || 0)
        + (mix.wind_mw || 0) + (mix.solar_mw || 0) + (mix.storage_mw || 0) + (mix.other_mw || 0);

    if (total <= 0) return '';

    const fuels = [
        { key: 'gas_mw', label: 'Gas', color: '#64748b' },
        { key: 'coal_mw', label: 'Coal', color: '#44403c' },
        { key: 'nuclear_mw', label: 'Nuclear', color: '#7c3aed' },
        { key: 'wind_mw', label: 'Wind', color: '#1d4ed8' },
        { key: 'solar_mw', label: 'Solar', color: '#d97706' },
        { key: 'storage_mw', label: 'Storage', color: '#059669' },
        { key: 'other_mw', label: 'Other', color: '#94a3b8' },
    ];

    let barHTML = '';
    let legendHTML = '';
    const fuelData = [];

    for (const fuel of fuels) {
        const mw = mix[fuel.key] || 0;
        if (mw <= 0) continue;
        const pct = (mw / total) * 100;
        const idx = fuelData.length;
        fuelData.push({ label: fuel.label, mw, pct });

        barHTML += `<div class="fuel-mix-segment" data-idx="${idx}" style="width: ${pct}%; background: ${fuel.color}"></div>`;

        legendHTML += `
            <div class="fuel-mix-legend-item" data-idx="${idx}">
                <span class="fuel-mix-swatch" style="background: ${fuel.color}"></span>
                <span>${fuel.label}</span>
                <span class="fuel-mix-pct">${pct.toFixed(0)}%</span>
            </div>
        `;
    }

    return `
        <div class="fuel-mix-section" data-fuels='${JSON.stringify(fuelData)}'>
            <div class="fuel-mix-title">Where Power Comes From — ${formatNum(total)} MW</div>
            <div class="fuel-mix-bar">${barHTML}</div>
            <div class="fuel-mix-legend">${legendHTML}</div>
        </div>
    `;
}
