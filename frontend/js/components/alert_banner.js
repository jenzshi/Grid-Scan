/* Conditional alert banner for fingerprint matches >= 0.4 */

function renderAlertBanner(matchLabel, similarity, detail) {
    if (!matchLabel || similarity < 0.4) return '';

    const pct = Math.round(similarity * 100);
    const level = similarity >= 0.7 ? 'critical' : 'warning';

    let detailLine = '';
    if (detail && detail.notes) {
        const firstSentence = detail.notes.split('. ')[0] + '.';
        detailLine = `<br><span style="font-weight:400">${firstSentence}</span>`;
    }

    return `
        <div class="alert-banner ${level}">
            Current conditions resemble <strong>${matchLabel}</strong>.
            Similarity: ${pct}%${detailLine}
        </div>
    `;
}
