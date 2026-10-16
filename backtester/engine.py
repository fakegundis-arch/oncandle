"""Bar-by-bar execution engine.

Rules (identical to the MT5 EAs in mt5/):
* Signals are evaluated on the CLOSE of bar i and executed at the OPEN of
  bar i+1 - no look-ahead.
* Every trade has a hard initial stop of `stop_mult * ATR` placed at entry.
  Position size = `risk` fraction of current equity / stop distance, so a
  full stop-out loses exactly `risk` (plus costs).  Results are therefore
  expressed in R-multiples and are independent of the account currency.
* Optional chandelier trailing stop: highest close since entry minus
  `trail_mult * ATR` (mirror for shorts); it only ever tightens.
* If a bar touches the stop it is filled at the stop, or at the open if the
  market gapped through it.  If a stop and a signal fall on the same bar the
  stop wins (pessimistic).
* `cost` (price units) is charged once per round trip: spread + commission
  (+ slippage allowance).  Swaps are not modelled.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

try:
    from numba import njit
except ImportError:  # pure-python fallback, ~50x slower
    def njit(*a, **k):
        return (lambda f: f) if not (a and callable(a[0])) else a[0]


@njit(cache=True)
def _run(o, h, l, c, atr, le, se, lx, sx, cost, stop_mult, trail_mult, risk):
    n = len(o)
    eq = 1.0
    equity = np.ones(n)
    max_tr = n // 2 + 1
    t_entry = np.zeros(max_tr, np.int64)
    t_exit = np.zeros(max_tr, np.int64)
    t_dir = np.zeros(max_tr, np.int64)
    t_r = np.zeros(max_tr)
    nt = 0

    pos = 0          # +1 long, -1 short
    entry = 0.0
    dist = 0.0
    stop = 0.0
    best = 0.0       # best close since entry (for trailing)
    ent_i = 0
    pending = 2      # desired position for next open: +1, -1, 0 (flat), 2 = keep
    if le[0] and not se[0]:
        pending = 1
    elif se[0] and not le[0]:
        pending = -1

    for i in range(1, n):
        # ---- 1. execute orders decided at close of i-1, at open of i
        if pending != 2 and pending != pos:
            if pos != 0:  # close existing at open
                r = (pos * (o[i] - entry) - cost) / dist
                eq *= 1.0 + risk * r
                t_entry[nt] = ent_i; t_exit[nt] = i; t_dir[nt] = pos; t_r[nt] = r; nt += 1
                pos = 0
            if pending != 0 and atr[i - 1] > 0:
                pos = pending
                entry = o[i]
                dist = stop_mult * atr[i - 1]
                stop = entry - pos * dist
                best = entry
                ent_i = i
        pending = 2

        # ---- 2. intrabar stop check
        if pos == 1 and l[i] <= stop:
            px = min(o[i], stop)
            r = (px - entry - cost) / dist
            eq *= 1.0 + risk * r
            t_entry[nt] = ent_i; t_exit[nt] = i; t_dir[nt] = 1; t_r[nt] = r; nt += 1
            pos = 0
        elif pos == -1 and h[i] >= stop:
            px = max(o[i], stop)
            r = (entry - px - cost) / dist
            eq *= 1.0 + risk * r
            t_entry[nt] = ent_i; t_exit[nt] = i; t_dir[nt] = -1; t_r[nt] = r; nt += 1
            pos = 0

        # ---- 3. trailing stop update at close
        if pos != 0 and trail_mult > 0 and atr[i] > 0:
            if pos == 1:
                best = max(best, c[i])
                stop = max(stop, best - trail_mult * atr[i])
            else:
                best = min(best, c[i])
                stop = min(stop, best + trail_mult * atr[i])

        # ---- 4. mark to market
        if pos != 0:
            equity[i] = eq * (1.0 + risk * (pos * (c[i] - entry) - cost) / dist)
        else:
            equity[i] = eq

        # ---- 5. signals at close -> orders for next open
        if pos == 1:
            if se[i]:
                pending = -1
            elif lx[i]:
                pending = 0
        elif pos == -1:
            if le[i]:
                pending = 1
            elif sx[i]:
                pending = 0
        else:
            if le[i] and not se[i]:
                pending = 1
            elif se[i] and not le[i]:
                pending = -1

    # close any open position at the last close
    if pos != 0:
        r = (pos * (c[n - 1] - entry) - cost) / dist
        eq *= 1.0 + risk * r
        t_entry[nt] = ent_i; t_exit[nt] = n - 1; t_dir[nt] = pos; t_r[nt] = r; nt += 1
        equity[n - 1] = eq

    return equity, t_entry[:nt], t_exit[:nt], t_dir[:nt], t_r[:nt]


@dataclass
class Result:
    equity: pd.Series
    trades: pd.DataFrame


def backtest(df: pd.DataFrame, signals: dict, atr: pd.Series, cost: float,
             stop_mult: float = 2.0, trail_mult: float = 0.0, risk: float = 0.01) -> Result:
    def b(k):
        return signals[k].fillna(False).to_numpy(dtype=np.bool_)

    a = atr.fillna(0).to_numpy(dtype=np.float64)
    eq, te, tx, td, tr = _run(df["open"].to_numpy(np.float64), df["high"].to_numpy(np.float64),
                              df["low"].to_numpy(np.float64), df["close"].to_numpy(np.float64), a,
                              b("le"), b("se"), b("lx"), b("sx"),
                              float(cost), float(stop_mult), float(trail_mult), float(risk))
    idx = df.index
    trades = pd.DataFrame({"entry_time": idx[te], "exit_time": idx[tx], "dir": td, "r": tr})
    return Result(pd.Series(eq, idx), trades)
