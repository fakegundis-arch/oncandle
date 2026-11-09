"""lean loader + helpers for the search (same semantics as btc_common.Market, less memory)."""
import os, sys
import numpy as np, pandas as pd, numba as nb
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import btc_common as bc

DATA = '/home/user/btc_lab_data'


@nb.njit(cache=True)
def _ffill_bfill(c):
    last = np.nan
    for i in range(len(c)):
        if np.isnan(c[i]):
            c[i] = last
        else:
            last = c[i]
    first = np.nan
    for i in range(len(c)):
        if not np.isnan(c[i]):
            first = c[i]
            break
    for i in range(len(c)):
        if np.isnan(c[i]):
            c[i] = first
        else:
            break


class Lean:
    def __init__(self, data_dir=DATA, start='2025-12-01', end='2026-07-01', exness=True):
        ms = [m for m in bc._months(start, end) if os.path.exists(os.path.join(data_dir, 'binance_1s', f'{m}.npz'))]
        self.t0, t1 = bc.ts_of(start), bc.ts_of(end)
        self.n = n = t1 - self.t0
        c = np.full(n, np.nan)
        self.raw = {k: np.zeros(n, np.float32) for k in ('bq', 'sq', 'mb', 'ms', 'nb', 'ns')}
        for m in ms:
            z = np.load(os.path.join(data_dir, 'binance_1s', f'{m}.npz'))
            t = z['t']; keep = (t >= self.t0) & (t < t1); i = t[keep] - self.t0
            c[i] = z['c'][keep]
            for k in self.raw:
                self.raw[k][i] = z[k][keep]
            del z, t, keep, i
        _ffill_bfill(c)
        self.c = c
        nm = n // 60
        mc = self.c[np.arange(1, nm + 1) * 60 - 1]
        mv = pd.Series(np.r_[np.nan, np.abs(np.diff(mc))]).rolling(60, min_periods=30).mean().to_numpy()
        self.mv = mv
        vv = np.r_[np.full(60, np.nan), np.repeat(mv, 60)]
        self.vol = np.full(n, np.nan); m_ = min(n, len(vv)); self.vol[:m_] = vv[:m_]
        if n > len(vv): self.vol[len(vv):] = mv[-1]
        del vv
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
        if exness:
            files = [np.load(os.path.join(data_dir, 'exness', f'{m}.npz')) for m in ms]
            orders = [np.argsort(f['t'], kind='stable') for f in files]
            tot = sum(len(o) for o in orders)
            keys = [k for k in files[0].files if k != 'n']
            tk = {}
            for k in keys:
                a = np.empty(tot, files[0][k].dtype); off = 0
                for f, o in zip(files, orders):
                    a[off:off + len(o)] = f[k][o]; off += len(o)
                tk[k] = a
            assert np.all(np.diff(tk['t']) >= 0)
            keep = np.r_[True, np.diff(tk['t']) > 0] & (tk['t'] < t1)
            for k in keys:
                tk[k] = np.ascontiguousarray(tk[k][keep])
            self.tk = tk
            self.gaps = np.flatnonzero(np.diff(self.tk['t']) >= bc.GAP).astype(np.int64)

    _metrics = bc.Market._metrics


def acct(t, start='2026-01-01', end='2026-07-01', maxpos=1, risk=0.1):
    return bc.account(t, start, end, risk=risk, maxpos=maxpos)
