"""Text / story / time / calendar features per post (only information known at the post time)."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from lib import tokens, first_line

STOP = set("""the a an of to in on for and or is are be by with at from as that this it its will has have was were
not no but if than then so we they he she you i our their his her them us u.s s says said say over after before
into about up down more less new last next week year month day today all any can could would should may might
amid also been being do does did out off per via vs mln bln""".split())

KW = {
    "trump": r"\btrump", "iran": r"iran|tehran|hormuz|araghchi|araqchi|qalibaf|irgc|khamenei|pezeshkian",
    "israel": r"israel|idf|netanyahu|gaza|hamas|hezbollah|lebanon", "russia": r"russia|putin|kremlin|moscow|ukrain|zelensk",
    "china": r"china|chinese|beijing|xi jinping|\bxi\b", "fed": r"\bfed\b|fed's|fomc|powell|warsh|federal reserve",
    "ecb": r"\becb\b|lagarde", "boj": r"\bboj\b|ueda|bank of japan", "tariff": r"tariff|levies|levy|duties",
    "oil": r"\boil\b|crude|opec|brent|\bwti\b|barrel", "sanction": r"sanction", "peace": r"ceasefire|cease-fire|peace|truce|deal|agreement|mou\b",
    "talks": r"talks|negotiat|meeting|summit", "war": r"strike|strikes|attack|missile|explosion|drone|bomb|war\b|military|troops|killed|shot down",
    "ship": r"hormuz|strait|shipping|tanker|vessel|blockade", "nuclear": r"nuclear|uranium|enrich", "gold": r"\bgold\b|bullion|xau",
    "inflation": r"inflation|\bcpi\b|\bpce\b|\bppi\b|prices", "jobs": r"payroll|jobless|employment|unemployment|jobs\b|labor",
    "rates": r"rate cut|rate hike|cuts|hikes|basis points|bps|rates\b", "stocks": r"\$[a-z]{1,5}\b|earnings|eps|revenue|shares",
    "bessent": r"bessent|treasury", "venez": r"venezuela|maduro", "greenland": r"greenland|denmark", "yen": r"\byen\b|intervention",
    "official": r"official|source|sources|reportedly|axios|wsj|reuters|bloomberg|cnbc|fox|nbc|cbs|ft\b",
    "neg": r"\bnot\b|\bno\b|won't|don't|never|den(y|ies)|reject|refuse|without",
    "escal": r"escalat|retaliat|threat|warn|attack|strike|invad|seize|blockade|shut|closed|close the",
    "deesc": r"ceasefire|de-escalat|pause|halt|calm|resume|reopen|withdraw|peace|agree",
}


def build(p: pd.DataFrame, cal: pd.DataFrame | None = None) -> pd.DataFrame:
    """p: posts with ts, ch, clean.  -> DataFrame of features (same index order)."""
    f = pd.DataFrame(index=p.index)
    txt = p.clean.fillna("")
    head = txt.map(first_line)
    low = txt.str.lower()
    f["ts"] = p.ts.to_numpy()
    f["wb"] = (p.ch == "WB").to_numpy()
    f["excl"] = head.str.contains("❗").to_numpy()
    f["excl_any"] = txt.str.contains("❗").to_numpy()
    f["brk"] = txt.str.contains("‼|BREAKING|🚨|⚠", regex=True).to_numpy()
    f["siren"] = txt.str.contains("🚨").to_numpy()
    f["star"] = head.str.match(r"^\s*[\-\*]").to_numpy()
    f["macro"] = (txt.str.contains(r"\$MACRO") | txt.str.contains(r"(?i)\bactual\b.*\(forecast", regex=True)).to_numpy()
    letters = head.map(lambda s: sum(ch.isalpha() for ch in s))
    upper = head.map(lambda s: sum(ch.isupper() for ch in s))
    f["caps"] = (upper / letters.clip(lower=1)).to_numpy()
    f["len"] = head.str.len().to_numpy()
    f["nlines"] = txt.str.count("\n").to_numpy()
    f["num"] = head.str.contains(r"\d").to_numpy()
    f["pct"] = head.str.contains("%").to_numpy()
    f["colon"] = head.str.contains(":").to_numpy()
    for k, rx in KW.items():
        f["kw_" + k] = low.str.contains(rx, regex=True).to_numpy()
    tt = pd.to_datetime(p.ts, unit="s", utc=True)
    f["hour"] = tt.dt.hour.to_numpy()
    f["dow"] = tt.dt.dayofweek.to_numpy()
    # ---- story features (earlier posts only)
    ts = p.ts.to_numpy()
    ch = p.ch.to_numpy()
    tok = [frozenset(w for w in tokens(h) if w not in STOP and len(w) > 2) for h in head]
    n = len(p)
    nprev60 = np.zeros(n, int); nprev300 = np.zeros(n, int)
    sim_prev = np.zeros(n, int)      # similar posts in previous 30 min (any channel)
    sim_other = np.zeros(n, bool)    # similar post in the OTHER channel in previous 5 min
    sim_same30 = np.zeros(n, bool)   # similar post (any channel) in the previous 30 min
    maxsim = np.zeros(n)
    lo60 = np.searchsorted(ts, ts - 60); lo300 = np.searchsorted(ts, ts - 300); lo1800 = np.searchsorted(ts, ts - 1800)
    for i in range(n):
        nprev60[i] = i - lo60[i]
        nprev300[i] = i - lo300[i]
        a = tok[i]
        if not a:
            continue
        cnt = 0; ms = 0.0; oth = False
        for k in range(lo1800[i], i):
            b = tok[k]
            if not b:
                continue
            inter = len(a & b)
            if inter == 0:
                continue
            s = inter / len(a | b)
            if s >= 0.25:
                cnt += 1
                if ch[k] != ch[i] and ts[k] >= ts[i] - 300:
                    oth = True
            ms = max(ms, s)
        sim_prev[i] = cnt; sim_other[i] = oth; maxsim[i] = ms
    f["nprev60"] = nprev60; f["nprev300"] = nprev300
    f["sim_prev"] = sim_prev; f["sim_other"] = sim_other; f["maxsim"] = maxsim
    f["first"] = sim_prev == 0
    # ---- calendar: scheduled USD high / medium events near the post (times known in advance)
    if cal is not None:
        c = cal[(cal.currency == "USD") & (cal.impact.isin(["high"]))]
        ct = np.sort((c.time_utc.astype("datetime64[ns]").astype("int64") // 10**9).unique())
        k = np.searchsorted(ct, ts, side="right")
        prev_ev = np.where(k > 0, ts - ct[np.clip(k - 1, 0, len(ct) - 1)], 10**9)
        next_ev = np.where(k < len(ct), ct[np.clip(k, 0, len(ct) - 1)] - ts, 10**9)
        f["cal_since"] = prev_ev    # seconds since last high-impact USD event
        f["cal_until"] = next_ev    # seconds until next
    return f
