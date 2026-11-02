"""Supply & demand v3 (family premium_discount; built by an explorer agent on Jan-Apr 2026 only and confirmed by an
independent auditor, scripts/sd_v3_eval.py protocol). Premium / discount supply & demand for gold (M1 bid bars, UTC).

Rules (see RULES text in RESULT.json for the plain-language version):
  * Zones: base of 1..n_cap small candles (range <= base_atr x ATR14) + one leg-out candle (range >= leg_min x ATR14,
    body >= half its range, closing beyond the base) on `tf`-minute bars (backtester.sd._find). Demand: proximal =
    highest base body, distal = lowest low of base+leg; supply mirrored. Known at the leg-out close.
  * `phases` > 1: zones are detected on `phases` separate `tf`-minute candle series whose start times are shifted by
    tf/phases minutes (BEST: 30-minute candles at :00/:30, :10/:40, :20/:50) and pooled - this removes most of the
    dependence on one arbitrary candle alignment.
  * Session of formation: the leg-out candle must start inside London (07-11 UTC) and/or New York (12-16 UTC).
  * One limit order per zone at the entry level (proximal, or a fraction into the zone), alive for `age_h` hours.
    The zone is used once: its FIRST touch either trades or kills it.
  * Premium / discount at the touch minute: reference range = previous completed trading day (D1), previous completed
    trading week (W1) or the latest confirmed swing high / swing low (fractal on `sw_tf` bars, k bars each side).
    Demand only if the entry level <= low + pd_f x (high - low) (discount half for pd_f = 0.5); supply only if the
    entry level >= high - pd_f x (high - low) (premium half).
  * Active hours: the touch minute's UTC hour must be in [act0, act1); never on Friday at/after 20:30 UTC, when any
    open trade is also closed at the market (weekend-gap guard).
  * Optional volatility band: percentile of the last completed H1 ATR(14) among the previous `vol_n` H1 ATR values
    (past only) must be in [vol_lo, vol_hi].
  * Stop `buf` x zone ATR beyond the distal line (at least `min_stop` $ from the fill); target `rr` R; optional
    partial exit (`part_frac` of the position at `part_R` R, then stop to break-even) and optional break-even after
    `be` R; optional time exit after `max_hold_h` hours (market exit at the next minute's open).
  * Fills: longs buy at ask = bid + cost when the ask trades through the level (fill at the open if it opens below),
    shorts sell at the bid when the bid trades through. Touches in the first 15 min after a reopen (pause > 30 min)
    or opening beyond the distal line cancel the zone. Stop before target in a minute; fill minute may only stop out.
  * One position at a time; at most `max_day` trades per trading day; optionally no new trade after a losing trade
    on the same trading day. Trading day = calendar date of (UTC time + 2 h) (the daily break is 21-22/22-23 UTC).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtester.engine import njit  # noqa: E402
from backtester import sd as SD  # noqa: E402
from backtester import indicators as ind  # noqa: E402

SESS = {"L": ((7, 11),), "NY": ((12, 16),), "LNY": ((7, 11), (12, 16)), "ALL": ((0, 24),)}
TRADE_FROM = "2026-01-01"  # earlier bars are warm-up / zone history only: no entries are generated before this


# ----------------------------------------------------------------------------------------------------------- helpers
def resample(m1: pd.DataFrame, minutes: int, offset: int = 0) -> pd.DataFrame:
    return m1.resample(f"{minutes}min", offset=f"{offset}min" if offset else None).agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


def trading_day(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return (idx + pd.Timedelta(hours=2)).normalize()


def _period_ref(m1: pd.DataFrame, key: pd.DatetimeIndex):
    """High / low of the previous completed period for every minute (period label per minute = key)."""
    g = pd.DataFrame({"h": m1.high.to_numpy(), "l": m1.low.to_numpy(), "k": key})
    agg = g.groupby("k").agg(h=("h", "max"), l=("l", "min")).sort_index()
    prev = agg.shift(1)
    hi = prev.h.reindex(key).to_numpy(); lo = prev.l.reindex(key).to_numpy()
    return hi, lo


def _swing_ref(m1: pd.DataFrame, minutes: int, k: int):
    """Latest confirmed fractal swing high / low on `minutes` bars: bar i's high > the k bars before and >= the k bars
    after; known once bar i+k has closed."""
    b = resample(m1, minutes)
    h = b.high.to_numpy(); l = b.low.to_numpy(); n = len(b)
    conf_t = (b.index + pd.Timedelta(minutes=minutes)).to_numpy()
    sh_t, sh_v, sl_t, sl_v = [], [], [], []
    for i in range(k, n - k):
        if h[i] > h[i - k:i].max() and h[i] >= h[i + 1:i + k + 1].max():
            sh_t.append(conf_t[i + k]); sh_v.append(h[i])
        if l[i] < l[i - k:i].min() and l[i] <= l[i + 1:i + k + 1].min():
            sl_t.append(conf_t[i + k]); sl_v.append(l[i])
    t = m1.index.to_numpy()
    out = []
    for ts, vs in ((sh_t, sh_v), (sl_t, sl_v)):
        ts = np.array(ts, dtype=t.dtype); vs = np.array(vs)
        p = np.searchsorted(ts, t, side="right") - 1
        out.append(np.where(p >= 0, vs[np.maximum(p, 0)], np.nan))
    a, c = out
    return np.fmax(a, c), np.fmin(a, c)


def ref_range(m1: pd.DataFrame, ref: str):
    if ref == "none":
        return np.full(len(m1), 1e9), np.full(len(m1), -1e9)
    if ref == "D1":
        return _period_ref(m1, trading_day(m1.index))
    if ref == "W1":
        d = trading_day(m1.index)
        return _period_ref(m1, d - pd.to_timedelta(d.dayofweek, unit="D"))
    if ref.startswith("SW"):  # SW<minutes>_<k>
        mins, k = ref[2:].split("_")
        return _swing_ref(m1, int(mins), int(k))
    raise ValueError(ref)


def vol_pct(m1: pd.DataFrame, n: int) -> np.ndarray:
    """Per minute: percentile rank of the last COMPLETED H1 ATR(14) among itself and the previous n-1 H1 values."""
    b = resample(m1, 60)
    a = ind.atr(b, 14)
    pr = a.rolling(n, min_periods=n // 2).rank(pct=True).to_numpy()
    conf_t = (b.index + pd.Timedelta(minutes=60)).to_numpy()
    p = np.searchsorted(conf_t, m1.index.to_numpy(), side="right") - 1
    return np.where(p >= 0, pr[np.maximum(p, 0)], np.nan)


# ----------------------------------------------------------------------------------------------------------- numba
@njit(cache=True)
def _first_touch(o, h, l, start, stop_k, d, lvl, dist, reopen, cost):
    """First minute in [start, stop_k) where the limit level trades through. -1 none, -2 cancelled (reopen window or
    opened beyond the distal line)."""
    nz = len(start)
    fi = np.full(nz, -1, np.int64); fp = np.full(nz, np.nan)
    n = len(o)
    for z in range(nz):
        for k in range(start[z], min(stop_k[z], n)):
            px = np.nan
            if d[z] == 1:
                if o[k] + cost <= lvl[z]:
                    px = o[k] + cost
                elif l[k] + cost < lvl[z]:
                    px = lvl[z]
            else:
                if o[k] >= lvl[z]:
                    px = o[k]
                elif h[k] > lvl[z]:
                    px = lvl[z]
            if px == px:
                if reopen[k] or d[z] * (px - dist[z]) <= 0:
                    fi[z] = -2
                else:
                    fi[z] = k; fp[z] = px
                break
    return fi, fp


@njit(cache=True)
def _outcomes(o, h, l, c, fi, fp, d, stop_lvl, rr, be, part_r, part_f, cost, min_stop, max_k, force):
    """Exit minute and R of each filled trade. Long exits at the bid, short exits at the ask (bid + cost)."""
    nz = len(fi)
    xi = np.full(nz, -1, np.int64); r_out = np.zeros(nz)
    n = len(o)
    for z in range(nz):
        j = fi[z]
        if j < 0:
            continue
        dz = d[z]; entry = fp[z]
        R = max(dz * (entry - stop_lvl[z]), min_stop)
        stop = entry - dz * R; tgt = entry + dz * rr * R; ptg = entry + dz * part_r * R
        best = entry; moved = False; pdone = part_f <= 0.0 or part_r <= 0.0 or part_r >= rr
        real = 0.0; rem = 1.0; px = np.nan; k = j
        while k < n:
            if dz == 1:
                bo = o[k]; bh = h[k]; bl = l[k]
            else:
                bo = o[k] + cost; bh = h[k] + cost; bl = l[k] + cost
            if (max_k > 0 and k - j >= max_k) or (k > j and force[k]):
                px = bo
                break
            if dz == 1:
                if bl <= stop:
                    px = min(bo, stop) if k > j else stop
                    break
                if k > j:
                    if not pdone and bh >= ptg:
                        real += part_f * (max(bo, ptg) - entry) / R; rem -= part_f; pdone = True
                        stop = max(stop, entry); moved = True
                    if bh >= tgt:
                        px = max(bo, tgt)
                        break
                    best = max(best, bh)
            else:
                if bh >= stop:
                    px = max(bo, stop) if k > j else stop
                    break
                if k > j:
                    if not pdone and bl <= ptg:
                        real += part_f * (entry - min(bo, ptg)) / R; rem -= part_f; pdone = True
                        stop = min(stop, entry); moved = True
                    if bl <= tgt:
                        px = min(bo, tgt)
                        break
                    best = min(best, bl)
            if be > 0 and not moved and dz * (best - entry) >= be * R:
                stop = entry
                moved = True
            k += 1
        if k >= n:
            k = n - 1
            px = c[k] if dz == 1 else c[k] + cost
        xi[z] = k
        r_out[z] = real + rem * dz * (px - entry) / R
    return xi, r_out


# ----------------------------------------------------------------------------------------------------------- stages
class Ctx:
    """Per-M1-frame cache of expensive pieces (bars, zones, references), so a search can reuse them."""

    def __init__(self, m1: pd.DataFrame):
        self.m1 = m1
        self.o = m1.open.to_numpy(np.float64); self.h = m1.high.to_numpy(np.float64)
        self.l = m1.low.to_numpy(np.float64); self.c = m1.close.to_numpy(np.float64)
        self.idx = m1.index
        self.reopen = SD.reopen_mask(m1.index)
        self.hour = m1.index.hour.to_numpy()
        self.day = trading_day(m1.index).to_numpy()
        mod = m1.index.hour.to_numpy() * 60 + m1.index.minute.to_numpy()
        # weekend guard: open trades are closed at the market from Friday 20:30 UTC, and no entries from then on
        self.force = (m1.index.dayofweek.to_numpy() == 4) & (mod >= 20 * 60 + 30)
        self._c: dict = {}

    def get(self, key, fn):
        if key not in self._c:
            self._c[key] = fn()
        return self._c[key]

    def zones(self, tf, base_atr, leg_min, n_cap, off=0):
        def f():
            b = resample(self.m1, tf, off)
            z = SD.zones(b, tf, base_atr, leg_min, n_cap)
            z["t_leg"] = z.t_make - pd.Timedelta(minutes=tf)
            z["k0"] = np.searchsorted(self.idx.to_numpy(), z.t_make.to_numpy(), side="left")
            return z
        return self.get(("z", tf, base_atr, leg_min, n_cap, off), f)

    def ref(self, ref):
        return self.get(("ref", ref), lambda: ref_range(self.m1, ref))

    def vol(self, n):
        return self.get(("vol", n), lambda: vol_pct(self.m1, n))

    def touches(self, cfg, cost):
        key = ("t", cfg["tf"], cfg["tf_off"], cfg.get("phases", 1), cfg["base_atr"], cfg["leg_min"], cfg["n_cap"], cfg["sess"], cfg["entry"],
               cfg["age_h"], cost)

        def f():
            ph = int(cfg.get("phases", 1))
            offs = [(cfg["tf_off"] + p * cfg["tf"] // ph) % cfg["tf"] for p in range(ph)]
            z = pd.concat([self.zones(cfg["tf"], cfg["base_atr"], cfg["leg_min"], cfg["n_cap"], o) for o in offs],
                          ignore_index=True)
            hr = z.t_leg.dt.hour.to_numpy()
            ok = np.zeros(len(z), bool)
            for a, b in SESS[cfg["sess"]]:
                ok |= (hr >= a) & (hr < b)
            z = z[ok]
            d = z.dir.to_numpy(np.int64); prox = z.prox.to_numpy(); dist = z.dist.to_numpy()
            lvl = prox + (dist - prox) * cfg["entry"]
            start = z.k0.to_numpy(np.int64)
            stop_k = np.searchsorted(self.idx.to_numpy(),
                                     (z.t_make + pd.Timedelta(hours=cfg["age_h"])).to_numpy(), side="left")
            fi, fp = _first_touch(self.o, self.h, self.l, start, stop_k.astype(np.int64), d, lvl, dist, self.reopen,
                                  cost)
            m = fi >= 0
            m[m] = self.idx[fi[m]] >= pd.Timestamp(TRADE_FROM)
            return dict(fi=fi[m], fp=fp[m], d=d[m], lvl=lvl[m], dist=dist[m], atr=z.atr.to_numpy()[m],
                        prox=prox[m], tmake=z.t_make.to_numpy()[m])
        return self.get(key, f)

    def outcomes(self, cfg, cost):
        key = ("o", cfg["tf"], cfg["tf_off"], cfg.get("phases", 1), cfg["base_atr"], cfg["leg_min"], cfg["n_cap"], cfg["sess"], cfg["entry"], cfg["age_h"],
               cost, cfg["buf"], cfg["min_stop"], cfg["rr"], cfg["be"], cfg["part_r"], cfg["part_f"], cfg["max_hold_h"])

        def f():
            t = self.touches(cfg, cost)
            stop_lvl = t["dist"] - t["d"] * cfg["buf"] * t["atr"]
            xi, r = _outcomes(self.o, self.h, self.l, self.c, t["fi"], t["fp"], t["d"], stop_lvl, float(cfg["rr"]),
                              float(cfg["be"]), float(cfg["part_r"]), float(cfg["part_f"]), cost,
                              float(cfg["min_stop"]), int(cfg["max_hold_h"] * 60), self.force)
            return xi, r
        return self.get(key, f)


DEFAULT = dict(tf=15, tf_off=0, phases=1, base_atr=0.6, leg_min=1.5, n_cap=4, sess="LNY", ref="D1", pd_f=0.5, act0=7, act1=20,
               vol_n=0, vol_lo=0.0, vol_hi=1.0, entry=0.0, age_h=24, buf=0.1, min_stop=1.5, rr=1.5, be=0.0,
               part_r=0.0, part_f=0.0, max_hold_h=0, max_day=1, stop_after_loss=1)


def trades_from_ctx(cfg: dict, cost: float, ctx: Ctx) -> pd.DataFrame:
    cfg = {**DEFAULT, **cfg}
    t = ctx.touches(cfg, cost)
    xi, r = ctx.outcomes(cfg, cost)
    fi = t["fi"]; d = t["d"]; lvl = t["lvl"]
    # premium / discount at the touch minute
    hi, lo = ctx.ref(cfg["ref"])
    H = hi[fi]; L = lo[fi]; f = cfg["pd_f"]
    okpd = np.where(d == 1, lvl <= L + f * (H - L), lvl >= H - f * (H - L)) & np.isfinite(H) & np.isfinite(L) & (H > L)
    if cfg["ref"] == "none":  # diagnostic baseline only (no premium / discount filter)
        okpd = np.ones(len(fi), bool)
    hr = ctx.hour[fi]
    a0, a1 = cfg["act0"], cfg["act1"]
    okh = (hr >= a0) & (hr < a1) if a0 < a1 else ((hr >= a0) | (hr < a1))
    ok = okpd & okh & (xi >= 0) & ~ctx.force[fi]
    if cfg["vol_n"] > 0 and (cfg["vol_lo"] > 0 or cfg["vol_hi"] < 1):
        v = ctx.vol(cfg["vol_n"])[fi]
        ok &= np.isfinite(v) & (v >= cfg["vol_lo"]) & (v <= cfg["vol_hi"])
    cand = np.nonzero(ok)[0]
    # newest zone first among touches in the same minute
    order = cand[np.lexsort((-t["tmake"][cand].astype(np.int64), fi[cand]))]
    last_exit = -1; cur_day = None; nday = 0; lost = False
    sel = []
    for z in order:
        if fi[z] <= last_exit:
            continue
        dd = ctx.day[fi[z]]
        if dd != cur_day:
            cur_day = dd; nday = 0; lost = False
        if nday >= cfg["max_day"] or (cfg["stop_after_loss"] and lost):
            continue
        sel.append(z); last_exit = xi[z]; nday += 1
        if r[z] < 0:
            lost = True
    sel = np.array(sel, dtype=np.int64)
    idx = ctx.idx
    return pd.DataFrame({"entry_time": idx[fi[sel]], "exit_time": idx[xi[sel]], "dir": d[sel].astype(int),
                         "r": r[sel]})


def make_trades(cfg: dict, cost: float, m1: pd.DataFrame) -> pd.DataFrame:
    """Trades (entry_time, exit_time, dir, r) built only from the given M1 bid frame."""
    return trades_from_ctx(cfg, cost, Ctx(m1))


# Search grid (ordered values; one-step neighbours move one knob by one position). be = 0.0 and part_r = 0.0 mean "off"
# and sit at the end of their lists. Knobs not listed (tf_off=0, act0=7, min_stop=1.5, part_f=0.5, max_hold_h=0,
# stop_after_loss=1, vol filter off) were fixed after early tests showed no effect or no benefit.
GRID = dict(
    tf=[15, 20, 30, 60],
    phases=[1, 2, 3, 6],
    base_atr=[0.7, 0.85, 1.0, 1.15, 1.3, 1.5],
    leg_min=[0.4, 0.6, 0.8, 1.0, 1.2, 1.4],
    n_cap=[1, 2, 3, 4, 6],
    sess=["L", "LNY", "NY"],
    entry=[0.25, 0.5, 0.75],
    age_h=[3, 6, 12, 24, 48],
    ref=["SW60_3", "SW60_5", "SW120_3", "SW240_2", "D1", "W1"],
    pd_f=[0.3, 0.4, 0.5, 0.6, 0.7],
    buf=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5],
    rr=[1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0],
    be=[0.5, 0.75, 1.0, 1.5, 2.0, 0.0],
    part_r=[0.5, 0.75, 1.0, 1.5, 0.0],
    max_day=[1, 2, 3],
    act1=[17, 20, 22],
)

BEST: dict = dict(tf=30, tf_off=0, phases=3, base_atr=1.0, leg_min=0.8, n_cap=2, sess="L", entry=0.5, age_h=12,
                  ref="D1", pd_f=0.4, act0=7, act1=17, vol_n=0, vol_lo=0.0, vol_hi=1.0, buf=0.3, min_stop=1.5,
                  rr=2.5, be=0.0, part_r=1.5, part_f=0.5, max_hold_h=0, max_day=2, stop_after_loss=1)


def neighbours(cfg: dict, grid: dict = GRID) -> list:
    out = []
    for k, vals in grid.items():
        i = vals.index(cfg[k])
        for j in (i - 1, i + 1):
            if 0 <= j < len(vals):
                out.append({**cfg, k: vals[j]})
    return out


NEIGHBOURS: list = neighbours(BEST)
