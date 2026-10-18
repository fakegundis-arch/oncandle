"""Gold Asian breakout v9: modes v5, B and C combined into ONE rule set that trades every month.

Ways of combining (all modes run all year, no calendar switching):
  together - every mode trades its own signals with its own risk; trades may overlap (risk = % of equity at entry)
  first    - one trade at a time; the first mode to signal takes it
  agree    - trade only when >= `k` modes signal the same direction on the same day (enter on the k-th signal)
Combination settings are chosen on 2026 only; 2025 and Q4 2024 are the test. Mode C was partly chosen on 2025
(its search ranked Apr/Jul/Sep 2025), so 2025 is fully clean only for combinations of v5 and B.
"""
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import gold as G  # noqa: E402
from gold_v3 import overlay  # noqa: E402

MODES = {
    "v5": (G.P(don=10, rr=4.0, stop_atr=1.5, be_buf=0.3, slope=16, max_per_day=2), (0, 0.0, -2.0)),
    "B": (G.P(ses_start=0, ses_end=6, don=10, ema=200, slope=8, stop_atr=1.5, rr=4.0, be_buf=0.3, regime_max=1.6),
          (10, -2.0, -2.0)),
    "C": (G.P(ses_start=0, ses_end=8, don=15, ema=200, slope=8, prev_day=False, stop_atr=1.5, rr=4.0, be_buf=0.3,
              max_per_day=2), (10, -2.0, -2.0)),
}
PERIODS = G.PERIODS


def streams():
    m1, m15 = G.data(ROOT)
    return {k: overlay(G.backtest(m1, m15, p), *ov).assign(mode=k) for k, (p, ov) in MODES.items()}


def sim(trades, a, b):
    """trades: entry_time, exit_time, r, f (risk fraction). Overlapping trades allowed. Returns equity, DD, months."""
    x = trades[(trades.entry_time >= a) & (trades.entry_time < b)]
    ev = sorted([(e, 0, i) for i, e in enumerate(x.entry_time)] + [(t, 1, i) for i, t in enumerate(x.exit_time)],
                key=lambda z: (z[0], z[1]))
    r, f = x.r.to_numpy(), x.f.to_numpy()
    eq, stake, pts = 1000.0, {}, [(pd.Timestamp(a), 1000.0)]
    for t, kind, i in ev:
        if kind == 0:
            stake[i] = f[i] * eq
        else:
            eq = max(eq + stake.pop(i) * r[i], 0.0)
            pts.append((t, eq))
    s = pd.Series([p[1] for p in pts], index=[p[0] for p in pts])
    me = s.resample("ME").last().ffill()
    rets = me / me.shift().fillna(1000.0) - 1
    c = s.to_numpy()
    return eq, float((c / np.maximum.accumulate(c) - 1).min()), rets, len(x)


def together(S, w, short_mult):
    out = []
    for k, t in S.items():
        if w.get(k, 0) > 0:
            out.append(t.assign(f=np.where(t.dir == 1, w[k], w[k] * short_mult)))
    return pd.concat(out).sort_values("entry_time")


def first(S, keys, risk, short_mult):
    x = pd.concat([S[k] for k in keys]).sort_values(["entry_time", "mode"])
    keep, busy = [], pd.Timestamp(0)
    for i, (e, xt) in enumerate(zip(x.entry_time, x.exit_time)):
        if e >= busy:
            keep.append(i); busy = xt
    y = x.iloc[keep]
    return y.assign(f=np.where(y.dir == 1, risk, risk * short_mult))


def agree(S, keys, k, risk, short_mult):
    x = pd.concat([S[m] for m in keys]).sort_values("entry_time")
    x = x.assign(day=x.entry_time.dt.normalize())
    rows, busy = [], pd.Timestamp(0)
    for (_, d), g in x.groupby(["day", "dir"]):
        if g["mode"].nunique() >= k:
            seen, pick = set(), None
            for _, row in g.iterrows():
                seen.add(row["mode"])
                if len(seen) >= k:
                    pick = row; break
            rows.append(pick)
    y = pd.DataFrame(rows).sort_values("entry_time")
    keep, busy = [], pd.Timestamp(0)
    for i, (e, xt) in enumerate(zip(y.entry_time, y.exit_time)):
        if e >= busy:
            keep.append(i); busy = xt
    y = y.iloc[keep]
    return y.assign(f=np.where(y.dir == 1, risk, risk * short_mult))


def candidates(S):
    for keys in (("v5", "B", "C"), ("v5", "B"), ("v5", "C"), ("B", "C")):
        for w in itertools.product((0.03, 0.04, 0.05, 0.06, 0.08), repeat=len(keys)):
            for sm in (1.0, 0.5):
                yield f"together {'+'.join(keys)} {'/'.join(f'{v:.0%}' for v in w)} short x{sm}", \
                    together(S, dict(zip(keys, w)), sm)
        for risk, sm in itertools.product((0.08, 0.10, 0.12), (1.0, 0.5)):
            yield f"first {'+'.join(keys)} {risk:.0%} short x{sm}", first(S, keys, risk, sm)
            for k in range(2, len(keys) + 1):
                yield f"agree{k} {'+'.join(keys)} {risk:.0%} short x{sm}", agree(S, keys, k, risk, sm)


def main():
    S = streams()
    rows = []
    for name, t in candidates(S):
        row = {"name": name}
        for p, (a, b) in PERIODS.items():
            e, dd, rets, n = sim(t, a, b)
            row.update({f"{p}_usd": e, f"{p}_dd": dd, f"{p}_up": int((rets > 0).sum()), f"{p}_m": len(rets),
                        f"{p}_worst": float(rets.min()), f"{p}_n": n})
        rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "results/gold/v9_combos.csv", index=False)
    return df, S


if __name__ == "__main__":
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    df, _ = main()
    print(len(df), "combinations")
