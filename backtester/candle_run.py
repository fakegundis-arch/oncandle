"""Candle Run - BTC M1 momentum strategy (strategy 3).

Signal: `run_len` consecutive candles of the same colour (green = close > open,
red = close < open; a doji breaks the run) that together have moved at least
`min_move_atr` x ATR(14) from the first candle's open to the last close -
i.e. price is clearly moving, not drifting in tiny candles.  The trade is
taken once, on the bar where the run reaches `run_len`, in the run's
direction (or against it when fade=True, a diagnostic).

Bracket (same machinery as Trend Rider): stop beyond the start of the run,
at least `min_stop_atr` x ATR, setup skipped if wider than `max_stop_atr` x
ATR; target = rr x risk; stop moved to entry + be_buffer x risk once price
has gone be_trigger x risk in favour.  Optional trend filter: only trade in
the direction of EMA(trend_ema) when trend_ema > 0.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import indicators as ind


@dataclass
class Params:
    run_len: int = 4
    min_move_atr: float = 1.5
    atr_period: int = 14
    min_stop_atr: float = 1.0
    max_stop_atr: float = 4.0
    rr: float = 3.0
    be_trigger: float = 1.0
    be_buffer: float = 0.1
    trend_ema: int = 0
    fade: bool = False


def run_length(df: pd.DataFrame) -> np.ndarray:
    """Signed length of the current same-colour run ending at each bar
    (+n = n green candles in a row, -n = n red candles in a row, 0 = doji)."""
    colour = np.sign(df["close"].to_numpy() - df["open"].to_numpy()).astype(np.int64)
    out = np.zeros(len(colour), np.int64)
    for i in range(len(colour)):
        c = colour[i]
        if c == 0:
            continue
        out[i] = out[i - 1] + c if i and np.sign(out[i - 1]) == c else c
    return out


def signals(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    c, o, h, l = df["close"], df["open"], df["high"], df["low"]
    a = ind.atr(df, p.atr_period)
    run = pd.Series(run_length(df), df.index)
    n = p.run_len

    first_open = o.shift(n - 1)
    move = (c - first_open).abs()
    strong = move >= p.min_move_atr * a
    up = (run == n) & strong
    dn = (run == -n) & strong
    if p.trend_ema:
        e = ind.ema(c, p.trend_ema)
        up &= c > e
        dn &= c < e

    run_low = l.rolling(n).min()
    run_high = h.rolling(n).max()
    long_dist, short_dist = c - run_low, run_high - c
    if p.fade:  # go against the run; the stop sits beyond the run's extreme
        up, dn = dn, up
    long_dist = long_dist.clip(lower=p.min_stop_atr * a)
    short_dist = short_dist.clip(lower=p.min_stop_atr * a)
    up &= long_dist <= p.max_stop_atr * a
    dn &= short_dist <= p.max_stop_atr * a

    sig = np.where(up, 1, np.where(dn, -1, 0))
    dist = np.where(sig == 1, long_dist, np.where(sig == -1, short_dist, 0.0))
    out = pd.DataFrame({"signal": sig, "dist": np.nan_to_num(dist)}, index=df.index)
    out.loc[a.isna(), ["signal", "dist"]] = 0
    return out
