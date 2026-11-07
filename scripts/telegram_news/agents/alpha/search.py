"""Stage-1 grid search: text filters x direction rules x instrument x delay x stop x target x timer.
One position per instrument at a time (a signal is skipped while the previous trade on that instrument is open), so
the account at 10 % risk is exactly 1000 * prod(1 + 0.1 r).  Usage: python search.py [tag] [rand_dir_seed]"""
import os, sys, time, itertools
import numpy as np, pandas as pd
from numba import njit
from lib import WORK

TAG = sys.argv[1] if len(sys.argv) > 1 else ""
RSEED = int(sys.argv[2]) if len(sys.argv) > 2 else -1
NCOMB = [0]
S0 = pd.Timestamp("2025-01-01", tz="UTC").timestamp()
S1 = pd.Timestamp("2026-05-01", tz="UTC").timestamp()     # search period [S0, S1)


@njit(cache=True)
def eval_set(idx, dsel, dl, R, DT, ET, Rs, DTs, ETs, mon, nmon, out, row0):
    """idx: candidate posts (time order); dsel: 0 buy / 1 sell.  Writes one stats row per exit combo."""
    ns, nq, nh = R.shape[3], R.shape[4], R.shape[5]
    row = row0
    mr = np.zeros(nmon)
    for s in range(ns):
        for q in range(nq):
            for h in range(nh):
                last = -1
                n = 0; sr = 0.0; gw = 0.0; gl = 0.0; w = 0; lg = 0.0; bal = 0.0; peak = 0.0; dd = 0.0
                mr[:] = 0.0
                for k in range(idx.shape[0]):
                    i = idx[k]
                    et = ET[i, dl]
                    if et < 0 or et < last:
                        continue
                    r = R[i, dl, dsel[k], s, q, h]
                    if r != r:
                        continue
                    last = et + DT[i, dl, dsel[k], s, q, h]
                    n += 1; sr += r
                    if r > 0:
                        gw += r; w += 1
                    else:
                        gl -= r
                    g = 1.0 + 0.1 * r
                    if g <= 1e-5:
                        lg = -1e9
                    else:
                        lg += np.log(g)
                    bal = lg
                    if bal > peak:
                        peak = bal
                    if bal - peak < dd:
                        dd = bal - peak
                    mr[mon[i]] += r
                # stress
                last = -1
                n2 = 0; sr2 = 0.0; gw2 = 0.0; gl2 = 0.0
                for k in range(idx.shape[0]):
                    i = idx[k]
                    et = ETs[i, dl]
                    if et < 0 or et < last:
                        continue
                    r = Rs[i, dl, dsel[k], s, q, h]
                    if r != r:
                        continue
                    last = et + DTs[i, dl, dsel[k], s, q, h]
                    n2 += 1; sr2 += r
                    if r > 0:
                        gw2 += r
                    else:
                        gl2 -= r
                mp = 0; mt = 0
                for m in range(nmon):
                    if mr[m] != 0.0:
                        mt += 1
                        if mr[m] > 0:
                            mp += 1
                out[row, 0] = s; out[row, 1] = q; out[row, 2] = h
                out[row, 3] = n; out[row, 4] = sr; out[row, 5] = gw / gl if gl > 0 else 99.0
                out[row, 6] = w / max(n, 1); out[row, 7] = lg; out[row, 8] = 1.0 - np.exp(dd)
                out[row, 9] = mp; out[row, 10] = mt; out[row, 11] = sr2; out[row, 12] = gw2 / gl2 if gl2 > 0 else 99.0
                row += 1
    return row


def load(tag=TAG):
    F = pd.read_pickle(f"{WORK}/feats{tag}.pkl")
    base, outc = {}, {}
    for inst in ["gold", "nasdaq"]:
        base[inst] = np.load(f"{WORK}/base{tag}_{inst}.npz")
        o = np.load(f"{WORK}/out{tag}_{inst}.npz")
        outc[inst] = {k: o[k] for k in o.files}
    ext = None
    if os.path.exists(f"{WORK}/macro{tag}.pkl") and os.path.exists(f"{WORK}/tscore{tag}.npz"):
        ext = {"mstrong": pd.read_pickle(f"{WORK}/macro{tag}.pkl").mstrong.to_numpy()}
        z = np.load(f"{WORK}/tscore{tag}.npz"); ext.update({k: z[k] for k in z.files})
        ext["srch"] = (F.ts.to_numpy() >= S0) & (F.ts.to_numpy() < S1)
    return F, base, outc, ext


def filters(F):
    a = {}
    a["all"] = np.ones(len(F), bool)
    for c in ["wb", "excl", "brk", "siren", "star", "macro", "first", "sim_other", "num", "pct"]:
        a[c] = F[c].to_numpy()
    a["fj"] = ~F.wb.to_numpy()
    a["nonmacro"] = ~F.macro.to_numpy()
    a["caps"] = (F.caps >= 0.7).to_numpy()
    a["follow"] = ~F["first"].to_numpy()
    a["burst"] = (F.nprev60 >= 2).to_numpy()
    a["quiet"] = (F.nprev300 == 0).to_numpy()
    a["long"] = (F.len >= 100).to_numpy()
    a["short"] = (F.len < 60).to_numpy()
    a["cal_near"] = (F.cal_since <= 900).to_numpy()
    a["cal_far"] = ((F.cal_since > 3600) & (F.cal_until > 3600)).to_numpy()
    h = F.hour.to_numpy()
    a["asia"] = (h <= 6); a["eu"] = (h >= 7) & (h <= 12); a["us"] = (h >= 13) & (h <= 20); a["late"] = h >= 21
    imp = list(a.keys())
    kws = [c for c in F.columns if c.startswith("kw_")]
    for c in kws:
        a[c[3:]] = F[c].to_numpy()
    out = dict(a)
    imp2 = [x for x in imp if x != "all"]
    for x, y in itertools.combinations(imp2, 2):
        m = a[x] & a[y]
        if m.sum() >= 40:
            out[f"{x}&{y}"] = m
    for x in imp2:
        for c in kws:
            m = a[x] & a[c[3:]]
            if m.sum() >= 40:
                out[f"{x}&{c[3:]}"] = m
    return out


def dir_rules(base, inst, dl, ext=None):
    P, offs, v = base[inst]["P"], list(base[inst]["offs"]), base[inst]["vol60"]
    v = np.where(np.isfinite(v), v, base[inst]["vol240"])
    o = {0: 2, 10: 12, 30: 30}[dl]
    po = P[:, offs.index(o)]
    rules = {"buy": np.ones(len(v), np.int8), "sell": -np.ones(len(v), np.int8)}
    for a in [-60, -10, 0, -1800]:
        pre = (po - P[:, offs.index(a)]) / v
        pre = np.where(np.isfinite(pre), pre, 0.0)
        for th in ([0.5, 1, 2, 3] if a != -1800 else [1, 3, 6]):
            m = (np.abs(pre) >= th).astype(np.int8) * np.sign(pre).astype(np.int8)
            rules[f"mom{a}_{th}"] = m
            rules[f"fade{a}_{th}"] = -m
    if ext is not None:
        ms = ext["mstrong"].astype(np.int8)
        rules["mac+"] = ms; rules["mac-"] = -ms
        pre = (po - P[:, offs.index(-60)]) / v
        agree = (np.sign(pre) == np.sign(ms)) & (np.abs(pre) >= 0.5)
        rules["mac+_pre"] = np.where(agree, ms, 0).astype(np.int8)    # follow: strong data & price already rising
        agree2 = (np.sign(pre) == -np.sign(ms)) & (np.abs(pre) >= 0.5)
        rules["mac-_pre"] = np.where(agree2, -ms, 0).astype(np.int8)  # strong data & price already falling
        srch = ext["srch"]
        pre10 = (po - P[:, offs.index(-10)]) / v
        for H in [60, 300, 1800]:
            sc = ext.get(f"{inst}_{H}")
            if sc is None:
                continue
            sc = np.where(np.isfinite(sc), sc, 0.0)
            for qq in [0.5, 0.8, 0.95]:
                th = np.quantile(np.abs(sc[srch & (sc != 0)]), qq)
                m = (np.abs(sc) >= th).astype(np.int8) * np.sign(sc).astype(np.int8)
                rules[f"ts{H}_q{qq}"] = m
                rules[f"ts{H}_q{qq}_agree"] = np.where(np.sign(pre10) == m, m, 0).astype(np.int8)
    return rules


def run(tag=TAG, rseed=RSEED, outname=None):
    t0 = time.time()
    F, base, outc, ext = load(tag)
    ts = F.ts.to_numpy()
    srch = (ts >= S0) & (ts < S1)
    mon = ((pd.to_datetime(ts, unit="s").year - 2025) * 12 + pd.to_datetime(ts, unit="s").month - 1).to_numpy().astype(np.int64)
    nmon = int(mon.max()) + 1
    flt = filters(F)
    fnames = list(flt)
    print("filters", len(fnames), flush=True)
    rng = np.random.default_rng(rseed) if rseed >= 0 else None
    meta, blocks = [], []
    NCOMB[0] = 0
    for ii, inst in enumerate(["gold", "nasdaq"]):
        oc = outc[inst]
        R, DT, ET, Rs, DTs, ETs = oc["R"], oc["DT"], oc["ET"], oc["R_s"], oc["DT_s"], oc["ET_s"]
        nex = R.shape[3] * R.shape[4] * R.shape[5]
        for di, dl in enumerate(oc["delays"]):
            rules = dir_rules(base, inst, int(dl), ext)
            rnames = list(rules)
            valid = srch & (ET[:, di] >= 0)
            for ri, rn in enumerate(rnames):
                d = rules[rn]
                if rng is not None:       # luck check: random directions with the same trade/no-trade pattern
                    d = (d != 0).astype(np.int8) * rng.choice(np.array([-1, 1], np.int8), len(d))
                base_m = valid & (d != 0)
                for fi, fn in enumerate(fnames):
                    m = base_m & flt[fn]
                    idx = np.flatnonzero(m)
                    if len(idx) < 30:
                        continue
                    dsel = (d[idx] < 0).astype(np.int64)
                    out = np.zeros((nex, 13), np.float32)
                    eval_set(idx, dsel, di, R, DT, ET, Rs, DTs, ETs, mon, nmon, out, 0)
                    NCOMB[0] += nex
                    keep = (out[:, 3] >= 30) & (out[:, 5] > 1.05) & (out[:, 11] > 0)
                    if keep.any():
                        blocks.append(out[keep])
                        meta.append(np.repeat(np.array([[ii, di, ri, fi]], np.int32), keep.sum(), 0))
            print(inst, dl, "rules", len(rnames), "rows", sum(len(b) for b in blocks), round(time.time() - t0), flush=True)
    res = np.concatenate(blocks); mt = np.concatenate(meta)
    df = pd.DataFrame(res, columns=["s", "q", "h", "n", "R", "pf", "win", "lg", "dd", "mpos", "mtot", "Rs", "pfs"])
    df[["inst", "dl", "rule", "flt"]] = mt
    df = df.astype({"s": np.int8, "q": np.int8, "h": np.int8, "n": np.int32, "inst": np.int8, "dl": np.int8, "rule": np.int16, "flt": np.int32})
    outname = outname or f"res{tag}{'_rd%d' % rseed if rseed >= 0 else ''}"
    df.to_parquet(f"{WORK}/{outname}.parquet")
    rn_all = {}
    for inst in ["gold", "nasdaq"]:
        for dl in [0, 10, 30]:
            rn_all = list(dir_rules(base, inst, dl, ext).keys())
    pd.Series(fnames).to_csv(f"{WORK}/{outname}_filters.csv")
    pd.Series(rn_all).to_csv(f"{WORK}/{outname}_rules.csv")
    print("saved", len(df), "rows of", NCOMB[0], "combinations", round(time.time() - t0), "s", flush=True)
    return df


if __name__ == "__main__":
    run()
