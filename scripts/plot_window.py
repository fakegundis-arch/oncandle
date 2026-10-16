#!/usr/bin/env python3
"""Plot M1 candles for a window with the bot's view: EMAs, minutes it rates
as trending, and signal/entry markers.

    python scripts/plot_window.py XAUUSD "2026-09-03 00:00" "2026-09-03 06:00" out.png [--v2]
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtester import data as D, indicators as ind, trend_rider as tr  # noqa: E402


def plot(sym, start, end, out, sig, trend, title, pad="90min"):
    g = D.load_csv(ROOT / "data" / f"{sym}_M1.csv").drop(columns="spread", errors="ignore")
    a, b = pd.Timestamp(start) - pd.Timedelta(pad), pd.Timestamp(end) + pd.Timedelta(pad)
    w = g.loc[a:b]
    e20, e50, e200 = (ind.ema(g.close, n).loc[a:b] for n in (20, 50, 200))
    x = np.arange(len(w))
    fig, ax = plt.subplots(figsize=(16, 7))
    up = w.close >= w.open
    ax.vlines(x, w.low, w.high, color=np.where(up, "#26a69a", "#ef5350"), linewidth=0.7)
    ax.vlines(x, w[["open", "close"]].min(axis=1), w[["open", "close"]].max(axis=1),
              color=np.where(up, "#26a69a", "#ef5350"), linewidth=2.2)
    ax.plot(x, e20, color="#f9a825", lw=1, label="EMA20")
    ax.plot(x, e50, color="#1e88e5", lw=1, label="EMA50")
    ax.plot(x, e200, color="#6a1b9a", lw=1, label="EMA200")
    tw = trend.reindex(w.index).fillna(0).to_numpy()
    lo, hi = w.low.min(), w.high.max()
    ax.fill_between(x, lo, hi, where=tw == 1, color="#26a69a", alpha=0.10, step="mid", label="bot: uptrend")
    ax.fill_between(x, lo, hi, where=tw == -1, color="#ef5350", alpha=0.10, step="mid", label="bot: downtrend")
    sw = sig.reindex(w.index).fillna(0).to_numpy()
    for i in np.where(sw != 0)[0]:
        if i + 1 < len(w):
            ax.annotate("BUY" if sw[i] > 0 else "SELL", (x[i + 1], w.open.iloc[i + 1]),
                        xytext=(0, -28 if sw[i] > 0 else 28), textcoords="offset points", ha="center",
                        color="#0d47a1", fontsize=8, arrowprops=dict(arrowstyle="->", color="#0d47a1"))
    ia, ib = w.index.searchsorted(pd.Timestamp(start)), w.index.searchsorted(pd.Timestamp(end))
    ax.axvspan(ia, ib, color="#ffd54f", alpha=0.12, label="window you highlighted")
    ticks = x[::30]
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{w.index[i]:%H:%M}\n({(w.index[i] + pd.Timedelta('1h')):%H:%M})" for i in ticks], fontsize=8)
    ax.set_xlabel("UTC   (UTC+1 in brackets)")
    ax.set_title(title)
    ax.legend(loc="upper left", fontsize=8, ncol=4, frameon=False)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    sym, start, end, out = sys.argv[1:5]
    g = D.load_csv(ROOT / "data" / f"{sym}_M1.csv").drop(columns="spread", errors="ignore")
    s = tr.signals(g, tr.Params(min_stop_price=10))
    plot(sym, start, end, out, s.signal, s.trend, f"{sym} M1 - current bot (Trend Rider)")


def plot_v2(sym, start, end, out, **kw):
    from backtester import trend_rider_v2 as v2
    g = D.load_csv(ROOT / "data" / f"{sym}_M1.csv").drop(columns="spread", errors="ignore")
    s = v2.signals(g, v2.Params(**kw))
    plot(sym, start, end, out, s.signal, s.trend, f"{sym} M1 - Trend Rider v2 (trend judged on M5, entry on M1)")
