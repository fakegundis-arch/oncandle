"""Trump Truth Social posts -> market events (keyword classification, known at post time).

A post is "high impact" if its text hits a topic list below.  Posts of one topic within `gap_min` minutes of the
previous one are merged (only the first starts an event).  `tone` is +1 risk-on / -1 risk-off from simple words.
The bot can only act after the post's minute is complete: first usable bar = minute after the post + `delay`.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

TOPICS = {
    "tariff": r"\btariff|\breciprocal\b|\bduties\b|\btrade deal|\btrade war|\bimport tax",
    "war": r"\biran\b|\bbomb|\bairstrike|\bstrike[sd]?\b|\bmissile|\bnuclear\b|\bwar\b|\bceasefire|\bcease-fire"
           r"|\bmilitary action|\bvenezuela|\bhamas\b|\bhezbollah|\bputin\b|\bukraine",
    "fed": r"\bpowell\b|\bfed\b|\bfederal reserve|\binterest rate|\brate cut|\bwarsh\b",
    "china": r"\bchina\b|\bxi\b|\bchinese\b",
    "oil": r"\boil\b|\bopec\b|\bgasoline\b",
    "crypto": r"\bbitcoin|\bcrypto",
}
RISK_OFF = r"\btariff|\bbomb|\bstrike|\battack|\bwar\b|\bsanction|\bdestroy|\bobliterat|\bretaliat|\bpenalt|\bblock"
RISK_ON = r"\bdeal\b|\bagreement|\bceasefire|\bcease-fire|\bpeace\b|\bpause|\bexempt|\bdelay|\breduc|\bcut rates|\brate cut" \
          r"|\bnegotiat|\bwonderful call|\bgreat call"
# market direction when the post is risk-on (+1)
RISK_ON_DIR = {"NAS100": 1, "US30": 1, "US500": 1, "BTCUSD": 1, "USOIL": 1, "XAUUSD": -1, "XAGUSD": 0,
               "USDJPY": 1, "EURUSD": 0, "GBPUSD": 0, "USDCAD": -1}


EXCLUDE = r"endorsement|is running for|vote for|early voting|get out and vote|happy birthday|congratulations to"


def classify(posts: pd.DataFrame, min_len: int = 40) -> pd.DataFrame:
    p = posts[posts.content.fillna("").str.len() >= min_len].copy()
    p = p[~p.content.str.lower().str.contains(EXCLUDE, regex=True)]
    low = p.content.str.lower()
    for k, rx in TOPICS.items():
        p[k] = low.str.contains(rx, regex=True)
    p["topic"] = p[list(TOPICS)].idxmax(axis=1).where(p[list(TOPICS)].any(axis=1))
    on = low.str.count(RISK_ON)
    off = low.str.count(RISK_OFF)
    p["tone"] = np.sign(on - off).astype(int)
    p["caps"] = p.content.map(lambda s: sum(ch.isupper() for ch in s) / max(1, sum(ch.isalpha() for ch in s)))
    return p[p.topic.notna()].drop(columns=list(TOPICS))


def events(cls: pd.DataFrame, gap_min: int = 60) -> pd.DataFrame:
    out = []
    for topic, g in cls.sort_values("time_utc").groupby("topic"):
        last = None
        for r in g.itertuples():
            if last is None or (r.time_utc - last) > pd.Timedelta(minutes=gap_min):
                out.append(r)
            last = r.time_utc
    ev = pd.DataFrame(out).drop(columns="Index", errors="ignore").sort_values("time_utc").reset_index(drop=True)
    return ev
