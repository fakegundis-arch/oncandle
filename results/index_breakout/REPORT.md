# Gold Asian breakout v3 method on Nasdaq, Dow and S&P 500

`scripts/index_breakout.py` -> `grid.parquet` (55,296 rows). Same engine as gold (M15 signals, M1-exact trades,
Exness spreads: NAS 1.2, Dow 2.0, S&P 0.5 points). Per market: 8 sessions (Asian 00-06, late Asian 02-07,
London open 07-10, London 07-12, NY open 13-16, NY 13-20, NY afternoon 16-20, all day) x Donchian 10/20/40 x EMA
100/400 x slope 4/16 x prev-day break on/off x stop 1-3 ATR x 2-4R x daily trend on/off x vol cap on/off, each with and
without the v3 overlays (equity-curve filter + weekly stop). Chosen on Q4 2024 + 2025; 2026 is the check.

| Market | Settings profitable in all 3 periods | Best session family | Its median PF 2025 / 2026 | Its median $1,000 in 2026 (10%) |
|---|---|---|---|---|
| **Gold (for comparison, v3 family)** | **91%** | Asian | 1.58 / 1.68 | $22,180 |
| Nasdaq | 17.6% | late Asian 02-07 | 1.20 / 1.21 | $1,149 |
| Dow | 4.4% | late Asian (2026 only) | 0.75 / 1.26 | $1,470 |
| S&P 500 | 4.2% | NY open + v3 | 0.92 / 0.99 | $501 |

Picking the best settings on Q4 2024 + 2025 (PF > 1.2 in both, highest 2025 growth), the top 50 per market did this
in 2026: Nasdaq 72% profitable, median $786; Dow 40%, median $267; S&P 64%, median $1,172. The top single Nasdaq pick
($69,848 in 2025) made $536 in 2026 with a -91% drawdown; the top Dow pick went from $17,488 to $88.
Patterns flip between years (Dow NY sessions win in 2025 and lose in 2026; Asian sessions the reverse).
Hindsight best 2026 results ($31k Nasdaq, $22k Dow, $22k S&P) come from settings that could not have been picked.

**Conclusion:** the breakout + trend method only works robustly on gold. On the US indices no session/setting family
holds up across Q4 2024, 2025 and 2026; no index version is recommended. (For Nasdaq the earlier Trend Rider v2 Asian
setup in `results/sessions/REPORT.md` remains the better option.)
