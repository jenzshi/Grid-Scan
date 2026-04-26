/* Trends view — charts, historical analysis, aggregate metrics */

async function renderTrendsView(container) {
    const guard = guardedFetch('trends');

    if (state.trendsData) {
        container.innerHTML = buildTrendsHTML(state.trendsData);
        drawTrendsCharts(state.trendsData);
        return;
    }

    container.innerHTML = '<div class="loading">Analyzing trends across 30 years of ERCOT data...</div>';

    const data = await fetchJSON('/trends');
    if (guard.isStale()) return;

    if (!data) {
        container.innerHTML = '<div class="loading">Unable to load trend data.</div>';
        return;
    }

    state.trendsData = data;
    container.innerHTML = buildTrendsHTML(data);
    drawTrendsCharts(data);
}

function buildTrendsHTML(data) {
    const hist = data.historical || {};
    let html = '';

    html += `<h2 class="view-title">Trends &amp; Historical Analysis</h2>`;
    html += `<p class="view-subtitle">${hist.total_periods || 0} peak periods analyzed across ${hist.year_range || '2003-2025'}</p>`;

    /* Key findings insight panel */
    html += buildInsightPanel(data);

    /* Outcome summary strip */
    const outcomes = hist.outcomes || {};
    const totalPeriods = hist.total_periods || 0;
    const catastrophic = outcomes.catastrophic || 0;
    const nearMiss = outcomes.near_miss || 0;
    const managed = outcomes.managed || 0;
    const normal = outcomes.normal || 0;

    html += `
        <div class="trends-summary-strip">
            <div class="trends-summary-item">
                <div class="trends-summary-value">${totalPeriods}</div>
                <div class="trends-summary-label">Total Periods</div>
            </div>
            <div class="trends-summary-item">
                <div class="trends-summary-value" style="color:var(--red)">${catastrophic}</div>
                <div class="trends-summary-label">Catastrophic</div>
            </div>
            <div class="trends-summary-item">
                <div class="trends-summary-value" style="color:var(--amber)">${nearMiss}</div>
                <div class="trends-summary-label">Near Miss</div>
            </div>
            <div class="trends-summary-item">
                <div class="trends-summary-value" style="color:var(--green)">${managed}</div>
                <div class="trends-summary-label">Managed</div>
            </div>
            <div class="trends-summary-item">
                <div class="trends-summary-value">${normal}</div>
                <div class="trends-summary-label">Normal</div>
            </div>
        </div>
    `;

    /* Peak forecast error by year — the money chart */
    if (hist.error_by_year && Object.keys(hist.error_by_year).length > 0) {
        html += `
            <div class="chart-section">
                <div class="chart-headline">Peak Forecast Error by Year</div>
                <div class="chart-note">Maximum forecast error % during each peak period. Higher = more dangerous. The 4 catastrophic failures all exceeded 8%.</div>
                <div class="chart-canvas-wrapper chart-tall">
                    <canvas id="hist-error-chart"></canvas>
                </div>
            </div>
        `;
    }

    /* Thermal outages by year */
    if (hist.outage_by_year && Object.keys(hist.outage_by_year).length > 0) {
        html += `
            <div class="chart-section">
                <div class="chart-headline">Peak Thermal Outages by Year</div>
                <div class="chart-note">Maximum MW of thermal generation offline during each peak period. Uri (2021) saw 28,000 MW — the worst in ERCOT history.</div>
                <div class="chart-canvas-wrapper chart-tall">
                    <canvas id="hist-outage-chart"></canvas>
                </div>
            </div>
        `;
    }

    /* Supply vs demand risk analysis */
    const supply = hist.supply_side || {};
    const demand = hist.demand_side || {};
    if (supply.total > 0 || demand.total > 0) {
        const supplyFailRate = supply.total > 0 ? Math.round(supply.failures / supply.total * 100) : 0;
        const demandFailRate = demand.total > 0 ? Math.round(demand.failures / demand.total * 100) : 0;

        html += `
            <div class="insight-section">
                <div class="section-heading">Supply-Side vs Demand-Side Risk</div>
                <div class="insight-grid">
                    <div class="insight-card-supply">
                        <div class="insight-card-title">Supply-Side Events</div>
                        <div class="insight-card-stat">${supply.total} periods</div>
                        <div class="insight-card-fail">${supply.failures} failures (${supplyFailRate}% failure rate)</div>
                        <div class="insight-card-detail">Generator trips, fuel shortages, equipment failures. When supply fails, it cascades — multiple units go down simultaneously.</div>
                    </div>
                    <div class="insight-card-demand">
                        <div class="insight-card-title">Demand-Side Events</div>
                        <div class="insight-card-stat">${demand.total} periods</div>
                        <div class="insight-card-fail">${demand.failures} failures (${demandFailRate}% failure rate)</div>
                        <div class="insight-card-detail">Temperature surprises driving load above forecast. More common but less likely to become catastrophic — ERCOT can deploy demand response.</div>
                    </div>
                </div>
            </div>
        `;
    }

    /* Season risk */
    const seasonRisk = hist.season_risk || {};
    if (Object.keys(seasonRisk).length > 0) {
        html += `
            <div class="insight-section">
                <div class="section-heading">Risk by Season</div>
                <div class="insight-grid">
        `;
        const seasonOrder = ['winter', 'summer', 'spring'];
        for (const season of seasonOrder) {
            const s = seasonRisk[season];
            if (!s) continue;
            const failRate = s.total > 0 ? Math.round(s.failures / s.total * 100) : 0;
            const riskColor = failRate > 15 ? 'var(--red)' : failRate > 5 ? 'var(--amber)' : 'var(--green)';
            html += `
                <div class="insight-card-season">
                    <div class="insight-card-title">${capitalize(season)}</div>
                    <div class="insight-card-stat">${s.total} periods</div>
                    <div class="insight-card-fail" style="color:${riskColor}">${s.failures} failures (${failRate}%)</div>
                </div>
            `;
        }
        html += `</div></div>`;
    }

    /* Notable events timeline — use enriched fingerprint narratives if available */
    const fpNarratives = data.fingerprint_narratives || [];
    const timelineEvents = fpNarratives.length > 0 ? fpNarratives : (hist.notable_events || []);
    if (timelineEvents.length > 0) {
        html += `<div class="section-heading">Critical Events Timeline</div>`;
        html += `<div class="timeline">`;
        for (const event of timelineEvents) {
            const outcomeClass = `outcome-${event.outcome}`;
            const errorPct = event.peak_error_pct ? (event.peak_error_pct * 100).toFixed(1) + '%' : '';
            const outage = event.max_thermal_outage_mw ? Math.round(event.max_thermal_outage_mw).toLocaleString() + ' MW outage' : '';
            const detail = [errorPct ? `${errorPct} error` : '', outage].filter(Boolean).join(' · ');
            const displayNotes = event.fingerprint_notes || event.notes || '';

            let impactLine = '';
            if (event.load_shed_mw) {
                impactLine += `Load shed: ${Math.round(event.load_shed_mw).toLocaleString()} MW`;
            }
            if (event.customers_affected) {
                impactLine += impactLine ? ' · ' : '';
                impactLine += `${Math.round(event.customers_affected).toLocaleString()} customers affected`;
            }
            if (event.eea_level_reached != null && event.eea_level_reached > 0) {
                impactLine += impactLine ? ' · ' : '';
                impactLine += `EEA Level ${event.eea_level_reached}`;
            }

            html += `
                <div class="timeline-item">
                    <div class="timeline-year">${event.year}</div>
                    <div class="timeline-content">
                        <span class="outcome-badge ${outcomeClass}">${formatOutcome(event.outcome)}</span>
                        <span class="timeline-season">${capitalize(event.season || '')}</span>
                        ${detail ? `<span class="timeline-detail">${detail}</span>` : ''}
                        ${event.fingerprint_label ? `<div style="font-size:0.8125rem;font-weight:600;color:var(--ink);margin-top:0.25rem">${event.fingerprint_label}</div>` : ''}
                        <div class="timeline-notes">${displayNotes}</div>
                        ${impactLine ? `<div class="timeline-detail" style="margin-top:0.375rem;font-weight:600;color:var(--ink-2)">${impactLine}</div>` : ''}
                    </div>
                </div>
            `;
        }
        html += `</div>`;
    }

    return html;
}

function drawTrendsCharts(data) {
    const hist = data.historical || {};

    if (hist.error_by_year && Object.keys(hist.error_by_year).length > 1) {
        drawBarChart('hist-error-chart', hist.error_by_year);
    }
    if (hist.outage_by_year && Object.keys(hist.outage_by_year).length > 1) {
        drawBarChart('hist-outage-chart', hist.outage_by_year);
    }
}

function formatOutcome(outcome) {
    if (!outcome) return '—';
    return outcome.replace('_', ' ');
}

function buildInsightPanel(data) {
    const statements = data.insight_statements;
    if (!statements || statements.length === 0) return '';

    let html = '<div class="insight-panel">';
    html += '<div class="insight-panel-title">Key Findings from 30 Years of ERCOT Data</div>';

    for (const statement of statements) {
        html += `<div class="insight-statement">${statement}</div>`;
    }

    html += '</div>';
    return html;
}
