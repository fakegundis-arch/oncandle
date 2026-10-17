//+------------------------------------------------------------------+
//|                                                  GoldMacdV3.mq5  |
//|  Gold MACD v3 (results/macd/REPORT.md, section v3). XAUUSD H2.    |
//|  Signals = v2: MACD(12,26,9) signal-line cross with the close on  |
//|  the right side of EMA(100). Stop 2 x ATR(14), target 3R; an      |
//|  opposite cross closes the trade (and reverses it if the cross    |
//|  passes the EMA filter).                                          |
//|  v3 adds:                                                         |
//|   1. Break-even: at +1.5R the stop moves to entry + 0.3R.         |
//|   2. Cool-down: after 5 real losses in a row, real trading pauses;|
//|      every signal is still traded on paper and the pause ends     |
//|      after the first winning paper trade.                         |
//|  Pause state is kept in terminal global variables.                |
//+------------------------------------------------------------------+
#property copyright "oncandle"
#property version   "3.00"

#include <Trade/Trade.mqh>

input int    InpMacdFast     = 12;
input int    InpMacdSlow     = 26;
input int    InpMacdSignal   = 9;
input int    InpTrendEMA     = 100;
input double InpStopATR      = 2.0;   // Stop = this x ATR(14)
input double InpRR           = 3.0;   // Target = RR x stop
input double InpBETrigger    = 1.5;   // Move stop at this many R (0 = off)
input double InpBEBuffer     = 0.3;   // ...to entry + this many R
input int    InpCoolLosses   = 5;     // Pause after this many losses in a row (0 = off)
input bool   InpReverse      = true;
input double InpRiskPercent  = 4.0;   // Risk per trade, % of equity
input int    InpMaxSpreadPts = 0;
input ulong  InpMagic        = 20261106;

CTrade   trade;
int      hMacd = INVALID_HANDLE, hEma = INVALID_HANDLE, hAtr = INVALID_HANDLE;
datetime lastBar = 0;

// paper position (always follows the v2 signals)
int    vPos = 0;
double vEntry = 0, vStop = 0, vTgt = 0, vR = 0;
bool   vMoved = false, vReal = false;

string GV(string k) { return StringFormat("GMV3_%I64u_%s", InpMagic, k); }
bool   Paused()      { return GlobalVariableGet(GV("paused")) > 0.5; }

double B(int h, int buf, int s)
  {
   double v[1];
   if(CopyBuffer(h, buf, s, 1, v) != 1) return EMPTY_VALUE;
   return v[0];
  }

int OnInit()
  {
   trade.SetExpertMagicNumber(InpMagic);
   hMacd = iMACD(_Symbol, _Period, InpMacdFast, InpMacdSlow, InpMacdSignal, PRICE_CLOSE);
   hEma = iMA(_Symbol, _Period, InpTrendEMA, 0, MODE_EMA, PRICE_CLOSE);
   hAtr = iATR(_Symbol, _Period, 14);
   if(hMacd == INVALID_HANDLE || hEma == INVALID_HANDLE || hAtr == INVALID_HANDLE) return INIT_FAILED;
   if(_Period != PERIOD_H2) Print("Warning: v3 was tested on H2");
   if(!GlobalVariableCheck(GV("paused"))) { GlobalVariableSet(GV("paused"), 0); GlobalVariableSet(GV("run"), 0); }
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason) { IndicatorRelease(hMacd); IndicatorRelease(hEma); IndicatorRelease(hAtr); }

ulong RealTicket()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == (long)InpMagic) return t;
     }
   return 0;
  }

double LotsForRisk(double dist)
  {
   double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
   double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tv <= 0 || ts <= 0 || dist <= 0) return 0;
   double lots = AccountInfoDouble(ACCOUNT_EQUITY) * InpRiskPercent / 100.0 / (dist / ts * tv);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   lots = MathFloor(lots / step) * step;
   if(lots < SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN)) return 0;
   return MathMin(lots, SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX));
  }

// a paper trade closed with result r (in R): update the loss run / pause
void OnPaperClose(double r)
  {
   if(vReal)
     {
      double run = r < 0 ? GlobalVariableGet(GV("run")) + 1 : 0;
      if(InpCoolLosses > 0 && run >= InpCoolLosses) { GlobalVariableSet(GV("paused"), 1); run = 0; }
      GlobalVariableSet(GV("run"), run);
     }
   else if(Paused() && r > 0)
      GlobalVariableSet(GV("paused"), 0);
   vPos = 0; vReal = false;
  }

void ClosePaper(double px)
  {
   if(vPos == 0) return;
   OnPaperClose(vPos * (px - vEntry) / vR);
   ulong t = RealTicket();
   if(t > 0) trade.PositionClose(t);
  }

void OpenPaper(int dir, double atr)
  {
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID), ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   vPos = dir; vR = InpStopATR * atr; vMoved = false;
   vEntry = dir == 1 ? ask : bid;
   vStop = vEntry - dir * vR; vTgt = vEntry + dir * InpRR * vR;
   vReal = false;
   if(Paused()) return;
   if(InpMaxSpreadPts > 0 && SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) > InpMaxSpreadPts) return;
   double lots = LotsForRisk(vR);
   if(lots <= 0) { Print("Lot size below broker minimum for this risk - skipped"); return; }
   int dg = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   vReal = dir == 1 ? trade.Buy(lots, _Symbol, ask, NormalizeDouble(vStop, dg), NormalizeDouble(vTgt, dg), "GoldMacdV3")
                    : trade.Sell(lots, _Symbol, bid, NormalizeDouble(vStop, dg), NormalizeDouble(vTgt, dg), "GoldMacdV3");
  }

// tick-level management of the paper trade (stop / target / break-even); mirrors the real trade's stop
void ManagePaper()
  {
   if(vPos == 0) return;
   double px = vPos == 1 ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if((vPos == 1 && px <= vStop) || (vPos == -1 && px >= vStop)) { OnPaperClose(vPos * (vStop - vEntry) / vR); return; }
   if((vPos == 1 && px >= vTgt) || (vPos == -1 && px <= vTgt))   { OnPaperClose(vPos * (vTgt - vEntry) / vR); return; }
   if(InpBETrigger > 0 && !vMoved && vPos * (px - vEntry) >= InpBETrigger * vR)
     {
      vStop = vEntry + vPos * InpBEBuffer * vR;
      vMoved = true;
      ulong t = RealTicket();
      if(t > 0 && PositionSelectByTicket(t))
         trade.PositionModify(t, NormalizeDouble(vStop, (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS)), PositionGetDouble(POSITION_TP));
     }
  }

void OnTick()
  {
   ManagePaper();
   datetime t0 = iTime(_Symbol, _Period, 0);
   if(t0 == lastBar) return;
   lastBar = t0;
   if(Bars(_Symbol, _Period) < InpTrendEMA + 50) return;

   double m1 = B(hMacd, 0, 1), s1 = B(hMacd, 1, 1), m2 = B(hMacd, 0, 2), s2 = B(hMacd, 1, 2);
   double e1 = B(hEma, 0, 1), atr = B(hAtr, 0, 1), c1 = iClose(_Symbol, _Period, 1);
   if(m1 == EMPTY_VALUE || s1 == EMPTY_VALUE || m2 == EMPTY_VALUE || s2 == EMPTY_VALUE || e1 == EMPTY_VALUE ||
      atr == EMPTY_VALUE || atr <= 0) return;
   bool crossUp = m1 > s1 && m2 <= s2, crossDn = m1 < s1 && m2 >= s2;
   bool le = crossUp && c1 > e1, se = crossDn && c1 < e1;
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID), ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);

   if(vPos == 1 && crossDn)  { ClosePaper(bid); if(se && InpReverse) OpenPaper(-1, atr); return; }
   if(vPos == -1 && crossUp) { ClosePaper(ask); if(le && InpReverse) OpenPaper(1, atr); return; }
   if(vPos == 0)
     {
      if(le) OpenPaper(1, atr);
      else if(se) OpenPaper(-1, atr);
     }
  }
//+------------------------------------------------------------------+
