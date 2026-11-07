"""Jan-Jun 2026 grid of gold_tune_lab.py (9,984 settings) and the pre-registered pick.
usage: cd <repo> && PYTHONDONTWRITEBYTECODE=1 python3 -I scripts/telegram_news/gold_tune_build.py"""
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bang_lab as B  # noqa: E402
import gold_tune_lab as G  # noqa: E402
import newsbot_lab as N  # noqa: E402

_F: dict = {}
NB_KNOBS = ["stop", "target", "H"]


def key(c):
    return tuple(str(c[k]) for k in G.KNOBS)


def neighbours(c):
    out = []
    for k in NB_KNOBS:
        vals = G.GRID[k]
        i = vals.index(c[k])
        out += [{**c, k: vals[j]} for j in (i - 1, i + 1) if 0 <= j < len(vals)]
    return out


def work(c):
    f = _F[c["trig"]]
    t, ts = G.run(f, c), G.run(f, c, stress=True)
    ok, m = B.passes_build(t, ts)
    return dict(c, ok=ok, **{k: v for k, v in m.items() if not k.endswith(("40", "1.3", "R>0", "1.15", "35%"))})


def main():
    sets = G.trigger_sets(*G.BUILD)
    for k, v in sets.items():
        assert (v.t < pd.Timestamp(G.BUILD[1], tz="UTC")).all()
        _F[k] = B.features(v, "gold")
    N.ticks("gold")
    cs = G.configs()
    with Pool(4) as pool:
        rows = pool.map(work, cs, chunksize=24)
    df = pd.DataFrame(rows)
    okd = {key(r): bool(r["ok"]) for r in rows}
    df["nb_pass"] = [np.mean([okd.get(key(n), False) for n in neighbours(r)]) for r in rows]
    df["desc"] = [G.describe({k: r[k] for k in G.KNOBS}) for r in rows]
    df.to_csv(N.OUT / "gold_tune_grid.csv", index=False)
    txt = [f"triggers Jan-Jun: story {len(sets['story'])} ({int(sets['story'].in_cal.sum())} in calendar windows), "
           f"every {len(sets['every'])}",
           f"{len(df)} settings, {int(df.ok.sum())} pass; median PF {df.pf.median():.2f}; {int((df.R > 0).sum())} made money"]
    for k in ["stop", "target", "H", "trig", "topics"]:
        txt.append(f"  median PF by {k:6s}: " + ", ".join(f"{v}: {df[df[k].astype(str) == str(v)].pf.median():.2f}"
                                                          for v in G.GRID[k]))
    ent = df.groupby("entry").pf.median()
    txt.append("  median PF by entry: " + ", ".join(f"{G.describe(dict(entry=e, stop=10, target=20, H=1800, trig='story', topics='ANY')).split(',')[0]}: {v:.2f}"
                                                     for e, v in ent.items()))
    cols = ["desc", "n", "R", "pf", "win", "dd", "usd", "h1R", "h2R", "stress_pf", "nb_pass"]
    txt.append("\nbest 15 by R:\n" + df.sort_values("R", ascending=False).head(15)[cols].to_string(index=False))
    cand = df[df.ok].sort_values(["nb_pass", "dd", "R"], ascending=[False, False, False])
    out = {}
    if len(cand):
        txt.append(f"\n{len(cand)} passing, by the pick rule:\n" + cand.head(20)[cols].to_string(index=False))
        c = {k: (cand.iloc[0][k].item() if hasattr(cand.iloc[0][k], "item") else cand.iloc[0][k]) for k in G.KNOBS}
        c["H"] = None if c["H"] is None or (isinstance(c["H"], float) and np.isnan(c["H"])) else int(c["H"])
        out["pick"] = c
        txt.append(f"\nPICK: {G.describe(c)}")
    else:
        b = df.sort_values("R", ascending=False).iloc[0]
        c = {k: (b[k].item() if hasattr(b[k], "item") else b[k]) for k in G.KNOBS}
        c["H"] = None if c["H"] is None or (isinstance(c["H"], float) and np.isnan(c["H"])) else int(c["H"])
        out["info_only"] = c
        txt.append(f"\nNO SETTING PASSES - info-only Jul-Oct run of the highest-R: {G.describe(c)}")
    (N.OUT / "gold_tune_build.txt").write_text("\n".join(txt) + "\n")
    (N.OUT / "gold_tune_pick.json").write_text(json.dumps(out, indent=1, default=str))
    print("\n".join(txt))


if __name__ == "__main__":
    main()
