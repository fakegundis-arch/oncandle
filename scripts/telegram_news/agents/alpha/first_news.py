"""Hypothesis family 'market had not moved yet': urgent headline, quiet price in the minute before the post, then
follow (or fade) the reaction measured between the post and the decision.  Small grid, evaluated per segment
(A=2025, B=Jan-Feb 26, C=Mar-Apr 26, D=May-Jun 26) with the walk-forward evaluator.  Usage: python first_news.py [tag]"""
import sys, itertools
import numpy as np, pandas as pd
import search as S, search_wf as W
from prep_outcomes import STOPS, TPS, TIMERS


def urgent_sets(F):
    si, br, ex, st = (F[c].to_numpy() for c in ["siren", "brk", "excl", "star"])
    return {"siren": si, "brk": br, "excl": ex, "star": st, "urg4": si | br | ex | st, "urg3": si | br | ex,
            "wb_caps": F.wb.to_numpy() & (F.caps >= 0.7).to_numpy() & F["first"].to_numpy(), "first_any": F["first"].to_numpy()}


def run(tag=""):
    F, base, outc, ext = S.load(tag)
    ts = F.ts.to_numpy(); dt = pd.to_datetime(ts, unit="s")
    mon = ((dt.year - 2025) * 12 + dt.month - 1).to_numpy().astype(np.int64)
    U = urgent_sets(F)
    rows = []
    for inst in ["gold", "nasdaq"]:
        b = base[inst]; P, offs = b["P"], list(b["offs"])
        v = np.where(np.isfinite(b["vol60"]), b["vol60"], b["vol240"])
        oc = outc[inst]
        pre = np.abs((P[:, offs.index(0)] - P[:, offs.index(-60)]) / v)
        for dl, (o1, o2) in [(10, (2, 12)), (10, (0, 12)), (30, (2, 30)), (30, (0, 30))]:
            di = list(oc["delays"]).index(dl)
            rx = (P[:, offs.index(o2)] - P[:, offs.index(o1)]) / v
            rx = np.where(np.isfinite(rx), rx, 0.0)
            for (un, um), q, th, mode in itertools.product(U.items(), [0.5, 1.0, 2.0, 99.0], [0.5, 1.0, 2.0], ["mom", "fade"]):
                d = (np.abs(rx) >= th) * np.sign(rx) * (1 if mode == "mom" else -1)
                m = (ts >= S.S0) & um & (pre < q) & (d != 0) & (oc["ET"][:, di] >= 0)
                idx = np.flatnonzero(m)
                if len(idx) < 20:
                    continue
                nex = oc["R"].shape[3] * oc["R"].shape[4] * oc["R"].shape[5]
                out = np.zeros((nex, W.NB, W.NC), np.float32)
                W.eval_wf(idx, (d[idx] < 0).astype(np.int64), di, oc["R"], oc["DT"], oc["ET"], oc["R_s"], oc["DT_s"], oc["ET_s"],
                          mon, 18, np.array(W.BOUNDS), np.array([12, 14, 16, 18], np.int64), out)
                sg = np.stack([out[:, 0]] + [out[:, k] - out[:, k - 1] for k in range(1, 4)], 1)
                for e in range(nex):
                    s, qq, h = e // 20, (e // 4) % 5, e % 4
                    rows.append((inst, dl, f"{o1}->{o2}", un, q, th, mode, STOPS[s], TPS[qq], TIMERS[h],
                                 *sg[e, :, 0], *sg[e, :, 1], *sg[e, :, 10], *sg[e, :, 5],
                                 out[e, 2, 0], out[e, 2, 5]))
    cols = ["inst", "dl", "win", "U", "q", "th", "mode", "stop", "tp", "hold"] + [f"n{x}" for x in "ABCD"] + \
           [f"R{x}" for x in "ABCD"] + [f"S{x}" for x in "ABCD"] + [f"lg{x}" for x in "ABCD"] + ["n_srch", "lg_srch"]
    df = pd.DataFrame(rows, columns=cols)
    df.to_parquet(f"{S.WORK}/first_news{tag}.parquet")
    return df


if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else ""
    df = run(tag)
    print(tag or "real", "combinations", len(df))
    ok = (df.n_srch >= 30)
    d = df[ok].sort_values("lg_srch", ascending=False)
    print("best search-period $", round(1000 * np.exp(d.lg_srch.iloc[0])))
    pd.set_option("display.width", 250)
    print(d.head(12)[["inst", "dl", "win", "U", "q", "th", "mode", "stop", "tp", "hold", "nA", "nB", "nC", "nD", "SA", "SB", "SC", "SD", "lg_srch"]].round(2).to_string())
