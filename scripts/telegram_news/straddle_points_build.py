"""Jan-Jun 2026 grid of the Nasdaq +/-30-point straddle (straddle_points_lab.py) and the pre-registered pick.
usage: cd <repo> && PYTHONDONTWRITEBYTECODE=1 python3 -I scripts/telegram_news/straddle_points_build.py"""
import itertools
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import newsbot_lab as N  # noqa: E402
import straddle_points_lab as P  # noqa: E402

_F: dict = {}


def key(c):
    return tuple(c[k] for k in P.KNOBS)


def neighbours(c):
    out = []
    for k in P.KNOBS:
        vals = P.GRID[k]
        i = vals.index(c[k])
        out += [{**c, k: vals[j]} for j in (i - 1, i + 1) if 0 <= j < len(vals)]
    return out


def work(c):
    t, ts = P.run(_F["f"], P.INST, c), P.run(_F["f"], P.INST, c, stress=True)
    ok, m = P.passes_build(t, ts)
    return dict(c, ok=ok, **{k: v for k, v in m.items() if not k.endswith(("40", "1.3", "R>0", "1.15", "35%"))})


def main():
    tp = N.tradable(N.load_posts(*P.BUILD))
    assert (tp.t < pd.Timestamp(P.BUILD[1], tz="UTC")).all()
    _F["f"] = P.features(tp)
    N.ticks(P.INST)
    cs = [dict(zip(P.KNOBS, c)) for c in itertools.product(*P.GRID.values())]
    with Pool(4) as pool:
        rows = pool.map(work, cs, chunksize=4)
    df = pd.DataFrame(rows)
    ok = {key(r): bool(r["ok"]) for r in rows}
    df["nb_pass"] = [np.mean([ok.get(key(n), False) for n in neighbours(r)]) for r in rows]
    df.to_csv(N.OUT / "straddle_nas30_grid.csv", index=False)
    cols = P.KNOBS + ["n", "R", "pf", "win", "dd", "usd", "h1R", "h2R", "stress_pf", "nb_pass"]
    txt = [f"{len(tp)} tradable posts Jan-Jun; {len(df)} settings, {int(df.ok.sum())} pass; median PF {df.pf.median():.2f}, "
           f"{int((df.R > 0).sum())} made money"]
    for k in P.KNOBS[1:]:
        txt.append(f"  by {k:6s}: " + ", ".join(f"{v}: PF {df[df[k].astype(str) == str(v)].pf.median():.2f}" for v in P.GRID[k]))
    txt.append("  best 12 by R:\n" + df.sort_values("R", ascending=False).head(12)[cols].to_string(index=False))
    cand = df[df.ok].sort_values(["nb_pass", "dd", "R"], ascending=[False, False, False])
    if len(cand):
        pick = {k: (cand.iloc[0][k].item() if hasattr(cand.iloc[0][k], "item") else cand.iloc[0][k]) for k in P.KNOBS}
        out = {"pick": pick}
        txt.append("  passing, by the pick rule:\n" + cand.head(10)[cols].to_string(index=False) + f"\n  PICK: {pick}")
    else:
        b = df.sort_values("R", ascending=False).iloc[0]
        info = {k: (b[k].item() if hasattr(b[k], "item") else b[k]) for k in P.KNOBS}
        out = {"info_only": info}
        txt.append(f"  NO SETTING PASSES - not traded (protocol); info-only Jul-Oct run of the highest-R setting: {info}")
    (N.OUT / "straddle_nas30_build.txt").write_text("\n".join(txt) + "\n")
    (N.OUT / "straddle_nas30_pick.json").write_text(json.dumps(out, indent=1))
    print("\n".join(txt))


if __name__ == "__main__":
    main()
