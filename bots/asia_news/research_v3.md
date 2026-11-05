# Nasdaq news bot v3 - breakout of the first 3 minutes

## Protocol (written and committed before any v3 run, 2026-11-05)

Request: build version 3 of the Nasdaq news bot on the "breakout of the first 3 minutes" entry (the Jan-Jun 2026 idea
table of `research_nq.md`: 28 trades, +11.3 R, PF 2.41 for one representative config).

1. **What is fixed (not searched):**
   * Releases: Forex Factory HIGH-impact **AUD and NZD** releases between 21:45 and 07:00 UTC (same-minute figures =
     one release). JPY is excluded as in v2: the BoJ minute is not known in advance and a breakout needs the minute.
     (The research_nq.md representative included JPY.) No actual, forecast or verdict is used.
   * Range: high and low of the NAS100 bid bars of the release minute and the next 2 minutes (release .. release + 2),
     widened to include the close of the bar before the release. The market must quote at the release minute (bar at
     the release minute present and the previous bar at most 5 minutes earlier), otherwise no trade (e.g. 21:45 UTC
     NZD releases while NAS100 is closed).
   * Entry: at release + 3 minutes a buy stop at range high + buffer and a sell stop at range low - buffer, one
     cancels the other; a buy stop triggers when the ask reaches its price, a sell stop when the bid does. A gap
     through a level fills at the open. Within 5 minutes of the release the spread is 2 x the base spread and a stop
     fill pays 1 x the base spread of slippage on top. If both levels are hit in the same minute the WORSE outcome is
     booked. Orders not triggered within W minutes are cancelled.
   * Trade: stop and target measured from the fill; stop before target within a minute; the fill minute can only stop
     out; time exit `hold` minutes after the fill; flat by Friday 20:00 UTC; one position at a time (a release while a
     trade is open is skipped); $1,000, 10 % of equity risked per trade.
   * Engine: `lab/strat.py` family "brk" (the v2 research engine). The bot's own backtest must reproduce the pick's
     Jan-Jun trades exactly before any test is run.
2. **Knobs searched on Jan-Jun 2026 only** (`lab/v3_select.py`, 288 configs): order window W = 30 / 60 / 120 min;
   stop = 0.5 / 1.0 x ATR(24 x H1) or the range (range + 2 buffers + 1 spread); buffer = 0 / 0.05 x ATR;
   target = none / 1 / 2 / 3 R; hold = 60 / 120 / 240 / 360 min.
3. **Pass rules (Jan-Jun, unchanged from `scripts/asia_news_lab.py`):** >= 15 trades, PF >= 1.3, R > 0 in both
   Jan-Mar and Apr-Jun, PF >= 1.15 at 2 x costs and with the entry 2 minutes later (a stop entry becomes a market
   order 2 minutes after its trigger), max drawdown at 10 % better than -35 %.
4. **The pick (no other choice is made):** among the passing configs, the one with the highest share of passing
   neighbours (a neighbour = one knob moved one step in the order above); ties -> the shallower Jan-Jun max drawdown;
   then the higher R. If no config passes, v3 stops there. The pick is written to `LOCKED_V3.json` and committed
   before the unseen periods are run.
5. **Unseen tests, each run once, after the lock:**
   * Jul 1 - Oct 15 2026: `asia_news_lab.final_test(tag="nasdaq_v3")`. Success (stated in the toolkit): >= 8 trades,
     R > 0, PF >= 1.3, max drawdown better than -35 %.
   * Jan - Dec 2025: `asia_news_lab.exam_2025(tag="nasdaq_v3")`. Success: R > 0 and PF >= 1.2.
   * v3 "works" only if it passes BOTH.
6. **What is not clean, stated in advance:**
   * The breakout family was chosen by the user from a table of Jan-Jun results only - fine - but that table came out
     of a search over many families, and research_nq.md section 3 found the release effect weak (the breakout's shift
     placebo: -13.7 R one hour later; 0.5 ATR breakout stops lose -0.15 R per trade at the same minutes on days
     without a release).
   * Jul-Oct 2026 is being used for the third time (v1, v2) and 2025 for the second (v2's exam). No v3 setting is
     chosen on either, but I have seen how NAS100 behaved after these releases in both periods (e.g. in 2025 buying at
     release + 2 min and holding 6 h made +2.24 R).

## Pick on Jan-Jun 2026 (`lab/v3_select.py` -> `lab/out_v3_select.txt`, `lab/out/grid_v3.csv`)

288 configs, 44 pass (15 %). Pass share by knob: stop 0.5 ATR 33 %, 1 ATR 12 %, range 0 %; hold 6 h 40 %, 1 h 0 %;
target 1R 0 %, 2-3R 21-25 %; buffer 0.05 ATR 20 % vs 0 10 %; the order window did not matter (15-16 %).

**Pick:** W 60 min, stop 0.5 x ATR, buffer 0.05 x ATR, target 3R, hold 6 h - all 6 neighbours pass (W 30 / 120,
buffer 0, target 2R, hold 4 h, stop 1 ATR). Locked in `LOCKED_V3.json` (commit 999f36b) before any unseen run.

| Jan-Jun 2026 | n | R | PF | win | max DD (10 %) | $1,000 -> | Jan-Mar / Apr-Jun R | PF 2 x cost | PF late |
|---|---|---|---|---|---|---|---|---|---|
| nasdaq_v3 | 24 | +13.44 | 2.34 | 58 % | -27.1 % | 2,834 | +3.33 / +10.10 | 1.36 (DD -42.7 %) | 2.03 |

Same rule at the same clock times on days without a release: +0.09 R per trade (PF 1.14) vs +0.56 at the releases
(p = 0.07). Already in the build period the drawdown at 10 % risk was -27 % (-43 % at 2 x cost).

## The bot (`newsbot`, entry = "breakout")

`strategy.breakout_setup` (range, levels, stop / target) is shared by the backtest and the live loop.
`backtest.simulate_breakout` fills the OCO stops as the protocol says. Live, the bot places real MT5 BUY_STOP /
SELL_STOP orders at release + 3 min (`MT5Broker.place_stop`, with an expiration or GTC + its own cancel), detects the
fill (`order_status`: the position whose identifier is the order ticket), cancels the other leg, re-anchors stop /
target to the real fill (`modify_sltp`) and keeps working orders in the state file. Checks on Jan-Jun 2026 (before
the unseen runs, commit f27553a): the bot backtest equals the lab engine trade for trade at base cost, 2 x cost and
with the late entry (max |dR| 5e-14); the live loop replayed minute by minute through `ReplayBroker`'s pending
orders takes the same 24 trades (max |dR| 0.000); v1 / v2 numbers and the v2 replay are unchanged; 30 unit tests.

## Unseen tests (run once, `lab/run_v3_tests.py` -> `lab/out_v3_tests.txt`)

| | n | R | PF | win | max DD (10 %) | $1,000 -> | success |
|---|---|---|---|---|---|---|---|
| Jul 1 - Oct 15 2026 (`results/asia_news/nasdaq_v3.json`) | 15 | -0.28 | 0.97 | 27 % | -52.2 % | 808 | **no** (rule: R > 0, PF >= 1.3, DD > -35 %) |
| same at 2 x cost | 15 | -4.28 | 0.64 | | -52.2 % | 560 | |
| Jan - Dec 2025 (`results/asia_news/exam2025_nasdaq_v3.json`) | 50 | -2.67 | 0.91 | 36 % | -68.2 % | 490 | **no** (rule: R > 0, PF >= 1.2) |
| same at 2 x cost | 50 | -3.45 | 0.89 | | -72.2 % | 459 | |

* Jul-Oct: 11 of 15 trades hit the 0.5 ATR stop, 3 reached the 3R target; August made +6.7 R, then 7 losses in a row
  (Sep 2 - Oct 15). Longs -2.3 R (9), shorts +2.0 R (6).
* 2025: 30 of 50 trades stopped, 6 reached the target; Jan-Mar -6.8 R, Apr-Jun -0.6, Jul-Sep +4.3, Oct-Dec +0.5.
  Longs +1.8 R (30), shorts -4.5 R (20).
* The win rate fell from 58 % (Jan-Jun) to 27-36 %: the first three minutes did not pick the direction of the next
  hours outside the build period. With a stop of half an hourly range, a 10 % risk per trade turns the normal losing
  streaks into -52 % to -68 % drawdowns.

**Conclusion: v3 fails both unseen tests. No demonstrated edge - do not trade it with real money.** The code works
(it reproduces the backtest exactly in the live loop) and stays in the bot as entry mode "breakout" for dry-run use.

