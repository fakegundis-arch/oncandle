"""Agent lab, agent B (built on Jan-Jun 2026, passed its 2nd Jul-Oct check): Asian-range breakout into the London morning,
gold (XAUUSD, UTC server time).

Rules
  * Asian range = high / low of the M1 bid bars from 00:00 to 07:30 UTC (needs >= 80% of the minutes present).
  * 07:30-10:00 UTC: buy-stop at range high + 0.03 x ATR(14) of completed UTC days, sell-stop at range low - the same
    buffer; OCO - the first one triggered is the day's only trade. Longs buy at the ask (bid + cost), shorts sell at bid.
  * Stop = 1.5 x the Asian range width from the fill (min $1); target = 0.75R; otherwise exit at 16:00 UTC (bar open).
  * Stop before target within a minute; the fill minute may only stop out; no entries in the first 15 min after any
    pause > 30 min or in the last 60 min before a weekend / holiday close; flat 10 min before such closes.
Implementation: fam.session() + lib.simulate() in this folder (M1-exact simulator).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fam  # noqa: E402

CFG = {"tz": "UTC", "mode": 1, "r0": 0, "r1": 450, "e1": 600, "sf": 1.5, "rr": 0.75, "buf": 0.03, "x": 960,
       "be_buf": 0.05}


def make_trades(cfg, cost, m1):
    """DataFrame(entry_time, exit_time, dir, r) built only from the M1 bid frame `m1`."""
    return fam.session(cfg, cost, m1)
