"""Gold Asian breakout v13, attempt 2: drawdown throttle on the v12 two-engine portfolio (same rules every month).
Risk per trade = base risk x `cut` while the account is more than `trig` below its peak, else base risk.
Chosen on 2026 only: >= 9/10 months up, drawdown >= -45%, above v12 ($414,516), half the neighbours passing,
then the highest 2026 total.   python scripts/gold_v13_risk.py [--reveal]   -> results/gold/v13_risk.csv"""
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import gold as G  # noqa: E402
from backtester.engine import njit  # noqa: E402
from gold_v12 import PER, stream  # noqa: E402
from gold_v11_check import ASIA, NY  # noqa: E402

GRID = dict(w_asia=[0.10, 0.12, 0.14, 0.16, 0.18], w_ny=[0.04, 0.05, 0.06], trig=[0.10, 0.15, 0.20, 0.30, 1.0],
            cut=[0.25, 0.5])
V12_2026 = 414_516


@njit(cache=True)
def _book(t_in, t_out, r, f, mon_out, n_mon, trig, cut):
    n = len(t_in)
    order = np.argsort(np.concatenate((t_in * 2, t_out * 2 + 1)), kind="mergesort")
    eq = 1000.0; peak = 1000.0; dd = 0.0
    stake = np.zeros(n)
    mon_eq = np.full(n_mon, -1.0)
    for o in order:
        i = o % n if o >= n else o
        if o < n:
            m = cut if eq / peak - 1.0 <= -trig else 1.0
            stake[i] = f[i] * m * eq
        else:
            eq = max(eq + stake[i] * r[i], 0.0)
            peak = max(peak, eq); dd = min(dd, eq / peak - 1.0)
            mon_eq[mon_out[i]] = eq
    return eq, dd, mon_eq


def book(x, trig, cut):
    out = {}
    for k, (a, b) in PER.items():
        y = x[(x.entry_time >= a) & (x.entry_time < b)]
        months = pd.period_range(a, pd.Timestamp(b) - pd.Timedelta("1D"), freq="M")
        mo = months.get_indexer(y.exit_time.dt.to_period("M").clip(upper=months[-1]))
        eq, dd, me = _book(y.entry_time.to_numpy("datetime64[m]").astype(np.int64),
                           y.exit_time.to_numpy("datetime64[m]").astype(np.int64), y.r.to_numpy(np.float64),
                           y.f.to_numpy(np.float64), mo.astype(np.int64), len(months), trig, cut)
        prev, rets = 1000.0, []
        for v in me:
            v = prev if v < 0 else v
            rets.append(v / prev - 1 if prev > 0 else 0.0); prev = v
        rets = np.array(rets)
        out[k] = (eq, dd, int((rets > 0).sum()), float(rets.min()))
    return out


def main(reveal=False):
    gold = G.data(ROOT)
    a, n = stream(*gold, ASIA), stream(*gold, NY)
    rows = []
    for v in itertools.product(*GRID.values()):
        kw = dict(zip(GRID, v))
        x = pd.concat([a.assign(f=kw["w_asia"]), n.assign(f=kw["w_ny"])])
        r = dict(kw)
        for k, (usd, dd, up, worst) in book(x, kw["trig"], kw["cut"]).items():
            r.update({f"{k}_usd": usd, f"{k}_dd": dd, f"{k}_up": up, f"{k}_worst": worst})
        rows.append(r)
    d = pd.DataFrame(rows)
    d["pass"] = (d.y26_up >= 9) & (d.y26_dd >= -0.45) & (d.y26_usd > V12_2026)
    look = d.set_index(list(GRID))["pass"].to_dict()
    share = []
    for _, r in d.iterrows():
        if not r["pass"]:
            share.append(0.0); continue
        hits = tot = 0
        for k, opts in GRID.items():
            p = opts.index(r[k])
            for q in (p - 1, p + 1):
                if 0 <= q < len(opts):
                    tot += 1; hits += bool(look.get(tuple(opts[q] if kk == k else r[kk] for kk in GRID), False))
        share.append(hits / tot)
    d["nb"] = share
    d.to_csv(ROOT / "results/gold/v13_risk.csv", index=False)
    c = d[d["pass"] & (d.nb >= 0.5)].sort_values("y26_usd", ascending=False)
    pd.set_option("display.width", 250)
    print(len(d), "setups |", int(d["pass"].sum()), "pass |", len(c), "with half the neighbours")
    print(c[list(GRID) + ["y26_usd", "y26_dd", "y26_up", "y26_worst", "nb"]].head(12).round(2).to_string())
    if reveal and len(c):
        p = c.iloc[0]
        print("\nPICK", {k: p[k] for k in GRID})
        for k in ("y26", "y25", "q4"):
            print(f"  {k}: ${p[f'{k}_usd']:,.0f} DD {p[f'{k}_dd']:.0%} months up {p[f'{k}_up']} worst {p[f'{k}_worst']:+.0%}")
    return d


if __name__ == "__main__":
    main("--reveal" in sys.argv)
