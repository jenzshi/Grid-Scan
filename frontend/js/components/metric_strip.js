/* Horizontal metrics row — 6 metrics, whitespace-separated, color-coded */

function renderMetricStrip(data) {
    const metrics = [
        {
            label: 'Forecast Error',
            value: formatMW(data.error_mw),
            sub: formatPct(data.error_pct),
            color: getErrorColor(data.error_pct),
        },
        {
            label: 'Error Growth Rate',
            value: `${Math.round(data.growth_rate_mw_per_hour || 0)} MW/h`,
            sub: getDirectionIndicator(data.growth_rate_mw_per_hour),
            badgeClass: getDirectionBadgeClass(data.growth_rate_mw_per_hour),
            color: getGrowthColor(data.growth_rate_mw_per_hour),
        },
        {
            label: 'Reserve Margin',
            value: formatPct(data.reserve_margin_pct),
            sub: '',
            color: getReserveColor(data.reserve_margin_pct),
        },
        {
            label: 'PRC',
            value: formatMW(data.prc_mw),
            sub: data.prc_status || '',
            badgeClass: `badge-${data.prc_status || 'normal'}`,
            color: getPRCColor(data.prc_status),
        },
        {
            label: 'Thermal Outages',
            value: formatMW(data.thermal_outage_mw),
            sub: '',
            color: 'var(--ink)',
        },
        {
            label: 'Reserve Price Adder',
            value: `$${(data.reserve_price_adder || 0).toFixed(2)}/MW`,
            sub: '',
            color: 'var(--ink)',
        },
    ];

    let html = '<div class="metric-strip">';
    for (const m of metrics) {
        const badgeClass = m.badgeClass || '';
        html += `
            <div class="metric-item">
                <div class="metric-value" style="color: ${m.color}">${m.value}</div>
                <div class="metric-label">${m.label}</div>
                ${m.sub ? `<div class="metric-badge ${badgeClass}">${m.sub}</div>` : ''}
            </div>
        `;
    }
    html += '</div>';
    return html;
}

function formatMW(mw) {
    if (mw == null) return '—';
    return `${Math.round(mw).toLocaleString()} MW`;
}

function formatPct(pct) {
    if (pct == null) return '—';
    return `${(pct * 100).toFixed(1)}%`;
}

function getDirectionIndicator(rate) {
    if (!rate || rate === 0) return '—';
    return rate > 0 ? 'Rising' : 'Falling';
}

function getDirectionBadgeClass(rate) {
    if (!rate || rate === 0) return '';
    return rate > 0 ? 'badge-rising' : 'badge-falling';
}

function getErrorColor(pct) {
    if (!pct) return 'var(--green)';
    const abs = Math.abs(pct);
    if (abs >= 0.10) return 'var(--red)';
    if (abs >= 0.05) return 'var(--amber)';
    return 'var(--green)';
}

function getGrowthColor(rate) {
    if (!rate) return 'var(--green)';
    if (Math.abs(rate) >= 1000) return 'var(--red)';
    if (Math.abs(rate) >= 500) return 'var(--amber)';
    return 'var(--green)';
}

function getReserveColor(pct) {
    if (!pct) return 'var(--ink-3)';
    if (pct < 0.10) return 'var(--red)';
    if (pct < 0.15) return 'var(--amber)';
    return 'var(--green)';
}

function getPRCColor(status) {
    if (status === 'critical') return 'var(--red)';
    if (status === 'watch') return 'var(--amber)';
    return 'var(--green)';
}
