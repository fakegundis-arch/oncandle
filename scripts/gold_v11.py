"""Gold Asian breakout v11: pick from results/gold/v11_search.parquet using 2026 ONLY, then show the 2025 / Q4 2024 test.

Rule (fixed before the test years were looked at):
  1. 2026: at least 9 of 10 months profitable.
  2. 2026 drawdown no worse than -45%.
  3. 2026 total above v10's ($72,607).
  4. At least half of the one-step neighbours (one engine setting moved to the next value, same overlay and risk)
     also pass rules 1-3.
  5. Highest 2026 total.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from gold_v11_search import ENGINE  # noqa: E402

OVER = ["eq_n", "eq_thr", "week_cap", "risk", "short"]
V10_2026 = 72_607


def load():
    d = pd.read_parquet(ROOT / "results/gold/v11_search.parquet")
    for k in d.select_dtypes("float32"):
        if not k.startswith("m"):
            d[k] = d[k].astype(float).round(2)
    yr = lambda y: [c for c in d if c.startswith(f"m{y}")]
    for y, k in (("2026", "y26"), ("2025", "y25"), ("2024", "q4")):
        d[k] = 1000 * np.prod(1 + d[yr(y)].astype(float), axis=1)
        d[f"up_{k}"] = (d[yr(y)] > 0).sum(axis=1)
        d[f"worst_{k}"] = d[yr(y)].min(axis=1)
    d["pass26"] = (d.up_y26 >= 9) & (d.dd_y26 >= -0.45) & (d.y26 > V10_2026)
    return d


def neighbour_share(d, flag="pass26"):
    keys = list(ENGINE) + OVER
    look = d.set_index(keys)[flag].to_dict()
    share = np.zeros(len(d))
    vals = d[keys].to_numpy(object)
    f = d[flag].to_numpy()
    for i in np.flatnonzero(f):
        row = list(vals[i])
        hits = tot = 0
        for j, k in enumerate(ENGINE):
            opts = ENGINE[k]
            p = opts.index(row[j])
            for q in (p - 1, p + 1):
                if 0 <= q < len(opts):
                    nb = row.copy(); nb[j] = opts[q]
                    tot += 1; hits += bool(look.get(tuple(nb), False))
        share[i] = hits / tot
    return share


def main():
    d = load()
    d["nb_share"] = neighbour_share(d)
    d.to_parquet(ROOT / "results/gold/v11_selected.parquet", index=False)
    print(len(d), "combinations |", int(d.pass26.sum()), "pass rules 1-3 |", int((d.pass26 & (d.nb_share >= 0.5)).sum()),
          "also pass rule 4")
    cand = d[d.pass26 & (d.nb_share >= 0.5)].sort_values("y26", ascending=False)
    cols = list(ENGINE) + OVER + ["y26", "dd_y26", "up_y26", "worst_y26", "nb_share"]
    pd.set_option("display.width", 320); pd.set_option("display.max_columns", 40)
    print(cand[cols].head(12).round(2).to_string())
    return d, cand


if __name__ == "__main__":
    main()
