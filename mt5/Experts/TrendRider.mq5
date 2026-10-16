//+------------------------------------------------------------------+
//|                                                 TrendRider.mq5   |
//|  M1 trend-joining EA. Watches several markets from ONE chart,     |
//|  stays out while a market is consolidating, joins a trend on a    |
//|  pullback with a 1:RR bracket, and moves the stop to just past    |
//|  entry as soon as price has travelled BE_Trigger x risk.          |
//|  Rules mirror backtester/trend_rider.py.                          |
//+------------------------------------------------------------------+
#property copyright "oncandle"
#property version   "1.00"

#include <Trade/Trade.mqh>

input group "Markets"
input string InpSymbols     = "BTCUSD,XAUUSD,NAS100,US30"; // Symbols (use your broker's names)
input ENUM_TIMEFRAMES InpTF = PERIOD_M1;                    // Timeframe

input group "Risk & bracket"
input double InpRiskPercent = 0.5;   // Risk per trade, % of equity
input double InpRR          = 3.0;   // Reward : risk (target = RR x risk)
input double InpBETrigger   = 1.0;   // Move SL to break-even at this many R (0 = off)
input double InpBEBuffer    = 0.1;   // ...placed this many R beyond entry
input double InpMinStopATR  = 1.0;   // Stop never tighter than this x ATR
input double InpMaxStopATR  = 4.0;
input string InpMinStopPrice = "XAU=10";  // Per-symbol minimum stop in price, e.g. "XAU=10,BTC=150" (symbol prefix=value)   // Skip setup if swing stop wider than this x ATR
input int    InpSwingBars   = 10;    // Swing high/low lookback for the stop
input int    InpMaxSpreadPts = 0;    // Skip entries when spread above this (points, 0 = off)

input group "Trend / consolidation filter"
input int    InpEmaFast   = 20;
input int    InpEmaMid    = 50;
input int    InpEmaSlow   = 200;
input int    InpSlopeBars = 10;      // EMA(mid) must be rising/falling over this many bars
input int    InpAdxPeriod = 14;
input double InpAdxMin    = 25;      // ADX above this = trending
input int    InpChopPeriod = 14;
input double InpChopMax   = 50;      // Choppiness below this = not ranging
input int    InpAtrPeriod = 14;

input group "Session (server time, 0/0 = always)"
input int    InpSessionStart = 0;
input int    InpSessionEnd   = 0;

input ulong  InpMagic = 20261017;

struct Market
  {
   string   sym;
   int      hFast, hMid, hSlow, hAdx, hAtr;
   datetime lastBar;
  };

Market mk[];
CTrade trade;

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
   ArrayResize(mk, 0);
   for(int i = 0; i < n; i++)
     {
      string s = parts[i];
      StringTrimLeft(s); StringTrimRight(s);
      if(s == "") continue;
      if(!SymbolSelect(s, true)) { Print("Symbol not found at this broker: ", s); continue; }
      Market m;
      m.sym = s;
      m.hFast = iMA(s, InpTF, InpEmaFast, 0, MODE_EMA, PRICE_CLOSE);
      m.hMid  = iMA(s, InpTF, InpEmaMid, 0, MODE_EMA, PRICE_CLOSE);
      m.hSlow = iMA(s, InpTF, InpEmaSlow, 0, MODE_EMA, PRICE_CLOSE);
      m.hAdx  = iADXWilder(s, InpTF, InpAdxPeriod);
      m.hAtr  = iATR(s, InpTF, InpAtrPeriod);
      m.lastBar = 0;
      if(m.hFast == INVALID_HANDLE || m.hMid == INVALID_HANDLE || m.hSlow == INVALID_HANDLE ||
         m.hAdx == INVALID_HANDLE || m.hAtr == INVALID_HANDLE)
        { Print("Indicator init failed for ", s); continue; }
      int k = ArraySize(mk);
      ArrayResize(mk, k + 1);
      mk[k] = m;
     }
   if(ArraySize(mk) == 0) return INIT_FAILED;
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
//| Minimum stop distance for a symbol from InpMinStopPrice           |
//+------------------------------------------------------------------+
double MinStopFor(string s)
  {
   string items[];
   int n = StringSplit(InpMinStopPrice, ',', items);
   for(int i = 0; i < n; i++)
     {
      string kv[];
      if(StringSplit(items[i], '=', kv) != 2) continue;
      string k = kv[0]; StringTrimLeft(k); StringTrimRight(k);
      if(k != "" && StringFind(s, k) == 0) return StringToDouble(kv[1]);
     }
   return 0.0;
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

bool InSession()
  {
   if(InpSessionStart == InpSessionEnd) return true;
   MqlDateTime t; TimeCurrent(t);
   if(InpSessionStart < InpSessionEnd) return t.hour >= InpSessionStart && t.hour < InpSessionEnd;
   return t.hour >= InpSessionStart || t.hour < InpSessionEnd;
  }

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
   if(lots < SymbolInfoDouble(s, SYMBOL_VOLUME_MIN)) return 0;   // never exceed the risk budget
   return MathMin(lots, SymbolInfoDouble(s, SYMBOL_VOLUME_MAX));
  }

//+------------------------------------------------------------------+
//| Break-even: once price has gone BETrigger x R in our favour, move |
//| the stop to entry + BEBuffer x R.  R is recovered from the TP     |
//| (TP = entry +/- RR x R), so it survives terminal restarts.        |
//+------------------------------------------------------------------+
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
      if(sl < be && SymbolInfoDouble(s, SYMBOL_BID) >= open + InpBETrigger * R)
         trade.PositionModify(ticket, be, tp);
     }
   else
     {
      double be = NormalizeDouble(open - InpBEBuffer * R, dg);
      if((sl == 0 || sl > be) && SymbolInfoDouble(s, SYMBOL_ASK) <= open - InpBETrigger * R)
         trade.PositionModify(ticket, be, tp);
     }
  }

//+------------------------------------------------------------------+
//| Signal on the last closed bar: +1 long, -1 short, 0 none          |
//+------------------------------------------------------------------+
int Signal(Market &m, double &dist)
  {
   string s = m.sym;
   dist = 0;
   if(Bars(s, InpTF) < InpEmaSlow + 50) return 0;
   double c1 = iClose(s, InpTF, 1), h1 = iHigh(s, InpTF, 1), l1 = iLow(s, InpTF, 1);
   double h2 = iHigh(s, InpTF, 2), l2 = iLow(s, InpTF, 2);
   double f1 = Buf(m.hFast, 0, 1), f2 = Buf(m.hFast, 0, 2);
   double m1 = Buf(m.hMid, 0, 1), mS = Buf(m.hMid, 0, 1 + InpSlopeBars);
   double s1 = Buf(m.hSlow, 0, 1);
   double adx = Buf(m.hAdx, 0, 1), atr = Buf(m.hAtr, 0, 1);
   if(f1 == EMPTY_VALUE || f2 == EMPTY_VALUE || m1 == EMPTY_VALUE || mS == EMPTY_VALUE ||
      s1 == EMPTY_VALUE || adx == EMPTY_VALUE || atr == EMPTY_VALUE || atr <= 0) return 0;

   bool trending = adx > InpAdxMin && Choppiness(s, 1) < InpChopMax;
   if(!trending) return 0;                                  // consolidation: stand aside

   bool up = m1 > s1 && c1 > m1 && m1 > mS;
   bool dn = m1 < s1 && c1 < m1 && m1 < mS;

   if(up && l2 <= f2 && c1 > f1 && c1 > h2)
     {
      double swing = iLow(s, InpTF, iLowest(s, InpTF, MODE_LOW, InpSwingBars, 1));
      dist = MathMax(c1 - swing, MathMax(InpMinStopATR * atr, MinStopFor(s)));
      return dist <= MathMax(InpMaxStopATR * atr, MinStopFor(s)) ? 1 : 0;
     }
   if(dn && h2 >= f2 && c1 < f1 && c1 < l2)
     {
      double swing = iHigh(s, InpTF, iHighest(s, InpTF, MODE_HIGH, InpSwingBars, 1));
      dist = MathMax(swing - c1, MathMax(InpMinStopATR * atr, MinStopFor(s)));
      return dist <= MathMax(InpMaxStopATR * atr, MinStopFor(s)) ? -1 : 0;
     }
   return 0;
  }

void Process()
  {
   for(int i = 0; i < ArraySize(mk); i++)
     {
      string s = mk[i].sym;
      ulong ticket = 0;
      bool inPos = HasPosition(s, ticket);
      if(inPos) ManageBreakEven(s, ticket);              // every tick / second

      datetime t0 = iTime(s, InpTF, 0);
      if(t0 == 0 || t0 == mk[i].lastBar) continue;       // entries only at a new bar's open
      mk[i].lastBar = t0;
      if(inPos || !InSession()) continue;
      if(InpMaxSpreadPts > 0 && SymbolInfoInteger(s, SYMBOL_SPREAD) > InpMaxSpreadPts) continue;

      double dist;
      int sig = Signal(mk[i], dist);
      if(sig == 0) continue;
      double lots = LotsForRisk(s, dist);
      if(lots <= 0) { Print(s, ": lot size below broker minimum for this risk - skipped"); continue; }
      int dg = (int)SymbolInfoInteger(s, SYMBOL_DIGITS);
      if(sig == 1)
        {
         double px = SymbolInfoDouble(s, SYMBOL_ASK);
         trade.Buy(lots, s, px, NormalizeDouble(px - dist, dg), NormalizeDouble(px + InpRR * dist, dg), "TrendRider");
        }
      else
        {
         double px = SymbolInfoDouble(s, SYMBOL_BID);
         trade.Sell(lots, s, px, NormalizeDouble(px + dist, dg), NormalizeDouble(px - InpRR * dist, dg), "TrendRider");
        }
     }
  }

void OnTick()  { Process(); }
void OnTimer() { Process(); }
//+------------------------------------------------------------------+
