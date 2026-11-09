import sys

import numpy as np
import pandas as pd

import search

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 40)
ST = search.settings()
SS = pd.DataFrame([(a, b[0], b[1], b[2], c, d, e, g[0], g[1]) for a, b, c, d, e, g in ST],
                  columns=["side", "kind", "off", "life", "stop", "hold", "tp", "be", "tr"])
import itertools
MK = pd.DataFrame(list(itertools.product(search.DOIS, search.MVS, search.NETS)), columns=["doi", "mv", "net"])


def load(tag):
    import os
    r = pd.read_parquet(f"res{os.environ.get("STAGE", "A")}_{tag}.parquet")
    return r


def describe(r, top=10):
    x = r.join(MK, on="mi").join(SS, on="si")
    return x


def summary(tag, show=True):
    r = load(tag)
    ruleA = (r.nA >= 27) & (r.pfA >= 1.3) & (r.ddA > -0.35) & (r.RA1 > 0) & (r.RA2 > 0)
    ruleJ = (r.n >= 40) & (r.pf >= 1.3) & (r.dd > -0.35) & (r.R1 > 0) & (r.R2 > 0)
    out = dict(tag=tag, combos=len(r), nA_ok=int(ruleA.sum()), nJ_ok=int(ruleJ.sum()))
    a = r[ruleA].sort_values("fA", ascending=False)
    j = r[ruleJ].sort_values("final", ascending=False)
    if len(a):
        b = a.iloc[0]
        out.update(bestA_fA=b.fA, bestA_RA=b.RA, bestA_R_JJ=b.R, bestA_final_JJ=b.final)
    if len(j):
        b = j.iloc[0]
        out.update(bestJ_final=b.final, bestJ_R=b.R, bestJ_n=b.n)
        jr = r[ruleJ].sort_values("R", ascending=False).iloc[0]
        out.update(bestJ_byR_R=jr.R, bestJ_byR_final=jr.final)
    if show:
        print(out)
        print("top Jan-Apr (rules A):")
        print(describe(a.head(15)).round(3).to_string())
        print("top Jan-Jun (rule 4 w/o stress):")
        print(describe(j.head(15)).round(3).to_string())
    return out, r, ruleA, ruleJ


if __name__ == "__main__":
    for tag in sys.argv[1:]:
        summary(tag)
