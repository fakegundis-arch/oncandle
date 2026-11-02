# Supply & demand v1 (gold, M1-exact) - chosen on 2026, tested on unseen 2025

Exness XAUUSD, $0.25 spread on every trade (stress test $0.40), one position at a time, risk = % of equity.
Code: `backtester/sd.py` (zones, fills, exits), `scripts/sd_v1_search.py` (grid), `scripts/sd_v1.py` (protocol, pick,
reveal), robot `mt5/Experts/SupplyDemandV1.mq5`.

## Rules
* **Zone:** a base of 1-3 small candles (range <= k x ATR) followed by one leg-out candle (range >= m x ATR, body >=
  half its range) that closes beyond the base. Demand: proximal = highest base body, distal = lowest low; supply mirrored.
* **Trade:** a limit order on the first return to the zone only (proximal line or zone middle), stop beyond the distal
  line, fixed-R target, optional break-even. A first touch that gaps through the zone, or comes in the first 15 minutes
  after a market reopen, cancels the zone.
* **Grid (559,872 combinations):** zone bars 15 / 30 / 60 / 240 min, base size, base count, leg-out size, zone height,
  entry, stop buffer, target 1.5-4R, break-even, trend filter (none / EMA200 / daily), session, order life, pattern
  (all / reversal / continuation).

## Protocol (committed before the search: 189b6ca; amendment before the reveal: 37af412)
2026: >= 60 trades, profit factor >= 1.3, both halves positive, still holding without the best trade and at a $0.40
spread; >= 60% of neighbours with PF >= 1.15; best plateau-median return / drawdown; risk from a bootstrap (worst decile
better than -25%). Success on 2025 stated in advance: total R > 0 and PF >= 1.1.
* The first pick (1511387) was withdrawn before the reveal: an audit found 62% of its 2026 R came from one fill at the
  12 Apr 2026 Sunday reopen, after price had gapped through the whole zone and its stop. The engine was fixed and two
  robustness checks were added to rule 1; 2025 stayed sealed throughout.

## Result
**Pick (28fa67c):** 15-min zones, base <= 0.75 ATR (up to 3 candles), leg-out >= 1.25 ATR, zone <= 1.5 ATR, reversal
bases (drop-base-rally / rally-base-drop) with yesterday's daily trend, limit at the zone middle, stop 0.25 ATR beyond
the distal line, target 4R, break-even after +1R, order valid 6 hours, risk 2%.

| | Trades | R | PF | $1,000 at 2% |
|---|---|---|---|---|
| 2026 (chosen on) | 73 | +37.9R | 2.05 (1.79 at $0.40) | $2,006 (-14%) |
| **2025 (unseen)** | 81 | **-0.6R** | **0.99** (0.84 at $0.40) | **$950 (-24%)** |
| 15 Nov - 31 Dec 2024 (unseen) | 8 | -4.7R | 0.06 | $909 (-9%) |

**It fails its 2025 test.** 2025 by month (trades / R): Jan 8 / -4.7, Feb 5 / -1.7, Mar 8 / -1.9, Apr 4 / -0.7,
May 9 / -1.8, Jun 6 / +2.3, Jul 9 / +2.1, Aug 6 / -2.7, Sep 5 / 0.0, Oct 3 / -0.8, Nov 6 / +1.2, Dec 12 / +8.1.
* 2026 profit came mostly from shorts (+31.3R of +37.9R); in 2025, a rising year for gold, shorts lost -9.6R.
* Checks before the reveal: two independent re-implementations matched all 73 2026 trades; a tick replay gave +37.8R;
  costs, stop slippage, exact targets and removing the top 3 trades all left +26-34R. The weakness was selection.
* Hindsight, all settings (not a pick): of the 599 settings passing the 2026 rules, only 17% would pass in 2025 (median
  2025 -13.5R, PF 0.79), and their 2026 and 2025 results are negatively correlated (-0.38). Over all 82,311 settings with
  >= 40 trades in both years the median profit factor is 0.87 in 2026 and 0.81 in 2025. **This mechanical supply &
  demand definition has no edge on gold after costs; the 2026 winners were chance.**

# Supply & demand v2 - agent search, chosen on 2026, tested on unseen 2025

Protocol committed first (f389148, `scripts/sd_v2_eval.py`): 2026 only; >= 60 trades, PF >= 1.3, both halves positive
with PF >= 1.1, PF >= 1.15 without the best trade and at a $0.40 spread, >= 60% of one-step neighbours with PF >= 1.15;
score = plateau-median growth at the user's 10% risk per trade; each candidate audited independently; v2 = the confirmed
candidate with the highest score; 2025 computed once. Success on 2025 stated in advance: total R > 0 and PF >= 1.1.

Five explorer agents each designed and searched one family on 2026 (2.8M-164.5M settings each); all five passed:

| Family | Idea | Plateau score | 2026 trades / R / PF | Audit |
|---|---|---|---|---|
| **structure_trend** | 15-min fair-value-gap zone whose impulse broke the last unbroken 15-min swing; daily swing structure (higher highs and higher lows and last break up, mirrored) must agree | **7.93** | 78 / +166.3R / 6.73 | confirmed (78/78 trades identical, truncation test, no look-ahead) |
| premium_discount | zones only in the discount / premium half of a reference range, session and volatility filters | 6.82 | 186 / +138.0R / 2.05 | confirmed (186/186; shifted bars PF 1.8-2.2) |
| rejection | enter after a rejection candle closes back outside the zone | 5.99 | 64 / +119.6R / 5.98 | confirmed, but shifted bars keep ~5% of the edge |
| zone_quality | score zones by departure, time away, leg strength | 5.89 | 241 / +114.1R / 1.94 | confirmed (241/241; shifted bars keep 55-75%) |
| mtf_refine | H1 zone, M15 change-of-character entry, 4R, 12-h exit | 2.17 | 204 / +55.1R / 1.49 | confirmed (204/204; shifted bars PF ~1.3) |

**v2 = structure_trend** (`scripts/sd_v2_strategy.py`, pick d7e6412): limit order at the gap edge, stop 0.25 ATR beyond
candle 1 (at least $1.5), target 12R, stop to +0.1R after +1R, order valid 96 bars, one position at a time.

| | Trades | R | PF | 12R winners | $1,000 at 10% |
|---|---|---|---|---|---|
| 2026 (chosen on) | 78 | +166.3R | 6.73 | 16 (21%) | $19,697,042 (-58%) |
| **2025 (unseen)** | 148 | **+30.6R** | **1.37** (1.32 at $0.40) | 9 (6%) | **$336 (-98.5%)** |
| 15 Nov - 31 Dec 2024 | 1 | -1.0R | - | 0 | $900 |

* **It passes the stated 2025 test** (R > 0, PF >= 1.1) - the first supply & demand version to do so - but the edge was
  far thinner than in 2026 (PF 1.37 against 6.73; big winners a third as often).
* **At 10% per trade it fails in money:** 83 losses and 56 break-evens around 9 big winners compound to $336, with a
  -98.5% drawdown. 2025 months at 10%: Jan +85%, Feb -4%, Mar -51%, Apr -27%, May -34%, Jun -50%, Jul -9%, Aug -7%,
  Sep -45%, Oct +68%, Nov +192%, Dec -29%.
* Hindsight, for information only: 2025 at 1% $1,273 (-27%), 2% $1,449 (-49%), 3% $1,502 (-65%), 5% $1,287 (-84%).
* Audit caveats (2026): picked from 164.5M settings; about half the 2026 edge depends on 15-min bars starting on the hour
  (bars shifted by 1-14 minutes still pass, PF 2.0-5.5); the daily structure filter carries most of the edge.
* Robot (`mt5/Experts/SupplyDemandV2.mq5`, default 10% risk as requested): an independent review ported its logic to
  Python and matched all 226 trades of 2025-2026. Its fixes are in: ATR from prices (no indicator handle to wait for at
  start-up), restarts rebuild the zones at the backtest's $0.25 spread, missed bars are replayed, no entry in the minute a
  trade closed, a warning when the server is not GMT+0. On Exness's own bars (9 Jul - 15 Oct 2026) 19 of 25 entries
  matched the backtest feed (+35.9R against +38.0R). The robot enters at market on the touch; the backtest assumes a limit
  fill at the line.

# Supply & demand v3 - built on Jan-Apr 2026, tested once on May-Oct 2026

Protocol committed first (2aaa6eb, `scripts/sd_v3_eval.py`): explorers and auditors got a data loader ending 30 Apr 2026;
$1,000 at 10% risk per trade; a candidate needed >= 30 Jan-Apr trades, PF >= 1.3, both two-month halves positive, PF >= 1.15
without its best trade and at a $0.40 spread, a Jan-Apr drawdown at 10% better than -35%, and a neighbour plateau. Success
on May-Oct stated in advance: total R > 0, PF >= 1.2 and drawdown at 10% better than -40%.

| Candidate (agent) | Jan-Apr trades / PF / drawdown at 10% | Plateau | Audit (Jan-Apr only) | May-Oct trades / R / PF | May-Oct drawdown | $1,000 May-Oct |
|---|---|---|---|---|---|---|
| **premium_discount = v3** (30-min London zones, entry at mid-zone only in the discount / premium 40% of the previous day's range, half off at 1.5R, rest 2.5R, max 2 a day, stop after a loss) | 53 / 3.61 / -27% | 3.25 | confirmed (passes at every candle shift) | **52 / -9.75R / 0.72** | **-88%** | **$257** |
| structure_trend (30-min FVG zones with the 12-h swing trend, 2R, 20:45 daily exit) | 38 / 3.68 / -27% | 1.49 | confirmed (18 of 29 shifts pass) | 46 / -7.15R / 0.71 | -62% | $376 |
| zone_quality (30/60-min zones scored by excursion, quick return, tight base; cooldown after 2 losses) | 73 / 3.37 / -19% | 3.52 | rejected (4 of 60 alignments pass) | 103 / -7.99R / 0.85 | -80% | $224 |
| mtf_refine (H1 zones, M3 engulfing entry, 3R) | 61 / 3.07 / -27% | 3.29 | rejected (2 of 60 pass) | 144 / -14.06R / 0.85 | -96% | $54 |
| rejection (M30 zones, M5 pin bar, 3R) | 108 / 2.84 / -34% | 4.06 | rejected (1 of 30 pass) | 126 / -15.00R / 0.77 | -95% | $83 |

* **v3 fails its test on every count** (pick committed in 1209327 before May-Oct was run; the result is the same at $0.40).
  Its win rate fell from 70% to 33%; 10 losses in a row from 20 Aug to 21 Sep took the account from $1,080 to $127. By
  month: May -31%, Jun -24%, Jul -2%, Aug -58%, Sep -33%, Oct (1-15) +80%.
* **All five failed** - including the two the audits confirmed. Every Jan-Apr profit factor of 2.8-3.7 became 0.71-0.85
  out of sample. Four months of data and tens of thousands of combinations per agent produced settings that fit Jan-Apr
  and nothing more; the audits' candle-shift test caught three of the five, and the other two failed anyway.
* Checks by the tester: Jan-Apr reproduced trade for trade on the full data; no overlaps; truncation tests identical;
  8 pick trades rebuilt by hand from raw bars; no pick trade held over a weekend or an early close.
* Jan-Oct as one run (Jan-Apr is the training period, so not a test): the pick reaches $38,025 by the end of April and
  ends at $9,778 (-89% drawdown).
