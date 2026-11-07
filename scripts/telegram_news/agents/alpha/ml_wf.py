"""Walk-forward ML angle: gradient boosting on text + story + time + calendar + price-reaction features predicts the
sign of the next-H-second move; trade the confident predictions.  Retrained every month on all earlier months.
Usage: python ml_wf.py [tag]"""
import sys
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from lib import WORK
from prep_outcomes import STOPS, TPS, TIMERS

tag = sys.argv[1] if len(sys.argv) > 1 else ""
F = pd.read_pickle(f"{WORK}/feats{tag}.pkl")
mac = pd.read_pickle(f"{WORK}/macro{tag}.pkl")
ts = F.ts.to_numpy()
dt = pd.to_datetime(ts, unit="s")
mon = ((dt.year - 2025) * 12 + dt.month - 1).to_numpy()
X0 = F.drop(columns=["ts"]).astype(float)
X0["cal_since"] = np.minimum(X0.cal_since, 86400); X0["cal_until"] = np.minimum(X0.cal_until, 86400)
X0["mstrong"] = mac.mstrong.to_numpy()
res = []
for inst in ["gold", "nasdaq"]:
    b = np.load(f"{WORK}/base{tag}_{inst}.npz"); P, offs = b["P"], list(b["offs"])
    v = np.where(np.isfinite(b["vol60"]), b["vol60"], b["vol240"])
    X = X0.copy()
    po = P[:, offs.index(2)]
    for a in [-3600, -1800, -600, -300, -60, -10, 0]:
        X[f"pre{a}"] = np.clip((po - P[:, offs.index(a)]) / v, -20, 20)
    X["vr"] = b["vol15"] / v; X["vl"] = v / b["vol240"]; X["sv"] = b["spr"] / v
    o = np.load(f"{WORK}/out{tag}_{inst}.npz")
    R, DT, ET = o["R"], o["DT"], o["ET"]
    for H, s, q, h in [(600, 2, 4, 2), (3600, 2, 4, 3), (120, 1, 4, 1)]:
        y = (P[:, offs.index(H)] - po) > 0
        okp = np.isfinite(P[:, offs.index(H)]) & np.isfinite(po) & np.isfinite(v) & (ET[:, 0] >= 0)
        pred = np.full(len(ts), np.nan)
        for m in range(9, 18):          # test Oct 2025 .. Jun 2026, train on all earlier months
            tr = okp & (mon < m); te = okp & (mon == m)
            if te.sum() == 0:
                continue
            # leave a gap: drop training samples whose horizon overlaps the test month start
            clf = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=150, min_samples_leaf=200,
                                                 l2_regularization=1.0, random_state=0)
            clf.fit(X[tr].to_numpy(), y[tr])
            pred[te] = clf.predict_proba(X[te].to_numpy())[:, 1]
        for dlt in [0.02, 0.05, 0.08, 0.12]:
            sig = np.where(pred > 0.5 + dlt, 1, np.where(pred < 0.5 - dlt, -1, 0))
            last = -1; rows = []
            for i in np.flatnonzero(sig != 0):
                et = ET[i, 0]
                dd = 0 if sig[i] > 0 else 1
                r = R[i, 0, dd, s, q, h]
                if et < last or not np.isfinite(r):
                    continue
                last = et + DT[i, 0, dd, s, q, h]
                rows.append((mon[i], r))
            if not rows:
                continue
            d = pd.DataFrame(rows, columns=["m", "r"])
            pm = d.groupby("m").r.sum()
            r = d.r.to_numpy()
            res.append((inst, H, dlt, len(r), r.sum(), r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9), 1000 * np.prod(1 + 0.1 * r),
                        (pm > 0).sum(), len(pm), " ".join(f"{x:+.0f}" for x in pm.values)))
        acc = np.nanmean((pred[np.isfinite(pred)] > 0.5) == y[np.isfinite(pred)])
        print(inst, H, "walk-forward hit rate", round(acc, 4), flush=True)
out = pd.DataFrame(res, columns=["inst", "H", "delta", "n", "R", "pf", "final", "mpos", "mtot", "R_by_month(Oct25..Jun26)"])
pd.set_option("display.width", 250)
print(out.round(2).to_string())
out.to_csv(f"{WORK}/ml_wf{tag}.csv", index=False)
