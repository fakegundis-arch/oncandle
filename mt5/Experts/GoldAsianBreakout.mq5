//+------------------------------------------------------------------+
//|                                           GoldAsianBreakout.mq5  |
//|  Winner of the 10%-risk deep search (results/deep/REPORT.md).     |
//|  Attach to XAUUSD M15. Only opens trades in the Asian session     |
//|  (Tokyo 09:00-15:00 = 00:00-06:00 on a GMT+0 server).             |
//|   Entry : close breaks above the highest high of the previous     |
//|           20 bars (below the lowest low for shorts) while the     |
//|           ~50-hour trend agrees: price above EMA(200 x M15) and   |
//|           that EMA higher than 1 hour ago.                        |
//|   Stop  : 1.5 x ATR(14)   Target: 3R                              |
//|   At +1R the stop moves to entry + 0.1R.                          |
//+------------------------------------------------------------------+
#property copyright "oncandle"
#property version   "1.00"

#include <Trade/Trade.mqh>

input int    InpDonchian     = 20;    // Breakout lookback (bars)
input int    InpTrendEMA     = 200;   // Trend EMA (200 x M15 = 50 hours)
input int    InpSlopeBars    = 4;     // EMA must be rising/falling vs this many bars ago
input double InpStopATR      = 1.5;   // Stop = this x ATR(14)
input double InpMinStop      = 2.0;   // Minimum stop distance in price ($)
input double InpRR           = 3.0;   // Target = RR x stop
input double InpBETrigger    = 1.0;   // Move stop to break-even at this many R (0 = off)
input double InpBEBuffer     = 0.1;   // ...this many R past entry
input double InpRiskPercent  = 10.0;  // Risk per trade, % of equity
input int    InpSessionStart = 0;     // Server hour: first hour to open trades
input int    InpSessionEnd   = 6;     // Server hour: stop opening trades from this hour
input int    InpMaxSpreadPts = 0;     // Skip entries above this spread (points, 0 = off)
input ulong  InpMagic        = 20261022;

CTrade   trade;
int      hEma = INVALID_HANDLE, hAtr = INVALID_HANDLE;
datetime lastBar = 0;

double Buf(int h, int s)
  {
   double v[1];
   if(CopyBuffer(h, 0, s, 1, v) != 1) return EMPTY_VALUE;
   return v[0];
  }

int OnInit()
  {
   trade.SetExpertMagicNumber(InpMagic);
   hEma = iMA(_Symbol, _Period, InpTrendEMA, 0, MODE_EMA, PRICE_CLOSE);
   hAtr = iATR(_Symbol, _Period, 14);
   if(hEma == INVALID_HANDLE || hAtr == INVALID_HANDLE) return INIT_FAILED;
   if(_Period != PERIOD_M15) Print("Warning: tested on M15 only");
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason) { IndicatorRelease(hEma); IndicatorRelease(hAtr); }

bool HasPosition(ulong &ticket)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == (long)InpMagic)
        { ticket = t; return true; }
     }
   return false;
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

void ManageBreakEven(ulong ticket)
  {
   if(InpBETrigger <= 0 || !PositionSelectByTicket(ticket)) return;
   double open = PositionGetDouble(POSITION_PRICE_OPEN);
   double sl = PositionGetDouble(POSITION_SL), tp = PositionGetDouble(POSITION_TP);
   if(tp == 0) return;
   double R = MathAbs(tp - open) / InpRR;
   int dg = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
     {
      double be = NormalizeDouble(open + InpBEBuffer * R, dg);
      if(sl < be && SymbolInfoDouble(_Symbol, SYMBOL_BID) >= open + InpBETrigger * R) trade.PositionModify(ticket, be, tp);
     }
   else
     {
      double be = NormalizeDouble(open - InpBEBuffer * R, dg);
      if((sl == 0 || sl > be) && SymbolInfoDouble(_Symbol, SYMBOL_ASK) <= open - InpBETrigger * R) trade.PositionModify(ticket, be, tp);
     }
  }

void OnTick()
  {
   ulong ticket = 0;
   bool inPos = HasPosition(ticket);
   if(inPos) ManageBreakEven(ticket);

   datetime t0 = iTime(_Symbol, _Period, 0);
   if(t0 == lastBar) return;
   lastBar = t0;
   if(inPos || Bars(_Symbol, _Period) < InpTrendEMA + InpDonchian + 10) return;

   MqlDateTime bt; TimeToStruct(iTime(_Symbol, _Period, 1), bt);       // signal bar's start hour
   bool inSession = InpSessionStart < InpSessionEnd ? (bt.hour >= InpSessionStart && bt.hour < InpSessionEnd)
                                                    : (bt.hour >= InpSessionStart || bt.hour < InpSessionEnd);
   if(!inSession) return;
   if(InpMaxSpreadPts > 0 && SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) > InpMaxSpreadPts) return;

   double c1 = iClose(_Symbol, _Period, 1), c2 = iClose(_Symbol, _Period, 2);
   double up1 = iHigh(_Symbol, _Period, iHighest(_Symbol, _Period, MODE_HIGH, InpDonchian, 2));
   double up2 = iHigh(_Symbol, _Period, iHighest(_Symbol, _Period, MODE_HIGH, InpDonchian, 3));
   double dn1 = iLow(_Symbol, _Period, iLowest(_Symbol, _Period, MODE_LOW, InpDonchian, 2));
   double dn2 = iLow(_Symbol, _Period, iLowest(_Symbol, _Period, MODE_LOW, InpDonchian, 3));
   double e1 = Buf(hEma, 1), eS = Buf(hEma, 1 + InpSlopeBars), atr = Buf(hAtr, 1);
   if(e1 == EMPTY_VALUE || eS == EMPTY_VALUE || atr == EMPTY_VALUE || atr <= 0) return;

   int dir = 0;
   if(c1 > up1 && c2 <= up2 && c1 > e1 && e1 > eS) dir = 1;
   else if(c1 < dn1 && c2 >= dn2 && c1 < e1 && e1 < eS) dir = -1;
   if(dir == 0) return;

   double dist = MathMax(InpStopATR * atr, InpMinStop);
   double lots = LotsForRisk(dist);
   if(lots <= 0) { Print("Lot size below broker minimum for this risk - skipped"); return; }
   int dg = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   if(dir == 1)
     {
      double px = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      trade.Buy(lots, _Symbol, px, NormalizeDouble(px - dist, dg), NormalizeDouble(px + InpRR * dist, dg), "GoldAsian");
     }
   else
     {
      double px = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      trade.Sell(lots, _Symbol, px, NormalizeDouble(px + dist, dg), NormalizeDouble(px - InpRR * dist, dg), "GoldAsian");
     }
  }
//+------------------------------------------------------------------+
