/* Canvas chart utilities — interactive with hover tooltips and crosshairs */

/* ============================================================
   TOOLTIP OVERLAY — shared across all charts
   ============================================================ */

function ensureTooltip() {
    let el = document.getElementById('chart-tooltip');
    if (el) return el;
    el = document.createElement('div');
    el.id = 'chart-tooltip';
    el.style.cssText = `
        position: fixed; pointer-events: none; z-index: 200;
        background: #0f172a; color: #fff; font-size: 12px;
        font-family: var(--font-num); padding: 6px 10px;
        border-radius: 3px; white-space: nowrap; display: none;
        line-height: 1.5; box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    `;
    document.body.appendChild(el);
    return el;
}

function showTooltip(e, html) {
    const tip = ensureTooltip();
    tip.innerHTML = html;
    tip.style.display = 'block';
    const rect = tip.getBoundingClientRect();
    let x = e.clientX + 12;
    let y = e.clientY - rect.height - 8;
    if (x + rect.width > window.innerWidth) x = e.clientX - rect.width - 12;
    if (y < 0) y = e.clientY + 16;
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';
}

function hideTooltip() {
    const tip = document.getElementById('chart-tooltip');
    if (tip) tip.style.display = 'none';
}

/* ============================================================
   CHART STATE STORE — keep data for re-render on hover
   ============================================================ */

const _chartState = {};

function storeChartState(canvas, state) {
    const id = canvas.id || canvas.dataset.chartId || ('chart-' + Math.random());
    if (!canvas.id) canvas.id = id;
    _chartState[id] = state;
}

function getChartState(canvas) {
    return _chartState[canvas.id] || null;
}

/* ============================================================
   SPARKLINE — Live view 24-hour trend
   ============================================================ */

function drawSparkline(canvas, scores, errors, timestamps) {
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();

    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const w = rect.width;
    const h = rect.height;
    const pad = { left: 40, right: 50, top: 16, bottom: 32 };

    if (scores && scores.length === 1) {
        ctx.fillStyle = getComputedColor('var(--ink)');
        ctx.beginPath();
        ctx.arc(w / 2, h / 2, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = getComputedColor('var(--ink-3)');
        ctx.font = '11px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(`Score: ${scores[0].toFixed(1)}`, w / 2, h / 2 + 20);
        return;
    }

    storeChartState(canvas, { type: 'sparkline', scores, errors, timestamps, w, h, pad });

    _renderSparklineFrame(ctx, scores, errors, timestamps, w, h, pad, -1);
    _attachSparklineEvents(canvas);
}

function _sparklineScaleY(val, min, range, h, pad) {
    return h - pad.bottom - ((val - min) / range) * (h - pad.top - pad.bottom);
}

function _sparklineX(i, n, pad, w) {
    return pad.left + (i / (n - 1)) * (w - pad.left - pad.right);
}

function _renderSparklineFrame(ctx, scores, errors, timestamps, w, h, pad, hoverIdx) {
    ctx.clearRect(0, 0, w, h);

    const chartL = pad.left;
    const chartR = w - pad.right;
    const chartT = pad.top;
    const chartB = h - pad.bottom;

    /* Score Y-axis (left): 0-100 */
    const sMin = 0;
    const sMax = 100;
    const sRange = 100;

    /* Error Y-axis (right): 0% to next whole percent above max */
    const rawEMax = errors && errors.length > 0 ? Math.max(...errors) : 0.05;
    const eMax = Math.max(Math.ceil(rawEMax * 100), 1);
    const eMin = 0;
    const eRange = eMax;

    /* Grid lines + Y-axis labels */
    ctx.font = '10px sans-serif';
    const ySteps = 4;
    for (let i = 0; i <= ySteps; i++) {
        const sVal = sMin + (sRange * i / ySteps);
        const y = chartB - (i / ySteps) * (chartB - chartT);

        ctx.strokeStyle = getComputedColor('var(--rule)');
        ctx.lineWidth = 0.5;
        ctx.beginPath();
        ctx.moveTo(chartL, y);
        ctx.lineTo(chartR, y);
        ctx.stroke();

        /* Left: score */
        ctx.fillStyle = getComputedColor('var(--ink)');
        ctx.textAlign = 'right';
        ctx.fillText(Math.round(sVal).toString(), chartL - 6, y + 3);

        /* Right: error % */
        const eVal = eMin + (eRange * i / ySteps);
        ctx.fillStyle = getComputedColor('var(--amber)');
        ctx.textAlign = 'left';
        ctx.fillText(eVal.toFixed(1) + '%', chartR + 6, y + 3);
    }

    /* X-axis time labels */
    const n = scores ? scores.length : 0;
    const tsLabels = timestamps && timestamps.length >= n ? timestamps : null;

    if (n > 1) {
        ctx.fillStyle = getComputedColor('var(--ink-3)');
        ctx.font = '10px sans-serif';
        const labelCount = Math.min(n, 6);
        const step = Math.max(1, Math.floor((n - 1) / (labelCount - 1)));

        for (let i = 0; i < n; i += step) {
            const x = _sparklineX(i, n, pad, w);
            const label = tsLabels ? formatChartLabel(tsLabels[i]) : `${i}`;
            ctx.textAlign = i === 0 ? 'left' : 'center';
            ctx.fillText(label, x, h - 6);
        }
        /* Always show last */
        const lastIdx = n - 1;
        if (lastIdx % step !== 0) {
            const x = _sparklineX(lastIdx, n, pad, w);
            const label = tsLabels ? formatChartLabel(tsLabels[lastIdx]) : `${lastIdx}`;
            ctx.textAlign = 'right';
            ctx.fillText(label, x, h - 6);
        }
    }

    /* Draw error line (amber) — line only, no fill */
    if (errors && errors.length > 1) {
        ctx.beginPath();
        ctx.strokeStyle = getComputedColor('var(--amber)');
        ctx.lineWidth = 1.5;
        ctx.lineJoin = 'round';
        ctx.setLineDash([4, 3]);
        for (let i = 0; i < errors.length; i++) {
            const x = _sparklineX(i, errors.length, pad, w);
            const y = _sparklineScaleY(errors[i] * 100, eMin, eRange, h, pad);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();
        ctx.setLineDash([]);

        /* Small dots on error line */
        ctx.fillStyle = getComputedColor('var(--amber)');
        for (let i = 0; i < errors.length; i++) {
            const x = _sparklineX(i, errors.length, pad, w);
            const y = _sparklineScaleY(errors[i] * 100, eMin, eRange, h, pad);
            ctx.beginPath();
            ctx.arc(x, y, 1.5, 0, Math.PI * 2);
            ctx.fill();
        }
    }

    /* Draw score line (dark) — solid line with very subtle fill */
    if (scores && scores.length > 1) {
        ctx.beginPath();
        ctx.strokeStyle = getComputedColor('var(--ink)');
        ctx.lineWidth = 2;
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';
        for (let i = 0; i < n; i++) {
            const x = _sparklineX(i, n, pad, w);
            const y = _sparklineScaleY(scores[i], sMin, sRange, h, pad);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();

        /* Subtle fill under score line */
        const lastX = _sparklineX(n - 1, n, pad, w);
        ctx.lineTo(lastX, chartB);
        ctx.lineTo(chartL, chartB);
        ctx.closePath();
        const grad = ctx.createLinearGradient(0, chartT, 0, chartB);
        grad.addColorStop(0, 'rgba(15, 23, 42, 0.06)');
        grad.addColorStop(1, 'rgba(15, 23, 42, 0.01)');
        ctx.fillStyle = grad;
        ctx.fill();

        /* Small dots on score line */
        ctx.fillStyle = getComputedColor('var(--ink)');
        for (let i = 0; i < n; i++) {
            const x = _sparklineX(i, n, pad, w);
            const y = _sparklineScaleY(scores[i], sMin, sRange, h, pad);
            ctx.beginPath();
            ctx.arc(x, y, 2, 0, Math.PI * 2);
            ctx.fill();
        }
    }

    /* Hover crosshair + enlarged dots */
    if (hoverIdx >= 0 && scores && hoverIdx < scores.length) {
        const x = _sparklineX(hoverIdx, n, pad, w);

        ctx.strokeStyle = getComputedColor('var(--ink-4)');
        ctx.lineWidth = 0.5;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(x, chartT);
        ctx.lineTo(x, chartB);
        ctx.stroke();
        ctx.setLineDash([]);

        const sy = _sparklineScaleY(scores[hoverIdx], sMin, sRange, h, pad);
        ctx.fillStyle = getComputedColor('var(--ink)');
        ctx.beginPath();
        ctx.arc(x, sy, 4, 0, Math.PI * 2);
        ctx.fill();

        if (errors && hoverIdx < errors.length) {
            const ey = _sparklineScaleY(errors[hoverIdx] * 100, eMin, eRange, h, pad);
            ctx.fillStyle = getComputedColor('var(--amber)');
            ctx.beginPath();
            ctx.arc(x, ey, 4, 0, Math.PI * 2);
            ctx.fill();
        }
    }
}

function _attachSparklineEvents(canvas) {
    if (canvas._hasSparklineEvents) return;
    canvas._hasSparklineEvents = true;

    canvas.style.cursor = 'crosshair';

    canvas.addEventListener('mousemove', (e) => {
        const st = getChartState(canvas);
        if (!st || st.type !== 'sparkline') return;
        const { scores, errors, timestamps, w, h, pad } = st;
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const n = scores ? scores.length : 0;
        if (n < 2) return;

        const idx = Math.round(((mx - pad.left) / (w - pad.left - pad.right)) * (n - 1));
        const clamped = Math.max(0, Math.min(n - 1, idx));

        const dpr = window.devicePixelRatio || 1;
        const ctx = canvas.getContext('2d');
        ctx.save();
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        _renderSparklineFrame(ctx, scores, errors, timestamps, w, h, pad, clamped);
        ctx.restore();

        let timeLabel = timestamps && clamped < timestamps.length
            ? formatChartLabel(timestamps[clamped]) : '';
        let tip = timeLabel ? `<strong>${timeLabel}</strong><br>` : '';
        tip += `Score: ${scores[clamped].toFixed(1)}`;
        if (errors && clamped < errors.length) {
            tip += `<br>Error: ${(errors[clamped] * 100).toFixed(2)}%`;
        }
        showTooltip(e, tip);
    });

    canvas.addEventListener('mouseleave', () => {
        const st = getChartState(canvas);
        if (!st || st.type !== 'sparkline') return;
        const { scores, errors, timestamps, w, h, pad } = st;
        const dpr = window.devicePixelRatio || 1;
        const ctx = canvas.getContext('2d');
        ctx.save();
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        _renderSparklineFrame(ctx, scores, errors, timestamps, w, h, pad, -1);
        ctx.restore();
        hideTooltip();
    });
}

/* ============================================================
   LINE CHART — stress score over time
   ============================================================ */

function drawLineChart(canvasId, dataObj, label) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();

    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const entries = Object.entries(dataObj).sort(([a], [b]) => a.localeCompare(b));
    if (entries.length === 0) return;

    const values = entries.map(([, v]) => v);
    const labels = entries.map(([k]) => k);
    const w = rect.width;
    const h = rect.height;
    const pad = { left: 40, right: 16, top: 16, bottom: 28 };

    const max = Math.max(...values);
    const min = Math.min(...values);
    const range = max - min || 1;

    const points = _computeLinePoints(entries, values, min, range, w, h, pad);

    storeChartState(canvas, {
        type: 'line', entries, values, labels, points, w, h, pad, min, max, range, label,
    });

    _renderLineFrame(ctx, w, h, pad, entries, values, points, min, max, range, label, -1);
    _attachLineEvents(canvas);
}

function _computeLinePoints(entries, values, min, range, w, h, pad) {
    const points = [];
    for (let i = 0; i < entries.length; i++) {
        const x = pad.left + (i / (entries.length - 1)) * (w - pad.left - pad.right);
        const y = h - pad.bottom - ((values[i] - min) / range) * (h - pad.top - pad.bottom);
        points.push([x, y]);
    }
    return points;
}

function _renderLineFrame(ctx, w, h, pad, entries, values, points, min, max, range, label, hoverIdx) {
    ctx.clearRect(0, 0, w, h);

    /* Y-axis */
    ctx.fillStyle = getComputedColor('var(--ink-4)');
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'right';
    const ySteps = 4;
    for (let i = 0; i <= ySteps; i++) {
        const val = min + (range * i / ySteps);
        const y = h - pad.bottom - (i / ySteps) * (h - pad.top - pad.bottom);
        ctx.fillText(val.toFixed(1), pad.left - 6, y + 3);
        ctx.strokeStyle = getComputedColor('var(--rule)');
        ctx.lineWidth = 0.5;
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(w - pad.right, y);
        ctx.stroke();
    }

    if (entries.length === 1) {
        const cx = (pad.left + w - pad.right) / 2;
        const cy = (pad.top + h - pad.bottom) / 2;
        ctx.fillStyle = getComputedColor('var(--ink)');
        ctx.beginPath();
        ctx.arc(cx, cy, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.textAlign = 'center';
        ctx.fillText(entries[0][0], cx, h - 6);
        return;
    }

    /* Line + fill */
    ctx.beginPath();
    ctx.strokeStyle = getComputedColor('var(--ink)');
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    for (let i = 0; i < points.length; i++) {
        if (i === 0) ctx.moveTo(points[i][0], points[i][1]);
        else ctx.lineTo(points[i][0], points[i][1]);
    }
    ctx.stroke();

    ctx.lineTo(points[points.length - 1][0], h - pad.bottom);
    ctx.lineTo(points[0][0], h - pad.bottom);
    ctx.closePath();
    const grad = ctx.createLinearGradient(0, pad.top, 0, h - pad.bottom);
    grad.addColorStop(0, 'rgba(15, 23, 42, 0.1)');
    grad.addColorStop(1, 'rgba(15, 23, 42, 0.01)');
    ctx.fillStyle = grad;
    ctx.fill();

    /* Data points */
    for (let i = 0; i < points.length; i++) {
        const isHover = i === hoverIdx;
        ctx.fillStyle = getComputedColor(isHover ? 'var(--blue)' : 'var(--ink)');
        ctx.beginPath();
        ctx.arc(points[i][0], points[i][1], isHover ? 5 : 2.5, 0, Math.PI * 2);
        ctx.fill();
    }

    /* X-axis labels */
    ctx.fillStyle = getComputedColor('var(--ink-4)');
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'center';
    const step = Math.max(1, Math.floor(entries.length / 6));
    for (let i = 0; i < entries.length; i += step) {
        ctx.fillText(formatChartLabel(entries[i][0]), points[i][0], h - 6);
    }
    if (entries.length > 1) {
        ctx.fillText(formatChartLabel(entries[entries.length - 1][0]), points[points.length - 1][0], h - 6);
    }

    /* Hover crosshair */
    if (hoverIdx >= 0 && hoverIdx < points.length) {
        const [hx, hy] = points[hoverIdx];
        ctx.strokeStyle = getComputedColor('var(--ink-4)');
        ctx.lineWidth = 0.5;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(hx, pad.top);
        ctx.lineTo(hx, h - pad.bottom);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(pad.left, hy);
        ctx.lineTo(w - pad.right, hy);
        ctx.stroke();
        ctx.setLineDash([]);
    }
}

function _attachLineEvents(canvas) {
    if (canvas._hasLineEvents) return;
    canvas._hasLineEvents = true;
    canvas.style.cursor = 'crosshair';

    canvas.addEventListener('mousemove', (e) => {
        const st = getChartState(canvas);
        if (!st || st.type !== 'line') return;
        const { entries, values, points, w, h, pad, min, max, range, label } = st;
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;

        const idx = _nearestPointIndex(points, mx);
        const dpr = window.devicePixelRatio || 1;
        const ctx = canvas.getContext('2d');
        ctx.save();
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        _renderLineFrame(ctx, w, h, pad, entries, values, points, min, max, range, label, idx);
        ctx.restore();

        showTooltip(e, `<strong>${formatChartLabel(entries[idx][0])}</strong><br>${label || 'Value'}: ${values[idx].toFixed(1)}`);
    });

    canvas.addEventListener('mouseleave', () => {
        const st = getChartState(canvas);
        if (!st || st.type !== 'line') return;
        const { entries, values, points, w, h, pad, min, max, range, label } = st;
        const dpr = window.devicePixelRatio || 1;
        const ctx = canvas.getContext('2d');
        ctx.save();
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        _renderLineFrame(ctx, w, h, pad, entries, values, points, min, max, range, label, -1);
        ctx.restore();
        hideTooltip();
    });
}

/* ============================================================
   BAR CHART — historical error/outage by year
   ============================================================ */

function drawBarChart(canvasId, dataObj) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();

    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const entries = Object.entries(dataObj).sort(([a], [b]) => a.localeCompare(b));
    if (entries.length === 0) return;

    const values = entries.map(([, v]) => v);
    const max = Math.max(...values) || 1;
    const w = rect.width;
    const h = rect.height;
    const pad = { left: 40, right: 16, top: 16, bottom: 28 };
    const chartW = w - pad.left - pad.right;
    const chartH = h - pad.top - pad.bottom;
    const slotWidth = chartW / Math.max(entries.length, 3);
    const barWidth = Math.min(slotWidth * 0.6, 60);

    storeChartState(canvas, {
        type: 'bar', entries, values, max, w, h, pad, chartW, chartH, slotWidth, barWidth,
    });

    _renderBarFrame(ctx, entries, values, max, w, h, pad, chartW, chartH, slotWidth, barWidth, -1);
    _attachBarEvents(canvas);
}

function _renderBarFrame(ctx, entries, values, max, w, h, pad, chartW, chartH, slotWidth, barWidth, hoverIdx) {
    ctx.clearRect(0, 0, w, h);

    /* Y-axis */
    ctx.fillStyle = getComputedColor('var(--ink-4)');
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'right';
    const ySteps = 4;
    for (let i = 0; i <= ySteps; i++) {
        const val = (max * i / ySteps);
        const y = h - pad.bottom - (i / ySteps) * chartH;
        ctx.fillText(Math.round(val).toString(), pad.left - 6, y + 3);
        ctx.strokeStyle = getComputedColor('var(--rule)');
        ctx.lineWidth = 0.5;
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(w - pad.right, y);
        ctx.stroke();
    }

    /* Bars */
    for (let i = 0; i < entries.length; i++) {
        const x = pad.left + i * slotWidth + (slotWidth - barWidth) / 2;
        const barH = (values[i] / max) * chartH;
        const y = h - pad.bottom - barH;
        const isHover = i === hoverIdx;

        const grad = ctx.createLinearGradient(x, y, x, h - pad.bottom);
        if (isHover) {
            grad.addColorStop(0, getComputedColor('var(--blue)'));
            grad.addColorStop(1, getComputedColor('var(--ink-2)'));
        } else {
            grad.addColorStop(0, getComputedColor('var(--ink)'));
            grad.addColorStop(1, getComputedColor('var(--ink-2)'));
        }
        ctx.fillStyle = grad;
        ctx.fillRect(x, y, barWidth, barH);

        /* Value on top — only for hovered or if few bars */
        if (isHover || entries.length <= 12) {
            ctx.fillStyle = getComputedColor(isHover ? 'var(--blue)' : 'var(--ink)');
            ctx.font = isHover ? 'bold 11px sans-serif' : '11px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(values[i].toString(), x + barWidth / 2, y - 6);
        }
    }

    /* X-axis labels */
    ctx.fillStyle = getComputedColor('var(--ink-4)');
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'center';
    const step = entries.length > 15 ? Math.ceil(entries.length / 10) : 1;
    for (let i = 0; i < entries.length; i += step) {
        const x = pad.left + i * slotWidth + slotWidth / 2;
        const isH = i === hoverIdx;
        if (isH) {
            ctx.fillStyle = getComputedColor('var(--blue)');
            ctx.font = 'bold 10px sans-serif';
        } else {
            ctx.fillStyle = getComputedColor('var(--ink-4)');
            ctx.font = '10px sans-serif';
        }
        ctx.fillText(formatChartLabel(entries[i][0]), x, h - 6);
    }

    /* Hover highlight line */
    if (hoverIdx >= 0 && hoverIdx < entries.length) {
        const x = pad.left + hoverIdx * slotWidth + slotWidth / 2;
        ctx.strokeStyle = getComputedColor('var(--blue)');
        ctx.lineWidth = 0.5;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(x, pad.top);
        ctx.lineTo(x, h - pad.bottom);
        ctx.stroke();
        ctx.setLineDash([]);
    }
}

function _attachBarEvents(canvas) {
    if (canvas._hasBarEvents) return;
    canvas._hasBarEvents = true;
    canvas.style.cursor = 'crosshair';

    canvas.addEventListener('mousemove', (e) => {
        const st = getChartState(canvas);
        if (!st || st.type !== 'bar') return;
        const { entries, values, max, w, h, pad, chartW, chartH, slotWidth, barWidth } = st;
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;

        const idx = Math.floor((mx - pad.left) / slotWidth);
        const clamped = Math.max(0, Math.min(entries.length - 1, idx));

        const dpr = window.devicePixelRatio || 1;
        const ctx = canvas.getContext('2d');
        ctx.save();
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        _renderBarFrame(ctx, entries, values, max, w, h, pad, chartW, chartH, slotWidth, barWidth, clamped);
        ctx.restore();

        showTooltip(e, `<strong>${entries[clamped][0]}</strong><br>${values[clamped].toLocaleString()}`);
    });

    canvas.addEventListener('mouseleave', () => {
        const st = getChartState(canvas);
        if (!st || st.type !== 'bar') return;
        const { entries, values, max, w, h, pad, chartW, chartH, slotWidth, barWidth } = st;
        const dpr = window.devicePixelRatio || 1;
        const ctx = canvas.getContext('2d');
        ctx.save();
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        _renderBarFrame(ctx, entries, values, max, w, h, pad, chartW, chartH, slotWidth, barWidth, -1);
        ctx.restore();
        hideTooltip();
    });
}

/* ============================================================
   SHARED UTILITIES
   ============================================================ */

function _drawFilledLine(ctx, data, w, h, padding, color, lineWidth) {
    const max = Math.max(...data);
    const min = Math.min(...data);
    const range = max - min || 1;

    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';

    for (let i = 0; i < data.length; i++) {
        const x = padding + (i / (data.length - 1)) * (w - 2 * padding);
        const y = h - padding - ((data[i] - min) / range) * (h - 2 * padding);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.stroke();

    ctx.lineTo(padding + ((data.length - 1) / (data.length - 1)) * (w - 2 * padding), h - padding);
    ctx.lineTo(padding, h - padding);
    ctx.closePath();
    const gradient = ctx.createLinearGradient(0, 0, 0, h);
    gradient.addColorStop(0, color.replace(')', ', 0.15)').replace('rgb(', 'rgba('));
    gradient.addColorStop(1, color.replace(')', ', 0.02)').replace('rgb(', 'rgba('));
    ctx.fillStyle = gradient;
    ctx.fill();
}

function _nearestPointIndex(points, mx) {
    let best = 0;
    let bestDist = Infinity;
    for (let i = 0; i < points.length; i++) {
        const d = Math.abs(points[i][0] - mx);
        if (d < bestDist) { bestDist = d; best = i; }
    }
    return best;
}

function formatChartLabel(label) {
    if (label.includes('T')) {
        const parts = label.split('T');
        const time = parts[1] || '';
        return time.substring(0, 5);
    }
    if (/^\d{4}-\d{2}$/.test(label)) {
        const [y, m] = label.split('-');
        const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
        return `${months[parseInt(m) - 1]} '${y.slice(2)}`;
    }
    return label;
}

function getComputedColor(cssVar) {
    if (!cssVar.startsWith('var(')) return cssVar;
    const prop = cssVar.replace('var(', '').replace(')', '');
    return getComputedStyle(document.documentElement).getPropertyValue(prop).trim() || '#111';
}
