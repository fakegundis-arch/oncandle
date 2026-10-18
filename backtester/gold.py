"""Gold Asian breakout lab: signals on M15, every trade simulated minute by minute on M1.

Baseline (the version in GoldAsianBreakout.mq5): XAUUSD M15, new trades only 00:00-06:00 UTC.
  * Donchian: close breaks the prior `don` bars' high (low), and the first close beyond it, with
    close > EMA(`ema`) and EMA rising vs `slope` bars ago (shorts mirror), OR
  * the first break of the previous UTC day's high / low in the session.
  Stop = max(`stop_atr` x ATR(14), $2); target `rr` R; stop to +`be_buf` R at +`be` R; one trade at a time.

Extensions tested here: session window, max trades/day, stop after a daily loss, volatility filter, daily-trend
filter, long/short only, partial take-profit, trailing stop after break-even, time exit.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import indicators as ind
from .engine import njit


@dataclass
class P:
    # entry
    don: int = 10
    ema: int = 400
    slope: int = 4
    prev_day: bool = True
    donchian: bool = True
    asian_range: int = 0          # >0: also trade a break of the first N minutes' range of the session
    ses_start: int = 0            # UTC hour (inclusive)
    ses_end: int = 6              # UTC hour (exclusive)
    side: int = 0                 # 0 both, 1 long only, -1 short only
    d1_trend: int = 0             # >0: require close vs EMA(n days of D1 closes) agreement
    vol_min: float = 0.0          # skip if ATR(14) / its 100-bar median < vol_min
    vol_max: float = 99.0
    strong_close: float = 0.0     # >0: signal bar must close in the top (bottom) fraction of its range
    regime_max: float = 99.0      # skip if ATR averaged over 5 days / over 60 days > regime_max
    regime_min: float = 0.0
    regime_warmup: int = 60       # days of history the 60-day regime average needs before it is used
    bar_min: int = 15             # signal bar length in minutes (the `m15` frame passed in must have this bar size)
    pd_range_min: float = 0.0     # skip if yesterday's range / daily ATR(14) (as of yesterday) < pd_range_min
    skip_weekdays: tuple = ()     # skip signals on these weekdays (0 = Monday)
    # exits
    stop_atr: float = 1.5
    min_stop: float = 2.0
    rr: float = 3.0
    be: float = 1.0
    be_buf: float = 0.1
    trail_atr: float = 0.0        # >0: after break-even, trail at this x ATR from the best price
    partial: float = 0.0          # fraction closed at `partial_r`
    partial_r: float = 1.5
    exit_hour: int = -1           # >=0: close any open trade at this UTC hour
    max_hold_h: float = 0.0       # >0: close after this many hours
    max_per_day: int = 99
    stop_after_loss: bool = False
    add_r: float = 0.0           # >0: add `add_size` units when the trade reaches +add_r R (after break-even)
    add_size: float = 0.0
    cost: float = 0.20


_CACHE: dict = {}


def data(root, symbol: str = "XAUUSD"):
    """M1 and M15 bars of `symbol` (default gold), cached per symbol."""
    if symbol not in _CACHE:
        from . import data as D
        m1 = D.load_csv(root / "data" / f"{symbol}_M1.csv").drop(columns="spread", errors="ignore")
        m15 = m1.resample("15min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
        _CACHE[symbol] = (m1, m15)
    return _CACHE[symbol]


def signals(m15: pd.DataFrame, p: P) -> pd.DataFrame:
    """Signal table on M15 bar starts: dir, sl (price), atr."""
    c, h, l = m15.close, m15.high, m15.low
    idx = m15.index
    hour = idx.hour
    ins = (hour >= p.ses_start) & (hour < p.ses_end) if p.ses_start < p.ses_end else (hour >= p.ses_start) | (hour < p.ses_end)
    ins = np.asarray(ins)
    atr = ind.atr(m15, 14)
    L = np.zeros(len(m15), bool)
    S = np.zeros(len(m15), bool)
    if p.donchian:
        up, dn = h.rolling(p.don).max().shift(), l.rolling(p.don).min().shift()
        e = ind.ema(c, p.ema)
        tu = (c > e) & (e > e.shift(p.slope))
        td = (c < e) & (e < e.shift(p.slope))
        L |= ((c > up) & (c.shift() <= up.shift()) & tu).to_numpy()
        S |= ((c < dn) & (c.shift() >= dn.shift()) & td).to_numpy()
    day = idx.normalize()
    if p.prev_day:
        dd = m15.groupby(day).agg(h=("high", "max"), l=("low", "min"))
        pdh = pd.Series(day).map(dd.h.shift()).to_numpy()
        pdl = pd.Series(day).map(dd.l.shift()).to_numpy()
        lb, sb = (c.to_numpy() > pdh) & ins, (c.to_numpy() < pdl) & ins
        first = pd.Series((lb | sb).astype(int)).groupby(day).cumsum().to_numpy() == 1
        L |= lb & first
        S |= sb & first
    if p.asian_range > 0:
        mod = hour * 60 + idx.minute
        s0 = p.ses_start * 60
        rng = (mod >= s0) & (mod < s0 + p.asian_range)
        hi = pd.Series(np.where(rng, h, np.nan)).groupby(day).transform("max").to_numpy()
        lo = pd.Series(np.where(rng, l, np.nan)).groupby(day).transform("min").to_numpy()
        after = mod >= s0 + p.asian_range
        lb, sb = ins & after & (c.to_numpy() > hi), ins & after & (c.to_numpy() < lo)
        first = pd.Series((lb | sb).astype(int)).groupby(day).cumsum().to_numpy() == 1
        L |= lb & first
        S |= sb & first
    L &= ins
    S &= ins
    if p.d1_trend > 0:
        dc = c.groupby(day).last()
        de = ind.ema(dc, p.d1_trend).shift()            # yesterday's value: no look-ahead
        dprev = dc.shift()
        up = pd.Series(day).map((dprev > de)).fillna(False).to_numpy(bool)
        dn = pd.Series(day).map((dprev < de)).fillna(False).to_numpy(bool)
        L &= up
        S &= dn
    if p.vol_min > 0 or p.vol_max < 99:
        rel = (atr / atr.rolling(100).median()).to_numpy()
        ok = (rel >= p.vol_min) & (rel <= p.vol_max)
        L &= ok
        S &= ok
    if p.regime_max < 99 or p.regime_min > 0:
        tr_ = ind.true_range(m15)
        bpd = 1440 // p.bar_min
        reg = (tr_.rolling(bpd * 5).mean() / tr_.rolling(bpd * 60, min_periods=bpd * p.regime_warmup).mean()).shift().to_numpy()
        ok = (reg <= p.regime_max) & (reg >= p.regime_min)
        L &= ok
        S &= ok
    if p.pd_range_min > 0:
        wk = m15[idx.weekday != 6]                                    # Sunday-evening bars are not a trading day
        d1 = wk.groupby(wk.index.normalize()).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                                                  close=("close", "last"))
        rel = ((d1.high - d1.low) / ind.atr(d1, 14)).shift()          # previous trading day vs ATR up to that day
        ok = pd.Series(day).map(rel).fillna(0).to_numpy() >= p.pd_range_min
        L &= ok
        S &= ok
    if p.skip_weekdays:
        ok = ~np.isin(idx.weekday, p.skip_weekdays)
        L &= ok
        S &= ok
    if p.strong_close > 0:
        pos = ((c - l) / (h - l).replace(0, np.nan)).to_numpy()
        L &= pos >= 1 - p.strong_close
        S &= pos <= p.strong_close
    if p.side == 1:
        S[:] = False
    elif p.side == -1:
        L[:] = False
    d = np.where(L, 1, np.where(S, -1, 0))
    sl = np.maximum(p.stop_atr * atr.to_numpy(), p.min_stop)
    k = (d != 0) & np.isfinite(sl)
    return pd.DataFrame({"dir": d[k], "sl": sl[k], "atr": atr.to_numpy()[k]}, index=idx[k])


@njit(cache=True)
def _run(o, h, l, c, mod, dayk, e_i, e_d, e_sl, e_atr, rr, be, be_buf, trail, partial, partial_r, exit_min,
         max_hold, max_per_day, stop_after_loss, cost, add_r=0.0, add_size=0.0):
    n_sig = len(e_i)
    out_in = np.zeros(n_sig, np.int64)
    out_ex = np.zeros(n_sig, np.int64)
    out_d = np.zeros(n_sig, np.int64)
    out_r = np.zeros(n_sig)
    nt = 0
    busy_until = -1
    cur_day = -1
    day_count = 0
    day_lost = False
    for q in range(n_sig):
        j = e_i[q]
        if j <= busy_until or j >= len(o):
            continue
        if dayk[j] != cur_day:
            cur_day = dayk[j]
            day_count = 0
            day_lost = False
        if day_count >= max_per_day or (stop_after_loss and day_lost):
            continue
        d = e_d[q]
        R = e_sl[q]
        entry = o[j] + cost if d == 1 else o[j]
        stop = entry - d * R
        tgt = entry + d * rr * R
        ptgt = entry + d * partial_r * R
        best = entry
        moved = False
        part_done = False
        realized = 0.0
        size = 1.0
        r = 0.0
        added = False
        add_px = 0.0
        k = j
        done = False
        px = 0.0                      # exit price on the position's closing side (bid for longs, ask for shorts)
        while k < len(o):
            bo = o[k] if d == 1 else o[k] + cost
            bh = h[k] if d == 1 else h[k] + cost
            bl = l[k] if d == 1 else l[k] + cost
            if k > j and ((exit_min >= 0 and mod[k] == exit_min) or (max_hold > 0 and k - j >= max_hold)):
                px = bo
                done = True
                break
            if d == 1:
                if bl <= stop:
                    px = min(bo, stop)
                    done = True
                    break
                if partial > 0 and not part_done and bh >= ptgt:
                    realized += partial * (max(bo, ptgt) - entry) / R
                    size -= partial
                    part_done = True
                if bh >= tgt:
                    px = max(bo, tgt)
                    done = True
                    break
                best = max(best, bh)
            else:
                if bh >= stop:
                    px = max(bo, stop)
                    done = True
                    break
                if partial > 0 and not part_done and bl <= ptgt:
                    realized += partial * (entry - min(bo, ptgt)) / R
                    size -= partial
                    part_done = True
                if bl <= tgt:
                    px = min(bo, tgt)
                    done = True
                    break
                best = min(best, bl)
            if be > 0 and not moved and d * (best - entry) >= be * R:
                stop = entry + d * be_buf * R
                moved = True
            if add_r > 0 and not added and moved and d * (best - entry) >= add_r * R:
                add_px = entry + d * (add_r * R + cost)        # filled on the opening side (ask for longs)
                added = True
            if trail > 0 and moved:
                ts = best - d * trail * e_atr[q]
                if (d == 1 and ts > stop) or (d == -1 and ts < stop):
                    stop = ts
            k += 1
        if not done:
            k = len(o) - 1
            px = c[k] if d == 1 else c[k] + cost
        r = realized + size * d * (px - entry) / R
        if added:
            r += add_size * d * (px - add_px) / R
        out_in[nt] = j
        out_ex[nt] = k
        out_d[nt] = d
        out_r[nt] = r
        nt += 1
        busy_until = k
        day_count += 1
        if r < 0:
            day_lost = True
    return out_in[:nt], out_ex[:nt], out_d[:nt], out_r[:nt]


def backtest(m1: pd.DataFrame, m15: pd.DataFrame, p: P) -> pd.DataFrame:
    s = signals(m15, p)
    mi = m1.index
    e_i = mi.searchsorted(s.index + pd.Timedelta(minutes=p.bar_min))  # next signal-bar open, on M1
    ok = e_i < len(mi)
    s, e_i = s[ok], e_i[ok]
    o, h, l, c = (m1[x].to_numpy(np.float64) for x in ("open", "high", "low", "close"))
    mod = (mi.hour * 60 + mi.minute).to_numpy(np.int64)
    dayk = (mi.year * 10000 + mi.month * 100 + mi.day).to_numpy(np.int64)
    ti, tx, td, tr = _run(o, h, l, c, mod, dayk, e_i.astype(np.int64), s.dir.to_numpy(np.int64), s.sl.to_numpy(),
                          s.atr.to_numpy(), p.rr, p.be, p.be_buf, p.trail_atr, p.partial, p.partial_r,
                          p.exit_hour * 60 if p.exit_hour >= 0 else -1, int(p.max_hold_h * 60), p.max_per_day,
                          p.stop_after_loss, p.cost, p.add_r, p.add_size)
    return pd.DataFrame({"entry_time": mi[ti], "exit_time": mi[tx], "dir": td, "r": tr,
                         "stop": s.sl.to_numpy()[np.searchsorted(e_i, ti)] if len(ti) else []})


PERIODS = {"q4_24": ("2024-10-01", "2025-01-01"), "y25": ("2025-01-01", "2026-01-01"), "y26": ("2026-01-01", "2027-01-01")}


def stats(t: pd.DataFrame, risk=0.10) -> dict:
    out = {}
    for k, (a, b) in PERIODS.items():
        x = t[(t.entry_time >= a) & (t.entry_time < b)].r.to_numpy()
        out[f"{k}_n"] = len(x)
        if not len(x):
            continue
        loss = -x[x < 0].sum()
        eq = 1000 * np.cumprod(np.maximum(1 + risk * x, 0))
        out.update({f"{k}_win": (x > 0).mean(), f"{k}_avg": x.mean(), f"{k}_pf": x[x > 0].sum() / loss if loss > 0 else 99,
                    f"{k}_usd": eq[-1], f"{k}_dd": (eq / np.maximum.accumulate(eq) - 1).min()})
    return out
