#!/usr/bin/env python3
"""Replay M15 entry signals minute-by-minute on M1 data (exact stop / break-even /
target ordering, spread on the right side).  Used to verify deep-search picks."""
from __future__ import annotations

import numpy as np
import pandas as pd


def replay(m1: pd.DataFrame, entries: pd.DataFrame, cost: float, rr: float, be: float = 1.0,
           be_buf: float = 0.1, risk: float = 0.10, bar: str = "15min") -> pd.DataFrame:
    """entries: index = signal-bar start time, columns dir (+1/-1), sl (price distance).
    Entry at the open of the next `bar`; one trade at a time."""
    mo, mh, ml = (m1[k].to_numpy() for k in ("open", "high", "low"))
    mi = m1.index
    out, busy = [], pd.Timestamp(0)
    step = pd.Timedelta(bar)
    for t_sig, row in entries.iterrows():
        et = t_sig + step
        if et < busy or not np.isfinite(row.sl) or row.sl <= 0:
            continue
        j = mi.searchsorted(et)
        if j >= len(mi):
            break
        d, R = int(row.dir), float(row.sl)
        e = mo[j] + cost if d == 1 else mo[j]
        stop, tgt, moved, r = e - d * R, e + d * rr * R, False, None
        while j < len(mi):
            hb = mh[j] if d == 1 else mh[j] + cost
            lb = ml[j] if d == 1 else ml[j] + cost
            ob = mo[j] if d == 1 else mo[j] + cost
            if d == 1:
                if lb <= stop: r = (min(ob, stop) - e) / R; break
                if hb >= tgt: r = (max(ob, tgt) - e) / R; break
                if be and not moved and hb >= e + be * R: stop, moved = e + be_buf * R, True
            else:
                if hb >= stop: r = (e - max(ob, stop)) / R; break
                if lb <= tgt: r = (e - min(ob, tgt)) / R; break
                if be and not moved and lb <= e - be * R: stop, moved = e - be_buf * R, True
            j += 1
        if r is None:
            break
        out.append((et, mi[j], d, r, R))
        busy = mi[j]
    return pd.DataFrame(out, columns=["entry_time", "exit_time", "dir", "r", "stop"])


def report(t: pd.DataFrame, risk: float = 0.10, start: float = 1000.0):
    for a0, b0, nm in [("2024-10-01", "2025-01-01", "Q4 2024"), ("2025-01-01", "2026-01-01", "2025"),
                       ("2026-01-01", "2027-01-01", "2026")]:
        r = t[(t.entry_time >= a0) & (t.entry_time < b0)].r.to_numpy()
        if not len(r):
            continue
        eq = start * np.cumprod(1 + risk * r)
        print(f"  {nm:8s} n {len(r):3d} win {np.mean(r > 0):.0%} PF {r[r > 0].sum() / -r[r < 0].sum():.2f} "
              f"${start:,.0f} @{risk:.0%} -> ${eq[-1]:,.0f}  maxDD {(eq / np.maximum.accumulate(eq) - 1).min():.0%}")
