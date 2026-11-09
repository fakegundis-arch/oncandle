"""Version 3: lead's reproduction on Jan-Jun 2026, the pre-declared pick, and ONE run of every candidate on the
sealed periods.  usage (one candidate per process, memory):
  python3 -I scripts/btc_liq/agents3/final_v3.py build <agent> <candidate>     # Jan-Jun 2026 on the agents' data copy
  python3 -I scripts/btc_liq/agents3/final_v3.py pick                          # applies the BRIEF rule, writes the pick
  python3 -I scripts/btc_liq/agents3/final_v3.py test <agent> <candidate>      # Jul-Oct 2026 + Jan-Nov 2025, once
Long periods run in chunks (each chunk extends one day past its end so open trades exit normally; only entries inside
the chunk are kept); the account is computed on the joined trade list with btc_common.account."""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import btc_common as bc  # noqa: E402

ROOT = HERE.parents[2]
OUT = ROOT / "results" / "btc_liq" / "v3"
SANDBOX = "/home/user/btc_lab_data"
FULL = os.environ.get("BTC_FULL_VIEW", "")
# researchers' own luck-check verdicts (their reports): candidates eligible for the version-3 pick
LUCK_PASSED = {("exec", "exec_flushfade_4v"): True, ("exec", "exec_flushfade_3v_be"): False,
               ("flow", "flow_bigprint_oiup_30s"): True, ("flow", "flow_info_60s_wide"): False,
               ("oi", "OI_BIGMOVE"): False}
ALL = list(LUCK_PASSED) + [("lead", "v1_honest"), ("lead", "v2_honest")]
CHUNKS = {"build": [("2026-01-01", "2026-04-01"), ("2026-04-01", "2026-07-01")],
          "test": [("2026-07-01", "2026-11-01")],
          "exam": [("2025-01-01", "2025-06-01"), ("2025-06-01", "2025-12-01")]}


def load(agent):
    f = HERE / ("lead_baselines.py" if agent == "lead" else f"{agent}/strategy.py")
    sys.path.insert(0, str(f.parent))                       # numba caches remember the module name "strategy"
    spec = importlib.util.spec_from_file_location("lead_baselines" if agent == "lead" else "strategy", f)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def run(mod, p, data, chunks, stress):
    parts = []
    for a, b in chunks:
        b1 = str((pd.Timestamp(b) + pd.Timedelta(days=1)).date())
        t = mod.backtest(p, data, a, b1, stress=stress)
        parts.append(t[(t.entry_ts >= bc.ts_of(a)) & (t.entry_ts < bc.ts_of(b))])
    return pd.concat(parts).sort_values(["entry_ts", "sig_ts"]).reset_index(drop=True)


def summary(t, ts_, a, b, maxpos, halves=None):
    m = {f"{int(r * 100)}%": bc.account(t, a, b, risk=r, maxpos=maxpos) for r in (0.10, 0.05, 0.02, 0.01)}
    out = dict(result=m, stress=bc.account(ts_, a, b, maxpos=maxpos))
    if halves:
        out["halves_R"] = [bc.account(t, x, y, maxpos=maxpos)["R"] for x, y in halves]
    month = pd.to_datetime(t.entry_ts, unit="s").dt.strftime("%Y-%m")
    out["month_R"] = t.groupby(month).r.agg(["size", "sum"]).round(2).to_dict("index")
    return out


def build(agent, name):
    mod = load(agent)
    p = mod.CANDIDATES[name]
    t, ts_ = run(mod, p, SANDBOX, CHUNKS["build"], False), run(mod, p, SANDBOX, CHUNKS["build"], True)
    s = summary(t, ts_, "2026-01-01", "2026-07-01", p.get("maxpos", 1),
                halves=[("2026-01-01", "2026-04-01"), ("2026-04-01", "2026-07-01")])
    m = s["result"]["10%"]
    s["rule4"] = bool(m["n"] >= 40 and m["pf"] >= 1.3 and min(s["halves_R"]) > 0 and s["stress"]["pf"] >= 1.15
                      and m["dd"] > -0.35)
    s["params"] = {k: (None if isinstance(v, float) and v != v else v) for k, v in p.items()}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"build_{agent}_{name}.json").write_text(json.dumps(s, indent=1, default=float))
    print(agent, name, f"n {m['n']} R {m['R']:+.1f} PF {m['pf']:.2f} win {m['win']:.0%} ${m['final']:,.0f} "
          f"DD {m['dd']:.0%} maxlot {m['max_lot']:.2f} | halves {[round(x, 1) for x in s['halves_R']]} | "
          f"stress PF {s['stress']['pf']:.2f} | rule 4: {s['rule4']}")


def pick():
    rows = []
    for agent, name in LUCK_PASSED:
        s = json.loads((OUT / f"build_{agent}_{name}.json").read_text())
        rows.append(dict(agent=agent, name=name, final=s["result"]["10%"]["final"], rule4=s["rule4"],
                         luck=LUCK_PASSED[(agent, name)]))
    df = pd.DataFrame(rows)
    elig = df[df.rule4 & df.luck].sort_values("final", ascending=False)
    rule = "highest Jan-Jun 2026 balance at 10 % among candidates meeting rule 4 whose researcher's luck check passed"
    if not len(elig):
        elig, rule = df[df.rule4].sort_values("final", ascending=False), rule + " (none: luck condition dropped)"
    v3 = elig.iloc[0]
    out = dict(rule=rule, version3=dict(agent=v3.agent, name=v3["name"]), table=df.to_dict("records"))
    (OUT / "pick.json").write_text(json.dumps(out, indent=1, default=str))
    print(df.to_string(index=False), "\nVERSION 3:", v3.agent, v3["name"])


def test(agent, name):
    if not FULL:
        raise SystemExit("set BTC_FULL_VIEW to the folder that holds all months")
    f = OUT / f"test_{agent}_{name}.json"
    if f.exists():
        raise SystemExit("already run once: " + str(f))
    mod = load(agent)
    p = mod.CANDIDATES[name]
    res = {}
    for per, (a, b) in {"test": ("2026-07-01", "2026-11-01"), "exam": ("2025-01-01", "2025-12-01")}.items():
        t, ts_ = run(mod, p, FULL, CHUNKS[per], False), run(mod, p, FULL, CHUNKS[per], True)
        res[per] = summary(t, ts_, a, b, p.get("maxpos", 1))
        res[per]["trades"] = t.to_dict("records")
        m = res[per]["result"]["10%"]
        print(agent, name, per, f"n {m['n']} R {m['R']:+.1f} PF {m['pf']:.2f} win {m['win']:.0%} ${m['final']:,.0f} "
              f"DD {m['dd']:.0%} | 2% ${res[per]['result']['2%']['final']:,.0f} | stress PF {res[per]['stress']['pf']:.2f}",
              flush=True)
    f.write_text(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    cmd = sys.argv[1]
    {"build": lambda: build(*sys.argv[2:4]), "pick": pick, "test": lambda: test(*sys.argv[2:4])}[cmd]()
