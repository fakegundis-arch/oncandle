"""plateau score on Jan-Apr for stage C: for each combo meeting the Jan-Apr rules, the median Jan-Apr R and the
median log final of its neighbours (one grid step in any one dimension, same maxpos).  Pick = best plateau score.
usage: python plateau.py tag [tag...]"""
import sys

import numpy as np
import pandas as pd

from analyzeC import load, rules, SS, MK

DIMS = {"w": [1, 2, 3], "doi": [-0.007, -0.01, -0.015], "mv": [0.003, 0.004, 0.006],
        "off": [0.0, 1.0, 2.0, 3.0, 4.0, 6.0], "life": [0, 600, 1200, 2400], "sk": None, "tp": [-1, 1.0, 2.0, 3.0, 4.0],
        "hold": [3600, 7200, 14400], "be": [-1, 1.0]}


def score(tag, top=10):
    r = load(tag).join(MK, on="mi").join(SS, on="si")
    r["tp"] = r.tp.fillna(-1)
    r["be"] = r.be.fillna(-1)
    r["skey"] = r.stype + r.sk.astype(str)
    A, J = rules(r)
    keys = ["w", "doi", "mv", "off", "life", "skey", "tp", "hold", "be", "mp"]
    r["lfA"] = np.log(r.fA.clip(lower=1))
    idx = r.set_index(keys)
    lf = idx.lfA
    ra = idx.RA
    cand = r[A].sort_values("fA", ascending=False).head(3000)
    svals = {"v": ["v8.0", "v12.0", "v16.0", "v24.0"], "m": ["m0.5", "m0.75", "m1.0"]}
    out = []
    for _, row in cand.iterrows():
        base = tuple(row[k] for k in keys)
        nb = [base]
        for i, k in enumerate(keys):
            if k == "mp":
                continue
            if k == "skey":
                vals = svals[row.stype]
            elif k in ("off", "life"):
                if row.kind == 0:
                    continue
                vals = [v for v in DIMS[k] if v != 0]
            else:
                vals = DIMS[k]
            j = vals.index(row[k])
            for jj in (j - 1, j + 1):
                if 0 <= jj < len(vals):
                    b = list(base)
                    b[i] = vals[jj]
                    nb.append(tuple(b))
        vals_lf = [lf.get(b, np.nan) for b in nb]
        vals_ra = [ra.get(b, np.nan) for b in nb]
        out.append(dict(**{k: row[k] for k in keys}, nA=row.nA, RA=row.RA, fA=row.fA, n=row.n, R=row.R,
                        final=row.final, dd=row.dd, RmayJun=row.R - row.RA, J_ok=bool(J.loc[_]),
                        nb=len(nb), nb_medRA=np.nanmedian(vals_ra), nb_minRA=np.nanmin(vals_ra),
                        nb_medF=float(np.exp(np.nanmedian(vals_lf)))))
    o = pd.DataFrame(out).sort_values("nb_medF", ascending=False)
    return o


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    for tag in sys.argv[1:]:
        o = score(tag)
        o.to_parquet(f"plateau_{tag}.parquet")
        print(tag)
        print(o.head(15).round(2).to_string())
