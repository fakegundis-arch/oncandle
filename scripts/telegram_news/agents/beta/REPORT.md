# beta: price reaction after FJ / WB posts (search on data to 2026-06-30)

Saved by the lead from beta's final message (the subagent could not write .md files).  Search period 2025-01 ..
2026-04, check period 2026-05 .. 2026-06.  All figures from $1,000 at 10 % risk, 30 % open-risk cap (common.py).

## Conclusion
$200k from $1,000 at 10 % risk is not reachable honestly: the search's best in-sample results are as large as what the
same search finds on fake signals.  The best real result is the gold "news-shock momentum" rule below (Jan-Jun 2026
$1,000 -> $58.6k, drawdown -64 %).  Rules that traded Nasdaq failed on the check months; Nasdaq is used only as a
confirming signal.

## What price does after posts
* No spike at post time on average; FJ posts scheduled data ($MACRO) a median 37 s after the release (28-50 s).
* Following or fading the first 5-120 s after a post earns about minus the costs, at every delay and threshold.
* When a post lands during a big move already under way (>= 3-6 sigma over the last 30-300 s), gold keeps drifting the
  same way for 10 min - 2 h, usually after a small pullback in the first 2 min.  Weaker and rarer at random times;
  weak on Nasdaq.
* A Nasdaq move and a quote burst at the same time lift gold's in-sample PF from 1.13 to 2.5.

## Search
* Numba copies of common.py's entry / exit / account, checked on 13k+ exits and ~1.9k pending orders: 0 mismatches.
* 43 entries (market at 0-300 s; stop orders 0.5 / 1 / 2 x 1-min vol, live 60-900 s; pullback limits 0.5 / 1 / 2 x
  1-min vol, live 120-1800 s; follow or fade the 10-300 s move) x 1,008 filters (move z >= 3-10; channel; ❗; $MACRO;
  distance to USD high-impact events; quote burst; other instrument confirming) x 750 exits (stop 1.5-7 x 1-min vol,
  break-even / trailing, target 1.5-10 R or none, timer 10 min - 4 h) = 325 M per instrument per data set; 650 M real,
  2.9 G on fake data.  Score sum(log(1 + 0.1 R)), positive in both halves of the search period; exact account on the top
  4,000; second pass smoothed over neighbouring exits.

## Luck check (best search-period $ at 10 %)
| Search | Best search $ | Its check $ | Best check $ in top-20 | Top-100 profitable on check |
|---|---|---|---|---|
| REAL gold | 200,136 | 777 | 20,708 (= candidate 1) | 66 % |
| REAL nasdaq | 165,252 | 634 | 859 | 13 % |
| Posts moved +/-14 days, gold (3 seeds) | 414,255 / 35,123 / 118,640 | 696 / 1,072 / 1,396 | 817 / 1,542 / 3,804 | 3 / 56 / 71 % |
| Posts moved +/-14 days, nasdaq (3 seeds) | 67,025 / 52,297 / 126,371 | 231 / 588 / 18 | 952 / 588 / 2,576 | 1 / 0 / 22 % |
| Random direction, gold (2 seeds) | 210,564 / 167,034 | 3,674 / 921 | 6,131 / 4,247 | 9 / 23 % |
| Random direction, nasdaq | 244,090 | 807 | 1,515 | 12 % |

In-sample the real search is no better than luck; out of sample real gold beats the fakes.  Candidate 1 at fake post
times: 9-11 trades per period, PF 0.13-0.72 for two seeds, 2.5 for one.  Candidate 1 was picked from the in-sample
top list after seeing the check results, so its check numbers are optimistic.  Around it, 81-100 % of neighbouring
settings are positive in-sample and 76-100 % on the check; fading the same moves loses in both periods.

## Candidates (gold, `strategy.py`)
Common rules: active market (the 900 bars ending 60 s before the post span < 1,500 s, >= 20 min since the last
>= 10-min pause, not in the hour before the daily break); sigma = RMS 1-s mid change over those 900 bars, 1-min vol =
sigma x sqrt(60); trigger: |mid move from just before post-30 s to the last bar before post+2 s| >= 3 sigma x sqrt(33),
quotes per second from the post to post+1 s >= 2 x normal, Nasdaq's same z >= 2 in size; direction = the move's sign;
stop 4.5 x 1-min vol, no target, out after 4 h or at the close; 10 % risk, 30 % cap (one shock can add up to 3 trades).
1. `gold_shock_pullback`: limit order 0.5 x 1-min vol better than the last mid, live 10 min.
2. `gold_shock_pullback_trail`: the same, stop trailing 3 R behind the best price.
3. `gold_shock_market`: market order at post + 2 s.

| Candidate | Period | Trades | R | PF | Win | $1k -> | DD | Max lot | Stress PF (final $) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | search | 85 | +73.5 | 2.44 | 39 % | 57,756 | -56 % | 14.3 | 2.19 (24,446) |
| 1 | check | 58 | +69.5 | 2.88 | 36 % | 20,718 | -64 % | 3.9 | 2.56 (9,452) |
| 1 | Jan-Jun 2026 | 119 | +95.7 | 2.26 | 35 % | 58,607 | -64 % | 11.0 | 2.06 (22,640) |
| 2 | search | 85 | +51.9 | 2.04 | 37 % | 11,394 | -60 % | 2.6 | 1.88 (6,328) |
| 2 | check | 58 | +55.5 | 2.64 | 38 % | 17,971 | -54 % | 3.4 | 2.28 (8,079) |
| 2 | Jan-Jun 2026 | 119 | +72.3 | 1.99 | 35 % | 24,861 | -60 % | 4.6 | 1.79 (9,496) |
| 3 | search | 90 | +65.2 | 2.12 | 33 % | 20,893 | -79 % | 10.7 | 1.71 (3,920) |
| 3 | check | 65 | +62.7 | 2.43 | 32 % | 11,440 | -64 % | 2.2 | 2.41 (12,396) |
| 3 | Jan-Jun 2026 | 129 | +75.0 | 1.83 | 29 % | 9,764 | -80 % | 1.8 | 1.61 (2,746) |

Per-month R, candidate 1 (trades / R): 2025-04 1/-1.0, 05 6/+8.1, 06 1/+1.1, 07 5/+1.2, 08 4/+30.2, 09 2/+2.4,
10 2/+5.4, 11 3/-0.1; 2026-01 8/+2.4, 02 10/+7.8, 03 16/+13.2, 04 27/+2.8, 05 20/+22.0, 06 38/+47.6.  Longs +59.5 R
(73 trades), shorts +83.6 R (70).  The 5 largest trades give 63 of 143 R (incl. right after the Jun 5 NFP and Jun 17
FOMC); without them +80 R.

## Caveats
Thin data (FJ 2025 partial, no Nasdaq in Dec 2025, 14 months); trades per month grow with post volume (27-38 in
Apr-Jun 2026); 55-80 % drawdowns at 10 % risk and a final $ that depends on a few big winners.  Treat it as an
unproven, modest edge and expect much less on new months.

## Files
`strategy.py` (candidates + backtest, common.py only; matches the search trades except one 2025-07 trade dropped by the
past-only "hour before the daily break" rule); `lab.py` + `validate.py` (fast copies of common.py and their check);
`events.py`, `outcomes.py` (precomputed outcomes; seed > 0 = posts moved to random times); `search.py`, `search2.py`;
`family*.py`, `neigh.py`, `luck_table.py`, `final_eval.py`, `monthly.py`; `cache/` (not committed; `python outcomes.py
gold 0` rebuilds it).
