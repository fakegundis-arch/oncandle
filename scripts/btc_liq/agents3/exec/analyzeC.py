import itertools
import sys

import numpy as np
import pandas as pd

import search3 as S3

ST = S3.settings()
SS = pd.DataFrame([(e[0], e[1], e[2], s[0], s[1], tp, h, bt[0], bt[1]) for e, s, tp, h, bt in ST],
                  columns=["kind", "off", "life", "stype", "sk", "tp", "hold", "be", "tr"])
MK = pd.DataFrame(list(itertools.product(S3.WS, S3.DOIS, S3.MVS)), columns=["w", "doi", "mv"])


def load(tag):
    return pd.read_parquet(f"resC_{tag}.parquet")


def rules(r):
    ruleA = (r.nA >= 27) & (r.pfA >= 1.3) & (r.ddA > -0.35) & (r.RA1 > 0) & (r.RA2 > 0)
    ruleJ = (r.n >= 40) & (r.pf >= 1.3) & (r.dd > -0.35) & (r.R1 > 0) & (r.R2 > 0)
    return ruleA, ruleJ


def summary(tag):
    r = load(tag)
    ruleA, ruleJ = rules(r)
    o = dict(tag=tag, nA_ok=int(ruleA.sum()), nJ_ok=int(ruleJ.sum()), medR=float(r.R.median()),
             posR=float((r.R > 0).mean()), p99R=float(r.R.quantile(0.99)))
    if ruleA.any():
        b = r[ruleA].sort_values("fA", ascending=False).iloc[0]
        o.update(A_fA=b.fA, A_RA=b.RA, A_RmayJun=b.R - b.RA, A_R=b.R, A_final=b.final)
        top = r[ruleA].sort_values("fA", ascending=False).head(50)
        o.update(A_top50_RmayJun_med=float((top.R - top.RA).median()))
    if ruleJ.any():
        b = r[ruleJ].sort_values("final", ascending=False).iloc[0]
        o.update(J_final=b.final, J_R=b.R, J_n=b.n)
        b = r[ruleJ].sort_values("R", ascending=False).iloc[0]
        o.update(J_byR_R=b.R, J_byR_final=b.final)
    return o


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    rows = [summary(t) for t in sys.argv[1:]]
    print(pd.DataFrame(rows).set_index("tag").round(2).T.to_string())
