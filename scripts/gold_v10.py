"""Gold Asian breakout v10: pick from results/gold/v10_search.parquet using 2026 ONLY, then show the 2025 / Q4 2024 test.

Rule (fixed before the test years were looked at):
  1. Feb, Apr, Jun, Jul and Sep 2026 (v5's losing months) all profitable.
  2. 2026 total >= v5's 2026 total ($126,210).
  3. At least half of the one-step neighbours (one engine setting moved to the next value, same overlay and risk)
     also pass rule 1.
  4. Highest combined return over those five months.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from gold_v10_search import ENGINE  # noqa: E402

BAD = ["m2026-02", "m2026-04", "m2026-06", "m2026-07", "m2026-09"]
OVER = ["eq_n", "eq_thr", "week_cap", "risk", "short"]
V5_2026 = 126_210


def load():
    d = pd.read_parquet(ROOT / "results/gold/v10_search.parquet")
    for k in d.select_dtypes("float32"):
        if not k.startswith("m"):
            d[k] = d[k].astype(float).round(2)
    yr = lambda y: [c for c in d if c.startswith(f"m{y}")]
    for y, k in (("2026", "y26"), ("2025", "y25"), ("2024", "q4")):
        d[k] = 1000 * np.prod(1 + d[yr(y)].astype(float), axis=1)
        d[f"up{k}"] = (d[yr(y)] > 0).sum(axis=1)
    d["bad_ok"] = (d[BAD] > 0).all(axis=1)
    d["bad_prod"] = np.prod(1 + d[BAD].astype(float), axis=1)
    return d


def neighbour_share(d):
    keys = list(ENGINE) + OVER
    ok = d.set_index(keys)["bad_ok"]
    look = ok.to_dict()
    share = np.zeros(len(d))
    for i, row in enumerate(d[keys].itertuples(index=False)):
        if not d.bad_ok.iat[i]:
            continue
        row = list(row)
        hits = tot = 0
        for j, k in enumerate(ENGINE):
            vals = ENGINE[k]
            p = vals.index(row[j])
            for q in (p - 1, p + 1):
                if 0 <= q < len(vals):
                    nb = row.copy(); nb[j] = vals[q]
                    tot += 1; hits += bool(look.get(tuple(nb), False))
        share[i] = hits / tot
    return share


def main():
    d = load()
    cand = d[d.bad_ok & (d.y26 >= V5_2026)].copy()
    print(len(d), "combinations |", int(d.bad_ok.sum()), "with all five months up |", len(cand), "also >= v5 2026 total")
    cand["nb_share"] = pd.Series(neighbour_share(d), index=d.index).loc[cand.index]   # neighbours from the full table
    pick_set = cand[cand.nb_share >= 0.5].sort_values(["bad_prod", "y26"], ascending=False)
    cols = list(ENGINE) + OVER + BAD + ["nb_share", "y26", "upy26"]
    pd.set_option("display.width", 320); pd.set_option("display.max_columns", 40)
    print(pick_set[cols].head(10).round(2).to_string())
    return d, pick_set


if __name__ == "__main__":
    main()
