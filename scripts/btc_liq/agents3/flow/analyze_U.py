import numpy as np, pandas as pd, sys
SP = '/home/user/oncandle/scripts/btc_liq/agents3/flow/cache/'
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 30)
grid = np.load(SP + 'A_real_out.npz')['grid']
def load(tag):
    R = pd.read_pickle(SP + f'searchU_{tag}.pkl')
    R['ok'] = (R.n >= 40) & (R.pf >= 1.3) & (R.R_q1 > 0) & (R.R_q2 > 0) & (R.spf >= 1.15) & (R.dd > -0.35)
    R['exit'] = [tuple(np.round(grid[int(g)], 1)) for g in R.g]
    return R
cols = ['un', 'a', 'br', 'exit', 'maxpos', 'n', 'R', 'pf', 'final', 'dd', 'R_q1', 'R_q2', 'spf', 'n_ja', 'R_ja', 'final_ja', 'dd_ja']
for tag in ['real'] + [f'fake{k}' for k in range(5)]:
    R = load(tag)
    ok = R[R.ok]
    b = ok.sort_values('final', ascending=False).head(1)
    print(tag, 'meet rules', len(ok), '| best final', round(b.final.iloc[0]) if len(b) else None, 'R', round(b.R.iloc[0], 1) if len(b) else None,
          '| best R', round(ok.R.max(), 1) if len(ok) else None)
R = load('real')
print(R[R.ok].sort_values('final', ascending=False).head(12)[cols].round(3).to_string())
# Jan-Apr selection
q = R[(R.n_ja >= 27) & (R.dd_ja > -0.35)]
print('by Jan-Apr final'); print(q.sort_values('final_ja', ascending=False).head(12)[cols].round(3).to_string())
