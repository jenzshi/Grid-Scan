/* Events view — event log and drill-down */

async function renderEventsView(container) {
    const guard = guardedFetch('events');

    /* Show cached data instantly */
    if (state.eventsData && state.eventsData.events && state.eventsData.events.length > 0) {
        container.innerHTML = buildEventsHTML(state.eventsData);
        return;
    }

    container.innerHTML = '<div class="loading">Loading event log...</div>';

    const data = await fetchJSON('/events');
    if (guard.isStale()) return;

    if (!data || !data.events || data.events.length === 0) {
        container.innerHTML = buildEmptyEventsHTML();
        return;
    }

    state.eventsData = data;
    container.innerHTML = buildEventsHTML(data);
}

function buildEmptyEventsHTML() {
    return `
        <h2 class="view-title">Stress Events</h2>
        <p class="view-subtitle">Automatic post-mortem log of every flagged event</p>
        <div class="empty-state">
            <div class="empty-state-title">No stress events recorded yet</div>
            <div class="empty-state-detail">
                Events are automatically logged when the grid stress score exceeds thresholds or
                forecast error grows dangerously fast. The system is actively monitoring ERCOT —
                events will appear here as they are detected.
            </div>
            <div class="empty-state-what" style="margin-top: 1.5rem">
                <div class="section-heading" style="margin-top:0">What triggers an event?</div>
                <table class="readings-table" style="max-width:36rem">
                    <tr><td class="readings-label">Forecast error exceeds</td><td class="readings-value">5% of demand</td></tr>
                    <tr><td class="readings-label">Error growth rate exceeds</td><td class="readings-value">1,000 MW/hour</td></tr>
                    <tr><td class="readings-label">PRC drops below</td><td class="readings-value">5,500 MW</td></tr>
                    <tr><td class="readings-label">Reserve margin below</td><td class="readings-value">10%</td></tr>
                </table>
            </div>
            <div class="empty-state-what" style="margin-top: 1.5rem">
                <div class="section-heading" style="margin-top:0">What gets logged?</div>
                <div class="empty-state-detail">
                    Each event captures: cause classification (demand vs supply side), peak error magnitude,
                    deterioration rate, ERCOT response lag, fingerprint match against 11 historical stress
                    signatures, and a plain-language AI summary. Events are stored permanently in the database
                    as automatic institutional memory.
                </div>
            </div>
        </div>
    `;
}

function buildEventsHTML(data) {
    let html = '';

    const activeCount = data.events.filter(e => !e.resolved_at).length;
    const resolvedCount = data.events.length - activeCount;

    html += `<h2 class="view-title">Stress Events</h2>`;
    html += `<p class="view-subtitle">${data.events.length} events recorded — ${activeCount} active, ${resolvedCount} resolved</p>`;

    /* Column headers */
    html += `
        <div class="event-list-header">
            <span>Date</span>
            <span>Duration</span>
            <span>Cause</span>
            <span>Peak Error</span>
            <span>Fingerprint Match</span>
            <span>Lag</span>
            <span></span>
        </div>
    `;

    html += `<ul class="event-list">`;
    for (const event of data.events) {
        const date = event.detected_at ? new Date(event.detected_at).toLocaleString() : '—';
        const duration = formatDuration(event.detected_at, event.resolved_at);
        const causeClass = `cause-${event.cause || 'mixed'}`;
        const causeLabel = formatCause(event.cause);
        const adequacyClass = event.response_adequate ? 'ok' : 'fail';
        const adequacySymbol = event.response_adequate == null ? '—' : (event.response_adequate ? '✓' : '✗');
        const activeClass = event.resolved_at ? '' : 'event-active';

        html += `
            <li class="event-row ${activeClass}" onclick="toggleEventDetail('${event.id}', this)">
                <span class="event-date">${date}</span>
                <span>${duration}</span>
                <span><span class="cause-badge ${causeClass}">${causeLabel}</span></span>
                <span class="event-error-mw">${Math.round(event.peak_error_mw || 0).toLocaleString()} MW</span>
                <span class="event-fingerprint">${event.fingerprint_match || '—'}</span>
                <span class="event-lag">${event.response_lag_minutes != null ? event.response_lag_minutes + 'm' : '—'}</span>
                <span class="event-adequacy ${adequacyClass}">${adequacySymbol}</span>
            </li>
            <li class="event-detail" id="detail-${event.id}" style="display:none">
                ${renderEventDetail(event)}
            </li>
        `;
    }
    html += `</ul>`;

    return html;
}

function toggleEventDetail(eventId, rowEl) {
    const el = document.getElementById(`detail-${eventId}`);
    if (!el) return;
    const showing = el.style.display !== 'none';
    el.style.display = showing ? 'none' : 'block';
    if (rowEl) rowEl.classList.toggle('is-open', !showing);
}

function renderEventDetail(event) {
    let html = '';

    /* Peak metrics strip */
    html += `<div class="metric-strip">`;
    html += metricItem('Peak Error', `${Math.round(event.peak_error_mw || 0).toLocaleString()} MW`);
    html += metricItem('Error %', `${((event.peak_error_pct || 0) * 100).toFixed(1)}%`);
    html += metricItem('Growth Rate', `${Math.round(event.error_growth_rate_mw_per_hour || 0).toLocaleString()} MW/h`);
    html += metricItem('Response Lag', event.response_lag_minutes != null ? `${event.response_lag_minutes} min` : '—');
    html += metricItem('Cause', formatCause(event.cause));
    html += metricItem('Adequate', event.response_adequate == null ? '—' : (event.response_adequate ? 'Yes' : 'No'));
    html += `</div>`;

    /* Claude summary */
    if (event.plain_summary) {
        html += `<p class="event-summary-text">${event.plain_summary}</p>`;
    }

    /* Response timeline */
    if (event.detected_at) {
        html += '<div class="event-timeline">';
        html += `<div class="event-timeline-item"><span class="event-timeline-label">Detected</span><span class="event-timeline-value">${new Date(event.detected_at).toLocaleString()}</span></div>`;
        if (event.response_lag_minutes != null) {
            html += `<div class="event-timeline-item"><span class="event-timeline-label">First Response</span><span class="event-timeline-value">${event.response_lag_minutes} minutes after onset</span></div>`;
        }
        if (event.resolved_at) {
            html += `<div class="event-timeline-item"><span class="event-timeline-label">Resolved</span><span class="event-timeline-value">${new Date(event.resolved_at).toLocaleString()}</span></div>`;
        } else {
            html += `<div class="event-timeline-item"><span class="event-timeline-label">Status</span><span class="event-timeline-value" style="color:var(--red);font-weight:700">ACTIVE</span></div>`;
        }
        html += '</div>';
    }

    /* Fingerprint match */
    if (event.fingerprint_match) {
        html += `<p class="event-fingerprint-line">Pattern match: <strong>${event.fingerprint_match}</strong> — similarity: ${((event.fingerprint_similarity || 0) * 100).toFixed(0)}%</p>`;
    }

    /* Survival context */
    html += buildSurvivalContextLine(event);

    return html;
}

function formatDuration(start, end) {
    if (!start) return '—';
    if (!end) return 'ongoing';
    const ms = new Date(end) - new Date(start);
    const minutes = Math.round(ms / 60000);
    if (minutes < 60) return `${minutes}m`;
    return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

function formatCause(cause) {
    if (!cause) return '—';
    return cause.replace('_', ' ');
}

function metricItem(label, value) {
    return `<div class="metric-item"><div class="metric-value">${value}</div><div class="metric-label">${label}</div></div>`;
}

function buildSurvivalContextLine(event) {
    const cause = event.cause || '';
    const match = event.fingerprint_match || '';
    let context = '';

    if (cause === 'supply_side') {
        context = 'Supply-side events have historically been more likely to cascade into catastrophic failure than demand-side events.';
    } else if (cause === 'demand_side') {
        context = 'Demand-side events are more common but historically less likely to become catastrophic — ERCOT can deploy demand response measures.';
    }

    if (match.includes('Uri')) {
        context = 'Conditions resembling Uri onset have historically resulted in catastrophic outcomes. Uri caused 20,000 MW of load shed affecting 4.5 million customers.';
    } else if (match.includes('Elliott')) {
        context = 'Elliott-like conditions (large forecast error, intact supply) have historically resolved safely when PRC remains above critical thresholds.';
    } else if (match.includes('Deferred Maintenance')) {
        context = 'Deferred maintenance cascades — where delayed service causes rapid simultaneous trips — are a recurring structural vulnerability.';
    } else if (match.includes('Spring')) {
        context = 'Spring maintenance season stress is a recurring vulnerability: high planned outages overlapping with unexpected demand.';
    } else if (match.includes('Summer Evening') || match.includes('August')) {
        context = 'Evening solar ramp-down stress is the defining summer pattern — demand holds while solar output drops rapidly between 19:00-21:00 CT.';
    }

    if (!context) return '';

    return `
        <div class="event-survival-context">
            ${context}
            <a href="#history" onclick="window.location.hash='history'">View full historical analysis \u2192</a>
        </div>
    `;
}
