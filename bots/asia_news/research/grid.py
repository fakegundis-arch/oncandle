"""Grid over a SMALL rule family (Jan-Jun 2026 only) to see where results are stable, not to pick the maximum.
usage: python grid.py gold|nasdaq|pair [name]"""
import itertools
import sys
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

TB = ["unemployment rate", "cpi y/y", "cpi q/q"]
SIGS = {"ff": {"vote": "ff"}, "ffTB": {"vote": "ff", "tiebreak": TB}}
GRID = dict(sig=list(SIGS), confirm=[0, 1], entry_delay=[1, 15, 30], stop_k=[0.5, 1.0, 1.5, 2.0],
            target_r=[1.0, 2.0, 3.0, 0.0], hold_min=[60, 120, 240, 360])
INST = {"gold": ("gold", "XAUUSD"), "nasdaq": ("nasdaq", "NAS100"), "pair": ("pair", None)}


def run(args):
    import harness as H
    inst, combo = args
    p = dict(zip(GRID, combo))
    kind, sym = INST[inst]
    cfg = dict(instrument=kind, signal=SIGS[p["sig"]], **{k: v for k, v in p.items() if k != "sig"})
    if kind == "pair":
        out, t = H.evaluate_pair(cfg)
    else:
        cfg["symbol"] = sym
        out, t = H.evaluate(cfg)
    out.update(H.loo(t) if len(t) > 2 else {})
    return {**p, **out}


if __name__ == "__main__":
    inst = sys.argv[1]
    combos = list(itertools.product(*GRID.values()))
    with Pool(4) as pool:
        rows = pool.map(run, [(inst, c) for c in combos], chunksize=8)
    df = pd.DataFrame(rows)
    df.to_csv(Path(__file__).parent / f"grid_{inst}.csv", index=False)
    print(len(df), "configs;", int(df.passed.sum()), "pass")
