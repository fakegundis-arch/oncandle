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
