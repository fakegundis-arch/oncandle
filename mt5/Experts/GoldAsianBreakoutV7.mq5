//+------------------------------------------------------------------+
//|                                         GoldAsianBreakoutV7.mq5  |
//|  Gold Asian breakout v7 (results/gold/REPORT.md, section v7):     |
//|  a seasonal two-mode bot.                                         |
//|   Feb-Jul  -> mode B (chosen on Feb-Jul 2026, checked on Feb-Jul  |
//|               2025): EMA(200) rising vs 8 bars ago, regime filter |
//|               (mean true range 5 days / 60 days <= 1.6),          |
//|               equity-curve filter (last 10 paper trades >= -2R),  |
//|               no daily trade limit, 10% risk longs and shorts.    |
//|   Aug-Jan  -> mode v5 (unchanged GoldAsianBreakoutV5): EMA(400)   |
//|               rising vs 16 bars ago, max 2 trades/day, 12% longs, |
//|               6% shorts.                                          |
//|  Shared: Donchian(10) break or first break of the previous day's  |
//|  high/low, new trades 00:00-06:00 server time, stop 1.5 ATR(14)   |
//|  (min $2), target 4R, stop to +0.3R at +1R, weekly stop -2R.      |
//|  Both modes are traded on paper all year (as in the backtest, so  |
//|  the equity-curve filter has history when Feb starts); only the   |
//|  mode of the current month places real orders.                    |
//|  Attach to XAUUSD M15 on a GMT+0 server (Exness).                 |
//|  State is kept in terminal global variables.                      |
//+------------------------------------------------------------------+
#property copyright "oncandle"
#property version   "7.00"

#include <Trade/Trade.mqh>

input string InpFebJulMonths = "2,3,4,5,6,7"; // Months that use mode B
// mode B (Feb-Jul)
input int    InpB_TrendEMA   = 200;
input int    InpB_SlopeBars  = 8;
input double InpB_RegimeMax  = 1.6;   // 5-day / 60-day mean true range (0 = off)
input int    InpB_EqTrades   = 10;    // Equity-curve filter: last N paper trades (0 = off)
input double InpB_EqMinR     = -2.0;
input int    InpB_MaxPerDay  = 0;     // 0 = no limit
input double InpB_RiskLong   = 10.0;  // % of equity
input double InpB_RiskShort  = 10.0;
// mode v5 (Aug-Jan)
input int    InpV_TrendEMA   = 400;
input int    InpV_SlopeBars  = 16;
input int    InpV_MaxPerDay  = 2;
input double InpV_RiskLong   = 12.0;
input double InpV_RiskShort  = 6.0;
// shared
input int    InpDonchian     = 10;
input bool   InpUsePrevDay   = true;
input double InpStopATR      = 1.5;
input double InpMinStop      = 2.0;
input double InpRR           = 4.0;
input double InpBETrigger    = 1.0;
input double InpBEBuffer     = 0.3;
input int    InpSessionStart = 0;
input int    InpSessionEnd   = 6;
input double InpWeekStopR    = -2.0;  // Weekly stop in R (0 = off)
input int    InpMaxSpreadPts = 0;
input ulong  InpMagic        = 20261109;

CTrade   trade;
int      hAtr = INVALID_HANDLE;
datetime lastBar = 0;
bool     febJul[13];

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

// one signal engine with its own paper trade, filters and state (mirrors backtester/gold.py + gold_v3.overlay)
class Engine
  {
public:
   string tag;
   int    hEma, slope, eqN, maxDay;
   double eqMin, regMax, riskL, riskS;
   int    pdDoneDay;
   bool   vOpen, vMoved, vTaken;       // vTaken: passed the overlays (counts for the weekly stop)
   int    vDir, vWeek;
   double vEntry, vStop, vTgt, vR;

   string GV(string k) { return StringFormat("GAB7_%I64u_%s_%s", InpMagic, tag, k); }

   bool Init(string t, int ema, int sl, double reg, int en, double em, int md, double rl, double rs)
     {
      tag = t; slope = sl; regMax = reg; eqN = en; eqMin = em; maxDay = md; riskL = rl; riskS = rs;
      pdDoneDay = -1; vOpen = false;
      hEma = iMA(_Symbol, _Period, ema, 0, MODE_EMA, PRICE_CLOSE);
      if(!GlobalVariableCheck(GV("n"))) GlobalVariableSet(GV("n"), 0);
      return hEma != INVALID_HANDLE;
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

   void Manage()
     {
      if(!vOpen) return;
      double px = vDir == 1 ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double r = EMPTY_VALUE;
      if(vDir == 1) { if(px <= vStop) r = (vStop - vEntry) / vR; else if(px >= vTgt) r = (vTgt - vEntry) / vR; }
      else          { if(px >= vStop) r = (vEntry - vStop) / vR; else if(px <= vTgt) r = (vEntry - vTgt) / vR; }
      if(r == EMPTY_VALUE)
        {
         if(InpBETrigger > 0 && !vMoved && vDir * (px - vEntry) >= InpBETrigger * vR)
           { vStop = vEntry + vDir * InpBEBuffer * vR; vMoved = true; }
         return;
        }
      PushPaper(r);
      if(vTaken && (int)GlobalVariableGet(GV("wk")) == vWeek) GlobalVariableSet(GV("wkR"), GlobalVariableGet(GV("wkR")) + r);
      vOpen = false;
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

   // called on each new M15 bar inside the session; returns the direction of a new paper trade (0 = none)
   int OnBar(int hour, int doy, double atr, double &dist)
     {
      int pdDir = 0;
      if(InpUsePrevDay && pdDoneDay != doy)
        {
         double c1b = iClose(_Symbol, _Period, 1);
         double pdh = iHigh(_Symbol, PERIOD_D1, 1), pdl = iLow(_Symbol, PERIOD_D1, 1);
         if(pdh > 0 && c1b > pdh)      pdDir = 1;
         else if(pdl > 0 && c1b < pdl) pdDir = -1;
         if(pdDir != 0) pdDoneDay = doy;
        }
      if(vOpen) return 0;
      double c1 = iClose(_Symbol, _Period, 1), c2 = iClose(_Symbol, _Period, 2);
      double up1 = iHigh(_Symbol, _Period, iHighest(_Symbol, _Period, MODE_HIGH, InpDonchian, 2));
      double up2 = iHigh(_Symbol, _Period, iHighest(_Symbol, _Period, MODE_HIGH, InpDonchian, 3));
      double dn1 = iLow(_Symbol, _Period, iLowest(_Symbol, _Period, MODE_LOW, InpDonchian, 2));
      double dn2 = iLow(_Symbol, _Period, iLowest(_Symbol, _Period, MODE_LOW, InpDonchian, 3));
      double e1 = Buf(hEma, 1), eS = Buf(hEma, 1 + slope);
      if(e1 == EMPTY_VALUE || eS == EMPTY_VALUE) return 0;
      int dir = 0;
      if(c1 > up1 && c2 <= up2 && c1 > e1 && e1 > eS) dir = 1;
      else if(c1 < dn1 && c2 >= dn2 && c1 < e1 && e1 < eS) dir = -1;
      if(dir == 0) dir = pdDir;
      if(dir == 0 || !RegimeOK() || !DayOK()) return 0;
      if(maxDay > 0) GlobalVariableSet(GV("dn"), GlobalVariableGet(GV("dn")) + 1);

      dist = MathMax(InpStopATR * atr, InpMinStop);
      vOpen = true; vDir = dir; vR = dist; vMoved = false;
      vEntry = dir == 1 ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
      vStop = vEntry - dir * dist; vTgt = vEntry + dir * InpRR * dist;
      vWeek = WeekKey(TimeCurrent());
      vTaken = EquityOK() && WeekOK(vWeek);
      return dir;
     }
  };

Engine engB, engV;

int OnInit()
  {
   trade.SetExpertMagicNumber(InpMagic);
   hAtr = iATR(_Symbol, _Period, 14);
   ArrayInitialize(febJul, false);
   string parts[];
   for(int i = StringSplit(InpFebJulMonths, ',', parts) - 1; i >= 0; i--)
     {
      int m = (int)StringToInteger(parts[i]);
      if(m >= 1 && m <= 12) febJul[m] = true;
     }
   if(hAtr == INVALID_HANDLE ||
      !engB.Init("B", InpB_TrendEMA, InpB_SlopeBars, InpB_RegimeMax, InpB_EqTrades, InpB_EqMinR, InpB_MaxPerDay, InpB_RiskLong, InpB_RiskShort) ||
      !engV.Init("V5", InpV_TrendEMA, InpV_SlopeBars, 0, 0, 0, InpV_MaxPerDay, InpV_RiskLong, InpV_RiskShort))
      return INIT_FAILED;
   if(_Period != PERIOD_M15) Print("Warning: tested on M15 only");
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason) { IndicatorRelease(hAtr); IndicatorRelease(engB.hEma); IndicatorRelease(engV.hEma); }

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
   engB.Manage();
   engV.Manage();
   ulong ticket = 0;
   bool inPos = HasPosition(ticket);
   if(inPos) ManageBreakEven(ticket);

   datetime t0 = iTime(_Symbol, _Period, 0);
   if(t0 == lastBar) return;
   lastBar = t0;
   if(Bars(_Symbol, _Period) < 96 * 60 + 10) return;   // regime filter needs 60 days of M15

   MqlDateTime bt; TimeToStruct(iTime(_Symbol, _Period, 1), bt);
   bool inSession = InpSessionStart < InpSessionEnd ? (bt.hour >= InpSessionStart && bt.hour < InpSessionEnd)
                                                    : (bt.hour >= InpSessionStart || bt.hour < InpSessionEnd);
   if(!inSession) return;
   double atr = Buf(hAtr, 1);
   if(atr == EMPTY_VALUE || atr <= 0) return;

   MqlDateTime now; TimeToStruct(TimeCurrent(), now);
   bool modeB = febJul[now.mon];
   double distB = 0, distV = 0;
   int dB = engB.OnBar(bt.hour, bt.day_of_year, atr, distB);
   int dV = engV.OnBar(bt.hour, bt.day_of_year, atr, distV);
   int dir = modeB ? dB : dV;
   double dist = modeB ? distB : distV;
   bool taken = modeB ? engB.vTaken : engV.vTaken;
   if(dir == 0 || !taken || inPos) return;
   if(InpMaxSpreadPts > 0 && SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) > InpMaxSpreadPts) return;

   double risk = modeB ? (dir == 1 ? InpB_RiskLong : InpB_RiskShort) : (dir == 1 ? InpV_RiskLong : InpV_RiskShort);
   double lots = LotsForRisk(dist, risk);
   if(lots <= 0) { Print("Lot size below broker minimum for this risk - skipped"); return; }
   int dg = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID), ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   string cm = modeB ? "GoldAsianV7-B" : "GoldAsianV7-v5";
   if(dir == 1) trade.Buy(lots, _Symbol, ask, NormalizeDouble(ask - dist, dg), NormalizeDouble(ask + InpRR * dist, dg), cm);
   else         trade.Sell(lots, _Symbol, bid, NormalizeDouble(bid + dist, dg), NormalizeDouble(bid - InpRR * dist, dg), cm);
  }
//+------------------------------------------------------------------+
