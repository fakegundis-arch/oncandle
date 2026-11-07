"""Telegram news bot: FinancialJuice + Walter Bloomberg headlines traded on gold and Nasdaq.  PROTOCOL (fixed before
any result was computed, Nov 7 2026) and the backtest engine.

DATA
  * Posts: @financialjuice and @WalterBloomberg public Telegram channels (tg_history.py), post time to the second.
  * Prices: Exness tick history (exness_ticks.py), XAUUSDm (gold) and USTECm (Nasdaq), one-second first / last / min /
    max of bid and ask - the broker's REAL spreads, including their widening on news.
  * BUILD on Jan 1 - Jun 30 2026 only (build() refuses later posts).  TEST once on Jul 1 - Oct 31 2026 with
    final_test() (refuses a second run).  Note: the earlier speed study (results/telegram_news/README.md) already
    looked at Sep 15 - Oct 15 price moves after these channels' posts, so the test months are not fully pristine.

TRADABLE POST (fixed rules, all known at post time)
  1. from either channel; not a scheduled data release or a preview (DATA regex);
  2. not from 2 min before to 15 min after a high / medium impact calendar event (data/calendar/ff_calendar.csv), or
     60 min after the start of a speech / testimony / press conference (fix of Nov 7, see below);
  3. the first post of its story: no post of either channel sharing >= 3 distinctive words (>= 50 % of the smaller
     set) in the previous 20 minutes;
  4. matches a topic: GEO (war, attacks, Iran / Israel / Russia / Ukraine / Taiwan, Hormuz ...), ENERGY (oil, OPEC,
     refineries ...), FED (Fed officials, rate hike / cut ...), TRADE (tariffs, sanctions, export controls ...),
     POLITICS (Trump, White House, Treasury officials ...), CHINA;
  5. the instrument quotes within 10 s of the entry time.

ENTRY / EXIT
  * The bot sees the post LAT = 2 s after its time and sends a market order: a long fills at the ASK of the first tick
    at / after that second, a short at the BID.  Stress test: LAT = 5 s plus one spread of extra slippage.
  * Direction families:  MOM  = sign of the mid move from (post - L s) to the entry, |move| >= k x vol;  FADE = -MOM;
    LEX = the headline's word direction (LEXICON below: escalation -> gold up / Nasdaq down, de-escalation -> the
    opposite, hawkish Fed -> both down, dovish Fed -> both up, trade escalation -> gold up / Nasdaq down, trade
    de-escalation -> the opposite; conflicting or no words -> no trade);  LEXMOM = LEX only when MOM (k = 0, L = 30)
    agrees.  vol = median |mid(t) - mid(t - 60 s)| over the 2 hours before the post (one sample per minute).
  * Stop = m x vol from the fill (at least 3 x the spread at entry), target = r x stop (r = 0: none), time exit H s
    after the fill.  Stop before target within a second; a gap through a level fills at the second's first price;
    checks start the second after the fill.  Longs exit on the bid, shorts on the ask.
  * One position per instrument at a time (a post while a trade is open is skipped).  $1,000, 10 % of equity risked per
    trade (compounding).  Gold and Nasdaq are separate strategies.
  * Knobs (searched on Jan-Jun): family, L in {10, 30, 60}, k in {0, 0.5, 1, 2}, H in {60, 120, 300, 900, 1800},
    m in {2, 4, 8}, r in {0, 1, 2}, topics in {ALL, GEO+ENERGY, FED, TRADE+POLITICS+CHINA}.

RULES
  * Jan-Jun pass (per instrument): >= 40 trades, PF >= 1.3, R > 0 in Jan-Mar and in Apr-Jun, PF >= 1.15 under the
    stress test, max drawdown at 10 % better than -35 %.
  * Pick (per instrument): among passing configs the one with the highest share of passing neighbours (one knob moved
    one step); ties -> shallower drawdown -> higher R.  No passing config -> that instrument is not traded.
  * Jul-Oct success (per instrument, stated in advance): >= 20 trades, R > 0, PF >= 1.3, max drawdown better than -35 %.

FIX (Nov 7, before any Jul-Oct result): the first Jan-Jun grid had rule 2 inverted in code (it dropped posts from 15
min BEFORE to 2 min after each event, so FOMC statement lines and other scheduled-event posts were traded).  Fixed;
speeches / press conferences now block 60 min; daily rate publications (effective fed funds, SOFR, reverse repo) count
as scheduled data.  The grid was re-run on Jan-Jun; the first run's picks were discarded.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HIST = ROOT / "data/telegram/history"
TICKS = ROOT / "data/ticks_exness"
OUT = ROOT / "results/telegram_news"
BUILD = ("2026-01-01", "2026-07-01")
BUILD_Q = {"jan-mar": ("2026-01-01", "2026-04-01"), "apr-jun": ("2026-04-01", "2026-07-01")}
TEST = ("2026-07-01", "2026-11-01")
SYMS = {"gold": "XAUUSDm", "nasdaq": "USTECm"}
RISK = 0.10
LAT, LAT_STRESS = 2, 5
GRID = dict(fam=["MOM", "FADE", "LEX", "LEXMOM"], L=[10, 30, 60], k=[0.0, 0.5, 1.0, 2.0], H=[60, 120, 300, 900, 1800],
            m=[2, 4, 8], r=[0, 1, 2], topics=["ALL", "GEO+ENERGY", "FED", "TRADE+POLITICS+CHINA"])

DATA = re.compile(r"ACTUAL|\bEST\.|\(EST|FORECAST|CONSENSUS|PREVIOUS|\bPREV\b|WATCH LIVE|\bPMI\b|MORTGAGE|BUYBACK|"
                  r"AUCTION|INVENTOR|CALENDAR|PREVIEW|AHEAD OF|COMING UP|DUE AT|DUE OUT|EFFECTIVE FED FUNDS|"
                  r"\bSOFR\b|REVERSE REPO|\bRRP\b", re.I)
def W(*terms: str) -> str:
    """Whole-word alternation; a term ending in '*' is a word START (e.g. ESCALAT* matches ESCALATION)."""
    return "|".join(rf"\b{t[:-1]}" if t.endswith("*") else rf"\b{t}\b" for t in terms)


TOPIC = {
    "GEO": W("ATTACK*", "STRIKE*", "MISSILE*", "DRONE*", "EXPLOSION*", "BLAST*", "KILLED", "WAR", "WARS", "TROOPS",
             "MILITARY", "INVASION", "INVADE*", "SHOT DOWN", "BOMB*", "HOSTAGE*", "HEZBOLLAH", "HAMAS", "HOUTHI*",
             "HORMUZ", "TANKER*", "NAVY", "NAVAL", "AIRSTRIKE*", "RETALIAT*", "ESCALAT*", "CEASEFIRE", "TRUCE", "PEACE",
             "NUCLEAR", "IRAN*", "ISRAEL*", "RUSSIA*", "UKRAIN*", "TAIWAN*", "NORTH KOREA*", "PENTAGON", "NATO"),
    "ENERGY": W("OIL", "OPEC*", "CRUDE", "REFINER*", "PIPELINE*", "BARREL*", "DIESEL", "GASOLINE", "NATURAL GAS", "LNG",
                "SPR", "IEA"),
    "FED": W("FED", "FED'S", "FOMC", "POWELL", "WARSH", "WALLER", "BOWMAN", "BARR", "GOOLSBEE", "WILLIAMS", "LOGAN",
             "HAMMACK", "MUSALEM", "KASHKARI", "DALY", "JEFFERSON", "COOK", "MIRAN", "RATE HIKE*", "RATE CUT*",
             "HAWKISH", "DOVISH"),
    "TRADE": W("TARIFF*", "TRADE DEAL*", "TRADE WAR*", "TRADE TALKS", "EXPORT CONTROL*", "SANCTION*", "DUTIES", "LEVY",
               "LEVIES"),
    "POLITICS": W("TRUMP*", "WHITE HOUSE", "BESSENT*", "LUTNICK*", "GREER*", "VANCE*", "RUBIO*", "TREASURY SEC*"),
    "CHINA": W("CHINA*", "CHINESE", "XI", "XI'S", "BEIJING"),
}
TOPICS = {"ALL": list(TOPIC), "GEO+ENERGY": ["GEO", "ENERGY"], "FED": ["FED"],
          "TRADE+POLITICS+CHINA": ["TRADE", "POLITICS", "CHINA"]}
# LEXICON: (regex, gold direction, nasdaq direction)
LEXICON = [
    (W("ATTACK*", "AIRSTRIKE*", "STRIKES ON", "STRIKES AGAINST", "STRIKE ON", "STRIKE AGAINST", "MISSILE*",
       "DRONE STRIKE*", "EXPLOSION*", "BLAST*", "KILLED", "SHOT DOWN", "BOMB*", "INVADE*", "INVASION", "ESCALAT*",
       "RETALIAT*", "DECLARES WAR", "DECLARED WAR", "CLOSE THE STRAIT", "CLOSES THE STRAIT", "CLOSED THE STRAIT",
       "CLOSE HORMUZ", "CLOSES HORMUZ", "SEIZE*", "EVACUAT*", "STATE OF EMERGENCY", "TROOPS TO", "TROOPS INTO",
       "MOBILIZ*", "NUCLEAR TEST*", "THREATEN*"), +1, -1),                                     # escalation
    (W("CEASEFIRE", "TRUCE", "PEACE DEAL", "PEACE AGREEMENT", "PEACE TALKS", "PEACE PLAN", "DE-ESCALAT*", "DEESCALAT*",
       "WITHDRAW*", "HOSTAGES RELEASED", "HOSTAGE RELEASED", "HOSTAGES FREED", "PROGRESS IN TALKS",
       "REACHED AGREEMENT", "REACHED AN AGREEMENT", "SIGNED A DEAL", "SIGNED AN AGREEMENT", "SIGNED DEAL", "REOPEN*"),
     -1, +1),                                                                                   # de-escalation
    (W("RATE HIKE", "RATE HIKES", "HIKE RATES", "HAWKISH", "HIGHER FOR LONGER", "NO CUTS", "NO RATE CUTS", "TIGHTEN*",
       "INFLATION TOO HIGH", "INFLATION IS TOO HIGH", "INFLATION CONCERN*", "MORE HIKES"), -1, -1),          # hawkish
    (W("RATE CUT", "RATE CUTS", "CUT RATES", "DOVISH", "EASING", "LOWER RATES", "PAUSE HIKES", "PAUSE IN HIKES"),
     +1, +1),                                                                                   # dovish
    (W("IMPOSE TARIFF*", "IMPOSES TARIFF*", "IMPOSED TARIFF*", "IMPOSE NEW TARIFF*", "IMPOSES NEW TARIFF*",
       "RAISE TARIFF*", "RAISES TARIFF*", "RAISED TARIFF*", "NEW TARIFF*", "TARIFFS OF", "TARIFFS ON", "TARIFF OF",
       "TARIFF ON", "EXPORT CONTROL*", "NEW SANCTIONS", "TRADE WAR", "RETALIATORY TARIFF*"), +1, -1),  # trade escalation
    (W("TRADE DEAL", "TARIFF RELIEF", "TARIFF PAUSE", "TARIFF CUT*", "TARIFF EXEMPTION*", "LIFT TARIFF*", "LIFTS TARIFF*",
       "LIFTED TARIFF*", "LIFT SANCTION*", "LIFTS SANCTION*", "LIFTED SANCTION*", "LIFTS THE SANCTION*",
       "ROLL BACK TARIFF*", "ROLLS BACK TARIFF*", "ROLLED BACK TARIFF*", "SANCTIONS RELIEF", "SANCTION RELIEF",
       "EASE TARIFF*", "EASES TARIFF*", "EASED TARIFF*", "EASE SANCTION*", "EASES SANCTION*", "EASED SANCTION*"),
     -1, +1),                                                                                   # trade de-escalation
]
STOP = set("""THE AND FOR WITH THAT THIS FROM WILL HAVE HAS ARE WAS WERE BEEN NOT BUT ALL ITS OUR ABOUT AFTER OVER INTO
THAN THEIR THEY THEM WHO WHAT WHEN WHERE WHICH WOULD COULD SHOULD MORE MOST VERY ALSO JUST ONLY SOME ANY CAN MAY NEW NOW
ONE TWO SAYS SAID SAY BREAKING REPORT REPORTS REPORTED NEWS ALERT UPDATE LIVE READ WATCH HERE THERE BEING DOES DID DONE
GET GOT HIS HER HIM SHE YOU YOUR SINCE UNTIL UPON PER VIA WALTERBLOOMBERG MACRO FJ HTTPS HTTP COM WWW TODAY WEEK MONTH
YEAR TIME PEOPLE OFFICIAL OFFICIALS SOURCE SOURCES ACCORDING AMID AHEAD AGAINST BETWEEN DURING WITHOUT ACROSS AROUND
BEFORE STILL EVEN MUCH MANY SUCH OTHER EACH BOTH FEW WELL BACK MADE MAKE TAKE GIVE STATES STATE UNITED""".split())


# ------------------------------------------------------------------------------------------------------------- posts
def clean(text: str) -> str:
    t = re.sub(r"\|FJ\s*$|\(@WalterBloomberg\)|\$MACRO|[❗‼️🔴⚠️]", " ", text)
    return re.sub(r"\s+", " ", t).strip()


def tokens(text: str) -> set[str]:
    w = re.findall(r"[A-Z][A-Z'\-]{2,}|\d+(?:[.,]\d+)?%?", text.upper())
    return {x.strip("'-") for x in w if x.strip("'-") not in STOP and not re.fullmatch(r"20\d\d", x)}


def load_posts(a: str, b: str) -> pd.DataFrame:
    rows = []
    for f in sorted(HIST.glob("financialjuice*.jsonl")) + [HIST / "WalterBloomberg.jsonl"]:
        ch = "FJ" if f.name.startswith("financialjuice") else "WB"
        for line in f.read_text().splitlines():
            if line.strip():
                p = json.loads(line)
                rows.append((ch, p["id"], p["time"], p["text"]))
    d = pd.DataFrame(rows, columns=["ch", "id", "time", "text"]).drop_duplicates(["ch", "id"])
    d["t"] = pd.to_datetime(d.time, utc=True)
    d = d[(d.t >= pd.Timestamp(a, tz="UTC")) & (d.t < pd.Timestamp(b, tz="UTC")) & (d.text.str.len() > 0)]
    d = d.sort_values(["t", "ch", "id"]).reset_index(drop=True)
    d["clean"] = d.text.map(clean)
    d["tok"] = d.clean.map(tokens)
    return d


def scheduled_times() -> tuple[np.ndarray, np.ndarray]:
    """(event times, seconds after each event during which posts are not tradable): 15 min after a release, 60 min
    after the start of a speech / testimony / press conference (they run about an hour)."""
    c = pd.read_csv(ROOT / "data/calendar/ff_calendar.csv", parse_dates=["time_utc"])
    c = c[c.impact.isin(["high", "medium"])].sort_values("time_utc")
    t = c.time_utc.values.astype("datetime64[s]").astype(np.int64)
    after = np.where(c.name.str.contains("Speaks|Press Conference|Testifies|Hearing", regex=True), 3600, 900)
    return t, after


def topics_of(text: str) -> list[str]:
    u = text.upper()
    return [k for k, rx in TOPIC.items() if re.search(rx, u)]


def lex_dir(text: str) -> tuple[int, int]:
    u = text.upper()
    hits = [(g, n) for rx, g, n in LEXICON if re.search(rx, u)]
    if not hits:
        return 0, 0
    g = {h[0] for h in hits}
    n = {h[1] for h in hits}
    return (g.pop() if len(g) == 1 else 0), (n.pop() if len(n) == 1 else 0)


def tradable(posts: pd.DataFrame) -> pd.DataFrame:
    """Rules 1-4 of the protocol (rule 5, the quote check, is applied in the engine)."""
    sched, after = scheduled_times()
    ts = posts.t.values.astype("datetime64[s]").astype(np.int64)
    keep, recent = [], []
    for i, p in enumerate(posts.itertuples()):
        t = ts[i]
        recent = [(tt, tok) for tt, tok in recent if t - tt <= 1200]
        dup = any(len(p.tok & tok) >= 3 and len(p.tok & tok) / max(1, min(len(p.tok), len(tok))) >= 0.5
                  for _, tok in recent)
        recent.append((t, p.tok))
        if dup or DATA.search(p.clean):
            continue
        j = np.searchsorted(sched, t)
        lo = max(0, j - 40)
        if any(-120 <= t - s <= a for s, a in zip(sched[lo: j + 3], after[lo: j + 3])):   # 2 min before .. after
            continue
        tp = topics_of(p.clean)
        if not tp:
            continue
        keep.append(i)
    out = posts.iloc[keep].copy()
    out["topics"] = out.clean.map(topics_of)
    out["lex_gold"], out["lex_nasdaq"] = zip(*out.clean.map(lex_dir)) if len(out) else ([], [])
    return out.reset_index(drop=True)


# ------------------------------------------------------------------------------------------------------------- ticks
_TK: dict = {}


def ticks(inst: str) -> dict:
    """One-second bars of the instrument for all months on disk (concatenated)."""
    if inst not in _TK:
        parts = [dict(np.load(f)) for f in sorted((TICKS / SYMS[inst]).glob("*.npz"))]
        _TK[inst] = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    return _TK[inst]


def mid_at(tk: dict, t: int) -> float:
    """mid of the last second at or before t (nan if older than 60 s)."""
    i = np.searchsorted(tk["t"], t, side="right") - 1
    if i < 0 or t - tk["t"][i] > 60:
        return np.nan
    return 0.5 * (tk["bid_last"][i] + tk["ask_last"][i])


def vol60(tk: dict, t: int) -> float:
    pts = t - 60 * np.arange(1, 121)
    i = np.searchsorted(tk["t"], pts, side="right") - 1
    i = np.clip(i, 0, None)
    m = 0.5 * (tk["bid_last"][i] + tk["ask_last"][i])
    d = np.abs(np.diff(m[::-1]))
    d = d[d > 0]
    return float(np.median(d)) if len(d) >= 20 else np.nan


def simulate(tk: dict, t_entry: int, d: int, sd: float, tp_r: float, H: int, slip: float):
    """Market order at the first tick at / after t_entry; -> (fill_time, exit_time, r) or None (no quote within 10 s)."""
    T = tk["t"]
    i = np.searchsorted(T, t_entry)
    if i >= len(T) or T[i] - t_entry > 10:
        return None
    spread = tk["ask_first"][i] - tk["bid_first"][i]
    fill = (tk["ask_first"][i] + slip) if d > 0 else (tk["bid_first"][i] - slip)
    sd = max(sd, 3 * spread)
    sl = fill - d * sd
    tp = fill + d * tp_r * sd if tp_r > 0 else None
    end = np.searchsorted(T, T[i] + H)
    j0, j1 = i + 1, min(end, len(T))
    if d > 0:
        first, lo, hi = tk["bid_first"][j0:j1], tk["bid_min"][j0:j1], tk["bid_max"][j0:j1]
        g_sl, h_sl = first <= sl, lo <= sl
        g_tp = (first >= tp) if tp is not None else np.zeros(len(first), bool)
        h_tp = (hi >= tp) if tp is not None else np.zeros(len(first), bool)
    else:
        first, lo, hi = tk["ask_first"][j0:j1], tk["ask_min"][j0:j1], tk["ask_max"][j0:j1]
        g_sl, h_sl = first >= sl, hi >= sl
        g_tp = (first <= tp) if tp is not None else np.zeros(len(first), bool)
        h_tp = (lo <= tp) if tp is not None else np.zeros(len(first), bool)
    hit = g_sl | h_sl | g_tp | h_tp
    if hit.any():
        k = int(np.argmax(hit))
        px = first[k] if (g_sl[k] or g_tp[k]) else (sl if h_sl[k] else tp)
        return int(T[i]), int(T[j0 + k]), d * (px - fill) / sd
    if j1 >= len(T):
        return None
    px = tk["bid_first"][j1] if d > 0 else tk["ask_first"][j1]
    return int(T[i]), int(T[j1]), d * (px - fill) / sd


# ---------------------------------------------------------------------------------------------------- strategy
def features(tp: pd.DataFrame, inst: str, lat: int) -> pd.DataFrame:
    """Per tradable post: price moves needed by the direction families (known at entry time)."""
    tk = ticks(inst)
    rows = []
    for p in tp.itertuples():
        t0 = int(p.t.timestamp())
        te = t0 + lat
        me = mid_at(tk, te)
        rec = dict(t_post=t0, t_entry=te, vol=vol60(tk, t0), lex=p.lex_gold if inst == "gold" else p.lex_nasdaq,
                   topics=p.topics)
        for L in GRID["L"]:
            rec[f"mv{L}"] = me - mid_at(tk, t0 - L)
        rows.append(rec)
    return pd.DataFrame(rows)


def direction(f, cfg) -> int:
    fam = cfg["fam"]
    if fam in ("MOM", "FADE"):
        mv = getattr(f, f"mv{cfg['L']}")
        if not np.isfinite(mv) or mv == 0 or abs(mv) < cfg["k"] * f.vol:
            return 0
        return int(np.sign(mv)) * (1 if fam == "MOM" else -1)
    if fam == "LEX":
        return int(f.lex)
    if fam == "LEXMOM":
        mv = f.mv30
        return int(f.lex) if f.lex != 0 and np.isfinite(mv) and np.sign(mv) == f.lex else 0
    raise ValueError(fam)


def run(feat: pd.DataFrame, inst: str, cfg: dict, stress: bool = False) -> pd.DataFrame:
    tk = ticks(inst)
    allowed = set(TOPICS[cfg["topics"]])
    rows, busy = [], -1
    for f in feat.itertuples():
        if f.t_post <= busy or not (set(f.topics) & allowed) or not np.isfinite(f.vol) or f.vol <= 0:
            continue
        d = direction(f, cfg)
        if d == 0:
            continue
        te = f.t_entry + (LAT_STRESS - LAT if stress else 0)
        i = np.searchsorted(tk["t"], te)
        slip = (tk["ask_first"][i] - tk["bid_first"][i]) if (stress and i < len(tk["t"])) else 0.0
        res = simulate(tk, te, d, cfg["m"] * f.vol, cfg["r"], cfg["H"], slip)
        if res is None:
            continue
        ft, xt, r = res
        busy = xt
        rows.append(dict(entry_time=pd.Timestamp(ft, unit="s"), exit_time=pd.Timestamp(xt, unit="s"), dir=d, r=r))
    return pd.DataFrame(rows, columns=["entry_time", "exit_time", "dir", "r"])


def metrics(t: pd.DataFrame, a: str, b: str, risk: float = RISK) -> dict:
    t = t[(t.entry_time >= a) & (t.entry_time < b)].sort_values("entry_time") if len(t) else t
    r = t.r.to_numpy(float) if len(t) else np.zeros(0)
    eq = np.cumprod(1 + risk * r) if len(r) else np.array([1.0])
    gl, gw = -r[r < 0].sum(), r[r > 0].sum()
    streak = cur = 0
    for x in r:
        cur = cur + 1 if x < 0 else 0
        streak = max(streak, cur)
    return dict(n=len(r), R=float(r.sum()), pf=float(gw / gl) if gl > 0 else (99.0 if gw > 0 else 0.0),
                win=float((r > 0).mean()) if len(r) else 0.0, usd=float(1000 * eq[-1]),
                dd=float((eq / np.maximum.accumulate(np.maximum(eq, 1.0)) - 1).min()), max_losing_streak=streak)


def passes_build(t: pd.DataFrame, ts: pd.DataFrame) -> tuple[bool, dict]:
    m = metrics(t, *BUILD)
    q1, q2 = metrics(t, *BUILD_Q["jan-mar"]), metrics(t, *BUILD_Q["apr-jun"])
    ms = metrics(ts, *BUILD)
    chk = {"n>=40": m["n"] >= 40, "pf>=1.3": m["pf"] >= 1.3, "jan-mar R>0": q1["R"] > 0, "apr-jun R>0": q2["R"] > 0,
           "stress pf>=1.15": ms["pf"] >= 1.15, "dd>-35%": m["dd"] > -0.35}
    return all(chk.values()), dict(m, q1R=q1["R"], q2R=q2["R"], stress_pf=ms["pf"], stress_R=ms["R"], **chk)


def build_features(inst: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Jan-Jun only."""
    tp = tradable(load_posts(*BUILD))
    assert (tp.t < pd.Timestamp(BUILD[1], tz="UTC")).all()
    return tp, features(tp, inst, LAT)


def final_test(picks: dict, tag: str = "newsbot") -> dict:
    """ONE run on Jul-Oct 2026: picks = {inst: cfg}. Saves results/telegram_news/<tag>_test.json, refuses a second run."""
    f = OUT / f"{tag}_test.json"
    if f.exists():
        raise RuntimeError("final_test has already been run")
    tp = tradable(load_posts("2026-06-30", TEST[1]))          # one day of overlap for the story-first rule
    res = {}
    for inst, cfg in picks.items():
        feat = features(tp, inst, LAT)
        t, ts = run(feat, inst, cfg), run(feat, inst, cfg, stress=True)
        m, ms = metrics(t, *TEST), metrics(ts, *TEST)
        ok = m["n"] >= 20 and m["R"] > 0 and m["pf"] >= 1.3 and m["dd"] > -0.35
        res[inst] = dict(cfg=cfg, test=m, test_stress=ms, success=ok,
                         trades=t[(t.entry_time >= TEST[0]) & (t.entry_time < TEST[1])].astype(str).to_dict("records"))
    OUT.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(timespec="seconds"), results=res), indent=1,
                            default=str))
    return res
