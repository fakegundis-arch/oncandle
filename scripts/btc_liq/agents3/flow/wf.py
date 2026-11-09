import numpy as np, pandas as pd
SP = '/home/user/oncandle/scripts/btc_liq/agents3/flow/cache/'
for kind in ('A', 'U'):
    for tag in ['real'] + [f'fake{k}' for k in range(5)]:
        R = pd.read_pickle(SP + f'search{kind}_{tag}.pkl')
        R['R_mj'] = R.R - R.R_ja; R['n_mj'] = R.n - R.n_ja
        q = R[(R.n_ja >= 27) & (R.dd_ja > -0.35)].sort_values('final_ja', ascending=False)
        top = q.head(100)
        t1 = q.head(1)
        print(kind, tag, f'Jan-Apr best final {t1.final_ja.iloc[0]:.0f} R_ja {t1.R_ja.iloc[0]:.1f} -> May-Jun R {t1.R_mj.iloc[0]:+.1f} (n {t1.n_mj.iloc[0]:.0f}) | top100: mean May-Jun R {top.R_mj.mean():+.1f}, frac>0 {np.mean(top.R_mj > 0):.2f}, mean n_mj {top.n_mj.mean():.0f}')
