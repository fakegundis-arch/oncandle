import numpy as np, numba as nb


@nb.njit(cache=True)
def bursts(c, vol, W, X, refr, lo, hi):
    out_s = []; out_d = []
    last = -10 ** 9
    for s in range(max(lo, W + 1), hi):
        v = vol[s]
        if not (v > 0):
            continue
        m = c[s - 1] - c[s - 1 - W]
        if abs(m) >= X * v and s - last >= refr:
            out_s.append(s); out_d.append(1 if m > 0 else -1); last = s
    return np.array(out_s, np.int64), np.array(out_d, np.int64)


@nb.njit(cache=True)
def stall(c, s0, d0, Q, maxwait):
    """after trigger (s0, d0): first second s where the d0-extreme of c over [s0-1, s-1] is older than Q s.
    -> s (decision second), extreme price, seconds since trigger"""
    n = len(s0)
    out = np.full(n, -1, np.int64); ext = np.zeros(n)
    for k in range(n):
        s = s0[k]; d = d0[k]
        best = c[s - 1]; tb = s - 1
        for x in range(s, min(s + maxwait, len(c))):
            # at decision second x we know c[x-1]
            p = c[x - 1]
            if d * (p - best) > 0:
                best = p; tb = x - 1
            if x - 1 - tb >= Q:
                out[k] = x; ext[k] = best
                break
    return out, ext
