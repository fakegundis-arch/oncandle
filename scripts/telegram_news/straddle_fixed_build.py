"""Jan-Jun 2026 grid of the fixed-distance straddle (straddle_fixed_lab.py protocol) and the pre-registered pick.
usage: cd <repo> && PYTHONDONTWRITEBYTECODE=1 python3 -I scripts/telegram_news/straddle_fixed_build.py
-> results/telegram_news/straddle_fixed_grid_<inst>.csv, straddle_fixed_build.txt, straddle_fixed_pick.json"""
import itertools
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import newsbot_lab as N  # noqa: E402
import straddle_fixed_lab as S  # noqa: E402

_F: dict = {}


def configs():
    return [dict(zip(S.KNOBS, c)) for c in itertools.product(*S.GRID.values())]


def key(c):
    return tuple(c[k] for k in S.KNOBS)


def neighbours(c):
    out = []
    for k in S.KNOBS:
        vals = S.GRID[k]
        i = vals.index(c[k])
        for j in (i - 1, i + 1):
            if 0 <= j < len(vals):
                out.append({**c, k: vals[j]})
    return out


def work(args):
    inst, c = args
    feat = _F[inst]
    t, ts = S.run(feat, inst, c), S.run(feat, inst, c, stress=True)
    ok, m = S.passes_build(t, ts)
    return dict(c, ok=ok, **{k: v for k, v in m.items() if not k.endswith(("40", "1.3", "R>0", "1.15", "35%"))})


def main():
    txt, picks = [], {}
    tp = N.tradable(N.load_posts(*S.BUILD))
    assert (tp.t >= pd.Timestamp(S.BUILD[0], tz="UTC")).all() and (tp.t < pd.Timestamp(S.BUILD[1], tz="UTC")).all()
    for inst in N.SYMS:
        _F[inst] = S.features(tp)
        N.ticks(inst)
    txt.append(f"{len(tp)} tradable posts Jan-Jun (FJ {int((tp.ch == 'FJ').sum())}, WB {int((tp.ch == 'WB').sum())})")
    cs = configs()
    for inst in N.SYMS:
        with Pool(4) as pool:
            rows = pool.map(work, [(inst, c) for c in cs], chunksize=16)
        df = pd.DataFrame(rows)
        ok = {key(r): bool(r["ok"]) for r in rows}
        df["nb_pass"] = [np.mean([ok.get(key(n), False) for n in neighbours(r)]) for r in rows]
        df.to_csv(N.OUT / f"straddle_fixed_grid_{inst}.csv", index=False)
        txt.append(f"\n== {inst}: {len(df)} settings, {int(df.ok.sum())} pass ({df.ok.mean():.1%}); median PF "
                   f"{df.pf.median():.2f}, median R {df.R.median():+.1f}, median trades {df.n.median():.0f}")
        for k in S.KNOBS:
            txt.append(f"  by {k:6s}: " + ", ".join(f"{v}: PF {df[df[k].astype(str) == str(v)].pf.median():.2f}"
                                                    for v in S.GRID[k]))
        cols = S.KNOBS + ["n", "R", "pf", "win", "dd", "usd", "h1R", "h2R", "stress_pf", "nb_pass"]
        txt.append("  best 12 by R:\n" + df.sort_values("R", ascending=False).head(12)[cols].to_string(index=False))
        cand = df[df.ok].sort_values(["nb_pass", "dd", "R"], ascending=[False, False, False])
        if len(cand):
            pick = {k: (cand.iloc[0][k].item() if hasattr(cand.iloc[0][k], "item") else cand.iloc[0][k]) for k in S.KNOBS}
            picks[inst] = pick
            txt.append("  passing, by the pick rule:\n" + cand.head(10)[cols].to_string(index=False))
            txt.append(f"  PICK {inst}: {pick}")
        else:
            best = df.sort_values("R", ascending=False).iloc[0]
            info = {k: (best[k].item() if hasattr(best[k], "item") else best[k]) for k in S.KNOBS}
            picks[inst + "_info_only"] = info
            txt.append(f"  NO SETTING PASSES for {inst} - not traded (protocol); info-only 2025 run of the highest-R "
                       f"setting: {info}")
    (N.OUT / "straddle_fixed_build.txt").write_text("\n".join(txt) + "\n")
    (N.OUT / "straddle_fixed_pick.json").write_text(json.dumps(picks, indent=1))
    print("\n".join(txt))


if __name__ == "__main__":
    main()
