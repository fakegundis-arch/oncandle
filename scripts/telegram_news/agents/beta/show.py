import sys, pandas as pd, numpy as np
pd.set_option('display.width', 260); pd.set_option('display.max_columns', 40)
from outcomes import styles
from search import exit_desc
cols = ['st', 'L', 'mode', 'filt', 'ex', 'n', 'proxy', 's_n', 's_R', 's_pf', 's_fin', 's_dd', 'c_n', 'c_R', 'c_pf', 'c_fin', 'h_fin']
for f in sys.argv[1:]:
    r = pd.read_pickle(f)
    r['st'] = [styles()[s] for s in r['style']]
    r['ex'] = [tuple(exit_desc(x).values()) for x in r.exit]
    print(f, 'best search $ %.0f' % r.s_fin.max(), 'median check $ of top-100 by search $: %.0f' % r.sort_values('s_fin', ascending=False).head(100).c_fin.median(),
          'frac check>1000 (top100): %.2f' % (r.sort_values('s_fin', ascending=False).head(100).c_fin > 1000).mean())
    print(r.sort_values('s_fin', ascending=False)[cols].head(int(10)).to_string())
