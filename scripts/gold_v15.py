"""Gold Asian breakout v15: pick from results/gold/v15_search.parquet using 2026 ONLY (Dukascopy's recorded spread).

Rule (fixed before 2025 was looked at):
  1. 2026 drawdown no worse than -40%  (v13 at the same spread: -76%). With --cost 0.30 (second attempt, after the
     first rule had no candidates at $0.30): no worse than v13 at $0.30 (-45%).
  2. At least 8 of 10 months of 2026 profitable.
  3. 2026 total above v13's at the same spread ($41,851).
  4. At least half of the one-step neighbours (any one setting moved to the next value) also pass 1-3.
  5. Highest 2026 total.
    python scripts/gold_v15.py            -> 2026 view
    python scripts/gold_v15.py --reveal   -> the pick on 2025 and Q4 2024
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from gold_v15_search import GRID, OVER, RISK  # noqa: E402

V13_2026 = 41_851                         # v13 at Dukascopy's spread; with --cost 0.30: v13 at $0.30
SRC = ROOT / "results/gold/v15_search.parquet"
if "--cost" in sys.argv:
    c = float(sys.argv[sys.argv.index("--cost") + 1])
    SRC = ROOT / f"results/gold/v15_search_c{c:.2f}.parquet"
    V13_2026 = {0.30: 387_196}[round(c, 2)]
ALL = {**GRID, **OVER, **RISK}
KEYS = list(ALL)


def load():
    d = pd.read_parquet(SRC)
    # at $0.30 no setup passed the first rule (drawdown >= -40% AND above v13); second rule, still on 2026 only:
    # drawdown no worse than v13's at the same spread (-45%) and more profit than v13
    dd_cap = -0.45 if "--cost" in sys.argv else -0.40
    d["pass"] = (d.y26_dd >= dd_cap) & (d.y26_up >= 8) & (d.y26_usd > V13_2026)
    look = d.set_index(KEYS)["pass"].to_dict()
    vals = d[KEYS].to_numpy(object)
    share = np.zeros(len(d))
    for i in np.flatnonzero(d["pass"].to_numpy()):
        row = list(vals[i]); hits = tot = 0
        for j, k in enumerate(KEYS):
            opts = ALL[k]; p = opts.index(row[j])
            for q in (p - 1, p + 1):
                if 0 <= q < len(opts):
                    nb = row.copy(); nb[j] = opts[q]
                    tot += 1; hits += bool(look.get(tuple(nb), False))
        share[i] = hits / tot
    d["nb"] = share
    return d


def main(reveal=False):
    d = load()
    c = d[d["pass"] & (d.nb >= 0.5)].sort_values("y26_usd", ascending=False)
    print(len(d), "setups |", int(d["pass"].sum()), "pass rules 1-3 |", len(c), "also rule 4")
    pd.set_option("display.width", 320); pd.set_option("display.max_columns", 40)
    print(c[KEYS + ["y26_usd", "y26_dd", "y26_up", "y26_worst", "y26_n", "nb"]].head(15).round(3).to_string())
    if reveal and len(c):
        p = c.iloc[0]
        print("\nPICK", {k: p[k] for k in KEYS})
        for k in ("y26", "y25", "q4"):
            print(f"  {k}: ${p[f'{k}_usd']:,.0f} DD {p[f'{k}_dd']:.0%} months up {p[f'{k}_up']}/{p[f'{k}_m']} "
                  f"worst {p[f'{k}_worst']:+.0%} trades {p[f'{k}_n']}")
    return d, c


if __name__ == "__main__":
    main("--reveal" in sys.argv)
