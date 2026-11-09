import numpy as np, pandas as pd, sys
SP = '/home/user/oncandle/scripts/btc_liq/agents3/flow/cache/'
tag = sys.argv[1] if len(sys.argv) > 1 else 'real'
R = pd.read_pickle(SP + f'searchA_{tag}.pkl')
grid = np.load(SP + f'A_{tag}_out.npz')['grid']
fams = [(30, 5), (30, 6), (30, 8), (60, 6), (60, 7), (60, 8), (60, 10), (120, 8), (120, 10), (120, 12), (300, 10), (300, 12), (300, 16)]
R = R[R.maxpos == 2]
pd.set_option('display.width', 250)
g0 = [i for i, g in enumerate(grid) if g[0] == 10 and g[2] == 7200 and np.isnan(g[1]) and np.isnan(g[3])][0]
g1 = [i for i, g in enumerate(grid) if g[0] == 20 and g[2] == 7200 and np.isnan(g[1]) and np.isnan(g[3])][0]
for g in (g0, g1):
    print('exit', grid[g])
    for xf in ('none', 'bigrel>.3', 'bigrel<.3'):
        q = R[(R.g == g) & (R.xf == xf) & (R.z == -99)]
        pv = q.pivot_table(index='fam', columns='a', values='R'); pv.index = [fams[i] for i in pv.index]
        pn = q.pivot_table(index='fam', columns='a', values='n'); pn.index = pv.index
        print(xf, 'R'); print(pv.round(1).to_string()); print('n'); print(pn.to_string())
