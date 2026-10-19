"""Supply & demand v2: the common 2026-only scorecard every explorer uses (and the rules fixed before v2 started).

PROTOCOL (committed before any v2 search):
  * Gold M1 (backtester.gold.data), bid prices; longs fill at bid + cost, shorts at bid; cost $0.25 (Exness measured),
    stress $0.40. One position at a time. Risk 10% of equity per trade, compounding (the user's choice).
  * Selection uses 2026 only: entries in [2026-01-01, 2026-10-16). 2025 and Q4 2024 are not computed, printed or used by
    any explorer or auditor; older bars only warm up indicators / zone history.
  * A candidate passes when, in 2026 at $0.25: >= 60 trades; profit factor >= 1.3; Jan-May and Jun-Oct each with
    total R > 0 and profit factor >= 1.1; without its single best trade profit factor >= 1.15; and at $0.40 profit
    factor >= 1.15; and >= 60% of its one-step neighbours (in the explorer's own grid) have profit factor >= 1.15 with
    >= 40 trades.
  * Score = growth at 10% risk, log(final / start) = sum(log(1 + 0.1 R)), taken as the median over the candidate and its
    one-step neighbours (a plateau, so one lucky cell cannot win). Each explorer reports its highest-scoring passing
    candidate; an independent auditor must confirm it (re-implementation, look-ahead, fills, gaps).
  * v2 = the confirmed candidate with the highest score. Its 2025 is then computed once. Success on 2025 (stated in
    advance): total R > 0 and profit factor >= 1.1.
Trades: a DataFrame with entry_time, exit_time (UTC minute stamps), dir (+1 / -1), r (result in R after costs).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

Y26 = ("2026-01-01", "2026-10-16")
H1 = ("2026-01-01", "2026-06-01")
H2 = ("2026-06-01", "2026-10-16")
RISK = 0.10


def _clip(t: pd.DataFrame, a: str, b: str) -> pd.DataFrame:
    return t[(t.entry_time >= a) & (t.entry_time < b)].sort_values("entry_time")


def _pf(r: np.ndarray) -> float:
    gl = -r[r < 0].sum()
    gw = r[r > 0].sum()
    return float(gw / gl) if gl > 0 else (99.0 if gw > 0 else 0.0)


def evaluate(trades: pd.DataFrame, risk: float = RISK) -> dict:
    """2026 scorecard of a trade list (only entries from 2026-01-01 are looked at)."""
    t = _clip(trades, *Y26)
    if len(t) > 1 and (t.entry_time.to_numpy()[1:] <= t.exit_time.to_numpy()[:-1]).any():
        raise ValueError("overlapping trades: v2 allows one position at a time")
    r = t.r.to_numpy(float)
    out = dict(n=len(r), R=float(r.sum()), pf=_pf(r), win=float((r > 0).mean()) if len(r) else 0.0)
    cum = np.cumsum(r)
    out["dd_R"] = float((cum - np.maximum.accumulate(np.maximum(cum, 0))).min()) if len(r) else 0.0
    best = r.max() if len(r) else 0.0
    rest = np.delete(r, r.argmax()) if len(r) else r
    out.update(best=float(best), R_wo_best=float(rest.sum()), pf_wo_best=_pf(rest))
    for k, (a, b) in (("h1", H1), ("h2", H2)):
        rr = _clip(trades, a, b).r.to_numpy(float)
        out.update({f"{k}_n": len(rr), f"{k}_R": float(rr.sum()), f"{k}_pf": _pf(rr)})
    eq = np.cumprod(1 + risk * r) if len(r) else np.array([1.0])
    out["log_growth"] = float(np.log(eq[-1]))
    out["usd"] = float(1000 * eq[-1])
    out["dd"] = float((eq / np.maximum.accumulate(np.maximum(eq, 1.0)) - 1).min())
    mon = t.assign(m=t.exit_time.dt.to_period("M"), g=np.log1p(risk * r)).groupby("m").g.sum()
    out["months_up"] = int((mon > 0).sum())
    out["months"] = {str(k): round(float(np.expm1(v)), 4) for k, v in mon.items()}
    return out


def passes(m25: dict, m40: dict) -> dict:
    """Rule checks for one setting: m25 = evaluate() at $0.25, m40 = evaluate() at $0.40 (neighbour rule separate)."""
    chk = {"trades>=60": m25["n"] >= 60, "pf>=1.3": m25["pf"] >= 1.3,
           "jan-may R>0 pf>=1.1": m25["h1_R"] > 0 and m25["h1_pf"] >= 1.1,
           "jun-oct R>0 pf>=1.1": m25["h2_R"] > 0 and m25["h2_pf"] >= 1.1,
           "pf without best>=1.15": m25["pf_wo_best"] >= 1.15, "pf at $0.40>=1.15": m40["pf"] >= 1.15}
    chk["all"] = all(chk.values())
    return chk


def neighbour_ok(m25: dict) -> bool:
    """What a one-step neighbour needs for the plateau rule."""
    return m25["pf"] >= 1.15 and m25["n"] >= 40
