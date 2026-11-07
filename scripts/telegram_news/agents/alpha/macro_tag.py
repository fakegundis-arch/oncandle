import sys, pandas as pd
from lib import WORK
import macro
tag = sys.argv[1] if len(sys.argv) > 1 else ""
p = pd.read_pickle(f"{WORK}/posts{tag}.pkl")
m = macro.parse(p.clean); m.index = p.index
m.to_pickle(f"{WORK}/macro{tag}.pkl")
print("macro", tag, (m.mstrong != 0).sum())
