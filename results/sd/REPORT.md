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
