"""Exit refinement (stop / target / timer / break-even / trailing) for the frozen candidates' entry signals.
Ranks on the search period only; prints the check period for the search-best exit and for the frozen exit."""
import itertools, sys
import numpy as np, pandas as pd
from lib import C, DATA, WORK, lean_ticks, known_price, minute_vol, mid_last
import strategy as ST
from engine import gaps
from stage2 import outcomes, dedupe

S1 = pd.Timestamp("2026-05-01", tz="UTC").timestamp(); S2 = pd.Timestamp("2026-07-01", tz="UTC").timestamp()
p = pd.read_pickle(f"{WORK}/posts.pkl")
F = pd.read_pickle(f"{WORK}/feats.pkl")
F["urg3"] = F.siren | F.brk | F.excl
tk = lean_ticks("gold"); T = tk["t"]; px = mid_last(tk); g = gaps(T)
ts = p.ts.to_numpy(np.int64)
for name, prm in ST.CANDIDATES.items():
    leg = prm["legs"][0]
    m = ST.filter_mask(F, leg["filter"])
    idx = np.flatnonzero(m); tsi = ts[idx]
    v = minute_vol(T, px, tsi, 60); v = np.where(np.isfinite(v), v, minute_vol(T, px, tsi, 240))
    o = {0: 2, 10: 12, 30: 30}[leg["delay"]]
    P = {"o": known_price(T, px, tsi + o)}
    r = leg["rule"]
    if r["kind"] in ("mom", "fade"):
        P[r["a"]] = known_price(T, px, tsi + r["a"])
    if r["kind"] == "react":
        for off in {0, -60, r["o1"], r["o2"]}:
            P[off] = known_price(T, px, tsi + off)
    d = ST.direction(r, P, v)
    k = (d != 0) & np.isfinite(v)
    tsi, d, v = tsi[k], d[k], v[k]
    dec = tsi + C.LAT + leg["delay"]
    rows = []
    for stop, tp, hold, be, tr in itertools.product([1.5, 3.0, 4.5, 6.0, 9.0], [None, 2.0, 4.0, 8.0], [600, 1800, 3600, 7200, 14400],
                                                    [None, 0.5, 1.0], [None, 0.5, 1.0, 2.0]):
        R, ET, XT, SD = outcomes(tk, g, dec, d, stop * v, tp, hold, be, tr)
        keep = dedupe(ET, XT, R)
        rr, et = R[keep], ET[keep]
        res = [stop, tp, hold, be, tr]
        for a, b in [(0, S1), (S1, S2)]:
            x = rr[(et >= a) & (et < b)]
            res += [len(x), x.sum(), x[x > 0].sum() / max(-x[x < 0].sum(), 1e-9), 1000 * np.exp(np.sum(np.log(np.maximum(1 + 0.1 * x, 1e-9))))]
        rows.append(res)
    df = pd.DataFrame(rows, columns=["stop", "tp", "hold", "be", "trail", "n_s", "R_s", "pf_s", "fin_s", "n_c", "R_c", "pf_c", "fin_c"])
    df.to_csv(f"{WORK}/stage2_{name}.csv", index=False)
    fz = df[(df.stop == leg["stop"]) & (df.tp.isna() if leg["tp"] is None else df.tp == leg["tp"]) & (df.hold == leg["hold"]) & df.be.isna() & df.trail.isna()]
    best = df.sort_values("fin_s", ascending=False).head(5)
    pd.set_option("display.width", 220)
    print("=====", name, "exits tried", len(df), "| share of exits with search R>0:", round((df.R_s > 0).mean(), 2), "| check R>0:", round((df.R_c > 0).mean(), 2))
    print("frozen exit:\n", fz.round(2).to_string())
    print("search-best exits:\n", best.round(2).to_string(), flush=True)
