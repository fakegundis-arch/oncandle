"""Pseudo-calendar placebo: replace every release by the SAME clock time on a random weekday without a release
(keeping the release's currency / kind / news sign), K times.  Run the same rule with the same pass rules on each
pseudo calendar.  'Does it work as well without news?' in the protocol's own terms.
usage: python pseudo.py  (imported by other scripts)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import common as C  # noqa: E402
import sim as S  # noqa: E402
import strat as St  # noqa: E402

_PS: dict = {}


def calendars(K=100, seed=11):
    if K in _PS:
        return _PS[K]
    rt = C.rel_table()
    days = {pd.Timestamp(t).date() for t in rt.time}
    ctxs, info = St.news_set()
    pool = {}
    for t in rt.time:
        pool[pd.Timestamp(t)] = S.contexts(C.placebo_times([t], exclude_days=days), "placebo")
    rng = np.random.default_rng(seed)
    out = []
    for k in range(K):
        cs, inf = [], {}
        for t in rt.time:
            t = pd.Timestamp(t)
            cands = pool[t]
            c = cands[int(rng.integers(len(cands)))]
            if c["t"] in inf:               # same day/time already used in this calendar: draw again
                c = cands[int(rng.integers(len(cands)))]
            cs.append(c)
            inf[c["t"]] = info[t]
        cs.sort(key=lambda c: c["t"])
        out.append((cs, inf))
    _PS[K] = out
    return out


def test(P, K=100):
    """-> DataFrame, one row per pseudo calendar: n, R, pf, ok (pass rules)."""
    rows = []
    for ev in calendars(K):
        o, _ = St.evaluate(P, placebo=False, events=ev)
        rows.append(o)
    return pd.DataFrame(rows)
