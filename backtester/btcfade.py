"""BTC Run Fade lab: signals on `tf` bars, every trade simulated minute by minute on M1 (engine: gold._run).

Baseline (RunFade.mq5 BTC preset): BTCUSD H1. After `run_len` candles of the same colour whose combined move
(close now - open `run_len`-1 bars ago) is >= `min_move` x ATR(14), trade against the run at the next bar's open.
Target `tp` x ATR, stop `sl` x ATR, close after `max_bars` bars. One trade at a time.

Extensions: confirmation candle, higher-timeframe trend filter, hour / weekday filters, volatility regime,
long/short only, break-even, trailing stop, max trades per day.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import indicators as ind
from .gold import _run

TF_MIN = {"30min": 30, "1h": 60, "2h": 120, "4h": 240}


@dataclass
class P:
    tf: str = "1h"
    run_len: int = 4
    min_move: float = 2.5
    max_move: float = 99.0        # skip runs larger than this x ATR (crashes / breakouts)
    tp: float = 0.5
    sl: float = 4.0
    max_bars: int = 30
    confirm: bool = False         # wait for the first opposite-colour candle, enter after it
    trend_ema: int = 0            # >0: only fade runs that go AGAINST the EMA(n) trend (pullbacks), -n: only WITH it
    side: int = 0
    hours: tuple = ()             # allowed UTC entry hours (empty = all)
    skip_weekend: bool = False
    vol_max: float = 99.0         # ATR / median(ATR, 200 bars)
    vol_min: float = 0.0
    be: float = 0.0
    be_buf: float = 0.0
    trail: float = 0.0            # x ATR, after break-even
    max_per_day: int = 99
    cost: float = 20.0


_C: dict = {}


def data(root):
    if "m1" not in _C:
        from . import data as D
        _C["m1"] = D.load_csv(root / "data" / "BTCUSD_M1.csv").drop(columns="spread", errors="ignore")
    return _C["m1"]


def bars(m1, tf):
    k = ("bars", tf)
    if k not in _C:
        _C[k] = m1.resample(tf).agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    return _C[k]


def signals(df: pd.DataFrame, p: P) -> pd.DataFrame:
    o, c = df.open.to_numpy(), df.close.to_numpy()
    col = np.sign(c - o)
    runl = np.zeros(len(col), np.int64)
    for i in range(len(col)):
        if col[i] == 0:
            continue
        runl[i] = runl[i - 1] + int(col[i]) if i and np.sign(runl[i - 1]) == col[i] else int(col[i])
    atr = ind.atr(df, 14).to_numpy()
    move = np.abs(c - np.roll(o, p.run_len - 1)) / atr
    move[: p.run_len] = 0
    ok = (move >= p.min_move) & (move <= p.max_move)
    d = np.where((runl == -p.run_len) & ok, 1, np.where((runl == p.run_len) & ok, -1, 0))
    if p.trend_ema:
        e = ind.ema(df.close, abs(p.trend_ema)).to_numpy()
        up = c > e
        if p.trend_ema > 0:      # fade only when the run went against the trend (long after a red run in an uptrend)
            d = np.where(((d == 1) & up) | ((d == -1) & ~up), d, 0)
        else:
            d = np.where(((d == 1) & ~up) | ((d == -1) & up), d, 0)
    if p.vol_max < 99 or p.vol_min > 0:
        a = pd.Series(atr)
        rel = (a / a.rolling(200).median()).to_numpy()
        d = np.where((rel <= p.vol_max) & (rel >= p.vol_min), d, 0)
    idx = df.index
    sig_i = np.flatnonzero(d != 0)
    if p.confirm:          # wait for the first candle of the opposite colour (within 3 bars), enter after it
        out = []
        for i in sig_i:
            for j in range(i + 1, min(i + 4, len(df))):
                if col[j] == d[i]:
                    out.append((j, d[i], atr[i]))
                    break
        sig = pd.DataFrame(out, columns=["i", "dir", "atr"])
    else:
        sig = pd.DataFrame({"i": sig_i, "dir": d[sig_i], "atr": atr[sig_i]})
    sig["t"] = idx[sig.i.to_numpy()] + pd.Timedelta(p.tf)          # entry at the next bar's open
    if p.hours:
        sig = sig[sig.t.dt.hour.isin(p.hours)]
    if p.skip_weekend:
        sig = sig[sig.t.dt.weekday < 5]
    if p.side:
        sig = sig[sig.dir == p.side]
    return sig[np.isfinite(sig.atr)]


def backtest(m1: pd.DataFrame, p: P) -> pd.DataFrame:
    s = signals(bars(m1, p.tf), p)
    mi = m1.index
    e_i = mi.searchsorted(s.t.to_numpy())
    ok = e_i < len(mi)
    s, e_i = s[ok], e_i[ok]
    o, h, l, c = (m1[x].to_numpy(np.float64) for x in ("open", "high", "low", "close"))
    mod = (mi.hour * 60 + mi.minute).to_numpy(np.int64)
    dayk = (mi.year * 10000 + mi.month * 100 + mi.day).to_numpy(np.int64)
    sl = p.sl * s.atr.to_numpy()
    ti, tx, td, tr = _run(o, h, l, c, mod, dayk, e_i.astype(np.int64), s.dir.to_numpy(np.int64), sl, s.atr.to_numpy(),
                          p.tp / p.sl, p.be, p.be_buf, p.trail, 0.0, 0.0, -1, p.max_bars * TF_MIN[p.tf], p.max_per_day,
                          False, p.cost)
    return pd.DataFrame({"entry_time": mi[ti], "exit_time": mi[tx], "dir": td, "r": tr})
