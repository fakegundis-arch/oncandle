"""lean loader + helpers for the search (same semantics as btc_common.Market, less memory)."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import btc_common as bc

DATA = '/home/user/btc_lab_data'


class Lean:
    def __init__(self, data_dir=DATA, start='2025-12-01', end='2026-07-01'):
        ms = [m for m in bc._months(start, end) if os.path.exists(os.path.join(data_dir, 'binance_1s', f'{m}.npz'))]
        self.t0, t1 = bc.ts_of(start), bc.ts_of(end)
        self.n = n = t1 - self.t0
        c = np.full(n, np.nan)
        self.raw = {k: np.zeros(n, np.float32) for k in ('bq', 'sq', 'mb', 'ms', 'nb', 'ns')}
        h = np.full(n, np.nan, np.float32); l = np.full(n, np.nan, np.float32)
        for m in ms:
            z = np.load(os.path.join(data_dir, 'binance_1s', f'{m}.npz'))
            t = z['t']; keep = (t >= self.t0) & (t < t1); i = t[keep] - self.t0
            c[i] = z['c'][keep]
            for k in self.raw:
                self.raw[k][i] = z[k][keep]
            hh = z['h'][keep]; ll = z['l'][keep]
            h[i] = np.where(hh == 0, np.nan, hh); l[i] = np.where(ll == 0, np.nan, ll)
            del z
        self.c = pd.Series(c).ffill().bfill().to_numpy()
        self.h, self.l = h, l
        nm = n // 60
        mc = self.c[np.arange(1, nm + 1) * 60 - 1]
        mv = pd.Series(np.r_[np.nan, np.abs(np.diff(mc))]).rolling(60, min_periods=30).mean().to_numpy()
        sm = np.arange(n) // 60 - 1
        self.vol = np.where(sm >= 0, mv[np.clip(sm, 0, nm - 1)], np.nan)
        self.mv = mv  # per-minute vol (index minute m -> known after minute m ends)
        self.data_dir = data_dir
        self.metrics = self._metrics('metrics.csv.gz', start, end)
        self.eth = self._metrics('eth_metrics.csv.gz', start, end)
        fr = pd.read_csv(os.path.join(data_dir, 'funding.csv.gz')); fr['ts'] = fr.calc_time // 1000
        self.funding = fr[(fr.ts >= self.t0 - 3 * 86400) & (fr.ts < t1)].reset_index(drop=True)
        pr = pd.read_parquet(os.path.join(data_dir, 'premium_1m.parquet')); pr['known_ts'] = pr.open_time // 1000 + 60
        self.premium = pr[(pr.known_ts >= self.t0) & (pr.known_ts < t1)].reset_index(drop=True)
        dps = [pd.read_parquet(os.path.join(data_dir, 'bookdepth', f'{m}.parquet')) for m in ms]
        d = pd.concat(dps).sort_values('time'); d['ts'] = d.time.astype('datetime64[s]').astype('int64')
        self.depth = d[(d.ts >= self.t0) & (d.ts < t1)].reset_index(drop=True)
        tparts = [dict(np.load(os.path.join(data_dir, 'exness', f'{m}.npz'))) for m in ms]
        tk = {k: np.concatenate([p[k] for p in tparts]) for k in tparts[0]}
        del tparts
        o = np.argsort(tk['t'], kind='stable'); tk = {k: v[o] for k, v in tk.items()}
        keep = np.r_[True, np.diff(tk['t']) > 0] & (tk['t'] < t1)
        self.tk = {k: np.ascontiguousarray(v[keep]) for k, v in tk.items()}
        self.gaps = np.flatnonzero(np.diff(self.tk['t']) >= bc.GAP).astype(np.int64)

    _metrics = bc.Market._metrics


def trades(mk, sig, dirs, **kw):
    return bc.trades(mk, sig, dirs, **kw)


def acct(t, start='2026-01-01', end='2026-07-01', maxpos=1, risk=0.1):
    return bc.account(t, start, end, risk=risk, maxpos=maxpos)
