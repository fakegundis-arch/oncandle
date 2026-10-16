//+------------------------------------------------------------------+
//|                                               TrendRiderV2.mq5   |
//|  Attach to an M1 chart (built for XAUUSD).                        |
//|  Trend is judged on COMPLETED M5 candles and held through         |
//|  pullbacks; entries are timed on M1 pullbacks to EMA20.           |
//|  Mirrors backtester/trend_rider_v2.py.                            |
//+------------------------------------------------------------------+
#property copyright "oncandle"
#property version   "2.00"

#include <Trade/Trade.mqh>

input group "Trend (higher timeframe)"
input ENUM_TIMEFRAMES InpHTF = PERIOD_M5;
input int    InpHtfFast   = 20;     // HTF EMA fast
input int    InpHtfSlow   = 50;     // HTF EMA slow
input int    InpSlopeBars = 3;      // HTF EMA fast must be rising/falling over this many bars
input int    InpAdxPeriod = 14;
input double InpAdxMin    = 20;     // HTF ADX above this
input int    InpErBars    = 12;     // Efficiency ratio lookback (HTF bars)
input double InpErMin     = 0.30;   // Clean move: efficiency ratio above this

input group "Entry (M1)"
input int    InpM1Ema     = 20;     // Pullback EMA
input double InpTouchATR  = 0.2;    // Pullback counts if within this x ATR of the EMA

input group "Risk & bracket"
input double InpRiskPercent = 0.5;
input double InpRR          = 3.0;
input double InpBETrigger   = 1.0;  // Move SL to break-even at this many R (0 = off)
input double InpBEBuffer    = 0.1;
input double InpMinStopPrice = 10.0;// Minimum stop distance in price ($10 on gold)
input double InpMinStopATR  = 1.0;
input double InpMaxStopATR  = 6.0;
input int    InpSwingBars   = 15;
input int    InpAtrPeriod   = 14;
input int    InpMaxSpreadPts = 0;
input ulong  InpMagic = 20261020;

CTrade   trade;
int      hF, hS, hAdx, hE20, hE50, hE200, hAtr;
datetime lastBar = 0;

double Buf(int h, int b, int s)
  {
   double v[1];
   if(CopyBuffer(h, b, s, 1, v) != 1) return EMPTY_VALUE;
   return v[0];
  }

int OnInit()
  {
   trade.SetExpertMagicNumber(InpMagic);
   hF    = iMA(_Symbol, InpHTF, InpHtfFast, 0, MODE_EMA, PRICE_CLOSE);
   hS    = iMA(_Symbol, InpHTF, InpHtfSlow, 0, MODE_EMA, PRICE_CLOSE);
   hAdx  = iADXWilder(_Symbol, InpHTF, InpAdxPeriod);
   hE20  = iMA(_Symbol, PERIOD_M1, InpM1Ema, 0, MODE_EMA, PRICE_CLOSE);
   hE50  = iMA(_Symbol, PERIOD_M1, 50, 0, MODE_EMA, PRICE_CLOSE);
   hE200 = iMA(_Symbol, PERIOD_M1, 200, 0, MODE_EMA, PRICE_CLOSE);
   hAtr  = iATR(_Symbol, PERIOD_M1, InpAtrPeriod);
   if(hF == INVALID_HANDLE || hS == INVALID_HANDLE || hAdx == INVALID_HANDLE || hE20 == INVALID_HANDLE ||
      hE50 == INVALID_HANDLE || hE200 == INVALID_HANDLE || hAtr == INVALID_HANDLE) return INIT_FAILED;
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   IndicatorRelease(hF); IndicatorRelease(hS); IndicatorRelease(hAdx);
   IndicatorRelease(hE20); IndicatorRelease(hE50); IndicatorRelease(hE200); IndicatorRelease(hAtr);
  }

//+------------------------------------------------------------------+
//| Trend regime from completed HTF bars, replayed over a window so   |
//| the hold-through-pullback state matches the backtest.             |
//+------------------------------------------------------------------+
int Regime()
  {
   int n = 300;
   if(Bars(_Symbol, InpHTF) < n + InpHtfSlow + InpErBars + 10) return 0;
   double f[], s[], adx[], c[];
   ArraySetAsSeries(f, true); ArraySetAsSeries(s, true); ArraySetAsSeries(adx, true); ArraySetAsSeries(c, true);
   int need = n + InpSlopeBars + InpErBars + 1;
   if(CopyBuffer(hF, 0, 1, need, f) != need || CopyBuffer(hS, 0, 1, need, s) != need ||
      CopyBuffer(hAdx, 0, 1, need, adx) != need || CopyClose(_Symbol, InpHTF, 1, need, c) != need) return 0;
   int reg = 0;
   for(int k = n - 1; k >= 0; k--)               // oldest -> newest completed HTF bar
     {
      double path = 0;
      for(int j = k; j < k + InpErBars; j++) path += MathAbs(c[j] - c[j + 1]);
      double er = path > 0 ? MathAbs(c[k] - c[k + InpErBars]) / path : 0;
      bool clean = adx[k] > InpAdxMin && er > InpErMin;
      bool startUp = f[k] > s[k] && f[k] > f[k + InpSlopeBars] && c[k] > f[k] && clean;
      bool startDn = f[k] < s[k] && f[k] < f[k + InpSlopeBars] && c[k] < f[k] && clean;
      if(startUp)                                   reg = 1;
      else if(startDn)                              reg = -1;
      else if(reg == 1 && f[k] > s[k] && c[k] > s[k])  reg = 1;   // hold through pullbacks
      else if(reg == -1 && f[k] < s[k] && c[k] < s[k]) reg = -1;
      else                                          reg = 0;
     }
   return reg;
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

   datetime t0 = iTime(_Symbol, PERIOD_M1, 0);
   if(t0 == lastBar) return;
   lastBar = t0;
   if(inPos || Bars(_Symbol, PERIOD_M1) < 400) return;
   if(InpMaxSpreadPts > 0 && SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) > InpMaxSpreadPts) return;

   int reg = Regime();
   if(reg == 0) return;

   double c1 = iClose(_Symbol, PERIOD_M1, 1);
   double h2 = iHigh(_Symbol, PERIOD_M1, 2), l2 = iLow(_Symbol, PERIOD_M1, 2);
   double e1 = Buf(hE20, 0, 1), e2 = Buf(hE20, 0, 2);
   double m50 = Buf(hE50, 0, 1), m200 = Buf(hE200, 0, 1);
   double atr1 = Buf(hAtr, 0, 1), atr2 = Buf(hAtr, 0, 2);
   if(e1 == EMPTY_VALUE || e2 == EMPTY_VALUE || m50 == EMPTY_VALUE || m200 == EMPTY_VALUE ||
      atr1 == EMPTY_VALUE || atr2 == EMPTY_VALUE || atr1 <= 0) return;

   double floorD = MathMax(InpMinStopATR * atr1, InpMinStopPrice);
   double capD   = MathMax(InpMaxStopATR * atr1, InpMinStopPrice);
   int dg = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);

   if(reg == 1)
     {
      bool m1Up = e1 > m50 && m50 > m200 && c1 > m200;
      bool pullback = l2 <= e2 + InpTouchATR * atr2 && c1 > e1 && c1 > h2;
      if(!(m1Up && pullback)) return;
      double dist = MathMax(c1 - iLow(_Symbol, PERIOD_M1, iLowest(_Symbol, PERIOD_M1, MODE_LOW, InpSwingBars, 1)), floorD);
      if(dist > capD) return;
      double lots = LotsForRisk(dist);
      if(lots <= 0) { Print("Lot size below broker minimum for this risk - skipped"); return; }
      double px = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      trade.Buy(lots, _Symbol, px, NormalizeDouble(px - dist, dg), NormalizeDouble(px + InpRR * dist, dg), "TrendRiderV2");
     }
   else
     {
      bool m1Dn = e1 < m50 && m50 < m200 && c1 < m200;
      bool pullback = h2 >= e2 - InpTouchATR * atr2 && c1 < e1 && c1 < l2;
      if(!(m1Dn && pullback)) return;
      double dist = MathMax(iHigh(_Symbol, PERIOD_M1, iHighest(_Symbol, PERIOD_M1, MODE_HIGH, InpSwingBars, 1)) - c1, floorD);
      if(dist > capD) return;
      double lots = LotsForRisk(dist);
      if(lots <= 0) { Print("Lot size below broker minimum for this risk - skipped"); return; }
      double px = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      trade.Sell(lots, _Symbol, px, NormalizeDouble(px + dist, dg), NormalizeDouble(px - InpRR * dist, dg), "TrendRiderV2");
     }
  }
//+------------------------------------------------------------------+
