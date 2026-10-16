//+------------------------------------------------------------------+
//|                                             ConfluenceRider.mq5  |
//|  Strategy 2. Watches several markets from ONE chart and only      |
//|  joins a trend when at least MinAgree markets trend the same way  |
//|  (one market trending alone is ignored). Entry, stop, 1:RR target |
//|  and the break-even move are the same as TrendRider.mq5.          |
//|  Rules mirror backtester/confluence.py.                           |
//+------------------------------------------------------------------+
#property copyright "oncandle"
#property version   "1.00"

#include <Trade/Trade.mqh>

enum ENUM_ENTRY
  {
   ENTRY_PULLBACK = 0,   // Pullback to EMA20 in an agreeing market
   ENTRY_ONSET           // The minute the group lines up
  };

input group "Markets"
input string InpSymbols     = "BTCUSD,XAUUSD,USTEC,US30"; // Symbols (your broker's names)
input ENUM_TIMEFRAMES InpTF = PERIOD_M1;
input int    InpMinAgree    = 2;     // Markets that must trend the same way (incl. the traded one)
input ENUM_ENTRY InpEntry   = ENTRY_PULLBACK;
input int    InpStaleMinutes = 5;    // A market with no bar for this long counts as not trending

input group "Risk & bracket"
input double InpRiskPercent = 0.5;
input double InpRR          = 3.0;
input double InpBETrigger   = 1.0;   // Move SL to break-even at this many R (0 = off)
input double InpBEBuffer    = 0.1;
input double InpMinStopATR  = 1.0;
input double InpMaxStopATR  = 4.0;
input int    InpSwingBars   = 10;
input int    InpMaxSpreadPts = 0;

input group "Trend / consolidation filter"
input int    InpEmaFast   = 20;
input int    InpEmaMid    = 50;
input int    InpEmaSlow   = 200;
input int    InpSlopeBars = 10;
input int    InpAdxPeriod = 14;
input double InpAdxMin    = 25;
input int    InpChopPeriod = 14;
input double InpChopMax   = 50;
input int    InpAtrPeriod = 14;

input ulong  InpMagic = 20261018;

struct Market
  {
   string sym;
   int    hFast, hMid, hSlow, hAdx, hAtr;
   int    state;     // +1 / -1 / 0 for the last closed minute
   int    shift;     // bar index of that minute (-1 = stale / closed)
  };

Market   mk[];
CTrade   trade;
datetime lastMinute = 0;
int      prevUp = 0, prevDn = 0;

//+------------------------------------------------------------------+
double Buf(int h, int b, int s)
  {
   double v[1];
   if(CopyBuffer(h, b, s, 1, v) != 1) return EMPTY_VALUE;
   return v[0];
  }

int OnInit()
  {
   trade.SetExpertMagicNumber(InpMagic);
   string parts[];
   int n = StringSplit(InpSymbols, ',', parts);
   for(int i = 0; i < n; i++)
     {
      string s = parts[i];
      StringTrimLeft(s); StringTrimRight(s);
      if(s == "" || !SymbolSelect(s, true)) { if(s != "") Print("Symbol not found: ", s); continue; }
      Market m;
      m.sym = s;
      m.hFast = iMA(s, InpTF, InpEmaFast, 0, MODE_EMA, PRICE_CLOSE);
      m.hMid  = iMA(s, InpTF, InpEmaMid, 0, MODE_EMA, PRICE_CLOSE);
      m.hSlow = iMA(s, InpTF, InpEmaSlow, 0, MODE_EMA, PRICE_CLOSE);
      m.hAdx  = iADXWilder(s, InpTF, InpAdxPeriod);
      m.hAtr  = iATR(s, InpTF, InpAtrPeriod);
      m.state = 0; m.shift = -1;
      if(m.hFast == INVALID_HANDLE || m.hMid == INVALID_HANDLE || m.hSlow == INVALID_HANDLE ||
         m.hAdx == INVALID_HANDLE || m.hAtr == INVALID_HANDLE) { Print("Indicator init failed: ", s); continue; }
      int k = ArraySize(mk);
      ArrayResize(mk, k + 1);
      mk[k] = m;
     }
   if(ArraySize(mk) < InpMinAgree) { Print("Fewer markets than MinAgree"); return INIT_FAILED; }
   EventSetTimer(1);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   for(int i = 0; i < ArraySize(mk); i++)
     {
      IndicatorRelease(mk[i].hFast); IndicatorRelease(mk[i].hMid); IndicatorRelease(mk[i].hSlow);
      IndicatorRelease(mk[i].hAdx);  IndicatorRelease(mk[i].hAtr);
     }
  }

//+------------------------------------------------------------------+
double Choppiness(string s, int shift)
  {
   double trSum = 0, hh = -DBL_MAX, ll = DBL_MAX;
   for(int i = shift; i < shift + InpChopPeriod; i++)
     {
      double h = iHigh(s, InpTF, i), l = iLow(s, InpTF, i), pc = iClose(s, InpTF, i + 1);
      trSum += MathMax(h, pc) - MathMin(l, pc);
      hh = MathMax(hh, h); ll = MathMin(ll, l);
     }
   if(hh - ll <= 0 || trSum <= 0) return 100;
   return 100.0 * MathLog10(trSum / (hh - ll)) / MathLog10(InpChopPeriod);
  }

int TrendState(Market &m, int sh)
  {
   string s = m.sym;
   if(sh < 0 || Bars(s, InpTF) < InpEmaSlow + 50 + sh) return 0;
   double c = iClose(s, InpTF, sh);
   double mid = Buf(m.hMid, 0, sh), midS = Buf(m.hMid, 0, sh + InpSlopeBars), slow = Buf(m.hSlow, 0, sh);
   double adx = Buf(m.hAdx, 0, sh);
   if(mid == EMPTY_VALUE || midS == EMPTY_VALUE || slow == EMPTY_VALUE || adx == EMPTY_VALUE) return 0;
   if(!(adx > InpAdxMin && Choppiness(s, sh) < InpChopMax)) return 0;   // consolidating
   if(mid > slow && c > mid && mid > midS) return 1;
   if(mid < slow && c < mid && mid < midS) return -1;
   return 0;
  }

// Stop distance for a long (+1) or short (-1) at bar sh; 0 if the setup is too wide.
double StopDist(Market &m, int sh, int dir)
  {
   string s = m.sym;
   double atr = Buf(m.hAtr, 0, sh), c = iClose(s, InpTF, sh);
   if(atr == EMPTY_VALUE || atr <= 0) return 0;
   double d = dir == 1 ? c - iLow(s, InpTF, iLowest(s, InpTF, MODE_LOW, InpSwingBars, sh))
                       : iHigh(s, InpTF, iHighest(s, InpTF, MODE_HIGH, InpSwingBars, sh)) - c;
   d = MathMax(d, InpMinStopATR * atr);
   return d <= InpMaxStopATR * atr ? d : 0;
  }

bool Pullback(Market &m, int sh, int dir)
  {
   string s = m.sym;
   double c = iClose(s, InpTF, sh), f = Buf(m.hFast, 0, sh), fPrev = Buf(m.hFast, 0, sh + 1);
   if(f == EMPTY_VALUE || fPrev == EMPTY_VALUE) return false;
   if(dir == 1)  return iLow(s, InpTF, sh + 1) <= fPrev && c > f && c > iHigh(s, InpTF, sh + 1);
   return iHigh(s, InpTF, sh + 1) >= fPrev && c < f && c < iLow(s, InpTF, sh + 1);
  }

//+------------------------------------------------------------------+
bool HasPosition(string s, ulong &ticket)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(PositionGetString(POSITION_SYMBOL) == s && PositionGetInteger(POSITION_MAGIC) == (long)InpMagic)
        { ticket = t; return true; }
     }
   return false;
  }

double LotsForRisk(string s, double dist)
  {
   double tv = SymbolInfoDouble(s, SYMBOL_TRADE_TICK_VALUE_LOSS);
   double ts = SymbolInfoDouble(s, SYMBOL_TRADE_TICK_SIZE);
   if(tv <= 0 || ts <= 0 || dist <= 0) return 0;
   double lots = AccountInfoDouble(ACCOUNT_EQUITY) * InpRiskPercent / 100.0 / (dist / ts * tv);
   double step = SymbolInfoDouble(s, SYMBOL_VOLUME_STEP);
   lots = MathFloor(lots / step) * step;
   if(lots < SymbolInfoDouble(s, SYMBOL_VOLUME_MIN)) return 0;
   return MathMin(lots, SymbolInfoDouble(s, SYMBOL_VOLUME_MAX));
  }

void ManageBreakEven(string s, ulong ticket)
  {
   if(InpBETrigger <= 0 || !PositionSelectByTicket(ticket)) return;
   double open = PositionGetDouble(POSITION_PRICE_OPEN);
   double sl = PositionGetDouble(POSITION_SL), tp = PositionGetDouble(POSITION_TP);
   if(tp == 0) return;
   double R = MathAbs(tp - open) / InpRR;
   int dg = (int)SymbolInfoInteger(s, SYMBOL_DIGITS);
   if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
     {
      double be = NormalizeDouble(open + InpBEBuffer * R, dg);
      if(sl < be && SymbolInfoDouble(s, SYMBOL_BID) >= open + InpBETrigger * R) trade.PositionModify(ticket, be, tp);
     }
   else
     {
      double be = NormalizeDouble(open - InpBEBuffer * R, dg);
      if((sl == 0 || sl > be) && SymbolInfoDouble(s, SYMBOL_ASK) <= open - InpBETrigger * R) trade.PositionModify(ticket, be, tp);
     }
  }

void Open(string s, int dir, double dist)
  {
   if(InpMaxSpreadPts > 0 && SymbolInfoInteger(s, SYMBOL_SPREAD) > InpMaxSpreadPts) return;
   double lots = LotsForRisk(s, dist);
   if(lots <= 0) { Print(s, ": lot size below broker minimum for this risk - skipped"); return; }
   int dg = (int)SymbolInfoInteger(s, SYMBOL_DIGITS);
   if(dir == 1)
     {
      double px = SymbolInfoDouble(s, SYMBOL_ASK);
      trade.Buy(lots, s, px, NormalizeDouble(px - dist, dg), NormalizeDouble(px + InpRR * dist, dg), "Confluence");
     }
   else
     {
      double px = SymbolInfoDouble(s, SYMBOL_BID);
      trade.Sell(lots, s, px, NormalizeDouble(px + dist, dg), NormalizeDouble(px - InpRR * dist, dg), "Confluence");
     }
  }

//+------------------------------------------------------------------+
void Process()
  {
   // break-even management on every tick / second
   for(int i = 0; i < ArraySize(mk); i++)
     {
      ulong t;
      if(HasPosition(mk[i].sym, t)) ManageBreakEven(mk[i].sym, t);
     }

   // once per minute, a couple of seconds after the boundary so every feed has ticked
   datetime now = TimeCurrent();
   datetime minute = now - now % 60;
   if(minute == lastMinute || now - minute < 2) return;
   lastMinute = minute;
   datetime closed = minute - 60;                       // the minute that just completed

   int nUp = 0, nDn = 0;
   for(int i = 0; i < ArraySize(mk); i++)
     {
      int sh = iBarShift(mk[i].sym, InpTF, closed, false);   // bar at or before `closed`
      if(sh < 0 || iTime(mk[i].sym, InpTF, sh) < closed - InpStaleMinutes * 60) sh = -1;
      mk[i].shift = sh;
      mk[i].state = TrendState(mk[i], sh);
      if(mk[i].state == 1) nUp++;
      if(mk[i].state == -1) nDn++;
     }

   for(int i = 0; i < ArraySize(mk); i++)
     {
      string s = mk[i].sym;
      ulong t;
      int st = mk[i].state, sh = mk[i].shift;
      if(st == 0 || sh < 0 || HasPosition(s, t)) continue;
      int agree = st == 1 ? nUp : nDn;
      if(agree < InpMinAgree) continue;                  // not enough markets agree
      bool trigger;
      if(InpEntry == ENTRY_ONSET) trigger = (st == 1 ? prevUp : prevDn) < InpMinAgree;
      else                        trigger = Pullback(mk[i], sh, st);
      if(!trigger) continue;
      double dist = StopDist(mk[i], sh, st);
      if(dist > 0) Open(s, st, dist);
     }
   prevUp = nUp; prevDn = nDn;
  }

void OnTick()  { Process(); }
void OnTimer() { Process(); }
//+------------------------------------------------------------------+
