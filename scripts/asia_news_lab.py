"""Asian-session high-impact news bot: research toolkit and protocol (fixed before any building).

PROTOCOL
  * News: Forex Factory calendar (data/calendar/ff_calendar.csv: time_utc, currency, impact, name, actual, forecast,
    previous, better_worse = FF's own verdict 1 better / 2 worse for the currency). Only HIGH-impact events released in
    the Asian session, 21:45-07:00 UTC (AUD, NZD, JPY releases and anything else that falls there); nothing outside it.
  * Instruments: gold (XAUUSD), Nasdaq (NAS100) and the currency's own pair (AUD -> AUDUSD, NZD -> NZDUSD,
    JPY -> USDJPY, where a stronger yen means USDJPY down). M1 BID bars; longs buy at bid + cost, shorts sell at bid.
  * Costs: base spread per instrument (COST); entries within the first 5 minutes after a release pay NEWS_MULT x the
    spread (spreads widen at releases); stress test = 2 x those costs. The earliest possible entry is the open of the
    minute AFTER the release minute (the bot has to read the actual first).
  * BUILD on January-June 2026 only: calendar_train() and prices_train(symbol). No result for any trade before
    2026-01-01 or after 2026-06-30 may be computed during the build.
  * TEST once on July 1 - October 15 2026 with final_test() after the settings are locked (it refuses a second run).
  * EXTRA EXAM on 2025 (Jan-Dec), run once afterwards by the coordinator - more events for a small sample.
  * Money: $1,000, 10% of equity risked per trade, one position per instrument at a time.
  * Jan-Jun pass rules per instrument: >= 15 trades, profit factor >= 1.3, R > 0 in both Jan-Mar and Apr-Jun, profit
    factor >= 1.15 at 2 x costs and with the entry 2 minutes later, max drawdown at 10% better than -35%.
  * Jul-Oct success per instrument (stated in advance): >= 8 trades, R > 0, profit factor >= 1.3, max drawdown at 10%
    better than -35%. 2025 exam success: R > 0 and profit factor >= 1.2.
A strategy is make_trades(cfg, calendar, m1, cost) -> DataFrame(entry_time, exit_time, dir, r, event) for ONE instrument.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TRAIN = ("2026-01-01", "2026-07-01")
TRAIN_Q = {"jan-mar": ("2026-01-01", "2026-04-01"), "apr-jun": ("2026-04-01", "2026-07-01")}
TEST = ("2026-07-01", "2026-10-16")
EXAM = ("2025-01-01", "2026-01-01")
PRICE_FROM = "2025-12-01"                       # warm-up for anything that needs history before 2026
ASIA = (21.75, 7.0)                             # UTC hours: 21:45 .. 07:00
COST = {"XAUUSD": 0.25, "NAS100": 1.5, "AUDUSD": 0.00015, "NZDUSD": 0.00020, "USDJPY": 0.015}
NEWS_MULT = 2.0
PAIR = {"AUD": ("AUDUSD", 1), "NZD": ("NZDUSD", 1), "JPY": ("USDJPY", -1)}   # (pair, sign: +1 = currency is the base)
RISK = 0.10
OUT = ROOT / "results/asia_news"
_C: dict = {}


def _calendar() -> pd.DataFrame:
    if "cal" not in _C:
        c = pd.read_csv(ROOT / "data/calendar/ff_calendar.csv", parse_dates=["time_utc"])
        h = c.time_utc.dt.hour + c.time_utc.dt.minute / 60
        c["asia"] = (h >= ASIA[0]) | (h < ASIA[1])
        _C["cal"] = c
    return _C["cal"]


def asia_high(c: pd.DataFrame) -> pd.DataFrame:
    return c[(c.impact == "high") & c.asia].copy()


def calendar_train() -> pd.DataFrame:
    """All Forex Factory events from 2026-01-01 to 2026-06-30 (column `asia` marks 21:45-07:00 UTC)."""
    c = _calendar()
    return c[(c.time_utc >= TRAIN[0]) & (c.time_utc < TRAIN[1])].copy()


def _m1(symbol: str) -> pd.DataFrame:
    if symbol not in _C:
        from backtester import data as D
        m = D.load_csv(ROOT / "data" / f"{symbol}_M1.csv")
        _C[symbol] = m[m.index >= "2024-10-01"]
    return _C[symbol]


def prices_train(symbol: str) -> pd.DataFrame:
    """M1 bid bars of `symbol` from 2025-12-01 to 2026-06-30 23:59 (December 2025 = warm-up only)."""
    m = _m1(symbol)
    return m[(m.index >= PRICE_FROM) & (m.index < TRAIN[1])].copy()


def _pf(r):
    gl = -r[r < 0].sum(); gw = r[r > 0].sum()
    return float(gw / gl) if gl > 0 else (99.0 if gw > 0 else 0.0)


def metrics(trades: pd.DataFrame, a: str, b: str, risk: float = RISK) -> dict:
    t = trades[(trades.entry_time >= a) & (trades.entry_time < b)].sort_values("entry_time")
    if len(t) > 1 and (t.entry_time.to_numpy()[1:] <= t.exit_time.to_numpy()[:-1]).any():
        raise ValueError("overlapping trades on one instrument")
    r = t.r.to_numpy(float)
    eq = np.cumprod(1 + risk * r) if len(r) else np.array([1.0])
    streak = cur = 0
    for x in r:
        cur = cur + 1 if x < 0 else 0; streak = max(streak, cur)
    return dict(n=len(r), R=float(r.sum()), pf=_pf(r), win=float((r > 0).mean()) if len(r) else 0.0,
                avg_R=float(r.mean()) if len(r) else 0.0, usd=float(1000 * eq[-1]),
                dd=float((eq / np.maximum.accumulate(np.maximum(eq, 1.0)) - 1).min()), max_losing_streak=streak)


def evaluate_train(trades: pd.DataFrame) -> dict:
    if len(trades) and ((trades.entry_time < TRAIN[0]) | (trades.entry_time >= TRAIN[1])).any():
        raise ValueError("build only on trades entered in Jan-Jun 2026")
    out = metrics(trades, *TRAIN)
    for k, (a, b) in TRAIN_Q.items():
        m = metrics(trades, a, b)
        out.update({f"{k}_n": m["n"], f"{k}_R": m["R"], f"{k}_pf": m["pf"]})
    return out


def passes_train(m: dict, m_2x_cost: dict, m_late: dict) -> dict:
    chk = {"trades>=15": m["n"] >= 15, "pf>=1.3": m["pf"] >= 1.3, "jan-mar R>0": m["jan-mar_R"] > 0,
           "apr-jun R>0": m["apr-jun_R"] > 0, "pf at 2x cost>=1.15": m_2x_cost["pf"] >= 1.15,
           "pf with entry 2 min later>=1.15": m_late["pf"] >= 1.15, "drawdown at 10% better than -35%": m["dd"] > -0.35}
    chk["all"] = all(chk.values())
    return chk


def final_test(strategies: dict) -> dict:
    """Run ONCE: strategies = {name: (make_trades, cfg, symbol)}. Returns and saves the Jul-Oct 2026 results at the base
    and 2x costs. Refuses to run again."""
    f = OUT / "final_test.json"
    if f.exists():
        raise RuntimeError("final_test has already been run")
    c = _calendar()
    cal = c[(c.time_utc >= TRAIN[0]) & (c.time_utc < TEST[1])].copy()
    res = {}
    for name, (mk, cfg, sym) in strategies.items():
        m1 = _m1(sym); m1 = m1[(m1.index >= PRICE_FROM) & (m1.index < "2026-10-17")]
        t1, t2 = mk(cfg, cal, m1, COST[sym]), mk(cfg, cal, m1, 2 * COST[sym])
        m, m2 = metrics(t1, *TEST), metrics(t2, *TEST)
        ok = m["n"] >= 8 and m["R"] > 0 and m["pf"] >= 1.3 and m["dd"] > -0.35
        res[name] = dict(symbol=sym, cfg=cfg, test=m, test_2x_cost=m2, success=ok,
                         trades=t1[(t1.entry_time >= TEST[0]) & (t1.entry_time < TEST[1])].astype(str).to_dict("records"))
    OUT.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(timespec="seconds"), results=res),
                            indent=1, default=str))
    return res
