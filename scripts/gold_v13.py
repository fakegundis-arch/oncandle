"""Gold Asian breakout v13: pick from results/gold/v13_search.parquet using 2026 ONLY.

Rule (fixed before the test years were looked at):
  1. 2026: at least 9 of 10 months profitable.
  2. 2026 drawdown no worse than -45%.
  3. 2026 total above v12's ($414,516).
  4. At least half of the one-step neighbours (one setting moved to the next value, same risk split) also pass 1-3.
  5. Highest 2026 total.
    python scripts/gold_v13.py            -> 2026 view of the candidates
    python scripts/gold_v13.py --reveal   -> the pick's 2025 / Q4 2024 test
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from gold_v13_search import GRID  # noqa: E402

V12_2026 = 414_516
KEYS = list(GRID) + ["w_asia", "w_ny"]


def load():
    d = pd.read_parquet(ROOT / "results/gold/v13_search.parquet")
    d["pass26"] = (d.y26_up >= 9) & (d.y26_dd >= -0.45) & (d.y26_usd > V12_2026)
    look = d.set_index(KEYS)["pass26"].to_dict()
    share = np.zeros(len(d))
    vals = d[KEYS].to_numpy(object)
    for i in np.flatnonzero(d.pass26.to_numpy()):
        row = list(vals[i]); hits = tot = 0
        for j, k in enumerate(GRID):
            opts = GRID[k]; p = opts.index(row[j])
            for q in (p - 1, p + 1):
                if 0 <= q < len(opts):
                    nb = row.copy(); nb[j] = opts[q]
                    tot += 1; hits += bool(look.get(tuple(nb), False))
        share[i] = hits / tot
    d["nb"] = share
    return d


def main(reveal=False):
    d = load()
    cand = d[d.pass26 & (d.nb >= 0.5)].sort_values("y26_usd", ascending=False)
    print(len(d), "combinations |", int(d.pass26.sum()), "pass rules 1-3 |", len(cand), "also pass rule 4")
    pd.set_option("display.width", 320); pd.set_option("display.max_columns", 40)
    print(cand[KEYS + ["y26_usd", "y26_dd", "y26_up", "y26_worst", "n26", "nb"]].head(15).round(2).to_string())
    if reveal and len(cand):
        p = cand.iloc[0]
        print("\nPICK:", {k: p[k] for k in KEYS})
        for k in ("y26", "y25", "q4"):
            print(f"  {k}: ${p[f'{k}_usd']:,.0f} DD {p[f'{k}_dd']:.0%} months up {p[f'{k}_up']} worst {p[f'{k}_worst']:+.0%}")
    return d, cand


if __name__ == "__main__":
    main("--reveal" in sys.argv)
