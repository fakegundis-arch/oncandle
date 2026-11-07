import sys, numpy as np, pandas as pd
import search as S, search_wf as W
from prep_outcomes import STOPS, TPS, TIMERS
_ctx = {}
def ctx(tag=""):
    if tag not in _ctx:
        F, base, outc, ext = S.load(tag)
        ts = F.ts.to_numpy(); dt = pd.to_datetime(ts, unit="s")
        mon = ((dt.year - 2025) * 12 + dt.month - 1).to_numpy().astype(np.int64)
        _ctx[tag] = (F, base, outc, ext, S.filters(F), mon)
    return _ctx[tag]
def segs(inst, dl, rule, flt, tag=""):
    F, base, outc, ext, flts, mon = ctx(tag)
    oc = outc[inst]; di = list(oc["delays"]).index(dl)
    d = S.dir_rules(base, inst, dl, ext)[rule]
    m = (F.ts.to_numpy() >= S.S0) & (oc["ET"][:, di] >= 0) & (d != 0) & flts[flt]
    idx = np.flatnonzero(m)
    nex = oc["R"].shape[3] * oc["R"].shape[4] * oc["R"].shape[5]
    out = np.zeros((nex, W.NB, W.NC), np.float32)
    W.eval_wf(idx, (d[idx] < 0).astype(np.int64), di, oc["R"], oc["DT"], oc["ET"], oc["R_s"], oc["DT_s"], oc["ET_s"], mon, 18,
              np.array(W.BOUNDS), np.array([12, 14, 16, 18], np.int64), out)
    sg = np.stack([out[:, 0]] + [out[:, b] - out[:, b - 1] for b in range(1, 4)], 1)  # [ex, seg, col]
    return sg
def show(inst, dl, rule, flt, tag=""):
    sg = segs(inst, dl, rule, flt, tag)
    rows = []
    for e in range(sg.shape[0]):
        s, q, h = e // 20, (e // 4) % 5, e % 4
        rows.append((STOPS[s], TPS[q], TIMERS[h], *sg[e, :, 1].round(1), *sg[e, :, 10].round(1), int(sg[e, :, 0].sum())))
    df = pd.DataFrame(rows, columns=["stop", "tp", "hold", "R_A", "R_B", "R_C", "R_D", "S_A", "S_B", "S_C", "S_D", "n"])
    return df
if __name__ == "__main__":
    a = sys.argv[1:]
    df = show(a[0], int(a[1]), a[2], a[3])
    pd.set_option("display.width", 200)
    print(" ".join(a)); print(df.to_string())
