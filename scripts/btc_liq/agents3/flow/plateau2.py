import numpy as np, pandas as pd
SP = '/home/user/oncandle/scripts/btc_liq/agents3/flow/cache/'
R = pd.read_pickle(SP + 'searchA_real.pkl'); grid = np.load(SP + 'A_real_out.npz')['grid']
fams = [(30, 5), (30, 6), (30, 8), (60, 6), (60, 7), (60, 8), (60, 10), (120, 8), (120, 10), (120, 12), (300, 10), (300, 12), (300, 16)]
R['ok'] = (R.n >= 40) & (R.pf >= 1.3) & (R.R_q1 > 0) & (R.R_q2 > 0) & (R.spf >= 1.15) & (R.dd > -0.35)
R['stop'] = grid[R.g.astype(int), 0]; R['tp'] = grid[R.g.astype(int), 1]; R['hold'] = grid[R.g.astype(int), 2]; R['trail'] = grid[R.g.astype(int), 3]
q = R[(R.xf == 'bigrel>.3') & (R.z == -99) & (R.maxpos == 2) & R.trail.isna()]
pd.set_option('display.width', 250)
# fraction of exits meeting rules per family x a
pv = q.groupby(['fam', 'a']).ok.mean().unstack(); pv.index = [fams[i] for i in pv.index]
print('share of 32 exit settings meeting all rules (bigrel>.3, maxpos 2)'); print(pv.round(2).to_string())
pv = q.groupby(['fam', 'a']).R.median().unstack(); pv.index = [fams[i] for i in pv.index]
print('median R over exit settings'); print(pv.round(1).to_string())
pv = q.groupby(['stop', 'hold']).R.median().unstack(); print('median R over fam x a by exit'); print(pv.round(1).to_string())
pv = q.groupby(['stop', 'hold']).ok.mean().unstack(); print(pv.round(2).to_string())
pv = q.groupby(['stop', 'hold']).dd.median().unstack(); print('median dd'); print(pv.round(2).to_string())
