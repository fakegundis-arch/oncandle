import numpy as np, pandas as pd
SP = '/home/user/oncandle/scripts/btc_liq/agents3/flow/cache/'
R = pd.read_pickle(SP + 'searchA_real.pkl'); grid = np.load(SP + 'A_real_out.npz')['grid']
fams = [(30, 5), (30, 6), (30, 8), (60, 6), (60, 7), (60, 8), (60, 10), (120, 8), (120, 10), (120, 12), (300, 10), (300, 12), (300, 16)]
R['stop'] = grid[R.g.astype(int), 0]; R['tp'] = grid[R.g.astype(int), 1]; R['hold'] = grid[R.g.astype(int), 2]; R['trail'] = grid[R.g.astype(int), 3]
R['famn'] = [fams[int(i)] for i in R.fam]; R['R_mj'] = R.R - R.R_ja
pd.set_option('display.width', 250)
q = R[(R.xf == 'bigrel>.3') & (R.z == -99) & R.trail.isna() & R.tp.isna() & (R.hold == 7200) & (R.maxpos == 2)]
for fam in (2, 4, 5, 7, 8, 9):
    print(q[(q.fam == fam)][['famn', 'a', 'stop', 'n', 'R', 'pf', 'final', 'dd', 'R_q1', 'R_q2', 'spf', 'R_ja', 'R_mj']].round(3).to_string(header=fam == 2))
