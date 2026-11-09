"""Extra Binance USD-M public data for the version-3 search (data.binance.vision):
  eth_metrics.csv.gz  ETHUSDT 5-minute open interest / long-short ratios (daily files)
  funding.csv.gz      BTCUSDT funding rates (calc_time ms, funding_interval_hours, last_funding_rate)
  premium_1m.parquet  BTCUSDT 1-minute premium index klines (open_time ms, open, high, low, close)
usage: python3 -I scripts/btc_liq/extra_data.py <YYYY-MM-DD> <YYYY-MM-DD>"""
import io
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from binance_data import get, read_csv  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "data" / "btc"
U = "https://data.binance.vision/data/futures/um/"


def main(a, b):
    d0, d1 = date.fromisoformat(a), date.fromisoformat(b)
    days = [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]
    months = sorted({d.strftime("%Y-%m") for d in days})
    with ThreadPoolExecutor(8) as ex:
        blobs = list(ex.map(lambda d: get(U + f"daily/metrics/ETHUSDT/ETHUSDT-metrics-{d}.zip"), days))
    eth = pd.concat([read_csv(x) for x in blobs if x is not None]).drop_duplicates("create_time").sort_values("create_time")
    eth.to_csv(OUT / "eth_metrics.csv.gz", index=False)
    print("eth metrics", len(eth), eth.create_time.min(), eth.create_time.max(), "missing days", sum(x is None for x in blobs))
    with ThreadPoolExecutor(8) as ex:
        fb = list(ex.map(lambda m: get(U + f"monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-{m}.zip"), months))
        pb = list(ex.map(lambda m: get(U + f"monthly/premiumIndexKlines/BTCUSDT/1m/BTCUSDT-1m-{m}.zip"), months))
    fr = pd.concat([read_csv(x) for x in fb if x is not None]).drop_duplicates("calc_time").sort_values("calc_time")
    fr.to_csv(OUT / "funding.csv.gz", index=False)
    pr = pd.concat([read_csv(x) for x in pb if x is not None])[["open_time", "open", "high", "low", "close"]]
    pr = pr.drop_duplicates("open_time").sort_values("open_time")
    pr.to_parquet(OUT / "premium_1m.parquet")
    print("funding", len(fr), "premium", len(pr), "missing months", sum(x is None for x in fb), sum(x is None for x in pb))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
