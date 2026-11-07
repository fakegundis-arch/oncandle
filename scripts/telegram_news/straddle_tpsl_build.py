"""Jan-Jun 2026 grid of the 2-minute TP / SL straddle (straddle_tpsl_lab.py), gold and Nasdaq, and the pre-registered
pick.  usage: cd <repo> && PYTHONDONTWRITEBYTECODE=1 python3 -I scripts/telegram_news/straddle_tpsl_build.py"""
import itertools
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import newsbot_lab as N  # noqa: E402
import straddle_tpsl_lab as L  # noqa: E402

_F: dict = {}


def key(c):
    return tuple(c[k] for k in L.KNOBS)


def neighbours(c, g):
    out = []
    for k in L.KNOBS:
        vals = g[k]
        i = vals.index(c[k])
        out += [{**c, k: vals[j]} for j in (i - 1, i + 1) if 0 <= j < len(vals)]
    return out


def work(args):
    inst, c = args
    t, ts = L.run(_F["f"], inst, c), L.run(_F["f"], inst, c, stress=True)
    ok, m = L.passes_build(t, ts)
    return dict(c, ok=ok, **{k: v for k, v in m.items() if not k.endswith(("40", "1.3", "R>0", "1.15", "35%"))})


def main():
    tp = N.tradable(N.load_posts(*L.BUILD))
    assert (tp.t < pd.Timestamp(L.BUILD[1], tz="UTC")).all()
    _F["f"] = L.features(tp)
    for inst in N.SYMS:
        N.ticks(inst)
    txt, out = [f"{len(tp)} tradable posts Jan-Jun (FJ {int((tp.ch == 'FJ').sum())}, WB {int((tp.ch == 'WB').sum())})"], {}
    cols = L.KNOBS + ["n", "R", "pf", "win", "dd", "usd", "h1R", "h2R", "stress_pf", "nb_pass"]
    for inst in N.SYMS:
        g = L.grid(inst)
        cs = [dict(zip(L.KNOBS, c)) for c in itertools.product(*g.values())]
        with Pool(4) as pool:
            rows = pool.map(work, [(inst, c) for c in cs], chunksize=8)
        df = pd.DataFrame(rows)
        ok = {key(r): bool(r["ok"]) for r in rows}
        df["nb_pass"] = [np.mean([ok.get(key(n), False) for n in neighbours(r, g)]) for r in rows]
        df.to_csv(N.OUT / f"straddle_tpsl_grid_{inst}.csv", index=False)
        txt.append(f"\n== {inst}: {len(df)} settings, {int(df.ok.sum())} pass; median PF {df.pf.median():.2f}; "
                   f"{int((df.R > 0).sum())} made money; median trades {df.n.median():.0f}")
        for k in L.KNOBS:
            txt.append(f"  by {k:7s}: " + ", ".join(f"{v}: PF {df[df[k].astype(str) == str(v)].pf.median():.2f}"
                                                     for v in g[k]))
        txt.append("  best 12 by R:\n" + df.sort_values("R", ascending=False).head(12)[cols].to_string(index=False))
        cand = df[df.ok].sort_values(["nb_pass", "dd", "R"], ascending=[False, False, False])
        if len(cand):
            pick = {k: (cand.iloc[0][k].item() if hasattr(cand.iloc[0][k], "item") else cand.iloc[0][k]) for k in L.KNOBS}
            out[inst] = {"pick": pick}
            txt.append("  passing, by the pick rule:\n" + cand.head(10)[cols].to_string(index=False) + f"\n  PICK {inst}: {pick}")
        else:
            b = df.sort_values("R", ascending=False).iloc[0]
            info = {k: (b[k].item() if hasattr(b[k], "item") else b[k]) for k in L.KNOBS}
            out[inst] = {"info_only": info}
            txt.append(f"  NO SETTING PASSES for {inst} - not traded (protocol); info-only Jul-Oct run of the highest-R "
                       f"setting: {info}")
    (N.OUT / "straddle_tpsl_build.txt").write_text("\n".join(txt) + "\n")
    (N.OUT / "straddle_tpsl_pick.json").write_text(json.dumps(out, indent=1))
    print("\n".join(txt))


if __name__ == "__main__":
    main()
