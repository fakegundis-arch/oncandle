import numpy as np, pandas as pd, numba as nb, fast, slib, btc_common as bc, sys, time, itertools
SP = '/home/user/oncandle/scripts/btc_liq/agents3/flow/cache/'
tag = sys.argv[1] if len(sys.argv) > 1 else 'real'
D = pd.read_pickle(SP + f'A_{tag}.pkl'); O = np.load(SP + f'A_{tag}_out.npz')
E, X, R, S, P, Rs, grid = O['E'], O['X'], O['R'].astype(float), O['S'].astype(float), O['P'].astype(float), O['Rs'].astype(float), O['grid']
T = {k: bc.ts_of(v) for k, v in dict(a='2026-01-01', m='2026-04-01', s='2026-05-01', e='2026-07-01').items()}
A_TH = (0.0005, 0.001, 0.0015, 0.002, 0.0025, 0.003, 0.004)
Z_TH = (-99, -2.0, 0.0, 2.0)
XF = {'none': np.ones(len(D), bool), 'edoi+': D.edoi0.fillna(-1).to_numpy() >= 0, 'doi1+': D.doi1.fillna(-1).to_numpy() >= 0,
      'bigrel<.3': D.big60_rel.fillna(9).to_numpy() <= 0.3, 'bigrel>.3': D.big60_rel.fillna(0).to_numpy() > 0.3,
      'v300<2': D.v300.fillna(9).to_numpy() < 2, 'v300>2': D.v300.fillna(0).to_numpy() >= 2,
      'brk4h>0': D.brk4h.fillna(-99).to_numpy() > 0, 'brk4h<0': D.brk4h.fillna(99).to_numpy() <= 0}


@nb.njit(cache=True)
def run_all(E, X, R, S, P, Rs, masks, idx, T_a, T_m, T_s, T_e):
    """masks [F, n] bool; idx = events of the family (sorted) -> metrics [F, G, 3(maxpos), 12]"""
    F, n = masks.shape; G = R.shape[0]
    out = np.zeros((F, G, 3, 12))
    for f in range(F):
        mk = masks[f]
        if mk.sum() < 10:
            continue
        for g in range(G):
            for mp in range(3):
                n1, R1, gw1, gl1, b1, dd1, Ra1, Rb1 = slib.acct_mask(E[g], X[g], R[g], S[g], P[g], mk, mp + 1, T_a, T_m, T_e)
                n2, R2, gw2, gl2, b2, dd2, Ra2, Rb2 = slib.acct_mask(E[g], X[g], R[g], S[g], P[g], mk, mp + 1, T_a, T_s, T_s)
                n3, R3, gw3, gl3, b3, dd3, Ra3, Rb3 = slib.acct_mask(E[g], X[g], Rs[g], S[g], P[g], mk, mp + 1, T_a, T_m, T_e)
                o = out[f, g, mp]
                o[0] = n1; o[1] = R1; o[2] = gw1 / max(gl1, 1e-9); o[3] = b1; o[4] = dd1; o[5] = Ra1; o[6] = Rb1
                o[7] = gw3 / max(gl3, 1e-9); o[8] = n2; o[9] = R2; o[10] = b2; o[11] = dd2
    return out


t0 = time.time()
res = []
fams = sorted(D.fam.unique())
d0 = D.doi0.to_numpy(); z = D.z.to_numpy()
combos = list(itertools.product(A_TH, Z_TH, XF.keys()))
for fi in fams:
    sel = np.flatnonzero(D.fam.to_numpy() == fi)
    masks = np.array([(d0[sel] >= a) & (z[sel] >= zz) & XF[x][sel] for a, zz, x in combos])
    out = run_all(E[:, sel], X[:, sel], R[:, sel], S[:, sel], P[:, sel], Rs[:, sel], masks, sel, T['a'], T['m'], T['s'], T['e'])
    for ci, (a, zz, x) in enumerate(combos):
        for g in range(len(grid)):
            for mp in range(3):
                o = out[ci, g, mp]
                if o[0] == 0: continue
                res.append((fi, a, zz, x, g, mp + 1, *o))
    print('fam', fi, time.time() - t0, flush=True)
cols = ['fam', 'a', 'z', 'xf', 'g', 'maxpos', 'n', 'R', 'pf', 'final', 'dd', 'R_q1', 'R_q2', 'spf', 'n_ja', 'R_ja', 'final_ja', 'dd_ja']
Rdf = pd.DataFrame(res, columns=cols)
Rdf.to_pickle(SP + f'searchA_{tag}.pkl')
print('combos', len(Rdf), time.time() - t0)
