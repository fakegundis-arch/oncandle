"""Every built Gold Asian breakout version as a list of engines, so they can be re-run on any data / cost setting.

Each engine = (lab settings, overlay (eq_n, eq_thr, week_cap), risk long, risk short). Engines in one version trade
side by side with their own position (risk = % of equity at entry); see gold_v12.book.
"""
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import gold as G  # noqa: E402
from backtester.engine import njit  # noqa: E402
from gold_v3 import overlay  # noqa: E402
from gold_v9 import MODES  # noqa: E402

V5 = G.P(don=10, rr=4.0, stop_atr=1.5, be_buf=0.3, slope=16, max_per_day=2)
V10 = G.P(don=10, ema=400, slope=16, prev_day=True, stop_atr=1.5, rr=4.0, be=1.0, be_buf=0.3, d1_trend=20,
          regime_max=1.6, regime_warmup=20)
NY = replace(V10, ses_start=12, ses_end=15, don=15)
OV10 = (10, -2.0, -2.0)

VERSIONS = {
    "v5": [(V5, (0, 0.0, -2.0), 0.12, 0.06)],
    "v9": [(MODES["v5"][0], MODES["v5"][1], 0.03, 0.03), (replace(MODES["B"][0], regime_warmup=20), MODES["B"][1], 0.06, 0.06),
           (MODES["C"][0], MODES["C"][1], 0.03, 0.03)],
    "v10": [(V10, OV10, 0.08, 0.08)],
    "v11": [(V10, OV10, 0.10, 0.10), (NY, OV10, 0.05, 0.05)],
    "v12": [(V10, OV10, 0.12, 0.12), (NY, OV10, 0.04, 0.04)],
    "v13": [(V10, OV10, 0.14, 0.14), (NY, OV10, 0.04, 0.04)],
}


def trades(version, m1, m15, **cost):
    """All engines' trades of `version` with risk column f; `cost` overrides lab cost settings (cost, cost_mode...)."""
    out = []
    for k, (p, ov, fl, fs) in enumerate(VERSIONS[version] if isinstance(version, str) else version):
        t = overlay(G.backtest(m1, m15, replace(p, **cost)), *ov)
        out.append(t.assign(f=np.where(t.dir == 1, fl, fs), engine=k))
    return pd.concat(out).sort_values("entry_time")


@njit(cache=True)
def _book(t_in, t_out, r, f, mon_out, n_mon):
    n = len(t_in)
    order = np.argsort(np.concatenate((t_in * 2, t_out * 2 + 1)), kind="mergesort")
    eq = 1000.0; peak = 1000.0; dd = 0.0
    stake = np.zeros(n)
    mon_eq = np.full(n_mon, -1.0)
    for o in order:
        if o < n:
            stake[o] = f[o] * eq
        else:
            i = o - n
            eq = max(eq + stake[i] * r[i], 0.0)
            peak = max(peak, eq); dd = min(dd, eq / peak - 1.0)
            mon_eq[mon_out[i]] = eq
    return eq, dd, mon_eq


def book(t, a, b):
    """$1,000 at `a`, trades entered in [a, b): (final $, max drawdown, monthly returns Series, trades)."""
    x = t[(t.entry_time >= a) & (t.entry_time < b)]
    months = pd.period_range(a, pd.Timestamp(b) - pd.Timedelta("1D"), freq="M")
    if len(x) == 0:
        return 1000.0, 0.0, pd.Series(0.0, index=months), 0
    mo = months.get_indexer(x.exit_time.dt.to_period("M").clip(upper=months[-1]))
    eq, dd, me = _book(x.entry_time.to_numpy("datetime64[m]").astype(np.int64),
                       x.exit_time.to_numpy("datetime64[m]").astype(np.int64), x.r.to_numpy(np.float64),
                       x.f.to_numpy(np.float64), mo.astype(np.int64), len(months))
    prev, rets = 1000.0, []
    for v in me:
        v = prev if v < 0 else v
        rets.append(v / prev - 1 if prev > 0 else 0.0); prev = v
    return eq, dd, pd.Series(rets, index=months), len(x)

V14 = replace(V10, atr_pct_min=0.10, be=1.5, be_buf=0.5, rr=4.0)
VERSIONS["v14"] = [(V14, OV10, 0.04, 0.04)]
