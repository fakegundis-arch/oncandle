# Telegram news channels - how fast do they post? (measured Nov 6 2026)

Goal: find the Telegram channels that post market-moving news within seconds, as the source for a news-trading bot on
gold and Nasdaq. This file is step 1 (speed). Step 2 will backtest their past posts against XAUUSD / NAS100.

## Method

* 40 scheduled high-impact releases, Sep 1 - Nov 6 2026 (Forex Factory calendar; 12 of them US: NFP x3, CPI x2,
  PPI x2, FOMC x2, ISM, GDP / PCE x2), plus ECB, BoE, BoC, RBA, RBNZ, SNB decisions and UK / CA / AU / NZ data.
* For each channel, every post from 60 s before to 15 min after each release was read from the channel's public web
  preview (t.me/s/<channel>), which gives the post time to the second (`scripts/telegram_news/speedtest.py`).
* Delay = time of the channel's first headline that names the release (keyword in the headline, a number for data,
  the right country; English and Russian terms) minus the scheduled release time
  (`scripts/telegram_news/rescore.py`). Per-release detail: `speed_by_release.csv`; table: `summary.txt`.
* Raw posts are kept locally in `data/telegram/speedtest/` (git-ignored).

## Results

| Channel | Handle | Subscribers | Releases posted (all / US) | Median delay | Within 10 s | Within 30 s | Range |
|---|---|---|---|---|---|---|---|
| Tree News | @TreeNewsFeed | 35k | 3 / 3 | **3 s** | 3 | 3 | 2-4 s |
| BWEnews (reposts Tree News) | @BWEnews | 72k | 3 / 3 | 4 s | 3 | 3 | 4-7 s |
| Newsmaker | @nwsmkr | 21k | 10 / 10 | **10 s** | 6 | 8 | 5-55 s |
| MarketTwits (Russian text, English data tags) | @markettwits | 341k | 25 / 12 | **12 s** | 11 | 21 | 3-112 s |
| unfolded | @unfolded | 117k | 4 / 4 | 14 s | 1 | 4 | 3-14 s |
| Watcher Guru | @WatcherGuru | 632k | 7 / 7 | 16 s | 0 | 5 | 11-263 s |
| Market News Feed | @marketfeed | 40k | **40 / 12** | 28 s (US 23 s) | 3 | 21 | 9-74 s |
| Breaking Market News (FinancialJuice mirror) | @BreakingMarketNews | 5k | 37 / 12 | 29 s | 0 | 20 | 25-111 s |
| FinancialJuice | @financialjuice | 8k | 36 / 12 | 31 s | 0 | 15 | 26-114 s |
| Walter Bloomberg | @WalterBloomberg | 34k | 19 / 12 | 35 s (US 28 s) | 1 | 7 | 9-169 s |
| FXStreet Forex News | @fxstreetforex | 103k | 35 / 10 | 90 s | 0 | 1 | 24-724 s |
| Insider Paper | @insiderpaper | 108k | 4 / 4 | 246 s | 0 | 0 | 141-297 s |
| Exness | @brokerexness | 14k | 0 | - (market commentary, no news flashes) | | | |
| FXGoldVision | @FXGoldVisionMarkets | 6k | 0 | - (signals / analysis) | | | |

Highlights per release: Fed decisions - MarketTwits 3 s (twice), Tree News 3 s, Newsmaker 5-10 s, Walter Bloomberg
9-13 s; NFP - MarketTwits 8-12 s, Newsmaker 9-24 s, Walter Bloomberg 22-61 s, FinancialJuice 40-56 s; CPI - Tree News
2-4 s, Newsmaker 6 s, MarketTwits 17-27 s, Watcher Guru 11-14 s.

Not testable from the public preview: @FinancialWorldUpdates (20k), @zerohedge (15k), the ForexLive / InvestingLive
group, and private / paid channels (e.g. the "BigLiquid Pro" channel Newsmaker credits).

## Reading of the results

* Fast and broad: **MarketTwits** (all 12 US releases plus ECB / BoE / BoC; 3-12 s on Fed / NFP / ECB / BoE) and
  **Newsmaker** (US only, 5-10 s typical). Fastest of all on what it covers: **Tree News** (2-4 s, only the
  biggest US releases).
* Complete but slower: **Market News Feed** posts every release (median 28 s) - a full-coverage baseline.
* FinancialJuice's Telegram channel runs about 30 s behind the release (its own site / squawk is faster).
* Even 3 s is late for the first price jump: banks and funds get these numbers from machine-readable feeds in
  milliseconds. The backtest has to enter at post time + the bot's own delay and measure what is left of the move.
* Unscheduled news (e.g. posts by politicians, geopolitics) was not measured here; that needs the source's own time.

# Unscheduled news - who posts surprise market news first? (measured Nov 7 2026)

Telegram only. 16 public channels, every post from Sep 15 to Nov 6 2026 (about 76,000 posts, `tg_history.py`; kept
locally in `data/telegram/history/`, git-ignored). `unscheduled.py` groups posts of different channels about the same
story (same distinctive words within 20 minutes). A story counts when 3+ channels posted it. Stories near scheduled
calendar events and anything that reads like a data release or a preview are dropped: **1,509 surprise stories**.
"Market-shaking" (Sep 15 - Oct 15, where price data exists): calm in the 15 minutes before the first post, then NAS100
or gold moved at least 2x a normal 15-minute move in the 15 minutes after it: **189 stories**.

| Channel | Handle | Surprise stories posted | First to post | Median seconds behind the first | Within 30 s of the first |
|---|---|---|---|---|---|
| FinancialJuice | @financialjuice | 1,190 | **645 (54%)** | 0 | 891 |
| Walter Bloomberg | @WalterBloomberg | 868 | 381 (44%) | 22 | 454 |
| Market News Feed | @marketfeed | 1,477 | 253 (17%) | 11 | 1,306 |
| Clash Report (war) | @ClashReport | 490 | 67 (14%) | 252 | 86 |
| MarketTwits | @markettwits | 328 | 50 (15%) | 93 | 91 |
| Watcher Guru | @WatcherGuru | 106 | 18 | 299 | 20 |
| Insider Paper | @insiderpaper | 113 | 16 | 457 | 17 |
| BRICS News | @BRICSNews | 142 | 13 | 333 | 15 |
| Rerum Novarum | @rnintel | 86 | 11 | 384 | 12 |
| Newsmaker | @nwsmkr | 67 | 11 | 42 | 27 |
| Intel Slava (war) | @IntelSlava | 50 | 5 | 584 | 6 |
| Tree News / BWEnews | @TreeNewsFeed / @BWEnews | 11 / 35 | 8 / 21 | 0 | mostly crypto stories |

Market-shaking stories only (189): FinancialJuice first on 87 (56%), Walter Bloomberg 51 (44%), Market News Feed 29;
Clash Report 8; MarketTwits 3; the big war / general channels 0-1.

Head to head (stories both posted; `unscheduled_head_to_head.csv`):
* FinancialJuice beat Walter Bloomberg 56% of the time (median 20 s earlier), Market News Feed 62% (6 s), MarketTwits
  87% (76 s), Clash Report 88% (4 min), Watcher Guru 94% (4 min), BRICS News 98% (6 min), Intel Slava 94% (10 min).
* Walter Bloomberg vs Market News Feed: a tie (51 / 49%, 2 s). Walter Bloomberg beat Clash Report 76% (3 min).
* Clash Report beats the other war channels (Intel Slava 88%, Rerum Novarum 65%) and is sometimes first on battlefield
  events (e.g. Iran shooting down a US drone: 12 minutes before FinancialJuice).

Reading: the fast tier is FinancialJuice + Walter Bloomberg (together first on about 2 of 3 surprise stories), with
Market News Feed a few seconds behind as a catch-all. The big audience channels (Watcher Guru 632k, Intel Slava 386k,
BRICS News 154k, Rerum Novarum 161k, Insider Paper 108k) post the same stories 3-10 minutes later - the gap the
strategy wants to use. Limits: "first" means first among these Telegram channels, not the original source (wires,
terminals, officials' own accounts are earlier); the price check is at 1-minute resolution, so a move that starts in the
same minute as the first post is not separated; story matching is by shared words, so Russian-language channels are
undercounted.

# Backtest: a bot trading FinancialJuice + Walter Bloomberg headlines on gold and Nasdaq (Nov 7 2026)

Protocol and engine: `scripts/telegram_news/newsbot_lab.py` (committed before any run), grid `newsbot_build.py`.
* Posts: 47,687 FinancialJuice + 16,035 Walter Bloomberg posts, Jan 1 - Oct 31 2026. Tradable = surprise headlines only
  (no scheduled data / previews, nothing from 2 min before to 15 min after a calendar release or 60 min after the start
  of a speech / press conference, first post of a story, topic: war / energy / Fed officials / trade / politics / China).
* Prices: Exness's own tick history (XAUUSDm, USTECm), one-second bid / ask - real spreads, including news widening.
* Bot: sees the post 2 s after it appears, market order at the real ask / bid; stress test 5 s + one spread slippage.
  Direction from price momentum, its fade, the headline's words, or words + momentum. $1,000, 10 % risk per trade.
* Built on Jan-Jun 2026 (4,680 settings per instrument), tested once on Jul-Oct 2026.
* Two bugs were found and fixed before the test (whole-word matching; the calendar window was inverted, which let
  scheduled FOMC posts in); the first grid's picks were discarded (commits 78b3cc7, a95e916).

Jan-Jun: almost everything loses - median profit factor 0.67-0.90 per direction family; only 4 gold and 2 Nasdaq
settings out of 4,680 passed the build rules (what chance alone produces in a search this size).

| Locked bot (picked on Jan-Jun) | Jan-Jun (built on) | Jul-Oct 2026 (unseen, run once) | Jul-Oct at 5 s + slippage |
|---|---|---|---|
| Gold: headline words + momentum agree, Fed-official headlines, 5 min hold | 99 trades, +6.6R, PF 1.39, -27%, $1,650 | **85 trades, -6.8R, PF 0.67, -62%, $446 - fails** | -9.6R, PF 0.56, $338 |
| Nasdaq: momentum, Fed-official headlines, 5 min hold | 40 trades, +12.4R, PF 2.35, -17%, $2,900 | **33 trades, -4.4R, PF 0.63, -51%, $597 - fails** | -8.1R, PF 0.40, $412 |
| Secondary (declared before the test): gold momentum after war / energy headlines, 30 min hold | 1,218 trades, +198R, PF 1.24, but -100% at 10% risk | **844 trades, -126R, PF 0.80: account wiped out at 10%; at 1% risk $239 (-85%)** | -209R, PF 0.68 |

Reading: no version holds up on unseen months. Jan-Jun's best patterns were the lucky few of 4,680 tries; Jul-Oct
lost in 10 of the 12 instrument-months. By the time these channels post (seconds after the wires), the first reaction
is already in the price; what follows is as likely to reverse as to continue. Tight stops do not protect in news
spikes: the secondary's worst trade lost 17.7x its planned risk when gold gapped through the stop. Results:
`newsbot_test.json`, `newsbot_secondary_test.json`, grids `newsbot_grid_*.csv`, build log `newsbot_build.txt`.

## The secondary candidate in detail (gold after war / energy headlines)

Chart: `secondary_performance.png`; every trade with its headline: `secondary_trades.csv`.

| | Jan-Jun (built on) | Jul-Oct (unseen) |
|---|---|---|
| Trades | 1,218 | 844 |
| Win rate | 32% | 25% |
| Average win / loss | +2.61R / -0.97R | +2.43R / -1.02R |
| Total | +198R, PF 1.24 | -126R, PF 0.80 |
| Longest losing streak | 17 | 16 |
| $1,000 at 10% / 2% / 1% / 0.5% risk | $44 / $15,974 / $5,300 / $2,484 | $0 / $41 / $239 / $509 |
| Max drawdown at 1% risk | -35% | -85% |

Engine flaw found here (it does not change the verdict): the backtest had no "flat before the market closes" rule, so
17 trades opened late on Fridays or just before the daily break were held to the reopen (up to 49 hours) - they hold the
best (+24R) and the worst (-17.7R) trades. Without them: Jan-Jun +142R (PF 1.18), Jul-Oct -119.5R (PF 0.81).

# Straddle version (Nov 7 2026)

Protocol and engine: `scripts/telegram_news/straddle_lab.py` (committed before any run), grid `straddle_build.py`.
When the bot reads a tradable FinancialJuice / Walter Bloomberg headline (same rules as above) it places a buy stop
above and a sell stop below the price, one cancels the other. Fills at the level or worse plus one spread of
slippage (stress: two, read 5 s late); the worse leg when both trigger in one second; flat before the daily / weekend
close. 2,592 settings per market: offset 0.5 / 1 / 2 / 3 x the typical 1-minute move, around the current price or the
price 30 s before the post, orders live 1 / 5 / 15 min, stop at the other level or 2 / 4 x the typical move, target
none / 1R / 2R, out after 5 / 15 / 30 min, four topic groups.

| Jan-Jun 2026 (built on) | Gold | Nasdaq |
|---|---|---|
| Settings passing the build rules | **0 of 2,592** | **0 of 2,592** |
| Settings that made money at all | 7 | 0 |
| Typical profit factor | 0.72 | 0.53 |
| Typical result per trade | -0.11 to -0.24R (wider straddles lose less) | -0.24 to -0.41R |

No setting passed, so there is no straddle bot to trade. Information-only check, declared before running
(`straddle_locked.json`): the best gold straddle of Jan-Jun (offset 3x, around the price 30 s before the post, orders
live 1 min, stop at the other level, out after 30 min, war / energy headlines: 1,364 trades, +63R, PF 1.08, wiped out at
10% risk) on Jul-Oct 2026: **988 trades, -90.6R, PF 0.85, win 33%; wiped out at 10% risk; $362 at 1%, $618 at 0.5%**
(stress: -160R, PF 0.76). Every month lost. `straddle_best_gold_info_test.json`.

Reading: a straddle does not need to know the direction, but it pays the spread plus slippage on every fill and is
triggered by noise as often as by real moves. After these headlines the move that would carry a straddle has mostly
happened already (the wires were faster), so the triggers that follow are as likely to reverse as to continue.

# Fixed-distance straddle - the user's design (Nov 7 2026)

When the bot reads a tradable FinancialJuice / Walter Bloomberg headline: buy stop at the price + p, sell stop at the
price - p (gold at 4,670 with p = $5: 4,675 / 4,665), one cancels the other. p is a percent of the price:
0.05 / 0.10 / 0.15 / 0.20 / 0.30 / 0.45 % (about $2.3 / 4.7 / 7.0 / 9.3 / 14 / 21 on gold at 4,670; 13 / 26 / 39 / 51 /
77 / 116 points on Nasdaq at 25,670). Same fills (+1 spread slippage), stress test, both-legs rule and flat-before-close
as the straddle above. 1,296 settings per market. Protocol `scripts/telegram_news/straddle_fixed_lab.py` (committed
before any result); built on Jan-Jun 2026, one run on Jul-Oct 2026.

Jan-Jun: gold 0 of 1,296 settings passed (median PF 0.87; 217 made money; best distance ~0.2 %); Nasdaq 1 of 1,296
(median PF 0.79; wider was better).

| | Jan-Jun 2026 (built on) | Jul-Oct 2026 (unseen, run once) |
|---|---|---|
| **Nasdaq pick** (0.45 % ~ 116 pts each side, orders 5 min, stop at the start price, 1R target, 5 min hold, all headlines) | 46 trades, +3.6R, PF 1.40, DD -23%, $1,328 | **10 trades, -1.5R, PF 0.34, $853 - fails** (too few trades, loses) |
| **Gold, info-only** (0.10 % ~ $4.7 each side, orders 1 min, stop at the other order, 2R target, 30 min hold, war / energy headlines) - did NOT pass the build rules | 762 trades, +57.5R, PF 1.14, win 40%; at 10% risk wiped out (-100%); at 2% $2,437 (-47%); at 1% $1,665 (-27%) | **145 trades, +22.5R, PF 1.35, win 49%; at 10% $3,631 after a -73% drawdown; at 2% $1,506 (-21%); at 1% $1,239 (-11%)**; stress +14.4R, PF 1.21 |

The gold result is the first positive unseen result of the news bots, but it is not a validated edge:
* it was the best of 1,296 settings and failed the build rules (10% risk wiped the account out in Jan-Jun);
* its Jul-Oct profit is concentrated: July +18.8R (+12R on Jul 7-8 alone); Aug-Oct +3.6R on 105 trades; without its
  10 best trades +2.4R;
* gold moved less after headlines in Jul-Oct: 36 trades a month vs 127 in Jan-Jun, with as many headlines;
* Jul-Oct had already served as the test of the earlier news bots (not of this design).
Next honest step: an untouched period (2025) and a forward test on a demo account, at 1-2% risk.
Results: `straddle_fixed_test.json`, `straddle_fixed_gold_info_test.json`, grids `straddle_fixed_grid_*.csv`.

# Nasdaq +/-30-point straddle - the user's design (Nov 7 2026)

Nasdaq at 26,700 -> buy stop 26,730, sell stop 26,670 when the bot reads a tradable FinancialJuice / Walter Bloomberg
headline; one cancels the other; same fills (+1 spread), stress test and flat-before-close as above. Distance fixed at
30 points; 216 settings of order life, stop (at the other order = 60 pts, or back at the start = 30 pts), target, hold
and topics. Protocol `scripts/telegram_news/straddle_points_lab.py` (committed before any result).

Jan-Jun 2026: **0 of 216 settings passed**; median PF 0.78; only 7 made money. No pick. Declared info-only run of the
highest-R setting (Fed headlines, orders live 1 min, stop back at the start price, no target, out after 30 min):

| | Jan-Jun 2026 (built on) | Jul-Oct 2026 (unseen, run once) |
|---|---|---|
| Trades / R / PF / win | 65 / +23.9R / 1.49 / 23% (Jan-Mar -12.7R, Apr-Jun +36.6R) | **27 / -10.4R / 0.53 / 19%** |
| $1,000 at 10% risk | $1,520 after a -89% drawdown | **$253 (-86%)** |
| $1,000 at 2% / 1% | $1,452 (-31%) / $1,236 (-17%) | $800 (-30%) / $898 (-17%) |

It loses on the unseen months (Jul -8.5R, Aug -6.4R, Sep -2.0R, Oct +6.5R). `straddle_nas30_info_test.json`,
grid `straddle_nas30_grid.csv`.
