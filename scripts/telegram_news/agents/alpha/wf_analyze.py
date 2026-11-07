"""Replay 'select on the past, trade the next two months' from a walk-forward search file, for real or fake data."""
import sys
import numpy as np, pandas as pd
from lib import WORK
from prep_outcomes import STOPS, TPS, TIMERS

FOLDS = ["train<2026-01 -> Jan-Feb", "train<2026-03 -> Mar-Apr", "train<2026-05 -> May-Jun"]


def load(name):
    z = np.load(f"{WORK}/{name}.npz", allow_pickle=True)
    return z["res"], z["meta"], list(z["fnames"]), list(z["rnames"]), int(z["ncomb"])


def stats(res, b):
    n, R, gw, gl, w, lg, dd, mp, mt, n2, R2, gw2, gl2 = [res[:, b, c] for c in range(13)]
    pf = np.where(gl > 0, gw / np.maximum(gl, 1e-9), 99.0)
    pf2 = np.where(gl2 > 0, gw2 / np.maximum(gl2, 1e-9), 99.0)
    return dict(n=n, R=R, pf=pf, lg=lg, dd=1 - np.exp(dd), fm=mp / np.maximum(mt, 1), mt=mt, R2=R2, pf2=pf2)


def diff(res, b0, b1):
    d = res[:, b1] - res[:, b0]
    n, R, gw, gl, lg = d[:, 0], d[:, 1], d[:, 2], d[:, 3], d[:, 5]
    n2, R2, gw2, gl2 = d[:, 9], d[:, 10], d[:, 11], d[:, 12]
    return dict(n=n, R=R, pf=np.where(gl > 0, gw / np.maximum(gl, 1e-9), 99.0), lg=lg, R2=R2,
                pf2=np.where(gl2 > 0, gw2 / np.maximum(gl2, 1e-9), 99.0))


def select(res, b, crit="robust"):
    s = stats(res, b)
    ok = (s["n"] >= 30) & (s["pf"] > 1.1) & (s["R2"] > 0)
    if crit == "robust":
        ok &= (s["fm"] >= 0.6) & (s["mt"] >= 4) & (s["pf2"] > 1.1) & (s["n"] >= 40)
    sc = np.where(ok, s["lg"], -np.inf)
    return np.argsort(-sc), ok


def describe(meta, fn, rn, i):
    ii, di, ri, fi, ex = meta[i]
    s, q, h = ex // (len(TPS) * len(TIMERS)), (ex // len(TIMERS)) % len(TPS), ex % len(TIMERS)
    return f"{['gold','nasdaq'][ii]} dl={[0,10,30][di]} {rn[ri]} | {fn[fi]} | stop {STOPS[s]}v tp {TPS[q]} hold {TIMERS[h]}"


def report(name, verbose=True, topk=(1, 10, 100)):
    res, meta, fn, rn, ncomb = load(name)
    out = {"name": name, "ncomb": ncomb}
    if verbose:
        print(f"===== {name}: {ncomb:,} combinations, {len(res):,} kept")
    for crit in ["robust", "loose"]:
        tot_lg = {k: 0.0 for k in topk}
        for f in range(3):
            order, ok = select(res, f, crit)
            te = diff(res, f, f + 1)
            line = []
            for k in topk:
                sel = order[:k]
                sel = sel[ok[sel]]
                if len(sel) == 0:
                    line.append(f"top{k}: none"); continue
                mlg = float(np.mean(te["lg"][sel])); tot_lg[k] += mlg
                line.append(f"top{k}: test $x{np.exp(mlg):.2f} R {np.mean(te['R'][sel]):+.1f} n {np.mean(te['n'][sel]):.0f} pfs {np.median(te['pf2'][sel]):.2f}")
            if verbose:
                tr = stats(res, f)
                b = order[0]
                print(f"  [{crit}] {FOLDS[f]}: eligible {ok.sum():,}; best train ${1000*np.exp(min(tr['lg'][b], 50)):,.0f} -> " + " | ".join(line))
                print(f"        best: {describe(meta, fn, rn, b)}")
        out[crit] = {k: float(np.exp(v)) for k, v in tot_lg.items()}
        if verbose:
            print(f"  [{crit}] chained 3 folds (Jan-Jun 2026) mean $ multiple: " + ", ".join(f"top{k}: x{np.exp(v):.2f}" for k, v in tot_lg.items()))
    # luck-check number: best search-period (< 2026-05-01) final $ at 10 %
    for crit in ["robust", "loose"]:
        order, ok = select(res, 2, crit)
        s = stats(res, 2)
        b = order[0]
        out[f"best_search_{crit}"] = float(1000 * np.exp(min(s["lg"][b], 50)))
        if verbose:
            print(f"  best search-period ({crit}) $1000 -> ${out[f'best_search_{crit}']:,.0f}: {describe(meta, fn, rn, b)}  n={s['n'][b]:.0f} R={s['R'][b]:.1f} pf={s['pf'][b]:.2f}")
    return out


if __name__ == "__main__":
    for nm in sys.argv[1:]:
        report(nm)
