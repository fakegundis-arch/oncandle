"""Stage-1 grid search for the OCO straddle family: filters x (offset, expiry) x stop x target x timer x instrument."""
import sys, time
import numpy as np, pandas as pd
from lib import WORK
import search as S
from prep_oco import XS, ES, YS, TPS, TIMERS

if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else ""
    t0 = time.time()
    F = pd.read_pickle(f"{WORK}/feats{tag}.pkl")
    ts = F.ts.to_numpy()
    srch = (ts >= S.S0) & (ts < S.S1)
    mon = ((pd.to_datetime(ts, unit="s").year - 2025) * 12 + pd.to_datetime(ts, unit="s").month - 1).to_numpy().astype(np.int64)
    flt = S.filters(F); fnames = list(flt)
    blocks, meta = [], []; ncomb = 0
    for ii, inst in enumerate(["gold", "nasdaq"]):
        o = np.load(f"{WORK}/oco{tag}_{inst}.npz")
        n = len(ts)
        def rs(a):
            return a.reshape(n, len(XS) * len(ES), 1, len(YS), len(TPS), len(TIMERS))
        R, DT, Rs, DTs = rs(o["R"]), rs(o["DT"]), rs(o["R_s"]), rs(o["DT_s"])
        ET, ETs = o["ET"].reshape(n, -1), o["ET_s"].reshape(n, -1)
        nex = len(YS) * len(TPS) * len(TIMERS)
        for k in range(len(XS) * len(ES)):
            valid = srch
            for fi, fn in enumerate(fnames):
                idx = np.flatnonzero(valid & flt[fn])
                if len(idx) < 30:
                    continue
                dsel = np.zeros(len(idx), np.int64)
                out = np.zeros((nex, 13), np.float32)
                S.eval_set(idx, dsel, k, R, DT, ET, Rs, DTs, ETs, mon, int(mon.max()) + 1, out, 0)
                ncomb += nex
                keep = (out[:, 3] >= 30) & (out[:, 5] > 1.05) & (out[:, 11] > 0)
                if keep.any():
                    blocks.append(out[keep]); meta.append(np.repeat(np.array([[ii, k, fi]], np.int32), keep.sum(), 0))
        print(inst, round(time.time() - t0), flush=True)
    res = np.concatenate(blocks) if blocks else np.zeros((0, 13), np.float32)
    mt = np.concatenate(meta) if meta else np.zeros((0, 3), np.int32)
    df = pd.DataFrame(res, columns=["s", "q", "h", "n", "R", "pf", "win", "lg", "dd", "mpos", "mtot", "Rs", "pfs"])
    df[["inst", "xe", "flt"]] = mt
    df.to_parquet(f"{WORK}/oco_res{tag}.parquet")
    print("saved", len(df), "of", ncomb, "combinations", round(time.time() - t0), flush=True)
