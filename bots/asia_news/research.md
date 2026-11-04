# Asian-session high-impact news bot - research log

Status: FINAL (Nov 4 2026). Build Jan-Jun 2026, settings locked in LOCKED.json, final_test (Jul 1 - Oct 15 2026) run
once. Short version: section 6.

Protocol: scripts/asia_news_lab.py (build on Jan-Jun 2026 only; one final_test on Jul 1 - Oct 15 2026).
All research scripts live in `research/`; the bot in `newsbot/`. Everything is run from /home/user/oncandle with
PYTHONDONTWRITEBYTECODE=1.

## 1. The events (Jan-Jun 2026)

`asia_news_lab.asia_high(calendar_train())` gives 87 lines; grouped by (currency, minute) and keeping only lines
with a number (no speeches / statements / press conferences) there are **32 releases**:

| currency | releases | of which |
|---|---|---|
| AUD | 19 | 7 CPI (monthly CPI m/m + y/y + trimmed mean m/m), 6 labour force (employment change + unemployment rate), 2 GDP, 4 RBA cash rate |
| NZD | 9 | 2 CPI q/q, 2 labour (employment change q/q + unemployment rate), 2 GDP, 3 RBNZ OCR |
| JPY | 4 | BoJ policy rate |
| CNY | 0 | (no CNY event is rated high impact) |

* Every central-bank decision (11) came out exactly as forecast (RBA hiked 3 times as expected, BoJ hiked once in
  June as expected) - FF verdict 0 for all of them. JPY therefore never has a surprise in the build period.
* Of the 21 data releases, 15 have a non-zero sum of FF verdicts, 4 are split labour reports (unemployment rate
  and employment change disagree), 2 are fully in line (AUD jobs 16 Apr, NZD GDP 18 Jun).
* FF's verdict has a materiality threshold: AUD employment 17.9K vs 19.1K forecast is marked 0 (in line).
* Releases come at 00:30 UTC (AUD, Jan-Mar), 01:30 UTC (AUD, Apr-Jun), 21:45 / 22:45 UTC (NZD), 03:00-04:30 UTC
  (RBA / BoJ / RBNZ). In Jan-Feb NAS100 is closed at 21:45 UTC (opens 23:00) and gold closes 22:00-23:00, in
  mid-March gold is closed at 21:45 too - those NZD releases cannot be traded on those instruments.

## 2. How the markets react (study1_reactions.py -> research/reactions.csv)

Moves measured from the earliest tradable price (open of the minute after the release minute), in multiples of the
protocol's base spread COST (AUDUSD 1.5 pips, NZDUSD 2 pips, USDJPY 1.5 pips, gold $0.25, NAS100 1.5 pts).
"r0" = the release-minute move (close before the release -> entry open), which the bot cannot capture.

Typical size of an hour's range in cost units (Jan-Jun 2026): gold 106, NAS100 64, USDJPY 12.6, AUDUSD 8.4,
NZDUSD 5.2. **The pairs are 10-20x more expensive relative to their movement than gold**: one AUDUSD hour is
8 spreads, a release entry pays 2.

Findings:
1. **The surprise is priced inside the release minute.** The sign of the release-minute move of the pair agrees with
   the FF verdict in 13 of the 15 releases with a non-zero verdict sum (exceptions: AUD GDP 4 Mar, AUD CPI 24 Jun).
   Typical r0 = 4-14 spreads (6-20 AUDUSD pips).
2. **No continuation after the entry in the pair.** Signed by the FF verdict, the pair's average move after the
   entry is -1.1 (5 min), -2.4 (15 min), -1.3 (60 min), -0.1 (240 min) spreads; for AUD alone the 15-minute move is
   against the surprise in 9 of 12 releases (the first-minute spike partly retraces), but by only ~3 spreads.
   Signed by the market's own first-minute direction instead: +0.4 (15 min), +1.4 (60 min), +3.3 (240 min) - nothing
   that survives 2 spreads of cost.
3. **Gold and Nasdaq**: AUD / NZD data cannot move them in any causal way and the numbers agree: Nasdaq's moves signed
   by the AUD verdict average ~0 at every horizon. Gold signed by the AUD verdict (bullish AUD -> long gold) shows
   +41 spreads at 60 min, +76 at 240 min (n=12, 67-75% positive), but with a 4-hour standard deviation of ~200 spreads
   that is ~1.3 standard errors, and gold's own trend (up to February, down from March) is a large part of it.
   NZD (n=3) points the other way.
4. Unconditional drift: on all Jan-Jun weekdays the 00:00-06:00 UTC change is ~0 for gold and Nasdaq (median Nasdaq
   +9 spreads, 60% up days).
5. **Path after the release (signed by the FF verdict, 19 releases incl. split reports, study in research/):**
   the pair's release-minute move averages +5.5 spreads; it gives back ~1.5 spreads in the next 15 minutes (the
   spike partly retraces) and then **drifts in the surprise direction for hours**: measured from the open 15 minutes
   after the release, +1.4 (30 min), +3.1 (90 min), +4.2 (5 h), +6.6 (6 h), +8.2 (7 h) spreads, 63-74% positive,
   t ~ 2.5 at 6 h. This is the classic post-announcement drift (rate expectations keep adjusting through the
   session). Gold signed by the AUD/NZD verdict drifts the same way (+64 spreads at 6 h, 84% positive, t ~ 1.5) but
   gold has no causal link to AUD data and its direction coincides with gold's own 10-20 day trend in 72-83% of
   these releases (Jan-Feb: strong AUD data and gold rallying; Apr-Jun: weak AUD data and gold falling).
   Nasdaq: nothing at any horizon.
6. **Split labour reports**: when the unemployment rate and employment change disagree, the release-minute move
   followed the unemployment rate in all 4 cases (AUD 19 Feb, 19 Mar; NZD 3 Feb, 5 May, the NZD ones only weakly).
   This is the usual market convention (the unemployment rate is the headline, Australian employment change is
   notoriously noisy) and is used as a tie-break - it is decided by the release-minute reaction, not by the P&L.

## 3. Rule search (Jan-Jun 2026 only)

Engine: `newsbot/backtest.py` (the bot's own code). Costs exactly as the protocol: long buys at bid + cost, short sells
at the bid and exits at bid + cost; a trade entered within 5 minutes of the release pays 2 x the spread (for a short
the wide spread is charged on its exit, so it cannot dodge it); stop before target inside a minute, the entry minute
can only stop out, gaps fill at the open; one position per instrument; flat by Friday 20:00 UTC; an entry is skipped
when the market is not quoting (NAS100 21:45 UTC in winter, gold 22:00-23:00 UTC daily break).
Stops are volatility-scaled: k x ATR of the 24 hourly bars before the release.

### 3a. First attempt - trade at the earliest possible minute (entry = open of release minute + 1)
FF verdict sum, bullish -> buy the pair / buy gold / buy Nasdaq, stop 1 x ATR(H1), target 2R, time exit 2 h:

| version | n | R | PF | Jan-Mar R | Apr-Jun R | PF 2x cost | PF late | pass |
|---|---|---|---|---|---|---|---|---|
| gold | 14 | +6.8 | 2.68 | +6.2 | +0.6 | 2.63 | 2.74 | no (n<15) |
| nasdaq | 13 | +1.0 | 1.35 | +1.7 | -0.8 | 1.19 | 1.57 | no |
| pair (AUDUSD+NZDUSD+USDJPY) | 15 | -0.3 | 0.96 | -3.9 | +3.6 | 0.19 | 0.67 | no |

The pair loses at the first minute in every exit setting tried (768-config grid, research/grid.py: 0 % of the
entry-at-minute-1 configs pass, median PF 0.80, median PF at 2x cost 0.28): the surprise is already in the price and
the double spread eats the rest.

### 3b. Grids (research/grid.py, 768 configs per version: signal ff / ff+tie-break, confirm 0/1, entry delay 1/15/30
min, stop 0.5/1/1.5/2 x ATR, target 1/2/3R/none, hold 60/120/240/360 min)

* ff without tie-break: never 15 trades on gold / Nasdaq (14 / 13 at most) -> 0 % pass. With the unemployment-rate
  tie-break: 18-19 trades.
* confirm filter (trade only if the release-minute move agrees): cuts trades to 8-10 -> 0 % pass; not used.
* gold: 42 % of ff+tie-break configs pass, almost every exit setting (median PF 3.65).
* pair: entry at +1 min 0 %, at +15 min 36 %, at +30 min 17 % (ff+tie-break, no confirm); hold 360 min 30 % vs
  60 min 0 %: the edge is the multi-hour drift, not the spike.
* nasdaq: 36 / 768 pass, scattered (non-monotonic in hold and stop); every one collapses when the best 1-2 trades are
  removed -> noise.

### 3c. Entry-delay scan with fixed exits (stop 1.5 x ATR, no target, 6 h), ff + tie-break

| delay (min) | 1 | 3 | 5 | 8 | 10 | 15 | 20 | 30 | 45 | 60 |
|---|---|---|---|---|---|---|---|---|---|---|
| gold PF | 8.0 | 8.0 | 8.8 | 9.3 | 8.0 | 7.3 | 7.3 | 8.2 | 7.6 | 5.6 |
| nasdaq PF | 1.9 | 1.6 | 2.1 | 2.1 | 1.5 | 1.6 | 1.2 | 1.1 | 0.9 | 0.8 |
| pair PF | 1.8 | 2.3 | 1.7 | 3.6 | 2.7 | 3.0 | 2.8 | 2.2 | 3.1 | 2.0 |
| pair PF 2x cost | 1.5 | 1.1 | 1.3 | 3.1 | 2.4 | 2.4 | 1.9 | 1.7 | 2.8 | 1.8 |

The pair passes for every delay from 8 to 60 minutes; gold for every delay; Nasdaq only up to 5 min and only barely.

### 3d. Stop / hold / target plateau at delay 15 (PF / R / maxDD, * = passes)
Gold passes all 75 combinations (stop 1-3 x ATR, hold 3-7 h, target 2R/3R/none). Pair passes all combinations with
stop 1-1.5 x ATR and every hold from 3 to 7 h, and stop 2-3 x ATR with holds >= 5-6 h. Nasdaq passes 6 of 75,
isolated (hold 6 h with stop >= 2.5 only). Targets are rarely reached with these stops; "no target" is the simplest.

### 3e. Robustness of the candidate (research/robust.py)
Candidate = FF verdicts + unemployment-rate / headline-CPI tie-break, entry 15 min after the release, stop 1.5 x
ATR(24 x H1), no target, time exit 6 h after the entry, one rule set for all three versions.

| check | gold | nasdaq | pair |
|---|---|---|---|
| n / R / PF / maxDD | 16 / +13.7 / 7.30 / -17 % | 16 / +1.8 / 1.57 / -17 % | 19 / +10.4 / 3.02 / -19 % |
| Jan-Mar R / Apr-Jun R | +7.1 / +6.7 | +1.9 / **-0.1** | +2.7 / +7.8 |
| PF at 2x cost / entry 2 min later | 7.23 / 10.1 | 1.50 / 1.24 | 2.35 / 2.11 |
| PF without best 1 / best 2 trades | 5.65 / 4.60 | **1.03 / 0.81** | 2.32 / 1.82 |
| R by currency | AUD +12.1 (13), NZD +1.6 (3) | AUD +3.0, NZD -1.3 | AUD +9.3 (14), NZD +1.1 (5), JPY 0 trades |
| R by event type | CPI +6.7 (8), jobs +7.4 (5), GDP -0.3 (3) | CPI +3.3, jobs +0.2, GDP -1.7 | CPI +2.8 (9), jobs +7.4 (7), GDP +0.2 (3) |
| R by month J/F/M/A/M/J | +4.8 +2.8 -0.5 -0.3 +6.3 +0.6 | +2.1 +0.4 -0.7 +0.3 -0.8 +0.4 | -1.8 +4.3 +0.2 -0.2 +6.4 +1.6 |
| longs / shorts R | +8.3 (8) / +5.4 (8) | +0.7 / +1.1 | +5.9 (9) / +4.5 (10) |
| variant: FF only, no tie-break | 14 trades (fails n) PF 4.91 | 14, PF 2.03 | 15, PF 2.04 (passes) |
| variant: computed sign instead of FF verdict | PF 6.10 (passes) | PF 1.42 (fails) | PF 2.53 (passes) |
| variant: in-line -> actual vs previous | 22 trades PF 6.42 | 22, PF 1.53 | 25, PF 2.26 |
| placebo: same trades, random direction (5000x) | p = 0.003 | p = 0.28 | p = 0.033 |
| always long / always short R | +2.5 / +3.4 | -0.5 / -0.9 | +1.6 / +1.7 |
| trend control (direction = 10-day trend) | R +8.2, agrees with news 82 % | R +1.6 | R -1.2, agrees 47 % |

Reading:
* **pair**: the drift after the surprise is spread over currencies, event types, months and both directions, the
  result is not a trend artefact (the trend rule makes nothing and agrees with the news direction half the time),
  survives 2x costs and later entries and the removal of the best two trades. It is the only version with an
  economic story (post-announcement drift in the currency whose data surprised).
* **gold**: passes everything in-sample and beats random directions, but the news direction coincides with gold's
  own trend 82 % of the time and the 10-day trend alone earns +8.2 R on the same events; AUD / NZD data have no
  plausible causal effect of this size on gold. Expect much worse out of sample.
* **nasdaq**: fails the Jan-Mar/Apr-Jun rule (Apr-Jun R -0.09), PF 1.03 without its best trade, random directions do
  as well 28 % of the time: no relation between Asian-session news and Nasdaq. It is kept with the SAME rules for the
  comparison (not tuned to pass - 36 of 768 grid configs pass by chance and every one of them collapses without its
  best trades), and would not be traded live.

## 4. Final rules (identical for the three versions)

1. Universe: FF high-impact AUD / NZD / JPY / CNY releases 21:45-07:00 UTC; same-minute figures of one currency = one
   release; speeches / statements / press conferences ignored.
2. Signal: each figure votes FF's verdict (better +1 / worse -1 / in line 0; if FF gives none: sign of actual -
   forecast, unemployment inverted). Sum > 0 bullish, < 0 bearish. Votes cancel (split report) -> the unemployment
   rate decides, then headline CPI y/y, then CPI q/q. All in line -> no trade (central-bank decisions in line with the
   forecast are not traded; a surprise decision is).
3. Direction: pair = currency's own pair (AUDUSD, NZDUSD; USDJPY inverted). Gold: bullish AUD / NZD / JPY -> buy gold
   (commodity-currency and haven co-movement). Nasdaq: bullish AUD / NZD -> buy (risk-on), bullish JPY -> sell
   (carry unwind).
4. Entry at the open of the minute 15 minutes after the release minute (the spike and its retracement are over, the
   wide news spread is gone, and the scraper has 15 minutes to read the actual).
5. Stop 1.5 x the average true range of the 24 hourly bars before the release; no target; exit 6 h after the entry
   (Friday 20:00 UTC at the latest); one position per instrument; 10 % of equity risked.
6. Knobs: 3 (entry delay, stop multiple, hold), each chosen in the middle of a plateau (delay 8-60, stop 1-2,
   hold 5-7 h all pass for the pair).

## 5. Package checks before locking

* `run_backtest.py` (the package's own backtest through the toolkit, reading LOCKED.json) reproduces the research
  numbers exactly: gold 16 / +13.69 R / PF 7.30, nasdaq 16 / +1.77 / 1.57, pair 19 / +10.41 / 3.02.
* `research/check_replay.py`: the LIVE loop (newsbot/bot.py with a simulated clock, historical bars as broker
  prices, the calendar as schedule + actual source with 30 s latency) replayed minute by minute over Jan-Jun takes
  exactly the backtest's trades for every version (same entries, directions, exits, R to 0.000). This caught one
  live-vs-backtest difference that was fixed: during gold's 22:00-23:00 UTC break the live loop would have filled on
  the last stale quote; it now waits for the first quote at/after the planned entry (as the backtest does) and skips
  after 2 minutes.
* `tests/` (pytest, synthetic data): value parsing, classification, votes / tie-break / in-line handling, pair /
  gold / Nasdaq mapping (USDJPY inverted), weekend cap, the FF weekly-JSON and page parsers, actual polling with a
  missing figure, simulator fills (news spread, short pays the spread on exit, entry minute cannot take the target,
  gap through the stop) and the MT5 broker against a fake `MetaTrader5` module (lot sizing from order_calc_profit,
  SL rounding, filling mode, close by ticket; dry-run never calls order_send). 15 tests pass.
* Live sources tried from the build machine (Nov 4 2026): the weekly JSON export first answered HTTP 429 "Request
  Denied - exceeded the limit for Calendar Export requests" (twice, minutes apart; the egress IP is shared), and
  ~40 minutes later HTTP 200 with 115 events (keys: title, country, date, impact, forecast, previous - no actual).
  The bot's parser picked exactly this week's two Asian target releases: RBA cash rate Nov 3 03:30 UTC (forecast
  4.85 % vs 4.60 %) and NZD employment change + unemployment rate Nov 3 21:45 UTC; statements / press conferences
  were correctly ignored. The FF calendar page in headless Chromium (default user agent) got Cloudflare's "Just a
  moment..." challenge (HTTP 403, 0 events): the actual reader could only be tested on synthetic pages in FF's
  embedded-JSON format. See README "Data sources" - the actual source is pluggable.

LOCKED.json written Nov 4 2026 (sha256 ab6c7ecd5c11...), then final_test run once.

## 6. final_test (Jul 1 - Oct 15 2026, never seen before, run once) - final_test_output.json

| version | Jan-Jun n / R / PF / maxDD | Jul-Oct n / R / PF / maxDD | Jul-Oct at 2x cost | Jul-Oct success |
|---|---|---|---|---|
| gold (XAUUSD) | 16 / +13.69 / 7.30 / -16.7 % (pass) | 11 / +0.05 / 1.01 / -29.7 % | -0.02 R, PF 1.00 | **no** |
| nasdaq (NAS100) | 16 / +1.77 / 1.57 / -16.7 % (**failed**: Apr-Jun R < 0) | 11 / +3.75 / 2.87 / -16.0 % | +3.65 R, PF 2.78 | yes (see below) |
| pair (AUDUSD+NZDUSD+USDJPY) | 19 / +10.41 / 3.02 / -19.0 % (pass) | 10 / -3.52 / 0.47 / -39.4 % | - | **no** |
| - pair_aud (AUDUSD) | 14 / +9.31 / 5.32 / -10.0 % | 8 / -3.92 / 0.30 / -40.9 % | -4.35 R, PF 0.25 | no |
| - pair_nzd (NZDUSD) | 5 / +1.09 / 1.36 / -23.5 % | 2 / +0.40 / 1.40 / -10.0 % | +0.21 R | no (n < 8) |
| - pair_jpy (USDJPY) | 0 trades (no BoJ surprise) | 0 trades | - | no (n = 0) |

$1,000 at 10 % risk in Jul-Oct: gold $954, Nasdaq $1,401, pair $669.

What happened:
* **pair** - the version with the best in-sample evidence and the only causal story failed: 3 wins in 10, 5 trades
  stopped out (AUD jobs 23 Jul, AUD CPI 29 Jul, AUD GDP 2 Sep, AUD CPI 30 Sep, NZD GDP 16 Sep), max drawdown -39 %.
  The "post-announcement drift" measured on 19 Jan-Jun releases (t ~ 2.5) did not repeat on 10 new ones. Possibly
  part of the Apr-Jun result (+7.8 R) was AUDUSD's own decline lining up with a run of weak Australian data - the
  trap identified for gold - which the trend control could not flag because over Jan-Jun as a whole the trend and
  the news direction agreed only 37-68 % of the time; with 19 trades it may equally have been plain luck.
* **gold** - flat (+0.05 R), as section 3e predicted: its in-sample PF of 7.3 came from gold's trend coinciding with
  the AUD surprises, not from the news.
* **nasdaq** - +3.75 R, PF 2.87, which formally meets the Jul-Oct success rule. It should not be read as an edge:
  it failed the Jan-Jun build rules, showed no relation to the news in any study (placebo p = 0.28, PF 1.03 without
  its best trade), and it took **exactly the same 11 trades in the same directions as the gold version** (both buy
  on a bullish AUD / NZD surprise) - gold made +0.05 R and Nasdaq +3.75 R on identical calls, i.e. the difference
  is the two instruments' own moves after 01:45 UTC, not the signal. 11 trades with PF 2.9 arise by chance easily.

## 7. Conclusions

1. Asian-session high-impact releases are priced inside the release minute; a bot that must read the actual first
   (entry at the next minute's open, double spread) has nothing left in the currency pair, and AUD / NZD data do not
   move gold or Nasdaq in a measurable way.
2. Every positive Jan-Jun result found here was explainable by the instrument's own trend lining up with a short run
   of same-signed surprises. With ~20 releases per half-year, a 6-month build cannot separate a news effect from
   that, and the out-of-sample test confirmed it for the two versions that passed the build.
3. Recommendation: do **not** trade any version live with real money. The bot is complete and its live code path is
   verified against the backtest (useful as infrastructure, e.g. for a dry-run journal or for other events), but no
   rule set in this study has demonstrated an edge. If anything is run, run `--signal-only` / dry-run and judge it
   on the 2025 exam and at least another half-year of live paper results, at 1-2 % risk rather than 10 %.

## Housekeeping note
During a smoke test I mistakenly wrote four files (config.toml, ff.json, state.json, bot.log) into a pre-existing
scratchpad folder `../smoke/` (outside my folder) and removed them right after; if that folder already held a
`config.toml`, it was overwritten. Nothing else outside this folder was written except the toolkit's own
results/asia_news/final_test.json (written by final_test, not read).

## Reproduce
```
cd /home/user/oncandle
export PYTHONDONTWRITEBYTECODE=1 N=<this folder>
python $N/research/study1_reactions.py        # reaction table -> research/reactions.csv
python $N/research/grid.py gold|nasdaq|pair    # 768-config grids -> research/grid_*.csv
python $N/research/robust.py                   # section 3e
python $N/run_backtest.py                      # Jan-Jun numbers of LOCKED.json
python $N/research/check_replay.py $N/LOCKED.json   # live loop == backtest
(cd $N && python -m pytest -q tests)
```
