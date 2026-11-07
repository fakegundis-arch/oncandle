"""Bitcoin liquidation bot: signals from Binance USD-M BTCUSDT data, trades on Exness BTCUSDm (the user's broker).
PROTOCOL (fixed before any result, Nov 7 2026).  BUILD on Jan 1 - Jun 30 2026 only; ONE test on Jul 1 - Oct 31 2026.

Data (binance_data.py, exness_ticks.py): Binance 1-second taker buy / sell volume and prices, 5-minute open interest,
~30-second order-book depth (+/-0.2 .. 5 %); Exness BTCUSDm 1-second bid / ask.  Files from 2026-07 on can only be
read inside final_test() (the loaders raise otherwise).  December 2025 is look-back only.

When a signal is known (Binance second s is complete at s + 1; a 5-minute open-interest value at its time + 60 s; a
depth snapshot at its time + 5 s) the bot sends a market order on Exness 2 s later (agents/common.py rules: real
ask / bid + 1 spread; stop fixed at entry, >= 3 spreads; stop before target; flat at the last quote before a >= 10-min
pause; stress = 5 s late, 2 spreads in, 1 more out).  One position at a time; 10 % of the balance risked per trade.
"vol" = mean |1-minute change| of the Binance price over the 60 minutes before the signal.

Signal families (all knobs searched on Jan-Jun):
  A  CASCADE (ride): over the last W s the net taker SELL (BUY) volume >= k x the normal volume for W s (24-h mean)
     and the price fell (rose) >= m vol -> sell (buy).  W {10, 30, 60}, k {2, 4, 8}, m {1, 2, 3}.
  B  FLUSH FADE: the same cascade test, then wait until the price has made no new low (high) for D s (within 10 min),
     then buy (sell).  W {30, 60, 180}, k {2, 4, 8}, m {2, 3, 5}, D {15, 60, 180}.
  C  LIQUIDATION MAP: every 5 min, a heatmap of estimated liquidation prices: each open-interest increase adds the same
     amount of new longs and shorts at that 5-min average price, split over 10x / 25x / 50x / 100x leverage
     (30 / 30 / 25 / 15 %), liquidating at price x (1 -/+ 1/L + 0.5 %); an open-interest fall shrinks every level in
     proportion; a level the price trades through is removed.  If the short liquidations within +d % above the price
     are >= q x the long liquidations within -d % below (and >= s % of open interest), buy (sell in the mirror case);
     dir "toward" = toward the bigger cluster, "away" = the opposite.  d {0.5, 1, 2}, q {1.5, 3, 6}, s {0.5, 2},
     dir {toward, away}.
  D  OPEN-INTEREST DROP: a 5-minute open-interest fall >= x % while the price moved >= y % -> "fade" or "follow" the
     move.  x {0.3, 0.7, 1.5}, y {0.3, 0.7, 1.5}, dir {fade, follow}.
  Depth filter for every family: none, or "thin" = order-book depth within 1 % on the side the trade moves into
  <= 0.8 x the other side.  A / B use a 15-min cooldown between events.
  Exits for every family: stop {1, 2, 3, 5} vol, target {1, 2, 4 R, none}, out after {5, 15, 60, 240} min.

Selection (Jan-Jun 2026): pass = >= 40 trades, PF >= 1.3, R > 0 in Jan-Mar and in Apr-Jun, stress PF >= 1.15, max
drawdown at 10 % better than -35 %.  Pick = most passing neighbours (every knob of the family one step), then shallower
drawdown, then higher R.  If nothing passes: the same pick without the drawdown rule; if still nothing, the highest-R
setting gets an information-only test.  LUCK CHECK: the same grid on fake events (every event moved by a random
1-14 days inside Jan-Jun, same direction), 3 seeds; the pick counts as better than luck only if its Jan-Jun R beats
the best fake setting (meeting every rule except drawdown) of every seed.
TEST once, Jul 1 - Oct 31 2026: success = >= 20 trades, R > 0, PF >= 1.3, drawdown at 10 % better than -35 %;
reported at 10 / 5 / 2 / 1 % risk.  Not modelled: Exness swap on positions held over the daily rollover (holds are at
most 4 h).
"""
from __future__ import annotations

import itertools
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "telegram_news" / "agents"))
import common as C  # noqa: E402

C.CONTRACT["btc"] = 1.0                        # Exness BTCUSD: 1 lot = 1 BTC
BIN = ROOT / "data" / "btc"
EXN = ROOT / "data" / "ticks_exness" / "BTCUSDm"
OUT = ROOT / "results" / "btc_liq"
START = "2025-12-01"
BUILD = ("2026-01-01", "2026-07-01")
HALVES = {"jan-mar": ("2026-01-01", "2026-04-01"), "apr-jun": ("2026-04-01", "2026-07-01")}
TEST = ("2026-07-01", "2026-11-01")
_ALLOW_TEST = False
DAY = 86400

FAMILIES = {
    "A": dict(W=[10, 30, 60], k=[2, 4, 8], m=[1, 2, 3], depth=["none", "thin"]),
    "B": dict(W=[30, 60, 180], k=[2, 4, 8], m=[2, 3, 5], D=[15, 60, 180], depth=["none", "thin"]),
    "C": dict(d=[0.5, 1, 2], q=[1.5, 3, 6], s=[0.5, 2], dir=["toward", "away"], depth=["none", "thin"]),
    "D": dict(x=[0.3, 0.7, 1.5], y=[0.3, 0.7, 1.5], dir=["fade", "follow"], depth=["none", "thin"]),
}
EXITS = dict(stop=[1, 2, 3, 5], target=[1, 2, 4, None], H=[300, 900, 3600, 14400])
LEV = [(10, 0.30), (25, 0.30), (50, 0.25), (100, 0.15)]
MM = 0.005


# ------------------------------------------------------------------ loaders (refuse the test months)
def _months(a: str, b: str) -> list[str]:
    out, m = [], pd.Period(a[:7], "M")
    while str(m) < b[:7]:
        out.append(str(m))
        m += 1
    return out


def _check(month: str):
    if month >= "2026-07" and not _ALLOW_TEST:
        raise RuntimeError(f"{month} is a test month: only final_test() may read it")


def load_binance(upto: str) -> dict:
    """regular 1-second grid from START to `upto` (exclusive): close (carried forward), taker buy / sell qty."""
    ms = _months(START, upto)
    for m in ms:
        _check(m)
    parts = [dict(np.load(BIN / "binance_1s" / f"{m}.npz")) for m in ms]
    z = {k: np.concatenate([p[k] for p in parts]) for k in ("t", "c", "bq", "sq")}
    t0, t1 = int(pd.Timestamp(START, tz="UTC").timestamp()), int(pd.Timestamp(upto, tz="UTC").timestamp())
    keep = (z["t"] >= t0) & (z["t"] < t1)
    i = z["t"][keep] - t0
    n = t1 - t0
    c = np.full(n, np.nan)
    c[i] = z["c"][keep]
    c = pd.Series(c).ffill().bfill().to_numpy()
    bq, sq = np.zeros(n), np.zeros(n)
    bq[i], sq[i] = z["bq"][keep], z["sq"][keep]
    return dict(t0=t0, n=n, c=c, bq=bq, sq=sq)


def load_exness(upto: str) -> dict:
    ms = _months(START, upto)
    for m in ms:
        _check(m)
    parts = [dict(np.load(EXN / f"{m}.npz")) for m in ms]
    tk = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    t1 = int(pd.Timestamp(upto, tz="UTC").timestamp())
    keep = tk["t"] < t1
    return {k: v[keep] for k, v in tk.items()}


def load_metrics(upto: str) -> pd.DataFrame:
    if upto > "2026-07-01" and not _ALLOW_TEST:
        raise RuntimeError("test months: only final_test() may read them")
    m = pd.read_csv(BIN / "metrics.csv.gz", parse_dates=["create_time"])
    m = m[m.create_time < pd.Timestamp(upto)].reset_index(drop=True)
    m["ts"] = m.create_time.astype("datetime64[s]").astype("int64")
    return m


def load_depth(upto: str) -> pd.DataFrame:
    for mo in _months(START, upto):
        _check(mo)
    parts = []
    for mo in _months(START, upto):
        f = BIN / "bookdepth" / f"{mo}.parquet"
        if f.exists():
            parts.append(pd.read_parquet(f))
    d = pd.concat(parts).sort_values("time").reset_index(drop=True)
    d = d[d.time < pd.Timestamp(upto)]
    d["ts"] = d.time.astype("datetime64[s]").astype("int64")
    return d.reset_index(drop=True)


# ------------------------------------------------------------------ market features
class Market:
    def __init__(self, upto: str):
        b = load_binance(upto)
        self.t0, self.n, self.c = b["t0"], b["n"], b["c"]
        self.CB = np.r_[0.0, np.cumsum(b["bq"])]
        self.CS = np.r_[0.0, np.cumsum(b["sq"])]
        # vol: mean |1-min change| over the 60 minutes before each second (last complete minute)
        nm = self.n // 60
        mc = self.c[np.arange(1, nm + 1) * 60 - 1]
        ad = np.r_[np.nan, np.abs(np.diff(mc))]
        mv = pd.Series(ad).rolling(60, min_periods=30).mean().to_numpy()
        sec_min = np.arange(self.n) // 60 - 1
        self.vol = np.where(sec_min >= 0, mv[np.clip(sec_min, 0, nm - 1)], np.nan)
        # normal volume per second: mean of the prior 24 h
        CV = self.CB + self.CS
        i = np.arange(self.n)
        lo = np.maximum(i - DAY, 0)
        self.base = (CV[i] - CV[lo]) / np.maximum(i - lo, 1)
        self.base[i < 6 * 3600] = np.nan
        self.metrics = load_metrics(upto)
        self.depth = load_depth(upto)
        self.dts = self.depth.ts.to_numpy()
        self._map = None

    def idx(self, ts):
        return np.asarray(ts) - self.t0

    # depth ratio on the side a trade in direction d moves into (asks for a buy), vs the other side; known at ts
    def depth_ratio(self, ts, d):
        k = np.searchsorted(self.dts, np.asarray(ts) - 5, side="right") - 1
        up, dn = self.depth["d+1.0"].to_numpy(), self.depth["d-1.0"].to_numpy()
        kk = np.clip(k, 0, len(up) - 1)
        r = np.where(np.asarray(d) > 0, up[kk] / dn[kk], dn[kk] / up[kk])
        stale = (k < 0) | (np.asarray(ts) - self.dts[kk] > 300)
        return np.where(stale, np.nan, r)

    # cascade condition at the end of second index i (complete), side -1 = selling cascade
    def cascade(self, W, k, m):
        i = np.arange(W, self.n)
        net_s = (self.CS[i + 1] - self.CS[i + 1 - W]) - (self.CB[i + 1] - self.CB[i + 1 - W])
        dp = self.c[i] - self.c[i - W]
        thr = k * self.base[i] * W
        v = self.vol[i]
        sell = (net_s >= thr) & (dp <= -m * v)
        buy = (-net_s >= thr) & (dp >= m * v)
        return i, sell, buy

    @staticmethod
    def _cool(idx, cool):
        out, last = [], -10**12
        for x in idx:
            if x - last >= cool:
                out.append(x)
                last = x
        return np.array(out, dtype=np.int64)

    def events_A(self, W, k, m):
        i, sell, buy = self.cascade(W, k, m)
        ev = self._cool(np.flatnonzero(sell | buy), 900)
        d = np.where(sell[ev], -1, 1)
        return (i[ev] + 1 + self.t0), d                         # known at the start of the next second

    def events_B(self, W, k, m, D):
        i, sell, buy = self.cascade(W, k, m)
        ev = self._cool(np.flatnonzero(sell | buy), 900)
        ts, ds = [], []
        for e in ev:
            s0, side = int(i[e]), (-1 if sell[e] else 1)
            seg = self.c[s0: min(s0 + 601, self.n)]
            if len(seg) < D + 2:
                continue
            ext = np.minimum.accumulate(seg) if side < 0 else np.maximum.accumulate(seg)
            new = np.r_[True, (seg[1:] < ext[:-1]) if side < 0 else (seg[1:] > ext[:-1])]
            last_new = np.maximum.accumulate(np.where(new, np.arange(len(seg)), 0))
            ok = np.flatnonzero(np.arange(len(seg)) - last_new >= D)
            if len(ok):
                ts.append(s0 + int(ok[0]) + 1 + self.t0)
                ds.append(-side)
        return np.array(ts, dtype=np.int64), np.array(ds, dtype=int)

    def _five_min(self):
        m = self.metrics
        ts = m.ts.to_numpy()
        ii = np.clip(self.idx(ts), 0, self.n - 1)
        i5 = np.clip(ii - 300, 0, self.n - 1)
        ok = (ts - 300 >= self.t0) & (ts < self.t0 + self.n)
        return m, ts, ii, i5, ok

    def events_D(self, x, y, dirn):
        m, ts, ii, i5, ok = self._five_min()
        oi = m.sum_open_interest.to_numpy(float)
        doi = np.r_[np.nan, oi[1:] / oi[:-1] - 1] * 100
        gap_ok = np.r_[False, np.diff(ts) == 300]
        dp = (self.c[ii] / self.c[i5] - 1) * 100
        sel = ok & gap_ok & (doi <= -x) & (np.abs(dp) >= y)
        d = np.sign(dp[sel]).astype(int) * (1 if dirn == "follow" else -1)
        return ts[sel] + 60, d

    def liq_map(self):
        """per 5-minute row: long liquidations within -d % and short liquidations within +d % (BTC), d in 0.5/1/2."""
        if self._map is not None:
            return self._map
        m, ts, ii, i5, ok = self._five_min()
        oi = m.sum_open_interest.to_numpy(float)
        lo_b, step = np.log(20000.0), 0.0005
        nb = int((np.log(400000.0) - lo_b) / step) + 1
        L, S = np.zeros(nb), np.zeros(nb)
        bin_of = lambda p: np.clip(((np.log(p) - lo_b) / step).astype(int), 0, nb - 1)
        res = {f"{w}_{d:g}": np.full(len(ts), np.nan) for w in ("L", "S") for d in (0.5, 1, 2)}
        for r in range(1, len(ts)):
            if not ok[r] or ts[r] - ts[r - 1] != 300:
                continue
            a, b = i5[r], ii[r]
            seg = self.c[a: b + 1]
            vwap, lo, hi = seg.mean(), seg.min(), seg.max()
            d_oi = oi[r] - oi[r - 1]
            if d_oi < 0 and oi[r - 1] > 0:
                f = 1 + d_oi / oi[r - 1]
                L *= f
                S *= f
            # levels the price traded through in this bucket are liquidated
            L[bin_of(np.array([lo]))[0]:] = 0.0
            S[: bin_of(np.array([hi]))[0] + 1] = 0.0
            if d_oi > 0:
                for lev, w in LEV:
                    L[bin_of(np.array([vwap * (1 - 1 / lev + MM)]))[0]] += d_oi * w
                    S[bin_of(np.array([vwap * (1 + 1 / lev - MM)]))[0]] += d_oi * w
            p = self.c[b]
            for d in (0.5, 1, 2):
                res[f"L_{d:g}"][r] = L[bin_of(np.array([p * (1 - d / 100)]))[0]: bin_of(np.array([p]))[0] + 1].sum()
                res[f"S_{d:g}"][r] = S[bin_of(np.array([p]))[0]: bin_of(np.array([p * (1 + d / 100)]))[0] + 1].sum()
        self._map = (ts, oi, res)
        return self._map

    def events_C(self, d, q, s, dirn):
        ts, oi, res = self.liq_map()
        Lv, Sv = res[f"L_{float(d):g}"], res[f"S_{float(d):g}"]
        with np.errstate(divide="ignore", invalid="ignore"):
            up = (Sv >= q * Lv) & (Sv >= s / 100 * oi)
            dn = (Lv >= q * Sv) & (Lv >= s / 100 * oi)
        sel = np.flatnonzero((up | dn) & np.isfinite(Lv))
        d_ = np.where(up[sel], 1, -1) * (1 if dirn == "toward" else -1)
        return ts[sel] + 60, d_

    def events(self, fam: str, c: dict):
        sig = {k: c[k] for k in FAMILIES[fam] if k != "depth"}
        ts, d = getattr(self, "events_" + fam)(**{("dirn" if k == "dir" else k): v for k, v in sig.items()})
        if c["depth"] == "thin" and len(ts):
            r = self.depth_ratio(ts, d)
            keep = r <= 0.8
            ts, d = ts[keep], d[keep]
        return ts, d


# ------------------------------------------------------------------ trades
def exit_list():
    return [dict(zip(EXITS, e)) for e in itertools.product(*EXITS.values())]


def outcomes(mk: Market, tk: dict, ts: np.ndarray, d: np.ndarray, stress=False) -> dict:
    """(decision ts, dir) -> {exit index: (entry_ts, exit_ts, r)} for every exit setting."""
    ex = exit_list()
    out = {}
    T = tk["t"]
    for s, di in zip(ts.tolist(), d.tolist()):
        if (s, di) in out:
            continue
        v = mk.vol[s - mk.t0] if 0 <= s - mk.t0 < mk.n else np.nan
        if not np.isfinite(v) or v <= 0:
            out[(s, di)] = None
            continue
        e = C.market_entry(tk, s, di, stress=stress)
        if e is None:
            out[(s, di)] = None
            continue
        j, fill = e
        row = {}
        for k, x in enumerate(ex):
            kx, r, sd = C.exit_trade(tk, j, fill, di, x["stop"] * v, tp_r=x["target"], max_hold_s=x["H"],
                                     stress=stress)
            row[k] = (int(T[j]), int(T[min(kx, len(T) - 1)]), float(r), float(sd))
        out[(s, di)] = row
    return out


def simulate(ts, d, oc: dict, k: int) -> pd.DataFrame:
    rows, busy = [], -1
    for s, di in zip(ts.tolist(), d.tolist()):
        if s <= busy:
            continue
        o = oc.get((s, di))
        if o is None:
            continue
        et, xt, r, sd = o[k]
        busy = xt
        rows.append((s, et, xt, di, r, sd))
    return pd.DataFrame(rows, columns=["sig_ts", "entry_ts", "exit_ts", "dir", "r", "sd"])


def quick(t: pd.DataFrame, a: str, b: str, risk=0.10) -> dict:
    """one position at a time -> the balance compounds trade by trade (same result as common.account)."""
    ta, tb = pd.Timestamp(a, tz="UTC").timestamp(), pd.Timestamp(b, tz="UTC").timestamp()
    r = t.r[(t.entry_ts >= ta) & (t.entry_ts < tb)].to_numpy(float) if len(t) else np.zeros(0)
    eq = np.cumprod(1 + risk * r) if len(r) else np.array([1.0])
    gw, gl = r[r > 0].sum(), -r[r < 0].sum()
    return dict(n=len(r), R=float(r.sum()), pf=float(gw / gl) if gl > 0 else (99.0 if gw > 0 else 0.0),
                win=float((r > 0).mean()) if len(r) else 0.0, usd=float(1000 * eq[-1]),
                dd=float((eq / np.maximum.accumulate(np.maximum(eq, 1.0)) - 1).min()))


def build_metrics(t, ts_) -> dict:
    m = quick(t, *BUILD)
    h1, h2 = quick(t, *HALVES["jan-mar"]), quick(t, *HALVES["apr-jun"])
    ms = quick(ts_, *BUILD)
    ok_nodd = m["n"] >= 40 and m["pf"] >= 1.3 and h1["R"] > 0 and h2["R"] > 0 and ms["pf"] >= 1.15
    return dict(m, h1R=h1["R"], h2R=h2["R"], stress_pf=ms["pf"], stress_R=ms["R"], ok_nodd=ok_nodd,
                ok=ok_nodd and m["dd"] > -0.35)


def shift_events(ts, d, seed, a=BUILD[0], b=BUILD[1]):
    """fake events: every event moved by a random 1-14 days (either way), wrapped inside [a, b)."""
    rng = np.random.default_rng(seed)
    lo, hi = int(pd.Timestamp(a, tz="UTC").timestamp()), int(pd.Timestamp(b, tz="UTC").timestamp())
    sh = rng.integers(DAY, 14 * DAY, len(ts)) * rng.choice([-1, 1], len(ts))
    x = (np.asarray(ts) - lo + sh) % (hi - lo) + lo
    o = np.argsort(x, kind="stable")
    return x[o], np.asarray(d)[o]


def describe(fam, c) -> str:
    ex = f"stop {c['stop']} vol, target {c['target']}R" if c["target"] else f"stop {c['stop']} vol, no target"
    ex += f", out after {c['H'] // 60} min"
    sig = ", ".join(f"{k}={c[k]}" for k in FAMILIES[fam])
    return f"{fam}: {sig}; {ex}"


def final_test(picks: dict, tag: str = "btc_liq") -> dict:
    """ONE run on Jul 1 - Oct 31 2026.  picks: {name: (family, cfg)}.  Refuses a second run."""
    global _ALLOW_TEST
    OUT.mkdir(parents=True, exist_ok=True)
    fpath = OUT / f"{tag}_test.json"
    if fpath.exists():
        raise RuntimeError("final_test has already been run")
    _ALLOW_TEST = True
    mk = Market(TEST[1])
    tk = load_exness(TEST[1])
    a = int(pd.Timestamp(TEST[0], tz="UTC").timestamp())
    res = {}
    for name, (fam, c) in picks.items():
        ts, d = mk.events(fam, c)
        keep = ts >= a - 4 * 3600
        ts, d = ts[keep], d[keep]
        ex = exit_list()
        k = next(i for i, x in enumerate(ex) if all(x[q] == c[q] for q in EXITS))
        t = simulate(ts, d, outcomes(mk, tk, ts, d), k)
        tsx = simulate(ts, d, outcomes(mk, tk, ts, d, stress=True), k)
        t["inst"], tsx["inst"] = "btc", "btc"
        m = {f"{int(rk * 100)}%": C.metrics(t, *TEST, risk=rk) for rk in (0.10, 0.05, 0.02, 0.01)}
        ms = C.metrics(tsx, *TEST)
        m10 = m["10%"]
        ok = m10["n"] >= 20 and m10["R"] > 0 and m10["pf"] >= 1.3 and m10["dd"] > -0.35
        tt = t[t.entry_ts >= a]
        month = pd.to_datetime(tt.entry_ts, unit="s").dt.strftime("%Y-%m")
        res[name] = dict(family=fam, cfg=c, desc=describe(fam, c), test=m, test_stress=ms, success=ok,
                         month_R=tt.groupby(month).r.agg(["size", "sum"]).round(2).to_dict("index"),
                         trades=tt.to_dict("records"))
    fpath.write_text(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(timespec="seconds"), results=res),
                                indent=1, default=float))
    return res
