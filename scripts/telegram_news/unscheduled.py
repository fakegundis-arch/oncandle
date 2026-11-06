"""Speed of Telegram channels on UNSCHEDULED news (Sep 15 - Nov 6 2026), Telegram posts only.

B. Stories: posts of different channels about the same story are grouped (same distinctive words within 20 minutes of
   the story's first post).  Stories starting near a scheduled calendar event (high / medium impact, 2 min before to
   15 min after) are dropped.  Per channel: how often it was FIRST and how far behind the first it was.
C. Market: for stories up to Oct 15 (price data end), NAS100 / XAUUSD M1 moves before and after the first post; the
   "market-moving" stories (a 15-min move after the first post of >= 2 x a normal 15-min move) get their own ranking.

usage: python3 -I scripts/telegram_news/unscheduled.py   (reads data/telegram/history, writes results/telegram_news/)"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
H = ROOT / "data/telegram/history"
OUT = ROOT / "results/telegram_news"
START, END = datetime(2026, 9, 15, tzinfo=timezone.utc), datetime(2026, 11, 7, tzinfo=timezone.utc)
CHANNELS = ["TreeNewsFeed", "BWEnews", "nwsmkr", "markettwits", "WalterBloomberg", "marketfeed", "financialjuice",
            "WatcherGuru", "unfolded", "insiderpaper", "disclosetv", "ClashReport", "IntelSlava", "osintdefender",
            "rnintel", "BRICSNews", "PolymarketIntel"]

STOP = set("""THE AND FOR WITH THAT THIS FROM WILL HAVE HAS ARE WAS WERE BEEN NOT BUT ALL ITS OUR ABOUT AFTER OVER INTO THAN
THEIR THEY THEM WHO WHAT WHEN WHERE WHICH WOULD COULD SHOULD MORE MOST VERY ALSO JUST ONLY SOME ANY CAN MAY NEW NOW ONE
TWO SAYS SAID SAY BREAKING REPORT REPORTS REPORTED NEWS ALERT UPDATE LIVE READ WATCH VIDEO JUSTIN MORE HERE THERE
BEING DOES DID DONE GET GOT HIS HER HIM SHE YOU YOUR WE'RE IT'S DON'T THAN THEN BECAUSE WHILE UNTIL UPON PER VIA
WALTERBLOOMBERG WATCHERGURU MACRO FJ HTTPS HTTP COM WWW TODAY YESTERDAY TOMORROW WEEK MONTH YEAR TIME TIMES PEOPLE
OFFICIAL OFFICIALS SOURCE SOURCES ACCORDING AMID AHEAD AGAINST BETWEEN DURING WITHOUT ACROSS AROUND BEFORE STILL
EVEN MUCH MANY SUCH OTHER EACH BOTH FEW WELL BACK MADE MAKE MAKING TAKE TAKES TOOK GIVE GIVEN STATES STATE UNITED""".split())
RU = {"ТРАМП": "TRUMP", "ПУТИН": "PUTIN", "СИ ЦЗИНЬПИН": "XI", "ЗЕЛЕНСК": "ZELENSKY", "НЕТАНЬЯХУ": "NETANYAHU",
      "ИРАН": "IRAN", "ИЗРАИЛ": "ISRAEL", "КИТА": "CHINA", "РОССИ": "RUSSIA", "УКРАИН": "UKRAINE", "США": "US",
      "ВЕНЕСУЭЛ": "VENEZUELA", "КАНАД": "CANADA", "МЕКСИК": "MEXICO", "ЯПОН": "JAPAN", "ИНДИ": "INDIA",
      "ЕВРОСОЮЗ": "EU", " ЕС ": "EU", "ТАЙВАН": "TAIWAN", "ГАЗ": "GAS", "НЕФТ": "OIL", "ЗОЛОТ": "GOLD",
      "ТАРИФ": "TARIFF", "ПОШЛИН": "TARIFF", "САНКЦИ": "SANCTIONS", "СДЕЛК": "DEAL", "ПЕРЕМИРИ": "CEASEFIRE",
      "УДАР": "STRIKE", "РАКЕТ": "MISSILE", "ОРМУЗ": "HORMUZ", "ТАНКЕР": "TANKER", "ФРС": "FED", "СТАВК": "RATE",
      "ЯДЕРН": "NUCLEAR", "ПЕРЕГОВОР": "TALKS", "ВОЙН": "WAR", "АТАК": "ATTACK", "ПЕНТАГОН": "PENTAGON",
      "БЕЛЫЙ ДОМ": "WHITE HOUSE", "ХУСИТ": "HOUTHI", "САУДОВ": "SAUDI", "ОПЕК": "OPEC", "БИТКОИН": "BITCOIN"}
CYR = re.compile(r"[А-ЯЁ]")


def tokens(text: str) -> set[str]:
    t = text.upper()
    extra = set()
    if CYR.search(t):                                     # Russian: map key entities to English
        for k, v in RU.items():
            if k in t:
                extra |= set(v.split())
    words = re.findall(r"[A-Z][A-Z'\-]{2,}|\d+(?:[.,]\d+)?%?", t)
    out = {w.strip("'-") for w in words if w.strip("'-") not in STOP and not re.fullmatch(r"20\d\d", w)}
    return {w for w in out if len(w) >= 3 or w.endswith("%")} | extra


def load_channels() -> dict[str, pd.DataFrame]:
    out = {}
    for ch in CHANNELS:
        f = H / f"{ch}.jsonl"
        if not f.exists():
            continue
        rows = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        d = pd.DataFrame(rows)
        if not len(d):
            continue
        d["t"] = pd.to_datetime(d.time, utc=True)
        d = d[(d.t >= START) & (d.t < END) & (d.text.str.len() > 0)].sort_values("t").reset_index(drop=True)
        d["tok"] = d.text.map(tokens)
        out[ch] = d
    return out


MARKET = re.compile(r"TARIFF|CHINA|\bXI\b|IRAN|ISRAEL|RUSSIA|PUTIN|UKRAINE|ZELENSKY|\bFED\b|POWELL|WARSH|RATES?\b|"
                    r"\bOIL\b|TRADE|DEAL|SANCTION|\bWAR\b|STRIKE|MILITARY|VENEZUELA|CANADA|MEXICO|EUROPE|\bEU\b|JAPAN|"
                    r"INDIA|STOCK|MARKET|GOLD|DOLLAR|\bTAX|SHUTDOWN|CHIP|SEMICONDUCTOR|NVIDIA|HORMUZ|NUCLEAR|"
                    r"CEASEFIRE|BOMB|ATTACK|TAIWAN|SAUDI|OPEC|CRYPTO|BITCOIN", re.I)


def scheduled_times() -> list[datetime]:
    c = pd.read_csv(ROOT / "data/calendar/ff_calendar.csv", parse_dates=["time_utc"])
    c = c[c.impact.isin(["high", "medium"])]
    ts = [t.tz_localize("UTC").to_pydatetime() for t in c.time_utc]
    wk = ROOT / "data/telegram/speedtest/ff_thisweek.json"
    if wk.exists():
        w = pd.DataFrame(json.load(open(wk)))
        w = w[w.impact.isin(["High", "Medium"])]
        ts += [pd.Timestamp(x).tz_convert("UTC").to_pydatetime() for x in w.date]
    return sorted(ts)


def stories(chans: dict[str, pd.DataFrame]) -> list[dict]:
    allp = pd.concat([d.assign(channel=ch) for ch, d in chans.items()], ignore_index=True)
    allp = allp[allp.tok.map(len) >= 3].sort_values("t").reset_index(drop=True)
    clusters, active = [], []
    for p in allp.itertuples():
        active = [c for c in active if p.t - c["t0"] <= timedelta(minutes=20)]
        best, bsc = None, 0.0
        for c in active:
            sh = len(p.tok & c["tok"])
            sc = sh / min(len(p.tok), len(c["tok"]))
            if sh >= 3 and sc >= 0.5 and sc > bsc:
                best, bsc = c, sc
        if best is None:
            c = {"t0": p.t, "tok": p.tok, "first": {}, "text": p.text[:140].replace("\n", " ")}
            clusters.append(c); active.append(c)
            best = c
        if p.channel not in best["first"]:
            best["first"][p.channel] = (p.t, p.text[:110].replace("\n", " "))
    sched = scheduled_times()
    out = []
    for c in clusters:
        if len(c["first"]) < 3:
            continue
        t0 = c["t0"].to_pydatetime()
        i = np.searchsorted(np.array(sched, dtype="datetime64[us]"), np.datetime64(t0.replace(tzinfo=None)))
        near = [s for s in sched[max(0, i - 3): i + 3] if timedelta(minutes=-15) <= t0 - s <= timedelta(minutes=2)
                or timedelta(minutes=-2) <= s - t0 <= timedelta(minutes=0)]
        if near:
            continue
        out.append(c)
    return out


def m1(sym: str) -> pd.DataFrame:
    import sys
    sys.path.insert(0, str(ROOT))
    from backtester import data as D
    m = D.load_csv(ROOT / "data" / f"{sym}_M1.csv")
    m = m[m.index >= "2026-09-01"]
    m.index = m.index.tz_localize("UTC")
    return m


def price_path(m: pd.DataFrame, t: datetime, offs=(-15, -5, 0, 1, 2, 5, 15, 30)) -> dict:
    """close of the minute bar at t + k minutes (the bar containing the post time for k = 0)."""
    out = {}
    base = pd.Timestamp(t).floor("min")
    for k in offs:
        i = m.index.searchsorted(base + pd.Timedelta(minutes=k), side="right") - 1
        out[k] = float(m.close.iloc[i]) if i >= 0 else np.nan
    return out


def channel_table(st: list[dict], chans, keep=None) -> pd.DataFrame:
    lag, firsts = defaultdict(list), defaultdict(int)
    for c in st:
        if keep is not None and c["t0"] not in keep:
            continue
        f0 = min(v[0] for v in c["first"].values())
        firsts[min(c["first"], key=lambda k: c["first"][k][0])] += 1
        for ch, (t, _) in c["first"].items():
            lag[ch].append((t - f0).total_seconds())
    rows = []
    for ch in chans:
        a = pd.Series(lag[ch], dtype=float)
        rows.append(dict(channel=ch, stories=len(a), first=firsts[ch], first_pct=round(100 * firsts[ch] / max(len(a), 1)),
                         median_behind_s=a.median(), within_30s_of_first=int((a <= 30).sum()),
                         within_60s=int((a <= 60).sum())))
    return pd.DataFrame(rows).sort_values(["first", "median_behind_s"], ascending=[False, True])


def main():
    chans = load_channels()
    print("posts: " + ", ".join(f"{c} {len(d)}" for c, d in chans.items()))
    st = stories(chans)
    B = channel_table(st, chans)
    srows = []
    for c in st:
        f = sorted(c["first"].items(), key=lambda kv: kv[1][0])
        srows.append(dict(t0=c["t0"], n_channels=len(f), first=f[0][0], text=c["text"],
                          order=" > ".join(f"{ch}+{int((t - f[0][1][0]).total_seconds())}s" for ch, (t, _) in f)))
    S = pd.DataFrame(srows)

    mk = {s: m1(s) for s in ("NAS100", "XAUUSD")}
    last = min(m.index[-1] for m in mk.values()).to_pydatetime()
    crow = []
    for r in S.itertuples():
        t0 = r.t0.to_pydatetime()
        if t0 > last - timedelta(minutes=35):
            continue
        rec = dict(t0=r.t0, text=r.text, order=r.order, first=r.first, n_channels=r.n_channels)
        for s, m in mk.items():
            pp = price_path(m, t0)
            day = m[(m.index >= r.t0 - pd.Timedelta(hours=24)) & (m.index < r.t0)]
            r15 = day.close.diff(15).abs().median() if len(day) > 100 else np.nan
            rec[f"{s}_before15"] = (pp[0] - pp[-15]) / r15
            rec[f"{s}_after15"] = (pp[15] - pp[0]) / r15
            rec[f"{s}_after30"] = (pp[30] - pp[0]) / r15
            rec[f"{s}_path"] = {k: round(v, 2) for k, v in pp.items()}
        crow.append(rec)
    C = pd.DataFrame(crow)
    big = C[(C.NAS100_after15.abs() >= 2) | (C.XAUUSD_after15.abs() >= 2)] if len(C) else C
    BB = channel_table(st, chans, keep=set(big.t0)) if len(big) else pd.DataFrame()

    OUT.mkdir(parents=True, exist_ok=True)
    S.to_csv(OUT / "unscheduled_stories.csv", index=False)
    C.to_csv(OUT / "unscheduled_market.csv", index=False)
    with open(OUT / "unscheduled_summary.txt", "w") as fh:
        fh.write(f"B. unscheduled stories posted by >= 3 channels: {len(S)}\n{B.to_string(index=False)}\n\n")
        fh.write(f"B2. market-moving stories only (Sep 15 - Oct 15; NAS100 or gold moved >= 2 x a normal 15-min move in "
                 f"the 15 min after the first post): {len(big)}\n{BB.to_string(index=False)}\n\n")
        for s in ("NAS100", "XAUUSD"):
            if not len(C):
                break
            c2 = C.assign(a=C[f"{s}_after15"].abs()).sort_values("a", ascending=False).head(12)
            fh.write(f"C. biggest {s} moves in the 15 min after the first post (units of a normal 15-min move)\n")
            for r in c2.itertuples():
                fh.write(f"  {r.t0:%Y-%m-%d %H:%M:%S} before {getattr(r, s + '_before15'):+.1f} after15 "
                         f"{getattr(r, s + '_after15'):+.1f} after30 {getattr(r, s + '_after30'):+.1f} | {r.text[:80]} | "
                         f"{r.order[:160]}\n")
            fh.write("\n")
    print((OUT / "unscheduled_summary.txt").read_text())


if __name__ == "__main__":
    main()
