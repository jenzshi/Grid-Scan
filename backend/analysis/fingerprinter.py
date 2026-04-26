"""Match current conditions against historical stress signatures."""

from backend.config import HISTORICAL_FINGERPRINTS

# Fields used for similarity scoring, with weights
_COMPARISON_FIELDS = {
    "peak_error_pct": 2.0,
    "thermal_outage_mw_peak": 1.5,
    "prc_collapsed": 1.0,
    "eea_level_reached": 1.0,
    "load_shed_mw": 0.5,
}

_MATCH_THRESHOLD = 0.4
_LOW_FIDELITY_CAP = 0.5


def fingerprint(current: dict) -> dict:
    """
    Score current conditions against each historical signature.

    Skips any field that is None when computing similarity.
    Weights score by the number of non-None fields matched.
    Low-fidelity entries cap similarity at 0.5.

    Args:
        current: Dict with keys like season, peak_error_pct,
                 thermal_outage_mw_peak, prc_collapsed, etc.

    Returns:
        Dict with 'match' (label or None) and 'similarity' (0-1 or None).
    """
    best_label = None
    best_score = 0.0

    for key, signature in HISTORICAL_FINGERPRINTS.items():
        score = _score_against(current, signature)
        if score > best_score:
            best_score = score
            best_label = signature["label"]

    if best_score < _MATCH_THRESHOLD:
        return {"match": None, "similarity": None}

    return {"match": best_label, "similarity": round(best_score, 3)}


def _score_against(current: dict, signature: dict) -> float:
    """
    Compute similarity between current conditions and one historical signature.

    Args:
        current: Current conditions dict.
        signature: Historical fingerprint dict from config.

    Returns:
        Similarity score between 0 and 1.
    """
    if not _season_compatible(current.get("season"), signature.get("season")):
        return 0.0

    total_weight = 0.0
    weighted_score = 0.0

    for field, weight in _COMPARISON_FIELDS.items():
        current_val = current.get(field)
        sig_val = signature.get(field)

        if current_val is None or sig_val is None:
            continue

        similarity = _field_similarity(field, current_val, sig_val, signature)
        weighted_score += similarity * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0

    raw_score = weighted_score / total_weight

    # Penalize for fewer matched fields (less confidence)
    fields_matched = total_weight / sum(_COMPARISON_FIELDS.values())
    confidence_adjusted = raw_score * (0.3 + 0.7 * fields_matched)

    # Cap low-fidelity entries
    is_low_fidelity = signature.get("data_fidelity") == "low"
    if is_low_fidelity:
        confidence_adjusted = min(confidence_adjusted, _LOW_FIDELITY_CAP)

    return confidence_adjusted


def _season_compatible(current_season: str | None, sig_season: str | None) -> bool:
    """
    Check if seasons are compatible for matching.

    Args:
        current_season: Current season string.
        sig_season: Signature season string.

    Returns:
        True if compatible.
    """
    if current_season is None or sig_season is None:
        return True
    return current_season == sig_season


def _field_similarity(
    field: str,
    current_val,
    sig_val,
    signature: dict,
) -> float:
    """
    Compute similarity for a single field.

    For boolean fields, exact match = 1.0, mismatch = 0.0.
    For numeric fields, uses range-based proximity.
    Also checks _range fields on the signature for fuzzy matching.

    Args:
        field: Field name.
        current_val: Current value.
        sig_val: Signature value.
        signature: Full signature dict (for range lookups).

    Returns:
        Similarity between 0 and 1.
    """
    if isinstance(sig_val, bool):
        return 1.0 if current_val == sig_val else 0.0

    if isinstance(sig_val, (int, float)) and isinstance(current_val, (int, float)):
        range_key = f"{field}_range"
        sig_range = signature.get(range_key)
        if sig_range and isinstance(sig_range, tuple) and len(sig_range) == 2:
            return _in_range_similarity(current_val, sig_range)
        # Both near zero is not a strong signal — reduce contribution
        if abs(sig_val) < 1 and abs(current_val) < 1:
            return 0.3
        return _numeric_similarity(current_val, sig_val)

    return 1.0 if current_val == sig_val else 0.0


def _numeric_similarity(current: float, target: float) -> float:
    """
    Compute similarity between two numeric values.

    Uses relative difference with a decay function.

    Args:
        current: Current numeric value.
        target: Target numeric value.

    Returns:
        Similarity between 0 and 1.
    """
    if target == 0 and current == 0:
        return 1.0
    max_val = max(abs(current), abs(target), 1.0)
    diff_ratio = abs(current - target) / max_val
    return max(0.0, 1.0 - diff_ratio)


def _in_range_similarity(value: float, value_range: tuple) -> float:
    """
    Score 1.0 if value falls within range, decay outside.

    Args:
        value: Value to check.
        value_range: (low, high) tuple.

    Returns:
        Similarity between 0 and 1.
    """
    low, high = value_range
    if low <= value <= high:
        return 1.0
    range_span = high - low if high > low else 1.0
    if value < low:
        distance = (low - value) / range_span
    else:
        distance = (value - high) / range_span
    return max(0.0, 1.0 - distance)
