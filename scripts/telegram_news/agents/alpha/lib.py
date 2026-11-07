"""alpha: shared helpers (text cleaning, price look-ups, fast numba copies of common.py exits)."""
from __future__ import annotations

import os
import re
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import common as C  # noqa: E402

DATA = "/home/user/news_lab_data"
WORK = os.path.join(HERE, "work")
os.makedirs(WORK, exist_ok=True)


# ---------------------------------------------------------------- text
_SUFFIX = re.compile(r"(\|FJ\s*$)|(\(@WalterBloomberg\)\s*$)")


def clean(text: str) -> str:
    t = _SUFFIX.sub("", text.strip()).strip()
    return t


def first_line(t: str) -> str:
    for line in t.split("\n"):
        if line.strip():
            return line.strip()
    return t


_TOK = re.compile(r"[a-z][a-z'\-]+|\d+(?:\.\d+)?%?")


def tokens(t: str) -> list[str]:
    t = t.lower().replace("’", "'")
    return _TOK.findall(t)


def posts(data_dir: str = DATA) -> pd.DataFrame:
    p = C.load_posts(data_dir).copy()
    p["clean"] = p.text.map(clean)
    p["head"] = p.clean.map(first_line)
    return p


# ---------------------------------------------------------------- prices
def mid_last(tk):
    return (tk["bid_last"] + tk["ask_last"]) * 0.5


def known_price(T, px, x, stale=600):
    """price of the last second strictly before x (np arrays). NaN if older than stale seconds."""
    i = np.searchsorted(T, x) - 1
    ok = (i >= 0)
    ii = np.clip(i, 0, len(T) - 1)
    out = np.where(ok & (x - T[ii] <= stale), px[ii], np.nan)
    return out


def minute_vol(T, px, x, window_min=60):
    """mean |1-minute change| of the known price over the window_min minutes before x (x array)."""
    g0 = (T[0] // 60) * 60
    g = np.arange(g0, T[-1] + 60, 60)
    pg = known_price(T, px, g, stale=120)
    d = np.abs(np.diff(pg))                 # change over minute k -> k+1 ; known at g[k+1]
    valid = ~np.isnan(d)
    d0 = np.where(valid, d, 0.0)
    cs = np.r_[0.0, np.cumsum(d0)]
    cn = np.r_[0, np.cumsum(valid)]
    # minute index m with g[m] <= x : changes d[k] for k+1 <= m  -> d[:m]
    m = np.searchsorted(g, x, side="right") - 1
    m = np.clip(m, 0, len(d))
    lo = np.clip(m - window_min, 0, None)
    s = cs[m] - cs[lo]
    n = cn[m] - cn[lo]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n >= window_min // 3, s / np.maximum(n, 1), np.nan)


COLS = ["t", "bid_first", "bid_last", "bid_min", "bid_max", "ask_first", "ask_last", "ask_min", "ask_max"]


def lean_ticks(inst: str, data_dir: str = DATA) -> dict:
    """Same arrays as common.load_ticks (without 'n'), loaded column by column to keep memory low.
    Falls back to the full stable sort + de-duplication of common.load_ticks if files overlap."""
    import glob
    files = sorted(glob.glob(os.path.join(data_dir, "ticks_exness*", C.SYMS[inst], "*.npz")), key=os.path.basename)
    ts = [np.load(f)["t"] for f in files]
    t = np.concatenate(ts); del ts
    srt = bool(np.all(np.diff(t) >= 0))
    if srt:
        keep = np.r_[True, np.diff(t) > 0]
        alln = bool(keep.all())
    out = {}
    for c in COLS:
        if c == "t":
            v = t
        else:
            v = np.concatenate([np.load(f)[c] for f in files])
        if not srt:
            o = np.argsort(t, kind="stable")
            v = v[o]
        out[c] = v
    if not srt:
        t2 = out["t"]
        keep = np.r_[True, np.diff(t2) > 0]
        out = {k: v[keep] for k, v in out.items()}
    elif not alln:
        out = {k: v[keep] for k, v in out.items()}
    return out
