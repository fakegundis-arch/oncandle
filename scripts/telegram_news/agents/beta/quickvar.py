from monthly import U, R, X, Fz, Fo, ev, ST, ex_index, fidx
from search import trades_for, evaluate
import numpy as np, pandas as pd
pd.set_option('display.width', 250)
rows = []
for st in [('P', 0, 0.5, 600), ('M', 0, 0.0, 0), ('S', 0, 0.5, 300)]:
    for filt in [(3, 'any', 0, 0, 'any', 1, 1), (3, 'any', 0, 0, 'any', 0, 0), (3, 'any', 0, 1, 'any', 1, 1), (3, 'any', 0, 0, 'any', 1, 0), (3, 'any', 0, 0, 'any', 0, 1)]:
        for ex in [(4.5, -1.0, -1.0, np.inf, 14400), (4.5, -1.0, 3.0, np.inf, 14400), (3.0, -1.0, -1.0, np.inf, 7200)]:
            rw = dict(style=ST.index(st), L=30, mode=1, fi=fidx(filt), exit=ex_index(*ex))
            o = evaluate(trades_for(U, R, X, Fz, Fo, ev, rw)); o.update(st=st, filt=filt, ex=ex); rows.append(o)
df = pd.DataFrame(rows)
print(df[['st', 'filt', 'ex', 's_n', 's_R', 's_pf', 's_fin', 'c_n', 'c_R', 'c_pf', 'c_fin', 'h_n', 'h_fin', 'h_dd']].round(2).to_string())
