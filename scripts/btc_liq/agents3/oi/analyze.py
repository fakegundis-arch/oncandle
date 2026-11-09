"""Summaries of stage-1 results: real vs fake (day-shifted) searches."""
import sys

import numpy as np
import pandas as pd

from outcomes import EXITS, STOPS


def ex_str(j):
    k, tp, h, (be, tr) = EXITS[int(j)]
    return f"stop{STOPS[k]} tp{tp} hold{h} be{be} tr{tr}"


def rule4(df):
    return df[(df.n >= 40) & (df.pf >= 1.3) & (df.RQ1 > 0) & (df.RQ2 > 0) & (df.dd > -0.35)]


def ja_rule(df):
    return df[(df.nJA >= 27) & (df.pfJA >= 1.3) & (df.ddJA > -0.35)]


def summary(seed, tag="", show=8):
    df = pd.read_parquet(f"s1_{seed}{tag}.parquet")
    dd = pd.read_parquet(f"s1defs_{seed}{tag}.parquet")
    r4 = rule4(df)
    ja = ja_rule(df)
    out = dict(seed=seed, settings_stored=len(df), r4=len(r4),
               best_R_r4=r4.R.max() if len(r4) else np.nan, best_final_r4=r4.final.max() if len(r4) else np.nan,
               best_fJA=ja.fJA.max() if len(ja) else np.nan, best_RJA=ja.RJA.max() if len(ja) else np.nan)
    if show:
        for col in ("fJA", "final"):
            top = (ja if col == "fJA" else r4).sort_values(col, ascending=False).head(show)
            print(f"--- seed {seed} top by {col}")
            for _, r in top.iterrows():
                d = dd.iloc[int(r["def"])]
                print(f"{d.oi_f}<={d.oi_v} |{d.mv_f}|>={d.mv_v} fade={d.fade} {d.flt}{'>=' if d.side == 1 else '<='}"
                      f"{d.th:.4g} | {ex_str(r.exit)} | JA n{r.nJA:.0f} R{r.RJA:.1f} pf{r.pfJA:.2f} ${r.fJA:.0f} "
                      f"dd{r.ddJA:.2f} | MJ n{r.nMJ:.0f} R{r.RMJ:.1f} pf{r.pfMJ:.2f} ${r.fMJ:.0f} | ALL n{r.n:.0f} "
                      f"R{r.R:.1f} pf{r.pf:.2f} ${r.final:.0f} dd{r.dd:.2f}")
    return out


if __name__ == "__main__":
    tag = sys.argv[2] if len(sys.argv) > 2 else ""
    for s in [int(x) for x in sys.argv[1].split(",")]:
        print(summary(s, tag))
