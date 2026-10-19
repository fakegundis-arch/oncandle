"""Gold Asian breakout v17: pick from results/gold/v17_search.npz using 2026 ONLY (Exness spread $0.25).

Rule (fixed before any v17 result existed):
  1. 2026 drawdown no worse than -35%.
  2. At least 8 of 10 months of 2026 profitable.
  3. At least half of the one-step neighbours have a 2026 drawdown no worse than -40% and >= 8/10 months up.
  4. Block bootstrap of the 2026 trades (2-week blocks, one-year horizon, 400 years): worst-decile drawdown better
     than -50%. Checked for the best 300 candidates of 1-3 by 2026 total.
  5. Highest 2026 total.
Target checked once on 2025 afterwards: drawdown better than -50%.
    python scripts/gold_v17.py            -> 2026 view + bootstrap
    python scripts/gold_v17.py --reveal   -> the pick on 2025 and Q4 2024
"""
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import gold_v17_search as SR  # noqa: E402
import gold_v17_sim as S  # noqa: E402

SHORTLIST = 300


def load():
    z = np.load(ROOT / "results/gold/v17_search.npz")
    shape = tuple(z["shape"])
    return {k: z[k].reshape(shape) for k in z.files if k != "shape"}, shape


def neighbour_share(p):
    hits = np.zeros(p.shape, np.float32); tot = np.zeros(p.shape, np.float32)
    for ax in range(p.ndim):
        lo = [slice(None)] * p.ndim; hi = [slice(None)] * p.ndim
        lo[ax] = slice(1, None); hi[ax] = slice(None, -1)
        hits[tuple(lo)] += p[tuple(hi)]; tot[tuple(lo)] += 1
        hits[tuple(hi)] += p[tuple(lo)]; tot[tuple(hi)] += 1
    return hits / np.maximum(tot, 1)


def dims():
    return [("e1", list(SR.E1)), ("e2", list(SR.E2)), ("e3", list(SR.E3))] + list(SR.RISK.items())


def describe(ix):
    return {k: v[i] for (k, v), i in zip(dims(), ix)}


def trades_of(d, m1, m15):
    parts = []
    for k, (E, key) in enumerate(((SR.E1, d["e1"]), (SR.E2, d["e2"]), (SR.E3, d["e3"]))):
        parts.append(SR.build(E[key], m1, m15).assign(eng=k))
    return pd.concat(parts, ignore_index=True)


def main(reveal=False):
    from backtester import gold as G
    r, shape = load()
    p = (r["y26_dd"] >= -0.35) & (r["y26_up"] >= 8)
    nb = neighbour_share((r["y26_dd"] >= -0.40) & (r["y26_up"] >= 8))
    c = p & (nb >= 0.5)
    print(f"{p.size:,} combinations | {int(p.sum()):,} pass rules 1-2 | {int(c.sum()):,} also rule 3")
    flat = np.flatnonzero(c.ravel())
    flat = flat[np.argsort(-r["y26_usd"].ravel()[flat])][:SHORTLIST]
    m1, m15 = G.data(ROOT)
    cache, rows = {}, []
    for j in flat:
        ix = np.unravel_index(j, shape); d = describe(ix)
        key = (d["e1"], d["e2"], d["e3"])
        if key not in cache:
            cache[key] = trades_of(d, m1, m15)
        w = [d["w1"], d["w2"], d["w3"]]; sm = [d["sm1"], d["sm2"], 1.0]
        p10, p50, p90, g = S.bootstrap_dd(cache[key], w, sm, d["cap"], d["dst"], "2026-01-01", "2026-10-15")
        rows.append(dict(ix=ix, y26=float(r["y26_usd"][ix]), dd26=float(r["y26_dd"][ix]), up=int(r["y26_up"][ix]),
                         nb=float(nb[ix]), boot_worst=p10, boot_med=p50, boot_growth=g, **d))
        if p10 > -0.50:
            break                                  # shortlist is sorted by 2026 total: the first that passes rule 4 wins
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 320); pd.set_option("display.max_columns", 40)
    print(df.drop(columns="ix").round(3).to_string())
    ok = df[df.boot_worst > -0.50]
    if not len(ok):
        print("no candidate passes rule 4")
        return r, None
    pick = ok.iloc[0]
    print("\nPICK:", {k: pick[k] for k, _ in dims()})
    if reveal:
        ix = pick["ix"]
        for k in ("y26", "y25", "q4"):
            print(f"  {k}: ${r[f'{k}_usd'][ix]:,.0f} DD {r[f'{k}_dd'][ix]:.0%} months up {int(r[f'{k}_up'][ix])} "
                  f"worst month {r[f'{k}_worst'][ix]:+.0%}")
    return r, pick


if __name__ == "__main__":
    main("--reveal" in sys.argv)
