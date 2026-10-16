# New York open straddle (Nasdaq and Dow), $1,000 at 10% risk

**Rules:** at 09:29:50 New York time, place a buy stop `dist` above the ask and a sell stop `dist` below the bid.
They are OCO (one cancels the other) and unfilled orders expire after 1 or 5 minutes. Stop `sl`, target `rr x sl`,
and the trade is closed after 15/30/60 minutes. Exness spreads plus extra slippage of 0 / 2-4 / 5-10 points.

**Data:**
* M1 bars for every NYSE open, Oct 2024 - Oct 2026 (about 510 opens per market)
* Dukascopy TICKS for about 95 opens per market, mostly Jun-Oct 2026 (Dukascopy throttles tick downloads)

**Bug caught:** when both stops trigger inside one minute, choosing the side from the candle's colour leaks the
minute's direction and produced fake results of "$1,000 -> $1,000,000+" on the Dow. The M1 model now assumes the
worse side filled first, and tick data resolves those minutes exactly.

## Results
| | Nasdaq | Dow |
|---|---|---|
| Default (NAS 10/20 pts, Dow 20/40 pts, 1:2) - 2025 | $1,000 -> $1 (PF 0.75) | $1,000 -> $11 (PF 0.87) |
| Default - 2026 | $1,000 -> $19 (PF 0.84) | $1,000 -> $599 (PF 1.11, DD -88%) |
| Configs profitable in both years (M1) | **0%** | 20% (none robust) |
| Tick-level, ~95 opens: configs with PF > 1 | 7% (median PF 0.79) | 88% (median PF 1.14) |
| Best-by-2025 config, judged on 2026 | loses | **$1,000 -> $434** (DD -89%); on ticks PF 0.98 |
| Most stable Dow region (dist 20, sl 80, 15 min) - 2026 | - | $1,000 -> about $2,200-2,400, DD about -85% |

**Verdict:** no reliable edge. Nasdaq clearly loses: the opening spike usually whipsaws and stops out the triggered
side. The Dow is around break-even, highly sensitive to settings, and at 10% risk the drawdowns are 85-90%.
Fills came a median 4.9 s after the open (ticks).

## R:R sweep (`rr_sweep.csv`)
Targets of 1:0.5, 1:1, 1:1.5, 1:2, 1:3, 1:4, 1:5 and none (time exit only) were tested across every distance,
stop and hold time. **No R:R makes it work.** Nasdaq's best tick-level median PF is 1.04 (no target); in the M1
history no R:R was profitable in both years in more than 19% of settings. The Dow's best tick-level median PF is 1.11
(1:1.5); in M1 at most 28% of settings were profitable in both years (1:3). Wider targets lift PF slightly but cut
the win rate to about 20-30%.
