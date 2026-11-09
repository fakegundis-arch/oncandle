import numpy as np, pandas as pd, sys
SP = '/home/user/oncandle/scripts/btc_liq/agents3/flow/cache/'
tag = sys.argv[1] if len(sys.argv) > 1 else 'real'
R = pd.read_pickle(SP + f'searchA_{tag}.pkl')
grid = np.load(SP + f'A_{tag}_out.npz')['grid']
fams = [(30, 5), (30, 6), (30, 8), (60, 6), (60, 7), (60, 8), (60, 10), (120, 8), (120, 10), (120, 12), (300, 10), (300, 12), (300, 16)]
R['ok'] = (R.n >= 40) & (R.pf >= 1.3) & (R.R_q1 > 0) & (R.R_q2 > 0) & (R.spf >= 1.15) & (R.dd > -0.35)
print(tag, 'combos', len(R), 'meeting rules on Jan-Jun', R.ok.sum())
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 30)
def show(df):
    df = df.copy(); df['fam'] = [fams[int(f)] for f in df.fam]; df['exit'] = [tuple(np.round(grid[int(g)], 1)) for g in df.g]
    print(df[['fam', 'a', 'z', 'xf', 'exit', 'maxpos', 'n', 'R', 'pf', 'final', 'dd', 'R_q1', 'R_q2', 'spf', 'n_ja', 'R_ja', 'final_ja', 'dd_ja']].round(3).to_string())
print('best Jan-Jun final meeting rules'); show(R[R.ok].sort_values('final', ascending=False).head(15))
print('best Jan-Jun R meeting rules'); show(R[R.ok].sort_values('R', ascending=False).head(5))
# Jan-Apr selection: rules analog on Jan-Apr (n_ja >= 27, dd_ja > -0.35) ; then show May-Jun = Jan-Jun minus? (need separate)
R['ok_ja'] = (R.n_ja >= 27) & (R.dd_ja > -0.35)
print('best Jan-Apr final'); show(R[R.ok_ja].sort_values('final_ja', ascending=False).head(15))
