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

**After the exam failure, agent A checked three materially different ideas; all passed Jan-Jun and all failed Jul-Oct:**

| Check | Idea | Jan-Jun PF / drawdown | Jul-Oct trades / R / PF / drawdown | Works |
|---|---|---|---|---|
| 2 | Asian session in the daily trend (00:00 UTC entry with yesterday's 50-day EMA and 5-day momentum, out at 06:00) | 1.87 / -14% | 50 / -1.3R / 0.80 / -25% | no |
| 3 | $50 round-number breakouts (stop orders at untouched round levels, 0.75R) | 1.86 / -24% | 115 / +6.8R / 1.22 / -47% | no (PF < 1.3, drawdown) |
| 4 | Prior-day value-area re-entry (back inside the 80% value area, target the most-traded price) | 2.66 / -21% | 48 / -5.2R / 0.78 / -69% | no |

It then tried 11 more ideas (zones on H2/H4, breakout-retests, pin bars / engulfing at extremes, sweep-and-reclaim,
wick-rejection zones, flipped zones, round-number retests, level breakouts, trend-day continuation, London fix,
compression / opening-range breaks) against a stricter bar of its own (settings chosen on odd weeks must hold on even
weeks) and none qualified, so it stopped with 4 checks unused. Its conclusion: passing every candle shift and most
neighbours on Jan-Jun was not real evidence (every variant re-measures the same ~125 days); only momentum effects
(big-candle continuation, round-number stop runs) stayed even partly positive in Jul-Oct.

## Agent B (any idea)
**Check 1 - H1 Donchian(20) breakout with the daily trend** (5 ATR stop, break-even at +0.3R): Jan-Jun PF 4.73, DD -18%,
very robust there (11/11 grid shifts, 13/13 neighbours) - Jul-Oct 34 trades, -3.2R, PF 0.66, DD -35%: **fails**, dropped.
Dropped without a check: RSI pullbacks, previous-day high / low fades (PF 0.72) and breakouts, London / New York
opening-range breakouts and fades.

**Check 2 - Asian-range breakout into the London morning** (`scripts/lab_b/`, fixed in 323a5de before the exam): range =
00:00-07:30 UTC high / low; 07:30-10:00 a buy-stop above / sell-stop below it (+0.03 x daily ATR), first one only; stop
1.5 x the range width, target 0.75R, otherwise out at 16:00 UTC; flat before weekend / holiday closes.

| | Trades | R | PF | Win | Max drawdown at 10% | $1,000 |
|---|---|---|---|---|---|---|
| Jan-Jun 2026 (built on) | 48 | +6.4R | 2.13 | - | -11% | $1,808 |
| Jul-Oct 2026 (check 2 of 8) | 35 | +8.1R | 3.86 | - | -11% | $2,161 - **passes** |
| **2025 (final exam)** | 134 | **-3.1R** | **0.91** | 46% | **-63%** | **$586 - fails** |

* 2025 by month: Jan +14%, Feb +1%, Mar +7%, Apr +4%, May +21%, Jun -19%, Jul +2%, Aug -8%, Sep -18%, Oct -1%, Nov -36%,
  Dec -5%. At $0.40: $567. (Q4 2024, information only: 26 trades, PF 1.03.)
* Both agents' Jul-Oct winners failed 2025: four months of validation did not separate real edges from luck. Each failed
  exam that sends an agent back for another try also uses up a little of 2025's value as an unseen test.
