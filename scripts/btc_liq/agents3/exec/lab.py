"""light-memory loader for searching (same numbers as btc_common.Market for the fields used here)."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import btc_common as bc  # noqa: E402

DATA = "/home/user/btc_lab_data"


class Lab:
    def __init__(self, data_dir=DATA, start="2025-12-01", end="2026-07-01", depth=False):
        self.data_dir = data_dir
        ms = [m for m in bc._months(start, end) if os.path.exists(os.path.join(data_dir, "binance_1s", f"{m}.npz"))]
        self.t0, t1 = bc.ts_of(start), bc.ts_of(end)
        self.n = n = t1 - self.t0
        c = np.full(n, np.nan)
        self.h = np.full(n, np.nan, np.float32)
        self.l = np.full(n, np.nan, np.float32)
        self.bq = np.zeros(n, np.float32)
        self.sq = np.zeros(n, np.float32)
        for m in ms:
            z = np.load(os.path.join(data_dir, "binance_1s", f"{m}.npz"))
            t = z["t"]
            keep = (t >= self.t0) & (t < t1)
            i = t[keep] - self.t0
            c[i] = z["c"][keep]
            h = z["h"][keep]
            lo = z["l"][keep]
            self.h[i] = np.where(h == 0, np.nan, h)
            self.l[i] = np.where(lo == 0, np.nan, lo)
            self.bq[i] = z["bq"][keep]
            self.sq[i] = z["sq"][keep]
            del z
        self.c = pd.Series(c).ffill().bfill().to_numpy()
        del c
        nm = n // 60
        mc = self.c[np.arange(1, nm + 1) * 60 - 1]
        self.mc = mc
        mv = pd.Series(np.r_[np.nan, np.abs(np.diff(mc))]).rolling(60, min_periods=30).mean().to_numpy()
        self.mv = mv  # mv[m] = vol known from minute m+1 on
        # vol[s] = mv[s//60 - 1]
        self.metrics = self._metrics("metrics.csv.gz", start, end)
        self.eth = self._metrics("eth_metrics.csv.gz", start, end)
        fr = pd.read_csv(os.path.join(data_dir, "funding.csv.gz"))
        fr["ts"] = fr.calc_time // 1000
        self.funding = fr[(fr.ts >= self.t0 - 3 * 86400) & (fr.ts < t1)].reset_index(drop=True)
        pr = pd.read_parquet(os.path.join(data_dir, "premium_1m.parquet"))
        pr["known_ts"] = pr.open_time // 1000 + 60
        self.premium = pr[(pr.known_ts >= self.t0) & (pr.known_ts < t1)].reset_index(drop=True)
        if depth:
            dps = [pd.read_parquet(os.path.join(data_dir, "bookdepth", f"{m}.parquet")) for m in ms
                   if os.path.exists(os.path.join(data_dir, "bookdepth", f"{m}.parquet"))]
            d = pd.concat(dps).sort_values("time")
            d["ts"] = d.time.astype("datetime64[s]").astype("int64")
            self.depth = d[(d.ts >= self.t0) & (d.ts < t1)].reset_index(drop=True)
        tparts = [np.load(os.path.join(data_dir, "exness", f"{m}.npz")) for m in ms]
        tt = np.concatenate([p["t"] for p in tparts])
        o = np.argsort(tt, kind="stable")
        tt = tt[o]
        keep = np.r_[True, np.diff(tt) > 0] & (tt < t1)
        self.tk = {"t": np.ascontiguousarray(tt[keep])}
        del tt
        for k in ("bid_first", "bid_last", "bid_min", "bid_max", "ask_first", "ask_last", "ask_min", "ask_max"):
            v = np.concatenate([p[k] for p in tparts])[o]
            self.tk[k] = np.ascontiguousarray(v[keep])
            del v
        del tparts, o, keep
        self.gaps = np.flatnonzero(np.diff(self.tk["t"]) >= bc.GAP).astype(np.int64)

    def vol_at(self, ts):
        s = np.asarray(ts) - self.t0
        sm = s // 60 - 1
        return np.where(sm >= 0, self.mv[np.clip(sm, 0, len(self.mv) - 1)], np.nan)

    def _metrics(self, f, start, end):
        return bc.Market._metrics(self, f, start, end)   # same (corrected) timing as btc_common

    def trades(self, sig_ts, dirs, **kw):
        return bc.trades(self, sig_ts, dirs, **kw)

    # nb_trades raw call with arrays
    def nbt(self, sig, dirs, kind, offset, life, stop_dist, tp_r, hold, be_at, trail, stress=False):
        tk = self.tk
        m = len(sig)
        f = lambda v, t: np.broadcast_to(np.asarray(v, t), (m,)).copy()
        return bc.nb_trades(tk["t"], tk["bid_first"], tk["bid_last"], tk["bid_min"], tk["bid_max"],
                            tk["ask_first"], tk["ask_last"], tk["ask_min"], tk["ask_max"], self.gaps,
                            np.asarray(sig, np.int64), f(dirs, np.int64), f(kind, np.int64), f(offset, float),
                            f(life, np.int64), f(stop_dist, float), f(tp_r, float), f(hold, np.int64),
                            f(be_at, float), f(trail, float), stress)
