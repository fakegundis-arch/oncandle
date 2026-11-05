"""Selection-adjusted placebo ("data snooping"): run a whole family grid on the real calendar AND on K pseudo
calendars (same clock times, days without releases).  For each calendar: share of configs that pass the pass rules,
best R among passing configs.  If pseudo calendars look as good as the real one, the family's best result is what a
search finds anywhere.   usage: python snoop.py <family> [K]"""
import itertools
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import pseudo as Ps  # noqa: E402
import strat as St  # noqa: E402
from grid import cfg_of  # noqa: E402

EX = dict(stop_k=[0.5, 1.0, 1.5, 2.0], tp_r=[0, 1, 2, 3], hold=[60, 120, 240, 360])
FAM = {
    "mom": dict(fam=["mom"], N=[1, 2, 3, 5], k=[0.0], **EX),
    "brk": dict(fam=["brk"], N=[1, 3, 5], W=[60], stop=[0.5, 1.0], buf=[0.0, 0.05], tp_r=[0, 1, 2, 3], hold=[60, 120, 240, 360]),
    "strad": dict(fam=["strad"], K=[15, 30], W=[10, 30], buf=[0.0], stop=[0.5, 1.0], tp_r=[0, 1, 2, 3], hold=[60, 120, 240]),
    "pairdir": dict(fam=["pairdir"], N=[1, 2, 3, 5], k=[0.0], **EX),
    "pairAN": dict(fam=["pairdir"], ccys=[("AUD", "NZD")], N=[1, 2, 3], k=[0.0], stop_k=[1.0, 1.5, 2.0],
                   tp_r=[0], hold=[240, 300, 360, 420]),
    "news": dict(fam=["news"], delay=[1, 3, 5, 10, 15], **EX),
}
CAL = None


def one(args):
    k, p = args
    ev = None if k < 0 else CAL[k]
    o, _ = St.evaluate(cfg_of(p), placebo=False, events=ev)
    return dict(cal=k, ok=o["ok"], R=o["R"], pf=o["pf"], n=o["n"], **{f"p_{a}": b for a, b in p.items()})


if __name__ == "__main__":
    fam = sys.argv[1]
    K = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    CAL = Ps.calendars(100)[:K]
    St.news_set(); St.placebo_set()
    g = FAM[fam]
    combos = [dict(zip(g, c)) for c in itertools.product(*g.values())]
    jobs = [(k, p) for k in range(-1, K) for p in combos]
    with Pool(4) as pool:
        rows = pool.map(one, jobs, chunksize=32)
    df = pd.DataFrame(rows)
    df.to_csv(Path(__file__).parent / "out" / f"snoop_{fam}.csv", index=False)
    s = df.groupby("cal").apply(lambda x: pd.Series(dict(pass_share=x.ok.mean(), best_R_pass=x[x.ok].R.max() if x.ok.any() else 0.0,
                                                          median_R=x.R.median(), mean_pf=x.pf.clip(upper=5).mean())))
    real = s.loc[-1]
    ps = s.drop(index=-1)
    print(f"{fam}: {len(combos)} configs, real calendar: pass {real.pass_share:.2f}, best passing R {real.best_R_pass:.1f}, "
          f"median R {real.median_R:.2f}")
    print(f"   pseudo ({K}): pass share median {ps.pass_share.median():.2f} (>= real: {(ps.pass_share >= real.pass_share).mean():.2f}); "
          f"best passing R median {ps.best_R_pass.median():.1f} (>= real: {(ps.best_R_pass >= real.best_R_pass).mean():.2f}); "
          f"median R >= real: {(ps.median_R >= real.median_R).mean():.2f}")
