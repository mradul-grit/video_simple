"""Keep every analysis item inside the source video's real timeline.

Providers (mock, Whisper, an LLM) can return times past the end of the file:
padding, hallucinated tails, or fixed demo data. Nothing outside [0, duration]
may reach the database, the editor or a manifest.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

# Items shorter than this after clamping carry no usable content.
MIN_ITEM_SECONDS = 0.05


def bound_items(
    items: Iterable[dict[str, Any]],
    duration: float | None,
    *,
    start_key: str = "start_seconds",
    end_key: str = "end_seconds",
) -> list[dict[str, Any]]:
    """Clamp items to [0, duration]; drop items that end up empty or start after the end.

    With no known duration, only negative/inverted ranges are dropped.
    Returns new dicts; inputs are not mutated.
    """
    out = []
    for item in items:
        try:
            start = max(0.0, float(item[start_key]))
            end = float(item[end_key])
        except (KeyError, TypeError, ValueError):
            continue
        if duration is not None and duration > 0:
            if start >= duration:
                continue
            end = min(end, float(duration))
        if end - start < MIN_ITEM_SECONDS:
            continue
        out.append({**item, start_key: round(start, 3), end_key: round(end, 3)})
    return out


def overlap_ratio(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    """Intersection over union of two ranges (0 when disjoint)."""
    inter = max(0.0, min(a_end, b_end) - max(a_start, b_start))
    union = max(a_end, b_end) - min(a_start, b_start)
    return inter / union if union > 0 else 0.0
