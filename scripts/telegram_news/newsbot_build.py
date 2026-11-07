"""Jan-Jun 2026 grid of the news bot (newsbot_lab.py protocol) and the pre-registered pick, per instrument.

usage: cd <repo> && PYTHONDONTWRITEBYTECODE=1 python3 -I scripts/telegram_news/newsbot_build.py
-> results/telegram_news/newsbot_grid_<inst>.csv, newsbot_build.txt, newsbot_pick.json"""
import itertools
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import newsbot_lab as N  # noqa: E402

KNOB_ORDER = ["L", "k", "H", "m", "r", "topics"]
_F: dict = {}


def configs():
    g = N.GRID
    out = []
    for fam in g["fam"]:
        Ls, ks = (g["L"], g["k"]) if fam in ("MOM", "FADE") else ([30], [0.0])
        for L, k, H, m, r, tp in itertools.product(Ls, ks, g["H"], g["m"], g["r"], g["topics"]):
            out.append(dict(fam=fam, L=L, k=k, H=H, m=m, r=r, topics=tp))
    return out


def key(c):
    return tuple(c[x] for x in ["fam"] + KNOB_ORDER)


def neighbours(c):
    out = []
    for x in KNOB_ORDER:
        if c["fam"] not in ("MOM", "FADE") and x in ("L", "k"):
            continue
        vals = N.GRID[x]
        i = vals.index(c[x])
        for j in (i - 1, i + 1):
            if 0 <= j < len(vals):
                out.append({**c, x: vals[j]})
    return out


def work(args):
    inst, c = args
    feat = _F[inst]
    t, ts = N.run(feat, inst, c), N.run(feat, inst, c, stress=True)
    ok, m = N.passes_build(t, ts)
    return dict(c, ok=ok, **{k: v for k, v in m.items() if not k.endswith(("40", "1.3", "R>0", "1.15", "35%"))})


def main():
    out_txt = []
    picks, grids = {}, {}
    for inst in N.SYMS:
        tp, feat = N.build_features(inst)
        _F[inst] = feat
        N.ticks(inst)
        out_txt.append(f"{inst}: {len(tp)} tradable posts Jan-Jun (FJ {int((tp.ch == 'FJ').sum())}, "
                       f"WB {int((tp.ch == 'WB').sum())}); lexicon direction on {int((feat.lex != 0).sum())}")
    cs = configs()
    for inst in N.SYMS:
        with Pool(4) as pool:
            rows = pool.map(work, [(inst, c) for c in cs], chunksize=20)
        df = pd.DataFrame(rows)
        ok = {key(r): bool(r["ok"]) for r in rows}
        df["nb_pass"] = [np.mean([ok.get(key(n), False) for n in neighbours(r)]) for r in rows]
        df.to_csv(N.OUT / f"newsbot_grid_{inst}.csv", index=False)
        grids[inst] = df
        out_txt.append(f"\n== {inst}: {len(df)} configs, {int(df.ok.sum())} pass ({df.ok.mean():.1%})")
        for fam, g in df.groupby("fam"):
            out_txt.append(f"  {fam:7s} {len(g):5d} configs, pass {g.ok.mean():6.1%}, median PF {g.pf.median():.2f}, "
                           f"median R {g.R.median():+.1f}, median n {g.n.median():.0f}")
        cand = df[df.ok].sort_values(["nb_pass", "dd", "R"], ascending=[False, False, False])
        cols = ["fam", "L", "k", "H", "m", "r", "topics", "n", "R", "pf", "win", "dd", "usd", "q1R", "q2R",
                "stress_pf", "nb_pass"]
        out_txt.append("  best 15 by R (any):\n" + df.sort_values("R", ascending=False).head(15)[cols].to_string(index=False))
        if len(cand):
            pick = {k: (cand.iloc[0][k].item() if hasattr(cand.iloc[0][k], "item") else cand.iloc[0][k])
                    for k in ["fam"] + KNOB_ORDER}
            picks[inst] = pick
            out_txt.append("  passing, by the pick rule:\n" + cand.head(10)[cols].to_string(index=False))
            out_txt.append(f"  PICK {inst}: {pick}")
        else:
            out_txt.append(f"  NO CONFIG PASSES for {inst} - not traded (protocol)")
    (N.OUT / "newsbot_build.txt").write_text("\n".join(out_txt) + "\n")
    (N.OUT / "newsbot_pick.json").write_text(json.dumps(picks, indent=1))
    print("\n".join(out_txt))


if __name__ == "__main__":
    main()
