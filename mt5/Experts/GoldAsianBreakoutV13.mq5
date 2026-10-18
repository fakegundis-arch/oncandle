//+------------------------------------------------------------------+
//|                                        GoldAsianBreakoutV13.mq5  |
//|  Gold Asian breakout v13 (results/gold/REPORT.md, section v13):   |
//|  v11 engines with more risk on the Asian engine (14% / NY 4%).    |
//|  Both engines trade every month with the same rules and their own |
//|  position; up to two trades can be open at once.                  |
//|   Engine Asia (14%): 00:00-06:00, Donchian(10).                   |
//|   Engine NY    (4%): 12:00-15:00, Donchian(15).                   |
//|  Both: break of the Donchian channel with EMA(400) rising vs 16   |
//|  bars ago, or the first break of the previous day's high/low in   |
//|  the session; daily trend (buy only if yesterday closed above the |
//|  D1 EMA(20), sell only if below); regime filter (5-day / 60-day   |
//|  mean true range <= 1.6); equity-curve filter (real trade only if |
//|  the engine's last 10 paper trades sum to >= -2R); stop 1.5       |
//|  ATR(14) (min $2), target 4R, stop to +0.3R at +1R, weekly stop   |
//|  -2R. Magic numbers: InpMagic + 0 (Asia) / + 1 (NY).              |
//|  Attach to XAUUSD M15 on a GMT+0 server (Exness).                 |
//|  State is kept in terminal global variables.                      |
//+------------------------------------------------------------------+
#property copyright "oncandle"
#property version   "13.00"

#include <Trade/Trade.mqh>

// engine Asia
input double InpA_Risk       = 14.0;  // % of equity per trade (0 = engine off)
input int    InpA_Donchian   = 10;
input int    InpA_SesStart   = 0;
input int    InpA_SesEnd     = 6;
// engine NY
input double InpN_Risk       = 4.0;
input int    InpN_Donchian   = 15;
input int    InpN_SesStart   = 12;
input int    InpN_SesEnd     = 15;
// shared
input int    InpTrendEMA     = 400;
input int    InpSlopeBars    = 16;
input bool   InpPrevDay      = true;
input int    InpD1TrendEMA   = 20;    // Daily trend EMA (0 = off)
input double InpRegimeMax    = 1.6;   // 5-day / 60-day mean true range (0 = off)
input int    InpEqTrades     = 10;    // Equity-curve filter: last N paper trades (0 = off)
input double InpEqMinR       = -2.0;
input int    InpMaxPerDay    = 0;     // 0 = no limit
input double InpStopATR      = 1.5;
input double InpMinStop      = 2.0;
input double InpRR           = 4.0;
input double InpBETrigger    = 1.0;
input double InpBEBuffer     = 0.3;
input double InpWeekStopR    = -2.0;  // Weekly stop in R, per engine (0 = off)
input int    InpMaxSpreadPts = 0;
input ulong  InpMagic        = 20261115;

int      hAtr = INVALID_HANDLE, hD1 = INVALID_HANDLE;
datetime lastBar = 0;

int WeekKey(datetime t)
  {
   MqlDateTime d; TimeToStruct(t, d);
   int dow = (d.day_of_week + 6) % 7;              // Monday = 0
   datetime monday = t - dow * 86400 - (d.hour * 3600 + d.min * 60 + d.sec);
   return (int)(monday / 86400);
  }

double Buf(int h, int s)
  {
   double v[1];
   if(CopyBuffer(h, 0, s, 1, v) != 1) return EMPTY_VALUE;
   return v[0];
  }

// daily trend from yesterday's close vs the D1 EMA (as of yesterday): +1 up, -1 down, 0 unknown
int D1Trend()
  {
   double e = Buf(hD1, 1), c = iClose(_Symbol, PERIOD_D1, 1);
   if(e == EMPTY_VALUE || c <= 0) return 0;
   return c > e ? 1 : (c < e ? -1 : 0);
  }

double LotsForRisk(double dist, double riskPct)
  {
   double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
   double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tv <= 0 || ts <= 0 || dist <= 0) return 0;
   double lots = AccountInfoDouble(ACCOUNT_EQUITY) * riskPct / 100.0 / (dist / ts * tv);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   lots = MathFloor(lots / step) * step;
   if(lots < SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN)) return 0;
   return MathMin(lots, SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX));
  }

// one breakout engine: its own signals, paper trade, filters, state and real position
// (mirrors backtester/gold.py + gold_v3.overlay)
class Engine
  {
public:
   string tag;
   ulong  magic;
   CTrade trade;
   int    hEma, don, slope, sesS, sesE, eqN, maxDay;
   bool   usePD;
   double eqMin, regMax, risk;
   int    pdDoneDay;
   bool   vOpen, vMoved, vTaken;       // vTaken: passed the overlays (counts for the weekly stop)
   int    vDir, vWeek;
   double vEntry, vStop, vTgt, vR;

   string GV(string k) { return StringFormat("GAB13_%I64u_%s", magic, k); }

   bool Init(string t, ulong mg, double rk, int dn, int ema, int sl, bool pd, int s0, int s1, double reg, int en,
             double em, int md)
     {
      tag = t; magic = mg; risk = rk; don = dn; slope = sl; usePD = pd; sesS = s0; sesE = s1; regMax = reg;
      eqN = en; eqMin = em; maxDay = md;
      pdDoneDay = -1; vOpen = false;
      trade.SetExpertMagicNumber(magic);
      hEma = iMA(_Symbol, _Period, ema, 0, MODE_EMA, PRICE_CLOSE);
      if(!GlobalVariableCheck(GV("n"))) GlobalVariableSet(GV("n"), 0);
      return hEma != INVALID_HANDLE;
     }

   ulong Ticket()
     {
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         ulong t = PositionGetTicket(i);
         if(PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == (long)magic) return t;
        }
      return 0;
     }

   void PushPaper(double r)
     {
      int n = (int)GlobalVariableGet(GV("n"));
      GlobalVariableSet(GV(StringFormat("r%d", n % 100)), r);
      GlobalVariableSet(GV("n"), n + 1);
     }

   bool EquityOK()
     {
      if(eqN <= 0) return true;
      int n = (int)GlobalVariableGet(GV("n"));
      if(n < eqN) return true;
      double s = 0;
      for(int i = n - eqN; i < n; i++) s += GlobalVariableGet(GV(StringFormat("r%d", i % 100)));
      return s >= eqMin;
     }

   bool WeekOK(int wk)
     {
      if(InpWeekStopR >= 0) return true;
      if((int)GlobalVariableGet(GV("wk")) != wk) { GlobalVariableSet(GV("wk"), wk); GlobalVariableSet(GV("wkR"), 0); }
      return GlobalVariableGet(GV("wkR")) > InpWeekStopR;
     }

   bool DayOK()
     {
      if(maxDay <= 0) return true;
      MqlDateTime d; TimeToStruct(TimeCurrent(), d);
      int dk = d.year * 10000 + d.mon * 100 + d.day;
      if((int)GlobalVariableGet(GV("dk")) != dk) { GlobalVariableSet(GV("dk"), dk); GlobalVariableSet(GV("dn"), 0); }
      return GlobalVariableGet(GV("dn")) < maxDay;
     }

   bool RegimeOK()
     {
      if(regMax <= 0) return true;
      int nS = 96 * 5, nL = 96 * 60;
      double hi[], lo[], cl[];
      if(CopyHigh(_Symbol, _Period, 2, nL, hi) != nL || CopyLow(_Symbol, _Period, 2, nL, lo) != nL ||
         CopyClose(_Symbol, _Period, 3, nL, cl) != nL) return false;
      double sS = 0, sL = 0;
      for(int i = 0; i < nL; i++)      // arrays are oldest-first; the last nS bars are the 5-day window
        {
         double tr = MathMax(hi[i], cl[i]) - MathMin(lo[i], cl[i]);
         sL += tr;
         if(i >= nL - nS) sS += tr;
        }
      return sL > 0 && (sS / nS) / (sL / nL) <= regMax;
     }

   // every tick: paper trade exits / break-even, and break-even on the real position
   void OnTickManage()
     {
      if(vOpen)
        {
         double px = vDir == 1 ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         double r = EMPTY_VALUE;
         if(vDir == 1) { if(px <= vStop) r = (vStop - vEntry) / vR; else if(px >= vTgt) r = (vTgt - vEntry) / vR; }
         else          { if(px >= vStop) r = (vEntry - vStop) / vR; else if(px <= vTgt) r = (vEntry - vTgt) / vR; }
         if(r == EMPTY_VALUE)
           {
            if(InpBETrigger > 0 && !vMoved && vDir * (px - vEntry) >= InpBETrigger * vR)
              { vStop = vEntry + vDir * InpBEBuffer * vR; vMoved = true; }
           }
         else
           {
            PushPaper(r);
            if(vTaken && (int)GlobalVariableGet(GV("wk")) == vWeek) GlobalVariableSet(GV("wkR"), GlobalVariableGet(GV("wkR")) + r);
            vOpen = false;
           }
        }
      ulong t = Ticket();
      if(t == 0 || InpBETrigger <= 0 || !PositionSelectByTicket(t)) return;
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl = PositionGetDouble(POSITION_SL), tp = PositionGetDouble(POSITION_TP);
      if(tp == 0) return;
      double R = MathAbs(tp - open) / InpRR;
      int dg = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
      if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
        {
         double be = NormalizeDouble(open + InpBEBuffer * R, dg);
         if(sl < be && SymbolInfoDouble(_Symbol, SYMBOL_BID) >= open + InpBETrigger * R) trade.PositionModify(t, be, tp);
        }
      else
        {
         double be = NormalizeDouble(open - InpBEBuffer * R, dg);
         if((sl == 0 || sl > be) && SymbolInfoDouble(_Symbol, SYMBOL_ASK) <= open - InpBETrigger * R) trade.PositionModify(t, be, tp);
        }
     }

   // each new M15 bar: signal -> paper trade -> real trade if the overlays allow it
   void OnBar(int hour, int doy, double atr)
     {
      if(risk <= 0) return;
      bool inSes = sesS < sesE ? (hour >= sesS && hour < sesE) : (hour >= sesS || hour < sesE);
      if(!inSes) return;
      int pdDir = 0;
      if(usePD && pdDoneDay != doy)
        {
         double c1b = iClose(_Symbol, _Period, 1);
         double pdh = iHigh(_Symbol, PERIOD_D1, 1), pdl = iLow(_Symbol, PERIOD_D1, 1);
         if(pdh > 0 && c1b > pdh)      pdDir = 1;
         else if(pdl > 0 && c1b < pdl) pdDir = -1;
         if(pdDir != 0) pdDoneDay = doy;
        }
      if(vOpen) return;
      double c1 = iClose(_Symbol, _Period, 1), c2 = iClose(_Symbol, _Period, 2);
      double up1 = iHigh(_Symbol, _Period, iHighest(_Symbol, _Period, MODE_HIGH, don, 2));
      double up2 = iHigh(_Symbol, _Period, iHighest(_Symbol, _Period, MODE_HIGH, don, 3));
      double dn1 = iLow(_Symbol, _Period, iLowest(_Symbol, _Period, MODE_LOW, don, 2));
      double dn2 = iLow(_Symbol, _Period, iLowest(_Symbol, _Period, MODE_LOW, don, 3));
      double e1 = Buf(hEma, 1), eS = Buf(hEma, 1 + slope);
      if(e1 == EMPTY_VALUE || eS == EMPTY_VALUE) return;
      int dir = 0;
      if(c1 > up1 && c2 <= up2 && c1 > e1 && e1 > eS) dir = 1;
      else if(c1 < dn1 && c2 >= dn2 && c1 < e1 && e1 < eS) dir = -1;
      if(dir == 0) dir = pdDir;
      if(dir == 0 || (InpD1TrendEMA > 0 && D1Trend() != dir) || !RegimeOK() || !DayOK()) return;
      if(maxDay > 0) GlobalVariableSet(GV("dn"), GlobalVariableGet(GV("dn")) + 1);

      double dist = MathMax(InpStopATR * atr, InpMinStop);
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID), ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      vOpen = true; vDir = dir; vR = dist; vMoved = false;
      vEntry = dir == 1 ? ask : bid;
      vStop = vEntry - dir * dist; vTgt = vEntry + dir * InpRR * dist;
      vWeek = WeekKey(TimeCurrent());
      vTaken = EquityOK() && WeekOK(vWeek);
      if(!vTaken || Ticket() != 0) return;
      if(InpMaxSpreadPts > 0 && SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) > InpMaxSpreadPts) return;
      double lots = LotsForRisk(dist, risk);
      if(lots <= 0) { Print(tag, ": lot size below broker minimum for this risk - skipped"); return; }
      int dg = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
      string cm = "GoldAsianV13-" + tag;
      if(dir == 1) trade.Buy(lots, _Symbol, ask, NormalizeDouble(ask - dist, dg), NormalizeDouble(ask + InpRR * dist, dg), cm);
      else         trade.Sell(lots, _Symbol, bid, NormalizeDouble(bid + dist, dg), NormalizeDouble(bid - InpRR * dist, dg), cm);
     }
  };

Engine eng[2];

int OnInit()
  {
   hAtr = iATR(_Symbol, _Period, 14);
   if(InpD1TrendEMA > 0) hD1 = iMA(_Symbol, PERIOD_D1, InpD1TrendEMA, 0, MODE_EMA, PRICE_CLOSE);
   if(hAtr == INVALID_HANDLE || (InpD1TrendEMA > 0 && hD1 == INVALID_HANDLE) ||
      !eng[0].Init("Asia", InpMagic, InpA_Risk, InpA_Donchian, InpTrendEMA, InpSlopeBars, InpPrevDay, InpA_SesStart,
                   InpA_SesEnd, InpRegimeMax, InpEqTrades, InpEqMinR, InpMaxPerDay) ||
      !eng[1].Init("NY", InpMagic + 1, InpN_Risk, InpN_Donchian, InpTrendEMA, InpSlopeBars, InpPrevDay, InpN_SesStart,
                   InpN_SesEnd, InpRegimeMax, InpEqTrades, InpEqMinR, InpMaxPerDay))
      return INIT_FAILED;
   if(_Period != PERIOD_M15) Print("Warning: tested on M15 only");
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   IndicatorRelease(hAtr);
   if(hD1 != INVALID_HANDLE) IndicatorRelease(hD1);
   for(int i = 0; i < 2; i++) IndicatorRelease(eng[i].hEma);
  }

void OnTick()
  {
   for(int i = 0; i < 2; i++) eng[i].OnTickManage();
   datetime t0 = iTime(_Symbol, _Period, 0);
   if(t0 == lastBar) return;
   lastBar = t0;
   if(Bars(_Symbol, _Period) < 96 * 60 + 10) return;   // regime filter needs 60 days of M15
   MqlDateTime bt; TimeToStruct(iTime(_Symbol, _Period, 1), bt);
   double atr = Buf(hAtr, 1);
   if(atr == EMPTY_VALUE || atr <= 0) return;
   for(int i = 0; i < 2; i++) eng[i].OnBar(bt.hour, bt.day_of_year, atr);
  }
//+------------------------------------------------------------------+
