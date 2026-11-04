# newsbot - Asian-session high-impact news bot (Python + MetaTrader 5)

Trades Forex Factory **high-impact** releases of **AUD, NZD, JPY (CNY)** published in the Asian session
(21:45-07:00 UTC): Australian CPI / jobs / GDP / RBA, New Zealand CPI / jobs / GDP / RBNZ, BoJ decisions.
At each release it reads the actual, compares it with the forecast (Forex Factory's own better / worse verdict),
decides whether the currency is bullish or bearish, and trades one of three versions:

| version | instrument | bullish currency means |
|---|---|---|
| `pair` | AUD -> AUDUSD, NZD -> NZDUSD, JPY -> USDJPY | buy AUDUSD / NZDUSD, **sell** USDJPY (stronger yen) |
| `gold` | XAUUSD | buy gold (AUD, NZD, JPY alike) |
| `nasdaq` | NAS100 | buy for AUD / NZD, sell for JPY |

> **Status after the out-of-sample test (Jul 1 - Oct 15 2026, run once on the locked settings):**
> pair 10 trades, -3.5 R, PF 0.47, max drawdown -39 % (fail); gold 11 trades, +0.05 R, PF 1.01 (fail);
> Nasdaq 11 trades, +3.8 R, PF 2.87 (formally passes, but it failed the build rules and took the very same calls as
> gold, so it is not evidence of an edge). **No version has a demonstrated edge - do not trade it with real money.**
> The bot itself works (its live loop reproduces the backtest trade for trade); use it in dry-run / signal-only
> mode. Details in `research.md`.

## The rules (frozen in LOCKED.json)

1. Each figure of the release votes +1 (better for the currency), -1 (worse) or 0 (in line) - Forex Factory's
   verdict, or the sign of actual - forecast when FF gives none (unemployment rate: lower is better). Figures
   published in the same minute are one release. A split report (votes cancel) is decided by the unemployment
   rate, then headline CPI. Everything in line (e.g. an expected rate decision) -> no trade.
2. Entry **15 minutes after the release** at market (the first-minute spike and its pull-back are over, the news
   spread has normalised, and the actual has had 15 minutes to arrive).
3. Stop = 1.5 x the average true range of the 24 hourly bars before the release; no target; close **6 hours after
   the entry** (Friday 20:00 UTC at the latest - never over a weekend). One position per instrument.
4. Size: the stop loses **10 % of equity** (lot size from `order_calc_profit`, rounded down; skipped if the
   minimum lot would risk more).

## Files

```
run_bot.py         main loop (dry-run by default)            config.toml   operational settings
run_backtest.py    Jan-Jun 2026 backtest of LOCKED.json       LOCKED.json   frozen strategy settings
newsbot/events.py  figure parsing, grouping into releases    newsbot/signal.py    actual/forecast -> bias -> direction
newsbot/strategy.py trade plan (stop, exit) - shared by the backtest and the live bot
newsbot/backtest.py M1 simulation with the protocol's costs   newsbot/feeds.py     FF weekly JSON + FF page actuals
newsbot/broker.py  MetaTrader 5 broker + dry-run book         newsbot/bot.py       the live loop
newsbot/replay.py  replays history through the live loop      research/            the study scripts
tests/             unit tests (pytest)
```

## Setup (Windows, MetaTrader 5)

1. Install MetaTrader 5 from your broker, log in, and enable *Tools > Options > Expert Advisors > Allow algorithmic
   trading*. Show the symbols you need in Market Watch (Exness: `XAUUSDm`, `USTECm`, `AUDUSDm`, `NZDUSDm`,
   `USDJPYm` - edit `[symbols]` in config.toml for other brokers).
2. Python 3.11+ (64-bit) and the packages:
   ```
   pip install MetaTrader5 pandas numpy requests playwright
   playwright install chromium
   ```
3. Edit `config.toml`: `[mt5]` login / password / server (or leave empty to use the logged-in terminal),
   `server_utc_offset_hours` (Exness 0; many brokers 2 or 3 - it converts bar times to UTC), the versions to run.
   Keep the PC clock synchronised (the schedule is in UTC from the system clock).

## Run - dry-run first

```
python run_bot.py --schedule          # this week's target releases and what "better" / "worse" would trade
python run_bot.py --signal-only       # no MT5: polls the calendar, reads actuals, logs the signal only
python run_bot.py                     # DRY-RUN: real MT5 prices, sizes and stops, orders only logged
python run_bot.py --live              # real orders - ONLY if config.toml also says mode = "live"
```

Run the dry-run through several releases (AUD CPI is monthly, AUD jobs monthly, NZD quarterly) and compare the
log (`logs/newsbot.log`, journal `logs/trades.csv`) with what the market did. The bot persists its state in
`state/` - a restart neither repeats a trade nor forgets an open position (the broker-side stop protects a position
while the bot is down; restart it to get the time exit).

To check the code path without waiting for news: `python research/check_replay.py` (needs the research repo) replays
Jan-Jun 2026 minute by minute through the live loop and confirms it takes exactly the backtest's trades;
`python -m pytest tests` runs the unit tests; `python run_backtest.py` reproduces the build numbers.

## Data sources, latency and blocking - be realistic

* **Schedule** (time, forecast, previous): Forex Factory's public weekly export
  `https://nfs.faireconomy.media/ff_calendar_thisweek.json`. FF updates it hourly and answers HTTP **429 "Request
  Denied"** when it is requested more than a few times per five minutes (this happened from the build machine; a
  later request returned the week's 115 events and the bot parsed the two Asian target releases correctly). The
  bot downloads it at most once per hour and works from the cached copy (`state/ff_thisweek.json`).
* **Actual**: the export has no actual values. The bot loads the Forex Factory calendar page of the day in headless
  Chromium (Playwright) and parses the event JSON embedded in the page (`actual`, `forecast`, `previous`,
  `actualBetterWorse`), polling every 10 s from the release time. FF typically posts the number within a minute; a
  page load takes 3-10 s. If no actual arrives within 10 minutes the release is skipped. Because the entry is 15
  minutes after the release, this latency costs nothing - the bot is deliberately **not** a speed trader (the
  research shows the first-minute move is gone before any retail bot could act on it).
* **Forex Factory sits behind Cloudflare.** From the build machine a headless Chromium got the "Just a moment..."
  challenge page (HTTP 403) instead of the calendar. From a home PC it may work or it may not, and it can stop working
  any day; scraping may also be against FF's terms of use - check them. The actual source is pluggable
  (`newsbot/feeds.py`, any object with `fetch(release_time, currency) -> rows`): `actual_source = "file"` reads
  `state/actuals.json`, which you (or another program / a paid calendar API) can fill. If the actual source fails,
  the bot simply does not trade - it never guesses.

## Risks - read before going live

* **10 % of equity per trade is very aggressive.** Four losses in a row cost 34 %; the Jan-Jun build had a worst
  drawdown of 17-19 % and that is the in-sample *best case*. Consider 1-2 % until the dry-run and a small live run
  match the backtest.
* **Small sample.** The build period had 19 tradable releases; out-of-sample there are ~10-15 in 3.5 months. A
  handful of trades decides the year. The statistics in research.md cannot prove an edge.
* **Gold and Nasdaq have no causal link to Australian / New Zealand data.** The gold result in the build period was
  mostly gold's own trend lining up with the AUD data surprises; Nasdaq showed no relation at all. See research.md for
  the out-of-sample verdict before running these two versions.
* Costs: the backtest assumes the protocol's spreads (AUDUSD 1.5 pips, NZDUSD 2, USDJPY 1.5, gold $0.25, NAS100 1.5
  points; double inside 5 minutes of a release). Check your broker's real spreads at 00:30-02:00 UTC; NZD and the
  21:45 UTC releases fall right after the daily rollover when spreads are widest, and gold / Nasdaq can be closed then
  (the bot skips an entry that does not get a quote within 2 minutes).
* The time exit needs the bot running; the stop does not (it is set on the order).
* MT5's Python API is Windows-only; run the bot on the same PC as the terminal. Use a demo account first.
* Nothing here is investment advice.
