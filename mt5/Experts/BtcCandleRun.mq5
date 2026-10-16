//+------------------------------------------------------------------+
//|                                                BtcCandleRun.mq5  |
//|  Strategy 3. Attach to a BTCUSD M1 chart. When RunLen candles in  |
//|  a row close the same colour and together moved >= MinMoveATR x   |
//|  ATR, join the move at the next bar's open. Stop beyond the start |
//|  of the run, 1:RR target, stop to break-even once price has gone  |
//|  BETrigger x risk in favour. Mirrors backtester/candle_run.py.    |
//+------------------------------------------------------------------+
#property copyright "oncandle"
#property version   "1.00"

#include <Trade/Trade.mqh>

input int    InpRunLen       = 4;     // Same-colour candles in a row
input double InpMinMoveATR   = 1.5;   // Run must move at least this x ATR
input int    InpTrendEMA     = 0;     // Only trade with EMA(n) trend (0 = off)
input double InpRiskPercent  = 0.5;   // Risk per trade, % of equity
input double InpRR           = 3.0;   // Reward : risk
input double InpBETrigger    = 1.0;   // Move SL to break-even at this many R (0 = off)
input double InpBEBuffer     = 0.1;   // ...this many R past entry
input double InpMinStopATR   = 1.0;
input double InpMaxStopATR   = 4.0;
input int    InpAtrPeriod    = 14;
input int    InpMaxSpreadPts = 0;     // Skip entries above this spread (points, 0 = off)
input ulong  InpMagic        = 20261019;

CTrade   trade;
int      hAtr = INVALID_HANDLE, hEma = INVALID_HANDLE;
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
   hAtr = iATR(_Symbol, _Period, InpAtrPeriod);
   if(InpTrendEMA > 0) hEma = iMA(_Symbol, _Period, InpTrendEMA, 0, MODE_EMA, PRICE_CLOSE);
   if(hAtr == INVALID_HANDLE || (InpTrendEMA > 0 && hEma == INVALID_HANDLE)) return INIT_FAILED;
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   IndicatorRelease(hAtr);
   if(hEma != INVALID_HANDLE) IndicatorRelease(hEma);
  }

// Signed run length ending at bar `sh`: +n green, -n red, 0 doji.
int RunLength(int sh)
  {
   int n = 0, dir = 0;
   for(int i = sh; i < sh + 100; i++)
     {
      double o = iOpen(_Symbol, _Period, i), c = iClose(_Symbol, _Period, i);
      int col = c > o ? 1 : (c < o ? -1 : 0);
      if(col == 0) break;
      if(dir == 0) dir = col;
      if(col != dir) break;
      n++;
     }
   return dir * n;
  }

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
   if(inPos) ManageBreakEven(ticket);                    // every tick

   datetime t0 = iTime(_Symbol, _Period, 0);
   if(t0 == lastBar) return;                             // entries only at a new bar's open
   lastBar = t0;
   if(inPos || Bars(_Symbol, _Period) < 300) return;
   if(InpMaxSpreadPts > 0 && SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) > InpMaxSpreadPts) return;

   int run = RunLength(1);
   if(MathAbs(run) != InpRunLen) return;                 // fire once, when the run reaches RunLen
   int dir = run > 0 ? 1 : -1;
   double atr = Buf(hAtr, 1);
   if(atr == EMPTY_VALUE || atr <= 0) return;
   double c1 = iClose(_Symbol, _Period, 1), firstOpen = iOpen(_Symbol, _Period, InpRunLen);
   if(MathAbs(c1 - firstOpen) < InpMinMoveATR * atr) return;   // not clearly moving
   if(InpTrendEMA > 0)
     {
      double e = Buf(hEma, 1);
      if(e == EMPTY_VALUE || (dir == 1 && c1 <= e) || (dir == -1 && c1 >= e)) return;
     }
   double dist = dir == 1 ? c1 - iLow(_Symbol, _Period, iLowest(_Symbol, _Period, MODE_LOW, InpRunLen, 1))
                          : iHigh(_Symbol, _Period, iHighest(_Symbol, _Period, MODE_HIGH, InpRunLen, 1)) - c1;
   dist = MathMax(dist, InpMinStopATR * atr);
   if(dist > InpMaxStopATR * atr) return;
   double lots = LotsForRisk(dist);
   if(lots <= 0) { Print("Lot size below broker minimum for this risk - skipped"); return; }
   int dg = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   if(dir == 1)
     {
      double px = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      trade.Buy(lots, _Symbol, px, NormalizeDouble(px - dist, dg), NormalizeDouble(px + InpRR * dist, dg), "CandleRun");
     }
   else
     {
      double px = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      trade.Sell(lots, _Symbol, px, NormalizeDouble(px + dist, dg), NormalizeDouble(px - InpRR * dist, dg), "CandleRun");
     }
  }
//+------------------------------------------------------------------+
