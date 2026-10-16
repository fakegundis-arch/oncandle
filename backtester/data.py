"""Loading, cleaning and resampling OHLC data.

Supported inputs
----------------
* MT5 "Export bars" CSV (View -> Symbols -> Bars -> Export), tab separated:
      <DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICKVOL> <VOL> <SPREAD>
* Generic CSV with a datetime column/index and Open/High/Low/Close columns
  (any capitalisation), e.g. files written by scripts/fetch_dukascopy.py.

All bars are treated as BID prices; the engine adds the spread on top.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

OHLC = ["open", "high", "low", "close"]


def load_csv(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    with open(path) as fh:
        first = fh.readline()

    if first.startswith("<DATE>"):  # MT5 export
        df = pd.read_csv(path, sep="\t")
        df.columns = [c.strip("<>").lower() for c in df.columns]
        if "time" in df.columns:
            ts = pd.to_datetime(df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M:%S")
        else:
            ts = pd.to_datetime(df["date"], format="%Y.%m.%d")
        df.index = ts
    else:
        df = pd.read_csv(path)
        df.columns = [str(c).strip().lower() for c in df.columns]
        tcol = next((c for c in df.columns if c in ("time", "date", "datetime", "timestamp", "gmt time")),
                    df.columns[0])
        df.index = pd.to_datetime(df[tcol], dayfirst=("." in str(df[tcol].iloc[0])[:3]))
    df.index.name = "time"
    df = df[OHLC].astype(float)
    return clean(df)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df[~df.index.duplicated(keep="first")].sort_index()
    df = df.dropna()
    # Dukascopy and some brokers emit flat "bars" for closed-market hours.
    flat = (df["high"] == df["low"]) & (df["open"] == df["close"])
    df = df[~flat]
    # Repair the occasional inconsistent bar.
    df["high"] = df[OHLC].max(axis=1)
    df["low"] = df[OHLC].min(axis=1)
    return df


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample H1 bars to H4 / D1.  Daily bars use a 22:00 UTC rollover
    (New York close), which is what most MT5 brokers on GMT+2/+3 servers show."""
    if rule in ("1h", "H1"):
        return df
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if rule in ("1D", "D1"):
        out = df.resample("1D", offset="22h").agg(agg)
    else:
        rule = {"H4": "4h"}.get(rule, rule)
        out = df.resample(rule, offset="2h").agg(agg)  # align H4 with a GMT+2 server
    out = out.dropna()
    # Drop tiny weekend stubs (e.g. Sunday open fragments).
    return out


def pip_size(symbol: str) -> float:
    s = symbol.upper()
    if s.startswith("XAU"):
        return 0.1
    if s.startswith("XAG"):
        return 0.01
    return 0.01 if "JPY" in s else 0.0001


# Typical all-in costs on a raw-spread ECN account, in pips, including
# ~$7/lot round-trip commission (= 0.7 pip on USD-quoted majors).
# These are deliberately a little pessimistic.
DEFAULT_COST_PIPS = {
    "EURUSD": 1.0, "GBPUSD": 1.3, "USDJPY": 1.1, "USDCHF": 1.4, "AUDUSD": 1.2,
    "USDCAD": 1.5, "NZDUSD": 1.6, "EURJPY": 1.6, "GBPJPY": 2.4, "EURGBP": 1.4,
    "AUDJPY": 1.8, "EURCHF": 1.8, "XAUUSD": 3.5,
}


def cost_pips(symbol: str) -> float:
    return DEFAULT_COST_PIPS.get(symbol.upper(), 2.0)
