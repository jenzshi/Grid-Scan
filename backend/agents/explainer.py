"""Claude API plain-language event summaries. Mock mode uses templates."""

import logging

from backend.config import MOCK_MODE, ANTHROPIC_API_KEY
from backend.exceptions import ExplainerError

logger = logging.getLogger(__name__)


def generate_summary(event: dict) -> str:
    """
    Generate a plain-English 3-sentence event summary.

    In mock mode, uses template-based generation.
    In live mode, calls Claude API.

    Args:
        event: Structured event dict with cause, peak_error_mw, etc.

    Returns:
        Plain-language summary string.
    """
    if MOCK_MODE:
        return _mock_summary(event)
    try:
        return _live_summary(event)
    except Exception as exc:
        raise ExplainerError(f"Failed to generate summary: {exc}") from exc


def _live_summary(event: dict) -> str:
    """
    Generate a summary using the Claude API.

    Args:
        event: Structured event dict.

    Returns:
        Three-sentence plain-language summary.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = _build_prompt(event)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )

    return message.content[0].text.strip()


def _build_prompt(event: dict) -> str:
    """
    Build the prompt for Claude to generate an event summary.

    Args:
        event: Event dict with all fields.

    Returns:
        Prompt string.
    """
    cause = event.get("cause", "unknown")
    peak_mw = event.get("peak_error_mw", 0)
    peak_pct = event.get("peak_error_pct", 0)
    growth = event.get("error_growth_rate_mw_per_hour", 0)
    lag = event.get("response_lag_minutes")
    adequate = event.get("response_adequate")
    fp_match = event.get("fingerprint_match")
    fp_sim = event.get("fingerprint_similarity")

    return (
        "You are an ERCOT grid analyst. Write exactly 3 sentences explaining "
        "this stress event in plain English. No jargon. No hedging. "
        "Explain what happened, why, and what it means for grid reliability.\n\n"
        f"Cause: {cause}\n"
        f"Peak forecast error: {abs(peak_mw):.0f} MW ({abs(peak_pct)*100:.1f}%)\n"
        f"Error growth rate: {growth:.0f} MW/hour\n"
        f"Response lag: {lag} minutes\n"
        f"Response adequate: {adequate}\n"
        f"Historical pattern match: {fp_match} "
        f"(similarity: {fp_sim*100:.0f}%)\n" if fp_match and fp_sim else
        "You are an ERCOT grid analyst. Write exactly 3 sentences explaining "
        "this stress event in plain English. No jargon. No hedging. "
        "Explain what happened, why, and what it means for grid reliability.\n\n"
        f"Cause: {cause}\n"
        f"Peak forecast error: {abs(peak_mw):.0f} MW ({abs(peak_pct)*100:.1f}%)\n"
        f"Error growth rate: {growth:.0f} MW/hour\n"
        f"Response lag: {lag} minutes\n"
        f"Response adequate: {adequate}\n"
        f"No historical pattern match.\n"
    )


def _mock_summary(event: dict) -> str:
    """
    Generate a template-based summary for mock mode.

    Args:
        event: Event dict with cause, peak_error_mw, peak_error_pct, etc.

    Returns:
        Three-sentence summary string.
    """
    cause = event.get("cause", "unknown")
    peak_mw = event.get("peak_error_mw", 0)
    peak_pct = event.get("peak_error_pct", 0)
    pct_display = f"{abs(peak_pct) * 100:.1f}%"

    if cause == "supply_side":
        sentence_one = (
            f"Forecast error peaked at {abs(peak_mw):.0f} MW ({pct_display}) "
            f"as thermal generation tripped offline faster than expected."
        )
        sentence_two = (
            "The primary driver was supply-side: multiple generating units "
            "experienced forced outages simultaneously."
        )
    elif cause == "demand_side":
        sentence_one = (
            f"Forecast error peaked at {abs(peak_mw):.0f} MW ({pct_display}) "
            f"as actual demand outpaced projections."
        )
        sentence_two = (
            "The primary driver was demand-side: temperatures exceeded "
            "the forecast, pushing cooling load above expectations."
        )
    else:
        sentence_one = (
            f"Forecast error reached {abs(peak_mw):.0f} MW ({pct_display})."
        )
        sentence_two = "The cause could not be clearly attributed to a single factor."

    fp_match = event.get("fingerprint_match")
    if fp_match:
        sentence_three = (
            f"This pattern resembled {fp_match}, suggesting similar "
            f"underlying grid conditions."
        )
    else:
        sentence_three = (
            "No strong historical pattern match was identified for this event."
        )

    return f"{sentence_one} {sentence_two} {sentence_three}"
