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
