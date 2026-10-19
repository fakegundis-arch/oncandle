# Improving the gold Asian breakout (v1 -> v2)

Engine: `backtester/gold.py` (signals on M15, every trade simulated minute by minute on M1, Exness spread $0.20).
Search: `scripts/gold_improve.py` (one-change sweeps -> `sweep.csv`; 5,184 combinations -> `combo.csv`;
2,304 neighbours of the pick -> `neighbourhood.csv`). Choices made on Q4 2024 + 2025 only; 2026 is the check.

## What changed (v2)
| Setting | v1 | v2 | Why (Q4 2024 / 2025 evidence) |
|---|---|---|---|
| Donchian lookback | 10 bars | **20 bars** | higher median PF in both periods across all combinations |
| Trend slope check | EMA vs 1 h ago (4 bars) | **vs 4 h ago (16 bars)** | higher 2025 PF |
| Target | 3R | **4R** | higher median PF in both periods |
| Break-even | +1R -> +0.1R | **+1R -> +0.3R** | better Q4 2024 |
Unchanged: 00:00-06:00 UTC entries, EMA400 trend, previous-day high/low break, stop 1.5 ATR (min $2), one trade at a time.

## Results ($1,000, 10% risk, M1-exact)
| Period | v1 PF | v1 $ | **v2 PF** | **v2 $** | v2 trades | v2 win | v2 max DD |
|---|---|---|---|---|---|---|---|
| Q4 2024 | 1.24 | $1,193 | 1.54 | $2,380 | 67 | 54% | -82% |
| 2025 (choice) | 1.73 | $317,385 | 2.04 | $612,758 | 240 | 63% | -58% |
| **2026 (check)** | 1.47 | $17,726 | **1.67** | **$28,138** | 194 | 56% | -82% |

Robustness: all 2,304 neighbouring settings of v2 are profitable in 2025 and 2026 (92% in Q4 2024); median 2026 PF 1.68,
median 2026 result $22,180 (10th percentile $7,348). Of all 5,184 combinations, 91% are profitable in all three periods.

2026 month-end balance at 10%: Jan $4,778, Feb $2,277, Mar $1,989, **Apr $967**, May $3,682, Jun $3,503, Jul $4,414,
Aug $21,362, Sep $17,791, Oct $28,138. Longest losing streak 6 (8 in Q4 2024).
Risk per trade in 2026: 5% -> $9,197 (DD -55%); 8% -> $20,221 (-74%); 10% -> $28,138 (-82%); 15% -> $34,966 (-94%).
Monte Carlo (2026 trades resampled, 10%): median $25,557; 26% chance of >= $100,000; 5% chance of ending below $1,000.

## Tested and not adopted
* Longer/shorter sessions, 22:00/23:00 starts, London/NY extensions: worse.
* Tighter stops (1.0-1.25 ATR), partial take-profit, time exits, trailing after break-even: worse or mixed.
* Long only: great in 2025 (PF 2.14) but PF 1.31 in 2026 - do not bet on direction.
* Daily-trend filter, volatility filter, strong-close filter, Asian opening-range entries: mixed, not consistent.
* Max 1-2 trades/day and stop-after-a-loss: help Q4 2024 but neutral overall; optional.
* Drawdown risk throttles (cut risk after -15 to -50%): lower drawdowns but lower profit by the same amount.
* Adding to winners at +1-2.5R: more 2026 profit only through more leverage (DD -91 to -96%), worse 2025: rejected.
* Weekday / hour filters: no stable pattern.

EA: `mt5/Experts/GoldAsianBreakout.mq5` v2.00 (defaults now = v2).

---
# v3: drawdown control + diversification

## Why v2 suffered
Feb-Apr 2026 gold turned extremely volatile (median stop $19-23 vs ~$12 normally) and breakouts kept failing; Dec 2024
looked the same. v2 at 10%: $1,000 -> $4,778 (Jan) -> $967 (Apr) -> $28,138 (Oct), max DD -82%.

## Step 1 - drawdown filters on the gold strategy (`scripts/gold_v3.py`, 2,016 variants, chosen on Q4 2024 + 2025)
Added to v2:
1. **Daily trend:** buy only if yesterday closed above the D1 EMA(20); sell only if below.
2. **Volatility cap:** skip if ATR(14) > 2 x its 100-bar median.
3. **Equity-curve filter:** every signal is traded on paper; a real trade is placed only if the last 10 paper trades
   sum to >= -2R (the strategy "sits out" its own losing streaks and comes back when the paper trades recover).
4. **Weekly stop:** after this week's real trades lose 2R, no new trades until next week.

| Gold alone, 10% risk | Q4 2024 | 2025 | 2026 (check) |
|---|---|---|---|
| v2 | $2,380, DD -82% | $612,758, DD -58% | $28,138, DD -82% |
| **v3** | **$9,450, DD -34%** | $125,692, **DD -42%** | **$30,750, DD -64%** (PF 2.18, 100 trades) |
The 144 neighbouring variants (d1 trend 20, equity filter 5-10 trades, any threshold / weekly cap) are all profitable in
all three periods; their median 2026 result is $9,929 (DD -66%), so v3's 2026 is at the good end.
Lower drawdowns, but one strategy alone still had -64% in 2026 at 10% risk.

## Step 2 - portfolio (`scripts/gold_v3_portfolio.py`; weights chosen on 2025 + Q4 2024 with a 35% drawdown budget)
Monthly R correlation with gold v3: Trump-tariff Dow -0.03, BTC H1 Run Fade -0.14, gold H4 MACD +0.35.

| v3 portfolio | Risk per trade |
|---|---|
| Gold Asian breakout v3 (`GoldAsianBreakoutV3.mq5`) | 7% |
| Truth Social tariff posts -> Dow (`results/truth/REPORT.md`, no EA yet) | 4% |
| BTC H1 Run Fade (`RunFade.mq5`) | 5% |
| Gold H4 MACD + EMA100 (`OnCandleTrend.mq5`, MACD strategy) | 4% |

| $1,000 | Q4 2024 | 2025 | **2026 (check)** |
|---|---|---|---|
| v2 at 10% | $2,380 / DD -82% | $612,758 / -58% | $28,138 / **-82%** |
| **v3 portfolio** | $5,746 / DD -31% | $176,034 / -34% | **$38,694 / DD -33%** |
| v3 portfolio without the Truth Social leg | $6,404 / -26% | $94,737 / -37% | $25,720 / -35% |
| gold v3 alone at 7% | $5,339 / -25% | $40,452 / -31% | $15,649 / -50% |

2026 month-end balance (full v3 portfolio): Jan $4,678, Feb $4,086, Mar $4,735, Apr $4,061, May $6,745, Jun $7,244,
Jul $8,316, Aug $32,392, Sep $38,351, Oct $38,694.
Lowest balance $1,120. Up to ~21% of equity can be at risk at once when all four strategies hold trades.
Note: a simulator bug (a trade opened and stopped in the same minute was not counted) was found and fixed; all numbers
above are after the fix.

## Portfolio rerun with the upgraded parts (same 7 / 4 / 5 / 4% weights, chosen earlier on 2025)
Gold Asian breakout v3 (7%) + Truth tariff Dow (4%) + **BTC Run Fade v2** (5%) + **Gold MACD v3, H2** (4%):

| $1,000 | Q4 2024 | 2025 | **2026** |
|---|---|---|---|
| Portfolio with upgraded parts | $7,835 / DD -33% | $382,457 / -40% | **$98,632 / DD -32%** |
| ... without the Truth Social leg | $8,749 / -28% | $208,175 / -42% | $66,744 / -32% |
Each part's improvement was chosen on Q4 2024 + 2025, but every chosen setting sits at the good end of its
neighbourhood, so treat these as optimistic; 2025 figures are in-sample.

---
# v4 (`scripts/gold_v4.py`, `scripts/gold_v4_search.py` -> `v4_grid.csv`, `v4_search.parquet`)

Goal: more than v3 (and $50k+ in 2026) without big drawdowns.

1. **Quality-tiered sizing** (keep every v2 trade, risk by flags: long side, daily trend, volatility, regime,
   equity-curve health, week not down 2R): 1,415 rules. Under a 45% drawdown budget (Q4 2024 + 2025) the best made
   $17k-27k in 2026: not better than v3. Only "long" and "week not down" were better in every period.
2. **Broad search** (864 engine variants x 15 overlay settings x risk 8-20% x short size 1 / 0.5 / 0): 194,400
   combinations. Picked on Q4 2024 + 2025 under 35-45% drawdown budgets, the top 100 made a median $6k-12k in 2026
   and none reached $50k (they fit 2025). Only 194 combinations reach $50k in 2026 with DD under 50%; they need a
   volatility-regime filter that cannot be judged in Q4 2024 and were mediocre in 2025, so they are hindsight picks.

## v4 = v3 + side-dependent size (shorts were weaker in Q4 2024, 2025 and 2026)
Longs 12%, shorts 6% (`GoldAsianBreakoutV4.mq5`, `v4_trades.csv`).

| $1,000 | Q4 2024 | 2025 | **2026** |
|---|---|---|---|
| v3 (10%) | $9,450 / DD -34% | $125,692 / -42% | $30,750 / -64% |
| **v4 (12% / 6%)** | **$12,046 / -22%** | **$181,427 / -47%** | **$38,290 / -63%** |
| v4 at 10% / 5% | $8,540 / -19% | $96,534 / -41% | $24,724 / -56% |

2026 month-end (v4): Jan $7,260, Feb $4,355, Mar $4,093, Apr $3,386, May $4,502, Jun $4,609, Jul $4,990,
Aug $34,216, Sep $37,489, Oct $38,290.
Neighbours (288 variants of d1 trend / equity filter / weekly stop, same sizing): all profitable in every period;
median 2026 $11,036 vs $9,706 for the same neighbours at v3 sizing; Q4 2024 median DD -39% vs -52%.
**$50k+ in 2026 with low drawdowns is not reachable on gold alone with any rule chosen in advance**; it needs
15%+ risk (DD -72%) or the multi-strategy portfolio ($98,632 in 2026, DD -32%).

---
# v5: settings chosen on 2026 (`scripts/gold_v5_search.py` -> `v5_search.parquet`, 691,200 combinations)

Reverse test: pick on 2026 (in-sample, so 2026 is overstated), check on 2025 and Q4 2024 (out-of-sample).
* Picking only on 2026 favours a volatility-regime filter that needs 60 days of history: those settings barely trade
  in Q4 2024 (end slightly down) and carry 2025 drawdowns of -61% to -85%.
* With the extra condition that 2025 and Q4 2024 are profitable and every drawdown stays within 60%, the best 2026
  result is the v5 below. **$400k in 2026 with 2025 and Q4 2024 profitable needs drawdowns of about -64% or worse**
  (same rules at 12% on both sides: 2026 $387,960 DD -64%, 2025 $389,261 DD -68%, Q4 2024 $1,480 DD -73%).

## v5 rules (`GoldAsianBreakoutV5.mq5`, `v5_trades.csv`)
v2 entries with Donchian 10 (EMA400 trend rising vs 16 bars ago, or the previous-day high/low break), 00:00-06:00
UTC, stop 1.5 ATR, target 4R, stop to +0.3R at +1R, **max 2 trades a day, weekly stop -2R**, no daily-trend /
volatility / equity-curve filter. **Longs 12%, shorts 6%.**

| $1,000 | Trades | Win | PF | Result | Max DD | Longest losing streak |
|---|---|---|---|---|---|---|
| **2026 (chosen on)** | 207 | 58% | 1.94 | **$126,210** | -57% | 7 |
| 2025 (test) | 254 | 62% | 1.86 | **$425,687** | -58% | 6 |
| Q4 2024 (test) | 55 | 51% | 1.41 | $2,550 | -56% | 8 |

2026 month-end: Jan $7,891, Feb $5,714, Mar $6,923, Apr $5,723, May $18,634, Jun $18,252, Jul $18,087, Aug $86,124,
Sep $69,940, Oct $126,210. 2025 month-end: Mar $11,957, Jun $37,891, Sep $137,358, Dec $425,687.

| Same rules, risk longs / shorts | 2026 | 2025 | Q4 2024 |
|---|---|---|---|
| 10% / 5% | $75,855 (-49%) | $225,348 (-51%) | $2,370 (-49%) |
| **12% / 6%** | **$126,210 (-57%)** | **$425,687 (-58%)** | **$2,550 (-56%)** |
| 12% / 12% | $387,960 (-64%) | $389,261 (-68%) | $1,480 (-73%) |
| 15% / 15% | $649,359 (-72%) | $630,141 (-77%) | $1,287 (-81%) |
| 20% / 20% | $763,750 (-83%) | $677,523 (-88%) | $855 (-90%, a loss) |

Neighbours (216 variants: Donchian 10-15, RR 3-5, stop 1.25-2, BE buffer 0.1-0.5, max/day 2 or none, weekly stop
-2/-3): all profitable in 2026 and 2025, 94% in Q4 2024; median 2026 $23,851 (25-75%: $14.8k-$35.9k), median DD -73%.
The pick is at the lucky end of its family, as expected for a setting chosen on the year it is scored on.

## One rule set for every month, chosen on 2026 only (after v5)
The seasonal versions (different rules by calendar month) were deleted: switching rules by month has no market
reason behind it. This is the honest attempt to beat v5 with **one rule set for all months**, settings chosen on
**2026 only**, tested on **2025** and Q4 2024. Data: `scripts/gold_monthly_search.py` (497,664 all-year combinations
with month-by-month returns). Each selection rule was fixed before its 2025 result was looked at.

| Selection rule (2026 only) | 2026 (chosen on) | 2025 (test) | Q4 2024 (test) |
|---|---|---|---|
| **v5** (for reference) | $126,210, 5/10 months up | **$425,687**, 9/12 up | $2,550 |
| 1. Best 2026 total with >= 9/10 months up, no month below -15% | $895,812, 9/10 up | $7,082, 8/12 up, worst -44% | $834 |
| 2. Family with the best 25th-percentile 2026 result, its best 2026 member | $341,913, 8/10 up | $75,196, 9/12 up, worst -30% | (regime warm-up) |
| 3. Same family, member with the best worst month in 2026 | $152,767, 8/10 up | $24,356, 8/12 up, worst -36% | $827 |

* Rule 2's family (00-06, Donchian 15, EMA400 rising vs 16 bars, previous-day break, stop 1.5 ATR, 4R, BE +0.3R;
  432 overlay / filter / risk variants) was profitable in 2025 in all 432 variants (median $48,320). The rules work,
  but none of the variants beats v5 on the test year.
* Q4 2024 can't be measured for variants with the regime filter: it needs 60 days of history and the data starts in
  October 2024.
* Conclusion: **no single rule set found beats v5 out of sample.** v5 remains the recommended version. Trying more
  rules until 2025 looks good would turn 2025 into a selection year, so the search stops here.

## v9: three breakout engines together, same rules every month (`GoldAsianBreakoutV9.mq5`, `scripts/gold_v9.py`)
Engines v5, B and C all run **all year**, each with its own signals, filters, position and risk (no calendar
switching). Up to three trades can be open at once. 454 ways of combining were tested (`v9_combos.csv`): engines
trading together at 3-8% each, one trade at a time from the first engine to signal, or a trade only when 2-3 engines
agree on the same day. Picked on **2026 only** (most months up, no month below -20%, drawdown no worse than -55%,
then the highest 2026 total): **together, v5 3% / B 6% / C 3%, shorts at full size.**

| $1,000 | Q4 2024 (test) | 2025 (test) | 2026 (chosen on) |
|---|---|---|---|
| v5 | $2,550 (-56%), 2/3 up | **$425,687** (-58%), 9/12 up | $126,210 (-57%), 5/10 up |
| **v9** | $1,552 (-42%), 2/3 up | **$104,212 (-66%), 10/12 up** | **$603,341 (-53%), 10/10 up** |
| v9 without C (v5 3% / B 6%) | $1,145 (-31%) | $50,607 (-62%), 9/12 up | $213,880 (-62%), 10/10 up |

v9 2026: Jan +575%, Feb +35%, Mar +75%, Apr +6%, May +337%, Jun +53%, Jul +12%, Aug +257%, Sep +22%, Oct +10%
(529 trades, 58% won). 2025: Jan +82%, Feb +136%, Mar +25%, Apr +175%, May +25%, Jun +118%, Jul +17%, Aug -11%,
Sep +49%, Oct -23%, Nov +108%, Dec +4% (683 trades, 61% won). Q4 2024: Oct +47%, Nov +68%, Dec -37%.

**Honest reading**
* One rule set every month: the month-by-month results come from the same three engines all year.
* All 234 combinations that passed the 2026 rule were profitable in 2025 (median $95,177).
* 2026 is in-sample: v5 was chosen on 2026, engine B on Feb-Jul 2026, engine C on Apr/Jul/Sep 2026.
* 2025 is not fully clean: engine C's search also ranked Apr/Jul/Sep 2025. The fully clean check is v9 without C:
  2025 $50,607, 9/12 months up.
* v9 makes less than v5 in 2025 and Q4 2024, with a deeper 2025 drawdown (-66% vs -58%), but more 2025 months up.
* Q4 2024 understates engine B: its regime filter needs 60 days of history and the data starts in October 2024
  (2 trades).

## v10: v5 with three general filters, same rules every month (`GoldAsianBreakoutV10.mq5`)
Goal: fix v5's losing 2026 months (Feb -28%, Apr -17%, Jun -2%, Jul -1%, Sep -19%) with rules that apply to every
month. Search: `scripts/gold_v10_search.py` (196,608 combinations of v5 plus previous-day-range filter, Monday skip,
daily trend, regime filter, stop after a daily loss, partial profit, break-even trigger, Donchian, slope, stop, RR,
trades/day, equity-curve filter, weekly stop, risk). Selection on **2026 only** (`scripts/gold_v10.py`): all five
months profitable, at least a quarter of one-step neighbours also passing, then the highest 2026 total. (The first
rule, "2026 total >= v5" with half the neighbours passing, had no candidates: the best all-five-up setting makes
$87,152 in 2026 and no setting has more than 42% of neighbours passing.)

**v10 rules:** v5 entries and exits (Donchian 10, EMA400 rising vs 16 bars, previous-day break, 00:00-06:00, stop
1.5 ATR, 4R, BE +1R -> +0.3R, weekly stop -2R) plus **daily trend** (D1 EMA20), **regime filter** (5-day / 60-day mean
true range <= 1.6) and **equity-curve filter** (last 10 paper trades >= -2R); no daily limit; **8% risk both sides**.

| $1,000 | Q4 2024 (test) | 2025 (test) | 2026 (chosen on) |
|---|---|---|---|
| v5 (12% / 6%) | $2,550 (-56%), 2/3 up | **$425,687 (-58%)**, 9/12 up, worst month -22% | $126,210 (-57%), 5/10 up |
| **v10 (8%)** | $1,607 (-29%), 2/3 up | $38,178 (-42%), 9/12 up, worst month -8% | $72,607 (-33%), **10/10 up** |
| v10 at 10% | $1,735 (-35%) | $68,795 (-52%), 9/12 up | $149,382 (-39%), 9/10 up |
| v10 at 12% | $1,846 (-41%) | $111,284 (-61%), 9/12 up | $273,620 (-45%), 8/10 up |

v10 2026: Jan +418%, Feb +2%, Mar +29%, Apr +13%, May +202%, Jun +2%, Jul +9%, Aug +131%, Sep +14%, Oct +6%
(131 trades, 60% won). 2025: Jan +114%, Feb +106%, Mar +99%, Apr +49%, May +20%, Jun -0%, Jul -7%, Aug -8%,
Sep +81%, Oct +20%, Nov +18%, Dec +11% (145 trades, 62% won).
Q4 2024 is measured with the regime filter starting after 20 days of history (the data begins in October 2024); with
the full 60-day warm-up v10 takes 1 trade there. Live, the EA has the full history.

**Honest reading**
* One rule set for every month; v5's bad 2026 months are now all positive, but only just (+2% to +14%).
* The same v10 engine is profitable in 2025 under all 24 overlay / risk variants (median $68,983).
* Selecting for those five 2026 months is mostly luck in general: of the 631 settings that made all five profitable,
  only half were profitable in 2025 (median $1,007). v10 passed, but the selection itself is weak evidence.
* v10 trades much less profit for much smaller drawdowns: 2025 -42% vs v5's -58%, 2026 -33% vs -57%.

## v11: v10 plus a New York-session engine, same rules every month (`GoldAsianBreakoutV11.mq5`)
Goal: more profit than v10 with one rule set for every month; chosen on 2026 only, tested on 2025 and Q4 2024.

**Attempt 1 (rejected): bigger winners and more entries.** `scripts/gold_v11_search.py`, 207,360 combinations of
v10 plus RR 3-6, ATR trailing stop, adding a second position at +1R / +2R, session to 08:00, Donchian 15, daily
trend EMA 10/20/50, regime 1.4/1.6/2.0, Asian-range entries, equity-curve filter and risk (`scripts/gold_v11.py`).
Rule: >= 9/10 months up in 2026, 2026 drawdown >= -45%, 2026 total above v10, half the neighbours passing (none
did; relaxed to 35%, the best group available). Pick: v10 + a second position at +2R, equity filter 5 / -1R, 10%:
2026 $724,445 (-39%), 10/10 up, **but 2025 $12,031 (-84%), May 2025 -66%.** Adding at +2R turns a trade that falls back
to the break-even stop into a -1.4R loss; it paid in trending 2026 only. Same engine, all 60 overlay/risk variants:
median 2025 $21,114, against $74,486 for the v10 engine.

**Attempt 2 (v11): a second v10-style engine on another session**, trading alongside v10 with its own position
(`scripts/gold_v11_sessions.py`, 90 setups: London 06-09 / 07-10 / 08-11 or New York 12-15 / 13-16, Donchian 10/15/20,
seven risk splits). Same rule (>= 9/10 months up, drawdown >= -45%, above v10), then the highest 2026 total:
**Asia engine (v10) 10% + New York engine 12:00-15:00, Donchian 15, 5%.**

| $1,000 | Q4 2024 (test) | 2025 (test) | 2026 (chosen on) |
|---|---|---|---|
| v5 (12% / 6%) | $2,550 (-56%) | $425,687 (-58%), 9/12 up | $126,210 (-57%), 5/10 up |
| v10 (8%) | $1,607 (-29%) | $38,178 (-42%), 9/12 up | $72,607 (-33%), 10/10 up |
| v10 at 10% | $1,735 (-35%) | $68,795 (-52%), 9/12 up | $149,382 (-39%), 9/10 up |
| **v11** | $1,440 (-57%), 1/3 up | **$97,956 (-53%), 10/12 up** | **$244,454 (-35%), 9/10 up** |

v11 2026: Jan +534%, Feb +0%, Mar +81%, Apr +30%, May +190%, Jun +64%, Jul -1%, Aug +171%, Sep +17%, Oct +9%
(196 trades: Asia 131, NY 65). 2025: Jan +125%, Feb +198%, Mar +96%, Apr +46%, May +22%, Jun -15%, Jul +30%, Aug -17%,
Sep +192%, Oct +21%, Nov +26%, Dec +3% (260 trades: Asia 145, NY 115). Q4 2024: Oct -4%, Nov +120%, Dec -32%.

**Honest reading**
* The New York window was the best second session in 2026 **and** in 2025 (median 2025 of all its setups $51,434,
  other sessions $11,581-$30,523). All 18 New York setups were profitable in 2025 and Q4 2024; 13 of 18 beat v10
  alone in 2025.
* The New York engine's edge is small: +0.13R per trade in 2025 (115 trades), -0.11R in Q4 2024 (23 trades). v11's
  Q4 2024 is worse than v10's ($1,440 vs $1,607, drawdown -57% vs -29%).
* Against v10 at the same Asian risk (10%), v11 adds about 42% to 2025 profit with a similar drawdown.

## v12 attempt: improving v11 (`scripts/gold_v12.py`, `v12_stageA/B/C.csv`)
Same method: one rule set every month, each stage chosen on 2026 only (>= 9/10 months up, drawdown >= -45%, above the
previous stage, half the neighbours passing), 2025 and Q4 2024 looked at once at the end.

* **Stage A, New York engine settings** (360: session 11-15 / 12-15 / 12-16 / 13-15 / 13-16, Donchian 10/15/20, RR 3/4/5,
  stop 1.5/2, daily trend on/off, regime on/off): only 2 beat v11's own New York engine in 2026, neither with half its
  neighbours passing. v11's New York engine kept.
* **Stage B, a third engine** (64: London 06-08 / 06-09 / 07-09 / 07-10 on gold, or v10 rules on silver in the Asian
  or New York session, 3% / 5%): London 07-09 passed in a broad cluster in 2026 (all Donchian / RR / risk variants).
* **Stage C, risk per engine** (48): pick Asia 12%, New York 4%, London 07-09 (Donchian 20, 4R) 3%.

| $1,000 | Q4 2024 (test) | 2025 (test) | 2026 (chosen on) |
|---|---|---|---|
| v11 (Asia 10%, NY 5%) | $1,440 (-57%) | $97,956 (-53%), 10/12 up | $244,454 (-35%), 9/10 up |
| v12 pick (Asia 12%, NY 4%, London 3%) | $1,390 (-58%) | $128,944 (-60%), 10/12 up | $597,794 (-44%), 9/10 up |
| same risk without London (Asia 12%, NY 4%) | $1,603 (-58%) | $152,918 (-58%), 10/12 up | $414,516 (-40%), 9/10 up |

**Verdict: no structural improvement.** The London engine helped in 2026 only: with v11's risk, all 12 London 07-09
setups made less in 2025 than v11 alone ($65,633-$94,330 vs $97,956), and the pick makes less in 2025 than the same
risk without London. Silver engines also lowered 2025 (median $75,498 Asian session, $34,283 New York). The only
change that raised 2025 profit is more risk on the Asian engine (12% instead of 10%), with deeper drawdowns. No v12
robot was built.

## v13: improving v12 (Asia 12% + New York 4%) (`GoldAsianBreakoutV13.mq5`)
Same method: one rule set every month, chosen on 2026 only (>= 9/10 months up, drawdown >= -45%, above v12's
$414,516, half the neighbours passing), 2025 and Q4 2024 looked at once per attempt.

1. **Exits and entry confirmation, shared by both engines** (`scripts/gold_v13_search.py`, 14,580: stop 1.25/1.5/2 ATR,
   RR 3/4/5, break-even at 0.75/1/1.5/2R or none, buffer 0/0.3/0.6R, half profit at 1R or 2R, strong-close entry,
   exit at 16:00 / 20:00, four risk splits): 2 pass, none robust. v12's exits sit on a sharp 2026 peak: one step away,
   2026 falls to $9k-$335k (stop 1.25 ATR $32,408, BE buffer 0.6R $34,513). Rejected.
2. **Drawdown throttle** (`scripts/gold_v13_risk.py`, 150: base risk Asia 10-18% / NY 4-6%, cut to 25% / 50% when the
   account is 10-30% below its peak): cutting risk in a drawdown misses the large winners that end the drawdowns;
   at Asia 12% a 50% cut at -10% turns 2026 $414,516 into $112,000. Rejected.
3. **A third engine on 30-minute / 1-hour bars** (`scripts/gold_v13_tf.py`, 128; the lab now takes `bar_min`): a broad
   2026 cluster (1-hour New York, 3R, 3%) passed, but the pick made less on the test years than v12 (2025 $142,236 vs
   $152,918, Q4 2024 $1,496 vs $1,603), and only 17 of 32 1-hour New York setups beat v12 in 2025. Rejected.
4. **Risk on the Asian engine** (same table as 2): the only setup passing rules 1-3, Asia 14% / New York 4%, also beats
   v12 on both test periods. It is a bigger bet on the same rules, not a better rule.

| $1,000 (v11 engines) | Q4 2024 (test) | 2025 (test) | 2026 (chosen on) |
|---|---|---|---|
| v11 (Asia 10%, NY 5%) | $1,440 (-57%) | $97,956 (-53%), 10/12 up | $244,454 (-35%), 9/10 up |
| v12 (Asia 12%, NY 4%) | $1,603 (-58%) | $152,918 (-58%), 10/12 up | $414,516 (-40%), 9/10 up |
| **v13 (Asia 14%, NY 4%)** | **$1,684 (-62%)** | **$221,532 (-64%), 9/12 up** | **$678,871 (-45%), 9/10 up** |
| Asia 16%, NY 4% | $1,746 (-65%) | $292,044 (-70%) | $1,004,896 (-50%) |
| Asia 18%, NY 4% | $1,788 (-69%) | $351,928 (-76%) | $1,351,685 (-57%) |

Profit and drawdown both rise with risk in every period; v13 is the largest risk inside the -45% 2026 drawdown cap.

## Costs and the 2023 - 2024 check (after v13)
### 1. Costs: Dukascopy's recorded spread is about 3x the $0.20 used so far
The M1 files carry the bid/ask spread of every minute. Median gold spread by UTC hour: $0.64-0.67 in 00:00-06:00,
$0.57-0.59 in 12:00-15:00; it rose with price (Asian session median $0.42 in late 2024, $0.61 in 2025, $0.74 in 2026).
The lab can now charge the recorded spread at each trade's entry minute (`cost_mode="data"`, `cost_scale`).
Exness's real spread may differ (`results/gold/cost_sensitivity.csv`):

| $1,000, 2025 | $0.20 | $0.40 | $0.60 | half Dukascopy | Dukascopy |
|---|---|---|---|---|---|
| v5 | $425,687 | $142,353 | $63,571 | $396,093 | $56,407 |
| v13 | $221,532 | $52,680 | $24,063 | $236,198 | $18,767 |
| v12 | $152,918 | $44,309 | $21,897 | $168,664 | $17,954 |
| v11 | $97,956 | $35,526 | $18,527 | $117,051 | $15,915 |
| v10 | $38,178 | $15,521 | $10,324 | $36,554 | $9,204 |
| v9 | $104,212 | $17,142 | $10,808 | $48,574 | $6,167 |

The R outcomes stay -1 / +0.3 / +4, but a wider spread means fewer trades reach +4R (v13 2026: 35 -> 28).

### 2. Final exam on gold data no version ever saw (Feb 2023 - Sep 2024)
`scripts/fetch_dukascopy_m1.py XAUUSD --start 2023-01-01 --end 2024-09-30 --out data/old`, joined to the main file as
`data/XAUUSD_LONG_M1.csv` (reproduces every 2025 / 2026 result exactly). `scripts/gold_exam.py`, Jan 2023 = warm-up:

| $1,000 at $0.20 | Feb-Dec 2023 | Jan-Sep 2024 |
|---|---|---|
| v5 | $79 (-96%) | $2 (-100%) |
| v9 | $54 (-97%) | $23 (-98%) |
| v10 | $394 (-80%) | $271 (-81%) |
| v11 | $204 (-90%) | $185 (-88%) |
| v12 | $149 (-93%) | $128 (-92%) |
| v13 | $95 (-95%) | $84 (-95%) |

Why (v5 trades): average +0.006R per trade in 2023 and -0.21R in Jan-Sep 2024 **even with zero cost**, against
+0.29R / +0.32R / +0.36R in Q4 2024 / 2025 / 2026. Gold was quiet then (median M15 ATR 0.066% / 0.081% of price,
against 0.123% in 2025 and 0.184% in 2026; median stop $2.00 / $2.74 against $6.24 / $12.25). The edge rises with
volatility (ATR below 0.064% of price: -0.10R per trade; 0.14-0.20%: +0.63R), but even the quietest trades of
Q4 2024 / 2025 were profitable while those of 2023 / 2024 were not: part of the edge belongs to the post-2024 market.
**Every version up to v13 was chosen on (and only works in) the volatile 2025-2026 market.**

## v15 attempts: v13 with drawdown controls (no robot built)
Request: improve v13 with smaller drawdowns and, if possible, more profit; choose on 2026, test on 2025. Every trade
charged a realistic spread. Search `scripts/gold_v15_search.py` (69,120 per spread level): break-even +1R / +1.5R to
+0.3R / +0.5R, target 3-5R, stop for the day after a loss, spread guard (stop >= 8 / 12 / 16 x the spread of the minute
before the order), minimum volatility 0 / 0.08 / 0.10% of price, graded equity-curve filter (last 10 / 20 paper
trades: pause below -2R / -3R, optional half risk below 0R), weekly stop, risk Asia 6-14% / New York 0-4%.

**Attempt 1, chosen at Dukascopy's recorded spread** (rule: 2026 drawdown >= -40%, >= 8/10 months up, above v13,
half the neighbours passing): Asian engine only, 8%, break-even +1.5R -> +0.5R, 4R, spread guard 8x, minimum
volatility 0.08%, equity filter 20 / -3R. 2026 $212,523 (-37%) against v13's $41,851 (-76%), but **2025 $1,798
(-55%) against v13's $18,767 (-86%)**. All 40 robust candidates made money in 2025 (median $2,783), none beat v13.
The first run read the spread guard's spread at the end of the entry minute; reading the minute before (as live)
left 2026 unchanged but cut this pick's 2025 from $7,715 to $1,798: the guard reacts to noise.

**Attempt 2, chosen at a $0.30 spread** (broker reviews put Exness Standard gold at roughly $0.16-0.35 in calm
markets: [BrokerListings](https://brokerlistings.com/reviews/exness/spreads),
[TradingBeasts](https://tradingbeasts.com/xau-usd-lowest-spread-brokers/)). The first rule had no candidates; with
"no worse drawdown than v13 (-45%) and more profit" 56 passed, all v13 plus small tweaks, none with more than a third
of the neighbours passing. Most robust: v13 + minimum volatility 0.08% + half risk while the last 10 paper trades sum
to between -2R and 0R. 2026 $423,367 (-45%) against $387,196, but **2025 $11,656 (-87%) against v13's $157,959 (-71%)**.

| $1,000, 2025 (test) | $0.20 | $0.30 | $0.40 | $0.60 | Dukascopy |
|---|---|---|---|---|---|
| v11 (Asia 10%, NY 5%) | $97,956 (-53%) | $86,179 (-59%) | $35,526 (-69%) | $18,527 (-64%) | $15,915 (-68%) |
| v12 (Asia 12%, NY 4%) | $152,918 (-58%) | $118,171 (-65%) | $44,309 (-75%) | $21,897 (-75%) | $17,954 (-79%) |
| **v13 (Asia 14%, NY 4%)** | **$221,532 (-64%)** | **$157,959 (-71%)** | **$52,680 (-80%)** | $24,063 (-82%) | $18,767 (-86%) |
| v15 attempt 1 | $13,570 (-59%) | $11,483 (-59%) | $8,135 (-59%) | $10,770 (-59%) | $1,798 (-55%) |

**Verdict:** the drawdown controls that help in 2026 did not carry over to 2025; v13's rules remain the best on the
test year at every spread. The only drawdown control that held up is lower risk on the same rules (v12, v11).

## Exness's real gold spread (MT5 export of XAUUSDm, the Standard account)
Source: the user's MT5 export of XAUUSDm M1 bars with spread, 8 Jul - 16 Oct 2026 (100,000 bars; kept locally as
`data/exness/XAUUSDm_M1_mt5.csv`, not in git). MT5 records each bar's lowest spread, so the spread at an order can be
slightly higher.

* **Exness spread: $0.24 (56% of minutes) or $0.26 (44%), at every hour**, including 00:00-06:00 UTC; median $0.24,
  90th percentile $0.26, highest $0.58. Dukascopy at the same minutes: $0.75-0.78 in the Asian session, $0.56-0.62 in
  the day. Exness server time = UTC (prices match Dukascopy within a median $0.21 at the same minute, $6+ when shifted
  by an hour).
* So the Dukascopy-spread figures of the cost sections above are too pessimistic for this account; **$0.25 is the
  measured cost and $0.30 a cautious one** (`results/gold/exness_spread_table.csv`):

| $1,000 | Q4 2024 at $0.25 | 2025 at $0.25 | 2026 at $0.25 | 2025 at $0.30 | 2026 at $0.30 |
|---|---|---|---|---|---|
| v5 | $2,550 (-56%) | $348,493 (-58%) | $105,584 (-57%) | $306,795 (-58%) | $105,584 (-57%) |
| v9 | $1,593 (-53%) | $82,789 (-64%) | $405,766 (-56%) | $63,683 (-68%) | $336,219 (-56%) |
| v10 | $1,569 (-31%) | $40,659 (-44%) | $57,753 (-33%) | $28,357 (-44%) | $57,753 (-33%) |
| v11 | $1,164 (-60%) | $134,065 (-59%) | $144,704 (-35%) | $86,179 (-59%) | $144,687 (-35%) |
| v12 | $1,333 (-61%) | $198,676 (-65%) | $246,285 (-40%) | $118,171 (-65%) | $246,261 (-40%) |
| **v13** | $1,391 (-64%) | **$286,377 (-71%)** | **$387,233 (-45%)** | $157,959 (-71%) | $387,196 (-45%) |

  A $0.05 change in spread moves a year by up to ~30% either way (it flips a few +4R winners).
* **Exness's own prices** (`data/XAUUSD_EXNESS_M1.csv`: Dukascopy bars at $0.25 until 8 Jul 2026, then the Exness bars
  with their recorded spread), 8 Jul - 15 Oct 2026, against Dukascopy bars at $0.25:

| | Exness bars | Dukascopy bars | Identical trades |
|---|---|---|---|
| v13 | 59 trades, +11.3R, $1,000 -> $2,478 (-38%) | 56 trades, +13.0R, $1,000 -> $2,966 (-43%) | 51 (50 with the same result) |
| v12 | 59 trades, +11.3R, -> $2,352 (-34%) | 56 trades, +13.0R, -> $2,751 (-38%) | 51 (50) |
| v11 | 59 trades, +11.3R, -> $2,122 (-33%) | 56 trades, +13.0R, -> $2,446 (-32%) | 51 (50) |
| v5 | 75 trades, +12.9R, -> $2,789 (-62%) | 69 trades, +18.9R, -> $4,319 (-55%) | 64 (64) |

  The bots take mostly the same trades on Exness's feed; over this window the Exness results were ~15-35% lower, so
  treat the Dukascopy backtests at $0.25 as a slightly optimistic guide.

## v16 attempt: v5 and v13 engines blended (no robot built)
Request: beat both v13 and v5 in 2026 and 2025, with a 2025 drawdown better than -50%; choose on 2026, 2025 unseen.
Exness spread $0.25. `scripts/gold_v16_search.py`: up to four engines side by side (v5's Asian engine; v13's Asian
engine; v13's New York engine; a London 07-09 engine with v13's filters), their settings (trades/day, equity-curve
filter, break-even, minimum volatility, London Donchian / RR) and each engine's risk (0-14%, half-size shorts or not):
**2,211,840 combinations**, booked with a vectorised portfolio simulator (reproduces v13 and v5 exactly).

Rule on 2026 (`scripts/gold_v16.py`): above v13 ($387,233), drawdown >= -40%, >= 8/10 months up, half the
neighbours at least as good as v13 (first form, "half the neighbours pass the strict rules", had no candidates), then
the highest 2026 total. 114 passed the strict rules, 10 the neighbour rule.

| $1,000 at $0.25 | Q4 2024 | 2025 (test) | 2026 (chosen on) |
|---|---|---|---|
| v5 | $2,550 (-56%) | $348,493 (-58%) | $105,584 (-57%) |
| v13 | $1,391 (-64%) | $286,377 (-71%) | $387,233 (-45%) |
| v16 pick (v5-Asia 3% / sells 1.5%, v13-Asia 9% with BE +1.5R -> +0.3R, New York 6%, London 2%) | $1,864 (-68%) | **$110,239 (-78%)** | $865,210 (-40%) |

* None of the 10 robust 2026 candidates met the 2025 targets (median 2025 $97,243, median drawdown -75%).
* Of all 2,211,840 combinations, 12 meet the 2025 targets (all v5-heavy blends: 2025 $361k-549k at -50%), and they
  make only $88k-127k in 2026 (ranked about 1.1-1.3 millionth on 2026). **No combination beats both v5 and v13 in both
  years with a 2025 drawdown better than -50%**, even with hindsight.
* Choosing on both years together (no unseen year left except Q4 2024), the best balanced blends make about
  $200k-245k in each year with drawdowns of -39% to -50% (e.g. v5-Asia 6%, v13-Asia 3%, New York 4%, London 4%:
  2025 $213,432 (-49%), 2026 $217,819 (-44%), Q4 2024 $1,231 (-59%)).
* 2025 rewarded v5-style trading (no daily-trend filter), 2026 v13-style trading with the extra sessions; no blend is
  best in both.

## v17 (deleted)
Deleted at the user's request: the robot's settings were chosen on 2025 + 2026, so 2025 was not an unseen test for it.
Kept as the lesson for v18: the same engine family (v5's Asian engine + v13's Asian and New York engines with the 2026
study's exits, quiet skip, daily stop and loss limit; 7,717,500 combinations) chosen on 2026 alone, with a block-bootstrap
drawdown check, made $627,876 (-34%) in 2026 and then **$30,781 (-59%) in 2025** (independent recount $31,997, -56%)
and $1,831 (-40%) in Q4 2024. A higher-risk variant's best figures came from a floating-point tie at its 6.00% daily
stop (v5 and New York risked 6% each, so one loss put the day at exactly -6%).

## Measurement caveats (apply to every version above)
* **Weekly stop tie.** Two full losses in a week sum to -2R +/- 1e-14, so the -2R weekly stop is decided by rounding
  (in the backtests and in the EAs); the equity-curve filter has the same tie at exactly -2R. Making the weekly stop
  always or never fire at exactly -2R moves v5's 2025 from $348,493 to $260,734-272,274 and v13's from $286,377 to
  $244,821-274,922.
* **Drawdowns are on closed trades.** Counting open positions at each minute's close adds roughly 3-10 points.

## v18: chosen on 2026 only, 2025 unseen (`GoldAsianBreakoutV18.mq5`, `scripts/gold_v18.py`)
Protocol committed before the search (b7abce1); pick committed before 2025 was opened (a916dc9); 2025 and Q4 2024 kept
in a sealed file the selection code never reads, opened once.

* Engines: v5's Asian engine, v13's Asian engine (break-even / target variants, quiet skip), v13's New York engine
  (exit variants, quiet skip); risk v5 0-8% (full- or half-size sells), Asia 0-8%, New York 0-6%; daily loss-count limit
  off / 2 / 3. Tie-free -2R filters (1e-9 margin); no percentage daily stop. **2,116,800 combinations.**
* The selection rule itself was chosen by a test inside 2026: six candidate rules (bootstrap bar -50% / -40%, a 0.1R
  edge haircut, best point / best plateau), each choosing on Jan-May and scored on Jun-Oct, and the other way round.
  No rule kept the scoring half better than -40% in both directions (worse half: R1/R4 -53%, R3/R6 -47%, R2/R5 -42%),
  so the stated fallback took R2 (bootstrap worst decile better than -40%, highest 2026 total).
* **Pick:** v5 1%, Asia 7% (break-even +1.5R -> +0.3R, 4R, quiet skip below 0.11%), New York 5% (+0.6R -> entry, 3R,
  stop 1.25 ATR), no new trades after 3 losing trades in a day.

| $1,000 at $0.25 | Q4 2024 (unseen) | 2025 (unseen) | 2026 (chosen on) |
|---|---|---|---|
| v18 | $1,158 (-36%), 1/3 up | **$17,860 (-56%), 8/12 up, worst month -45%** | $922,583 (-30%), 9/10 up |

**It fails the target (2025 drawdown better than -50%).** No re-pick was made.
