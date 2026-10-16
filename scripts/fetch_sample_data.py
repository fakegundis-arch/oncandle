#!/usr/bin/env python3
"""Build data/EURUSD_H1.csv (Jan 2017 - Feb 2018, real hourly bars) from the
sample files that ship inside two PyPI packages.  Useful when no market-data
host is reachable; far too short for conclusions - see README."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([sys.executable, "-m", "pip", "download", "-q", "--no-deps", "-d", tmp,
                        "gym-anytrading==2.0.0", "backtesting==0.6.6"], check=True)
        frames = []
        for whl in Path(tmp).glob("*.whl"):
            with zipfile.ZipFile(whl) as z:
                for name in z.namelist():
                    if name.endswith("FOREX_EURUSD_1H_ASK.csv"):
                        d = pd.read_csv(z.open(name))
                        d.index = pd.to_datetime(d.pop("Time"), format="%d.%m.%Y %H:%M:%S.%f")
                        frames.append(d)
                    elif name.endswith("test/EURUSD.csv"):
                        d = pd.read_csv(z.open(name), index_col=0, parse_dates=True)
                        frames.append(d)
    df = pd.concat(frames)
    df.columns = [c.lower() for c in df.columns]
    df = df[~df.index.duplicated(keep="first")].sort_index()[["open", "high", "low", "close"]]
    df.index.name = "time"
    out = ROOT / "data" / "EURUSD_H1.csv"
    out.parent.mkdir(exist_ok=True)
    df.to_csv(out)
    print(f"EURUSD: {len(df):,} bars {df.index[0]} -> {df.index[-1]} -> {out}")


if __name__ == "__main__":
    main()
