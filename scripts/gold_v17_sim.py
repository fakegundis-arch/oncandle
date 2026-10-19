"""Portfolio simulator for v17: several engines side by side (risk = % of equity at entry) plus two account-level
rules that act across engines at order time:
  cap   : total risk of open positions may not exceed cap x equity (a new trade is cut to what is left, or skipped)
  dstop : no new trades for the rest of the UTC day once the day's equity is down more than dstop
  dloss : no new trades for the rest of the UTC day once `dloss` real trades have closed at a loss that day
Also a block-bootstrap estimate of next-year drawdown from one year of trades.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtester.engine import njit  # noqa: E402


@njit(cache=True)
def sim_rules(order, n, r, eng, short, day, xday, mon, n_mon, W, SM, CAP, DST, DL):
    """Book every row of W (n_mix x n_eng risk), SM (short multipliers), CAP (open-risk cap, 0 = none),
    DST (daily stop, 0 = none) and DL (losing trades per UTC day before new entries stop, 0 = none).
    Returns final multiple, max drawdown, months up, worst month per row."""
    n_mix = W.shape[0]
    fin = np.empty(n_mix); mdd = np.empty(n_mix); up = np.empty(n_mix, np.int64); worst = np.empty(n_mix)
    stake = np.empty(n)
    mon_eq = np.empty(n_mon)
    for w in range(n_mix):
        eq = 1.0; peak = 1.0; dd = 0.0; open_risk = 0.0
        cur_day = -1; day_eq = 1.0; loss_day = -1; loss_cnt = 0
        for m in range(n_mon):
            mon_eq[m] = -1.0
        for o in order:
            if o < n:
                d = day[o]
                if d != cur_day:
                    cur_day = d; day_eq = eq
                f = W[w, eng[o]]
                if short[o]:
                    f *= SM[w, eng[o]]
                s = f * eq
                if DST[w] > 0 and eq / day_eq - 1.0 <= -DST[w]:
                    s = 0.0
                if DL[w] > 0 and loss_day == d and loss_cnt >= DL[w]:
                    s = 0.0
                if CAP[w] > 0 and s > 0:
                    room = CAP[w] * eq - open_risk
                    if room <= 0:
                        s = 0.0
                    elif s > room:
                        s = room
                stake[o] = s
                open_risk += s
            else:
                i = o - n
                if xday[i] != loss_day:
                    loss_day = xday[i]; loss_cnt = 0
                if stake[i] > 0 and r[i] < 0:
                    loss_cnt += 1
                open_risk -= stake[i]
                if open_risk < 1e-12:
                    open_risk = 0.0
                eq = eq + stake[i] * r[i]
                if eq < 0.0:
                    eq = 0.0
                if eq > peak:
                    peak = eq
                if peak > 0 and eq / peak - 1.0 < dd:
                    dd = eq / peak - 1.0
                mon_eq[mon[i]] = eq
        prev = 1.0; u = 0; wr = 0.0
        for m in range(n_mon):
            v = mon_eq[m] if mon_eq[m] >= 0 else prev
            ret = v / prev - 1.0 if prev > 0 else 0.0
            if ret > 0:
                u += 1
            if ret < wr:
                wr = ret
            prev = v
        fin[w] = eq; mdd[w] = dd; up[w] = u; worst[w] = wr
    return fin, mdd, up, worst


def prepare(t, a, b):
    """Event arrays for trades (entry_time, exit_time, r, dir, eng) entered in [a, b)."""
    x = t[(t.entry_time >= a) & (t.entry_time < b)].reset_index(drop=True)
    months = pd.period_range(a, pd.Timestamp(b) - pd.Timedelta("1D"), freq="M")
    tin = x.entry_time.to_numpy("datetime64[m]").astype(np.int64)
    tout = x.exit_time.to_numpy("datetime64[m]").astype(np.int64)
    order = np.argsort(np.concatenate((tin * 2, tout * 2 + 1)), kind="mergesort").astype(np.int64)
    mon = months.get_indexer(x.exit_time.dt.to_period("M").clip(upper=months[-1])).astype(np.int64)
    day = (tin // 1440).astype(np.int64)
    xday = (tout // 1440).astype(np.int64)
    return dict(order=order, n=len(x), r=x.r.to_numpy(np.float64), eng=x.eng.to_numpy(np.int64),
                short=(x.dir.to_numpy() == -1), day=day, xday=xday, mon=mon, n_mon=len(months), x=x)


def run(ev, W, SM, CAP, DST, DL=None):
    if DL is None:
        DL = np.zeros(len(W), np.int64)
    return sim_rules(ev["order"], ev["n"], ev["r"], ev["eng"], ev["short"], ev["day"], ev["xday"], ev["mon"],
                     ev["n_mon"], W, SM, CAP, DST, np.asarray(DL, np.int64))


def bootstrap_dd(t, w_row, sm_row, cap, dst, a, b, n_sim=400, block_days=14, horizon_days=365, seed=11, dl=0):
    """Resample [a, b) in blocks of `block_days` calendar days (all engines' trades of a block kept together, times
    shifted into a synthetic year) and return (p10, p50, p90 of max drawdown, median growth)."""
    x = t[(t.entry_time >= a) & (t.entry_time < b)].reset_index(drop=True)
    t0 = pd.Timestamp(a)
    span = (pd.Timestamp(b) - t0).days
    nb = span // block_days
    blk = ((x.entry_time - t0).dt.days // block_days).to_numpy()
    groups = [x[blk == k] for k in range(nb)]
    rng = np.random.default_rng(seed)
    need = horizon_days // block_days
    W = np.array([w_row], float); SM = np.array([sm_row], float)
    CAP = np.array([cap], float); DST = np.array([dst], float); DL = np.array([dl], np.int64)
    dds, gs = [], []
    for _ in range(n_sim):
        parts = []
        for j, k in enumerate(rng.integers(0, nb, need)):
            g = groups[k]
            if len(g) == 0:
                continue
            shift = pd.Timedelta(days=int(j * block_days - k * block_days))
            parts.append(g.assign(entry_time=g.entry_time + shift, exit_time=g.exit_time + shift))
        if not parts:
            dds.append(0.0); gs.append(1.0); continue
        y = pd.concat(parts, ignore_index=True)
        s0 = t0
        ev = prepare(y, s0, s0 + pd.Timedelta(days=need * block_days + 60))
        fin, dd, _, _ = run(ev, W, SM, CAP, DST, DL)
        dds.append(dd[0]); gs.append(fin[0])
    dds = np.array(dds)
    return float(np.percentile(dds, 10)), float(np.percentile(dds, 50)), float(np.percentile(dds, 90)), float(np.median(gs))


@njit(cache=True)
def _dd_path(order, n, r, eng, short, day, xday, w, sm, cap, dst, dl):
    """Max drawdown and final multiple of one risk row (same rules as sim_rules)."""
    stake = np.zeros(n)
    eq = 1.0; peak = 1.0; dd = 0.0; open_risk = 0.0
    cur_day = -1; day_eq = 1.0; loss_day = -1; loss_cnt = 0
    for o in order:
        if o < n:
            d = day[o]
            if d != cur_day:
                cur_day = d; day_eq = eq
            f = w[eng[o]]
            if short[o]:
                f *= sm[eng[o]]
            s = f * eq
            if dst > 0 and eq / day_eq - 1.0 <= -dst:
                s = 0.0
            if dl > 0 and loss_day == d and loss_cnt >= dl:
                s = 0.0
            if cap > 0 and s > 0:
                room = cap * eq - open_risk
                s = 0.0 if room <= 0 else min(s, room)
            stake[o] = s; open_risk += s
        else:
            i = o - n
            if xday[i] != loss_day:
                loss_day = xday[i]; loss_cnt = 0
            if stake[i] > 0 and r[i] < 0:
                loss_cnt += 1
            open_risk = max(open_risk - stake[i], 0.0)
            eq = max(eq + stake[i] * r[i], 0.0)
            peak = max(peak, eq)
            if peak > 0:
                dd = min(dd, eq / peak - 1.0)
    return eq, dd


def bootstrap_fast(t, w_row, sm_row, cap, dst, dl, a, b, n_sim=400, block_days=14, horizon_days=365, seed=11):
    """Same block bootstrap as bootstrap_dd, in numpy: (worst-decile drawdown, median drawdown, median growth)."""
    x = t[(t.entry_time >= a) & (t.entry_time < b)]
    t0 = pd.Timestamp(a)
    nb = (pd.Timestamp(b) - t0).days // block_days
    tin = ((x.entry_time - t0).dt.total_seconds() // 60).to_numpy(np.int64)
    tout = ((x.exit_time - t0).dt.total_seconds() // 60).to_numpy(np.int64)
    blk = tin // (block_days * 1440)
    cols = (x.r.to_numpy(np.float64), x.eng.to_numpy(np.int64), (x.dir.to_numpy() == -1))
    groups = [np.flatnonzero(blk == k) for k in range(nb)]
    rng = np.random.default_rng(seed)
    need = horizon_days // block_days
    w = np.asarray(w_row, float); sm = np.asarray(sm_row, float)
    dds, gs = np.empty(n_sim), np.empty(n_sim)
    for s_ in range(n_sim):
        pick = rng.integers(0, nb, need)
        idx = [groups[k] for k in pick]
        shift = np.concatenate([np.full(len(g), (j - k) * block_days * 1440, np.int64) for j, (g, k) in enumerate(zip(idx, pick))]) if idx else np.zeros(0, np.int64)
        ii = np.concatenate(idx) if idx else np.zeros(0, np.int64)
        ti, to = tin[ii] + shift, tout[ii] + shift
        n = len(ii)
        if n == 0:
            dds[s_], gs[s_] = 0.0, 1.0; continue
        order = np.argsort(np.concatenate((ti * 2, to * 2 + 1)), kind="mergesort").astype(np.int64)
        g, d = _dd_path(order, n, cols[0][ii], cols[1][ii], cols[2][ii], ti // 1440, to // 1440, w, sm, cap, dst, dl)
        dds[s_], gs[s_] = d, g
    return float(np.percentile(dds, 10)), float(np.median(dds)), float(np.median(gs))


def boot_samples(t, a, b, n_sim=400, block_days=14, horizon_days=365, seed=11):
    """Pre-draw `n_sim` block-bootstrap years from the trades in [a, b) (same draws as bootstrap_fast) and return
    their event arrays, so every risk mix can be booked on the same simulated years."""
    x = t[(t.entry_time >= a) & (t.entry_time < b)]
    t0 = pd.Timestamp(a)
    nb = (pd.Timestamp(b) - t0).days // block_days
    tin = ((x.entry_time - t0).dt.total_seconds() // 60).to_numpy(np.int64)
    tout = ((x.exit_time - t0).dt.total_seconds() // 60).to_numpy(np.int64)
    blk = tin // (block_days * 1440)
    r, eng, short = x.r.to_numpy(np.float64), x.eng.to_numpy(np.int64), (x.dir.to_numpy() == -1)
    groups = [np.flatnonzero(blk == k) for k in range(nb)]
    rng = np.random.default_rng(seed)
    need = horizon_days // block_days
    out = []
    for _ in range(n_sim):
        pick = rng.integers(0, nb, need)
        idx = [groups[k] for k in pick]
        ii = np.concatenate(idx)
        shift = np.concatenate([np.full(len(g), (j - k) * block_days * 1440, np.int64) for j, (g, k) in enumerate(zip(idx, pick))])
        ti, to = tin[ii] + shift, tout[ii] + shift
        order = np.argsort(np.concatenate((ti * 2, to * 2 + 1)), kind="mergesort").astype(np.int64)
        out.append((order, len(ii), r[ii], eng[ii], short[ii], ti // 1440, to // 1440))
    return out


def boot_p10(samples, W, SM, CAP, DST, DL):
    """Worst-decile (10th percentile) max drawdown of every risk row over pre-drawn bootstrap years."""
    dds = np.empty((len(samples), len(W)))
    mon = None
    for s, (order, n, r, eng, short, day, xday) in enumerate(samples):
        if mon is None or len(mon) < n:
            mon = np.zeros(max(n, 1), np.int64)
        _, dd, _, _ = sim_rules(order, n, r, eng, short, day, xday, mon[:n], 1, W, SM, CAP, DST, np.asarray(DL, np.int64))
        dds[s] = dd
    return np.percentile(dds, 10, axis=0)
