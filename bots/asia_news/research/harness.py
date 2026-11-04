"""Evaluate a newsbot config on Jan-Jun 2026 with the protocol's pass rules."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, "/home/user/oncandle/scripts")
import asia_news_lab as L  # noqa: E402
from newsbot.backtest import make_trades  # noqa: E402

_P: dict = {}
CAL = L.calendar_train()


def px(sym):
    if sym not in _P:
        _P[sym] = L.prices_train(sym)
    return _P[sym]


def trades(cfg, mult=1.0, late=0, detail=False):  # noqa: D103
    sym = cfg["symbol"]
    delay = None if not late else cfg.get("entry_delay", 1) + late
    t = make_trades(cfg, CAL, px(sym), mult * L.COST[sym], entry_delay=delay, detail=detail)
    if len(t):
        t = t[(t.entry_time >= L.TRAIN[0]) & (t.entry_time < L.TRAIN[1])]
    return t


def evaluate(cfg, verbose=False):
    t1, t2, t3 = trades(cfg), trades(cfg, 2.0), trades(cfg, 1.0, late=2)
    m, m2, m3 = L.evaluate_train(t1), L.evaluate_train(t2), L.evaluate_train(t3)
    ok = L.passes_train(m, m2, m3)
    out = dict(n=m["n"], R=round(m["R"], 2), pf=round(m["pf"], 2), win=round(m["win"], 2), dd=round(m["dd"], 3),
               usd=round(m["usd"]), q1R=round(m["jan-mar_R"], 2), q2R=round(m["apr-jun_R"], 2),
               pf2x=round(m2["pf"], 2), pfLate=round(m3["pf"], 2), passed=ok["all"])
    if verbose:
        out["checks"] = ok
    return out, t1


def loo(t: pd.DataFrame) -> dict:
    """Robustness: profit factor / R after removing the best 1 and best 2 trades."""
    r = t.r.sort_values(ascending=False).to_numpy()
    res = {}
    for k in (1, 2):
        rr = r[k:]
        gl = -rr[rr < 0].sum(); gw = rr[rr > 0].sum()
        res[f"pf-top{k}"] = round(gw / gl, 2) if gl > 0 else 99.0
        res[f"R-top{k}"] = round(rr.sum(), 2)
    return res


PAIRS = {"AUD": "AUDUSD", "NZD": "NZDUSD", "JPY": "USDJPY"}


def pair_cfgs(cfg):
    """The pair version = one config per pair, each trading only its own currency."""
    return {sym: {**cfg, "instrument": "pair", "symbol": sym, "currencies": [ccy]} for ccy, sym in PAIRS.items()}


def metrics_any(t, a, b, risk=L.RISK):
    """asia_news_lab.metrics without the overlap check (trades on different pairs may overlap in time)."""
    t = t[(t.entry_time >= a) & (t.entry_time < b)].sort_values("entry_time")
    r = t.r.to_numpy(float)
    import numpy as np
    eq = np.cumprod(1 + risk * r) if len(r) else np.array([1.0])
    gl = -r[r < 0].sum(); gw = r[r > 0].sum()
    pf = float(gw / gl) if gl > 0 else (99.0 if gw > 0 else 0.0)
    return dict(n=len(r), R=float(r.sum()), pf=pf, win=float((r > 0).mean()) if len(r) else 0.0,
                usd=float(1000 * eq[-1]), dd=float((eq / np.maximum.accumulate(np.maximum(eq, 1.0)) - 1).min()))


def evaluate_pair(cfg):
    """Pass rules applied to the combined pair version (AUDUSD + NZDUSD + USDJPY trades in time order)."""
    cs = pair_cfgs(cfg)
    T = [pd.concat([trades(c, *a) for c in cs.values()]) for a in ((1.0, 0), (2.0, 0), (1.0, 2))]
    m = metrics_any(T[0], *L.TRAIN)
    q1, q2 = metrics_any(T[0], *L.TRAIN_Q["jan-mar"]), metrics_any(T[0], *L.TRAIN_Q["apr-jun"])
    m2, m3 = metrics_any(T[1], *L.TRAIN), metrics_any(T[2], *L.TRAIN)
    mm = {**m, "jan-mar_R": q1["R"], "apr-jun_R": q2["R"]}
    ok = L.passes_train(mm, m2, m3)
    out = dict(n=m["n"], R=round(m["R"], 2), pf=round(m["pf"], 2), win=round(m["win"], 2), dd=round(m["dd"], 3),
               usd=round(m["usd"]), q1R=round(q1["R"], 2), q2R=round(q2["R"], 2), pf2x=round(m2["pf"], 2),
               pfLate=round(m3["pf"], 2), passed=ok["all"])
    return out, T[0]
