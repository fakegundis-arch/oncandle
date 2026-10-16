//+------------------------------------------------------------------+
//|                                                     RunFade.mq5  |
//|  High-win-rate mean reversion. After RunLen candles in a row of   |
//|  the same colour that together moved >= MinMoveATR x ATR(14),     |
//|  trade AGAINST the run for a small snap-back:                     |
//|    target = TP_ATR x ATR, stop = SL_ATR x ATR, time exit MaxBars. |
//|  Mirrors backtester/hwr.py run_fade().                            |
//|                                                                   |
//|  Tested presets (attach one EA per chart, different Magic each):  |
//|    BTCUSD H1 : RunLen 4, MinMove 2.5, TP 0.5, SL 4.0, MaxBars 30  |
//|    US30   H4 : RunLen 4, MinMove 1.5, TP 0.3, SL 3.0, MaxBars 10  |
//|    XAUUSD H1 : RunLen 4, MinMove 3.0, TP 0.5, SL 4.0, MaxBars 10  |
//+------------------------------------------------------------------+
#property copyright "oncandle"
#property version   "1.00"

#include <Trade/Trade.mqh>

input int    InpRunLen      = 4;     // Same-colour candles in a row
input double InpMinMoveATR  = 2.5;   // The run must have moved at least this x ATR
input double InpTP_ATR      = 0.5;   // Take profit, x ATR (small)
input double InpSL_ATR      = 4.0;   // Stop loss, x ATR (wide)
input int    InpMaxBars     = 30;    // Close the trade after this many bars (0 = off)
input double InpRiskPercent = 1.0;   // Risk per trade (% of equity lost if the stop is hit)
input int    InpAtrPeriod   = 14;
input int    InpMaxSpreadPts = 0;    // Skip entries above this spread (points, 0 = off)
input ulong  InpMagic       = 20261021;

CTrade   trade;
int      hAtr = INVALID_HANDLE;
datetime lastBar = 0;

int OnInit()
  {
   trade.SetExpertMagicNumber(InpMagic);
   hAtr = iATR(_Symbol, _Period, InpAtrPeriod);
   return hAtr == INVALID_HANDLE ? INIT_FAILED : INIT_SUCCEEDED;
  }

void OnDeinit(const int reason) { IndicatorRelease(hAtr); }

double Atr(int s)
  {
   double v[1];
   if(CopyBuffer(hAtr, 0, s, 1, v) != 1) return 0;
   return v[0];
  }

// Signed run length ending at bar `sh`: +n green, -n red, 0 doji.
int RunLength(int sh)
  {
   int n = 0, dir = 0;
   for(int i = sh; i < sh + 50; i++)
     {
      double o = iOpen(_Symbol, _Period, i), c = iClose(_Symbol, _Period, i);
      int col = c > o ? 1 : (c < o ? -1 : 0);
      if(col == 0 || (dir != 0 && col != dir)) break;
      dir = col;
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
   if(lots < SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN)) return 0;   // never exceed the risk budget
   return MathMin(lots, SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX));
  }

void OnTick()
  {
   datetime t0 = iTime(_Symbol, _Period, 0);
   if(t0 == lastBar) return;                       // act once per bar, at its open
   lastBar = t0;

   ulong ticket = 0;
   if(HasPosition(ticket))
     {
      // time exit: close once the trade has been open for MaxBars completed bars
      if(InpMaxBars > 0 && PositionSelectByTicket(ticket))
        {
         int held = iBarShift(_Symbol, _Period, (datetime)PositionGetInteger(POSITION_TIME));
         if(held >= InpMaxBars) trade.PositionClose(ticket);
        }
      return;
     }
   if(Bars(_Symbol, _Period) < 100) return;
   if(InpMaxSpreadPts > 0 && SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) > InpMaxSpreadPts) return;

   int run = RunLength(1);
   if(MathAbs(run) != InpRunLen) return;            // fires once, on the bar the run reaches RunLen
   double atr = Atr(1);
   if(atr <= 0) return;
   double move = MathAbs(iClose(_Symbol, _Period, 1) - iOpen(_Symbol, _Period, InpRunLen));
   if(move < InpMinMoveATR * atr) return;           // run must be a real, stretched move

   int dir = run > 0 ? -1 : 1;                      // FADE the run
   double sl = InpSL_ATR * atr, tp = InpTP_ATR * atr;
   double lots = LotsForRisk(sl);
   if(lots <= 0) { Print("Lot size below broker minimum for this risk - skipped"); return; }
   int dg = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   if(dir == 1)
     {
      double px = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      trade.Buy(lots, _Symbol, px, NormalizeDouble(px - sl, dg), NormalizeDouble(px + tp, dg), "RunFade");
     }
   else
     {
      double px = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      trade.Sell(lots, _Symbol, px, NormalizeDouble(px + sl, dg), NormalizeDouble(px - tp, dg), "RunFade");
     }
  }
//+------------------------------------------------------------------+
