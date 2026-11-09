"""Bitcoin liquidation bot VERSION 2 (open-interest drop, follow the move): PROTOCOL fixed before any V2 result,
Nov 9 2026.  Build on Jan 1 - Jun 30 2026 only.  Then ONE run on Jul 1 - Oct 31 2026 and ONE run on Jan 1 - Nov 30
2025 (a period no version has touched).  Jul-Oct 2026 is no longer clean: version 1's trades there were looked at, and
the idea of giving trades more room came from them; 2025 is the clean exam.

Version 1 (results/btc_liq): a 5-minute Binance open-interest fall >= 0.7 % with a BTC move >= 0.3 % -> follow the move
60 s after the 5-minute mark (+2 s), stop 5 x 1-min vol, target 2R, out after 5 min, one trade at a time.

Version 2 search (Jan-Jun 2026), "follow" only (fading lost in the version-1 grid):
  signal:  x  open-interest fall >= {0.2, 0.3, 0.5, 0.7, 1.0} %       y  price move >= {0.2, 0.3, 0.5, 0.8} %
           w  over the last {1, 2} five-minute buckets
           late  {any, same}: "same" = the price kept moving the same way in the 60 s before the entry
           flow  {any, confirm}: "confirm" = net aggressive (taker) volume in the window agrees with the move
           depth {none, thin}: order-book depth within 1 % on the side the trade moves into <= 0.8 x the other side
  entry:   {mkt, lim0.5, lim1}: market order, or a limit order 0.5 / 1 x 1-min vol back from the Exness mid, live 3 min
           (fills only if the price trades 1 spread through it; stress 2)
  exit:    stop {1.5, 2, 3, 5, 8} x 1-min vol; target {0.5, 1, 1.5, 2, 3 R, none}; timer {2, 5, 10, 15, 30, 60} min;
           manage {none, be (stop to entry at +1R), trail1, trail2 (after +1R the stop trails 1 / 2 R behind the best)}
  positions {1 at a time, up to 3 (a new signal adds a trade; open risk <= 30 %)}
  -> 320 x 3 x 720 x 2 = 1,382,400 settings.
Execution and costs as agents/common.py (2 s latency, Exness ask / bid + 1 spread, stop >= 3 spreads, stop before
target, flat before >= 10-min pauses; stress 5 s late, 2 spreads in, 1 more out).  10 % risk per trade, position capped
at 100 x the balance in notional (lot x price) - the account and the selection use the cap.  Binance rows with open
interest 0 are treated as missing.

Selection: pass = >= 40 trades, PF >= 1.3, R > 0 in Jan-Mar and in Apr-Jun, stress PF >= 1.15, max drawdown at 10 %
better than -35 %.  Pick = most passing neighbours (every knob one step), then the highest Jan-Jun balance at 10 %,
then the shallower drawdown.  None passing -> the same without the drawdown rule -> else the highest R (info only).
Luck check: the same grid on fake events (every signal moved 1-14 days inside Jan-Jun, same direction), 3 seeds; the
pick counts as better than luck only if its Jan-Jun R beats the best fake setting meeting every rule except drawdown.
Success on a test period: >= 20 trades, R > 0, PF >= 1.3, drawdown at 10 % better than -35 %.  Version 1 is run on
2025 in the same call, for comparison.
"""
from __future__ import annotations

import itertools
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numba as nb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "telegram_news" / "agents"))
import common as C  # noqa: E402

BIN = ROOT / "data" / "btc"
EXN = ROOT / "data" / "ticks_exness" / "BTCUSDm"
OUT = ROOT / "results" / "btc_liq" / "v2"
PERIODS = {"build": ("2025-12-01", "2026-07-01", "2026-01-01"),     # (load from, to, trade from)
           "test": ("2026-05-01", "2026-11-01", "2026-07-01"),
           "exam": ("2024-12-01", "2025-12-01", "2025-01-01")}
SEALED = {"test": [f"2026-{m:02d}" for m in range(7, 11)], "exam": [f"2025-{m:02d}" for m in range(1, 12)] + ["2024-12"]}
HALVES = (("2026-01-01", "2026-04-01"), ("2026-04-01", "2026-07-01"))
_ALLOW: set = set()
DAY = 86400
RISK, CAP, MAXOPEN = 0.10, 100.0, 0.30

SIG = dict(x=[0.2, 0.3, 0.5, 0.7, 1.0], y=[0.2, 0.3, 0.5, 0.8], w=[1, 2], late=["any", "same"], flow=["any", "confirm"],
           depth=["none", "thin"])
ENTRY = ["mkt", "lim0.5", "lim1"]
MANAGE = {"none": (np.nan, np.nan), "be": (1.0, np.nan), "trail1": (1.0, 1.0), "trail2": (1.0, 2.0)}
EXITS = dict(stop=[1.5, 2, 3, 5, 8], target=[0.5, 1, 1.5, 2, 3, None], timer=[120, 300, 600, 900, 1800, 3600],
             manage=list(MANAGE))
POS = [1, 3]
V1 = dict(x=0.7, y=0.3, w=1, late="any", flow="any", depth="none", entry="mkt", stop=5, target=2, timer=300,
          manage="none", pos=1)


def months(a, b):
    out, m = [], pd.Period(a[:7], "M")
    while str(m) < b[:7]:
        out.append(str(m))
        m += 1
    return out


def _check(ms):
    for name, sealed in SEALED.items():
        if name not in _ALLOW and any(m in sealed for m in ms):
            raise RuntimeError(f"{name} months are sealed: only final_run('{name}') may read them")


# ------------------------------------------------------------------ data
class Data:
    def __init__(self, period: str):
        a, b, self.trade_from = PERIODS[period]
        ms = months(a, b)
        _check(ms)
        parts = [dict(np.load(BIN / "binance_1s" / f"{m}.npz")) for m in ms]
        z = {k: np.concatenate([p[k] for p in parts]) for k in ("t", "c", "bq", "sq")}
        self.t0, t1 = int(pd.Timestamp(a, tz="UTC").timestamp()), int(pd.Timestamp(b, tz="UTC").timestamp())
        self.n = t1 - self.t0
        keep = (z["t"] >= self.t0) & (z["t"] < t1)
        i = z["t"][keep] - self.t0
        c = np.full(self.n, np.nan)
        c[i] = z["c"][keep]
        self.c = pd.Series(c).ffill().bfill().to_numpy()
        bq, sq = np.zeros(self.n), np.zeros(self.n)
        bq[i], sq[i] = z["bq"][keep], z["sq"][keep]
        self.CB, self.CS = np.r_[0.0, np.cumsum(bq)], np.r_[0.0, np.cumsum(sq)]
        nm = self.n // 60
        mc = self.c[np.arange(1, nm + 1) * 60 - 1]
        mv = pd.Series(np.r_[np.nan, np.abs(np.diff(mc))]).rolling(60, min_periods=30).mean().to_numpy()
        sm = np.arange(self.n) // 60 - 1
        self.vol = np.where(sm >= 0, mv[np.clip(sm, 0, nm - 1)], np.nan)
        m = pd.read_csv(BIN / "metrics.csv.gz", parse_dates=["create_time"])
        m = m[(m.create_time >= pd.Timestamp(a)) & (m.create_time < pd.Timestamp(b))].sort_values("create_time")
        m = m.drop_duplicates("create_time").reset_index(drop=True)
        self.mts = m.create_time.astype("datetime64[s]").astype("int64").to_numpy()
        oi = m.sum_open_interest.to_numpy(float)
        oi[~(oi > 0)] = np.nan
        self.oi = oi
        dps = []
        for mo in ms:
            f = BIN / "bookdepth" / f"{mo}.parquet"
            if f.exists():
                dps.append(pd.read_parquet(f))
        d = pd.concat(dps).sort_values("time")
        self.dts = d.time.astype("datetime64[s]").astype("int64").to_numpy()
        self.dup, self.ddn = d["d+1.0"].to_numpy(float), d["d-1.0"].to_numpy(float)
        tparts = [dict(np.load(EXN / f"{mo}.npz")) for mo in ms]
        tk = {k: np.concatenate([p[k] for p in tparts]) for k in tparts[0]}
        o = np.argsort(tk["t"], kind="stable")
        tk = {k: v[o] for k, v in tk.items()}
        keep = np.r_[True, np.diff(tk["t"]) > 0] & (tk["t"] < t1)
        self.tk = {k: v[keep] for k, v in tk.items()}
        self.gaps = np.flatnonzero(np.diff(self.tk["t"]) >= C.GAP).astype(np.int64)

    def depth_ratio(self, ts, d):
        k = np.searchsorted(self.dts, ts - 5, side="right") - 1
        kk = np.clip(k, 0, len(self.dts) - 1)
        r = np.where(d > 0, self.dup[kk] / self.ddn[kk], self.ddn[kk] / self.dup[kk])
        return np.where((k < 0) | (ts - self.dts[kk] > 300), np.nan, r)

    def signals(self, x, y, w, late, flow, depth):
        """-> (signal ts, direction) for every 5-min mark meeting the conditions (signal known 60 s after the mark)."""
        ts, oi = self.mts, self.oi
        r = np.arange(w, len(ts))
        ok = (ts[r] - ts[r - w] == 300 * w)
        doi = (oi[r] / oi[r - w] - 1) * 100
        ii = ts[r] - self.t0
        iw = ii - 300 * w
        sig = ts[r] + 60
        isg = sig - self.t0
        ok &= (iw >= 0) & (isg < self.n) & np.isfinite(doi)
        ii, iw, isg = np.clip(ii, 0, self.n - 1), np.clip(iw, 0, self.n - 1), np.clip(isg, 1, self.n - 1)
        dp = (self.c[ii] / self.c[iw] - 1) * 100
        d = np.sign(dp).astype(int)
        cond = ok & (doi <= -x) & (np.abs(dp) >= y) & np.isfinite(self.vol[isg]) & (self.vol[isg] > 0)
        if late == "same":
            cond &= d * (self.c[isg - 1] - self.c[ii]) >= 0
        if flow == "confirm":
            net = (self.CB[ii + 1] - self.CB[iw + 1]) - (self.CS[ii + 1] - self.CS[iw + 1])
            cond &= d * net > 0
        if depth == "thin":
            cond &= self.depth_ratio(sig, d) <= 0.8
        sel = np.flatnonzero(cond)
        keep = sig[sel] >= int(pd.Timestamp(self.trade_from, tz="UTC").timestamp()) - 4 * 3600
        return sig[sel][keep], d[sel][keep]


# ------------------------------------------------------------------ numba engine (same rules as common.py)
@nb.njit(cache=True)
def _next_close(T, gaps, i):
    k = np.searchsorted(gaps, i)
    return gaps[k] if k < len(gaps) else len(T) - 1


@nb.njit(cache=True)
def nb_exit(T, bf, bl, bmin, bmax, af, al, amin, amax, gaps, j, fill, d, stop_dist, tp_r, hold, be_at, trail, stress):
    n = len(T)
    sp0 = af[j] - bf[j]
    sd = max(stop_dist, 3 * sp0)
    end = _next_close(T, gaps, j)
    if hold > 0:
        k_end = min(np.searchsorted(T, T[j] + hold), end + 1)
    else:
        k_end = end + 1
    timer = hold > 0 and k_end <= end
    sl = fill - d * sd
    has_tp = not np.isnan(tp_r)
    tp = fill + d * tp_r * sd if has_tp else 0.0
    use_be = not np.isnan(be_at)
    use_tr = not np.isnan(trail)
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
            if d > 0:
                best = max(best, fav)
            else:
                best = min(best, fav)
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
def nb_entry(T, bf, af, amin, bmax, gaps, sig_ts, d, kind, vol, stress):
    """kind 0 = market; 1 / 2 = limit 0.5 / 1 x vol back from the Exness mid, live 180 s.  -> (j, fill) or (-1, 0)"""
    lat = 5 if stress else 2
    k = 2.0 if stress else 1.0
    ts = sig_ts + lat
    i = np.searchsorted(T, ts)
    if i >= len(T) or T[i] - ts > 10:
        return -1, 0.0
    if kind == 0:
        sp = af[i] - bf[i]
        return i, (af[i] if d > 0 else bf[i]) + d * k * sp
    back = 0.5 if kind == 1 else 1.0
    px = 0.5 * (af[i] + bf[i]) - d * back * vol
    end = _next_close(T, gaps, i)
    w = min(np.searchsorted(T, T[i] + 180), end + 1)
    for x in range(i + 1, w):
        sp = af[x] - bf[x]
        if d > 0 and amin[x] <= px - k * sp:
            return x, px
        if d < 0 and bmax[x] >= px + k * sp:
            return x, px
    return -1, 0.0


def exit_list():
    return [dict(zip(EXITS, e)) for e in itertools.product(*EXITS.values())]


EXL = exit_list()


@nb.njit(cache=True)
def nb_outcomes(T, bf, bl, bmin, bmax, af, al, amin, amax, gaps, sig, dirs, vols, kind, stops, tps, holds, bes, trs,
                stress):
    """every event x every exit -> entry ts, exit ts, r, stop distance, entry price (nan r = no trade)."""
    ne, nx = len(sig), len(stops)
    ent = np.zeros((ne, nx), np.int64)
    ext = np.zeros((ne, nx), np.int64)
    rr = np.full((ne, nx), np.nan)
    sds = np.zeros((ne, nx))
    pxs = np.zeros((ne, nx))
    for e in range(ne):
        j, fill = nb_entry(T, bf, af, amin, bmax, gaps, sig[e], dirs[e], kind, vols[e], stress)
        if j < 0:
            continue
        for q in range(nx):
            kx, r, sd = nb_exit(T, bf, bl, bmin, bmax, af, al, amin, amax, gaps, j, fill, dirs[e], stops[q] * vols[e],
                                tps[q], holds[q], bes[q], trs[q], stress)
            ent[e, q], ext[e, q], rr[e, q], sds[e, q], pxs[e, q] = T[j], T[min(kx, len(T) - 1)], r, sd, fill
    return ent, ext, rr, sds, pxs


@nb.njit(cache=True)
def nb_account(ent, ext, rr, sds, pxs, maxpos, risk, cap, maxopen, split_ts, start_ts, end_ts):
    """events in signal order (rows of the outcome arrays, one exit column).  Stake = risk x balance at entry, lot
    capped at cap x balance / price, P&L at exit, open risk <= maxopen x balance, at most maxpos open, one at a time if
    maxpos == 1.  -> n, R, gross win, gross loss, R before split, R after split, final, dd, max lot"""
    bal, peak, dd = 1000.0, 1000.0, 0.0
    o_exit = np.zeros(8, np.int64)
    o_lot = np.zeros(8)
    o_sd = np.zeros(8)
    o_r = np.zeros(8)
    o_stake = np.zeros(8)
    o_on = np.zeros(8, np.bool_)
    n = 0
    R = gw = gl = r1 = r2 = 0.0
    maxlot = 0.0
    for e in range(len(rr)):
        if np.isnan(rr[e]) or ent[e] < start_ts or ent[e] >= end_ts:
            continue
        # close positions that exited before this entry (in exit order)
        while True:
            best, bk = -1, 0
            for s in range(8):
                if o_on[s] and o_exit[s] <= ent[e] and (best < 0 or o_exit[s] < best):
                    best, bk = o_exit[s], s
            if best < 0:
                break
            bal += o_lot[bk] * o_sd[bk] * o_r[bk]
            if bal < 0:
                bal = 0.0
            o_on[bk] = False
            if bal > peak:
                peak = bal
            if peak > 0 and bal / peak - 1 < dd:
                dd = bal / peak - 1
        cnt, risk_open = 0, 0.0
        for s in range(8):
            if o_on[s]:
                cnt += 1
                risk_open += o_stake[s]
        if cnt >= maxpos or bal <= 0:
            continue
        st = risk * bal
        if risk_open + st > maxopen * bal + 1e-9:
            continue
        lot = st / sds[e]
        lim = cap * bal / pxs[e]
        if lot > lim:
            lot = lim
        for s in range(8):
            if not o_on[s]:
                o_on[s], o_exit[s], o_lot[s], o_sd[s], o_r[s], o_stake[s] = True, ext[e], lot, sds[e], rr[e], lot * sds[e]
                break
        if lot > maxlot:
            maxlot = lot
        n += 1
        R += rr[e]
        if rr[e] > 0:
            gw += rr[e]
        else:
            gl -= rr[e]
        if ent[e] < split_ts:
            r1 += rr[e]
        else:
            r2 += rr[e]
    while True:
        best, bk = -1, 0
        for s in range(8):
            if o_on[s] and (best < 0 or o_exit[s] < best):
                best, bk = o_exit[s], s
        if best < 0:
            break
        bal += o_lot[bk] * o_sd[bk] * o_r[bk]
        if bal < 0:
            bal = 0.0
        o_on[bk] = False
        if bal > peak:
            peak = bal
        if peak > 0 and bal / peak - 1 < dd:
            dd = bal / peak - 1
    return n, R, gw, gl, r1, r2, bal, dd, maxlot


def exit_arrays():
    stops = np.array([x["stop"] for x in EXL], float)
    tps = np.array([np.nan if x["target"] is None else x["target"] for x in EXL], float)
    holds = np.array([x["timer"] for x in EXL], np.int64)
    bes = np.array([MANAGE[x["manage"]][0] for x in EXL], float)
    trs = np.array([MANAGE[x["manage"]][1] for x in EXL], float)
    return stops, tps, holds, bes, trs


def outcomes(D: Data, sig, dirs, kind, stress, exl_idx=None):
    tk = D.tk
    vols = D.vol[np.clip(sig - D.t0, 0, D.n - 1)]
    stops, tps, holds, bes, trs = exit_arrays()
    if exl_idx is not None:
        stops, tps, holds, bes, trs = (a[exl_idx] for a in (stops, tps, holds, bes, trs))
    return nb_outcomes(tk["t"], tk["bid_first"], tk["bid_last"], tk["bid_min"], tk["bid_max"], tk["ask_first"],
                       tk["ask_last"], tk["ask_min"], tk["ask_max"], D.gaps, sig.astype(np.int64),
                       dirs.astype(np.int64), vols, kind, stops, tps, holds, bes, trs, stress)


def summarize(res, risk_note=""):
    n, R, gw, gl, r1, r2, bal, dd, maxlot = res
    return dict(n=int(n), R=float(R), pf=float(gw / gl) if gl > 0 else (99.0 if gw > 0 else 0.0), h1R=float(r1),
                h2R=float(r2), usd=float(bal), dd=float(dd), max_lot=float(maxlot))


def describe(c) -> str:
    t = "no target" if c["target"] is None else f"target {c['target']}R"
    return (f"OI fall >= {c['x']} % & move >= {c['y']} % over {5 * c['w']} min, late={c['late']}, flow={c['flow']}, "
            f"depth={c['depth']}; entry {c['entry']}; stop {c['stop']} vol, {t}, out after {c['timer'] // 60} min, "
            f"manage {c['manage']}; {'one trade at a time' if c['pos'] == 1 else 'up to 3 trades'}")


def run_setting(D: Data, c: dict, a: str, b: str, risk=RISK, stress=False, trades=False):
    """one setting on [a, b) -> summary (and the trade list)."""
    sig, d = D.signals(c["x"], c["y"], c["w"], c["late"], c["flow"], c["depth"])
    q = next(i for i, x in enumerate(EXL) if all(x[k] == c[k] for k in EXITS))
    ent, ext, rr, sds, pxs = outcomes(D, sig, d, ENTRY.index(c["entry"]), stress, exl_idx=np.array([q]))
    ta, tb = int(pd.Timestamp(a, tz="UTC").timestamp()), int(pd.Timestamp(b, tz="UTC").timestamp())
    res = nb_account(ent[:, 0], ext[:, 0], rr[:, 0], sds[:, 0], pxs[:, 0], c["pos"], risk, CAP, MAXOPEN, tb, ta, tb)
    out = summarize(res)
    if trades:
        ok = ~np.isnan(rr[:, 0]) & (ent[:, 0] >= ta) & (ent[:, 0] < tb)
        out["signals"] = pd.DataFrame(dict(sig_ts=sig[ok], dir=d[ok], entry_ts=ent[ok, 0], exit_ts=ext[ok, 0],
                                           r=rr[ok, 0], sd=sds[ok, 0], entry_px=pxs[ok, 0]))
    return out


def final_run(period: str, picks: dict) -> dict:
    """ONE run of the frozen settings on a sealed period ('test' = Jul-Oct 2026, 'exam' = Jan-Nov 2025)."""
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"{period}.json"
    if f.exists():
        raise RuntimeError(f"final_run('{period}') has already been run")
    _ALLOW.add(period)
    D = Data(period)
    a, b = PERIODS[period][2], PERIODS[period][1]
    res = {}
    for name, c in picks.items():
        m = {f"{int(rk * 100)}%": run_setting(D, c, a, b, risk=rk) for rk in (0.10, 0.05, 0.02, 0.01)}
        ms = run_setting(D, c, a, b, stress=True)
        full = run_setting(D, c, a, b, trades=True)
        tr = full.pop("signals")
        ok = m["10%"]["n"] >= 20 and m["10%"]["R"] > 0 and m["10%"]["pf"] >= 1.3 and m["10%"]["dd"] > -0.35
        month = pd.to_datetime(tr.entry_ts, unit="s").dt.strftime("%Y-%m")
        res[name] = dict(cfg=c, desc=describe(c), result=m, stress=ms, success=bool(ok),
                         month_R=tr.groupby(month).r.agg(["size", "sum"]).round(2).to_dict("index"),
                         trades=tr.to_dict("records"))
    f.write_text(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(timespec="seconds"), period=period,
                                 results=res), indent=1, default=float))
    return res
