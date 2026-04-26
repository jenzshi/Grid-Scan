/* History view — survival analysis */

async function renderHistoryView(container) {
    const guard = guardedFetch('history');

    /* Show cached data instantly */
    if (state.historyData) {
        container.innerHTML = buildHistoryHTML(state.historyData);
        return;
    }

    container.innerHTML = `
        <div class="loading-hero">
            <div class="loading-title">Analyzing Historical ERCOT Data</div>
            <div class="loading-subtitle">Comparing current conditions against 30 years of grid events...</div>
            <div class="loading-bar"><div class="loading-bar-fill"></div></div>
        </div>
    `;

    const data = await fetchJSON('/history');
    if (guard.isStale()) return;

    if (!data) {
        container.innerHTML = '<div class="loading">Unable to load historical analysis.</div>';
        return;
    }

    state.historyData = data;
    container.innerHTML = buildHistoryHTML(data);
}

function buildHistoryHTML(data) {
    let html = '';

    html += `<h2 class="view-title">Historical Context for Current Conditions</h2>`;
    html += `<p class="view-subtitle">${data.condition_description || ''}</p>`;

    /* Narrative lead paragraph */
    html += buildHistoryNarrative(data);

    /* Survival summary — prominent callout */
    const rate = data.survival_rate || {};
    const total = rate.total || 0;
    const failCount = (rate.by_outcome?.catastrophic || 0) + (rate.by_outcome?.near_miss || 0);
    const safeCount = total - failCount;
    const safePct = total > 0 ? Math.round((safeCount / total) * 100) : 0;
    const failRate = rate.failure_rate || 0;

    html += `
        <div class="survival-callout">
            <div class="survival-callout-number" style="color: ${failRate > 0.3 ? 'var(--red)' : failRate > 0.1 ? 'var(--amber)' : 'var(--green)'}">${safePct}%</div>
            <div class="survival-callout-label">resolved safely</div>
            <div class="survival-callout-detail">${data.survival_summary || 'No similar historical periods found.'}</div>
        </div>
    `;

    /* Outcome breakdown chips */
    if (rate.by_outcome && Object.keys(rate.by_outcome).length > 0) {
        html += '<div class="outcome-chips">';
        const outcomeOrder = ['normal', 'managed', 'near_miss', 'catastrophic'];
        for (const key of outcomeOrder) {
            const count = rate.by_outcome[key] || 0;
            if (count > 0) {
                html += `<span class="outcome-chip outcome-${key}">${count} ${formatOutcome(key)}</span>`;
            }
        }
        html += '</div>';
    }

    /* Pattern threads */
    html += buildPatternThreadsSection(data);

    /* Similar periods table */
    if (data.similar_periods && data.similar_periods.length > 0) {
        html += `<h3 class="section-heading">Most Similar Historical Periods</h3>`;
        html += `<table class="periods-table"><thead><tr>
            <th>Year</th><th>Season</th><th>Peak Error</th><th>Peak Demand</th><th>Outages</th><th>Outcome</th><th>Note</th>
        </tr></thead><tbody>`;

        for (const period of data.similar_periods) {
            const outcomeClass = `outcome-${period.outcome}`;
            const peakError = period.peak_error_pct
                ? (period.peak_error_pct * 100).toFixed(1) + '%'
                : '—';
            const peakDemand = period.peak_actual_mw
                ? Math.round(period.peak_actual_mw).toLocaleString() + ' MW'
                : '—';
            const outages = period.max_thermal_outage_mw
                ? Math.round(period.max_thermal_outage_mw).toLocaleString() + ' MW'
                : '—';
            const note = period.notes || '—';
            const noteShort = note.length > 60 ? note.substring(0, 60) + '…' : note;

            html += `<tr class="period-row" onclick="togglePeriodDetail(this)">
                <td>${period.year}</td>
                <td>${capitalize(period.season || '')}</td>
                <td>${peakError}</td>
                <td>${peakDemand}</td>
                <td>${outages}</td>
                <td><span class="outcome-badge ${outcomeClass}">${formatOutcome(period.outcome)}</span></td>
                <td class="note-cell">${noteShort}</td>
            </tr>
            <tr class="period-detail-row" style="display:none">
                <td colspan="7">
                    <div class="period-detail-content">
                        ${renderPeriodDetail(period)}
                    </div>
                </td>
            </tr>`;
        }

        html += `</tbody></table>`;
    }

    /* Survival factors */
    if (data.survival_factors && data.survival_factors.length > 0) {
        html += `<h3 class="section-heading">What Separated Failures from Survivals</h3>`;
        html += `<div class="factors-intro">Key differences between periods that ended in failure versus those that resolved safely:</div>`;
        html += `<ul class="factor-list">`;
        for (const factor of data.survival_factors) {
            html += `<li>${factor.description}</li>`;
        }
        html += `</ul>`;
    }

    /* Counterfactual section */
    html += buildCounterfactualSection(data);

    return html;
}

function togglePeriodDetail(rowEl) {
    const detailRow = rowEl.nextElementSibling;
    if (!detailRow) return;
    const showing = detailRow.style.display !== 'none';
    detailRow.style.display = showing ? 'none' : 'table-row';
    rowEl.classList.toggle('is-open', !showing);
}

function renderPeriodDetail(period) {
    let html = '<div class="period-detail-grid">';

    if (period.peak_actual_mw) {
        html += `<div class="period-detail-stat"><span class="period-detail-stat-value">${Math.round(period.peak_actual_mw).toLocaleString()} MW</span><span class="period-detail-stat-label">Peak Demand</span></div>`;
    }
    if (period.max_thermal_outage_mw) {
        html += `<div class="period-detail-stat"><span class="period-detail-stat-value">${Math.round(period.max_thermal_outage_mw).toLocaleString()} MW</span><span class="period-detail-stat-label">Thermal Outages</span></div>`;
    }
    if (period.min_reserve_margin_pct != null) {
        html += `<div class="period-detail-stat"><span class="period-detail-stat-value">${(period.min_reserve_margin_pct * 100).toFixed(1)}%</span><span class="period-detail-stat-label">Min Reserve Margin</span></div>`;
    }
    if (period.peak_error_pct != null) {
        html += `<div class="period-detail-stat"><span class="period-detail-stat-value">${(period.peak_error_pct * 100).toFixed(1)}%</span><span class="period-detail-stat-label">Peak Error</span></div>`;
    }

    html += '</div>';

    if (period.notes && period.notes !== '—') {
        html += `<div class="period-detail-notes">${period.notes}</div>`;
    }

    return html || 'No additional detail available.';
}

function formatOutcome(outcome) {
    if (!outcome) return '—';
    return outcome.replace('_', ' ');
}

function buildHistoryNarrative(data) {
    const rate = data.survival_rate || {};
    const catCount = rate.by_outcome?.catastrophic || 0;
    const nearMiss = rate.by_outcome?.near_miss || 0;
    const total = rate.total || 0;

    if (total === 0) return '';

    let narrative = '<div class="history-narrative">';

    if (catCount > 0) {
        narrative += `ERCOT has experienced <strong>${catCount} catastrophic grid failure${catCount > 1 ? 's' : ''}</strong> `;
        narrative += `in ${total} similar historical periods — events where controlled rolling `;
        narrative += `blackouts were ordered and millions lost power. `;

        narrative += `The question this analysis answers: <strong>what separated the failures `;
        narrative += `from the periods that looked equally dangerous but held?</strong>`;
    } else if (nearMiss > 0) {
        narrative += `Among ${total} similar periods, <strong>${nearMiss} became near-misses</strong> — `;
        narrative += `situations where the grid came close to emergency action but held. `;
        narrative += `Understanding what prevented escalation in these cases reveals the `;
        narrative += `margin between safety and failure.`;
    } else {
        narrative += `Historical conditions similar to today have consistently resolved safely. `;
        narrative += `This analysis shows what factors maintained grid stability under `;
        narrative += `comparable stress levels.`;
    }

    narrative += '</div>';
    return narrative;
}

function buildPatternThreadsSection(data) {
    const threads = data.pattern_threads;
    if (!threads || threads.length === 0) return '';

    let html = '<h3 class="section-heading">Recurring Failure Patterns</h3>';

    for (const thread of threads) {
        const typeClass = thread.type === 'contrast' ? 'contrast'
            : thread.type === 'structural_pattern' ? 'structural' : '';

        html += `<div class="pattern-thread ${typeClass}">`;
        html += `<div class="pattern-thread-title">${thread.title}</div>`;
        html += `<div class="pattern-thread-narrative">${thread.narrative}</div>`;

        if (thread.events && thread.events.length > 0) {
            html += '<div class="pattern-thread-events">';
            for (const ev of thread.events) {
                const outcomeClass = `outcome-${ev.outcome}`;
                html += `<span class="outcome-badge ${outcomeClass}">${ev.label}</span>`;
            }
            html += '</div>';
        }

        html += '</div>';
    }

    return html;
}

function buildCounterfactualSection(data) {
    const items = data.counterfactual;
    if (!items || items.length === 0) return '';

    let html = '<h3 class="section-heading">What Would Need to Change</h3>';
    html += '<div class="counterfactual-section">';

    for (const statement of items) {
        html += `<div class="counterfactual-item">${statement}</div>`;
    }

    html += '</div>';
    return html;
}
