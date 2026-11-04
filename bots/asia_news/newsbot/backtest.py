"""M1-exact backtest with the protocol's costs, using the same signal / plan code as the live bot.

Fills (bars are BID):
  * long  buys at the ask = bid + cost, exits at the bid; short sells at the bid, exits at the ask = bid + cost;
    a short's stop / target is hit when bid + cost reaches it
  * cost = `cost` (the protocol's base spread), x `news_mult` for a trade ENTERED within `news_window` minutes of the
    release; the trade pays that spread once, at the entry for a long, at the exit (stop / target / time) for a
    short - so a short entered at a release cannot escape the wide spread by exiting after the window
  * entry at the OPEN of the first bar at release + entry_delay minutes; skipped if the market is not quoting then
  * stop before target inside a minute; the entry minute can only stop out; a gap through a level fills at the open
  * time exit at the open of the first bar at / after the exit time; weekends closed by Friday 20:00 UTC
  * one position per instrument at a time (a release arriving while a trade is open is skipped)
make_trades(cfg, calendar, m1, cost) is the strategy entry point used by asia_news_lab.final_test.
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from .events import releases_from_frame
from .strategy import atr, confirmed, full_cfg, make_plan

_ATR: dict = {}                            # (frame fingerprint, release, tf, n) -> ATR  (speed only)
MAX_ENTRY_GAP = timedelta(minutes=2)       # market not quoting within 2 min of the planned entry -> skip


def simulate(m1: pd.DataFrame, plan, cost: float, news_mult: float, news_window: int):
    """Return (entry_time, exit_time, r, reason, entry_price, exit_price) or None if no entry."""
    idx = m1.index
    i = idx.searchsorted(pd.Timestamp(plan.entry_after))
    if i >= len(idx) or idx[i] - pd.Timestamp(plan.entry_after) > MAX_ENTRY_GAP:
        return None
    rel_t = pd.Timestamp(plan.release.time)
    win_end = rel_t + timedelta(minutes=news_window)
    o, h, l = m1.open.to_numpy(), m1.high.to_numpy(), m1.low.to_numpy()
    d, sd = plan.direction, plan.stop_dist
    t_e = idx[i]
    ct = cost * news_mult if t_e <= win_end else cost        # the trade's spread
    fill = o[i] + ct if d > 0 else o[i]                      # long buys at the ask, short sells at the bid
    sl = fill - d * sd
    tp = fill + d * plan.target_dist if np.isfinite(plan.target_dist) else None
    ex_t = pd.Timestamp(plan.exit_by)
    j = i
    while j < len(idx):
        t = idx[j]
        c = ct if d < 0 else 0.0                             # shorts exit at the ask
        if t >= ex_t and j > i:
            px = o[j] + c
            return t_e, t, d * (px - fill) / sd, "time", fill, px
        op, hi, lo = o[j] + c, h[j] + c, l[j] + c
        if j > i:                                            # gaps at the open
            if (d > 0 and op <= sl) or (d < 0 and op >= sl):
                return t_e, t, d * (op - fill) / sd, "stop-gap", fill, op
            if tp is not None and ((d > 0 and op >= tp) or (d < 0 and op <= tp)):
                return t_e, t, d * (op - fill) / sd, "target-gap", fill, op
        if (d > 0 and lo <= sl) or (d < 0 and hi >= sl):
            return t_e, t, -1.0, "stop", fill, sl
        if j > i and tp is not None and ((d > 0 and hi >= tp) or (d < 0 and lo <= tp)):
            return t_e, t, d * (tp - fill) / sd, "target", fill, tp
        j += 1
    px = m1.close.iloc[-1] + (ct if d < 0 else 0.0)
    return t_e, idx[-1], d * (px - fill) / sd, "end-of-data", fill, px


_REL: dict = {}


def _releases(calendar):
    k = (id(calendar), len(calendar))
    if k not in _REL:
        _REL.clear()
        _REL[k] = releases_from_frame(calendar)
    return _REL[k]


def make_trades(cfg: dict, calendar: pd.DataFrame, m1: pd.DataFrame, cost: float,
                entry_delay: int | None = None, detail: bool = False) -> pd.DataFrame:
    """Strategy for ONE instrument: cfg["symbol"] / cfg["instrument"] decide which releases it trades."""
    c = full_cfg(cfg)
    rels = _releases(calendar)
    lo, hi = m1.index[0], m1.index[-1]
    fp = (len(m1), lo, hi, float(m1.close.iloc[0]), float(m1.close.iloc[-1]), float(m1.high.max()))
    rows, busy_until = [], None
    for rel in rels:
        if not (lo <= pd.Timestamp(rel.time) <= hi):
            continue
        key = (fp, rel.time, int(c["stop_atr_tf"]), int(c["stop_atr_n"]))
        if key not in _ATR:
            _ATR[key] = atr(m1, rel.time, int(c["stop_atr_tf"]), int(c["stop_atr_n"]))
        plan = make_plan(rel, c, None, entry_delay, atr_value=_ATR[key])
        if plan is None:
            continue
        if busy_until is not None and pd.Timestamp(plan.entry_after) <= busy_until:
            continue
        if c["confirm"]:
            p0 = m1.index.searchsorted(pd.Timestamp(rel.time)) - 1          # last bar before the release minute
            k = m1.index.searchsorted(pd.Timestamp(plan.entry_after))
            if p0 < 0 or k >= len(m1) or not confirmed(plan.direction, m1.close.iloc[p0], m1.open.iloc[k]):
                continue
        res = simulate(m1, plan, cost, c["news_mult"], c["news_window"])
        if res is None:
            continue
        te, tx, r, why, fill, px = res
        busy_until = tx
        row = dict(entry_time=te, exit_time=tx, dir=plan.direction, r=float(r), event=plan.why)
        if detail:
            row.update(reason=why, entry=fill, exit=px, stop_dist=plan.stop_dist, ccy=rel.currency, kind=rel.kind,
                       release=pd.Timestamp(rel.time))
        rows.append(row)
    if rows:
        return pd.DataFrame(rows)
    return pd.DataFrame({"entry_time": pd.Series(dtype="datetime64[ns]"), "exit_time": pd.Series(dtype="datetime64[ns]"),
                         "dir": pd.Series(dtype=int), "r": pd.Series(dtype=float), "event": pd.Series(dtype=str)})
