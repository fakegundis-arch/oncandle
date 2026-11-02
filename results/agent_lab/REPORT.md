# Agent lab: agents build on Jan-Jun 2026 and check themselves on Jul-Oct 2026; 2025 = final exam

Protocol (ccd5208, `scripts/agent_lab.py`): two agents build on Jan-Jun 2026 only, each may check up to 8 strategies on
Jul 1 - Oct 15 2026 (only ones that pass the Jan-Jun rules; every check logged in `checks.jsonl`), and drop what fails.
Because the agents look at Jul-Oct and retry, Jul-Oct is a validation period; 2025 is never given to them and is the final
exam, run once per passing strategy. $1,000 at 10% risk per trade; Exness spread $0.25 (stress $0.40).

## Agent A (supply & demand / price action)
Dropped without a check: base + leg-out zones on 5-60 min bars (PF ~1.0 on the worst shifted grid, drawdowns -50% to -85%).

**Check 1 - H1 fair-value-gap retest** (`scripts/lab_a_fvg.py`, fixed in 9112d3d before the exam): a 3-bar gap whose
middle H1 candle moved >= 2.25 x ATR; limit 25% into the gap, valid 40 H1 bars, first touch only; stop at the move's origin,
target 0.75R; at most 2 losses a day; flat at 20:45 UTC; no trading on US holiday / early-close days.

| | Trades | R | PF | Win | Max drawdown at 10% | $1,000 |
|---|---|---|---|---|---|---|
| Jan-Jun 2026 (built on) | 51 | +18.3R | 3.51 | 75% | -23% | $5,503 |
| Jul-Oct 2026 (check 1 of 8) | 28 | +4.0R | 1.52 | - | -21% | $1,381 - **passes** |
| **2025 (final exam)** | 95 | **-11.5R** | **0.69** | 46% | **-83%** | **$241 - fails** |

* 2025 by month: Jan -13%, Feb -13%, Mar -29%, Apr -21%, May +17%, Jun -17%, Jul -42%, Aug -11%, Sep -16%, Oct +19%,
  Nov +13%, Dec +1%. Same at $0.40 ($237); with the holiday calendar left as the agent wrote it (2026 dates only): $272.
* For the exam the holiday rule was applied to 2025 with the official US calendar (the agent's list covered late 2025 and
  2026 only); nothing else was changed.
* Note: early on agent A printed about 10 warm-up trades from Oct-Dec 2025 of a plain zone baseline (not tuned on them).
* Lesson: a single passing check on four months (+4R, PF 1.5) was not enough evidence; the edge did not exist in 2025.
