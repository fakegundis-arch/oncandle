# Bitcoin liquidation bot - version 3 (three research agents, Nov 9-10 2026)

Three independent agents built on Dec 2025 - Jun 2026 data only (a sealed copy; no internet, no earlier results),
with one shared, checked rulebook (`scripts/btc_liq/agents3/btc_common.py`: Binance signals, Exness BTCUSDm fills at
bid / ask + 1 spread, 2 s latency, stop before target, flat before pauses, 10 % risk, position <= 100 x balance, open
risk <= 30 %).  Brief and the version-3 selection rule: `agents3/BRIEF.txt` (written before any agent result).

**Timing correction found during this work:** a Binance 5-minute metrics row describes the 5 minutes AFTER its
create_time, so it can only be used from create_time + 360 s.  Versions 1 and 2 used it from + 60 s (look-ahead) -
their earlier results are void.  All version-3 work and the baselines below use the honest timing.

## The agents
* **oi** (positioning: open interest over 5-30 min, ETH open interest, long / short ratios, funding, premium): ~258 M
  settings.  The full search did not beat its fake-signal searches; its candidate OI_BIGMOVE only passed a post-hoc
  narrower check.  Verdict: not better than luck.
* **exec** (trading the open-interest signal: entries, exits, scaling): following the move after an honest
  open-interest drop has no edge (1.1 M variants, real +15.8R vs fakes up to +33.0R).  Found "flush fade": after
  open interest falls >= 1 % in 15 min with a >= 0.4 % move, a limit order 4 x vol further into the flush, stop
  0.75 x the move, target 4R, up to 4 h, up to 3 positions.  Beat its own fakes, thinly.
* **flow** (catching liquidations from 1-second flow): nothing in that angle worked honestly.  Found "big-print
  burst": BTC moves >= 8 x vol in 30 s with a large aggressive print and open interest RISING in that 5-minute bucket
  -> follow at the bucket's known time, stop 10 x vol, target 3R, up to 2 h, up to 2 positions.  575,808 settings;
  beat its fakes (+54.2R vs best fake +42.3R).

**Version 3** (pre-declared rule: highest Jan-Jun balance at 10 % among candidates meeting the build rules whose
agent's luck check passed): `flow_bigprint_oiup_30s`.  The lead reproduced every candidate's Jan-Jun numbers exactly
before any sealed run (`build_*.json`, `pick.json`).

## Results, $1,000 at 10 % risk (one run each on the sealed periods)
| Candidate | Jan-Jun 2026 (built on) | Jul-Oct 2026 (unseen) | Jan-Nov 2025 (unseen) |
|---|---|---|---|
| **Version 3: big-print burst** | 69 trades, +54.2R, PF 3.22, **$85,229**, DD -32 % | 65 trades, -4.1R, PF 0.90, **$419**, DD -77 % | 107 trades, -0.7R, PF 0.99, **$277**, DD -91 % |
| Flush fade 4 x vol | 67, +34.6R, PF 2.54, $14,394 | 27, -18.7R, PF 0.13, $121 | 115, -48.9R, PF 0.40, $3 |
| Flush fade 3 x vol + break-even | 73, +29.5R, PF 2.61, $9,830 | 24, -12.0R, PF 0.13, $269 | 113, -21.7R, PF 0.63, $43 |
| Big-print 60 s, wide stop (info) | 76, +24.4R, PF 2.45, $8,076 | 51, -5.3R, PF 0.74, $484 | 100, +2.0R, PF 1.05, $724 |
| OI_BIGMOVE (positioning) | 61, +20.1R, PF 2.20, $5,601 | 20, +0.2R, PF 1.02, $909 | 90, +0.3R, PF 1.01, $678 |
| Version 1, honest timing | 88, -3.7R, PF 0.84, $581 | 27, -6.3R, PF 0.43, $494 | 131, -28.1R, PF 0.52, $40 |
| Version 2, honest timing | 177, -1.2R, PF 0.96, $718 | 53, -6.4R, PF 0.44, $504 | 241, -19.3R, PF 0.69, $101 |

At 2 % risk on the unseen periods every candidate ends between $355 and $1,018 (`test_*.json`).  With worse fills
(stress) none has a profit factor above 0.86 on either unseen period.

## Verdict
No Bitcoin liquidation bot built here makes money on months it was not built on.  Every January-June edge - including
the agents' best, which passed their luck checks - disappeared on Jul-Oct 2026 and on 2025.  With honest data timing,
the moves around open-interest drops and liquidation bursts that a retail bot can still catch after the fact are
smaller than Exness's round-trip cost (about two $6-18 spreads).  Do not trade any of these versions.
