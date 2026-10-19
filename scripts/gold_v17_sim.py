"""Portfolio simulator for v17: several engines side by side (risk = % of equity at entry) plus two account-level
rules that act across engines at order time:
  cap   : total risk of open positions may not exceed cap x equity (a new trade is cut to what is left, or skipped)
  dstop : no new trades for the rest of the UTC day once the day's equity is down more than dstop
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
def sim_rules(order, n, r, eng, short, day, mon, n_mon, W, SM, CAP, DST):
    """Book every row of W (n_mix x n_eng risk), SM (short multipliers), CAP (open-risk cap, 0 = none) and
    DST (daily stop, 0 = none). Returns final multiple, max drawdown, months up, worst month per row."""
    n_mix = W.shape[0]
    fin = np.empty(n_mix); mdd = np.empty(n_mix); up = np.empty(n_mix, np.int64); worst = np.empty(n_mix)
    stake = np.empty(n)
    mon_eq = np.empty(n_mon)
    for w in range(n_mix):
        eq = 1.0; peak = 1.0; dd = 0.0; open_risk = 0.0
        cur_day = -1; day_eq = 1.0
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
    return dict(order=order, n=len(x), r=x.r.to_numpy(np.float64), eng=x.eng.to_numpy(np.int64),
                short=(x.dir.to_numpy() == -1), day=day, mon=mon, n_mon=len(months), x=x)


def run(ev, W, SM, CAP, DST):
    return sim_rules(ev["order"], ev["n"], ev["r"], ev["eng"], ev["short"], ev["day"], ev["mon"], ev["n_mon"],
                     W, SM, CAP, DST)


def bootstrap_dd(t, w_row, sm_row, cap, dst, a, b, n_sim=400, block_days=14, horizon_days=365, seed=11):
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
    CAP = np.array([cap], float); DST = np.array([dst], float)
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
        fin, dd, _, _ = run(ev, W, SM, CAP, DST)
        dds.append(dd[0]); gs.append(fin[0])
    dds = np.array(dds)
    return float(np.percentile(dds, 10)), float(np.percentile(dds, 50)), float(np.percentile(dds, 90)), float(np.median(gs))
