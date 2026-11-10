# Backtest: 4newgolds gold bot, Telegram channels (Jan 1 - Oct 31 2026)

Bot: github.com/fakegundis-arch/4newgolds, branch `claude/code-review-understanding-swltkb` (commit cb6d625,
config.yaml as committed).  Replay: `scripts/goldbot_backtest/replay.py` (run with the bot's folder as argument).

## What was replayed
* **Posts:** every post of the three channels in `telegram_feed.channels` - @FinancialJuice, @WalterBloomberg,
  @apewirenews (posts from Apr 11 2026, when the channel started) - from their public Telegram history, to the second:
  51,331 posts in Jan-Oct 2026.
* **The bot's own code** for everything it decides: its config loader (`load_config`), the Telegram profile
  (`telegram_feed.profile_for(x_feed.defaults)`), keyword / blacklist matching (`newsbot.utils`), the ❗/🔴 fast track,
  the order prices (`round_price`, ask + $5 / bid - $5), SL / TP from the real fill (`sltp_from_fill_dist`), the
  break-even stages on wicks (`staged_break_even_sl`, `sl_placeable_now`) and the trailing stop (`trailing_sl`).  The
  gate methods of bot.py (`_emoji_flag`, `_post_tradable`, `_social_open_blocked` order, `_content_key`) are copied
  line for line.  450 of the bot's 452 unit tests pass here (the 2 failures: a test expecting older companion values,
  and one needing Telegram credentials).
* **Settings in force** (from config.yaml): keywords Fed, Fed's, Warsh, Federal reserve, trump, Bessent, scott,
  treasury, white house (official) - whole words; blacklist opinion, anniversary, bank(s), isreal, year and "effective
  fed funds rate"; ❗ / 🔴 posts skip the keyword gate unless they say "macro" / "$MACRO"; posts older than 120 s,
  forwards, replies and texts under 15 characters are skipped; same story within 10 min traded once; no trading for
  30 min after a high-impact USD release (60 min after a speech / statement); one straddle open at a time across the
  channels (global cap 1).  Gold straddle: buy stop ask + $5, sell stop bid - $5, 0.01 lot, live 120 s, OCO, SL $3 from
  the fill, no TP, break-even at +$4.5 -> SL entry + $1, at +$15 -> entry + $12, trailing from +$24 at $4 behind.
  Companion USTECm straddle with every gold straddle (unless one is still open): +/-30 points, 0.5 lot, SL 40, TP 40.
* **Execution** on Exness 1-second bid / ask (XAUUSDm, USTECm): the bot acts 2 s after a post; its management loop
  runs every 2 s (SL attached at the first tick after a fill, retried while MT5 would reject it); stop orders fill at
  the worse of the order price and the second's first quote + 1 spread; SL / TP fill at their level or at a gapped
  price; positions are kept over nights and weekends like the bot does; posts while the market is shut place no
  orders.  P&L: gold 0.01 lot = $1 per $1; USTECm 0.5 lot = $0.50 per point (Exness contract size 1 - check yours).

**Not reproduced:** the AI post review (`ai_post_check`, gpt-4o-mini; no OpenAI key here).  It only cancels UNFILLED
orders ~1-3 s after arming and never reviews ❗/🔴 posts, so it is shown as three scenarios.  Not included: the
Truth Social (Trump) feed, which also trades; swaps; commissions (none on Exness Standard).

## Results
| Scenario | Straddles armed | Gold positions | Gold P&L | Nasdaq positions | Nasdaq P&L | **Total** | Worst drawdown |
|---|---|---|---|---|---|---|---|
| **Base**: acts 2 s after the post, +1 spread on fills, AI keeps every trade | 6,646 | 1,395 | -$96 (PF 0.96) | 779 | -$1,406 (PF 0.83) | **-$1,502** | -$2,068 |
| AI review ~ "only a principal speaking" (Trump / Fed / Treasury / White House headline) | 7,940 | 835 | -$262 | 460 | -$685 | **-$947** | -$1,306 |
| AI review strict (vetoes every reviewed post; ❗/🔴 still trade) | 12,080 | 277 | -$144 | 186 | -$641 | **-$786** | -$999 |
| Optimistic: acts 1 s after the post, no slippage | 6,583 | 1,365 | +$240 (PF 1.10) | 781 | -$922 | **-$683** | -$1,222 |
| Stress: acts 5 s after the post, +2 spreads in, +1 out | 6,677 | 1,406 | -$967 | 804 | -$3,414 | **-$4,382** | -$4,527 |

(A vetoed straddle frees the one-at-a-time slot sooner, so the AI scenarios arm more straddles but fill fewer.)

Base, in detail (`trades_base.csv` = every straddle and position, `decisions_base.csv` = what happened to every post):
* What happened to the 51,331 posts: no keyword 44,320; armed 6,646; blocked by the one-straddle cap 6,739;
  blacklisted 4,071; market shut 1,749; USD news blackout 1,637; duplicate 44; forward 31; too short 23; reply 11.
* Only 21 % of straddles fill (the price must move $5 within 2 minutes).  Gold exits: stop loss 897 (-$2,697),
  break-even 461 (+$1,648), trailing 37 (+$953).  No position was left without a stop, none was held over a day.
* By channel (gold / Nasdaq): FinancialJuice -$101 / -$564; WalterBloomberg +$39 / -$783; apewirenews -$34 / -$59.
* By trigger: ❗ fast track (FinancialJuice) gold -$112 (PF 0.73), Nasdaq -$321; keyword posts gold +$17 (PF 1.01),
  Nasdaq -$1,085.  The keyword "trump" alone triggers 702 of 1,191 keyword gold positions and loses -$165 (it fires on
  any headline naming him or his family).
* Nasdaq companion: 424 stop-outs at -$20 vs 355 take-profits at +$20 (win rate 46 % at 1:1) - it loses in every
  scenario and is most of the loss.
* By month (total $): Jan +116, Feb -86, Mar -489, Apr +42, May -532, Jun +23, Jul -682, Aug +38, Sep -118, Oct +189.

## Things found in the bot's settings
* **The calendar straddle never trades:** `calendar.currencies: ["UASD"]` (typo for "USD").
* **Forex Factory news trading is off:** `forexfactory_news.enabled: false`, so `news_straddle` and the AI news trades
  never see a headline.
* **Live trading is on:** `demo_only: false`, `trading_enabled: true`.
* **The companion Nasdaq straddle risks ~$20 per trade vs $3 for gold** (0.5 lot x 40 points) and decides the result.
* **🔴 is a fast-track emoji**, and apewirenews marks earnings misses with 🔴 (e.g. "🔴 Revenue $1.5B vs $1.58B"), so
  company earnings can open gold straddles (2 such posts in this period, more since November).

## Verdict
Replayed with its own logic on Jan-Oct 2026, the Telegram part of the bot loses money in every scenario: -$1,502 in
the base case (gold about flat, the Nasdaq companion -$1,406).  Gold alone is near break-even and only positive with
perfect, slippage-free fills.  Comparing against the bot's real trades needs its MT5 account history or its log
(logs/newsbot.log); with either, each live trade can be matched to its replayed counterpart.

## Correction (Nov 10 2026): news blackout in November
The calendar file used for the USD news blackout ended on Oct 31, so the first runs that reached into November
(`*_to_2026-11-10*`, the last-30-days list) applied no blackout on Nov 1-9.  The November 2026 Forex Factory calendar
was added (`scripts/fetch_ff_calendar.py --start 2026-11 --end 2026-11`) and the run repeated: Jan-Oct is identical;
two gold trades right after the Nov 6 jobs report (13:33 and 13:36 UTC, -$3 each) are now blocked, as the bot would.
Nov 1-9: 73 trades, +$199.37 (was 75, +$193.37); Jan 1 - Nov 9: -$1,302.90 (was -$1,308.90); last 30 days: 124
trades, +$329.90 (was 126, +$323.90).

## The bot's real AI review on the last 30 days (Oct 11 - Nov 9 2026)
With the user's OpenAI key (used only for this run, never stored), the bot's own `AIPostChecker` (its prompt,
gpt-4o-mini, temperature 0, principal + rating >= 60 gates) reviewed the 919 posts of the window that could trade
(armed, or blocked only by the one-straddle cap): keep 214, not a principal 405, rating below 60 300, errors 0, median
response 0.88 s (`ai_verdicts_last30.csv`).  Replayed with those verdicts (`scenario ai_real`: a "no" cancels the
unfilled orders at the first bot tick after the measured response time; ❗/🔴 posts are never reviewed):

| Last 30 days | Straddles armed | Trades | Gold | Nasdaq | Total | Profit factor | Worst drawdown |
|---|---|---|---|---|---|---|---|
| Without the AI review (fails open) | 526 | 124 | +$10.07 | +$319.83 | **+$329.90** | 1.42 | -$119.10 |
| With the real AI review | 748 (568 vetoed) | 46 | -$19.07 | $0.00 | **-$19.07** | 0.94 | -$79.00 |

With the review: posts the AI kept -$75.00 (26 trades); ❗/🔴 posts (not reviewed) +$55.93 (20 trades).  Verdicts
from today's model can differ slightly from what it answered live.

## Checked against the bot's own live log (Oct 25 - Nov 10 2026)

The bot's `newsbot.log` (Oct 25 - Nov 10, clock UTC+3) was parsed (`scripts/goldbot_backtest/live_log.py`; the log
itself holds account numbers and is not in the repo) and every live decision and fill was compared with the replay
(`scripts/goldbot_backtest/live_check.py`).  Files: `live_log_check/`.

**Post decisions.** 3,652 Telegram posts the live bot saw (to Nov 9): the replay made the same decision on 95.8 %
(`post_decisions_crosstab.txt`).  The differences: 79 posts in the Oct 28 FOMC hours (the live bot had no news
blackout yet - it was added Nov 1); straddles from the X feed (@DeItaone etc.) holding the global cap live (the
replay has no X data); posts the live bot got late and skipped as stale (e.g. Nov 6 14:43, 128-261 s late); and
keyword-list edits.

**Straddle by straddle.** All 756 straddles the live bot armed (Telegram, X and Trump feeds; gold and USTECm) were run
through the replay engine with what the bot had at that moment: the logged arm second, the last quote before it, the
logged USTECm stop prices, the AI verdict at its logged time, and the settings in force, read from the fills:

| live period (UTC) | gold offset / SL | USTECm offset / SL / TP, lot, break-even |
|---|---|---|
| to Nov 1 | 6 / 6 | no companion |
| Nov 1 - Nov 4 18:45 | 6 / 5 | 25 / 30 / 30, 0.1, on (20 -> +5) |
| Nov 4 18:45 - Nov 5 22:33 | 5 / 3 | 30 / 40 / 40, 0.1, on |
| Nov 5 22:33 - Nov 9 14:40 | 5 / 3 | 30 / 40 / 40, 0.1, off |
| from Nov 9 14:40 | 5 / 3 | 30 / 40 / 40, 0.5, off |

Result (straddles with price data): USTECm 15 of 16 live fills on the same side at the same price to the cent, 196 of
196 unfilled ones unfilled too; the one other-side case is a live order the broker rejected ("bad stops", the bot was
2.8 s behind).  Gold: 9 of 12 live fills on the same side (prices within $0.0-0.5), 418 of 424 unfilled ones unfilled.
The gold differences are $0.2-0.7 quote differences at arming, and 5 straddles that the replay fills in the 24 h
after the Oct 28 FOMC trades - the live account was empty then (balance $16.39 -> $0.00), so its triggered orders
could not fill.

**Live trades and the account balance.** Each live fill, run forward from its real price and second
(`live_trade_exits.csv`), against the bot's own daily balance lines:

| interval | balance change | replay of the live fills |
|---|---|---|
| live account 1, Oct 28 (FOMC) | -16.39 (emptied) | -10.00 |
| live account 2, Nov 2 | -3.64 | -4.50 |
| live account 2, Nov 3 | -25.29 (emptied) | -18.54, see below |
| demo, Nov 4 | -3.00 | -3.00 |
| demo, Nov 5 (if $1,000 was added) | -7.76 | -7.62 |
| demo, Nov 6 | -4.00 | -4.00 |
| demo, Nov 6 - 9 | +1.00 | +1.00 (gold -3.00, USTECm +4.00 at its TP - from the MT5 export, see below) |
| demo, Nov 9 14:40 - Nov 10 01:37 | +2.57 | +1.00 (gold +1.00, USTECm +20.00 and -20.00) |

Live account 2 was emptied by a bot failure: the USTECm BUY of Nov 3 23:38 UTC never got its stop loss (114
"bad stops" rejections - price had already gone through the SL level), stayed open with no stop, and its loss reached
the account's remaining ~$9.8 at 23:41:50, when the retries stop.  Two more live-only events the replay does not
model: stop-loss rejections leave positions naked, and orders placed while the bot is busy use a quote up to ~3 s old.

**What changed in the replay.** The bot arms a median 2 s after the post (1 s: 95, 2 s: 110, 3 s: 81, 4 s: 55 posts)
and prices from the last quote before that second; its stops filled at their price.  The old replay priced from the
end of that second and added one spread of slippage.  New scenarios `live` / `live_ai_real` do it the bot's way
(`summary_to_2026-11-10.json`).  Today's config, Jan 1 - Nov 9:

| | gold | Nasdaq | total |
|---|---|---|---|
| old `base` (no AI) | -56.45 | -1,246.45 | -1,302.90 |
| calibrated `live` (no AI) | +250.27 | -744.44 | -494.17 |
| calibrated `live_ai_real` (real AI Oct 11 - Nov 9, none before) | +219.88 | -944.33 | -724.45 |

Last 30 days (Oct 11 - Nov 9) with the real AI review: old -$19.07, calibrated +$5.92.  My recorded AI verdicts agree
with the live bot's on 280 of 285 posts both reviewed.  USTECm prices for Nov 9-10 are not in the Exness archive yet.

## Nasdaq for Nov 9 - 10 from the user's MT5 export

The Exness tick archive has USTECm only to Nov 8 23:59 UTC (last updated Nov 9 09:41 UTC), so the Nov 9 - 10 Nasdaq
trades could not be replayed.  The user exported USTECm 1-minute bars from their MT5 terminal (kept locally in
`data/mt5_exports/`, not in the repo).  Check: same clock as the archive (UTC) and 79 % of Oct 1 - Nov 8 OHLC values
equal to the cent; the bot's own quote at arming lies inside that minute's range for all 74 Nov 9 - 10 USTECm
straddles.  `scripts/goldbot_backtest/m1_nasdaq.py`; files `live_log_check/nasdaq_live_trades_nov9_10_m1.csv`,
`nasdaq_nov9_m1_backtest.csv`.  With minute bars the order of prices inside a minute is unknown; every result below
comes out the same whichever came first.

The live bot's USTECm trades (each from its real fill, with its real SL / TP):

| filled (UTC) | post | trade | result |
|---|---|---|---|
| Nov 9 13:10 | ❗ Qatari Official: reports on US-Iran proposal false | SELL 27193.54, 0.1 lot | take profit 13:20, +$4.00 |
| Nov 9 16:04 | ❗ US chip inquiry halted after Nvidia intervention | SELL 27867.54, 0.5 lot | take profit 16:09, +$20.00 |
| Nov 9 19:39 | ❗ Al Arabiya: US allowed uranium enrichment | BUY 27989.90, 0.5 lot | stop loss 19:39-19:44, -$20.00 |
| Nov 10 09:01 | ❗ Fed's Waller: half-point hike may be needed | SELL 27798.04, 0.5 lot | stop loss 09:01-09:02, -$20.00 |
| Nov 10 15:50 | Gordon Johnson slams Fed balance sheet | SELL 27661.57, 0.5 lot | take profit 15:50-15:56, +$20.00 |
| Nov 10 15:57 | ❗ Traders price two BoE hikes by March | BUY 27668.41, 0.5 lot | take profit 16:00, +$20.00 |

Against the bot's balance lines: Nov 6 17:42 - Nov 9 14:36 +$1.00 = gold -3.00 + this +4.00, exact.  Nov 9 14:40 -
Nov 10 01:37 +$2.57 against +$1.00 here: $1.57, about 3 points at 0.5 lot on one of the two exits.

The backtest (`live_ai_real`) had 12 USTECm straddles on Nov 9 waiting for these prices that its AI review kept; the
live bot armed all 12 at the same moments, so their stop prices come from the log.  Result: the same three trades
as live (Qatari +$20, Nvidia +$20, Al Arabiya -$20 at today's 0.5 lot), the other 9 unfilled as live: +$20.00.
Updated `live_ai_real` totals: Jan 1 - Nov 9 -$704.45; last 30 days +$25.92.  The Nov 10 gold trades still need
XAUUSDm prices for Nov 10.
