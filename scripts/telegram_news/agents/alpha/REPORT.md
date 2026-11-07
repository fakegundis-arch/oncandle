# alpha: headline content (search on data to 2026-06-30)

Saved by the lead from alpha's final message (the subagent could not write .md files).  Search period 2025-01 ..
2026-04, check period 2026-05 .. 2026-06.  $1,000 at 10 % risk, common.py fills / exits / account.

## Verdict
$1,000 -> $200,000+ at 10 % risk cannot be reached honestly with these headlines.  About 16.8 M rule combinations; the
best on the search period turns $1,000 into $819k, but the same search on fake signals (posts moved to wrong times, or
random directions) finds $537k-$637k.  Every way of picking rules on past data lost in the following months
(walk-forward).  None of the three frozen candidates passes the luck check or the May-Jun check.

## Data facts
* The channels are late: FJ macro posts arrive a median 45-100 s after the release (41-76 s in 2026), WB data posts
  ~30-40 s.  For ❗ / ‼ and macro posts the volatility jump comes BEFORE the post (-60 to -10 s); after the post
  volatility is only 1.2-1.4 x normal (~1.0 x for ordinary headlines).
* Costs vs movement ("vol" = mean |1-min mid change| over the prior 60 min): gold spread ~0.2 vol (round trip 0.4
  vol), Nasdaq ~0.35 vol (0.7 vol) - on Nasdaq the cost alone is bigger than any effect found.
* FJ formats change: 2025 merges several headlines per post; Jan-May 2026 macro posts are mixed case without
  "$MACRO"; June 2026 upper case with "$MACRO"; ❗ already appears in 2025.  WB marks urgent news with 🚨 and
  terminal headlines with "*".

## Features (all known at decision time)
Text (channel, ❗, ‼ / BREAKING / 🚨 / ⚠, 🚨, "*", macro, capitals share, length, lines, numbers, %, colon, negation),
29 keyword groups (Trump, Iran / Hormuz, Israel, Russia / Ukraine, China, Fed, ECB, BoJ, tariffs, oil, sanctions,
peace / deal, talks, war / strike, shipping, nuclear, gold, inflation, jobs, rates, stocks, Bessent, Venezuela,
Greenland, yen, source / outlet, escalation, de-escalation), story (posts in the previous 60 / 300 s, first post vs
follow-up by token Jaccard >= 0.25 in 30 min, other channel carried it in 5 min), hour, weekday, time to / from
high-impact USD events, US macro surprise parsed from 641 posts, price moves from -3600 / -1800 / -60 / -10 / 0 s to
the decision in vol units, learned per-word / word-pair direction (cross-fitted by month on the search period).

## Engine
numba copies of common.py: market entry + stop / target / timer 0 mismatches in 20,320 trades (normal and stress);
OCO 0 mismatches in 4,212 (one stress tie broken to the other leg with identical r); break-even / trailing 0 in 1,808.
Final numbers from strategy.backtest (common.py only), identical to the vectorised search.

## Search (~16.8 M on real data)
One position per instrument at a time.  Main grid 16,300,160: 901 filters (single atoms + pairs with >= 40 posts) x
54 direction rules (buy, sell, momentum / fade of the -60 / -10 / 0 / -1800 s move at 3-4 thresholds, macro surprise
with / without reaction agreement, learned text score at 3 horizons x 3 quantiles with / without agreement) x delay
0 / 10 / 30 s x gold / Nasdaq x stop 0.75 / 1.5 / 3 / 6 vol x target 0.5 / 1 / 2 / 4 R / none x timer 30 / 120 / 600 /
3600 s.  Also OCO straddles at +/-0.5 / 1 / 2 vol, expiry 60 / 300 s (387,936), "market had not moved yet" (115,040),
exit refinement incl. break-even / trailing (3,600), walk-forward gradient boosting (24).

## Validation
* Text direction: the cross-fitted word score correlates -0.03 to +0.02 with the next 1 / 5 / 30 min; word averages
  keep their sign between 2025 and Jan-Apr 2026 only 47-53 % of the time; gradient boosting 50.0-51.0 % walk-forward,
  all 24 configurations lose.
* Immediate reaction: gold mean-reverts slightly (t ~ -2 to -3), less than the cost; Nasdaq loses both ways.
* Macro surprise: drift in the surprise direction for 30-120 s after the post (gold t -2.8 at 30 s, Nasdaq t -3.4 at
  60 s), 0.2-0.4 vol, below the cost; trading versions lose.
* Walk-forward (train before Jan -> Jan-Feb, before Mar -> Mar-Apr, before May -> May-Jun), chained over Jan-Jun
  2026: x0.05 top-1, x0.03 top-10 average, x0.06 top-100 average; other choosers (t-stat, n >= 200, stress R / PF)
  also lose.
* Persistence: of rules with stress R > 0 in each of 2025, Jan-Feb and Mar-Apr (n >= 10 each), 26 % are positive in
  May-Jun (fake data 20 %, unconditioned rules 18 %).

## Luck check (best search-period $ at 10 %; robust filter = n >= 40, stress PF > 1.1, >= 60 % months positive)
| run | main grid robust | main grid loose | OCO | "not moved yet" | walk-forward top-1 / top-10 |
|---|---|---|---|---|---|
| real | $819,254 | $819,254 | $18,808 | $47,409 | x0.05 / x0.03 |
| posts shifted +34.1 d | $65,141 | $65,141 | $17,069 | $5,839 | x0.65 / x0.31 |
| posts shifted +19.7 d | $302,420 | $637,483 | $54,984 | $18,196 | x0.02 / x0.03 |
| posts shifted +9.9 d | $97,843 | $104,902 | $91,863 | $24,051 | x0.03 / x0.08 |
| real posts, random directions | $536,635 | $536,635 | - | - | x0.61 / x0.05 |

The real best is < 1.3 x the best fake (1.5 x random directions).  Only "not moved yet" clearly beat its fakes ($47k
vs <= $24k), and it lost in May-Jun.

## Candidates (gold only, one trade at a time; vol = mean |1-min mid change| over the prior 60 min, 240 if missing)
1. `iran_siren_short` (search winner): post contains 🚨 and an Iran keyword (iran, tehran, hormuz, araghchi / araqchi,
   qalibaf, irgc, khamenei, pezeshkian) -> sell gold at market at post + 32 s; stop 3 vol, no target, out after 1 h.
2. `eu_burst_fade` (13 of 13 search months positive): any post 07:00-12:59 UTC with >= 2 other posts in the previous
   60 s; if gold moved >= 0.5 vol from post - 10 s to the last second before post + 2 s, trade against it at post + 2 s;
   stop 6 vol, no target, out after 1 h.
3. `urgent_first_follow` (best "not moved yet"): post with 🚨 / ‼ / BREAKING / ⚠ / ❗ and gold moved < 1 vol in the
   60 s before; if gold moves >= 1 vol from post + 2 s to post + 30 s, follow it at post + 32 s; stop 6 vol, target
   4 R, out after 1 h.

| candidate | period | trades | R | PF | win | final $ | max DD | biggest lot | stress PF (final $) |
|---|---|---|---|---|---|---|---|---|---|
| iran_siren_short | search | 153 | +115.7 | 2.19 | 36 % | 819,254 | -55 % | 177.8 | 1.63 ($14,843) |
| | check May-Jun | 34 | -2.4 | 0.91 | 24 % | 462 | -69 % | 0.9 | 0.73 ($267) |
| | Jan-Jun 2026 | 164 | +84.8 | 1.77 | 32 % | 57,097 | -69 % | 109.0 | 1.32 ($1,086) |
| eu_burst_fade | search | 197 | +85.5 | 1.82 | 45 % | 158,780 | -63 % | 62.3 | 1.55 ($18,424) |
| | check | 104 | +9.0 | 1.14 | 36 % | 701 | -81 % | 0.2 | 0.99 ($269) |
| | Jan-Jun 2026 | 217 | +32.0 | 1.25 | 39 % | 1,762 | -90 % | 1.0 | 1.05 ($148) |
| urgent_first_follow | search | 291 | +72.8 | 1.48 | 43 % | 47,409 | -73 % | 19.5 | 1.24 ($2,136) |
| | check | 51 | -9.2 | 0.72 | 29 % | 267 | -82 % | 0.3 | 0.56 ($134) |
| | Jan-Jun 2026 | 164 | +28.3 | 1.32 | 40 % | 2,802 | -94 % | 4.3 | 1.07 ($360) |

Jan-Jun 2026 includes Jan-Apr, inside the search period.  iran_siren_short made almost all of its profit in
Mar-Apr 2026 (79 + 37 trades, +54.7 / +25.0 R) when gold fell during the Iran war - a trend bet, not a headline edge.
eu_burst_fade is a sharp peak (only stop 6 vol + 1 h works).  Exit refinement (1,200 settings per candidate, ranked on
the search period) did not help: positive on the search period 82 / 44 / 61 %, in May-Jun 18 / 31 / 3 %.

## Bottom line
Nothing reaches $200k.  The headlines reach these channels after the market has moved; what is left after the post is
smaller than gold and Nasdaq trading costs.  A real news bot would need a faster source (original wires within about
1 s) and testing on months it has never seen.

## Files
`strategy.py` (+ `feats.py`, `lib.py`; fills / exits / account from common.py), `final_eval.py`, searches
`search_wf.py`, `search_oco.py`, `first_news.py`, `ml_wf.py`, `stage2_run.py`, luck checks `make_fake.py`,
`run_fake.sh`, analysis `wf_analyze.py`, `wf_crit.py`, `persist.py`, `neigh.py`, engine + tests `engine.py`,
`engine2.py`, `stage2.py`, `test_engine*.py`, `test_stage2.py`.  `work/` (large regenerable arrays) not committed.
