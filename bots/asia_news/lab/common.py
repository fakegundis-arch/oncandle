"""Lab helpers for the Nasdaq v2 study (Jan-Jun 2026 only, data through scripts/asia_news_lab.py).

Run from the repository root with PYTHONDONTWRITEBYTECODE=1.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
NQ = HERE.parent
sys.path.insert(0, str(NQ.parents[1] / "scripts"))
sys.path.insert(0, str(NQ))                   # the bot folder (events / signal code unchanged from v1)
import asia_news_lab as L  # noqa: E402
from newsbot.events import releases_from_frame  # noqa: E402
from newsbot.signal import currency_bias  # noqa: E402

SYM = "NAS100"
COST = L.COST[SYM]
TB = ["unemployment rate", "cpi y/y", "cpi q/q"]
T0, T1 = pd.Timestamp(L.TRAIN[0]), pd.Timestamp(L.TRAIN[1])
ONE = pd.Timedelta(minutes=1)

_C: dict = {}


def cal():
    if "cal" not in _C:
        _C["cal"] = L.calendar_train()
    return _C["cal"]


def px():
    if "px" not in _C:
        m = L.prices_train(SYM)
        _C["px"] = m
    return _C["px"]


def rels():
    """Releases (newsbot grouping) inside Jan-Jun 2026."""
    if "rels" not in _C:
        _C["rels"] = [r for r in releases_from_frame(cal()) if T0 <= pd.Timestamp(r.time) < T1]
    return _C["rels"]


def rel_table() -> pd.DataFrame:
    rows = []
    for r in rels():
        b = currency_bias(r, {"vote": "ff", "tiebreak": TB})
        b0 = currency_bias(r, {"vote": "ff"})
        votes = [v for _, v in b.votes]
        rows.append(dict(time=pd.Timestamp(r.time), ccy=r.currency, kind=r.kind, nfig=len(r.figures),
                         score=b.score, bias=b.bias, bias_notb=b0.bias, agree=int(len(votes) > 0 and all(v == votes[0] and v != 0 for v in votes)),
                         figs="; ".join(f"{f.name[:18]} {f.actual:g}/{f.forecast:g}/{f.previous:g} v{f.verdict}" for f in r.figures)))
    return pd.DataFrame(rows)


def arrays():
    m = px()
    return m.index.values, m.open.to_numpy(), m.high.to_numpy(), m.low.to_numpy(), m.close.to_numpy()


def idx_at(t) -> int:
    """index of the first bar at or after t"""
    return int(px().index.searchsorted(pd.Timestamp(t)))


def idx_before(t) -> int:
    """index of the last bar strictly before t"""
    return int(px().index.searchsorted(pd.Timestamp(t))) - 1


def atr_h1(t, n=24) -> float:
    """mean true range of the n hourly bars before t (same definition as newsbot.strategy.atr)."""
    m = px()
    w = m.loc[t - pd.Timedelta(minutes=60 * (n + 1) * 3): t - ONE]
    agg = w.resample("60min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    agg = agg.iloc[-(n + 1):]
    pc = agg.close.shift(1)
    tr = pd.concat([agg.high - agg.low, (agg.high - pc).abs(), (agg.low - pc).abs()], axis=1).max(axis=1).iloc[1:]
    return float(tr.mean())


def placebo_times(times, weekdays_only=True, exclude_days=None, months=None) -> list:
    """Same clock time (UTC hh:mm) on every other weekday in Jan-Jun 2026 that has no target release that day."""
    m = px()
    ex = set(exclude_days or [])
    out = []
    days = pd.date_range(T0, T1 - ONE, freq="D")
    for t in times:
        t = pd.Timestamp(t)
        for d in days:
            pt = d + pd.Timedelta(hours=t.hour, minutes=t.minute)
            if pt.date() == t.date():
                continue
            if weekdays_only and pt.weekday() >= 5:
                continue
            if pt.weekday() == 4 and pt.hour >= 20:
                continue
            if pt.date() in ex:
                continue
            out.append(pt)
    return sorted(set(out))
