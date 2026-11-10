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
