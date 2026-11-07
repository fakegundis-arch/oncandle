"""Trades of one search spec over ALL months (search + check), from the precomputed arrays."""
import sys
import numpy as np, pandas as pd
from lib import WORK
import search as S

_cache = {}


def get(tag=""):
    if tag not in _cache:
        F, base, outc, ext = S.load(tag)
        _cache[tag] = (F, base, outc, ext, S.filters(F))
    return _cache[tag]


def trades(inst, dl, rule, flt, s, q, h, tag="", stress=False):
    F, base, outc, ext, flts = get(tag)
    oc = outc[inst]
    di = list(oc["delays"]).index(dl)
    sfx = "_s" if stress else ""
    R, DT, ET = oc["R" + sfx], oc["DT" + sfx], oc["ET" + sfx]
    d = S.dir_rules(base, inst, dl, ext)[rule]
    m = flts[flt] & (d != 0) & (ET[:, di] >= 0)
    idx = np.flatnonzero(m)
    rows, last = [], -1
    for i in idx:
        dd = 0 if d[i] > 0 else 1
        et = ET[i, di]
        r = R[i, di, dd, s, q, h]
        if et < last or not np.isfinite(r):
            continue
        xt = et + DT[i, di, dd, s, q, h]
        last = xt
        rows.append((i, F.ts.iloc[i], et, xt, int(d[i]), float(r)))
    t = pd.DataFrame(rows, columns=["post", "post_ts", "entry_ts", "exit_ts", "dir", "r"])
    t["m"] = pd.to_datetime(t.entry_ts, unit="s").dt.strftime("%Y-%m")
    return t


def summary(t, label=""):
    srch = t.entry_ts < S.S1
    out = {}
    for nm, x in [("search", t[srch]), ("check", t[~srch]), ("2026H1", t[t.entry_ts >= pd.Timestamp("2026-01-01", tz="UTC").timestamp()])]:
        r = x.r.to_numpy()
        gw, gl = r[r > 0].sum(), -r[r < 0].sum()
        out[nm] = dict(n=len(r), R=round(r.sum(), 1), pf=round(gw / gl, 2) if gl > 0 else 99, final=round(1000 * np.prod(1 + 0.1 * r)))
    print(label, out)
    print("   per month R:", t.groupby("m").r.sum().round(1).to_dict())


if __name__ == "__main__":
    a = sys.argv[1:]
    t = trades(a[0], int(a[1]), a[2], a[3], int(a[4]), int(a[5]), int(a[6]))
    summary(t, " ".join(a))
