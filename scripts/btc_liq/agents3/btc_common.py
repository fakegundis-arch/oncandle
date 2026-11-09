"""FIXED rules for the version-3 agent search (Bitcoin, signals from Binance, trades on Exness BTCUSDm).  Do not edit.

Every strategy must take its data, fills, exits and account figures from this module.

data_dir layout (the agents get a copy that covers 2025-12-01 .. 2026-06-30; December 2025 is look-back only):
  binance_1s/<YYYY-MM>.npz   Binance USD-M BTCUSDT, one row per second with trades: t (UTC s), o/h/l/c price,
                             bq / sq taker BUY / SELL quantity (BTC), nb / ns number of aggressive buy / sell trades,
                             mb / ms largest single aggressive buy / sell trade (BTC)
  metrics.csv.gz             BTCUSDT every 5 min: create_time, sum_open_interest (BTC), sum_open_interest_value,
                             count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio, count_long_short_ratio,
                             sum_taker_long_short_vol_ratio.  A value is known 60 s after create_time.
  eth_metrics.csv.gz         the same for ETHUSDT
  funding.csv.gz             BTCUSDT funding: calc_time (ms), funding_interval_hours, last_funding_rate
  premium_1m.parquet         BTCUSDT premium index, 1-minute klines: open_time (ms), open, high, low, close
                             (a minute is known at its end: open_time + 60 s)
  bookdepth/<YYYY-MM>.parquet order-book depth (BTC) at -5..-0.2 % and +0.2..+5 % from the price, ~30 s apart; a
                             snapshot is known 5 s after its time
  exness/<YYYY-MM>.npz       Exness BTCUSDm one-second bid / ask bars (t, bid_first/last/min/max, ask_first/last/min/max,
                             n) - the prices the bot trades at

Rules (enforced below): a decision taken at second s may use Binance seconds < s, a 5-minute metrics row only from its
create_time + 60 s, depth snapshots from their time + 5 s, premium minutes from their end, funding from calc_time.
Orders reach Exness 2 s after the decision (stress: 5 s).  Market buy = ask + 1 spread (stress 2), sell = bid - 1
spread.  Stop orders fill at max(price, ask) + 1 spread (buy); limit orders fill at their price only if the price trades
1 spread through it (stress 2).  Every trade has a stop fixed at entry, at least 3 spreads; r = profit / stop
distance.  Exits checked from the second after the fill; stop and target in the same second -> stop; gaps fill at the
second's first price; timer exits at the first price at / after fill + timer; flat at the last quote before a
>= 10-minute pause; break-even / trailing stop changes apply from the next second; stress loses 1 more spread on the
exit.  Account: 10 % of the balance risked per trade, lot capped at 100 x balance / price, at most 30 % of the balance
at risk at once, P&L booked at exit.
"""
from __future__ import annotations

import os

import numba as nb
import numpy as np
import pandas as pd

LAT, LAT_STRESS, GAP = 2, 5, 600
RISK, CAP, MAXOPEN = 0.10, 100.0, 0.30


def _months(a, b):
    out, m = [], pd.Period(a[:7], "M")
    while str(m) < b[:7]:
        out.append(str(m))
        m += 1
    return out


def ts_of(s) -> int:
    return int(pd.Timestamp(s, tz="UTC").timestamp())


class Market:
    """everything for [start, end) (start should leave look-back before the first trade)."""

    def __init__(self, data_dir: str, start: str, end: str):
        self.data_dir = data_dir
        ms = [m for m in _months(start, end) if os.path.exists(os.path.join(data_dir, "binance_1s", f"{m}.npz"))]
        if not ms:
            raise FileNotFoundError("no data for " + start + " .. " + end)
        self.t0, t1 = ts_of(start), ts_of(end)
        self.n = t1 - self.t0
        parts = [dict(np.load(os.path.join(data_dir, "binance_1s", f"{m}.npz"))) for m in ms]
        z = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
        keep = (z["t"] >= self.t0) & (z["t"] < t1)
        i = z["t"][keep] - self.t0
        c = np.full(self.n, np.nan)
        c[i] = z["c"][keep]
        self.c = pd.Series(c).ffill().bfill().to_numpy()          # last trade price of each second
        self.raw = {k: np.zeros(self.n, np.float32 if k in ("bq", "sq", "mb", "ms") else np.float64)
                    for k in ("bq", "sq", "mb", "ms", "nb", "ns", "h", "l")}
        for k in self.raw:
            self.raw[k][i] = z[k][keep]
        self.raw["h"][self.raw["h"] == 0] = np.nan
        self.raw["l"][self.raw["l"] == 0] = np.nan
        self.CB = np.r_[0.0, np.cumsum(self.raw["bq"], dtype=np.float64)]   # CB[i] = taker buy BTC in seconds < i
        self.CS = np.r_[0.0, np.cumsum(self.raw["sq"], dtype=np.float64)]
        nm = self.n // 60
        mc = self.c[np.arange(1, nm + 1) * 60 - 1]
        mv = pd.Series(np.r_[np.nan, np.abs(np.diff(mc))]).rolling(60, min_periods=30).mean().to_numpy()
        sm = np.arange(self.n) // 60 - 1
        self.vol = np.where(sm >= 0, mv[np.clip(sm, 0, nm - 1)], np.nan)  # mean |1-min change|, prior 60 min
        self.metrics = self._metrics("metrics.csv.gz", start, end)
        self.eth = self._metrics("eth_metrics.csv.gz", start, end)
        fr = pd.read_csv(os.path.join(data_dir, "funding.csv.gz"))
        fr["ts"] = fr.calc_time // 1000
        self.funding = fr[(fr.ts >= self.t0 - 3 * 86400) & (fr.ts < t1)].reset_index(drop=True)
        pr = pd.read_parquet(os.path.join(data_dir, "premium_1m.parquet"))
        pr["known_ts"] = pr.open_time // 1000 + 60
        self.premium = pr[(pr.known_ts >= self.t0) & (pr.known_ts < t1)].reset_index(drop=True)
        dps = [pd.read_parquet(os.path.join(data_dir, "bookdepth", f"{m}.parquet")) for m in ms
               if os.path.exists(os.path.join(data_dir, "bookdepth", f"{m}.parquet"))]
        d = pd.concat(dps).sort_values("time")
        d["ts"] = d.time.astype("datetime64[s]").astype("int64")
        self.depth = d[(d.ts >= self.t0) & (d.ts < t1)].reset_index(drop=True)
        tparts = [dict(np.load(os.path.join(data_dir, "exness", f"{m}.npz"))) for m in ms]
        tk = {k: np.concatenate([p[k] for p in tparts]) for k in tparts[0]}
        o = np.argsort(tk["t"], kind="stable")
        tk = {k: v[o] for k, v in tk.items()}
        keep = np.r_[True, np.diff(tk["t"]) > 0] & (tk["t"] < t1)
        self.tk = {k: np.ascontiguousarray(v[keep]) for k, v in tk.items()}
        self.gaps = np.flatnonzero(np.diff(self.tk["t"]) >= GAP).astype(np.int64)

    def _metrics(self, f, start, end):
        m = pd.read_csv(os.path.join(self.data_dir, f), parse_dates=["create_time"])
        m = m[(m.create_time >= pd.Timestamp(start)) & (m.create_time < pd.Timestamp(end))]
        m = m.drop_duplicates("create_time").sort_values("create_time").reset_index(drop=True)
        m["ts"] = m.create_time.astype("datetime64[s]").astype("int64")
        m["known_ts"] = m.ts + 60
        oi = m.sum_open_interest.to_numpy(float).copy()
        oi[~(oi > 0)] = np.nan                                   # Binance sometimes publishes 0: missing
        m["sum_open_interest"] = oi
        return m

    def idx(self, ts):
        return np.asarray(ts) - self.t0


# ------------------------------------------------------------------ numba engine
@nb.njit(cache=True)
def _next_close(T, gaps, i):
    k = np.searchsorted(gaps, i)
    return gaps[k] if k < len(gaps) else len(T) - 1


@nb.njit(cache=True)
def nb_entry(T, bf, af, amin, amax, bmin, bmax, gaps, sig_ts, d, kind, offset, life, stress):
    """decision at sig_ts.  kind 0 = market; 1 = limit at (Exness mid - d * offset); 2 = stop at (mid + d * offset);
    pending orders live `life` s.  -> (fill index, fill price) or (-1, 0)."""
    lat = 5 if stress else 2
    k = 2.0 if stress else 1.0
    ts = sig_ts + lat
    i = np.searchsorted(T, ts)
    if i >= len(T) or T[i] - ts > 10:
        return -1, 0.0
    if kind == 0:
        sp = af[i] - bf[i]
        return i, (af[i] if d > 0 else bf[i]) + d * k * sp
    mid = 0.5 * (af[i] + bf[i])
    px = mid - d * offset if kind == 1 else mid + d * offset
    end = _next_close(T, gaps, i)
    w = min(np.searchsorted(T, T[i] + life), end + 1)
    for x in range(i + 1, w):
        sp = af[x] - bf[x]
        if kind == 1:
            if d > 0 and amin[x] <= px - k * sp:
                return x, px
            if d < 0 and bmax[x] >= px + k * sp:
                return x, px
        else:
            if d > 0 and amax[x] >= px:
                return x, max(px, af[x]) + k * sp
            if d < 0 and bmin[x] <= px:
                return x, min(px, bf[x]) - k * sp
    return -1, 0.0


@nb.njit(cache=True)
def nb_exit(T, bf, bl, bmin, bmax, af, al, amin, amax, gaps, j, fill, d, stop_dist, tp_r, hold, be_at, trail, stress):
    """position filled at index j -> (exit index, r, stop distance).  tp_r / be_at / trail: nan = off; hold 0 = none."""
    n = len(T)
    sd = max(stop_dist, 3 * (af[j] - bf[j]))
    end = _next_close(T, gaps, j)
    k_end = min(np.searchsorted(T, T[j] + hold), end + 1) if hold > 0 else end + 1
    timer = hold > 0 and k_end <= end
    sl = fill - d * sd
    has_tp = not np.isnan(tp_r)
    tp = fill + d * tp_r * sd if has_tp else 0.0
    use_be, use_tr = not np.isnan(be_at), not np.isnan(trail)
    armed = not use_be
    best = fill
    kx, px = -1, 0.0
    for x in range(j + 1, k_end):
        if d > 0:
            f, adv, fav = bf[x], bmin[x], bmax[x]
        else:
            f, adv, fav = af[x], amax[x], amin[x]
        if d * (f - sl) <= 0:
            kx, px = x, f
            break
        if has_tp and d * (f - tp) >= 0:
            kx, px = x, f
            break
        if d * (adv - sl) <= 0:
            kx, px = x, sl
            break
        if has_tp and d * (fav - tp) >= 0:
            kx, px = x, tp
            break
        if use_be or use_tr:
            best = max(best, fav) if d > 0 else min(best, fav)
            if (not armed) and d * (best - fill) >= be_at * sd:
                armed = True
                if d * (fill - sl) > 0:
                    sl = fill
            if armed and use_tr:
                cand = best - d * trail * sd
                if d * (cand - sl) > 0:
                    sl = cand
    if kx < 0:
        if timer:
            kx = k_end
            px = bf[kx] if d > 0 else af[kx]
        else:
            kx = min(end, n - 1)
            px = bl[kx] if d > 0 else al[kx]
    r = d * (px - fill) / sd
    if stress:
        k2 = min(kx, n - 1)
        r -= (af[k2] - bf[k2]) / sd
    return kx, r, sd


@nb.njit(cache=True)
def nb_trades(T, bf, bl, bmin, bmax, af, al, amin, amax, gaps, sig, dirs, kind, offset, life, stop_dist, tp_r, hold,
              be_at, trail, stress):
    """many signals, one setting each (arrays per signal) -> entry ts, exit ts, r, stop distance, entry price
    (r = nan when the order was not filled)."""
    m = len(sig)
    ent = np.zeros(m, np.int64)
    ext = np.zeros(m, np.int64)
    rr = np.full(m, np.nan)
    sds = np.zeros(m)
    pxs = np.zeros(m)
    for e in range(m):
        j, fill = nb_entry(T, bf, af, amin, amax, bmin, bmax, gaps, sig[e], dirs[e], kind[e], offset[e], life[e], stress)
        if j < 0:
            continue
        kx, r, sd = nb_exit(T, bf, bl, bmin, bmax, af, al, amin, amax, gaps, j, fill, dirs[e], stop_dist[e], tp_r[e],
                            hold[e], be_at[e], trail[e], stress)
        ent[e], ext[e], rr[e], sds[e], pxs[e] = T[j], T[min(kx, len(T) - 1)], r, sd, fill
    return ent, ext, rr, sds, pxs


@nb.njit(cache=True)
def nb_account(ent, ext, rr, sds, pxs, maxpos, risk, cap, maxopen, start_ts, end_ts):
    """trades in entry order.  -> n, wins, R, gross win, gross loss, final balance, max drawdown, biggest lot"""
    bal, peak, dd = 1000.0, 1000.0, 0.0
    o_on = np.zeros(16, np.bool_)
    o_exit = np.zeros(16, np.int64)
    o_lot = np.zeros(16)
    o_sd = np.zeros(16)
    o_r = np.zeros(16)
    n = wn = 0
    R = gw = gl = maxlot = 0.0
    for e in range(len(rr) + 1):
        last = e == len(rr)
        if not last and (np.isnan(rr[e]) or ent[e] < start_ts or ent[e] >= end_ts):
            continue
        while True:
            best, bk = -1, 0
            for s in range(16):
                if o_on[s] and (last or o_exit[s] <= ent[e]) and (best < 0 or o_exit[s] < best):
                    best, bk = o_exit[s], s
            if best < 0:
                break
            bal = bal + o_lot[bk] * o_sd[bk] * o_r[bk]
            if bal <= 0.01:                                   # wiped out
                bal = 0.0
            o_on[bk] = False
            peak = max(peak, bal)
            if peak > 0:
                dd = min(dd, bal / peak - 1)
        if last:
            break
        cnt, ro = 0, 0.0
        for s in range(16):
            if o_on[s]:
                cnt += 1
                ro += o_lot[s] * o_sd[s]
        if cnt >= maxpos or bal <= 0:
            continue
        st = risk * bal
        if ro + st > maxopen * bal + 1e-9:
            continue
        lot = min(st / sds[e], cap * bal / pxs[e])
        for s in range(16):
            if not o_on[s]:
                o_on[s], o_exit[s], o_lot[s], o_sd[s], o_r[s] = True, ext[e], lot, sds[e], rr[e]
                break
        maxlot = max(maxlot, lot)
        n += 1
        R += rr[e]
        if rr[e] > 0:
            gw += rr[e]
            wn += 1
        else:
            gl -= rr[e]
    return n, wn, R, gw, gl, bal, dd, maxlot


# ------------------------------------------------------------------ python wrappers
def trades(mk: Market, sig_ts, dirs, *, kind=0, offset=0.0, life=180, stop_dist, tp_r=np.nan, hold=0, be_at=np.nan,
           trail=np.nan, stress=False) -> pd.DataFrame:
    """signals (decision second, direction +1 / -1) -> one row per signal with entry_ts, exit_ts, r, sd, entry_px
    (rows without a fill dropped).  Every argument may be a scalar or one value per signal; prices / distances in $."""
    sig = np.asarray(sig_ts, np.int64)
    m = len(sig)
    f = lambda v, t: np.broadcast_to(np.asarray(v, t), (m,)).copy()
    tk = mk.tk
    ent, ext, rr, sds, pxs = nb_trades(tk["t"], tk["bid_first"], tk["bid_last"], tk["bid_min"], tk["bid_max"],
                                       tk["ask_first"], tk["ask_last"], tk["ask_min"], tk["ask_max"], mk.gaps, sig,
                                       f(dirs, np.int64), f(kind, np.int64), f(offset, float), f(life, np.int64),
                                       f(stop_dist, float), f(tp_r, float), f(hold, np.int64), f(be_at, float),
                                       f(trail, float), stress)
    ok = ~np.isnan(rr)
    return pd.DataFrame(dict(sig_ts=sig[ok], dir=f(dirs, np.int64)[ok], entry_ts=ent[ok], exit_ts=ext[ok], r=rr[ok],
                             sd=sds[ok], entry_px=pxs[ok]))


def account(t: pd.DataFrame, start, end, risk=RISK, maxpos=1) -> dict:
    """trade list (sorted by entry) -> n, R, PF, win rate, final balance from $1,000, max drawdown, biggest lot (BTC).
    maxpos 1 = one position at a time (a trade starting while another is open is skipped)."""
    t = t.sort_values(["entry_ts", "sig_ts"]) if len(t) else t
    a, b = ts_of(start), ts_of(end)
    if len(t) == 0:
        return dict(n=0, R=0.0, pf=0.0, win=0.0, final=1000.0, dd=0.0, max_lot=0.0)
    n, wn, R, gw, gl, bal, dd, ml = nb_account(t.entry_ts.to_numpy(np.int64), t.exit_ts.to_numpy(np.int64),
                                          t.r.to_numpy(float), t.sd.to_numpy(float), t.entry_px.to_numpy(float),
                                          maxpos, risk, CAP, MAXOPEN, a, b)
    return dict(n=int(n), R=float(R), pf=float(gw / gl) if gl > 0 else (99.0 if gw > 0 else 0.0), win=wn / n if n else 0.0,
                final=float(bal), dd=float(dd), max_lot=float(ml))
