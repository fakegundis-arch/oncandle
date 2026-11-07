"""AFTER the one Jul-Oct test of gold_tune_lab (gold_tune_test.json): the whole grid on Jul-Oct, descriptive only -
does the Jan-Jun pattern (small stops worse, $20 targets and stop / target exits better) hold on the later months?
Nothing is picked from this file.  usage: cd <repo> && PYTHONDONTWRITEBYTECODE=1 python3 -I scripts/telegram_news/gold_tune_after.py"""
import sys
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bang_lab as B  # noqa: E402
import gold_tune_lab as G  # noqa: E402
import newsbot_lab as N  # noqa: E402

_F: dict = {}


def work(c):
    m = N.metrics(G.run(_F[c["trig"]], c), *G.TEST)
    return dict(c, **{f"t_{k}": v for k, v in m.items()})


def main():
    assert (N.OUT / "gold_tune_test.json").exists(), "the one Jul-Oct test must come first"
    for k, v in G.trigger_sets("2026-06-30", G.TEST[1]).items():
        _F[k] = B.features(v, "gold")
    N.ticks("gold")
    with Pool(4) as pool:
        rows = pool.map(work, G.configs(), chunksize=24)
    t = pd.DataFrame(rows)
    b = pd.read_csv(N.OUT / "gold_tune_grid.csv")
    t["H"], b["H"] = t.H.fillna(0).astype(int), b.H.fillna(0).astype(int)
    df = b.merge(t, on=G.KNOBS, how="inner", validate="one_to_one")
    assert len(df) == len(b)
    df.to_csv(N.OUT / "gold_tune_after.csv", index=False)


if __name__ == "__main__":
    main()
