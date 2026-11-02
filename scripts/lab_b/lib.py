"""Agent B lab helpers: M1-exact simulator with realistic fills, bar building with grid offsets, evaluation helpers.

Fills: bars are BID. Longs buy at ask = bid + cost and sell at bid; shorts sell at bid and buy back at ask.
Orders: market (next minute open), stop-entry (breakout), limit (fills only when price trades THROUGH the level).
Exits: stop before target within a minute; entry minute may only stop out; flat before weekend / holiday closes;
time exit; break-even; optional trailing. Entries in the first 15 min after a reopen (pause > 30 min) are cancelled,
as are entries that gap through the stop. One position at a time.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from numba import njit  # noqa: E402

HERE = Path(__file__).resolve().parent
THRU = 0.05   # a limit must be traded through by this much to fill


def load_train():
    return pd.read_pickle(HERE / "train.pkl")


_PREP: dict = {}


def prep(m1: pd.DataFrame, flat_min: int = 10, noentry_min: int = 60, long_gap: int = 120):
    """Arrays + masks for an M1 frame (cached by identity of first/last index and length).
    flat[k]   : position must be closed at the open of bar k (within flat_min minutes of a scheduled close, i.e. the
                last bar before a pause of more than `long_gap` minutes: weekends and holiday early closes).
    noentry[k]: no new entries (first 15 min after any pause > 30 min, or within noentry_min of a scheduled close)."""
    key = (len(m1), m1.index[0], m1.index[-1], flat_min, noentry_min, long_gap)
    if key in _PREP:
        return _PREP[key]
    idx = m1.index
    t = idx.to_numpy("datetime64[m]").astype(np.int64)
    o, h, l, c = (m1[x].to_numpy(np.float64) for x in ("open", "high", "low", "close"))
    gap_after = np.concatenate([np.diff(t), [10 ** 6]])
    # time of the next scheduled close for every bar
    close_t = np.where(gap_after > long_gap, t, np.iinfo(np.int64).max)
    nxt = np.minimum.accumulate(close_t[::-1])[::-1]
    to_close = nxt - t                      # minutes until the last bar before a long pause
    flat = to_close <= flat_min
    first = np.concatenate([[True], np.diff(t) > 30])
    last_open = np.maximum.accumulate(np.where(first, t, np.iinfo(np.int64).min))
    reopen = (t - last_open) < 15
    noentry = reopen | (to_close <= noentry_min)
    out = dict(o=o, h=h, l=l, c=c, t=t, flat=flat, noentry=noentry, idx=idx)
    _PREP[key] = out
    return out


def bars(m1: pd.DataFrame, minutes: int, offset: int = 0) -> pd.DataFrame:
    """Bars of `minutes` built from M1 with the grid shifted by `offset` minutes. Index = bar START.
    A bar is usable only after its close time = start + minutes (column 'tclose')."""
    b = m1.resample(f"{minutes}min", offset=f"{offset}min").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    b["tclose"] = b.index + pd.Timedelta(minutes=minutes)
    return b


def atr(b: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = b.close.shift()
    tr = pd.concat([b.high - b.low, (b.high - pc).abs(), (b.low - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def rsi(s: pd.Series, n: int) -> pd.Series:
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


@njit(cache=True)
def _sim(o, h, l, c, t, flat, noentry, s_k, s_exp, s_dir, s_type, s_lvl, s_stop, s_tgt, s_tend, cost, thru,
         be_r, be_buf, trail_r, max_per_day, dayk, stop_after_loss, cool_losses, cool_min):
    """s_type: 0 market at open of s_k; 1 stop-entry at s_lvl; 2 limit at s_lvl (order live from s_k to s_exp incl.).
    s_stop: stop distance in price (>0). s_tgt: target in R (<=0: none). s_tend: absolute minute time (t units) at
    which to exit at the bar open if still open (very large = none)."""
    n = len(o); ns = len(s_k)
    oi = np.zeros(ns, np.int64); ox = np.zeros(ns, np.int64); od = np.zeros(ns, np.int64); orr = np.zeros(ns)
    nt = 0; busy = -1; cur_day = -1; day_n = 0; day_lost = False; streak = 0; cool_until = -1
    for q in range(ns):
        k0 = s_k[q]
        if k0 <= busy or k0 >= n:
            continue
        d = s_dir[q]
        # find fill
        j = -1; entry = 0.0
        for k in range(k0, min(s_exp[q] + 1, n)):
            if k <= busy:
                continue
            if s_type[q] == 0:
                j = k; entry = o[k] + cost if d == 1 else o[k]
                break
            elif s_type[q] == 1:
                L = s_lvl[q]
                if d == 1:
                    if h[k] + cost >= L:
                        j = k; entry = max(o[k] + cost, L)
                        break
                else:
                    if l[k] <= L:
                        j = k; entry = min(o[k], L)
                        break
            else:
                L = s_lvl[q]
                if d == 1:
                    if l[k] + cost <= L - thru:
                        j = k; entry = min(o[k] + cost, L)
                        break
                else:
                    if h[k] >= L + thru:
                        j = k; entry = max(o[k], L)
                        break
        if j < 0:
            continue
        if noentry[j] or flat[j] or t[j] < cool_until:
            continue
        if dayk[j] != cur_day:
            cur_day = dayk[j]; day_n = 0; day_lost = False
        if day_n >= max_per_day or (stop_after_loss and day_lost):
            continue
        R = s_stop[q]
        if not (R > 0):
            continue
        stop = entry - d * R
        # entry that gaps through the stop: for stop/limit orders the stop is relative to the fill, so it cannot;
        # for market orders likewise. (Level-based stops are converted to distances by the caller, which drops
        # signals whose open is already beyond the stop level.)
        tgt = entry + d * s_tgt[q] * R if s_tgt[q] > 0 else (1e18 if d == 1 else -1e18)
        best = entry; moved = False; px = 0.0; k = j; done = False
        while k < n:
            bo = o[k] if d == 1 else o[k] + cost
            bh = h[k] if d == 1 else h[k] + cost
            bl = l[k] if d == 1 else l[k] + cost
            if k > j and (flat[k] or t[k] >= s_tend[q]):
                px = bo; done = True
                break
            if d == 1:
                if bl <= stop:
                    px = min(bo, stop) if k > j else stop
                    done = True
                    break
                if k > j and bh >= tgt:
                    px = max(bo, tgt); done = True
                    break
                if k > j:
                    best = max(best, bh)
            else:
                if bh >= stop:
                    px = max(bo, stop) if k > j else stop
                    done = True
                    break
                if k > j and bl <= tgt:
                    px = min(bo, tgt); done = True
                    break
                if k > j:
                    best = min(best, bl)
            if be_r > 0 and not moved and d * (best - entry) >= be_r * R:
                stop = entry + d * be_buf * R
                moved = True
            if trail_r > 0 and moved:
                ts = best - d * trail_r * R
                if d * (ts - stop) > 0:
                    stop = ts
            k += 1
        if not done:
            k = n - 1
            px = c[k] if d == 1 else c[k] + cost
        r = d * (px - entry) / R
        oi[nt] = j; ox[nt] = k; od[nt] = d; orr[nt] = r; nt += 1
        busy = k
        day_n += 1
        if r < 0:
            day_lost = True
            streak += 1
            if cool_losses > 0 and streak >= cool_losses:
                cool_until = t[k] + cool_min
                streak = 0
        else:
            streak = 0
    return oi[:nt], ox[:nt], od[:nt], orr[:nt]


def simulate(m1, sig: pd.DataFrame, cost: float, *, be_r=0.0, be_buf=0.0, trail_r=0.0, max_per_day=99,
             stop_after_loss=False, cool_losses=0, cool_min=0, flat_min=10, noentry_min=60) -> pd.DataFrame:
    """sig columns: t_act (Timestamp the order becomes live = signal bar close), dir, type (0/1/2), lvl, stop (price
    distance), tgt (R), t_exp (Timestamp order expires), t_end (Timestamp to time-exit; NaT = none)."""
    P = prep(m1, flat_min, noentry_min)
    idx = P["idx"]
    if len(sig) == 0:
        return pd.DataFrame({"entry_time": pd.DatetimeIndex([]), "exit_time": pd.DatetimeIndex([]), "dir": [], "r": []})
    sig = sig.sort_values("t_act", kind="mergesort")
    s_k = idx.searchsorted(sig.t_act.to_numpy()).astype(np.int64)
    exp = sig.t_exp.to_numpy() if "t_exp" in sig else sig.t_act.to_numpy()
    s_exp = (idx.searchsorted(exp, side="right") - 1).astype(np.int64)
    s_exp = np.maximum(s_exp, s_k) if ("type" not in sig) else np.where(sig.type.to_numpy() == 0, s_k, s_exp)
    tend = sig.t_end.to_numpy() if "t_end" in sig else np.full(len(sig), np.datetime64("NaT"))
    tend_m = pd.DatetimeIndex(tend).to_numpy("datetime64[m]").astype(np.int64)
    tend_m = np.where(pd.isna(tend), np.iinfo(np.int64).max, tend_m)
    dayk = (idx.year * 10000 + idx.month * 100 + idx.day).to_numpy(np.int64)
    typ = sig.type.to_numpy(np.int64) if "type" in sig else np.zeros(len(sig), np.int64)
    lvl = sig.lvl.to_numpy(np.float64) if "lvl" in sig else np.zeros(len(sig))
    oi, ox, od, orr = _sim(P["o"], P["h"], P["l"], P["c"], P["t"], P["flat"], P["noentry"], s_k, s_exp,
                           sig.dir.to_numpy(np.int64), typ, lvl, sig.stop.to_numpy(np.float64),
                           sig.tgt.to_numpy(np.float64), tend_m, float(cost), THRU, float(be_r), float(be_buf),
                           float(trail_r), int(max_per_day), dayk, bool(stop_after_loss), int(cool_losses),
                           int(cool_min))
    return pd.DataFrame({"entry_time": idx[oi], "exit_time": idx[ox], "dir": od, "r": orr})


# ---------------------------------------------------------------- evaluation
import agent_lab as A  # noqa: E402


def ev(make_trades, cfg, m1, cost=0.25):
    t = make_trades(cfg, cost, m1)
    t = t[t.entry_time >= "2026-01-01"]
    return A.evaluate_train(t), t


def full(make_trades, cfg, m1):
    m25, t25 = ev(make_trades, cfg, m1, 0.25)
    m40, _ = ev(make_trades, cfg, m1, 0.40)
    p = A.passes_train(m25, m40)
    return dict(n=m25["n"], R=round(m25["R"], 1), pf=round(m25["pf"], 2), win=round(m25["win"], 2),
                pfwb=round(m25["pf_wo_best"], 2), pf40=round(m40["pf"], 2), dd=round(m25["dd"], 3),
                q1=round(m25["jan-mar_pf"], 2), q2=round(m25["apr-jun_pf"], 2), streak=m25["max_losing_streak"],
                usd=round(m25["usd"]), ok=p["all"]), t25


def short(m):
    return {k: m[k] for k in ("n", "R", "pf", "win", "pfwb", "pf40", "dd", "q1", "q2", "streak", "usd", "ok")}
