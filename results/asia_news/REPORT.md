# Asian-session high-impact news bot (Python) - built on Jan-Jun 2026, tested on Jul-Oct 2026 and 2025

Bot: `bots/asia_news/` (Python package `newsbot/`, `run_bot.py`, `config.toml`, README; dry-run by default). Protocol:
`scripts/asia_news_lab.py` (committed before the build). One agent built it on Jan-Jun 2026 only; Jul-Oct 2026 was run
once by `final_test` (`final_test.json`); 2025 was run once afterwards as an extra exam.

## What it trades
* Forex Factory HIGH-impact releases of the Asian currencies (AUD, NZD, JPY; Forex Factory rates no CNY release high)
  between 21:45 and 07:00 UTC. In 2026: AUD CPI, employment, GDP, RBA cash rate; NZD CPI, employment, GDP, RBNZ cash
  rate; BoJ policy rate. About 32 tradable releases in Jan-Jun, 20 in Jul-Oct.
* Signal: Forex Factory's better / worse verdicts of the release's figures (actual vs forecast), summed; a split report
  is decided by the unemployment rate, then headline CPI; all in line = no trade.
* Entry 15 minutes after the release (the surprise is priced inside the release minute; entering in the next minute lost
  in every test), stop 1.5 x the average hourly range of the day before, no target, out after 6 hours, flat by Friday
  20:00 UTC, $1,000 at 10% risk per trade.
* Versions: the currency's own pair (AUDUSD, NZDUSD, USDJPY inverted); gold (bought on a bullish AUD / NZD / JPY
  surprise); Nasdaq (bought on bullish AUD / NZD, sold on a bullish yen).

## Results ($1,000, 10% risk per trade, Exness spreads, doubled in the first 5 minutes after a release)

| Version | Jan-Jun 2026 (built on) | Jul-Oct 2026 (test, run once) | 2025 (extra exam, run once) |
|---|---|---|---|
| Gold | 16 trades, +13.7R, PF 7.30, -17% - passed | 11, +0.05R, PF 1.01, -30%, $954 - **fails** | 38, -5.0R, PF 0.64, -59%, $549 - **fails** |
| Nasdaq | 16, +1.8R, PF 1.57 - failed (Apr-Jun < 0) | 11, +3.75R, PF 2.87, -16%, $1,401 - meets the rule | 38, -1.3R, PF 0.90, -47%, $785 - **fails** |
| Pair (AUD + NZD + JPY) | 19, +10.4R, PF 3.02, -19% - passed | 10, -3.5R, PF 0.47, -39% - **fails** | 41, -8.5R, PF 0.61, -69%, $351 - **fails** |

* **No version has an edge.** Nasdaq's Jul-Oct pass came from the same 11 calls as gold and did not repeat in 2025.
* What the data showed: the surprise is priced within the release minute (the pair's first minute agreed with the
  verdict in 13 of 15 releases); AUD / NZD data had no measurable effect on Nasdaq; gold's Jan-Jun result tracked gold's
  own trend (the agent flagged it before the test); all 11 central-bank decisions were exactly as forecast, so the yen
  never traded.
* Live use: the bot reads the schedule from Forex Factory's JSON feed and the actual from the Forex Factory page in
  headless Chromium. From this machine the feed worked (after HTTP 429 retries) but the page was blocked by Cloudflare,
  so the live actual reader is untested against the real page; the actual source can be replaced. 15 unit tests pass,
  including the MT5 broker against a fake MetaTrader5 module (the real package runs on Windows only).

## Nasdaq v2 - "pair reaction" entry (built Nov 5 2026)

Brief: make the Nasdaq version more profitable by trying different entries on Jan-Jun 2026 only, then test once on
Jul-Oct 2026. One agent did the build (`bots/asia_news/research_nq.md`, scripts in `bots/asia_news/lab/`); the rules
were locked in `bots/asia_news/LOCKED_NQ.json` before `final_test(tag="nasdaq_v2")` (`nasdaq_v2.json`); 2025 was run
once afterwards (`exam2025_nasdaq_v2.json`).

**Rule:** at each Forex Factory high-impact AUD / NZD release in 21:45-07:00 UTC, look at the currency's own pair
(AUDUSD / NZDUSD) from the close before the release to release + 2 min. Currency stronger -> buy NAS100, weaker ->
sell, at release + 2 min. Stop 2 x the hourly ATR(24), no target, out after 6 h (Friday 20:00 UTC at the latest).
No actual is needed, so the bot no longer depends on scraping the Forex Factory page; JPY is out (the BoJ minute is
not known in advance).

Entries tried on Jan-Jun 2026 (one representative each; full grids and placebo tests in research_nq.md):

| Entry idea | Jan-Jun 2026 | Passes build rules |
|---|---|---|
| v1: FF verdict, entry +15 min | 16 trades, +1.8R, PF 1.57 | no |
| FF verdict, entry +3 min | 16, +3.3R, PF 3.56 | yes |
| Only big surprises / all figures agreeing | 5-6 trades, -0.5 to +0.2R | no (went the wrong way) |
| FF verdict confirmed by NAS100 at +5 min | 10, +3.2R, PF 10.5 | no (too few trades) |
| **Pair reaction at +2 min (chosen)** | **24, +4.4R, PF 2.97, -7%** | **yes** |
| NAS100 release-minute momentum | 26, +8.3R, PF 2.87 | yes, but -3.8R if read 1 minute later |
| Breakout of the first 3 minutes | 28, +11.3R, PF 2.41 | yes |
| Breakout of the first 15 minutes | 24, -4.1R | no |
| Fade the first 5 / 15 minutes | -4.3R / +4.0R | no / yes |
| Limit at 50% pullback of the first 10 minutes | 15, +8.3R, PF 2.57 | yes |
| Straddle of the pre-release range | 25, +7.4R, PF 2.62 | yes |
| Fade the previous US session | 29, -3.4R | no |

The agent chose the pair reaction over higher-R ideas because it held up best when settings were shifted and has a
reason behind it. It also found that NAS100 itself does not move more at these releases than at the same minute on
other days, and that running the same search on a calendar with no news also finds "passing" rules (p ~ 0.03-0.3).

| Nasdaq v2 | Trades | R | PF | Max DD at 10% | $1,000 -> | Rule | Result |
|---|---|---|---|---|---|---|---|
| Jan-Jun 2026 (built on) | 24 | +4.41 | 2.97 | -7.2% | $1,507 | build rules | passes |
| Jul-Oct 2026 (test, run once) | 13 | +2.34 | 2.24 | -15.9% | $1,236 | >= 8 trades, R > 0, PF >= 1.3, DD > -35% | **meets it** |
| Jul-Oct at 2x cost | 13 | +2.14 | 2.10 | -16.2% | | | |
| 2025 (extra exam, run once) | 47 | +0.26 | 1.02 | -46.2% | $942 | R > 0, PF >= 1.2 | **fails** |
| 2025 at 2x cost | 47 | -1.41 | 0.88 | -53.8% | $794 | | |

* **No demonstrated edge.** The Jul-Oct pass rested on 2-3 trades (+0.38R without the best two) and Jul-Oct had been
  used once before (v1's test). Over 2025's 47 trades it broke even: Jan-Sep lost 5.2R, Oct-Dec made 5.5R, and the
  drawdown at 10% risk was -46%.
* Buying NAS100 at the same entries regardless of the pair made more in 2025 (+2.24R, PF 1.24) and almost as much in
  Jan-Jun (+4.01R): the AUD / NZD reaction says nothing useful about Nasdaq's direction.
* The bot works: 21 unit tests pass, the backtest reproduces the build and the Jul-Oct numbers trade for trade, and the
  live loop replayed minute by minute over Jan-Jun takes the same 24 trades. Run it in dry-run only
  (`python run_bot.py`, config.toml now points at LOCKED_NQ.json; `locked_file = "LOCKED.json"` runs v1).

