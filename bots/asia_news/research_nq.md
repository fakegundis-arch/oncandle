# Nasdaq news bot v2 - research (Jan-Jun 2026 build, then one final_test)

Status: rules LOCKED in LOCKED_NQ.json at 2026-11-05T09:28:40Z; final_test (tag "nasdaq_v2") run once afterwards - section 6;
2025 exam run once after that - section 7: **fails** (47 trades, +0.26 R, PF 1.02, DD -46 %).

In the repository this folder is `bots/asia_news/`: `bot/` below = this folder, `base/` = the first bot (git history
before this commit), `lab/` = `bots/asia_news/lab/`. The large lab outputs (`lab/out/snoop_*.csv`,
`lab/out/placebo_reactions.csv`, `lab/out/ctx_cache.pkl`) are not committed; the scripts regenerate them.

## Summary

* NAS100 does not react to the Asian AUD / NZD / JPY high-impact releases: no extra volatility in the release minute
  or the first 5 minutes (percentile 0.50-0.51 vs the same minute on other days), no surprise-sign or surprise-size
  effect (big surprises went the wrong way). v1's entry at +15 min sits where nothing works.
* Every entry idea of the brief was run as a family grid with the pass rules and a same-clock-time placebo; the ones
  that pass all take a direction in the first 1-5 minutes after the release and hold it 4-6 h. Pseudo-calendar tests
  (the same search on Jan-Jun without news) show that such a search finds passing rules by chance too: the release
  effect is weak evidence (p ~ 0.03-0.3 after the search), not proof.
* Chosen: **nasdaq_v2 = trade NAS100 in the direction of the released currency's own pair reaction (AUDUSD / NZDUSD,
  release -> +2 min), entry at +2 min, stop 2 ATR, exit after 6 h, AUD / NZD only** - the most robust plateau, a
  reason, and no need for the actual. Jan-Jun: 24 trades, +4.41 R, PF 2.97, DD -7.2 %, passes.
* final_test (Jul 1 - Oct 15 2026, run once): **13 trades, +2.34 R, PF 2.24, DD -15.9 %, $1,000 -> $1,236; success by
  the stated rule** (2 x cost: +2.14 R, PF 2.10). It rests on 2-3 trades (R without the best two: +0.38).

### Entry ideas, Jan-Jun 2026 (one representative config each; lab/out_representatives.txt)

placebo = the same rule at the same UTC minute on the 95 weekdays without a release per release (R per trade), p =
P(mean of n random placebo trades >= the releases' mean). For news-sign rules the placebo direction is random.

| idea | rule | n | R | PF | DD | pass | R / trade: news vs placebo | p |
|---|---|---|---|---|---|---|---|---|
| 1 news sign, delayed | v1: +15 min, stop 1.5 ATR, 6 h | 16 | +1.77 | 1.57 | -16.7 % | no (Apr-Jun < 0) | +0.11 vs +0.02 | 0.34 |
| 1 | +3 min, stop 2 ATR, 6 h | 16 | +3.32 | 3.56 | -7.3 % | yes | +0.21 vs +0.01 | 0.10 |
| 1 | only abs(score) >= 2 | 5 | +0.18 | 1.35 | -3.7 % | no (n) | +0.04 vs +0.01 | 0.45 |
| 1 | only all figures agreeing | 6 | -0.48 | 0.58 | -10.7 % | no | -0.08 vs +0.01 | 0.63 |
| 2 price-confirmed | news sign + NAS100 agrees at +5 min | 10 | +3.15 | 10.5 | -3.3 % | no (n) | +0.32 vs -0.01 | 0.05 |
| 2' currency's reaction | **AUDUSD / NZDUSD reaction at +2 min, stop 2, 6 h (FINAL)** | 24 | +4.41 | 2.97 | -7.2 % | yes | +0.18 vs -0.01 | 0.07 |
| 2' | pair reaction (+JPY) + NAS100 agrees, +1 min, stop 1, 4 h | 18 | +7.13 | 3.58 | -10.4 % | yes | +0.40 vs -0.01 | 0.03 |
| 3 momentum | sign of NAS100's release-minute move, stop 1, 4 h | 26 | +8.29 | 2.87 | -14.2 % | yes | +0.32 vs -0.03 | 0.03 |
| 3 | same, read 1 minute later (N = 2) | 27 | -3.80 | 0.67 | -55.8 % | no | -0.14 vs +0.03 | 0.83 |
| 3 | same, N = 5 | 27 | +2.38 | 1.32 | -23.4 % | yes (barely) | +0.09 vs -0.02 | 0.27 |
| 3 breakout | first 3 min range, stop orders, stop 0.5 ATR, 1R, 6 h | 28 | +11.3 | 2.41 | -20.6 % | yes | +0.40 vs -0.00 | 0.02 |
| 3 | first 15 min range, stop 1 ATR, 2R, 4 h | 24 | -4.08 | 0.55 | -44.9 % | no | -0.17 vs +0.10 | 0.94 |
| 4 fade | first 5 min (> 0.05 ATR), stop 1, 1R, 2 h | 19 | -4.34 | 0.48 | -42.7 % | no | -0.23 vs -0.03 | 0.93 |
| 4 | first 15 min (> 0.2 ATR), stop 1, 2R, 2 h | 15 | +3.95 | 2.59 | -14.9 % | yes | +0.26 vs -0.05 | 0.05 |
| 5 pullback | limit at 50 % of the first 10-min move, stop 0.5, 2R, 4 h | 15 | +8.30 | 2.57 | -19.0 % | yes | +0.55 vs -0.05 | 0.03 |
| 6 straddle | OCO at the pre-release 15-min range, stop 1, 1R, 4 h | 25 | +7.42 | 2.62 | -19.0 % | yes | +0.30 vs -0.04 | 0.01 |
| 7 context | fade the previous US session at the release, stop 2, 6 h | 29 | -3.35 | 0.57 | - | no | -0.12 vs +0.05 (placebo PF 1.24) | - |

Single representatives flatter every family (they are among its better configs); the family-level numbers (share of
configs passing, section 2) and the pseudo-calendar tests (section 3) are the fair comparison.

Folder layout: `lab/` = the study scripts (lab/common.py data access only through scripts/asia_news_lab.py,
lab/sim.py the trade simulator, lab/strat.py the entry families, lab/study_*.py the studies, lab/out/ their output);
`bot/` = the bot package (copy of base/ + the v2 entry); `base/` = the first bot, untouched.

## 0. Engine check
The lab simulator (lab/sim.py + lab/strat.py) reproduces the v1 Nasdaq backtest exactly (news sign, entry +15 min,
stop 1.5 x ATR(24 H1), no target, 6 h): 16 trades, +1.77 R, PF 1.57, every trade identical to newsbot.backtest
to 1e-14 R. Same fills as the protocol: M1 bid bars, long pays bid + 1.5 pt, short pays the spread on its exit, 2 x
spread for entries within 5 min of the release, stop before target, entry minute can only stop out, gaps at the open,
flat by Friday 20:00 UTC, one position at a time.

## 1. How NAS100 moves around the releases (lab/study_reactions.py -> lab/out_study_reactions.txt, lab/study_context.py -> lab/out_study_context.txt)

The 32 releases (newsbot grouping): AUD 19 (7 CPI, 6 jobs, 2 GDP, 4 RBA), NZD 9 (2 CPI, 2 jobs, 2 GDP, 3 RBNZ), JPY 4
(BoJ). NAS100 is NOT quoting at the release minute for the three 21:45 UTC NZD releases (Jan 22, Feb 3, Mar 18 - the
CFD reopens 22:00 / 23:00), so price-led entries can use at most **29 releases**; a news-sign entry 15 min later can
use 30 (Mar 18 opens at 22:00). 16 releases have a non-zero FF verdict (with the unemployment-rate / CPI tie-break);
the other 13 are in line (all 11 central-bank decisions, AUD jobs Apr 16, NZD GDP Jun 17). The BoJ minute in the
historical calendar is the actual announcement minute (03:07, 02:46, 03:04, 03:19): live, the FF schedule only has a
tentative time.

Units: ATR = mean true range of the 24 hourly bars before the release (the bot's stop unit, ~50-175 points, median ~73);
cost 1.5 points = 0.02 ATR, so costs are small for Nasdaq. Placebo = the same clock time (UTC hh:mm) on every other
weekday of Jan-Jun without a release (95 days per release, 2770 samples; time-of-day mix identical to the releases).

**Volatility: Nasdaq does not notice these releases.** Percentile of each release's |move| / range within its own
placebo days (0.5 = an ordinary day at that minute), mean over the 29 releases:

| measure | release minute range | release-minute move | 0-5 min range | 0-15 min range | 0-60 min range | 0-4 h move |
|---|---|---|---|---|---|---|
| mean percentile | 0.51 | 0.41 | 0.50 | 0.55 | 0.47 | 0.48 |
| news mean / placebo mean (ATR) | 0.118 / 0.113 | 0.043 / 0.061 | 0.233 / 0.232 | 0.476 / 0.393 | 0.715 / 0.763 | 0.66 / 0.78 |
| p (29 random placebo days >= news) | 0.34 | - | 0.48 | 0.03 | 0.70 | - |

The release-minute move is SMALLER than usual (median 2.3 points vs 4.0 on placebo days - liquidity is thin, nothing
happens). By currency: JPY (BoJ, n=4) release-minute range percentile 0.81 and 0-15 min 0.84 - the only group with a
visible reaction; AUD 0.54 / 0.56; NZD 0.22 / 0.31 (quieter than usual). The 0-15 min range excess (p 0.03) comes from
3 releases (NZD jobs May 5 1.4 ATR in 15 min, AUD CPI Jan 28 0.9, BoJ Jun 16 0.6) and is gone by 60 min.

**Direction from the news sign** (Nasdaq map: bullish AUD / NZD -> up, bullish JPY -> down; n=16): mean move from the
earliest entry +0.00 (5 min), +0.14 (15), +0.18 (30), +0.12 (60), +0.06 (120), +0.04 (240), +0.34 (360 min) ATR,
t = 0.1-1.6; AUD (n=14) +0.06 / +0.07 / +0.34 at 15 / 60 / 360 min. Big surprises go the WRONG way: |score| >= 2
(n=5) -0.24 ATR at 15 min, -0.25 at 60, -0.25 at 240; all figures agreeing (n=6) -0.17 / -0.27 / -0.41. The sign of
Nasdaq's release-minute move agrees with the news direction in 9 of 16 releases (chance). No surprise-size effect -
the "large surprise" filter of idea 1 has nothing to work with.

**Cross-asset:** the currency's own pair reacts strongly (AUDUSD 4-17 spreads in the release minute, in the surprise
direction) but NAS100's move correlates only weakly with it: corr(pair move, NAS100 move) = +0.12 (1 min), +0.31
(5 min), +0.26 (15 min), +0.22 (60 min), AUD / NZD only +0.26 / +0.32 / +0.31 / +0.22 (n=25, none significant).

**Direction from Nasdaq's own early move** (sign of the move from the pre-release close to the open of minute N,
then the move from that open; news vs placebo, mean ATR, % positive):

| signal | +30 min | +60 | +120 | +240 | +360 | placebo (same rule) |
|---|---|---|---|---|---|---|
| release minute (N=1), news | +0.14 (55%) | +0.21 (72%) | +0.27 (66%) | +0.28 (69%) | +0.30 (69%) | ~0.00, -0.04 at 240 (48%) |
| p (placebo >= news) | 0.02 | 0.01 | 0.03 | 0.04 | 0.05 | |
| first 3 min, news | -0.10 | -0.03 | +0.05 | +0.24 | +0.04 | ~0.0 |
| first 5 min, news | +0.11 | +0.12 | +0.10 | +0.11 | +0.10 | ~-0.02 |
| first 10 min, news | +0.02 | +0.03 | +0.01 | +0.09 | +0.12 | ~0.0 |
| first 15 min, news | -0.03 | -0.03 | -0.04 | -0.03 | +0.03 | ~+0.02 |

The release-minute sign "predicts" the next hours at the releases and not on placebo days, but the 3-minute sign does
not, and the release-minute move itself is only ~2 points (smaller than usual) - a pattern that does not decay
smoothly with the window is what chance looks like with 29 events (see section 2 for the full grid).

**Background (all 127 weekdays, no news needed):** the Asian session (23:00-07:00 UTC) moves +0.06 ATR on average
(57 % up; by month +0.27, -0.10, -0.18, +0.03, +0.01, +0.34). It tends to REVERSE the previous US cash session:
corr(US 14:30-20:00 move, Asian move) = -0.21, the Asian move has the US move's sign on only 39 % of days (mean
-0.35 ATR when signed by the US move). Hourly range is largest 00-01 UTC (0.98 ATR, Tokyo open) and 01-02 (0.85,
China / HK open), smallest 04-05 (0.54).

## 2. Entry ideas on Jan-Jun (lab/grid.py -> lab/out/grid_<family>.csv)

Every family was run over a grid of its own knobs x exits (stop 0.5 / 1 / 1.5 / 2 x ATR, target 0 (none) / 1 / 2 / 3 R,
time exit 60 / 120 / 240 / 360 min; breakout / straddle also stop = the range), on the releases with the pass rules
(n >= 15, PF >= 1.3, R > 0 in Jan-Mar and in Apr-Jun, PF >= 1.15 at 2 x cost and with the entry 2 min later,
DD at 10 % better than -35 %), AND on the clock-time placebo (same rule, same UTC minute, the 95 weekdays without a
release per release). "late" = entry 2 minutes later (market entry 2 min later; a stop-order / limit entry becomes a
market order 2 min after its trigger). Stop orders pay the 2 x news spread plus 1 x spread slippage when they fill
within 5 min of the release; when both legs of an OCO trigger in the same minute the WORSE leg is booked.
"pass" = share of the family's configs passing; avgR = median over configs of R per trade; placebo = the same
statistic for the same configs on the placebo times; p = median over configs of P(mean of n random placebo trades >=
the releases' mean).

| idea | family / variant | configs | n (median) | pass | median PF | avgR news | avgR placebo | p |
|---|---|---|---|---|---|---|---|---|
| 1 news sign, delayed | all releases, delay 1 / 3 / 5 min | 64 each | 16 | 53 / 62 / 62 % | 1.60 / 1.73 / 1.76 | +0.09 / +0.12 / +0.10 | 0.00 | 0.18-0.23 |
| 1 | delay 10 / 15 / 30 / 60 | 64 each | 16-17 | 5 / 3 / 0 / 0 % | 1.08 / 1.25 / 0.86 / 0.76 | +0.01 / +0.02 / -0.05 / -0.06 | 0.00 | 0.42-0.60 |
| 1 | large surprises only (abs score >= 2) | 448 | 5 | 0 % | 0.3-1.9 | -0.22..+0.08 | 0.00 | - |
| 1 | all figures agree | 448 | 6-7 | 0 % | 0.2-0.7 | -0.32..-0.07 | 0.00 | - |
| 2 news sign + Nasdaq's move agrees (at the entry) | delay 1 / 5 / 15 | 64 each | 9 / 10 / 10 | 0 % (n < 15) | 9.1 / 3.4 / 0.8 | +0.40 / +0.26 / -0.03 | 0.0 | 0.03 / 0.07 / 0.65 |
| 2' direction from the currency pair's own reaction (AUDUSD / NZDUSD / USDJPY, cross-asset) | N = 1 / 2 / 3 / 5 / 15 min | 192 each | 19-23 | 46 / 40 / 37 / 27 / 3 % | 1.73 / 1.40 / 1.82 / 1.27 / 0.76 | +0.16 / +0.07 / +0.15 / +0.06 / -0.06 | +0.01..+0.06 | 0.18-0.80 |
| 2' + Nasdaq agrees | N = 1 / 2 / 3 / 5 | 192 each | 13-15 | 55 / 17 / 24 / 56 % | 4.14 / 1.06 / 1.82 / 1.89 | +0.27 / +0.02 / +0.19 / +0.11 | -0.01..+0.04 | 0.03-0.62 |
| 3a momentum: sign of Nasdaq's move release -> minute N, enter at N | N = 1 / 2 / 3 / 5 / 10 / 15 / 30 (k = 0..0.2 ATR) | 256 each | 6-22 | 20 / 0 / 17 / 39 / 6 / 0 / 0 % | 1.99 / 1.47 / 1.36 / 1.98 / 1.10 / 0.66 / 0.95 | +0.18 / +0.08 / +0.09 / +0.17 / +0.02 / -0.06 / -0.01 | -0.03..+0.03 | 0.15-0.79 |
| 3a | N = 1, k = 0 (every release) | 64 | 27 | 81 % | 3.14 | +0.24 | -0.03 | 0.02 |
| 3b breakout of the first N minutes' range (incl. pre-release close), stop orders for W min | N = 1 / 3 / 5 / 10 / 15 / 30 | 288 each | 22-28 | 18 / 28 / 14 / 0 / 2 / 22 % | 1.14 / 1.30 / 1.27 / 0.77 / 0.76 / 1.58 | +0.06 / +0.09 / +0.08 / -0.08 / -0.09 / +0.16 | -0.15 / -0.02 / +0.03 / +0.08 / +0.11 / +0.09 | 0.13-0.83 |
| 3b | N = 1 / 3 / 5 with stop 0.5 ATR | 96 each | 27 | 38 / 65 / 29 % | 1.76 / 1.83 / 1.70 | +0.27 / +0.30 / +0.27 | -0.14 / +0.01 / +0.06 | 0.04 / 0.11 / 0.22 |
| 4 fade the first move | N = 1 / 2 / 3 / 5 / 10 / 15 / 30 | 256 each | 6-22 | 0 / 0 / 0 / 0 / 0 / 16 / 5 % | 0.11 / 0.45 / 0.60 / 0.37 / 0.77 / 1.15 / 0.91 | -0.28 / -0.13 / -0.13 / -0.22 / -0.05 / +0.02 / -0.02 | -0.04..0.00 | 0.30-0.95 |
| 5 pullback: limit at x = 38 / 50 / 62 % retrace of the first N-min move (> k ATR), join it | N = 3 / 5 / 10 / 15 | 324 each | 2-10 | 0 / 0 / 17 / 5 % | 0.74 / 2.67 / 1.10 / 1.19 | +0.14 / +0.33 / +0.03 / +0.06 | -0.07..+0.07 | 0.27-0.42 |
| 6 straddle: OCO stops at the last K minutes' high / low, placed before the release | K = 15 / 30 / 60 | 324 each | 14-25 | 31 / 6 / 14 % | 1.46 / 1.03 / 1.47 | +0.13 / +0.01 / +0.13 | +0.01 / +0.02 / +0.02 | 0.26-0.52 |

Reading of the grids:
* **Idea 1 (news sign)** works only when entered in the first 5 minutes (n = 16, just above the 15 minimum) and dies
  from 10 minutes on - the v1 entry at 15 min sits in the dead zone (PF 1.57 on a single config, 3 % of its
  neighbours pass). Surprise-size filters (abs score >= 2, all figures agreeing) select the releases where Nasdaq went
  the OTHER way, and leave 5-7 trades: rejected. The live bot would have to read the actual within 1-5 minutes of the
  release (FF page latency 5-60 s + Cloudflare) for the only delays that work.
* **Idea 2 (price confirmation)** improves the per-trade numbers but halves the trades (8-10): never 15 trades.
  The cross-asset version (direction = the currency pair's own release reaction, 2') gives a direction for in-line
  central-bank decisions too (n 19-23) and passes 27-46 % for N = 1-5 min.
* **Idea 3 (Nasdaq's own early move)**: every price-led family "works" when the direction is taken in the first 1-5
  minutes after the release and fails from 10 minutes on: momentum N = 1 (81 % of exits pass with k = 0), breakout of
  the release-minute / first-3-minute range with a 0.5 ATR stop (38 / 65 %), the pre-release straddle K = 15 (31 %).
  But the pattern is not smooth: momentum N = 2 passes 0 % (13 of 29 release-minute signs flip in the second minute -
  the release-minute move is only ~2 points), N = 3 17 %, N = 5 39 %.
* **Idea 4 (fade)** is the mirror image and loses (0 % pass up to N = 10).
* **Idea 5 (pullback)**: too few retraces of a meaningful first move (n <= 10 except N = 10 with n = 15).
* **Idea 6 (straddle)**: placing OCO stops at the pre-release 15-min range is the breakout idea without needing the
  first minute; it passes 31 % with K = 15, less with wider ranges.
* **Placebo**: on the same clock times without a release the same rules make ~0 per trade (and the 0.5 ATR breakout
  stops lose -0.15 R per trade on placebo days): whatever works at the releases does not work at those minutes on other
  days.

**Idea 7 (context filters, lab/study_filters.py -> lab/out_study_filters.txt)** on the three leading entries:
splitting by "trade agrees with the previous US cash session's direction", "agrees with the last 6 h", ATR above /
below the median, and day of week gives no consistent help (e.g. final rule: with / against the US session +0.22 /
+0.15 R per trade; high / low ATR +0.08 / +0.32 but the momentum rule has the opposite, +0.54 / +0.10; Wednesdays
dominate only because AUD CPI is published on Wednesdays). Every split halves n below 15. The context-only rule
"fade the previous US session" (entered 2 min after the release, stop 2 ATR, 6 h) earns +0.05 R per trade on the 2718
placebo times (PF 1.24 - the Asian-session reversal of section 1) but LOSES at the releases (29 trades, -3.4 R,
PF 0.57): it is not a news effect and it does not help at news times. No context filter is used.

## 3. Is any of it a news effect? (lab/robust.py, lab/pseudo.py, lab/snoop.py -> lab/out_snoop.txt)

Three placebos beyond the clock-time one:
* **shift**: the same rule on the release DAYS at the release minute -90 / -60 / -30 / +30 / +60 / +90 min;
* **random direction**: the same entries and exits with random directions (5000 x);
* **pseudo calendars**: every release moved to the same clock time on a random weekday without a release (keeping its
  currency / kind / FF sign), 100 calendars; the same rule and the SAME pass rules are run on each. A pseudo calendar is
  "Jan-Jun without any news" with the releases' exact time-of-day structure.
* **selection-adjusted ("snooping")**: a whole family grid run on the real calendar and on 40-100 pseudo calendars;
  compares the share of passing configs and the best passing R - i.e. what a search like this one finds where there is
  no news at all.

| rule (Jan-Jun) | n | R | PF | shift placebo R (-90..+90 min) | random dir. p | pseudo cal.: pass / R >= real | family snoop: pass share real vs pseudo median (P pseudo >= real) |
|---|---|---|---|---|---|---|---|
| Nasdaq release-minute momentum (N=1, stop 1, 4 h) | 26 | +8.29 | 2.87 | -11.2 / -3.2 / -3.2 / -2.5 / +2.4 / +2.0 | 0.002 | 14 % / 0 % | 0.45 vs 0.13 (0.10); best R P = 0.17 |
| breakout of the release minute (N=1, stop 0.5, 3R, 4 h) | 27 | +15.2 | 2.52 | -5.4 / -15.6 / -0.4 / -2.4 / -9.8 / +0.4 | - | 1 % / 0 % | 0.31 vs 0.10 (0.17); best R P = 0.23 |
| breakout of the first 3 min (stop 0.5, 1R, 6 h) | 28 | +11.3 | 2.41 | 0.0 / +4.0 / +0.8 / 0.0 / -13.7 / -4.0 | - | 14 % / 0 % | (same family) |
| straddle of the pre-release 15 min (stop 1, 1R, 4 h) | 25 | +7.42 | 2.62 | -2.0 / -1.0 / +2.0 / -1.7 / -1.0 / -1.3 | - | 11 % / 1 % | 0.27 vs 0.04 (0.20); best R P = 0.05 |
| news sign +3 min (stop 2, 6 h) | 16 | +3.32 | 3.56 | - | - | 15 % / 11 % | 0.37 vs 0.02 (0.12); best R P = 0.17 |
| v1: news sign +15 min (stop 1.5, 6 h) | 16 | +1.77 | 1.57 | - | 0.28 (v1) | 25 % / 34 % | - |
| **pair reaction, AUD / NZD, +2 min (stop 2, 6 h) = final** | 24 | +4.41 | 2.97 | -2.7 / +0.8 / -3.2 / -0.8 / -3.6 / +0.4 | 0.016 | 26 % / 7 % | 0.86 vs 0.03 (0.03); best R P = 0.33; median R P = 0.12 |
| pair reaction incl. JPY / all three currencies, N = 1-5 (family) | 26 | +5.55 | 3.51 | - | 0.008 | - | 0.45 vs 0.08 (0.12); best R P = 0.12 |

What this says:
* For a SINGLE config, the early-direction rules look far better at the releases than on pseudo calendars (R >= real
  in 0-7 % of no-news calendars) and than at other minutes of the same days (shift placebo mostly negative).
* But the protocol's pass rules are easy to meet by chance at this sample size: a fixed rule passes on 11-26 % of the
  no-news calendars, and a family search finds a passing config on almost every pseudo calendar (median pass share
  2-13 %). After accounting for the search, the real calendar sits at roughly the 80th-97th percentile of no-news
  calendars: p ~ 0.03-0.33 depending on the statistic. **This is weak evidence, not proof, of a release effect.**
* Mechanically, NAS100 does not react to these releases (section 1: no extra volatility in the first 5 minutes, the
  release-minute move is smaller than usual). What the profitable rules share is a direction taken in the first 1-5
  minutes and held for 4-6 hours on days whose Asian morning trended; that the release minute picks the right side
  more often than other minutes is not explained by any visible reaction of Nasdaq itself.

## 4. The choice

Final = **pair reaction**: trade NAS100 in the direction of the released currency's own pair reaction (AUDUSD for AUD,
NZDUSD for NZD): from the close of the minute before the release to the open 2 minutes after the release minute;
currency stronger -> buy NAS100 (risk-on read), weaker -> sell. Entry at that same open (release + 2 min) at market;
stop 2 x ATR(24 x H1) (a disaster stop: no Jan-Jun trade reached it); no target; exit 6 h after the entry (Friday 20:00
UTC cap); one position at a time; AUD and NZD releases only.

Why this one and not the bigger in-sample numbers:
1. **A reason, and the most robust plateau.** The signal is the market's own reading of the release in the currency the
   data is about - a large, unambiguous move (AUDUSD 2-16 spreads in 2 minutes), not Nasdaq's 2-point release-minute
   tick. It agrees with FF's verdict on 12 of 14 data releases (exceptions: AUD GDP Mar 4, AUD CPI Jun 24) and also
   gives a direction for in-line central-bank decisions and in-line data (RBA, RBNZ, AUD jobs Apr 16, NZD GDP Jun 17).
   AUD / NZD are the Asian-hours risk proxies, and the read is held for the Asian session. It is smooth in every knob:
   86 % of its 36 neighbours (N = 1 / 2 / 3 min x stop 1 / 1.5 / 2 x hold 4 / 5 / 6 / 7 h) pass, vs 3 % median on
   pseudo calendars (3 of 100 reach 86 %); N = 5 min fades; stop 1.5-3 ATR and hold 4-7 h all pass.
2. The Nasdaq momentum rule (N=1) has bigger numbers but is a knife edge: the same rule read one minute later (N = 2)
   loses in every exit setting (13 of 29 release-minute signs flip in the next minute; the moves are 1-10 points).
   The breakout / straddle rules have 0.5 ATR stops with deep drawdowns (-19 to -34 %) and their structure earns on
   placebo days too (breakout, no target: +0.10 to +0.13 R per trade on placebo times).
3. **It needs no actual.** The decision is made from prices at release + 2 min, so the live bot does not depend on
   scraping Forex Factory through Cloudflare within minutes (the only news-sign entries that work are at +1-5 min).
4. **Few knobs**: N = 2 (middle of the 1-3 plateau), the stop and the 6 h hold are v1's (stop widened from 1.5 to 2 ATR,
   inside the 1.5-3 plateau, where it is only a disaster stop), no threshold on the pair move, no filters.
5. **JPY excluded:** the BoJ announcement minute is not known in advance (FF lists it as tentative; the historical
   calendar carries the real minute 03:07 / 02:46 / 03:04 / 03:19), and a price-led entry needs the minute; the backtest
   must not trade a minute the live bot could not know. (With JPY the Jan-Jun numbers would be better: 26 trades, +5.55 R.)

Weaknesses, stated up front:
* **The upward drift does most of the work.** Always long on the same 24 entries makes +4.01 R; the rule's longs make
  +4.52 R (13), its shorts -0.11 R (11). Against random directions it is p = 0.016, but it barely beats "always long".
* NZD adds little (5 trades, +0.28 R); central-bank decisions lose (6 trades, -0.41 R); Jan +1.80 and Mar-May carry it,
  June -0.08.
* R per trade is small (+0.18) because the stop is wide: $1,000 -> $1,507 in Jan-Jun at 10 % risk.
* Selection-adjusted evidence of a news effect is weak (section 3). Expect Jul-Oct to be closer to the placebo
  (about 0 R per trade) than to Jan-Jun.

### Final rule, Jan-Jun 2026 (bot/run_backtest.py = lab = live-loop replay)

| | n | R | PF | win | max DD (10 %) | $1,000 -> | Jan-Mar R | Apr-Jun R | PF 2 x cost | PF entry +2 min | pass |
|---|---|---|---|---|---|---|---|---|---|---|---|
| nasdaq_v2 | 24 | +4.41 | 2.97 | 67 % | -7.2 % | 1,507 | +3.12 | +1.29 | 2.67 | 3.37 | PASS |
| v1 nasdaq (for comparison) | 16 | +1.77 | 1.57 | 62 % | -16.7 % | 1,154 | +1.86 | -0.09 | 1.50 | 1.24 | fail |

All 24 trades exit on time (none reaches the 2 ATR stop). R without the best 1 / 2 / 3 trades: +2.55 / +1.78 / +1.08;
PF without the best 1 / 2: 2.14 / 1.79. By currency AUD 19 trades +4.13 R, NZD 5 +0.28; by kind CPI +2.62 (8), jobs
+1.37 (7), GDP +0.83 (3), rate decisions -0.41 (6); by month +1.80 / +0.37 / +0.95 / +0.32 / +1.05 / -0.08; longs
+4.52 (13), shorts -0.11 (11). Clock-time placebo (same rule, same minute, days without a release, 2282 trades)
-0.014 R per trade, PF 0.94 (p 0.067 for the releases' mean); shift placebo (same days, other minutes) -2.7 / +0.8 /
-3.2 / -0.8 / -3.6 / +0.4 R; random directions p = 0.016; always long +4.01 R, always short -4.88 R.
Trade list: lab/out/backtest_v2_trades.csv, lab/out_robust_final.txt.

## 5. The bot (bot/ = base/ + the v2 entry)

* `newsbot/strategy.py`: new entry mode `entry = "pair_reaction"` with `signal_pairs`, `react_min`, `react_min_move`,
  `pre_gap_max`; `reaction_from_prices` is THE direction rule (used by the backtest and the live loop),
  `reaction_direction` its bar-based form for the backtest, `make_plan(..., reaction=...)` builds the plan.
  `entry = "news"` (v1) is unchanged.
* `newsbot/backtest.py`: `make_trades(cfg, calendar, m1, cost, entry_delay=None, detail=False, aux=None)` - for
  pair_reaction it needs the signal pair's M1 bars (`aux`, or `AUX_PRICES` = the toolkit: `prices_train()` when the
  traded bars end inside the build period - a build run never loads later data - and the toolkit's own M1 loader
  `asia_news_lab._m1` cut to the traded bars' span in final_test, the only way final_test can give it the pair's
  Jul-Oct bars). The "entry 2 minutes later" stress moves the entry (+4 min) but not the signal (+2 min).
* `newsbot/bot.py`: at the scheduled release minute a pair_reaction version is scheduled without waiting for any
  actual; at release + react_min the bot reads the pair (pre-release close from M1 bars, post = the first quote at /
  after that minute), then buys / sells NAS100 at the first quote at / after release + entry_delay; pair or NAS100 not
  quoting within 120 s -> skipped (as the backtest's 2-minute rule); the outcome is persisted per version and
  release; signal-only mode logs that the version needs prices. The v1 actual-polling path is unchanged and only
  runs for v1 versions.
* `newsbot/replay.py`: the replay broker now charges the protocol's 2 x spread from the release minute to 5 minutes
  after it and makes a short pay its entry spread on the exit (exactly the backtest's fills) - the v1 entries at
  +15 min were outside the window, so this never mattered before.
* `run_bot.py --schedule` prints, for v2, which pair is read when and what it would trade; `config.toml` runs
  `nasdaq_v2` from `LOCKED_NQ.json` (dry-run by default, `--live` AND mode = "live" needed for real orders).
* Checks (all from /home/user/oncandle with PYTHONDONTWRITEBYTECODE=1):
  - `bot/run_backtest.py` (LOCKED_NQ.json): 24 / +4.41 R / PF 2.97 / -7.2 % / PASS - identical to the lab.
  - `bot/research/check_replay.py bot/LOCKED_NQ.json`: the live loop (simulated clock every 30 s, historical bars as
    broker prices, the calendar as schedule) takes the same 24 trades, same directions, same exits, max |dR| 2e-14
    (lab/out/replay_v2_trades.csv). The first attempt differed by 0.017 R per trade - the replay broker charged 1 x
    spread at +2 min where the protocol (and the backtest) charge 2 x - fixed in replay.py, not in the strategy.
  - `bot/run_backtest.py --locked bot/LOCKED.json`: v1 numbers unchanged (gold 16 / +13.69, nasdaq 16 / +1.77,
    pair 19 / +10.41).
  - `python -m pytest bot/tests`: 21 passed (15 v1 + 6 new: direction rule incl. stale / missing pair quotes and the
    JPY mapping, plan without reaction, make_trades fills / news spread / late entry on synthetic bars, live loop =
    backtest on synthetic data with no actual ever available, flat pair -> no trade, signal-only mode, replay spread).

## 6. final_test (Jul 1 - Oct 15 2026, run ONCE, tag "nasdaq_v2")

`lab/run_final_test.py` -> `asia_news_lab.final_test({"nasdaq_v2": (newsbot.backtest.make_trades, cfg, "NAS100")},
tag="nasdaq_v2")` with cfg = LOCKED_NQ.json (locked 2026-11-05T09:28:40Z). Output: final_test_nasdaq_v2.txt /
final_test_nasdaq_v2.json (the toolkit also wrote results/asia_news/nasdaq_v2.json in the repository). The signal
pair's Jul-Oct bars came through the toolkit (`asia_news_lab._m1`, cut to the NAS100 span final_test passed).

| | n | R | PF | win | max DD (10 %) | $1,000 -> | success rule (>= 8 trades, R > 0, PF >= 1.3, DD > -35 %) |
|---|---|---|---|---|---|---|---|
| Jul 1 - Oct 15 2026 | 13 | +2.34 | 2.24 | 62 % | -15.9 % | 1,236 | **yes** |
| same at 2 x cost | 13 | +2.14 | 2.10 | | -16.2 % | | |
| Jan-Jun 2026 (build) | 24 | +4.41 | 2.97 | 67 % | -7.2 % | 1,507 | (passes the build rules) |

The 13 trades (from the final_test output): RBNZ Jul 8 long -0.21; AUD jobs Jul 23 long -1.00 (the only stop hit, in
either period); AUD CPI Jul 29 short +0.01; NZD jobs Aug 4 short -0.46; RBA Aug 11 short +0.32; AUD jobs Aug 20
short +0.16; AUD CPI Aug 26 long +0.54; AUD GDP Sep 2 long -0.13; NZD GDP Sep 16 long +0.69; AUD jobs Sep 24 short
+1.04; RBA Sep 29 long +0.92; AUD CPI Sep 30 short -0.09; AUD jobs Oct 15 short +0.55.
Breakdown: AUD 10 trades +2.32 R, NZD 3 +0.02; rate decisions 3 +1.03, data 10 +1.30; longs 6 +0.80, shorts 7 +1.53
(in Jan-Jun the shorts were flat - here they carried it, so "always long" did not drive the out-of-sample result);
by month Jul -1.20 (3), Aug +0.56 (4), Sep +2.43 (5), Oct +0.55 (1). R without the best 1 / 2 / 3 trades: +1.30 /
+0.38 / -0.17.

Reading: the locked rule met the success rule out of sample, with per-trade R (+0.18) the same as in the build period.
It should not be over-read:
* 13 trades; the profit comes from 2-3 of them (Sep 24, Sep 29, Sep 16) and the drawdown (-15.9 %) was twice the
  build period's; a July start would have been 3 losses in a row (-1.2 R).
* Jul-Oct was already used once, for the first bot's final test (the toolkit says so); this build did not look at that
  result (results/ was not read), but the months are no longer pristine.
* The build-period evidence that this is a release effect at all is weak (section 3); one out-of-sample period with 13
  trades (mean +0.18 R, t = 1.1, bootstrap P(mean <= 0) = 0.12) does not change that much. The planned 2025 exam (more events) is
  the better judge; until then trade it in the dry-run, then at 1-2 % risk rather than 10 %.

## 7. 2025 exam (Jan-Dec 2025, run ONCE by the coordinator after the final_test)

Same locked cfg (LOCKED_NQ.json), the bot's own `newsbot.backtest.make_trades`, Forex Factory calendar from
2024-12-01, NAS100 / AUDUSD / NZDUSD M1 bars from 2024-11-01 (the signal pairs passed in explicitly as `aux`), Exness
costs with the news multiplier. Output: `results/asia_news/exam2025_nasdaq_v2.json`. Success rule (stated in the
toolkit before any build): R > 0 and PF >= 1.2.

| | n | R | PF | win | max DD (10 %) | $1,000 -> | success |
|---|---|---|---|---|---|---|---|
| 2025 | 47 | +0.26 | 1.02 | 45 % | -46.2 % | 942 | **no** |
| same at 2 x cost | 47 | -1.41 | 0.88 | 43 % | -53.8 % | 794 | |

By quarter: Q1 -2.09 R (11), Q2 -0.77 (11), Q3 -2.36 (15), Q4 +5.48 (10). AUD 36 trades +1.55 R, NZD 11 -1.29 R.
Longest losing streak 6. Diagnostic (not a candidate): buying NAS100 at the same entries whatever the pair did made
+2.24 R, PF 1.24 in 2025 - more than the rule, so the AUD / NZD reaction added no information about Nasdaq's direction.
The harness reproduces the saved Jul-Oct final_test trade for trade (13 / 13). (A first exam run by mistake read the
lock file's top level, so it ran the package defaults - v1's news entry - instead of nasdaq_v2; it was discarded and
nothing was changed after it.)

Conclusion: the Jul-Oct pass did not hold on a full year; with section 3's weak build-period evidence, nasdaq_v2 has no
demonstrated edge. Dry-run only.
