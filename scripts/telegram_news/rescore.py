"""Re-score the stored windows (win_<channel>.json) with headline-only, language-aware matching (EN + RU).
usage: python3 -I scripts/telegram_news/rescore.py data/telegram/speedtest"""
import json, os, re, sys
from pathlib import Path
from datetime import datetime
import pandas as pd
sys.argv = ["x", os.path.abspath(sys.argv[1])]
ns = {"__file__": str(Path(__file__).with_name("speedtest.py"))}
exec(Path(__file__).with_name("speedtest.py").read_text().split("def main")[0], ns)
os.chdir(sys.argv[1])
KINDS, COUNTRY, events = ns["KINDS"], ns["COUNTRY"], ns["events"]
RU_KIND = {0: r"NON-?FARM|PAYROLL", 1: r"БЕЗРАБОТИЦ|ЗАНЯТОСТ|РАБОЧИХ МЕСТ", 2: r"ИНФЛЯЦИ|ИПЦ", 4: r"РОЗНИЧН", 9: r"ВВП",
           11: r"СТАВКА ФРС|ФРС", 12: r"БАНК АНГЛИИ|СТАВКА", 13: r"ЕЦБ|СТАВКА", 14: r"РБА|СТАВКА", 15: r"РБНЗ|СТАВКА",
           16: r"БАНК КАНАДЫ|СТАВКА", 17: r"ШНБ|СТАВКА", 18: r"PMI|ИНДЕКС"}
RU_CTY = {"USD": r"США|ФРС", "GBP": r"БРИТАН|АНГЛИ", "EUR": r"ЕВРОЗОН|ЕЦБ|ГЕРМАН", "CAD": r"КАНАД", "AUD": r"АВСТРАЛ",
          "NZD": r"ЗЕЛАНД", "JPY": r"ЯПОН", "CHF": r"ШВЕЙЦАР"}
CTY = {k: v + "|" + RU_CTY[k] for k, v in COUNTRY.items()}
NOISE = r"PODCAST|ПОДКАСТ|WEBINAR|PREVIEW|AHEAD OF|COMING UP|DUE AT|EXPECTED AT|CALENDAR"

def match(e, posts):
    pat = "|".join([KINDS[k][2] for k in e["kinds"]] + [RU_KIND[k] for k in e["kinds"] if k in RU_KIND])
    own, other = CTY[e["ccy"]], "|".join(v for c, v in CTY.items() if c != e["ccy"])
    cb = bool(e["kinds"] & set(range(11, 18)))
    best = None
    for p in posts:
        dt = (datetime.fromisoformat(p["time"]) - e["time"].to_pydatetime()).total_seconds()
        if dt < -5 or dt > 900:
            continue
        tx = p["text"].upper()
        head = tx[:160]
        if re.search(NOISE, head) or not re.search(pat, head, re.I) or not (cb or re.search(r"\d", head)):
            continue
        if e["ccy"] == "USD":
            if re.search(other, head) and not re.search(own, head):
                continue
        elif not re.search(own, head):
            continue
        if best is None or dt < best[0]:
            best = (dt, p["text"][:100].replace("\n", " "))
    return best

ev = events()
nus = sum(e["ccy"] == "USD" for e in ev)
rows, detail = [], {}
for ch in sys.argv[2:] if len(sys.argv) > 2 else []:
    pass
CH = ["TreeNewsFeed", "BWEnews", "nwsmkr", "markettwits", "WatcherGuru", "marketfeed", "BreakingMarketNews",
      "financialjuice", "WalterBloomberg", "fxstreetforex", "insiderpaper", "unfolded", "brokerexness", "FXGoldVisionMarkets"]
for ch in CH:
    try:
        w = json.load(open(f"win_{ch}.json"))["windows"]
    except FileNotFoundError:
        continue
    res = []
    for e in ev:
        b = match(e, w.get(str(e["time"]), []))
        res.append(dict(time=str(e["time"])[:16], ccy=e["ccy"], event="; ".join(sorted(e["names"]))[:50],
                        delay=b[0] if b else None, post=b[1] if b else None))
    detail[ch] = res
    d = pd.DataFrame(res)
    a, u = d.delay.dropna(), d[d.ccy == "USD"].delay.dropna()
    rows.append(dict(channel=ch, matched=f"{len(a)}/{len(ev)}", us=f"{len(u)}/{nus}",
                     median_all=a.median() if len(a) else None, median_us=u.median() if len(u) else None,
                     le10=int((a <= 10).sum()), le30=int((a <= 30).sum()), fastest=a.min() if len(a) else None,
                     slowest=a.max() if len(a) else None))
t = pd.DataFrame(rows)
print(t.to_string(index=False))
json.dump(detail, open("rescored.json", "w"), indent=1, default=str)
