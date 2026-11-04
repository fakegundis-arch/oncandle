"""Research helpers (Jan-Jun 2026 only, through scripts/asia_news_lab.py)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path("/home/user/oncandle")
sys.path.insert(0, str(REPO / "scripts"))
import asia_news_lab as L  # noqa: E402

SYMS = ["XAUUSD", "NAS100", "AUDUSD", "NZDUSD", "USDJPY"]


def num(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return np.nan
    s = str(x).strip().replace(",", "")
    m = re.search(r"-?\d+(\.\d+)?", s)
    if not m:
        return np.nan
    v = float(m.group(0))
    mult = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
    for k, f in mult.items():
        if s.upper().endswith(k):
            v *= f
    return v


def kind(name: str) -> tuple[str, int] | None:
    n = name.lower()
    if "speaks" in n or "statement" in n or "conference" in n or "report" in n or "election" in n:
        return None
    if "unemployment" in n:
        return "EMP", -1
    if "employment" in n:
        return "EMP", 1
    if "cpi" in n:
        return "CPI", 1
    if "gdp" in n:
        return "GDP", 1
    if "rate" in n:  # cash rate / OCR / BOJ policy rate
        return "CB", 1
    return None


def releases(cal: pd.DataFrame) -> pd.DataFrame:
    """One row per (currency, minute) with the figures attached."""
    a = L.asia_high(cal)
    rows = []
    for (t, ccy), g in a.groupby(["time_utc", "currency"]):
        figs = []
        for _, e in g.iterrows():
            k = kind(e["name"])
            if k is None:
                continue
            act, fc, pv = num(e.actual), num(e.forecast), num(e.previous)
            if np.isnan(act):
                continue
            figs.append(dict(name=e["name"], kind=k[0], sign=k[1], actual=act, forecast=fc, previous=pv,
                             bw=int(e.better_worse) if not pd.isna(e.better_worse) else 0))
        if figs:
            rows.append(dict(time=t, ccy=ccy, kind=figs[0]["kind"], figs=figs))
    return pd.DataFrame(rows)
