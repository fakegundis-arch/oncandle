"""Data copy for the version-3 agents: 2025-12-01 .. 2026-06-30 only (Jul-Oct 2026 and 2025 stay sealed).
usage: python3 -I scripts/btc_liq/agents3/make_sandbox.py <sandbox dir>"""
import os
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
B, X = ROOT / "data" / "btc", ROOT / "data" / "ticks_exness" / "BTCUSDm"
dst = Path(sys.argv[1])
dst.mkdir(parents=False, exist_ok=False)
MS = [f"2025-12"] + [f"2026-{m:02d}" for m in range(1, 7)]
for sub, src, ext in (("binance_1s", B / "binance_1s", "npz"), ("bookdepth", B / "bookdepth", "parquet"), ("exness", X, "npz")):
    (dst / sub).mkdir()
    for m in MS:
        shutil.copy2(src / f"{m}.{ext}", dst / sub / f"{m}.{ext}")
lo, hi = pd.Timestamp("2025-12-01"), pd.Timestamp("2026-07-01")
for f in ("metrics.csv.gz", "eth_metrics.csv.gz"):
    m = pd.read_csv(B / f, parse_dates=["create_time"])
    m[(m.create_time >= lo) & (m.create_time < hi)].to_csv(dst / f, index=False)
fr = pd.read_csv(B / "funding.csv.gz")
fr[(fr.calc_time >= (lo - pd.Timedelta(days=3)).value // 10**6) & (fr.calc_time < hi.value // 10**6)].to_csv(dst / "funding.csv.gz", index=False)
pr = pd.read_parquet(B / "premium_1m.parquet")
pr[(pr.open_time >= lo.value // 10**6) & (pr.open_time < hi.value // 10**6 - 60_000)].to_parquet(dst / "premium_1m.parquet")
print("sandbox ready:", sorted(os.listdir(dst)))
