"""Trend Rider - M1 trend-joining strategy with a fixed R:R target and an
early move to break-even.

Rules (mirrored by mt5/Experts/TrendRider.mq5)
----------------------------------------------
Stay out of consolidation - a market only counts as trending when ALL hold:
    * EMA(50) above EMA(200) (below, for shorts)
    * close above EMA(50) and EMA(50) higher than it was `slope_bars` ago
    * ADX(14) > adx_min        (trend strength)
    * Choppiness(14) < chop_max (not a sideways range)

Join the trend on a pullback:
    * the previous bar dipped to / through EMA(20)  (pullback)
    * this bar closes back above EMA(20) AND above the previous bar's high
Enter at the next bar's open.

Bracket:
    * stop  = below the lowest low of the last `swing_bars` bars,
              never tighter than `min_stop_atr` x ATR; the setup is skipped
              if the swing stop is wider than `max_stop_atr` x ATR;
              optionally never tighter than `min_stop_price` (e.g. $10 on gold)
    * target = entry + rr x risk          (default 1:3)
    * once price reaches entry + be_trigger x risk (default 1R) the stop is
      moved to entry + be_buffer x risk  -> a "free" trade
One position per market at a time.

Fill model (pessimistic on M1 OHLC):
    * longs buy at open + spread/commission (`cost`), sell at the BID
    * if a bar touches both stop and target, the stop is assumed first
    * the break-even move only takes effect from the bar AFTER the one that
      reached the trigger (we cannot know the order of ticks inside a bar);
      the live EA moves it on the tick, which can only be better
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import indicators as ind
from .engine import njit


@dataclass
class Params:
    ema_fast: int = 20
    ema_mid: int = 50
    ema_slow: int = 200
    slope_bars: int = 10
    adx_period: int = 14
    adx_min: float = 25.0
    chop_period: int = 14
    chop_max: float = 50.0
    atr_period: int = 14
    swing_bars: int = 10
    min_stop_atr: float = 1.0
    max_stop_atr: float = 4.0
    min_stop_price: float = 0.0   # floor in price units, e.g. 10.0 = $10 on gold (0 = off)
    rr: float = 3.0
    be_trigger: float = 1.0     # in R; <= 0 disables break-even
    be_buffer: float = 0.1      # in R, how far past entry the stop goes
    session_utc: tuple | None = None  # e.g. (13, 20): only open trades 13:00-19:59 UTC
    extra: dict = field(default_factory=dict)


def choppiness(df: pd.DataFrame, n: int) -> pd.Series:
    tr_sum = ind.true_range(df).rolling(n).sum()
    rng = df["high"].rolling(n).max() - df["low"].rolling(n).min()
    return 100 * np.log10(tr_sum / rng) / np.log10(n)


def signals(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    c, h, l = df["close"], df["high"], df["low"]
    e_f, e_m, e_s = ind.ema(c, p.ema_fast), ind.ema(c, p.ema_mid), ind.ema(c, p.ema_slow)
    _, _, adx = ind.adx(df, p.adx_period)
    chop = choppiness(df, p.chop_period)
    a = ind.atr(df, p.atr_period)

    trending = (adx > p.adx_min) & (chop < p.chop_max)
    up = (e_m > e_s) & (c > e_m) & (e_m > e_m.shift(p.slope_bars))
    dn = (e_m < e_s) & (c < e_m) & (e_m < e_m.shift(p.slope_bars))

    trend = pd.Series(np.where(up & trending, 1, np.where(dn & trending, -1, 0)), df.index)
    pb_long = (l.shift() <= e_f.shift()) & (c > e_f) & (c > h.shift())
    pb_short = (h.shift() >= e_f.shift()) & (c < e_f) & (c < l.shift())
    long_setup = (trend == 1) & pb_long
    short_setup = (trend == -1) & pb_short

    # Stop distance measured from the signal close; the engine re-anchors it
    # to the actual fill price.
    floor = np.maximum(p.min_stop_atr * a, p.min_stop_price)
    cap = np.maximum(p.max_stop_atr * a, p.min_stop_price)   # a price floor is never "too wide"
    long_dist = (c - l.rolling(p.swing_bars).min()).clip(lower=floor)
    short_dist = (h.rolling(p.swing_bars).max() - c).clip(lower=floor)
    long_ok = long_dist <= cap
    short_ok = short_dist <= cap

    if p.session_utc is not None:
        hr = df.index.hour
        lo, hi = p.session_utc
        ok = (hr >= lo) & (hr < hi) if lo < hi else (hr >= lo) | (hr < hi)
        long_ok &= ok
        short_ok &= ok
    long_setup &= long_ok
    short_setup &= short_ok

    sig = np.where(long_setup, 1, np.where(short_setup, -1, 0))
    dist = np.where(sig == 1, long_dist, np.where(sig == -1, short_dist, 0.0))
    out = pd.DataFrame({"signal": sig, "dist": dist,
                        # building blocks reused by the multi-market strategy
                        "trend": trend, "pb_long": pb_long & long_ok, "pb_short": pb_short & short_ok,
                        "long_dist": long_dist, "short_dist": short_dist,
                        "long_ok": long_ok, "short_ok": short_ok}, index=df.index)
    warm = a.isna() | e_s.isna() | adx.isna() | chop.isna()
    out.loc[warm, ["signal", "dist", "trend"]] = 0
    out.loc[warm, ["pb_long", "pb_short", "long_ok", "short_ok"]] = False
    return out


@njit(cache=True)
def _run_bracket(o, h, l, c, sig, dist, costs, rr, be_trigger, be_buffer, risk):
    n = len(o)
    eq = 1.0
    equity = np.ones(n)
    t_entry = np.zeros(n, np.int64)
    t_exit = np.zeros(n, np.int64)
    t_dir = np.zeros(n, np.int64)
    t_r = np.zeros(n)
    t_kind = np.zeros(n, np.int64)   # 1 target, 2 stop, 3 break-even stop, 4 end of data
    nt = 0

    pos = 0
    entry = 0.0      # effective entry incl. cost (ask for longs, bid for shorts)
    R = 0.0
    stop = 0.0
    tp = 0.0
    be_done = False
    ent_i = 0

    for i in range(1, n):
        # ---- entry at open from the previous bar's signal
        cost = costs[i]
        if pos == 0 and sig[i - 1] != 0 and dist[i - 1] > 0:
            pos = sig[i - 1]
            R = dist[i - 1]
            if pos == 1:
                entry = o[i] + cost        # pay spread + commission on the way in
                stop = entry - R
                tp = entry + rr * R
            else:
                entry = o[i]
                stop = entry + R
                tp = entry - rr * R
            be_done = False
            ent_i = i

        if pos != 0:
            # Bars are BID; a short is closed at the ASK = bid + cost.
            bh = h[i] if pos == 1 else h[i] + cost
            bl = l[i] if pos == 1 else l[i] + cost
            bo = o[i] if pos == 1 else o[i] + cost
            px = 0.0
            kind = 0
            if pos == 1:
                if bl <= stop:
                    px = min(bo, stop); kind = 3 if be_done else 2
                elif bh >= tp:
                    px = max(bo, tp); kind = 1
            else:
                if bh >= stop:
                    px = max(bo, stop); kind = 3 if be_done else 2
                elif bl <= tp:
                    px = min(bo, tp); kind = 1
            if kind != 0:
                r = pos * (px - entry) / R
                eq *= 1.0 + risk * r
                t_entry[nt] = ent_i; t_exit[nt] = i; t_dir[nt] = pos; t_r[nt] = r; t_kind[nt] = kind
                nt += 1
                pos = 0
            elif be_trigger > 0 and not be_done:
                if (pos == 1 and bh >= entry + be_trigger * R) or (pos == -1 and bl <= entry - be_trigger * R):
                    stop = entry + pos * be_buffer * R
                    be_done = True

        if pos != 0:
            mark = c[i] if pos == 1 else c[i] + cost
            equity[i] = eq * (1.0 + risk * pos * (mark - entry) / R)
        else:
            equity[i] = eq

    if pos != 0:
        mark = c[n - 1] if pos == 1 else c[n - 1] + costs[n - 1]
        r = pos * (mark - entry) / R
        eq *= 1.0 + risk * r
        t_entry[nt] = ent_i; t_exit[nt] = n - 1; t_dir[nt] = pos; t_r[nt] = r; t_kind[nt] = 4
        nt += 1
        equity[n - 1] = eq

    return equity, t_entry[:nt], t_exit[:nt], t_dir[:nt], t_r[:nt], t_kind[:nt]


KINDS = {1: "target", 2: "stop", 3: "breakeven", 4: "open_at_end"}


@dataclass
class Result:
    equity: pd.Series
    trades: pd.DataFrame


def backtest(df: pd.DataFrame, p: Params, cost: float, risk: float = 0.005,
             sig: pd.DataFrame | None = None) -> Result:
    """`cost`: round-trip spread+commission in price units.  If df has a
    per-bar `spread` column (MT5 export) the larger of the two is used on
    every bar, so spread spikes (rollover, news) are paid for."""
    sig = signals(df, p) if sig is None else sig
    costs = np.full(len(df), float(cost))
    if "spread" in df.columns:
        costs = np.maximum(costs, df["spread"].fillna(0).to_numpy(np.float64))
    eq, te, tx, td, tr, tk = _run_bracket(
        df["open"].to_numpy(np.float64), df["high"].to_numpy(np.float64),
        df["low"].to_numpy(np.float64), df["close"].to_numpy(np.float64),
        sig["signal"].to_numpy(np.int64), sig["dist"].to_numpy(np.float64),
        costs, float(p.rr), float(p.be_trigger), float(p.be_buffer), float(risk))
    idx = df.index
    trades = pd.DataFrame({"entry_time": idx[te], "exit_time": idx[tx], "dir": td, "r": tr,
                           "exit": [KINDS[k] for k in tk]})
    return Result(pd.Series(eq, idx), trades)
