import sys
import numpy as np, pandas as pd
from lib import WORK
from prep_outcomes import STOPS, TPS, TIMERS

name = sys.argv[1] if len(sys.argv) > 1 else "res"
df = pd.read_parquet(f"{WORK}/{name}.parquet")
fl = pd.read_csv(f"{WORK}/{name}_filters.csv", index_col=0).iloc[:, 0].tolist()
rl = pd.read_csv(f"{WORK}/{name}_rules.csv", index_col=0).iloc[:, 0].tolist()
df["final"] = 1000 * np.exp(df.lg.clip(upper=50))
df["frac_mpos"] = df.mpos / df.mtot.clip(lower=1)


def show(d, k=25):
    d = d.head(k).copy()
    d["inst"] = d.inst.map({0: "gold", 1: "nasdaq"})
    d["dl"] = d.dl.map({0: 0, 1: 10, 2: 30})
    d["rule"] = d.rule.map(lambda i: rl[i]); d["flt"] = d.flt.map(lambda i: fl[i])
    d["stop"] = d.s.map(lambda i: STOPS[i]); d["tp"] = d.q.map(lambda i: TPS[i]); d["tmr"] = d.h.map(lambda i: TIMERS[i])
    cols = ["inst", "dl", "rule", "flt", "stop", "tp", "tmr", "n", "R", "pf", "win", "final", "dd", "mpos", "mtot", "Rs", "pfs"]
    print(d[cols].round(3).to_string())


print("rows kept", len(df))
print("\n== top by final $ (search period), any")
show(df.sort_values("lg", ascending=False))
rob = df[(df.n >= 40) & (df.pfs > 1.1) & (df.frac_mpos >= 0.65) & (df.mtot >= 5)]
print("\n== robust (n>=40, stress PF>1.1, >=65% months positive):", len(rob))
show(rob.sort_values("lg", ascending=False))
