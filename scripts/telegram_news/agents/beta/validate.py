from lab import *
import time
rng = np.random.default_rng(0)
for inst in ['gold', 'nasdaq']:
    I = Inst(inst)
    tk = I.tk
    tps = np.array([0.5, 1.0, 2.0, 3.0, np.inf])
    holds = np.array([5, 30, 120, 600, 3600, 0], np.int64)
    bad = 0; cnt = 0
    t0 = time.time()
    for it in range(400):
        ts = int(rng.integers(I.t[0] + 1000, I.t[-1] - 100000))
        d = int(rng.choice([-1, 1]))
        stress = bool(rng.random() < 0.3)
        e = C.market_entry(tk, ts, d, stress=stress)
        if e is None:
            continue
        j, fill = e
        sdist = float(rng.choice([0.3, 1.0, 3.0, 8.0])) * (1 if inst == 'gold' else 8)
        be = float(rng.choice([-1, 0.5, 1.0, 2.0])); tr = float(rng.choice([-1, -1, 0.5, 1.0, 2.0]))
        out_r = np.zeros((len(tps), len(holds))); out_x = np.zeros((len(tps), len(holds)), np.int64)
        exit_multi(*args(I), j, fill, d, sdist, be, tr, tps, holds, stress, out_r, out_x)
        for q, tp in enumerate(tps):
            for h, ho in enumerate(holds):
                if ho == 0 and (be >= 0 or tr >= 0):
                    continue  # slow python loop to next close
                k, r, sd = C.exit_trade(tk, j, fill, d, sdist, None if np.isinf(tp) else tp,
                                        None if ho == 0 else int(ho), None if be < 0 else be, None if tr < 0 else tr,
                                        stress=stress)
                cnt += 1
                if k != out_x[q, h] or abs(r - out_r[q, h]) > 1e-9:
                    bad += 1
                    if bad < 5:
                        print('MISMATCH', inst, ts, d, sdist, be, tr, tp, ho, k, r, out_x[q, h], out_r[q, h])
    print(inst, 'exit checks', cnt, 'bad', bad, time.time() - t0)
    # pending
    bad = 0; cnt = 0
    for it in range(1500):
        ts = int(rng.integers(I.t[0] + 1000, I.t[-1] - 100000))
        i0 = C.bar_at(tk, ts)
        if i0 is None:
            continue
        m = (I.af[i0] + I.bf[i0]) / 2
        dist = float(rng.choice([0.1, 0.5, 2.0])) * (1 if inst == 'gold' else 8)
        kind = int(rng.integers(0, 2)); stress = bool(rng.random() < 0.3)
        exp = int(rng.choice([10, 60, 600]))
        mode = int(rng.integers(0, 3))
        if kind == 0:
            bp, sp_ = m + dist, m - dist
        else:
            bp, sp_ = m - dist, m + dist
        if mode == 1: sp_ = np.nan
        if mode == 2: bp = np.nan
        orders = []
        if not np.isnan(bp): orders.append(('stop' if kind == 0 else 'limit', 1, bp))
        if not np.isnan(sp_): orders.append(('stop' if kind == 0 else 'limit', -1, sp_))
        ref = C.pending_entry(tk, i0, orders, exp, stress=stress)
        x, dd_, fl = pending_scan(*pargs(I), i0, bp, sp_, kind, exp, stress)
        cnt += 1
        if ref is None:
            if x != -1: bad += 1; print('P1', ref, x)
        else:
            jj, legs = ref
            if len(legs) == 2:
                if not (x == jj and dd_ == 0): bad += 1; print('P2', ref, x, dd_)
            elif not (x == jj and dd_ == legs[0][0] and abs(fl - legs[0][1]) < 1e-9):
                bad += 1; print('P3', ref, x, dd_, fl)
    print(inst, 'pending checks', cnt, 'bad', bad)
    # account
    n = 300
    e = np.sort(rng.integers(0, 10**6, n)); x = e + rng.integers(1, 20000, n)
    tr = pd.DataFrame(dict(entry_ts=e, exit_ts=x, r=rng.normal(0.1, 1.5, n)))
    a = C.account(tr); b = account_df(tr)
    print('account', a['final'], b[0], a['dd'], b[1], a['taken'], b[2])
    del I; C._TK.clear()
