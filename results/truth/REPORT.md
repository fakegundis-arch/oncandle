# Trading Trump's Truth Social posts

Data: 37,122 @realDonaldTrump posts with exact timestamps (Feb 2022 - Oct 2026; stilesdata archive + trumpstruth.org,
`scripts/fetch_truth_posts.py`). A post is "high impact" if its text hits a topic list (tariffs, war/Iran/strikes, Fed,
China, oil, crypto; endorsements excluded), first post of a topic within 60 min only. Since Oct 2024: 1,166 events
(2025: 604, 2026: 567). Tone: +1 if "deal / agreement / ceasefire / pause / exempt / negotiate..." words outnumber
"tariff / bomb / strike / attack / sanction..." words, -1 if fewer. The bot acts 1, 2 or 5 min after the post's minute.
Code: `backtester/truth.py`, `scripts/run_truth.py` (508,032 settings), costs 3x spread, 2025 = discovery, 2026 = check.

## Overall
| Family | Profitable in both years |
|---|---|
| Straddle at the post (OCO stops) | 1% |
| Follow the first move | 4% |
| Fade the first move | 2% |
| Trade the post's tone | 7% |
No setting reaches $100,000 in 2026 even with hindsight (best $51,959).

## The one real finding: tariff posts -> Dow (US30)
Rules (picked on 2025): tariff post -> 2 min reaction + 5 min wait -> enter the tone direction (plain tariff threat =
SELL the Dow; deal/pause/exempt words = BUY) at the next M1 open; stop 12 x pre-post M1 range; target 3R; stop to +0.1R
at +1R; close after 60 min. `scripts/truth_tariff_trades.py` -> `tariff_us30_trades.csv`.

| Year | Trades | Win | PF | $1,000 at 10% | Max DD | at 20% | at 30% |
|---|---|---|---|---|---|---|---|
| 2025 (picked here) | 143 | 56% | 1.66 | $4,203 | -56% | $8,964 (-83%) | $10,294 (-95%) |
| **2026 (unseen)** | 61 | 54% | **2.58** | **$2,648** | **-15%** | $5,456 (-30%) | $9,195 (-45%) |

Controls (same trade rules, SELL the Dow): after random posts PF 0.84 / 0.92; after war/Fed/China posts 0.67 / 0.88;
after tariff posts 1.34 / 1.87; with the tone 1.65 / 2.58. So the edge is tied to tariff posts, not to a falling Dow.
Caveats: only 34% of the tariff-tone Dow variants are profitable in both years; the same rule is flat-to-negative on
Nasdaq and S&P 500 (median PF 0.8), which is odd for an effect that should hit all US indices; 61 trades in 2026.
Live, the bot needs a real-time Truth Social feed; posts are visible within seconds, so a 2-min delay is realistic.
