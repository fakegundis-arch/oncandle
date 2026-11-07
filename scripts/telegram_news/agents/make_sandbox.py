"""Copy of the data that ends on 2026-06-30 23:59:59 UTC for the search agents (Jul-Oct 2026 stays hidden).
usage: python3 -I scripts/telegram_news/agents/make_sandbox.py <repo data dir> <sandbox dir>"""
import glob
import json
import os
import shutil
import sys

import pandas as pd

src, dst = sys.argv[1], sys.argv[2]
CUT = pd.Timestamp("2026-07-01", tz="UTC")
os.makedirs(dst, exist_ok=False)
for f in glob.glob(os.path.join(src, "ticks_exness*", "*", "*.npz")):
    month = os.path.basename(f)[:7]
    if month < "2026-07":
        out = os.path.join(dst, os.path.relpath(f, src))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        shutil.copy2(f, out)
for f in glob.glob(os.path.join(src, "telegram", "history", "**", "*.jsonl"), recursive=True):
    b = os.path.basename(f)
    if not (b.startswith("financialjuice") or b.startswith("WalterBloomberg")):
        continue
    keep = [ln for ln in open(f, encoding="utf-8") if pd.Timestamp(json.loads(ln)["time"]) < CUT]
    out = os.path.join(dst, os.path.relpath(f, src))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").writelines(keep)
cal = pd.read_csv(os.path.join(src, "calendar", "ff_calendar.csv"), parse_dates=["time_utc"])
os.makedirs(os.path.join(dst, "calendar"))
cal[cal.time_utc < "2026-07-01"].to_csv(os.path.join(dst, "calendar", "ff_calendar.csv"), index=False)
