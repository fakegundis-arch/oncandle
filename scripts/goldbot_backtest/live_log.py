"""Parse the bot's own log (logs/newsbot.log) into one row per Telegram post it saw, with what it decided and every
fill, so the replay can be checked post by post; straddles() gives one row per straddle the bot armed (all feeds, gold
and the USTECm companion) with its fills, SL / TP, AI verdict and break-even moves.  The log clock is UTC+3 (checked:
FinancialJuice post 145781 sent 19:39:27 UTC is logged 22:39:28; the USTECm fills match the Exness ticks to the cent).
The raw log holds account numbers: it is read in place and never copied into the repo.
usage: python3 -I scripts/goldbot_backtest/live_log.py <newsbot.log> <out.csv>"""
import re
import sys

import pandas as pd

OFF = pd.Timedelta(hours=3)
LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) (\w+) +([\w.]+) \| (.*)$")


def parse(path):
    posts, fills, events = {}, [], []
    cur = None                      # the post whose NOTIFY line came last (its URL line follows)
    last_recv = {}
    armed_by_title = []             # (title prefix, post key) of straddles in arming order
    awaiting = []                   # armed, reviewed posts still waiting for their AI verdict
    for raw in open(path, encoding="utf-8", errors="replace"):
        raw = raw.rstrip("\n")
        if raw.startswith("https://t.me/"):
            m = re.match(r"https://t.me/(\w+)/(\d+)", raw)
            if m and cur is not None:
                key = (m.group(1), int(m.group(2)))
                posts.setdefault(key, dict(channel=m.group(1), post_id=int(m.group(2)), **cur))
                cur["key"] = key
            continue
        m = LINE.match(raw)
        if not m:
            continue
        t = pd.Timestamp(m.group(1)) - OFF
        msg = m.group(4)
        r = re.match(r"Telegram @(\w+) post received ([\d.]+)s after it was sent \((push|poll)\)", msg)
        if r:
            last_recv[r.group(1)] = (t, float(r.group(2)), r.group(3))
            continue
        r = re.match(r"NOTIFY \| 📣 @(\w+)(?: [↩🔁])? \((\d+)s ago(?:, \d+s queued)?\): (.*)", msg)
        if r:
            ch = r.group(1)
            rt, lat, via = last_recv.get(ch, (t, float("nan"), ""))
            cur = dict(recv_utc=rt, latency_s=lat, via=via, text=r.group(3), decision="", key=None)
            continue
        if msg.startswith(("NOTIFY | 🐦 @", "NOTIFY | 🇺🇸 TRUMP POST")):
            cur = None                  # another feed's post: what follows is about it, not the last Telegram post
            continue
        if "NewsBot starting" in msg:
            awaiting.clear()
            cur = None
            continue
        awaiting[:] = [a for a in awaiting if (t - posts[a]["armed_utc"]).total_seconds() <= 40]   # 20-s API timeout
        if msg.startswith("TELEGRAM post review vetoed but the straddle is already"):
            if awaiting:
                awaiting.pop(0)         # the verdict came after the straddle had finished: nothing was cancelled
            continue
        if msg.startswith("NOTIFY | 🤖 TELEGRAM review:"):
            # verdicts come back a few seconds after arming, possibly after later posts: oldest unanswered straddle
            if awaiting:
                q = posts[awaiting.pop(0)]
                q["ai"] = "keep" if "review: keep" in msg else "close"
                q["ai_text"] = msg.split("review:", 1)[1].strip()[:120]
                q["ai_utc"] = t
            continue
        if cur is None:
            continue
        k = cur.get("key")
        p = posts.get(k) if k else None
        if p is None:
            continue
        if msg.startswith("Telegram post NOT traded"):
            p["decision"] = re.sub(r"^Telegram post NOT traded \(@\w+, ([^)]*)\).*", r"\1", msg)
        elif msg.startswith("Max TELEGRAM straddles open"):
            p["decision"] = "channel max_open"
        elif msg.startswith("Global cap reached") and "skip telegram" in msg:
            p["decision"] = "global cap"
        elif "USD news blackout" in msg and "not traded" in msg:
            p["decision"] = "USD news blackout"
        elif "same content already traded" in msg:
            p["decision"] = "duplicate content"
        elif msg.startswith("NOTIFY | 📣 Armed TELEGRAM straddle"):
            r = re.search(r"\((\d+) orders, ([\d.]+) lots\)", msg)
            p["decision"] = "ARMED" + (" (fast track)" if "flagged" in msg else "")
            p["gold_lots"] = float(r.group(2)) if r else None
            p["armed_utc"] = t
            armed_by_title.append((p["text"][:40], k))
            if "flagged" not in msg:
                awaiting.append(k)
        elif msg.startswith("NOTIFY | ⚠️ TELEGRAM straddle placed NO orders"):
            p["decision"] = "NO orders: " + msg.split("—")[-1].strip()
        elif msg.startswith("NOTIFY | 📊 Armed USTECm straddle alongside gold (TELEGRAM)"):
            r = re.search(r"([\d.]+) lots, ([\d.]+) / ([\d.]+)", msg)
            if r:
                p["nas_lots"], p["nas_buy"], p["nas_sell"] = float(r.group(1)), float(r.group(2)), float(r.group(3))
        r = re.match(r"NOTIFY \| (.{1,60}): (BUY|SELL) filled @ ([\d.]+) — set SL ([\d.]+) / TP ([\d.]+)", msg)
        if r:
            fills.append(dict(utc=t, title=r.group(1), side=r.group(2), price=float(r.group(3)), sl=float(r.group(4)),
                              tp=float(r.group(5))))
        r = re.match(r"NOTIFY \| (.{1,60}): (BUY|SELL) filled @ ([\d.]+) \((\w+) straddle\)", msg)
        if r:
            events.append(dict(utc=t, title=r.group(1), side=r.group(2), price=float(r.group(3)), kind=r.group(4)))
        r = re.match(r"NOTIFY \| 🔒 Break-even stage (\d): SL moved to ([\d.]+) on (BUY|SELL) @ ([\d.]+)", msg)
        if r:
            events.append(dict(utc=t, title="", side=r.group(3), price=float(r.group(4)), kind=f"BE{r.group(1)}",
                               sl=float(r.group(2))))
    P = pd.DataFrame(posts.values())
    F = pd.DataFrame(events)
    S = pd.DataFrame(fills)
    return P, F, S


if __name__ == "__main__":
    P, F, S = parse(sys.argv[1])
    P.to_csv(sys.argv[2], index=False)
    F.to_csv(sys.argv[2].replace(".csv", "_fills.csv"), index=False)
    S.to_csv(sys.argv[2].replace(".csv", "_sltp.csv"), index=False)
    print(len(P), "posts;", P.decision.value_counts().to_dict())
    print(len(F), "fill / break-even events;", F.kind.value_counts().to_dict() if len(F) else {})


# ------------------------------------------------------------------ every straddle the bot armed, with what became of it
ARM = re.compile(r"NOTIFY \| \S+ Armed (TELEGRAM|X|TRUMP) straddle (?:\(@(\w+)\) )?\((\d+) orders, ([\d.]+) lots\)(.*?)"
                 r"(?: on)? “(.*)”$")
COMP = re.compile(r"NOTIFY \| 📊 Armed USTECm straddle alongside gold \((TELEGRAM|X|TRUMP)\): \d+ orders, ([\d.]+) lots, "
                  r"([\d.]+) / ([\d.]+)")
VETO = re.compile(r"^(TELEGRAM|X|TRUMP)( → USTECm)? straddle vetoed by AI review")
PASS = re.compile(r"^(TELEGRAM|X|TRUMP) post review passed")
SLTP = re.compile(r"NOTIFY \| (.{1,60}): (BUY|SELL) filled @ ([\d.]+) — set SL ([\d.]+) / TP ([\d.]+)")
FILL = re.compile(r"NOTIFY \| (.{1,60}): (BUY|SELL) filled @ ([\d.]+) \((Telegram|USTECm|X|Trump|TRUMP) straddle")
OVER = re.compile(r"^(Telegram|USTECm|X|Trump|TRUMP) straddle (.{1,60}): window over, no fill")
BE = re.compile(r"NOTIFY \| 🔒 Break-even stage (\d)( \(USTECm\))?: SL moved to ([\d.]+) on (BUY|SELL) @ ([\d.]+)")


def straddles(path):
    """One row per armed straddle (gold, and the USTECm companion as its own row), UTC times."""
    rows, last_by_feed = [], {}
    pending = None                  # the last "filled @ P — set SL / TP" line, joined to the fill line next to it

    def owner(title, sym):
        title = title.strip()
        for s in reversed(rows):
            if s["symbol"] == sym and s["title"].strip().startswith(title[:35]):
                return s
        return None

    for raw in open(path, encoding="utf-8", errors="replace"):
        m = LINE.match(raw.rstrip("\n"))
        if not m:
            continue
        t = pd.Timestamp(m.group(1)) - OFF
        msg = m.group(4)
        r = ARM.search(msg)
        if r:
            feed = r.group(1)
            s = dict(feed=feed, source=r.group(2) or "", symbol="XAUUSDm", arm_utc=t, lots=float(r.group(4)),
                     flagged="flagged" in r.group(5), title=r.group(6), buy_stop=None, sell_stop=None, ai="",
                     ai_utc=None, fills=[], sltp=[], be=[], no_fill_utc=None, no_orders="")
            rows.append(s)
            last_by_feed[feed] = [s]
            continue
        r = COMP.search(msg)
        if r and r.group(1) in last_by_feed:
            g = last_by_feed[r.group(1)][0]
            c = dict(g, symbol="USTECm", arm_utc=t, lots=float(r.group(2)), buy_stop=float(r.group(3)),
                     sell_stop=float(r.group(4)), fills=[], sltp=[], be=[])
            rows.append(c)
            last_by_feed[r.group(1)] = [g, c]
            continue
        r = VETO.match(msg)
        if r and r.group(1) in last_by_feed:
            for s in last_by_feed[r.group(1)]:
                if (s["symbol"] == "USTECm") == bool(r.group(2)) and not s["ai"]:
                    s["ai"], s["ai_utc"] = "close", t
            continue
        r = PASS.match(msg)
        if r and r.group(1) in last_by_feed:
            for s in last_by_feed[r.group(1)]:
                if not s["ai"]:
                    s["ai"], s["ai_utc"] = "keep", t
            continue
        if "straddle placed NO orders" in msg:
            # a failed placement logs no "Armed" line: it belongs to a post that never became a straddle, not to the
            # straddle armed before it
            continue
        r = SLTP.search(msg)
        if r:                       # usually just before the fill line, sometimes seconds after it (a retried SL)
            side, px, sl, tp = r.group(2), float(r.group(3)), float(r.group(4)), float(r.group(5))
            done = False
            for sym in ("USTECm", "XAUUSDm"):
                s = owner(r.group(1), sym)
                if s is not None and not s["sltp"] and any(f[1] == side and abs(f[2] - px) < 1e-6 for f in s["fills"]):
                    s["sltp"].append((sl, tp))
                    done = True
                    break
            pending = None if done else (side, px, sl, tp)
            continue
        r = FILL.search(msg)
        if r:
            sym = "USTECm" if r.group(4) == "USTECm" else "XAUUSDm"
            s = owner(r.group(1), sym)
            if s is not None:
                s["fills"].append((t, r.group(2), float(r.group(3))))
                if pending and pending[0] == r.group(2) and abs(pending[1] - float(r.group(3))) < 1e-6:
                    s["sltp"].append(pending[2:])
            pending = None
            continue
        r = OVER.match(msg)
        if r:
            sym = "USTECm" if r.group(1) == "USTECm" else "XAUUSDm"
            s = owner(r.group(2), sym)
            if s is not None:
                s["no_fill_utc"] = t
            continue
        r = BE.search(msg)
        if r:
            sym = "USTECm" if r.group(2) else "XAUUSDm"
            for s in reversed(rows):
                tol = 1.0 if sym == "USTECm" else 0.06          # the log rounds the entry to 1 decimal / whole points
                if s["symbol"] == sym and any(f[1] == r.group(4) and abs(f[2] - float(r.group(5))) < tol
                                              for f in s["fills"]):
                    s["be"].append((t, int(r.group(1)), float(r.group(3))))
                    break
    out = []
    for s in rows:
        f = s["fills"][0] if s["fills"] else (None, "", None)
        sl, tp = s["sltp"][0] if s["sltp"] else (None, None)
        out.append(dict(feed=s["feed"], source=s["source"], symbol=s["symbol"], arm_utc=s["arm_utc"], lots=s["lots"],
                        flagged=s["flagged"], title=s["title"], buy_stop=s["buy_stop"], sell_stop=s["sell_stop"],
                        ai=s["ai"], ai_utc=s["ai_utc"], no_orders=s["no_orders"], n_fills=len(s["fills"]),
                        fill_utc=f[0], side=f[1], fill=f[2], sl=sl, tp=tp,
                        fill2_side=s["fills"][1][1] if len(s["fills"]) > 1 else "",
                        be_utc=s["be"][0][0] if s["be"] else None, be_sl=s["be"][0][2] if s["be"] else None,
                        no_fill_utc=s["no_fill_utc"]))
    return pd.DataFrame(out)
