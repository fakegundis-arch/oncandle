import numpy as np, pandas as pd, fast, btc_common as bc
from sklearn.ensemble import HistGradientBoostingRegressor
SP = '/home/user/oncandle/scripts/btc_liq/agents3/flow/cache/'
F = pd.read_pickle(SP + 'ev.pkl').replace([np.inf, -np.inf], np.nan)
F['h1'] = F.ts < bc.ts_of('2026-04-01')
skip = {'s', 'd', 'ts', 'sk', 'h1', 'doi_n', 'doi0', 'doi1', 'tvr0', 'edoi0'} | {c for c in F.columns if c[0] in 'fg' and c[1:].isdigit()}
cols = [c for c in F.columns if c not in skip]
for tgt in ('f300', 'f900', 'f3600'):
    y = F[tgt].clip(-30, 30)
    res = []
    for tr, te in ((F.h1, ~F.h1), (~F.h1, F.h1)):
        mdl = HistGradientBoostingRegressor(max_depth=3, max_iter=200, learning_rate=0.03, min_samples_leaf=100)
        mdl.fit(F.loc[tr, cols], y[tr]); p = mdl.predict(F.loc[te, cols])
        yt = F.loc[te, tgt].to_numpy()
        o = np.argsort(-p); n = len(o)
        top = yt[o[:n // 10]]; bot = yt[o[-n // 10:]]
        res.append(f'top10% {np.nanmean(top):+.2f} bot10% {np.nanmean(bot):+.2f} all {np.nanmean(yt):+.2f} corr {np.corrcoef(p, np.nan_to_num(yt))[0,1]:+.3f}')
    print(tgt, ' || '.join(res), flush=True)
