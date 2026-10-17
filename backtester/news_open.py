"""News-bias at the New York open.

1. READ THE NEWS.  For each trading day, take every USD medium- and
   high-impact release from the previous NY close (16:00 ET) up to the NY
   open (09:30 ET).  Forex Factory's own verdict (`better_worse`: 1 = better
   than forecast for USD, 2 = worse) gives each release a sign; high impact
   counts double.  Sum -> USD score; |score| >= `min_score` sets the day's
   USD bias (+1 bullish USD / -1 bearish USD), otherwise no trade.
2. MAP TO MARKETS.  Expected direction of each market when USD is bullish:
   gold/silver/EURUSD/GBPUSD/BTC/indices/oil go DOWN (-1), USDJPY/USDCAD UP (+1).
3. WAIT AND OBSERVE.  No trade at the release.  At the NY open watch the
   first `observe_min` minutes; a market qualifies only if it has moved in
   the expected direction by at least `min_move` x its opening unit
   (median 15-minute opening range of the previous 20 days).
4. ENTER.  "momentum": at the next bar's open; "pullback": wait (up to 90
   min) for an M1 pullback to EMA20 that resumes in the bias direction;
   "breakout": wait (up to 120 min) for a close beyond the observation
   range in the bias direction.
   Stop beyond the observation window's opposite extreme (at least 0.3
   units) or `stop_units` x unit; target `rr` x stop, or hold to 16:00 ET.
5. PICK.  "best": only the qualifying market with the strongest move;
   "all": every qualifying market (risk split between them).

`mode="ignore_news"` and `mode="against_news"` give the control tests.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import indicators as ind
from .straddle import ny_open_utc

USD_BULL_DIRECTION = {"XAUUSD": -1, "XAGUSD": -1, "EURUSD": -1, "GBPUSD": -1, "USDJPY": 1, "USDCAD": 1,
                      "BTCUSD": -1, "NAS100": -1, "US30": -1, "US500": -1, "USOIL": -1}


@dataclass
class Params:
    min_score: int = 2
    observe_min: int = 15
    min_move: float = 0.25
    entry: str = "momentum"        # "momentum" | "pullback" | "breakout"
    stop: str = "window"           # "window" | "half_window" | "units"
    stop_units: float = 0.5
    rr: float = 2.0                # 0 = no target, hold to 16:00 ET
    be: float = 0.0
    pick: str = "best"             # or "all"
    mode: str = "news"             # "news" | "ignore_news" | "against_news"


def day_scores(cal: pd.DataFrame, days) -> pd.DataFrame:
    u = cal[(cal.currency == "USD") & cal.impact.isin(["high", "medium"]) & cal.better_worse.isin([1, 2])]
    s = np.where(u.better_worse == 1, 1, -1) * np.where(u.impact == "high", 2, 1)
    u = u.assign(s=s)
    rows = []
    for d in days:
        t0 = ny_open_utc(d)
        prev = (pd.Timestamp(d) - pd.offsets.BDay()).date()
        pc = pd.Timestamp(f"{prev} 16:00", tz="America/New_York").tz_convert("UTC").tz_localize(None)
        w = u[(u.time_utc >= pc) & (u.time_utc < t0)]
        rows.append({"day": pd.Timestamp(d), "t0": t0, "score": int(w.s.sum()), "n_events": len(w),
                     "events": "; ".join(f"{n} ({'+' if v > 0 else '-'})" for n, v in zip(w.name, w.s))})
    return pd.DataFrame(rows).set_index("day")


def opening_unit(m1: pd.DataFrame, days, minutes=15, lookback=20) -> pd.Series:
    rng = {}
    for d in days:
        t0 = ny_open_utc(d)
        w = m1.loc[t0:t0 + pd.Timedelta(minutes=minutes - 1)]
        if len(w) >= minutes // 2:
            rng[pd.Timestamp(d)] = w.high.max() - w.low.min()
    return pd.Series(rng).sort_index().shift().rolling(lookback, min_periods=10).median()


def candidates(m1: pd.DataFrame, market: str, scores: pd.DataFrame, unit: pd.Series, p: Params) -> pd.DataFrame:
    """One row per day on which `market` qualifies: entry bar index, direction, stop distance, strength."""
    idx = m1.index
    o, h, l, c = (m1[x].to_numpy() for x in ("open", "high", "low", "close"))
    ema = ind.ema(m1.close, 20).to_numpy() if p.entry == "pullback" else None
    beta = USD_BULL_DIRECTION[market]
    out = []
    for day, row in scores.iterrows():
        u = unit.get(day, np.nan)
        if not np.isfinite(u) or u <= 0:
            continue
        bias = int(np.sign(row.score)) if abs(row.score) >= p.min_score else 0
        if p.mode != "ignore_news" and bias == 0:
            continue
        i0 = idx.searchsorted(row.t0)
        iN = idx.searchsorted(row.t0 + pd.Timedelta(minutes=p.observe_min))
        if i0 >= len(idx) or idx[i0] > row.t0 + pd.Timedelta("2min") or iN >= len(idx) or iN <= i0:
            continue
        move = c[iN - 1] - o[i0]
        seen = int(np.sign(move))
        if p.mode == "news":
            want = bias * beta
        elif p.mode == "against_news":
            want = -bias * beta
        else:
            want = seen
        if want == 0 or seen != want or abs(move) < p.min_move * u:
            continue
        wl, wh = l[i0:iN].min(), h[i0:iN].max()
        e = iN                                       # entry at this bar's open
        if p.entry == "breakout":
            # patient entry: wait for a close beyond the observation range in the bias direction
            e = None
            stop_t = row.t0 + pd.Timedelta(minutes=p.observe_min + 120)
            j = iN
            while j < len(idx) and idx[j] < stop_t:
                if (want == 1 and c[j] > wh) or (want == -1 and c[j] < wl):
                    e = j + 1
                    break
                j += 1
            if e is None or e >= len(idx):
                continue
        if p.entry == "pullback":
            e = None
            stop_t = row.t0 + pd.Timedelta(minutes=p.observe_min + 90)
            j = iN + 1
            while j < len(idx) and idx[j] < stop_t:
                touched = (l[j - 1] <= ema[j - 1]) if want == 1 else (h[j - 1] >= ema[j - 1])
                resumed = (c[j] > h[j - 1]) if want == 1 else (c[j] < l[j - 1])
                if touched and resumed:
                    e = j + 1
                    wl, wh = l[i0:j + 1].min(), h[i0:j + 1].max()
                    break
                j += 1
            if e is None or e >= len(idx):
                continue
        ref = o[e]
        if p.stop == "window":
            dist = (ref - wl) if want == 1 else (wh - ref)
            dist = max(dist, 0.3 * u)
        elif p.stop == "half_window":
            dist = max(abs(ref - (wl + wh) / 2), 0.3 * u)
        else:
            dist = p.stop_units * u
        out.append({"day": day, "market": market, "entry_i": e, "dir": want, "sl": dist,
                    "strength": abs(move) / u, "score": row.score, "events": row.events})
    return pd.DataFrame(out)


def session_end_flags(m1: pd.DataFrame) -> np.ndarray:
    loc = m1.index.tz_localize("UTC").tz_convert("America/New_York")
    mod = loc.hour * 60 + loc.minute
    return np.asarray(mod >= 16 * 60) | np.asarray(mod < 9 * 60 + 30)


@dataclass
class ParamsM1:
    """All-M1 version: short observation, M1 entries, stops sized from M1 ATR."""
    min_score: int = 2
    observe_min: int = 5           # minutes after 09:30 ET that must move with the news
    entry: str = "pullback"        # "momentum" | "pullback" | "breakout" | "candle"
    stop: str = "atr"              # "atr" | "swing"
    stop_atr: float = 2.0
    wait_min: int = 30             # how long to wait for a pullback / breakout entry
    mode: str = "news"


def candidates_m1(m1: pd.DataFrame, market: str, scores: pd.DataFrame, p: ParamsM1, atr=None, ema=None) -> pd.DataFrame:
    """M1 only.  The first `observe_min` M1 candles after the open must close in the news direction, then:
    momentum = next M1 open; pullback = M1 touch of EMA9 that resumes (close beyond the prior candle);
    breakout = M1 close beyond the observation range; candle = first M1 candle that closes in the
    news direction and beyond the prior candle's extreme.  Stop = `stop_atr` x M1 ATR(14), or the
    last 5 M1 candles' extreme (at least 1 ATR)."""
    idx = m1.index
    o, h, l, c = (m1[x].to_numpy() for x in ("open", "high", "low", "close"))
    atr = ind.atr(m1, 14).to_numpy() if atr is None else atr
    ema = ind.ema(m1.close, 9).to_numpy() if ema is None else ema
    beta = USD_BULL_DIRECTION[market]
    out = []
    for day, row in scores.iterrows():
        bias = int(np.sign(row.score)) if abs(row.score) >= p.min_score else 0
        if p.mode != "ignore_news" and bias == 0:
            continue
        i0 = idx.searchsorted(row.t0)
        iN = idx.searchsorted(row.t0 + pd.Timedelta(minutes=p.observe_min))
        if i0 >= len(idx) or idx[i0] > row.t0 + pd.Timedelta("2min") or iN >= len(idx) or iN <= i0:
            continue
        move = c[iN - 1] - o[i0]
        seen = int(np.sign(move))
        want = bias * beta if p.mode == "news" else -bias * beta if p.mode == "against_news" else seen
        if want == 0 or seen != want:
            continue
        a = atr[iN - 1]
        if not np.isfinite(a) or a <= 0:
            continue
        wl, wh = l[i0:iN].min(), h[i0:iN].max()
        e = iN if p.entry == "momentum" else None
        end_t = row.t0 + pd.Timedelta(minutes=p.observe_min + p.wait_min)
        j = iN
        while e is None and j < len(idx) and idx[j] < end_t:
            if p.entry == "breakout":
                ok = c[j] > wh if want == 1 else c[j] < wl
            elif p.entry == "pullback":
                ok = j > iN and ((l[j - 1] <= ema[j - 1] and c[j] > h[j - 1]) if want == 1
                                 else (h[j - 1] >= ema[j - 1] and c[j] < l[j - 1]))
            else:  # candle
                ok = (c[j] > o[j] and c[j] > h[j - 1]) if want == 1 else (c[j] < o[j] and c[j] < l[j - 1])
            if ok:
                e = j + 1
            j += 1
        if e is None or e >= len(idx):
            continue
        if p.stop == "swing":
            k = max(e - 5, 0)
            dist = (o[e] - l[k:e].min()) if want == 1 else (h[k:e].max() - o[e])
            dist = max(dist, a)
        else:
            dist = p.stop_atr * a
        out.append({"day": day, "market": market, "entry_i": e, "dir": want, "sl": dist,
                    "strength": abs(move) / a, "score": row.score, "events": row.events})
    return pd.DataFrame(out)
