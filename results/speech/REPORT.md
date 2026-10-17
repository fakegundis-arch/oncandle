# Trump / Fed-chair speech straddle

Code: `backtester/speech.py`, `scripts/run_speech.py` -> `grid.csv`, `events.csv`.
Events (Forex Factory, scheduled, Oct 2024 - Oct 2026): 114 "President Trump Speaks" (28 high, 86 medium) and 45
Fed-chair events (Powell / Warsh speeches and testimony, FOMC press conferences). 2025: 65 Trump + 25 Fed; 2026: 49 + 16.
Unscheduled posts (Truth Social) have no reliable timestamped history here and cannot be backtested.

Rules: at the event minute, OCO buy stop / sell stop at +/- k x (pre-event M1 range); orders live 5-120 min; stop
0.5-2 x the distance, target 1-5R, optional break-even, hold 1-4 h; 3x Exness spread. If one M1 bar touches both orders the
worse fill is kept. 2,400 settings x 11 markets x 4 event sets (Trump, Trump high only, Fed, both) + all markets together.

| | Result |
|---|---|
| Settings profitable in both 2025 and 2026 | **1.4%** (gold best: 11%) |
| Median profit factor | 0.06-0.10 pessimistic; 0.5-0.9 with the most optimistic fill assumption |
| Best 2026 result with hindsight (10% risk) | $6,942 (gold), median gold setting $146 |
| Trump only | 0% of settings profitable in both years |
| Fed only | 4% |

Even when the fill bar is never allowed to stop the trade (optimistic), no market reaches a median PF of 1.
**Rejected.** Most scheduled speeches do not move markets at the start; the straddle gets whipsawed both ways, and the
remarks that do move markets come at unknown times, by which time fast news algorithms have already priced them.
