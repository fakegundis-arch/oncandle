"""Evaluate given search rows (inst, dl, rule, flt, s, q, h) on another period [t0, t1)."""
import numpy as np, pandas as pd
import search as S


def eval_specs(specs, t0, t1, ctx):
    """specs: DataFrame with columns inst (0/1), dl (index), rule (name), flt (name), s, q, h.  ctx from load_ctx."""
    F, base, outc, ext, flts, mon, nmon = ctx
    ts = F.ts.to_numpy()
    per = (ts >= t0) & (ts < t1)
    res = []
    rule_cache = {}
    for (ii, dli, rn, fn), g in specs.groupby(["inst", "dl", "rule", "flt"], sort=False):
        inst = ["gold", "nasdaq"][ii]
        oc = outc[inst]
        dl = int(oc["delays"][dli])
        key = (inst, dl)
        if key not in rule_cache:
            rule_cache[key] = S.dir_rules(base, inst, dl, ext)
        d = rule_cache[key][rn]
        m = per & (oc["ET"][:, dli] >= 0) & (d != 0) & flts[fn]
        idx = np.flatnonzero(m)
        nex = oc["R"].shape[3] * oc["R"].shape[4] * oc["R"].shape[5]
        out = np.zeros((nex, 13), np.float32)
        if len(idx):
            S.eval_set(idx, (d[idx] < 0).astype(np.int64), dli, oc["R"], oc["DT"], oc["ET"], oc["R_s"], oc["DT_s"], oc["ET_s"], mon, nmon, out, 0)
        nq, nh = oc["R"].shape[4], oc["R"].shape[5]
        for ix, r in g.iterrows():
            row = out[int(r.s) * nq * nh + int(r.q) * nh + int(r.h)]
            res.append((ix, *row[3:]))
    o = pd.DataFrame(res, columns=["ix", "n", "R", "pf", "win", "lg", "dd", "mpos", "mtot", "Rs", "pfs"]).set_index("ix")
    return o.reindex(specs.index)


def load_ctx(tag=""):
    F, base, outc, ext = S.load(tag)
    ts = F.ts.to_numpy()
    mon = ((pd.to_datetime(ts, unit="s").year - 2025) * 12 + pd.to_datetime(ts, unit="s").month - 1).to_numpy().astype(np.int64)
    return F, base, outc, ext, S.filters(F), mon, int(mon.max()) + 1
