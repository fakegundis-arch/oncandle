"""Parse macro-data posts: actual vs forecast -> surprise sign and indicator polarity."""
from __future__ import annotations
import re
import numpy as np, pandas as pd

RX_FJ = re.compile(r"(?i)^[^A-Za-z]*(?:breaking:\s*)?(?P<name>.+?)\s+actual\s+(?P<act>[-+]?\d[\d,]*\.?\d*)\s*(?P<u>[%kmbt]?)\s*\(forecast\s+(?P<fc>[-+]?\d[\d,]*\.?\d*|-)")
RX_WB = re.compile(r"(?i)^[\*\s]*(?P<name>.+?)\s+(?P<act>[-+]?\d[\d,]*\.?\d*)\s*(?P<u>[%kmbt]?)\s*[;,(]\s*(?:consensus|est\.?|exp\.?|expected|forecast)\s+(?P<fc>[-+]?\d[\d,]*\.?\d*)")

INFL = r"cpi|ppi|pce|inflation|price|earnings|wage|employment cost|deflator"
NEGP = r"unemployment|jobless|claims"
US = r"^(?:us|u\.s\.|united states)\b|\bu\.s\.|\bus\b|nonfarm|jolts|ism|adp|michigan|conference board|philly|empire|chicago pmi"


def _num(s):
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return np.nan


def parse_line(line: str):
    line = line.strip()
    for rx in (RX_FJ, RX_WB):
        m = rx.search(line)
        if m:
            name = m.group("name").strip().lower()
            a, f = _num(m.group("act")), _num(m.group("fc")) if m.group("fc") != "-" else np.nan
            return name, a, f
    return None


def parse(clean: pd.Series) -> pd.DataFrame:
    rows = []
    for t in clean:
        best = None
        for line in t.split("\n")[:6]:
            r = parse_line(line)
            if r is None or not np.isfinite(r[2]):
                continue
            name, a, f = r
            if not re.search(US, name):
                continue
            imp = 3 if re.search(r"nonfarm|payroll|cpi|pce|ism|retail sales|gdp|jobless claims", name) else 1
            if best is None or imp > best[3]:
                best = (name, a, f, imp)
        if best is None:
            rows.append((None, np.nan, np.nan, 0, 0, 0))
            continue
        name, a, f, imp = best
        s = np.sign(a - f)
        pol = -1 if re.search(NEGP, name) else 1
        infl = 1 if re.search(INFL, name) else 0
        rows.append((name, a, f, imp, int(s), pol * int(s)))
    return pd.DataFrame(rows, columns=["mname", "act", "fc", "mimp", "msurp", "mstrong"])  # mstrong>0: hot/strong US data
