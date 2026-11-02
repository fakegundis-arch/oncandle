"""Strategy families (agent B). Each is make_trades(cfg, cost, m1)."""
from __future__ import annotations

import numpy as np
import pandas as pd

import lib

_BARS: dict = {}


def B(m1, tf, off):
    key = (len(m1), m1.index[-1], tf, off)
    if key not in _BARS:
        _BARS[key] = lib.bars(m1, tf, off)
    return _BARS[key]


def _sig(b, mask, d, stop, tgt, typ=0, lvl=None, exp_bars=0, tf=60, hold_bars=0, t_end=None):
    s = pd.DataFrame({"t_act": b.tclose[mask].to_numpy(), "dir": d[mask], "stop": stop[mask],
                      "tgt": np.full(mask.sum(), float(tgt)), "type": typ})
    if lvl is not None:
        s["lvl"] = lvl[mask]
    s["t_exp"] = s.t_act + pd.Timedelta(minutes=tf * exp_bars) - pd.Timedelta(minutes=1) if exp_bars else s.t_act
    if t_end is not None:
        s["t_end"] = t_end[mask]
    elif hold_bars:
        s["t_end"] = s.t_act + pd.Timedelta(minutes=tf * hold_bars)
    else:
        s["t_end"] = pd.NaT
    return s[np.isfinite(s.stop) & (s.stop > 0)]


def d1_trend(m1, times, n):
    """Sign of (last COMPLETED UTC day's close - EMA(n) of daily closes), for each timestamp in `times`."""
    dc = m1.close.resample("1D").last().dropna()
    sg = np.sign(dc - dc.ewm(span=n, adjust=False).mean())
    day = pd.DatetimeIndex(times).normalize()
    pos = dc.index.searchsorted(day, side="left") - 1          # last day strictly before the current day
    out = np.where(pos >= 0, sg.to_numpy()[np.maximum(pos, 0)], 0)
    return out.astype(int)


# ---------------------------------------------------------------- T: Donchian breakout (trend following)
def donchian(cfg, cost, m1):
    tf, off = cfg["tf"], cfg.get("off", 0)
    b = B(m1, tf, off)
    a = lib.atr(b, 14).to_numpy()
    c = b.close.to_numpy()
    N = cfg["N"]
    hi = b.high.rolling(N).max().shift().to_numpy(); lo = b.low.rolling(N).min().shift().to_numpy()
    up = c > hi; dn = c < lo
    fresh_up = up & ~np.r_[False, up[:-1]]; fresh_dn = dn & ~np.r_[False, dn[:-1]]
    d = np.where(fresh_up, 1, np.where(fresh_dn, -1, 0))
    if cfg.get("ema"):
        e = b.close.ewm(span=cfg["ema"], adjust=False).mean().to_numpy()
        d = np.where((d == 1) & (c > e) | (d == -1) & (c < e), d, 0)
    if cfg.get("d1ema"):
        d = np.where(d == d1_trend(m1, b.tclose, cfg["d1ema"]), d, 0)
    if cfg.get("er"):   # efficiency ratio filter over the channel length
        er = (b.close - b.close.shift(N)).abs() / b.close.diff().abs().rolling(N).sum()
        d = np.where(er.to_numpy() >= cfg["er"], d, 0)
    if cfg.get("side"):
        d = np.where(d == cfg["side"], d, 0)
    stop = cfg["k"] * a
    s = _sig(b, d != 0, d, stop, cfg["rr"], tf=tf, hold_bars=cfg.get("hold", 0))
    return lib.simulate(m1, s, cost, be_r=cfg.get("be", 0), be_buf=cfg.get("be_buf", 0.05),
                        trail_r=cfg.get("trail", 0), cool_losses=cfg.get("cl", 0), cool_min=cfg.get("cm", 0),
                        max_per_day=cfg.get("mpd", 99))


# ---------------------------------------------------------------- M: RSI pullback in trend (mean reversion)
def rsi_pull(cfg, cost, m1):
    tf, off = cfg["tf"], cfg.get("off", 0)
    b = B(m1, tf, off)
    a = lib.atr(b, 14).to_numpy()
    c = b.close.to_numpy()
    r = lib.rsi(b.close, cfg["rn"]).to_numpy()
    lo_, hi_ = cfg["lo"], 100 - cfg["lo"]
    L = (r < lo_) & np.r_[False, r[:-1] >= lo_] if cfg.get("cross", 1) else (r < lo_)
    S = (r > hi_) & np.r_[False, r[:-1] <= hi_] if cfg.get("cross", 1) else (r > hi_)
    tr = cfg.get("trend", 0)
    if tr:
        e = b.close.ewm(span=tr, adjust=False).mean().to_numpy()
        if cfg.get("against", 0):
            L &= c < e; S &= c > e
        else:
            L &= c > e; S &= c < e
    d = np.where(L, 1, np.where(S, -1, 0))
    if cfg.get("side"):
        d = np.where(d == cfg["side"], d, 0)
    stop = cfg["k"] * a
    s = _sig(b, d != 0, d, stop, cfg["rr"], tf=tf, hold_bars=cfg.get("hold", 0))
    return lib.simulate(m1, s, cost, be_r=cfg.get("be", 0), be_buf=cfg.get("be_buf", 0.05))


# ---------------------------------------------------------------- R: run of same-colour candles, fade
def run_fade(cfg, cost, m1):
    tf, off = cfg["tf"], cfg.get("off", 0)
    b = B(m1, tf, off)
    a = lib.atr(b, 14).to_numpy()
    o, c = b.open.to_numpy(), b.close.to_numpy()
    col = np.sign(c - o)
    n = cfg["run"]
    s = pd.Series(col)
    upn = s.rolling(n).apply(lambda x: (x > 0).all(), raw=True).to_numpy() == 1
    dnn = s.rolling(n).apply(lambda x: (x < 0).all(), raw=True).to_numpy() == 1
    move = (b.close - b.open.shift(n - 1)).to_numpy()
    big = np.abs(move) >= cfg.get("mv", 0) * a
    d = np.where(upn & big, -1, np.where(dnn & big, 1, 0))
    if cfg.get("follow"):
        d = -d
    stop = cfg["k"] * a
    sg = _sig(b, d != 0, d, stop, cfg["rr"], tf=tf, hold_bars=cfg.get("hold", 0))
    return lib.simulate(m1, sg, cost, be_r=cfg.get("be", 0), be_buf=cfg.get("be_buf", 0.05))


# ---------------------------------------------------------------- S: session range breakout / fade (M1 levels)
from numba import njit as _njit


@_njit(cache=True)
def _first_trigger(o, h, l, starts, ends, hi, lo, mode, cost, thru):
    """For each day: first minute in [start, end) where the long or short order triggers. mode 1 = stop entries at hi
    (long) / lo (short); mode -1 = limit fades: short limit at hi, long limit at lo. Returns (index, dir)."""
    nd = len(starts)
    oi = np.full(nd, -1, np.int64); od = np.zeros(nd, np.int64)
    for q in range(nd):
        for k in range(starts[q], ends[q]):
            if mode == 1:
                if h[k] + cost >= hi[q]:
                    oi[q] = k; od[q] = 1
                    break
                if l[k] <= lo[q]:
                    oi[q] = k; od[q] = -1
                    break
            else:
                if h[k] >= hi[q] + thru:
                    oi[q] = k; od[q] = -1
                    break
                if l[k] + cost <= lo[q] - thru:
                    oi[q] = k; od[q] = 1
                    break
    return oi, od


_LOC: dict = {}


def _local(m1, tz):
    key = (len(m1), m1.index[-1], tz)
    if key not in _LOC:
        loc = m1.index.tz_localize("UTC").tz_convert(tz)
        mod = np.asarray(loc.hour * 60 + loc.minute)
        day = np.asarray(loc.year * 10000 + loc.month * 100 + loc.day)
        _LOC[key] = (mod, day)
    return _LOC[key]


def d1_atr(m1, times, n=14):
    """ATR(n) of COMPLETED UTC days, for each timestamp."""
    d = m1.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    a = lib.atr(d, n)
    pos = d.index.searchsorted(pd.DatetimeIndex(times).normalize(), side="left") - 1
    return np.where(pos >= 0, a.to_numpy()[np.maximum(pos, 0)], np.nan)


def session(cfg, cost, m1):
    tz = cfg.get("tz", "UTC")
    mod, day = _local(m1, tz)
    r0, r1, e1, x = cfg["r0"], cfg["r1"], cfg["e1"], cfg["x"]
    P = lib.prep(m1)
    o, h, l = P["o"], P["h"], P["l"]
    idx = m1.index
    inr = (mod >= r0) & (mod < r1)
    df = pd.DataFrame({"day": day, "h": np.where(inr, h, np.nan), "l": np.where(inr, l, np.nan),
                       "cnt": inr.astype(int)})
    g = df.groupby("day").agg(hi=("h", "max"), lo=("l", "min"), cnt=("cnt", "sum"))
    pos = np.arange(len(idx))
    ent = (mod >= r1) & (mod < e1)
    st = pd.Series(np.where(ent, pos, np.nan)).groupby(day).agg(["min", "max"])
    g = g.join(st, how="inner").dropna()
    g = g[g.cnt >= (r1 - r0) * 0.8]
    starts = g["min"].to_numpy(np.int64); ends = g["max"].to_numpy(np.int64) + 1
    width = (g.hi - g.lo).to_numpy()
    da = d1_atr(m1, idx[starts])
    ok = np.isfinite(da) & (width >= cfg.get("wmin", 0) * da) & (width <= cfg.get("wmax", 99) * da)
    starts, ends, width, da = starts[ok], ends[ok], width[ok], da[ok]
    hi = g.hi.to_numpy()[ok]; lo = g.lo.to_numpy()[ok]
    mode = cfg["mode"]
    buf = cfg.get("buf", 0.0) * da
    if mode == 1:
        Lh, Ll = hi + buf, lo - buf
    else:
        Lh, Ll = hi + buf, lo - buf
    ti, td = _first_trigger(o, h, l, starts, ends, Lh, Ll, mode, cost, lib.THRU)
    k = ti >= 0
    ti, td, width, da, Lh, Ll = ti[k], td[k], width[k], da[k], Lh[k], Ll[k]
    lvl = np.where(td == 1, Lh, Ll) if mode == 1 else np.where(td == 1, Ll, Lh)
    if cfg.get("stop_atr"):
        stop = cfg["stop_atr"] * da
    else:
        stop = cfg["sf"] * width
    stop = np.maximum(stop, cfg.get("min_stop", 1.0))
    # exit time: today's local x
    t_act = idx[ti]
    loc_day = t_act.tz_localize("UTC").tz_convert(tz).normalize()
    t_end = (loc_day + pd.to_timedelta(x, unit="min")).tz_convert("UTC").tz_localize(None)
    t_end = np.where(t_end > t_act, t_end, t_end + pd.Timedelta(days=1))
    s = pd.DataFrame({"t_act": t_act, "dir": td, "type": 1 if mode == 1 else 2, "lvl": lvl, "stop": stop,
                      "tgt": float(cfg["rr"]), "t_exp": t_act, "t_end": pd.DatetimeIndex(t_end)})
    if cfg.get("side"):
        s = s[s.dir == cfg["side"]]
    return lib.simulate(m1, s, cost, be_r=cfg.get("be", 0), be_buf=cfg.get("be_buf", 0.05))


def pdhl(cfg, cost, m1):
    """Previous (completed UTC) day's high / low as levels; entries between local e0 and e1 (tz), breakout (mode 1, stop
    orders beyond the level +buf) or fade (mode -1, limits beyond the level +buf). Stop stop_atr x D1 ATR, target rr,
    time exit at local x."""
    tz = cfg.get("tz", "UTC")
    mod, day = _local(m1, tz)
    P = lib.prep(m1)
    o, h, l = P["o"], P["h"], P["l"]
    idx = m1.index
    d = m1.resample("1D").agg({"high": "max", "low": "min"}).dropna()
    pos = np.arange(len(idx))
    ent = (mod >= cfg["e0"]) & (mod < cfg["e1"])
    st = pd.Series(np.where(ent, pos, np.nan)).groupby(day).agg(["min", "max"]).dropna()
    starts = st["min"].to_numpy(np.int64); ends = st["max"].to_numpy(np.int64) + 1
    t0 = idx[starts]
    p = d.index.searchsorted(t0.normalize(), side="left") - 1
    ok = p >= 0
    starts, ends, p = starts[ok], ends[ok], p[ok]
    hi = d.high.to_numpy()[p]; lo = d.low.to_numpy()[p]
    da = d1_atr(m1, idx[starts])
    ok = np.isfinite(da)
    # require price to start inside yesterday's range
    c0 = o[starts]
    ok &= (c0 < hi) & (c0 > lo)
    starts, ends, hi, lo, da = starts[ok], ends[ok], hi[ok], lo[ok], da[ok]
    buf = cfg.get("buf", 0.0) * da
    mode = cfg["mode"]
    ti, td = _first_trigger(o, h, l, starts, ends, hi + buf, lo - buf, mode, cost, lib.THRU)
    k = ti >= 0
    ti, td, da, hi, lo, buf = ti[k], td[k], da[k], hi[k], lo[k], buf[k]
    if mode == 1:
        lvl = np.where(td == 1, hi + buf, lo - buf)
    else:
        lvl = np.where(td == 1, lo - buf, hi + buf)
    stop = np.maximum(cfg["stop_atr"] * da, 1.0)
    t_act = idx[ti]
    loc_day = t_act.tz_localize("UTC").tz_convert(tz).normalize()
    t_end = (loc_day + pd.to_timedelta(cfg["x"], unit="min")).tz_convert("UTC").tz_localize(None)
    t_end = np.where(t_end > t_act, t_end, t_end + pd.Timedelta(days=1))
    s = pd.DataFrame({"t_act": t_act, "dir": td, "type": 1 if mode == 1 else 2, "lvl": lvl, "stop": stop,
                      "tgt": float(cfg["rr"]), "t_exp": t_act, "t_end": pd.DatetimeIndex(t_end)})
    return lib.simulate(m1, s, cost, be_r=cfg.get("be", 0), be_buf=cfg.get("be_buf", 0.05))
