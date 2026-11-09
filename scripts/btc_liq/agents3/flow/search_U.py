"""unions of burst families (deduplicated by decision second) x filters x exits x maxpos"""
import numpy as np, pandas as pd, numba as nb, fast, slib, btc_common as bc, sys, time, itertools
from srch import run_all, T
SP = '/home/user/oncandle/scripts/btc_liq/agents3/flow/cache/'
tag = sys.argv[1] if len(sys.argv) > 1 else 'real'
D = pd.read_pickle(SP + f'A_{tag}.pkl'); O = np.load(SP + f'A_{tag}_out.npz')
E, X, R, S, P, Rs, grid = O['E'], O['X'], O['R'].astype(float), O['S'].astype(float), O['P'].astype(float), O['Rs'].astype(float), O['grid']
fams = [(30, 5), (30, 6), (30, 8), (60, 6), (60, 7), (60, 8), (60, 10), (120, 8), (120, 10), (120, 12), (300, 10), (300, 12), (300, 16)]
UN = {'W30': [0, 1, 2], 'W60': [3, 4, 5, 6], 'W120': [7, 8, 9], 'W300': [10, 11, 12], 'W30-120': list(range(10)), 'all': list(range(13)),
      'small': [0, 3, 7, 10], 'mid': [1, 4, 8, 11], 'big': [2, 5, 9, 12]}
A_TH = (-0.0005, 0.0, 0.0005, 0.001, 0.0015, 0.002, 0.003)
BR = (0.0, 0.2, 0.3, 0.4, 0.5)
d0 = D.doi0.to_numpy(); br = D.big60_rel.fillna(0).to_numpy(); sig = D.sig.to_numpy(); fam = D.fam.to_numpy()
res = []; t0 = time.time()
for un, fl in UN.items():
    sel = np.flatnonzero(np.isin(fam, fl))
    ss = sig[sel]
    masks = []
    combos = list(itertools.product(A_TH, BR))
    for a, b in combos:
        mk = (d0[sel] >= a) & (br[sel] > b)
        # dedupe by decision second among the kept events
        idx = np.flatnonzero(mk)
        _, first = np.unique(ss[idx], return_index=True)
        m2 = np.zeros(len(sel), bool); m2[idx[first]] = True
        masks.append(m2)
    masks = np.array(masks)
    out = run_all(E[:, sel], X[:, sel], R[:, sel], S[:, sel], P[:, sel], Rs[:, sel], masks, sel, T['a'], T['m'], T['s'], T['e'])
    for ci, (a, b) in enumerate(combos):
        for g in range(len(grid)):
            for mp in range(3):
                o = out[ci, g, mp]
                if o[0] == 0: continue
                res.append((un, a, b, g, mp + 1, *o))
    print(un, time.time() - t0, flush=True)
cols = ['un', 'a', 'br', 'g', 'maxpos', 'n', 'R', 'pf', 'final', 'dd', 'R_q1', 'R_q2', 'spf', 'n_ja', 'R_ja', 'final_ja', 'dd_ja']
pd.DataFrame(res, columns=cols).to_pickle(SP + f'searchU_{tag}.pkl')
print('combos', len(res))
