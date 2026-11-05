"""Step 2: grids over each entry family (Jan-Jun 2026 releases) with the pass rules and the same-clock-time placebo.
Looks for plateaus, not maxima.  usage: python grid.py <family> [...]  -> out/grid_<family>.csv
"""
import itertools
import sys
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import strat as St  # noqa: E402

EXITS = dict(stop_k=[0.5, 1.0, 1.5, 2.0], tp_r=[0, 1, 2, 3], hold=[60, 120, 240, 360])
GRIDS = {
    "news": dict(fam=["news"], delay=[1, 3, 5, 10, 15, 30, 60], filt=["all", "score2", "agree", "confirm"], **EXITS),
    "mom": dict(fam=["mom"], N=[1, 2, 3, 5, 10, 15, 30], k=[0.0, 0.05, 0.1, 0.2], **EXITS),
    "fade": dict(fam=["fade"], N=[1, 2, 3, 5, 10, 15, 30], k=[0.0, 0.05, 0.1, 0.2], **EXITS),
    "brk": dict(fam=["brk"], N=[1, 3, 5, 10, 15, 30], W=[30, 60, 120], stop=["range", 0.5, 1.0], buf=[0.0, 0.05],
                tp_r=[0, 1, 2, 3], hold=[60, 120, 240, 360]),
    "strad": dict(fam=["strad"], K=[15, 30, 60], W=[10, 30, 60], buf=[0.0, 0.05, 0.1], stop=["range", 0.5, 1.0],
                  tp_r=[0, 1, 2, 3], hold=[60, 120, 240]),
    "pairdir": dict(fam=["pairdir"], N=[1, 2, 3, 5, 15], k=[0.0, 2.0, 5.0], nq_agree=[0, 1], **EXITS),
    "pairAN": dict(fam=["pairdir"], ccys=[("AUD", "NZD")], N=[1, 2, 3, 5], k=[0.0, 2.0], stop_k=[1.0, 1.5, 2.0],
                   tp_r=[0, 2], hold=[120, 180, 240, 300, 360, 420]),
    "momAN": dict(fam=["mom"], ccys=[("AUD", "NZD")], N=[1, 2, 3, 5], k=[0.0], stop_k=[1.0, 1.5, 2.0], tp_r=[0, 2], hold=[120, 180, 240, 300, 360, 420]),
    "pull": dict(fam=["pull"], N=[3, 5, 10, 15], x=[0.382, 0.5, 0.618], k=[0.1, 0.2, 0.3], W=[30, 60],
                 stop_k=[0.5, 1.0, 1.5], tp_r=[0, 1, 2], hold=[120, 240]),
}


def cfg_of(p: dict) -> dict:
    P = dict(p)
    f = P.pop("filt", None)
    if f == "score2":
        P["min_score"] = 2
    elif f == "agree":
        P["agree"] = 1
    elif f == "confirm":
        P["confirm"] = 1
    if "stop" in P:
        s = P.pop("stop")
        if s == "range":
            P["stop"] = "range"
        else:
            P["stop_k"] = float(s)
    return P


def run(p):
    o, _ = St.evaluate(cfg_of(p), placebo=True, boot=500)
    return {**p, **o}


if __name__ == "__main__":
    St.news_set(); St.placebo_set()
    for fam in sys.argv[1:]:
        g = GRIDS[fam]
        combos = [dict(zip(g, c)) for c in itertools.product(*g.values())]
        with Pool(4) as pool:
            rows = pool.map(run, combos, chunksize=16)
        df = pd.DataFrame(rows)
        df.to_csv(Path(__file__).parent / "out" / f"grid_{fam}.csv", index=False)
        print(f"{fam}: {len(df)} configs, {int(df.ok.sum())} pass ({df.ok.mean():.0%}); median PF {df.pf.median():.2f}; "
              f"median placebo PF {df.pl_pf.median():.2f}; median avgR news {df.avgR.median():+.3f} placebo "
              f"{df.pl_avgR.median():+.3f}")
