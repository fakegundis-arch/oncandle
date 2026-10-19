"""Gold Asian breakout v16: pick from results/gold/v16_search.npz using 2026 ONLY (Exness spread $0.25).

Rule (fixed before 2025 was looked at):
  1. 2026 total above v13's ($387,233), so above v5's too ($105,584).
  2. 2026 drawdown no worse than -40%.
  3. At least 8 of 10 months of 2026 profitable.
  4. At least half of the one-step neighbours (any one setting or risk moved to the next value) at least as good as
     v13 in 2026 (first written as "also pass 1-3", which no combination met).
  5. Highest 2026 total (ties: more robust neighbours).
Targets checked once on 2025 afterwards: drawdown better than -50%, total above v5 ($348,493) and v13 ($286,377).
    python scripts/gold_v16.py            -> 2026 view
    python scripts/gold_v16.py --reveal   -> the pick on 2025 and Q4 2024
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from gold_v16_search import RISK, VAR  # noqa: E402

V13_2026, V5_2025, V13_2025 = 387_233, 348_493, 286_377
DIMS = {**VAR, **RISK}


def load():
    z = np.load(ROOT / "results/gold/v16_search.npz")
    shape = tuple(z["shape"])
    return {k: z[k].reshape(shape) for k in z.files if k != "shape"}, shape


def neighbour_share(p):
    hits = np.zeros(p.shape, np.float32)
    tot = np.zeros(p.shape, np.float32)
    for ax in range(p.ndim):
        lo = [slice(None)] * p.ndim; hi = [slice(None)] * p.ndim
        lo[ax] = slice(1, None); hi[ax] = slice(None, -1)
        hits[tuple(lo)] += p[tuple(hi)]; tot[tuple(lo)] += 1      # neighbour one step down
        hits[tuple(hi)] += p[tuple(lo)]; tot[tuple(hi)] += 1      # neighbour one step up
    return hits / np.maximum(tot, 1)


def describe(ix):
    return {k: v[i] for (k, v), i in zip(DIMS.items(), ix)}


def main(reveal=False):
    r, shape = load()
    p = (r["y26_usd"] > V13_2026) & (r["y26_dd"] >= -0.40) & (r["y26_up"] >= 8)
    # rule 4 as first written (half the neighbours passing 1-3) had no candidates: the passers sit on the -40% edge, so
    # one risk step breaks the cap. Rule 4, second form (2026 only): half the neighbours at least as good as v13
    # (2026 above $387,233 with a drawdown no worse than v13's -45%, >= 8/10 months up).
    nb = neighbour_share((r["y26_usd"] > V13_2026) & (r["y26_dd"] >= -0.45) & (r["y26_up"] >= 8))
    c = p & (nb >= 0.5)
    print(f"{p.size:,} combinations | {int(p.sum()):,} pass rules 1-3 | {int(c.sum()):,} also rule 4")
    if not c.any():
        return r, None
    flat = np.flatnonzero(c.ravel())
    key = np.lexsort((-nb.ravel()[flat], -r["y26_usd"].ravel()[flat]))   # highest 2026, then most robust
    order = flat[key]
    for j in order[:12]:
        ix = np.unravel_index(j, shape)
        print(f"  2026 ${r['y26_usd'][ix]:,.0f} DD {r['y26_dd'][ix]:.0%} up {int(r['y26_up'][ix])}/10 nb {nb[ix]:.2f} | "
              + ", ".join(f"{k}={v}" for k, v in describe(ix).items()))
    pick = np.unravel_index(order[0], shape)
    if reveal:
        print("\nPICK:", describe(pick))
        for k in ("y26", "y25", "q4"):
            print(f"  {k}: ${r[f'{k}_usd'][pick]:,.0f} DD {r[f'{k}_dd'][pick]:.0%} months up {int(r[f'{k}_up'][pick])} "
                  f"worst month {r[f'{k}_worst'][pick]:+.0%}")
        ok25 = (r["y25_dd"] > -0.50) & (r["y25_usd"] > V5_2025)
        print(f"\n2025 targets (drawdown better than -50% and above ${V5_2025:,}):")
        print(f"  the pick: {'MET' if ok25[pick] else 'NOT met'}")
        print(f"  among the {int(c.sum()):,} robust 2026 candidates: {int((ok25 & c).sum()):,} meet them "
              f"({(ok25 & c).sum() / c.sum():.1%}); median 2025 ${np.median(r['y25_usd'][c]):,.0f}, "
              f"median 2025 drawdown {np.median(r['y25_dd'][c]):.0%}")
        print(f"  among all {p.size:,} combinations: {int(ok25.sum()):,} meet them ({ok25.mean():.2%})")
    return r, pick


if __name__ == "__main__":
    main("--reveal" in sys.argv)
