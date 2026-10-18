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


## v7: seasonal two-mode bot for Feb-Jul (`GoldAsianBreakoutV7.mq5`, `scripts/gold_v7.py`)
Request: do better than v5 in February-July. v5's Feb-Jul 2026 turned $1,000 into only $2,292 (2 of 6 months up).
Search (`scripts/gold_febjul_search.py`, 737,280 combinations of session, Donchian, EMA, slope, stop, RR, BE buffer,
daily trend, volatility cap, regime filter, trades/day, equity-curve filter, weekly stop, risk), scored on the
**Feb-Jul 2026 window only (chosen on)** and checked on **Feb-Jul 2025 (test)**. The pick had to be profitable in
both windows with most months up.

**Mode B** (used Feb-Jul): Donchian 10, **EMA200 rising vs 8 bars ago**, previous-day break, 00:00-06:00, stop 1.5 ATR,
4R, BE +1R -> +0.3R, **regime filter** (5-day / 60-day mean true range <= 1.6: skip when gold is unusually wild),
**equity-curve filter** (last 10 paper trades >= -2R), weekly stop -2R, no daily limit, **10% risk both sides**.
Aug-Jan keeps v5 unchanged.

| $1,000, Feb-Jul only | 2026 (chosen on) | 2025 (test) |
|---|---|---|
| v5 | $2,292, 2/6 months up | **$21,141**, 5/6 up |
| **Mode B** | **$14,925, 6/6 up**, worst month 0%, DD -44% | $13,104, 5/6 up, worst -2%, DD -48% |
| Alternative A (00-08, Donchian 15, vol cap 2) | $46,864, 6/6 up | $4,075, DD -64% (rejected) |

Full years, $1,000 start each period:

| | Q4 2024 | 2025 | 2026 |
|---|---|---|---|
| v5 | $2,550 (-56%) | **$425,687** (-58%), 9/12 months up | $126,210 (-57%), 5/10 up |
| **v7 = B Feb-Jul + v5 Aug-Jan** | $2,550 (-56%) | $263,864 (-58%), 9/12 up | **$821,795 (-55%), 9/10 up** |

v7 2026 months: Jan +689%, Feb +82%, Mar +68%, Apr +0%, May +177%, Jun +61%, Jul +9%, Aug +376%, Sep -19%, Oct +80%.
v7 2025 months: Jan +157%, Feb +152%, Mar +23%, Apr +50%, May +49%, Jun +93%, Jul -2%, Aug -12%, Sep +186%, Oct -18%,
Nov +269%, Dec +3%.

**Honest reading**
* Mode B's settings were chosen on Feb-Jul 2026, so v7's 2026 result ($821,795) is mostly **in-sample**.
* On the test window (Feb-Jul 2025) mode B made less than v5 ($13,104 vs $21,141), so **v7's 2025 is below v5's**
  ($263,864 vs $425,687). B is smoother (5/6 months up, worst -2%) but not more profitable there.
* Neighbours of B (48 variants: session 00-06/01-06/00-08, Donchian 10/15, stop 1.5/2, RR 3/4, regime 1.4/1.6): all
  profitable in both Feb-Jul windows, 38 of 48 above $2,000 in both, but the **median is $1,971 in Feb-Jul 2026 and
  $4,354 in Feb-Jul 2025**. B is the luckiest member of its family; a typical neighbour is no better than v5.
* Conclusion: v7 is a reasonable alternative to v5 if smooth Feb-Jul months matter more than the highest total, but
  the evidence that it beats v5 out of sample is weak. Demo-test before using real money.

## v8: mode C for April, July and September (`GoldAsianBreakoutV8.mq5`, `scripts/gold_v8.py`)
Request: make April, July and September 2026 profitable (v7: +0%, +9%, -19%).
Search (`scripts/gold_weakmonths_search.py`, 497,664 combinations, month-by-month returns stored for every one).
Only 1.5% of all combinations make all three 2026 months > +10%. Among those, mode C was ranked by the same three
months of **2025**, so **both years were used to choose it**; there is no untouched test period for mode C.

**Mode C** (Apr, Jul, Sep): Donchian 15, EMA200 rising vs 8 bars ago, **no previous-day break**, **00:00-08:00**,
stop 1.5 ATR, 4R, BE +1R -> +0.3R, max 2 trades/day, equity-curve filter 10 / -2R, weekly stop -2R, 10% both sides.
Mode B now runs Feb, Mar, May, Jun; v5 runs Aug and Oct-Jan.

| $1,000 | Q4 2024 | 2025 | 2026 |
|---|---|---|---|
| v5 | $2,550 (-56%) | $425,687 (-58%), 9/12 up | $126,210 (-57%), 5/10 up |
| v7 | $2,550 (-56%) | $263,864 (-58%), 9/12 up | $821,795 (-55%), 9/10 up |
| **v8** | $2,550 (-56%) | **$663,535 (-58%), 10/12 up** | **$2,444,405 (-45%), 10/10 up** |
| mode C alone, all year | $2,381 (-47%) | $35,763 (-63%), 8/12 up | $89,673 (-48%), 8/10 up |

| | Apr 2026 | Jul 2026 | Sep 2026 | Apr 2025 | Jul 2025 | Sep 2025 |
|---|---|---|---|---|---|---|
| v7 | +0% (8 trades) | +9% (14) | -19% (15) | +50% | -2% | +186% |
| **v8** | **+15% (8)** | **+33% (15)** | **+73% (18)** | +299% | +35% | +98% |

v8 2026 months: Jan +689%, Feb +82%, Mar +68%, Apr +15%, May +177%, Jun +61%, Jul +33%, Aug +376%, Sep +73%,
Oct +80% (170 trades).

**Honest reading**
* All three target months are in the period used to choose mode C. v8's numbers are **in-sample**.
* Mode C is fragile. Of 864 neighbours (session 00-06/00-08/01-06, Donchian 10/15/20, slope, stop 1.5/2, RR 3/4,
  BE buffer, trades/day, weekly stop), only **4% keep April, July and September 2026 all positive**. The median
  neighbour makes April 2026 -25%, July +6%, September +14%. One-step changes to the session, Donchian, stop, RR or
  BE buffer each turn at least one target month negative.
* In its favour: as a stand-alone all-year bot mode C is profitable in Q4 2024, 2025 and 2026, so it is a working
  variant of the breakout rather than a pure fit to three months.
* Switching between three rule sets by calendar month has no market reason behind it. Expect future April/July/
  September results to look like the neighbour medians, not like the table above.
* At these account sizes, 10% risk on gold needs over 100 lots per trade; real fills would be worse than the backtest.
