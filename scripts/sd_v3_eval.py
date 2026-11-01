"""Supply & demand v3: build on Jan-Apr 2026 only, test once on May-Oct 2026 (protocol fixed before any v3 search).

PROTOCOL
  * Gold M1 bid bars (data/XAUUSD_M1.csv); longs fill at bid + cost, shorts at bid; cost $0.25 (Exness measured), stress
    $0.40. One position at a time. $1,000 start, 10% of equity risked per trade, compounding (the user's choice).
  * BUILD (explorers and auditors): only train_data() - M1 bars from 2025-10-01 (indicator warm-up / zone history only)
    up to 2026-04-30 23:59. Results are judged only on entries in Jan-Apr 2026. Nothing from May 2026 on is loaded,
    computed or printed, and no result for entries before 2026 is computed or printed.
  * A candidate passes when, in Jan-Apr 2026 at $0.25: >= 30 trades; profit factor >= 1.3; Jan-Feb and Mar-Apr each with
    total R > 0 and profit factor >= 1.1; profit factor >= 1.15 without its single best trade and at $0.40; max drawdown
    at 10% risk better than -35% (no terrible drawdowns); and >= 60% of its one-step neighbours (in the explorer's own
    grid) have profit factor >= 1.15 with >= 20 trades.
  * Score = median over the candidate and its one-step neighbours of growth at 10% risk, log(final / start). Each
    explorer reports its highest-scoring passing candidate; an independent auditor checks it on the same Jan-Apr data.
  * v3 = the confirmed candidate with the highest score, committed before any May-Oct result exists. Then a tester runs
    every candidate on May-Oct 2026 once (only v3's result is a clean test; picking another afterwards is hindsight).
  * Success on May-Oct (stated in advance): total R > 0, profit factor >= 1.2 and max drawdown at 10% risk better than -40%.
Trades: DataFrame with entry_time, exit_time (UTC minute stamps), dir (+1 / -1), r (result in R after costs).
Deliverable of an explorer: make_trades(cfg, cost, m1) -> trades, built only from the M1 frame it is given (bid OHLC +
spread columns), so the tester can pass the full data later.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TRAIN = ("2026-01-01", "2026-05-01")
TRAIN_HALVES = {"jan-feb": ("2026-01-01", "2026-03-01"), "mar-apr": ("2026-03-01", "2026-05-01")}
TEST = ("2026-05-01", "2026-10-16")
WARMUP = "2025-10-01"
RISK = 0.10
_CACHE: dict = {}


def train_data() -> pd.DataFrame:
    """M1 bid bars from 2025-10-01 to 2026-04-30 23:59 - the only data explorers and auditors may use."""
    if "train" not in _CACHE:
        from backtester import gold as G
        m1 = G.data(ROOT)[0]
        _CACHE["train"] = m1[(m1.index >= WARMUP) & (m1.index < TRAIN[1])].copy()
    return _CACHE["train"]


def resample(m1: pd.DataFrame, minutes: int) -> pd.DataFrame:
    return m1.resample(f"{minutes}min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


def _pf(r: np.ndarray) -> float:
    gl = -r[r < 0].sum(); gw = r[r > 0].sum()
    return float(gw / gl) if gl > 0 else (99.0 if gw > 0 else 0.0)


def metrics(trades: pd.DataFrame, a: str, b: str, risk: float = RISK) -> dict:
    """Scorecard of trades entered in [a, b) at `risk` per trade, $1,000 start."""
    t = trades[(trades.entry_time >= a) & (trades.entry_time < b)].sort_values("entry_time")
    if len(t) > 1 and (t.entry_time.to_numpy()[1:] <= t.exit_time.to_numpy()[:-1]).any():
        raise ValueError("overlapping trades: one position at a time")
    r = t.r.to_numpy(float)
    eq = np.cumprod(1 + risk * r) if len(r) else np.array([1.0])
    cum = np.cumsum(r) if len(r) else np.array([0.0])
    rest = np.delete(r, r.argmax()) if len(r) else r
    streak = cur = 0
    for x in r:
        cur = cur + 1 if x < 0 else 0; streak = max(streak, cur)
    mon = t.assign(m=t.exit_time.dt.to_period("M"), g=np.log1p(risk * r)).groupby("m").g.sum()
    return dict(n=len(r), R=float(r.sum()), pf=_pf(r), win=float((r > 0).mean()) if len(r) else 0.0,
                dd_R=float((cum - np.maximum.accumulate(np.maximum(cum, 0))).min()), best=float(r.max()) if len(r) else 0.0,
                pf_wo_best=_pf(rest), log_growth=float(np.log(eq[-1])), usd=float(1000 * eq[-1]),
                dd=float((eq / np.maximum.accumulate(np.maximum(eq, 1.0)) - 1).min()), max_losing_streak=streak,
                months={str(k): round(float(np.expm1(v)), 4) for k, v in mon.items()})


def evaluate(trades: pd.DataFrame) -> dict:
    """Training scorecard: Jan-Apr 2026 plus its two halves. Refuses trades entered after April 2026."""
    if len(trades) and (trades.entry_time >= TRAIN[1]).any():
        raise ValueError("trades after April 2026 must not exist during the build")
    out = metrics(trades, *TRAIN)
    for k, (a, b) in TRAIN_HALVES.items():
        m = metrics(trades, a, b)
        out.update({f"{k}_n": m["n"], f"{k}_R": m["R"], f"{k}_pf": m["pf"]})
    return out


def passes(m25: dict, m40: dict) -> dict:
    chk = {"trades>=30": m25["n"] >= 30, "pf>=1.3": m25["pf"] >= 1.3,
           "jan-feb R>0 pf>=1.1": m25["jan-feb_R"] > 0 and m25["jan-feb_pf"] >= 1.1,
           "mar-apr R>0 pf>=1.1": m25["mar-apr_R"] > 0 and m25["mar-apr_pf"] >= 1.1,
           "pf without best>=1.15": m25["pf_wo_best"] >= 1.15, "pf at $0.40>=1.15": m40["pf"] >= 1.15,
           "drawdown at 10% better than -35%": m25["dd"] > -0.35}
    chk["all"] = all(chk.values())
    return chk


def neighbour_ok(m25: dict) -> bool:
    return m25["pf"] >= 1.15 and m25["n"] >= 20
