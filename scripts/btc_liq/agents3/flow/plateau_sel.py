"""plateau selection on Jan-Apr only: score = median log(final Jan-Apr) over the 3x3x3x3 neighbourhood (OI threshold, X within W, stop, hold)"""
import numpy as np, pandas as pd, sys, itertools
SP = '/home/user/oncandle/scripts/btc_liq/agents3/flow/cache/'
tag = sys.argv[1] if len(sys.argv) > 1 else 'real'
R = pd.read_pickle(SP + f'searchA_{tag}.pkl'); grid = np.load(SP + f'A_{tag}_out.npz')['grid']
fams = [(30, 5), (30, 6), (30, 8), (60, 6), (60, 7), (60, 8), (60, 10), (120, 8), (120, 10), (120, 12), (300, 10), (300, 12), (300, 16)]
A_TH = [0.0005, 0.001, 0.0015, 0.002, 0.0025, 0.003, 0.004]; ST = [10, 15, 20, 30]; HO = [1800, 3600, 7200, 14400]
g = R.g.astype(int).to_numpy()
R['si'] = [ST.index(int(x)) for x in grid[g, 0]]; R['hi'] = [HO.index(int(x)) for x in grid[g, 2]]
R['tpk'] = np.where(np.isnan(grid[g, 1]), 0, 1); R['trk'] = np.where(np.isnan(grid[g, 3]), 0, 1)
R['ai'] = [A_TH.index(x) for x in R.a]
R['W'] = [fams[int(f)][0] for f in R.fam]; R['xi'] = [sorted([x for w, x in fams if w == fams[int(f)][0]]).index(fams[int(f)][1]) for f in R.fam]
R['lf'] = np.log(np.maximum(R.final_ja, 1.0)) * ((R.n_ja >= 27) & (R.dd_ja > -0.35)) + np.log(np.maximum(R.final_ja, 1.0)).where(~((R.n_ja >= 27) & (R.dd_ja > -0.35)), 0) * 0
R.loc[~((R.n_ja >= 27) & (R.dd_ja > -0.35)), 'lf'] = np.log(np.maximum(R.final_ja, 1.0)) - 1.0   # penalise rule breakers
key = ['W', 'xi', 'ai', 'z', 'xf', 'si', 'hi', 'tpk', 'trk', 'maxpos']
lut = dict(zip(map(tuple, R[key].to_numpy().tolist()), R.lf.to_numpy()))
sc = []
for row in R[key].itertuples(index=False):
    W, xi, ai, z, xf, si, hi, tpk, trk, mp = row
    vals = []
    for dx, da, ds, dh in itertools.product((-1, 0, 1), repeat=4):
        v = lut.get((W, xi + dx, ai + da, z, xf, si + ds, hi + dh, tpk, trk, mp))
        vals.append(v if v is not None else 0.0)   # missing neighbour (edge) counts as break-even (log 1000 ~ 6.9 -> use 0 = worse)
    sc.append(np.median(vals))
R['score'] = sc
R['R_mj'] = R.R - R.R_ja; R['n_mj'] = R.n - R.n_ja
best = R.sort_values('score', ascending=False).head(10)
best = best.assign(fam=[fams[int(f)] for f in best.fam], exit=[tuple(np.round(grid[int(x)], 1)) for x in best.g])
pd.set_option('display.width', 250)
print(tag); print(best[['fam', 'a', 'z', 'xf', 'exit', 'maxpos', 'score', 'n_ja', 'R_ja', 'final_ja', 'dd_ja', 'R_mj', 'n_mj', 'n', 'R', 'pf', 'final', 'dd', 'spf']].round(3).to_string())
