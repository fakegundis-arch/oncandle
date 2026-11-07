import sys, pandas as pd, numpy as np
pd.set_option('display.width', 260); pd.set_option('display.max_columns', 40)
from outcomes import styles
from search import exit_desc
cols = ['st', 'L', 'mode', 'filt', 'ex', 'smooth', 'fam_mean', 's_n', 's_R', 's_pf', 's_fin', 's_dd', 'c_n', 'c_R', 'c_pf', 'c_fin', 'h_fin']
N = int(sys.argv[1])
for f in sys.argv[2:]:
    r = pd.read_pickle(f)
    r['st'] = [styles()[s] for s in r['style']]
    r['ex'] = [tuple(exit_desc(x).values()) for x in r.exit]
    t = r.head(100)
    print(f, 'top-by-smooth: search$ %.0f  check$ %.0f | top100: max search$ %.0f med search$ %.0f med check$ %.0f frac>1000 %.2f med checkR %.1f' % (
        r.s_fin.iloc[0], r.c_fin.iloc[0], t.s_fin.max(), t.s_fin.median(), t.c_fin.median(), (t.c_fin > 1000).mean(), t.c_R.median()))
    if N: print(r[cols].head(N).to_string())
