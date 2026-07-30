"""Token pricing for the models this backend calls.

Rates verified 2026-07-29 against platform.claude.com/docs/en/about-claude/pricing.
Anthropic bills cache reads at 0.1x and 5-minute cache writes at 1.25x the
base input rate, so a cached call priced at the flat input rate overstates
its cost by up to 10x. cost_usd is the only place that arithmetic lives.
"""

import logging

logger = logging.getLogger(__name__)

# USD per million tokens, as (input, output). Keys are matched as prefixes
# so one entry covers both the undated alias a caller may configure and the
# dated id the API returns.
_RATES: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
}

_CACHE_READ_MULTIPLIER = 0.10
_CACHE_WRITE_MULTIPLIER = 1.25

_warned_unpriced: set[str] = set()


def _lookup(model: str) -> tuple[float, float] | None:
    """Longest matching prefix, so a dated id resolves through its alias."""
    best: str | None = None
    for prefix in _RATES:
        if model.startswith(prefix) and (best is None or len(prefix) > len(best)):
            best = prefix
    return _RATES[best] if best else None


def cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read: int,
    cache_creation: int,
) -> tuple[float, bool]:
    """Price one call. Returns (usd, priced).

    input_tokens is LangChain's true total, which already includes the
    cached tokens, so the cache portions are subtracted out before the base
    rate is applied and then charged at their own multipliers.
    """
    rate = _lookup(model)
    if rate is None:
        if model not in _warned_unpriced:
            _warned_unpriced.add(model)
            logger.warning("no price entry for model %r — its calls will report $0", model)
        return 0.0, False

    in_rate, out_rate = rate
    billable = max(0, input_tokens - cache_read - cache_creation)
    total = (
        billable * in_rate
        + cache_read * in_rate * _CACHE_READ_MULTIPLIER
        + cache_creation * in_rate * _CACHE_WRITE_MULTIPLIER
        + output_tokens * out_rate
    )
    return total / 1_000_000, True
