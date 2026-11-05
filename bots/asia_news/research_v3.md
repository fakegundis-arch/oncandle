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
