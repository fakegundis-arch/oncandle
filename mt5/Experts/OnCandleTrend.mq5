//+------------------------------------------------------------------+
//|                                               OnCandleTrend.mq5  |
//|  12 trend-following strategies in one EA, mirroring the Python   |
//|  backtester in this repo bar-for-bar:                            |
//|   * signals on the CLOSE of the last bar, orders at the next OPEN|
//|   * hard stop = StopATR x ATR(14) placed with every order        |
//|   * lot size so a stop-out loses RiskPercent of equity           |
//|   * optional chandelier trail = best close - TrailATR x ATR      |
//|   * opposite entry signal reverses the position                  |
//+------------------------------------------------------------------+
#property copyright "oncandle"
#property version   "1.00"

#include <Trade/Trade.mqh>

enum ENUM_STRATEGY
  {
   STRAT_EMA_CROSS = 0,   // EMA Crossover
   STRAT_DONCHIAN,        // Donchian Breakout
   STRAT_SUPERTREND,      // Supertrend
   STRAT_MACD,            // MACD + EMA Filter
   STRAT_ADX,             // ADX/DMI
   STRAT_KELTNER,         // Keltner Breakout
   STRAT_BOLLINGER,       // Bollinger Breakout
   STRAT_TRIPLE_EMA,      // Triple EMA
   STRAT_ICHIMOKU,        // Ichimoku
   STRAT_TSMOM,           // TS Momentum
   STRAT_PSAR,            // PSAR + EMA
   STRAT_KAMA             // KAMA Trend
  };

input group "General"
input ENUM_STRATEGY InpStrategy   = STRAT_TSMOM; // Strategy
input double InpRiskPercent       = 0.5;   // Risk per trade, % of equity
input double InpStopATR           = 3.0;   // Initial stop, x ATR
input double InpTrailATR          = 0.0;   // Chandelier trail, x ATR (0 = off)
input int    InpATRPeriod         = 14;    // ATR period for stops
input int    InpMaxSpreadPoints   = 0;     // Skip entries above this spread (0 = off)
input ulong  InpMagic             = 20261016;

input group "EMA Crossover"
input int    InpEmaFast = 20;
input int    InpEmaSlow = 50;

input group "Donchian Breakout"
input int    InpDonEntry = 55;
input int    InpDonExit  = 20;

input group "Supertrend"
input int    InpStPeriod = 10;
input double InpStMult   = 3.0;

input group "MACD + EMA Filter"
input int    InpMacdFast   = 12;
input int    InpMacdSlow   = 26;
input int    InpMacdSignal = 9;
input int    InpMacdTrend  = 200;

input group "ADX/DMI"
input int    InpAdxPeriod    = 14;
input double InpAdxThreshold = 25;

input group "Keltner Breakout"
input int    InpKcPeriod = 20;
input double InpKcMult   = 2.5;

input group "Bollinger Breakout"
input int    InpBbPeriod = 20;
input double InpBbDev    = 2.0;

input group "Triple EMA"
input int    InpTeFast = 20;
input int    InpTeMid  = 50;
input int    InpTeSlow = 200;

input group "Ichimoku"
input int    InpTenkan = 9;
input int    InpKijun  = 26;
input int    InpSenkou = 52;

input group "TS Momentum"
input int    InpMomLookback = 100;

input group "PSAR + EMA"
input double InpSarStep  = 0.02;
input int    InpSarTrend = 200;

input group "KAMA Trend"
input int    InpKamaPeriod = 10;
input int    InpKamaFast   = 2;
input int    InpKamaSlow   = 30;

CTrade   trade;
int      hATR = INVALID_HANDLE, h1 = INVALID_HANDLE, h2 = INVALID_HANDLE, h3 = INVALID_HANDLE;
datetime lastBar = 0;

//+------------------------------------------------------------------+
double Buf(int handle, int buffer, int shift)
  {
   double v[1];
   if(CopyBuffer(handle, buffer, shift, 1, v) != 1) return EMPTY_VALUE;
   return v[0];
  }
double C(int i) { return iClose(_Symbol, _Period, i); }
double H(int i) { return iHigh(_Symbol, _Period, i); }
double L(int i) { return iLow(_Symbol, _Period, i); }
double HH(int count, int start) { return H(iHighest(_Symbol, _Period, MODE_HIGH, count, start)); }
double LL(int count, int start) { return L(iLowest(_Symbol, _Period, MODE_LOW, count, start)); }
bool CrossUp(double a1, double b1, double a2, double b2) { return a1 > b1 && a2 <= b2; }
bool CrossDn(double a1, double b1, double a2, double b2) { return a1 < b1 && a2 >= b2; }

//+------------------------------------------------------------------+
int OnInit()
  {
   trade.SetExpertMagicNumber(InpMagic);
   hATR = iATR(_Symbol, _Period, InpATRPeriod);
   switch(InpStrategy)
     {
      case STRAT_EMA_CROSS:
         h1 = iMA(_Symbol, _Period, InpEmaFast, 0, MODE_EMA, PRICE_CLOSE);
         h2 = iMA(_Symbol, _Period, InpEmaSlow, 0, MODE_EMA, PRICE_CLOSE); break;
      case STRAT_SUPERTREND:
         h1 = iATR(_Symbol, _Period, InpStPeriod); break;
      case STRAT_MACD:
         h1 = iMACD(_Symbol, _Period, InpMacdFast, InpMacdSlow, InpMacdSignal, PRICE_CLOSE);
         h2 = iMA(_Symbol, _Period, InpMacdTrend, 0, MODE_EMA, PRICE_CLOSE); break;
      case STRAT_ADX:
         h1 = iADXWilder(_Symbol, _Period, InpAdxPeriod); break;
      case STRAT_KELTNER:
         h1 = iMA(_Symbol, _Period, InpKcPeriod, 0, MODE_EMA, PRICE_CLOSE);
         h2 = iATR(_Symbol, _Period, InpKcPeriod); break;
      case STRAT_BOLLINGER:
         h1 = iBands(_Symbol, _Period, InpBbPeriod, 0, InpBbDev, PRICE_CLOSE); break;
      case STRAT_TRIPLE_EMA:
         h1 = iMA(_Symbol, _Period, InpTeFast, 0, MODE_EMA, PRICE_CLOSE);
         h2 = iMA(_Symbol, _Period, InpTeMid, 0, MODE_EMA, PRICE_CLOSE);
         h3 = iMA(_Symbol, _Period, InpTeSlow, 0, MODE_EMA, PRICE_CLOSE); break;
      case STRAT_PSAR:
         h1 = iSAR(_Symbol, _Period, InpSarStep, 10 * InpSarStep);
         h2 = iMA(_Symbol, _Period, InpSarTrend, 0, MODE_EMA, PRICE_CLOSE); break;
      case STRAT_KAMA:
         h1 = iAMA(_Symbol, _Period, InpKamaPeriod, InpKamaFast, InpKamaSlow, 0, PRICE_CLOSE); break;
      default: break; // Donchian, Ichimoku, TS Momentum use raw prices
     }
   if(hATR == INVALID_HANDLE) return INIT_FAILED;
   bool needs1 = !(InpStrategy == STRAT_DONCHIAN || InpStrategy == STRAT_ICHIMOKU || InpStrategy == STRAT_TSMOM);
   if(needs1 && h1 == INVALID_HANDLE) return INIT_FAILED;
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   if(hATR != INVALID_HANDLE) IndicatorRelease(hATR);
   if(h1 != INVALID_HANDLE) IndicatorRelease(h1);
   if(h2 != INVALID_HANDLE) IndicatorRelease(h2);
   if(h3 != INVALID_HANDLE) IndicatorRelease(h3);
  }

//+------------------------------------------------------------------+
//| Supertrend direction at bar `shift`, recomputed over a window     |
//+------------------------------------------------------------------+
int SupertrendDir(int shift)
  {
   int n = 600;
   if(Bars(_Symbol, _Period) < n + shift + InpStPeriod + 2) return 0;
   double a[];
   ArraySetAsSeries(a, true);
   if(CopyBuffer(h1, 0, shift, n, a) != n) return 0;
   double fub = 0, flb = 0;
   int d = 1;
   for(int k = n - 1; k >= 0; k--)          // oldest -> newest
     {
      int i = k + shift;
      double hl2 = (H(i) + L(i)) / 2.0;
      double ub = hl2 + InpStMult * a[k], lb = hl2 - InpStMult * a[k];
      if(k == n - 1) { fub = ub; flb = lb; continue; }
      double cPrev = C(i + 1);
      fub = (ub < fub || cPrev > fub) ? ub : fub;
      flb = (lb > flb || cPrev < flb) ? lb : flb;
      if(d == 1) d = (C(i) < flb) ? -1 : 1;
      else       d = (C(i) > fub) ? 1 : -1;
     }
   return d;
  }

void Ichimoku(int shift, double &tenkan, double &kijun, double &top, double &bot)
  {
   tenkan = (HH(InpTenkan, shift) + LL(InpTenkan, shift)) / 2.0;
   kijun  = (HH(InpKijun, shift)  + LL(InpKijun, shift))  / 2.0;
   int p = shift + InpKijun;                  // cloud at this bar was projected kijun bars ago
   double ta = (HH(InpTenkan, p) + LL(InpTenkan, p)) / 2.0;
   double ka = (HH(InpKijun, p)  + LL(InpKijun, p))  / 2.0;
   double sa = (ta + ka) / 2.0;
   double sb = (HH(InpSenkou, p) + LL(InpSenkou, p)) / 2.0;
   top = MathMax(sa, sb);
   bot = MathMin(sa, sb);
  }

//+------------------------------------------------------------------+
//| Signals on the last closed bar (1) vs the one before (2)          |
//+------------------------------------------------------------------+
void GetSignals(bool &le, bool &se, bool &lx, bool &sx)
  {
   le = se = lx = sx = false;
   double c1 = C(1), c2 = C(2);
   switch(InpStrategy)
     {
      case STRAT_EMA_CROSS:
        {
         double f1 = Buf(h1, 0, 1), f2 = Buf(h1, 0, 2), s1 = Buf(h2, 0, 1), s2 = Buf(h2, 0, 2);
         le = CrossUp(f1, s1, f2, s2); se = CrossDn(f1, s1, f2, s2); break;
        }
      case STRAT_DONCHIAN:
        {
         double up1 = HH(InpDonEntry, 2), up2 = HH(InpDonEntry, 3);
         double dn1 = LL(InpDonEntry, 2), dn2 = LL(InpDonEntry, 3);
         le = CrossUp(c1, up1, c2, up2); se = CrossDn(c1, dn1, c2, dn2);
         lx = c1 < LL(InpDonExit, 2);    sx = c1 > HH(InpDonExit, 2); break;
        }
      case STRAT_SUPERTREND:
        {
         int d1 = SupertrendDir(1), d2 = SupertrendDir(2);
         le = d1 == 1 && d2 == -1; se = d1 == -1 && d2 == 1; break;
        }
      case STRAT_MACD:
        {
         double m1 = Buf(h1, 0, 1), m2 = Buf(h1, 0, 2), g1 = Buf(h1, 1, 1), g2 = Buf(h1, 1, 2);
         double t1 = Buf(h2, 0, 1);
         le = CrossUp(m1, g1, m2, g2) && c1 > t1; se = CrossDn(m1, g1, m2, g2) && c1 < t1;
         lx = CrossDn(m1, g1, m2, g2);          sx = CrossUp(m1, g1, m2, g2); break;
        }
      case STRAT_ADX:
        {
         double a1 = Buf(h1, 0, 1);
         double p1 = Buf(h1, 1, 1), p2 = Buf(h1, 1, 2), n1 = Buf(h1, 2, 1), n2 = Buf(h1, 2, 2);
         le = CrossUp(p1, n1, p2, n2) && a1 > InpAdxThreshold;
         se = CrossDn(p1, n1, p2, n2) && a1 > InpAdxThreshold;
         lx = CrossDn(p1, n1, p2, n2); sx = CrossUp(p1, n1, p2, n2); break;
        }
      case STRAT_KELTNER:
        {
         double m1 = Buf(h1, 0, 1), m2 = Buf(h1, 0, 2), a1 = Buf(h2, 0, 1), a2 = Buf(h2, 0, 2);
         le = CrossUp(c1, m1 + InpKcMult * a1, c2, m2 + InpKcMult * a2);
         se = CrossDn(c1, m1 - InpKcMult * a1, c2, m2 - InpKcMult * a2);
         lx = c1 < m1; sx = c1 > m1; break;
        }
      case STRAT_BOLLINGER:
        {
         double m1 = Buf(h1, 0, 1);
         double u1 = Buf(h1, 1, 1), u2 = Buf(h1, 1, 2), d1 = Buf(h1, 2, 1), d2 = Buf(h1, 2, 2);
         le = CrossUp(c1, u1, c2, u2); se = CrossDn(c1, d1, c2, d2);
         lx = c1 < m1; sx = c1 > m1; break;
        }
      case STRAT_TRIPLE_EMA:
        {
         double f1 = Buf(h1, 0, 1), f2 = Buf(h1, 0, 2), m1 = Buf(h2, 0, 1), m2 = Buf(h2, 0, 2);
         double s1 = Buf(h3, 0, 1), s2 = Buf(h3, 0, 2);
         le = (f1 > m1 && m1 > s1) && !(f2 > m2 && m2 > s2);
         se = (f1 < m1 && m1 < s1) && !(f2 < m2 && m2 < s2);
         lx = f1 < m1; sx = f1 > m1; break;
        }
      case STRAT_ICHIMOKU:
        {
         double t1, k1, top1, bot1, t2, k2, top2, bot2;
         Ichimoku(1, t1, k1, top1, bot1);
         Ichimoku(2, t2, k2, top2, bot2);
         le = (c1 > top1 && t1 > k1) && !(c2 > top2 && t2 > k2);
         se = (c1 < bot1 && t1 < k1) && !(c2 < bot2 && t2 < k2);
         lx = c1 < k1; sx = c1 > k1; break;
        }
      case STRAT_TSMOM:
        {
         double r1 = c1 / C(1 + InpMomLookback) - 1.0, r2 = c2 / C(2 + InpMomLookback) - 1.0;
         le = CrossUp(r1, 0, r2, 0); se = CrossDn(r1, 0, r2, 0); break;
        }
      case STRAT_PSAR:
        {
         double s1 = Buf(h1, 0, 1), s2 = Buf(h1, 0, 2), t1 = Buf(h2, 0, 1);
         bool up1 = s1 < c1, up2 = s2 < c2;
         bool flipUp = up1 && !up2, flipDn = !up1 && up2;
         le = flipUp && c1 > t1; se = flipDn && c1 < t1;
         lx = flipDn; sx = flipUp; break;
        }
      case STRAT_KAMA:
        {
         double k1 = Buf(h1, 0, 1), k2 = Buf(h1, 0, 2);
         le = CrossUp(c1, k1, c2, k2) && k1 > k2;
         se = CrossDn(c1, k1, c2, k2) && k1 < k2; break;
        }
     }
  }

//+------------------------------------------------------------------+
bool GetPosition(int &dir, ulong &ticket)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != (long)InpMagic) continue;
      ticket = t;
      dir = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1;
      return true;
     }
   dir = 0; ticket = 0;
   return false;
  }

double LotsForRisk(double stopDist)
  {
   double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
   double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tv <= 0 || ts <= 0 || stopDist <= 0) return 0;
   double riskMoney = AccountInfoDouble(ACCOUNT_EQUITY) * InpRiskPercent / 100.0;
   double lots = riskMoney / (stopDist / ts * tv);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   lots = MathFloor(lots / step) * step;
   if(lots < SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN)) return 0;  // never exceed risk
   return MathMin(lots, SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX));
  }

void Open(int dir)
  {
   if(InpMaxSpreadPoints > 0 && SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) > InpMaxSpreadPoints) return;
   double atr = Buf(hATR, 0, 1);
   if(atr == EMPTY_VALUE || atr <= 0) return;
   double dist = InpStopATR * atr;
   double lots = LotsForRisk(dist);
   if(lots <= 0) { Print("Lot size below minimum for the requested risk - skipped"); return; }
   int dg = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   if(dir == 1)
     {
      double px = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      trade.Buy(lots, _Symbol, px, NormalizeDouble(px - dist, dg), 0, "OnCandle");
     }
   else
     {
      double px = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      trade.Sell(lots, _Symbol, px, NormalizeDouble(px + dist, dg), 0, "OnCandle");
     }
  }

void Trail(ulong ticket, int dir)
  {
   if(InpTrailATR <= 0 || !PositionSelectByTicket(ticket)) return;
   double atr = Buf(hATR, 0, 1);
   if(atr == EMPTY_VALUE || atr <= 0) return;
   int since = iBarShift(_Symbol, _Period, (datetime)PositionGetInteger(POSITION_TIME));
   if(since < 1) return;
   double best = PositionGetDouble(POSITION_PRICE_OPEN);
   for(int i = 1; i <= since; i++)
      best = dir == 1 ? MathMax(best, C(i)) : MathMin(best, C(i));
   int dg = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double sl = PositionGetDouble(POSITION_SL);
   double nsl = NormalizeDouble(dir == 1 ? best - InpTrailATR * atr : best + InpTrailATR * atr, dg);
   if((dir == 1 && nsl > sl) || (dir == -1 && (sl == 0 || nsl < sl)))
      trade.PositionModify(ticket, nsl, PositionGetDouble(POSITION_TP));
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   datetime t0 = iTime(_Symbol, _Period, 0);
   if(t0 == lastBar) return;               // act once per bar, at its open
   if(Bars(_Symbol, _Period) < 400) return;
   lastBar = t0;

   int dir; ulong ticket;
   GetPosition(dir, ticket);
   if(dir != 0) Trail(ticket, dir);

   bool le, se, lx, sx;
   GetSignals(le, se, lx, sx);

   if(dir == 1)
     {
      if(se)      { trade.PositionClose(ticket); Open(-1); }
      else if(lx)   trade.PositionClose(ticket);
     }
   else if(dir == -1)
     {
      if(le)      { trade.PositionClose(ticket); Open(1); }
      else if(sx)   trade.PositionClose(ticket);
     }
   else
     {
      if(le && !se)      Open(1);
      else if(se && !le) Open(-1);
     }
  }
//+------------------------------------------------------------------+
