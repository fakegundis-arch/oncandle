#!/usr/bin/env bash
# Bring the gold-bot backtest up to date and rerun it.
#   scripts/goldbot_backtest/refresh.sh <bot repo dir> [newsbot.log]
# 1. this month's Exness ticks for XAUUSDm and USTECm (the archive adds a day at ~01:40 UTC for gold, ~22:00 for Nasdaq)
# 2. the three channels' posts of the last 3 days
# 3. with a log: the AI-verdict files and the as-live check (results/goldbot_backtest/as_live/scoreboard.txt)
# 4. the backtest to the end of the price data (summary_to_<date>.json)
set -euo pipefail
cd "$(dirname "$0")/../.."
BOT="${1:?bot repo dir}"; LOG="${2:-}"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
MONTH="$(date -u +%Y-%m)"; END="$(date -u -d tomorrow +%F)"
PYTHONDONTWRITEBYTECODE=1 python3 -I - "$WORK" "$MONTH" <<'PY'
import sys
sys.path.insert(0, "scripts/telegram_news")
from pathlib import Path
import numpy as np, pandas as pd
import exness_ticks as ex
work, (y, m) = Path(sys.argv[1]), map(int, sys.argv[2].split("-"))
for s in ("XAUUSDm", "USTECm"):
    z = work / f"{s}.zip"
    ex.fetch(ex.URL.format(s=s, y=y, m=m), z)
    a = ex.convert(z)
    out = Path("data/ticks_exness") / s / f"{y}-{m:02d}.npz"
    old = int(np.load(out)["t"][-1]) if out.exists() else 0
    if int(a["t"][-1]) >= old:                       # never replace a file with a shorter one
        np.savez_compressed(out, **a)
    print(s, "ticks to", pd.to_datetime(int(a["t"][-1]), unit="s"), flush=True)
PY
python3 -I scripts/telegram_news/tg_history.py "$(date -u -d '3 days ago' +%F)" "$WORK/tg" financialjuice WalterBloomberg apewirenews
for c in financialjuice WalterBloomberg apewirenews; do
  cp "$WORK/tg/$c.jsonl" "data/telegram/history/${c}__zz$(date -u +%Y%m%d%H%M).jsonl"
done
export GOLDBOT_END="$END" PYTHONDONTWRITEBYTECODE=1
if [ -n "$LOG" ]; then
  python3 -I scripts/goldbot_backtest/ai_standin.py "$BOT" "$LOG"
  python3 -I scripts/goldbot_backtest/as_live.py "$BOT" "$LOG"
fi
python3 -I scripts/goldbot_backtest/replay.py "$BOT" main live_ai_real live
