"""Per-5-minute-bucket feature table (decision at create_time + 60 s + DELAY), light-memory loader.
Mirrors btc_common.Market's arrays (c ffill/bfill, vol); checked against Market in check_prep.py.
Output: feat.parquet (one row per metrics bucket, Dec 1 2025 .. Jun 30 2026)."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import btc_common as bc  # noqa: E402

D = "/home/user/btc_lab_data"
OUT = os.path.dirname(os.path.abspath(__file__))
START, END = "2025-12-01", "2026-07-01"


def load_binance(start, end):
    t0, t1 = bc.ts_of(start), bc.ts_of(end)
    n = t1 - t0
    c = np.full(n, np.nan)
    bq = np.zeros(n, np.float32)
    sq = np.zeros(n, np.float32)
    for m in bc._months(start, end):
        f = os.path.join(D, "binance_1s", f"{m}.npz")
        if not os.path.exists(f):
            continue
        z = np.load(f)
        t = z["t"]
        k = (t >= t0) & (t < t1)
        i = t[k] - t0
        c[i] = z["c"][k]
        bq[i] = z["bq"][k]
        sq[i] = z["sq"][k]
        del z
    c = pd.Series(c).ffill().bfill().to_numpy()
    return t0, n, c, bq, sq


def vol_of(c, n):
    nm = n // 60
    mc = c[np.arange(1, nm + 1) * 60 - 1]
    mv = pd.Series(np.r_[np.nan, np.abs(np.diff(mc))]).rolling(60, min_periods=30).mean().to_numpy()
    return mv  # vol at second s = mv[s // 60 - 1]


def metrics(f, start, end):
    m = pd.read_csv(os.path.join(D, f), parse_dates=["create_time"])
    m = m[(m.create_time >= pd.Timestamp(start)) & (m.create_time < pd.Timestamp(end))]
    m = m.drop_duplicates("create_time").sort_values("create_time").reset_index(drop=True)
    m["ts"] = m.create_time.astype("datetime64[s]").astype("int64")
    oi = m.sum_open_interest.to_numpy(float).copy()
    oi[~(oi > 0)] = np.nan
    m["sum_open_interest"] = oi
    return m


def build(delay=0, mode="rule"):
    """mode 'rule': decision at create_time + 60 (+delay), price bucket [ct-300, ct) (btc_common timing).
    mode 'honest': the metrics row of create_time ct describes [ct, ct+300) (verified: taker ratio of row ct = taker
    flow in [ct, ct+300), corr 0.994), so it is used only from ct + 360 (+delay); price bucket [ct, ct+300)."""
    t0, n, c, bq, sq = load_binance(START, END)
    mv = vol_of(c, n)
    CB = np.r_[0.0, np.cumsum(bq, dtype=np.float64)]
    CS = np.r_[0.0, np.cumsum(sq, dtype=np.float64)]
    nb_ = n // 300
    grid = t0 + 300 * np.arange(nb_)
    m = metrics("metrics.csv.gz", START, END).set_index("ts").reindex(grid)
    e = metrics("eth_metrics.csv.gz", START, END).set_index("ts").reindex(grid)
    F = pd.DataFrame(index=np.arange(nb_))
    F["ct"] = grid
    s = grid + (60 if mode == "rule" else 360) + delay      # decision second
    bsh = 0 if mode == "rule" else 300                      # price bucket = [ct + bsh - 300, ct + bsh)
    F["s"] = s
    si = s - t0
    ok = si < n
    si = np.minimum(si, n - 1)
    cti = grid - t0 + bsh
    # ---- open interest
    oi = m.sum_open_interest.to_numpy(float)
    lo = np.log(oi)
    def dl(x, k):
        out = np.full(len(x), np.nan)
        out[k:] = x[k:] - x[:-k]
        return out
    for k, nm in [(1, 5), (2, 10), (3, 15), (6, 30), (12, 60)]:
        F[f"d{nm}"] = np.expm1(dl(lo, k))
    F["prev5"] = np.r_[np.nan, F.d5.to_numpy()[:-1]]
    F["accel"] = F.d5 - F.prev5
    d5 = F.d5.to_numpy()
    nd = np.zeros(nb_)
    for i in range(1, nb_):
        nd[i] = nd[i - 1] + 1 if d5[i] < 0 else 0
    F["ndrop"] = nd
    s5 = pd.Series(d5)
    for w, nm in [(288, "1d"), (2016, "7d")]:
        sd = s5.shift(1).rolling(w, min_periods=w // 2).std()
        F[f"z5_{nm}"] = d5 / sd
    F["z10_7d"] = F.d10 / pd.Series(F.d10.to_numpy()).shift(2).rolling(2016, min_periods=1000).std()
    F["z15_7d"] = F.d15 / pd.Series(F.d15.to_numpy()).shift(3).rolling(2016, min_periods=1000).std()
    # OI level relative to its 7-day / 1-day mean (positioning build-up)
    F["oi_rel7d"] = oi / pd.Series(oi).shift(1).rolling(2016, min_periods=1000).mean() - 1
    F["oi_rel1d"] = oi / pd.Series(oi).shift(1).rolling(288, min_periods=144).mean() - 1
    # ---- ETH
    eoi = np.log(e.sum_open_interest.to_numpy(float))
    for k, nm in [(1, 5), (2, 10), (3, 15), (6, 30)]:
        F[f"e{nm}"] = np.expm1(dl(eoi, k))
    e5 = F.e5.to_numpy()
    F["ez5_7d"] = e5 / pd.Series(e5).shift(1).rolling(2016, min_periods=1000).std()
    # ---- ratios
    for col, nm in [("count_long_short_ratio", "lsr"), ("count_toptrader_long_short_ratio", "tacc"),
                    ("sum_toptrader_long_short_ratio", "tpos")]:
        x = np.log(m[col].to_numpy(float))
        F[nm] = np.exp(x)
        F[nm + "_c5"] = dl(x, 1)
        F[nm + "_c60"] = dl(x, 12)
        sx = pd.Series(x).shift(1)
        F[nm + "_z7d"] = (x - sx.rolling(2016, min_periods=1000).mean()) / sx.rolling(2016, min_periods=1000).std()
    ex = np.log(e.count_long_short_ratio.to_numpy(float))
    F["elsr"] = np.exp(ex)
    F["taker"] = m.sum_taker_long_short_vol_ratio.to_numpy(float)
    F["taker_prev"] = np.r_[np.nan, F.taker.to_numpy()[:-1]]
    F["etaker"] = e.sum_taker_long_short_vol_ratio.to_numpy(float)
    # ---- funding (last known)
    fr = pd.read_csv(os.path.join(D, "funding.csv.gz"))
    fr["ts"] = fr.calc_time // 1000
    fr = fr.sort_values("ts")
    j = np.searchsorted(fr.ts.to_numpy(), s, side="right") - 1
    F["fund"] = np.where(j >= 0, fr.last_funding_rate.to_numpy()[np.maximum(j, 0)], np.nan)
    # ---- premium index (minute known at open_time + 60)
    pr = pd.read_parquet(os.path.join(D, "premium_1m.parquet")).sort_values("open_time")
    pk = pr.open_time.to_numpy() // 1000 + 60
    pc = pr.close.to_numpy(float)
    cpc = np.r_[0.0, np.cumsum(pc)]
    j = np.searchsorted(pk, s, side="right")          # minutes known at s: [0, j)
    F["prem"] = np.where(j > 0, pc[np.maximum(j - 1, 0)], np.nan)
    for w in (60, 480):
        a = np.maximum(j - w, 0)
        F[f"prem{w}"] = np.where(j > w, (cpc[j] - cpc[a]) / np.maximum(j - a, 1), np.nan)
    p480 = pd.Series(F.prem480.to_numpy())
    F["prem_z"] = (F.prem - F.prem480) / pd.Series(F.prem.to_numpy()).rolling(2016, min_periods=1000).std().shift(1)
    # ---- Binance price / taker flow (seconds < s only)
    px = lambda i: c[np.clip(i - 1, 0, n - 1)]     # last price before second i
    F["p_ct"] = px(cti)
    F["p_s"] = px(si)
    F["m5"] = px(cti) / px(cti - 300) - 1
    F["m10"] = px(cti) / px(cti - 600) - 1
    F["m15"] = px(cti) / px(cti - 900) - 1
    F["m60"] = px(cti) / px(cti - 3600) - 1
    F["mlag"] = px(si) / px(cti) - 1
    F["mtot"] = px(si) / px(cti - 300) - 1
    cc = lambda C, a, b: C[np.clip(b, 0, n)] - C[np.clip(a, 0, n)]
    F["buy5"] = cc(CB, cti - 300, cti)
    F["sell5"] = cc(CS, cti - 300, cti)
    F["nt5"] = F.buy5 - F.sell5
    F["imb5"] = F.nt5 / (F.buy5 + F.sell5)
    F["ntlag"] = cc(CB, cti, si) - cc(CS, cti, si)
    F["tv60m"] = (cc(CB, cti - 3600, cti) + cc(CS, cti - 3600, cti)) / 12   # mean 5-min volume, past hour
    F["vrel5"] = (F.buy5 + F.sell5) / F.tv60m
    cr = c.reshape(-1, 300)
    hi = np.r_[np.nan, cr.max(1)[:-1]]
    lo_ = np.r_[np.nan, cr.min(1)[:-1]]              # bucket [ct-300, ct)
    if bsh:
        hi, lo_ = cr.max(1), cr.min(1)
    F["rng5"] = (hi - lo_) / F.p_ct
    # position of the price at decision inside the bucket range, in the move's direction
    # ---- vol
    sm = si // 60 - 1
    F["vol"] = np.where(sm >= 0, mv[np.clip(sm, 0, len(mv) - 1)], np.nan)
    v = pd.Series(mv)
    vmed = v.rolling(7 * 1440, min_periods=1440).median().to_numpy()
    F["volreg"] = F.vol / np.where(sm >= 0, vmed[np.clip(sm, 0, len(mv) - 1)], np.nan)
    F["volp"] = F.vol / F.p_s
    F["hour"] = (grid // 3600) % 24
    F["dow"] = ((grid // 86400) + 3) % 7                # 0 = Monday
    # ---- depth (snapshot known at time + 5 s)
    dps = []
    for mo in bc._months(START, END):
        f = os.path.join(D, "bookdepth", f"{mo}.parquet")
        if os.path.exists(f):
            dps.append(pd.read_parquet(f))
    d = pd.concat(dps).sort_values("time")
    dts = d.time.astype("datetime64[s]").astype("int64").to_numpy() + 5
    j = np.searchsorted(dts, s, side="right") - 1
    jj = np.maximum(j, 0)
    for lv in ("1.0", "2.0", "5.0"):
        b = d[f"d-{lv}"].to_numpy()[jj]
        a = d[f"d+{lv}"].to_numpy()[jj]
        F[f"dimb{lv[0]}"] = np.where(j >= 0, (b - a) / (b + a), np.nan)
    F["dage"] = np.where(j >= 0, s - dts[jj], np.nan)
    F["valid"] = ok
    return F


if __name__ == "__main__":
    mode = sys.argv[1]
    delay = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    F = build(delay, mode)
    F.to_parquet(os.path.join(OUT, f"feat_{mode}_d{delay}.parquet"))
    print(F.shape)
    print(F.describe().T.to_string())
