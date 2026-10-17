//+------------------------------------------------------------------+
//|                                                  GoldMacdV2.mq5  |
//|  Gold MACD v2 (results/macd/REPORT.md). Attach to XAUUSD H2.      |
//|  Long when MACD(12,26,9) crosses above its signal line and the    |
//|  close is above EMA(100); short mirrors.                          |
//|  Stop 2 x ATR(14), target 3R. An opposite MACD cross closes the   |
//|  trade at the next bar's open, and reverses it if that cross also |
//|  passes the EMA filter.                                           |
//|  v1 = H4, stop 3 ATR, no target (OnCandleTrend.mq5, MACD preset). |
//|  Mirrors backtester/macd.py (tf 2h, stop_atr 2, rr 3).            |
//+------------------------------------------------------------------+
#property copyright "oncandle"
#property version   "2.00"

#include <Trade/Trade.mqh>

input int    InpMacdFast     = 12;
input int    InpMacdSlow     = 26;
input int    InpMacdSignal   = 9;
input int    InpTrendEMA     = 100;   // Trend filter EMA on the chart timeframe
input double InpStopATR      = 2.0;   // Stop = this x ATR(14)
input double InpRR           = 3.0;   // Target = RR x stop (0 = no target)
input bool   InpReverse      = true;  // Opposite signal reverses the position
input double InpRiskPercent  = 4.0;   // Risk per trade, % of equity
input int    InpMaxSpreadPts = 0;     // Skip entries above this spread (points, 0 = off)
input ulong  InpMagic        = 20261105;

CTrade   trade;
int      hMacd = INVALID_HANDLE, hEma = INVALID_HANDLE, hAtr = INVALID_HANDLE;
datetime lastBar = 0;

double B(int h, int buf, int s)
  {
   double v[1];
   if(CopyBuffer(h, buf, s, 1, v) != 1) return EMPTY_VALUE;
   return v[0];
  }

int OnInit()
  {
   trade.SetExpertMagicNumber(InpMagic);
   hMacd = iMACD(_Symbol, _Period, InpMacdFast, InpMacdSlow, InpMacdSignal, PRICE_CLOSE);  // signal = SMA, as backtested
   hEma = iMA(_Symbol, _Period, InpTrendEMA, 0, MODE_EMA, PRICE_CLOSE);
   hAtr = iATR(_Symbol, _Period, 14);
   if(hMacd == INVALID_HANDLE || hEma == INVALID_HANDLE || hAtr == INVALID_HANDLE) return INIT_FAILED;
   if(_Period != PERIOD_H2) Print("Warning: v2 was tested on H2");
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason) { IndicatorRelease(hMacd); IndicatorRelease(hEma); IndicatorRelease(hAtr); }

int PositionDir(ulong &ticket)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == (long)InpMagic)
        { ticket = t; return PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1; }
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

void Open(int dir, double atr)
  {
   if(InpMaxSpreadPts > 0 && SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) > InpMaxSpreadPts) return;
   double dist = InpStopATR * atr;
   double lots = LotsForRisk(dist);
   if(lots <= 0) { Print("Lot size below broker minimum for this risk - skipped"); return; }
   int dg = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   if(dir == 1)
     {
      double px = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double tp = InpRR > 0 ? NormalizeDouble(px + InpRR * dist, dg) : 0;
      trade.Buy(lots, _Symbol, px, NormalizeDouble(px - dist, dg), tp, "GoldMacdV2");
     }
   else
     {
      double px = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double tp = InpRR > 0 ? NormalizeDouble(px - InpRR * dist, dg) : 0;
      trade.Sell(lots, _Symbol, px, NormalizeDouble(px + dist, dg), tp, "GoldMacdV2");
     }
  }

void OnTick()
  {
   datetime t0 = iTime(_Symbol, _Period, 0);
   if(t0 == lastBar) return;                    // decide once per bar, at its open
   lastBar = t0;
   if(Bars(_Symbol, _Period) < InpTrendEMA + 50) return;

   double m1 = B(hMacd, 0, 1), s1 = B(hMacd, 1, 1), m2 = B(hMacd, 0, 2), s2 = B(hMacd, 1, 2);
   double e1 = B(hEma, 0, 1), atr = B(hAtr, 0, 1), c1 = iClose(_Symbol, _Period, 1);
   if(m1 == EMPTY_VALUE || s1 == EMPTY_VALUE || m2 == EMPTY_VALUE || s2 == EMPTY_VALUE || e1 == EMPTY_VALUE ||
      atr == EMPTY_VALUE || atr <= 0) return;
   bool crossUp = m1 > s1 && m2 <= s2, crossDn = m1 < s1 && m2 >= s2;
   bool le = crossUp && c1 > e1, se = crossDn && c1 < e1;

   ulong ticket = 0;
   int pos = PositionDir(ticket);
   if(pos == 1 && crossDn)
     {
      trade.PositionClose(ticket);
      if(se && InpReverse) Open(-1, atr);
      return;
     }
   if(pos == -1 && crossUp)
     {
      trade.PositionClose(ticket);
      if(le && InpReverse) Open(1, atr);
      return;
     }
   if(pos == 0)
     {
      if(le) Open(1, atr);
      else if(se) Open(-1, atr);
     }
  }
//+------------------------------------------------------------------+
