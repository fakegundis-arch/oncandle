"""Nasdaq v3 (first-3-minutes breakout): the settings grid on Jan-Jun 2026 and the pre-registered pick (research_v3.md).

usage: cd <repo> && PYTHONDONTWRITEBYTECODE=1 python bots/asia_news/lab/v3_select.py
-> lab/out/grid_v3.csv (every config), lab/out_v3_select.txt (the pick, its neighbours, its placebo), lab/out/v3_pick.json

Data: Jan-Jun 2026 only (lab/common.py -> scripts/asia_news_lab.prices_train / calendar_train).
"""
import itertools
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import strat as St  # noqa: E402

# Fixed by the protocol: N = 3 (the user's choice), AUD / NZD releases only, range incl. the pre-release close.
FIXED = dict(fam="brk", N=3, ccys=("AUD", "NZD"), incl_pre=True)
# The knobs, each in its order (neighbours = one knob moved one step).
KNOBS = dict(W=[30, 60, 120], stop=[0.5, 1.0, "range"], buf=[0.0, 0.05], tp_r=[0, 1, 2, 3], hold=[60, 120, 240, 360])


def cfg_of(k: dict) -> dict:
    P = {**FIXED, **{x: v for x, v in k.items() if x != "stop"}}
    if k["stop"] == "range":
        P["stop"] = "range"
    else:
        P["stop_k"] = float(k["stop"])
    return P


def run(k):
    o, _ = St.evaluate(cfg_of(k), placebo=False)
    return {**k, **o}


def key(k: dict) -> tuple:
    return tuple(str(k[x]) for x in KNOBS)


def neighbours(k: dict) -> list[dict]:
    out = []
    for x, vals in KNOBS.items():
        i = vals.index(k[x])
        for j in (i - 1, i + 1):
            if 0 <= j < len(vals):
                out.append({**k, x: vals[j]})
    return out


def main():
    St.news_set()
    combos = [dict(zip(KNOBS, c)) for c in itertools.product(*KNOBS.values())]
    with Pool(4) as pool:
        rows = pool.map(run, combos, chunksize=8)
    df = pd.DataFrame(rows)
    ok = {key(r): bool(r["ok"]) for r in rows}
    df["nb_pass"] = [sum(ok[key(n)] for n in neighbours(r)) / len(neighbours(r)) for r in rows]
    df["nb_n"] = [len(neighbours(r)) for r in rows]
    df.to_csv(HERE / "out" / "grid_v3.csv", index=False)

    # THE PICK (research_v3.md, protocol 4): among the passing configs, the highest share of passing neighbours;
    # ties -> the shallower Jan-Jun max drawdown at 10 %; then -> the higher R.
    cand = df[df.ok].sort_values(["nb_pass", "dd", "R"], ascending=[False, False, False])
    lines = [f"configs {len(df)}, passing {int(df.ok.sum())} ({df.ok.mean():.0%}); median PF {df.pf.median():.2f}, "
             f"median R {df.R.median():+.2f}, median n {df.n.median():.0f}"]
    for x, vals in KNOBS.items():
        lines.append(f"  pass share by {x}: " + ", ".join(f"{v}: {df[df[x].astype(str) == str(v)].ok.mean():.0%}"
                                                          for v in vals))
    if not len(cand):
        lines.append("NO CONFIG PASSES - v3 stops here (protocol 4).")
        (HERE / "out_v3_select.txt").write_text("\n".join(lines) + "\n")
        print("\n".join(lines))
        return
    lines.append("\ntop 10 by the pick rule:")
    lines.append(cand.head(10)[list(KNOBS) + ["n", "R", "pf", "dd", "q1", "q2", "pf2x", "pfL", "win", "nb_pass"]]
                 .to_string(index=False))
    pick = {x: cand.iloc[0][x] for x in KNOBS}
    pick = {x: (v if x == "stop" and str(v) == "range" else (float(v) if x in ("stop", "buf") else int(v)))
            for x, v in pick.items()}
    P = cfg_of(pick)
    full, trades = St.evaluate(P, placebo=True, boot=5000)
    lines.append(f"\nPICK {pick}\n  Jan-Jun: {full}")
    nb = df[[key(r) in {key(n) for n in neighbours(pick)} for r in rows]]
    lines.append("  neighbours:\n" + nb[list(KNOBS) + ["n", "R", "pf", "dd", "ok"]].to_string(index=False))
    lines.append("  trades:\n" + trades.to_string(index=False))
    (HERE / "out_v3_select.txt").write_text("\n".join(lines) + "\n")
    (HERE / "out" / "v3_pick.json").write_text(json.dumps(dict(knobs=pick, lab_cfg={**P, "ccys": list(P["ccys"])},
                                                               jan_jun=full), indent=1, default=str))
    print("\n".join(lines[:12]))
    print(f"\nPICK {pick}\n  {full}")


if __name__ == "__main__":
    main()
