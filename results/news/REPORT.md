# High-impact news trading (tick-level)

## FINAL: all ~310 high-impact USD releases per market (Oct 2024 - Oct 2026)

| | Gold | Nasdaq | Dow | EURUSD |
|---|---|---|---|---|
| A) Straddle: settings PF>1 in 2025 / 2026 / both | 0% / 0% / 0% | 21% / 24% / **5%** | 17% / 0% / 0% | 18% / 2% / 1% |
| A) Best-by-2025 setting, $1,000 in 2026 at 10% | $80 | $16 | $19 | $289 |
| A) at 1:3 only: settings PF>1 in both years | 0% | 3% | 0% | 0% |
| B) Buy+sell 5 s before: settings PF>1 in 2025 / 2026 / both | 0% / 0% / 0% | 0% / 42% / **0%** | 0% / 0% / 0% | 0% / 8% / 0% |
| B) Best-by-2025 setting, $1,000 in 2026 (5% per leg) | $346 | $277 | $73 | $750 |

**Verdict: neither setup is profitable.** No setting on any market made money in both 2025 and 2026, apart from a
handful of Nasdaq straddle settings (5%) that are indistinguishable from luck. The settings that looked best on 2025 lost
70-98% of the account in 2026. The interim result (Nasdaq looked promising on 2026 alone) did not hold up on 2025.

---

# INTERIM (kept for reference): ~75 USD releases per market, mostly 2026

Calendar: Forex Factory (10,583 events Oct 2024 - Oct 2026, exact UTC timestamps) -> 316 high-impact USD data
releases (speeches and press conferences excluded). Prices: Dukascopy ticks with real bid/ask, including the spread
spike at the release. Distances are multiples of each market's "news unit" (median first-minute range of the
previous 10 releases): gold ~$10.7, Nasdaq ~34 pts, Dow ~47 pts, EURUSD ~6 pips.

## A) Straddle (OCO stops, 10% risk/trade), 216 settings per market
| Market | Settings PF > 1 | Median PF | Best setting PF | Best setting $1,000 -> |
|---|---|---|---|---|
| Nasdaq | 31% | 0.81 | 1.41 (dist 0.25u, SL 1u, 1:3, 10 s before) | $2,137 (DD -74%) |
| EURUSD | 6% | 0.74 | 1.11 | $383 |
| Dow | 1% | 0.58 | 1.00 | $326 |
| Gold | 0% | 0.50 | 0.94 | $342 |

## B) Buy + sell 5 s before (5% per leg), 12 settings per market
| Market | Settings PF > 1 | Median PF | Best |
|---|---|---|---|
| Nasdaq | 75% | 1.03 | PF 1.19 ($1,000 -> $1,142) |
| EURUSD | 17% | 0.72 | PF 1.19 ($1,139) |
| Gold | 0% | 0.57 | PF 0.88 |
| Dow | 0% | 0.52 | PF 0.81 |

## Why
Spread 5 s before -> max spread in the first 5 s after the release (medians): gold $1.05 -> $4.16, Nasdaq 1.2 -> 6.2 pts,
Dow 2.1 -> 14.9 pts. Straddle fill slippage: median about 3-6% of the unit, but the worst 10% of fills slip
$3.2 (gold), 9 pts (Nasdaq) and 83 pts (Dow).
