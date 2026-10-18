"""Gold Asian breakout v12: v11 (Asia 10% + New York 5%) improved, ONE rule set every month.

Stages, each chosen on 2026 ONLY (>= 9/10 months up, drawdown >= -45%, total above the previous stage, and for
parameter grids at least half of the one-step neighbours also passing; then the highest 2026 total):
  A. New York engine settings (session, Donchian, RR, stop, daily trend, regime) with Asia fixed.
  B. a third engine: London session on gold, or v10 rules on silver (Asia / New York session).
  C. risk per engine.
2025 and Q4 2024 are printed only for the final pick (and stored for every row in results/gold/v12_*.csv).
"""
import itertools
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import gold as G  # noqa: E402
from backtester.engine import njit  # noqa: E402
from gold_v3 import overlay  # noqa: E402
from gold_v10_check import V10, V10_OVERLAY  # noqa: E402

ASIA = replace(V10, regime_warmup=20)
NY11 = replace(ASIA, ses_start=12, ses_end=15, don=15)
SILVER = dict(cost=0.03, min_stop=0.05)
V11_2026 = 244_454
OUT = ROOT / "results/gold"


@njit(cache=True)
def _book(t_in, t_out, r, f, mon_out, n_mon):
    """Fixed-fraction portfolio with overlapping trades. Events: entries before exits at the same minute."""
    n = len(t_in)
    times = np.concatenate((t_in, t_out))
    kind = np.concatenate((np.zeros(n, np.int64), np.ones(n, np.int64)))
    idx = np.concatenate((np.arange(n), np.arange(n)))
    order = np.argsort(times * 2 + kind, kind="mergesort")
    eq = 1000.0
    peak = 1000.0
    dd = 0.0
    stake = np.zeros(n)
    mon_eq = np.full(n_mon, -1.0)
    for o in order:
        i = idx[o]
        if kind[o] == 0:
            stake[i] = f[i] * eq
        else:
            eq = max(eq + stake[i] * r[i], 0.0)
            peak = max(peak, eq)
            dd = min(dd, eq / peak - 1.0)
            mon_eq[mon_out[i]] = eq
    return eq, dd, mon_eq


PER = {"q4": ("2024-10-01", "2025-01-01"), "y25": ("2025-01-01", "2026-01-01"), "y26": ("2026-01-01", "2026-11-01")}


def book(trades):
    """trades: entry_time, exit_time, r, f -> {period: (usd, dd, months_up, n_months, worst_month)}."""
    out = {}
    for k, (a, b) in PER.items():
        x = trades[(trades.entry_time >= a) & (trades.entry_time < b)]
        months = pd.period_range(a, pd.Timestamp(b) - pd.Timedelta("1D"), freq="M")
        if len(x) == 0:
            out[k] = (1000.0, 0.0, 0, len(months), 0.0); continue
        mo = months.get_indexer(x.exit_time.dt.to_period("M").clip(upper=months[-1]))
        eq, dd, me = _book(x.entry_time.to_numpy("datetime64[m]").astype(np.int64),
                           x.exit_time.to_numpy("datetime64[m]").astype(np.int64), x.r.to_numpy(np.float64),
                           x.f.to_numpy(np.float64), mo.astype(np.int64), len(months))
        prev, rets = 1000.0, []
        for v in me:
            v = prev if v < 0 else v
            rets.append(v / prev - 1 if prev > 0 else 0.0); prev = v
        rets = np.array(rets)
        out[k] = (eq, dd, int((rets > 0).sum()), len(rets), float(rets.min()))
    return out


def row(name, trades, **kw):
    r = {"name": name, **kw}
    for k, (usd, dd, up, nm, worst) in book(trades).items():
        r.update({f"{k}_usd": usd, f"{k}_dd": dd, f"{k}_up": up, f"{k}_worst": worst})
    return r


def stream(m1, m15, p):
    return overlay(G.backtest(m1, m15, p), *V10_OVERLAY)


def passes(df, floor):
    return (df.y26_up >= 9) & (df.y26_dd >= -0.45) & (df.y26_usd > floor)


def neighbour_ok(df, grid, flag):
    keys = list(grid)
    look = df.set_index(keys)[flag].to_dict()
    share = []
    for _, r in df.iterrows():
        if not r[flag]:
            share.append(0.0); continue
        hits = tot = 0
        for k in keys:
            opts = grid[k]; p = opts.index(r[k])
            for q in (p - 1, p + 1):
                if 0 <= q < len(opts):
                    nb = tuple(opts[q] if kk == k else r[kk] for kk in keys)
                    tot += 1; hits += bool(look.get(nb, False))
        share.append(hits / tot if tot else 0.0)
    return np.array(share)


def show(df, cols, n=10):
    pd.set_option("display.width", 300); pd.set_option("display.max_columns", 40)
    print(df[cols].head(n).round(2).to_string())


NY_GRID = dict(ses=["11-15", "12-15", "12-16", "13-15", "13-16"], don=[10, 15, 20], rr=[3.0, 4.0, 5.0],
               stop_atr=[1.5, 2.0], d1_trend=[0, 20], regime_max=[1.6, 99.0])
THIRD = ([("london", s, d, rr) for s in ["06-09", "07-10", "06-08", "07-09"] for d in (10, 15, 20) for rr in (3.0, 4.0)]
         + [("silver", s, d, rr) for s in ["00-06", "12-15"] for d in (10, 15) for rr in (3.0, 4.0)])
W_ASIA, W_NY, W_3 = [0.08, 0.10, 0.12], [0.04, 0.05, 0.06, 0.08], [0.0, 0.03, 0.05, 0.08]


def ses(s):
    a, b = s.split("-")
    return int(a), int(b)


def main():
    gold = G.data(ROOT)
    silver = G.data(ROOT, "XAGUSD")
    asia = stream(*gold, ASIA)
    # ---- stage A: New York engine
    ny, rows = {}, []
    for v in itertools.product(*NY_GRID.values()):
        kw = dict(zip(NY_GRID, v)); s0, s1 = ses(kw["ses"])
        p = replace(ASIA, ses_start=s0, ses_end=s1, **{k: kw[k] for k in kw if k != "ses"})
        ny[v] = stream(*gold, p)
        rows.append(row("ny", pd.concat([asia.assign(f=0.10), ny[v].assign(f=0.05)]), **kw))
    A = pd.DataFrame(rows)
    A["pass"] = passes(A, V11_2026)
    A["nb"] = neighbour_ok(A, NY_GRID, "pass")
    A.to_csv(OUT / "v12_stageA.csv", index=False)
    a_ok = A[A["pass"] & (A.nb >= 0.5)].sort_values("y26_usd", ascending=False)
    print(f"A: {len(A)} New York settings | {int(A['pass'].sum())} pass | {len(a_ok)} also with half the neighbours")
    show(a_ok, list(NY_GRID) + ["y26_usd", "y26_dd", "y26_up", "y26_worst", "nb"])
    v11_key = ("12-15", 15, 4.0, 1.5, 20, 1.6)                     # no robust improvement -> keep v11's engine
    best_a = a_ok.iloc[0] if len(a_ok) else A[[tuple(r) == v11_key for r in A[list(NY_GRID)].itertuples(index=False)]].iloc[0]
    ny_key = tuple(best_a[k] for k in NY_GRID)
    ny_best = ny[ny_key]
    floor = best_a.y26_usd
    # ---- stage B: third engine
    third, rows = {}, []
    for kind, sname, don, rr in THIRD:
        s0, s1 = ses(sname)
        p = replace(ASIA, ses_start=s0, ses_end=s1, don=don, rr=rr, **(SILVER if kind == "silver" else {}))
        third[(kind, sname, don, rr)] = stream(*(silver if kind == "silver" else gold), p)
        for w in (0.03, 0.05):
            t = pd.concat([asia.assign(f=0.10), ny_best.assign(f=0.05), third[(kind, sname, don, rr)].assign(f=w)])
            rows.append(row("third", t, kind=kind, ses=sname, don=don, rr=rr, w=w))
    B = pd.DataFrame(rows)
    B["pass"] = passes(B, floor)
    B.to_csv(OUT / "v12_stageB.csv", index=False)
    b_ok = B[B["pass"]].sort_values("y26_usd", ascending=False)
    print(f"\nB: {len(B)} third-engine setups | {len(b_ok)} pass (above stage A ${floor:,.0f})")
    show(b_ok, ["kind", "ses", "don", "rr", "w", "y26_usd", "y26_dd", "y26_up", "y26_worst"])
    best_b = b_ok.iloc[0] if len(b_ok) else None
    t3 = third[(best_b.kind, best_b.ses, best_b.don, best_b.rr)] if best_b is not None else None
    # ---- stage C: risk per engine
    rows = []
    for wa, wn, w3 in itertools.product(W_ASIA, W_NY, W_3 if t3 is not None else [0.0]):
        parts = [asia.assign(f=wa), ny_best.assign(f=wn)] + ([t3.assign(f=w3)] if w3 > 0 else [])
        rows.append(row("risk", pd.concat(parts), w_asia=wa, w_ny=wn, w_third=w3))
    C = pd.DataFrame(rows)
    C["pass"] = passes(C, 0)
    C["nb"] = neighbour_ok(C, dict(w_asia=W_ASIA, w_ny=W_NY, w_third=W_3 if t3 is not None else [0.0]), "pass")
    C.to_csv(OUT / "v12_stageC.csv", index=False)
    c_ok = C[C["pass"] & (C.nb >= 0.5)].sort_values("y26_usd", ascending=False)
    print(f"\nC: {len(C)} risk splits | {int(C['pass'].sum())} pass | {len(c_ok)} also with half the neighbours")
    show(c_ok, ["w_asia", "w_ny", "w_third", "y26_usd", "y26_dd", "y26_up", "y26_worst", "nb"])
    pick = c_ok.iloc[0]
    print("\nPICK:", dict(ny=dict(zip(NY_GRID, ny_key)), third=None if best_b is None else
                          dict(kind=best_b.kind, ses=best_b.ses, don=best_b.don, rr=best_b.rr),
                          risk=(pick.w_asia, pick.w_ny, pick.w_third)))
    return A, B, C, pick


if __name__ == "__main__":
    main()
