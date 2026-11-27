"""G3 (S9 plan): a causal status source for risk layer V3 built ONLY from the point-in-time epoch table.

An epoch row is (symbol, start, end); ``end`` is the end of the last observed candle. That an epoch has
ended is knowable only after the stale horizon without a candle, so the DELISTED event is stamped
``end + horizon`` (never ``end``). Epochs that run to the dataset cutoff are not delisted. Nothing here
reads a price; the status at time t depends only on epoch facts knowable at t (prefix invariance, tested)."""

from __future__ import annotations

import pandas as pd

from quantlab.risk_v3 import ScheduleFeed, Status


def epoch_status_events(
    epochs: list[dict], horizon: pd.Timedelta, cutoff: pd.Timestamp
) -> dict[str, list[tuple[pd.Timestamp, Status]]]:
    """``epochs``: dicts with ``symbol`` (pair name), ``end`` (pd.Timestamp) and optional ``open`` (bool: the
    epoch still runs at the cutoff). Returns ScheduleFeed events {pair: [(known_from, Status.DELISTED)]}."""
    events: dict[str, list[tuple[pd.Timestamp, Status]]] = {}
    for e in epochs:
        if e.get("open") or e["end"] >= cutoff:
            continue
        events.setdefault(e["symbol"], []).append((e["end"] + horizon, Status.DELISTED))
    return events


def epoch_feed(epochs: list[dict], horizon: pd.Timedelta, cutoff: pd.Timestamp) -> ScheduleFeed:
    return ScheduleFeed(epoch_status_events(epochs, horizon, cutoff))


def truncate_epochs(epochs: list[dict], t: pd.Timestamp, horizon: pd.Timedelta) -> list[dict]:
    """The epoch table as knowable at time ``t``: epochs starting after t do not exist yet, and an epoch counts
    as ended only once ``horizon`` has passed without a candle; otherwise it is open (the future is unknown)."""
    out = []
    for e in epochs:
        if e["start"] > t:
            continue
        ended = (not e.get("open")) and e["end"] + horizon <= t
        out.append({**e, "end": min(e["end"], t), "open": not ended})
    return out
