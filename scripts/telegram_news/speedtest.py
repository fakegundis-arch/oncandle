"""Telegram news-channel speed test (Nov 6 2026): seconds from a scheduled high-impact release to the channel's first headline.

Releases: Forex Factory high-impact events Sep 1 - Oct 31 2026 (local calendar) + this week's FF feed (Nov 1-6).
Posts: the channel's public web preview search (t.me/s/<channel>?q=<term>), timestamps to the second.
A post counts for a release if it is within [release - 5 s, release + 15 min], matches the release's keyword, carries a
number, and names the right country (non-USD) / no other country (USD).
usage: python3 -I scripts/telegram_news/speedtest.py data/telegram/speedtest <channel> [...]
(<outdir> must hold ff_thisweek.json, Forex Factory's weekly JSON for the current week)."""
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import pandas as pd

OUT = sys.argv[1]
CHANNELS = sys.argv[2:]
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
SINCE = datetime(2026, 9, 1, tzinfo=timezone.utc)

# FF event name -> (search terms, match regex)
KINDS = [
    (r"Non-Farm|Average Hourly", ["payrolls", "nonfarm", "NFP"], r"payroll|non-?farm|\bNFP\b|hourly earnings|unemployment rate"),
    (r"^Unemployment Rate$|Employment Change", ["unemployment", "employment", "jobs"], r"unemployment|employment|jobs|payroll"),
    (r"CPI", ["CPI", "inflation"], r"\bCPI\b|inflation"),
    (r"PPI", ["PPI"], r"\bPPI\b|producer price"),
    (r"Retail Sales", ["retail sales"], r"retail sales"),
    (r"ISM", ["ISM"], r"\bISM\b"),
    (r"ADP", ["ADP"], r"\bADP\b"),
    (r"JOLTS", ["JOLTS"], r"JOLTS|job openings"),
    (r"Unemployment Claims", ["jobless", "claims"], r"jobless|initial claims|continuing claims"),
    (r"GDP", ["GDP"], r"\bGDP\b"),
    (r"PCE", ["PCE"], r"\bPCE\b"),
    (r"Federal Funds Rate|FOMC Statement", ["FOMC", "Fed"], r"FOMC|\bFED\b|federal funds|fed funds"),
    (r"Official Bank Rate|Monetary Policy Summary", ["BOE", "Bank of England"], r"\bBOE\b|bank of england"),
    (r"Main Refinancing Rate|Monetary Policy Statement", ["ECB"], r"\bECB\b"),
    (r"Cash Rate|RBA Rate Statement", ["RBA"], r"\bRBA\b|reserve bank of australia"),
    (r"Official Cash Rate|RBNZ", ["RBNZ"], r"RBNZ|reserve bank of new zealand"),
    (r"Overnight Rate|BOC Rate", ["BOC", "Bank of Canada"], r"\bBOC\b|bank of canada"),
    (r"SNB Policy Rate", ["SNB"], r"\bSNB\b|swiss national bank"),
    (r"PMI", ["PMI"], r"\bPMI\b"),
]
SKIP = r"Speaks|Press Conference|Election|Testifies|Minutes|Votes|Report$|Monetary Policy Report|Statement$|Policy Statement"
COUNTRY = {"USD": r"\bU\.?S\.?\b|\bUSA?\b|\bFED\b|FOMC|AMERICA|NONFARM|PAYROLL",
           "GBP": r"\bUK\b|U\.K\.|BRIT|ENGLAND|\bBOE\b|\bGBP\b",
           "EUR": r"EURO|\bECB\b|\bEZ\b|GERMAN|\bEUR\b|EMU",
           "CAD": r"CANAD|\bBOC\b|\bCAD\b",
           "AUD": r"AUSTRAL|\bRBA\b|\bAUD\b|\bAUS\b",
           "NZD": r"ZEALAND|RBNZ|\bNZD?\b",
           "JPY": r"JAPAN|\bBOJ\b|\bJPY\b",
           "CHF": r"SWISS|SWITZERLAND|\bSNB\b|\bCHF\b"}


def events() -> list[dict]:
    c = pd.read_csv(__import__("pathlib").Path(__file__).resolve().parents[2] / "data/calendar/ff_calendar.csv",
                    parse_dates=["time_utc"])
    c = c[(c.impact == "high") & (c.time_utc >= "2026-09-01")]
    rows = [(t.tz_localize("UTC"), cur, n) for t, cur, n in zip(c.time_utc, c.currency, c.name)]
    wk = pd.DataFrame(json.load(open(OUT + "/ff_thisweek.json")))
    wk = wk[wk.impact == "High"]
    rows += [(pd.Timestamp(d).tz_convert("UTC"), cur, n) for d, cur, n in zip(wk.date, wk.country, wk.title)]
    g: dict = {}
    for t, cur, n in rows:
        if re.search(SKIP, n) and not re.search(r"Rate Statement|Monetary Policy Summary|FOMC Statement|Monetary Policy Statement", n):
            continue
        if cur == "JPY" and re.search(r"BOJ|Policy Rate|Monetary Policy Statement", n):
            continue                                            # BoJ minute not scheduled
        k = next((i for i, (pat, _, _) in enumerate(KINDS) if re.search(pat, n)), None)
        if k is None:
            continue
        e = g.setdefault((t, cur), {"time": t, "ccy": cur, "names": set(), "kinds": set()})
        e["names"].add(n); e["kinds"].add(k)
    return sorted(g.values(), key=lambda e: e["time"])


def get(url: str) -> str:
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as ex:                                 # noqa: BLE001
            time.sleep(3 * (i + 1))
    return ""


MSG = re.compile(r'data-post="([^"/]+)/(\d+)"(.*?)(?=data-post="|\Z)', re.S)


def parse(page: str) -> list[dict]:
    out = []
    for ch, mid, body in MSG.findall(page):
        t = re.search(r'<time datetime="([^"]+)"', body)
        tx = re.search(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', body, re.S)
        if not t:
            continue
        text = html.unescape(re.sub(r"<br\s*/?>", "\n", tx.group(1)) if tx else "")
        text = re.sub(r"<[^>]+>", "", text).strip()
        out.append({"id": int(mid), "time": t.group(1), "text": text})
    return out


def search(ch: str, term: str, max_pages: int = 6) -> list[dict]:
    posts, before = [], None
    for _ in range(max_pages):
        q = f"https://t.me/s/{ch}?q={urllib.parse.quote(term)}" + (f"&before={before}" if before else "")
        ps = parse(get(q))
        time.sleep(0.6)
        if not ps:
            break
        posts += ps
        oldest = min(ps, key=lambda p: p["id"])
        if datetime.fromisoformat(oldest["time"]) < SINCE:
            break
        before = oldest["id"]
    return posts


def window_posts(ch: str, events_: list[dict], cache: dict) -> dict:
    """All posts of `ch` from 60 s before to 900 s after each event (found by interpolating on message ids)."""
    def fetch(param: str) -> list[dict]:
        ps = parse(get(f"https://t.me/s/{ch}?{param}"))
        time.sleep(0.5)
        for p in ps:
            cache[p["id"]] = p
        return ps
    fetch("")
    out = {}
    for e in events_:
        T = e["time"].to_pydatetime()
        t0 = T - timedelta(seconds=60)
        for _ in range(14):
            an = sorted((p["id"], datetime.fromisoformat(p["time"])) for p in cache.values())
            lo = [x for x in an if x[1] <= t0]
            hi = [x for x in an if x[1] > t0]
            if lo and hi and hi[0][0] - lo[-1][0] <= 1:
                break
            if lo and hi:
                (i0, a0), (i1, a1) = lo[-1], hi[0]
                f = (t0 - a0).total_seconds() / max((a1 - a0).total_seconds(), 1)
                g = int(i0 + max(1, min(i1 - i0 - 1, f * (i1 - i0))))
            elif hi:
                (i1, a1) = hi[0]
                rate = max((an[-1][0] - an[0][0]) / max((an[-1][1] - an[0][1]).total_seconds(), 1), 1e-4) if len(an) > 1 else 0.01
                g = int(i1 - rate * (a1 - t0).total_seconds())
                if g <= 1:
                    break
            else:
                break
            got = fetch(f"before={g + 10}")
            if not got and g <= 1:
                break
        an = sorted((p["id"], datetime.fromisoformat(p["time"])) for p in cache.values())
        lo = [x for x in an if x[1] <= t0]
        start = lo[-1][0] if lo else 0
        posts = []
        for _ in range(12):                                   # forward to release + 15 min
            got = fetch(f"after={start}")
            if not got:
                break
            posts += got
            last = max(got, key=lambda p: p["id"])
            if datetime.fromisoformat(last["time"]) > T + timedelta(seconds=900):
                break
            start = last["id"]
        out[str(e["time"])] = [p for p in posts if t0 <= datetime.fromisoformat(p["time"]) <= T + timedelta(seconds=900)]
    return out


def match(e: dict, posts: list[dict]):
    pat = "|".join(KINDS[k][2] for k in e["kinds"])
    own = COUNTRY[e["ccy"]]
    other = "|".join(v for c2, v in COUNTRY.items() if c2 != e["ccy"])
    best = None
    for p in posts:
        dt = (datetime.fromisoformat(p["time"]) - e["time"].to_pydatetime()).total_seconds()
        if dt < -5 or dt > 900:
            continue
        tx = p["text"].upper()
        cb = bool(e["kinds"] & set(range(11, 18)))           # rate decisions: the headline may carry no number
        if not re.search(pat, tx, re.I) or not (cb or re.search(r"\d", tx)):
            continue
        if e["ccy"] == "USD":
            if re.search(other, tx) and not re.search(own, tx):
                continue
        elif not re.search(own, tx):
            continue
        if best is None or dt < best[0]:
            best = (dt, p["text"][:100].replace("\n", " "))
    return best


def main():
    ev = events()
    res = {}
    for ch in CHANNELS:
        cache: dict = {}
        win = window_posts(ch, ev, cache)
        json.dump({"windows": win, "n_cached": len(cache)}, open(f"{OUT}/win_{ch}.json", "w"))
        rows = []
        for e in ev:
            best = match(e, win.get(str(e["time"]), []))
            rows.append({"time": str(e["time"]), "ccy": e["ccy"], "event": "; ".join(sorted(e["names"]))[:60],
                         "n_window": len(win.get(str(e["time"]), [])),
                         "delay_s": best[0] if best else None, "post": best[1] if best else None})
        res[ch] = rows
        json.dump(rows, open(f"{OUT}/speed_{ch}.json", "w"), indent=1, default=str)
        d = pd.Series([r["delay_s"] for r in rows if r["delay_s"] is not None], dtype=float)
        print(f"{ch:22s} events matched {len(d):2d}/{len(ev)} | median {d.median() if len(d) else float('nan'):6.1f} s "
              f"| <=30 s {int((d <= 30).sum()):2d} | <=10 s {int((d <= 10).sum()):2d}", flush=True)
    print("events:", len(ev))


if __name__ == "__main__":
    main()
