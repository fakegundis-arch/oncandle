"""Confluence Rider - only joins a trend when several markets trend together.

Watches BTC, gold, Nasdaq and Dow on M1.  Each market gets a trend state
every minute (+1 up, -1 down, 0 = consolidating), using the same definition
as Trend Rider (EMA 50/200 alignment and slope, ADX > 25, Choppiness < 50).

A trade in market X is allowed only when X itself is trending AND at least
`min_agree` markets in total (X included) are trending the same way.  One
market trending alone is ignored.  Entry trigger (`entry`):
    "pullback" - X pulls back to EMA(20) and resumes (Trend Rider's trigger)
    "onset"    - enter X the minute the group reaches `min_agree` agreeing
                 markets (no pullback needed)
Stops, the 1:3 target and the break-even move at 1R are identical to Trend
Rider.  A market whose feed has no bar for more than `stale_minutes`
(index closed, weekend) counts as not trending.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import trend_rider as tr


@dataclass
class Params:
    min_agree: int = 2
    entry: str = "pullback"
    stale_minutes: int = 5
    base: tr.Params = None

    def __post_init__(self):
        if self.base is None:
            self.base = tr.Params()


def group_trend(states: dict[str, pd.Series], stale_minutes: int) -> pd.DataFrame:
    """Align every market's trend state on one minute grid."""
    idx = pd.DatetimeIndex(sorted(set().union(*(s.index for s in states.values()))))
    return pd.DataFrame({k: s.reindex(idx).ffill(limit=stale_minutes).fillna(0) for k, s in states.items()})


def signals(universe: dict[str, pd.DataFrame], p: Params) -> dict[str, pd.DataFrame]:
    base = {k: tr.signals(df, p.base) for k, df in universe.items()}
    g = group_trend({k: b["trend"] for k, b in base.items()}, p.stale_minutes)
    n_up = (g == 1).sum(axis=1)
    n_dn = (g == -1).sum(axis=1)

    out = {}
    for k, b in base.items():
        up_ok = (n_up.reindex(b.index) >= p.min_agree) & (b["trend"] == 1)
        dn_ok = (n_dn.reindex(b.index) >= p.min_agree) & (b["trend"] == -1)
        if p.entry == "onset":
            prev_up = n_up.shift().reindex(b.index) < p.min_agree
            prev_dn = n_dn.shift().reindex(b.index) < p.min_agree
            long_ = up_ok & prev_up & b["long_ok"]
            short_ = dn_ok & prev_dn & b["short_ok"]
        else:
            long_ = up_ok & b["pb_long"]
            short_ = dn_ok & b["pb_short"]
        sig = np.where(long_, 1, np.where(short_, -1, 0))
        dist = np.where(sig == 1, b["long_dist"], np.where(sig == -1, b["short_dist"], 0.0))
        out[k] = pd.DataFrame({"signal": sig, "dist": np.nan_to_num(dist),
                               "n_up": n_up.reindex(b.index), "n_dn": n_dn.reindex(b.index)}, index=b.index)
    return out
