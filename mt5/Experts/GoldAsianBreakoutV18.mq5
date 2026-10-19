//+------------------------------------------------------------------+
//|                                        GoldAsianBreakoutV18.mq5  |
//|  Gold Asian breakout v18 (results/gold/REPORT.md, section v18):   |
//|  chosen on 2026 ONLY, 2025 kept unseen (scripts/gold_v18.py).     |
//|  Engines (own position each; risk = % of balance at the order):   |
//|   v5   : 00:00-06:00, Donchian 10, EMA400 rising vs 16 bars,      |
//|          previous-day break, max 2 trades/day, no daily-trend or  |
//|          regime filter, no equity-curve filter.                   |
//|   Asia : same signals + daily trend (D1 EMA20), regime filter     |
//|          (5-day / 60-day mean true range <= 1.6), equity-curve    |
//|          filter (last 10 paper trades >= -2R).                    |
//|   NY   : as Asia on 12:00-15:00 with Donchian 15.                 |
//|  Quiet-market skip: no REAL trade while ATR(14) of the signal bar |
//|  is below a % of price; the signal still runs as a paper trade.   |
//|  Weekly stop -2R per engine (real trades). The -2R comparisons    |
//|  carry a 1e-9 margin, so two full losses always count as -2R      |
//|  (same as the backtest).                                          |
//|  Account level: no new orders for the rest of the UTC day once    |
//|  InpDailyMaxLosses trades of this EA have closed at a loss that   |
//|  day (a loss = more than 0.25% of balance; break-even exits with  |
//|  a few cents of slippage do not count).                           |
//|  Magic numbers: InpMagic + 0 (v5) / + 1 (Asia) / + 2 (NY).        |
//|  Attach to XAUUSD M15 on a GMT+0 server (Exness).                 |
//|  State is kept in terminal global variables.                      |
//+------------------------------------------------------------------+
#property copyright "oncandle"
#property version   "18.00"

#include <Trade/Trade.mqh>

// engine v5 (sleeve)
input double InpV_Risk       = 1.0;   // % of balance per trade (0 = engine off)
input double InpV_SellMult   = 1.0;   // sells at this x the risk (1 = same as buys)
input double InpV_BETrigger  = 1.0;
input double InpV_BEBuffer   = 0.3;
input double InpV_RR         = 4.0;
input double InpV_StopATR    = 1.5;
// engine Asia
input double InpA_Risk       = 7.0;
input double InpA_BETrigger  = 1.5;
input double InpA_BEBuffer   = 0.3;
input double InpA_RR         = 4.0;
input double InpA_StopATR    = 1.5;
input double InpA_QuietPct   = 0.11;  // no real trade if ATR(14) < this % of price (0 = off)
// engine NY
input double InpN_Risk       = 5.0;
input double InpN_BETrigger  = 0.6;
input double InpN_BEBuffer   = 0.0;
input double InpN_RR         = 3.0;
input double InpN_StopATR    = 1.25;
input double InpN_QuietPct   = 0.0;
// account level
input int    InpDailyMaxLosses = 3;   // stop new orders after this many losing trades today (0 = off)
// shared
input int    InpTrendEMA     = 400;
input int    InpSlopeBars    = 16;
input int    InpD1TrendEMA   = 20;
input double InpRegimeMax    = 1.6;
input int    InpEqTrades     = 10;
input double InpEqMinR       = -2.0;
input double InpMinStop      = 2.0;
input double InpWeekStopR    = -2.0;
input int    InpMaxSpreadPts = 0;
input ulong  InpMagic        = 20261118;

int      hAtr = INVALID_HANDLE, hD1 = INVALID_HANDLE;
datetime lastBar = 0;

int WeekKey(datetime t)
  {
   MqlDateTime d; TimeToStruct(t, d);
   int dow = (d.day_of_week + 6) % 7;
   datetime monday = t - dow * 86400 - (d.hour * 3600 + d.min * 60 + d.sec);
   return (int)(monday / 86400);
  }

double Buf(int h, int s)
  {
   double v[1];
   if(CopyBuffer(h, 0, s, 1, v) != 1) return EMPTY_VALUE;
   return v[0];
  }

int D1Trend()
  {
   double e = Buf(hD1, 1), c = iClose(_Symbol, PERIOD_D1, 1);
   if(e == EMPTY_VALUE || c <= 0) return 0;
   return c > e ? 1 : (c < e ? -1 : 0);
  }

int    DayKey(datetime t) { MqlDateTime d; TimeToStruct(t, d); return d.year * 10000 + d.mon * 100 + d.day; }

// global-variable prefix: account and symbol, so demo/live accounts and symbols never share state
string Pfx() { return StringFormat("GAB18_%I64d_%s_", AccountInfoInteger(ACCOUNT_LOGIN), _Symbol); }

// positions of this EA (any engine) on this symbol closed at a loss today; deals of one position are summed first
int LossesToday()
  {
   datetime now = TimeCurrent();
   MqlDateTime d; TimeToStruct(now, d); d.hour = 0; d.min = 0; d.sec = 0;
   if(!HistorySelect(StructToTime(d), now + 3600)) return 0;
   ulong ids[]; double net[]; int k = 0;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
     {
      ulong t = HistoryDealGetTicket(i);
      long mg = HistoryDealGetInteger(t, DEAL_MAGIC);
      long en = HistoryDealGetInteger(t, DEAL_ENTRY);
      if(mg < (long)InpMagic || mg > (long)InpMagic + 2 || HistoryDealGetString(t, DEAL_SYMBOL) != _Symbol) continue;
      if(en != DEAL_ENTRY_OUT && en != DEAL_ENTRY_OUT_BY) continue;
      ulong id = (ulong)HistoryDealGetInteger(t, DEAL_POSITION_ID);
      double v = HistoryDealGetDouble(t, DEAL_PROFIT) + HistoryDealGetDouble(t, DEAL_COMMISSION);
      int j = 0;
      while(j < k && ids[j] != id) j++;
      if(j == k) { ArrayResize(ids, k + 1); ArrayResize(net, k + 1); ids[k] = id; net[k] = 0; k++; }
      net[j] += v;
     }
   int n = 0;
   for(int j = 0; j < k; j++)
      if(net[j] < -0.0025 * AccountInfoDouble(ACCOUNT_BALANCE)) n++;
   return n;
  }

// account-level rules, checked when an engine is about to send a real order
bool AccountOK()
  {
   return InpDailyMaxLosses <= 0 || LossesToday() < InpDailyMaxLosses;
  }

double LotsForRisk(double dist, double riskPct)
  {
   double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
   double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tv <= 0 || ts <= 0 || dist <= 0) return 0;
   double lots = AccountInfoDouble(ACCOUNT_BALANCE) * riskPct / 100.0 / (dist / ts * tv);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   lots = MathFloor(lots / step + 1e-9) * step;
   if(lots < SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN)) return 0;
   return MathMin(lots, SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX));
  }

// one breakout engine (mirrors backtester/gold.py + scripts/gold_v18_search.overlay)
class Engine
  {
public:
   string tag;
   ulong  magic;
   CTrade trade;
   int    hEma, don, sesS, sesE, eqN, maxDay;
   bool   useD1, useRegime;
   double eqMin, risk, sellMult, be, beBuf, rr, stopAtr, quiet;
   int    pdDoneDay;
   bool   vOpen, vMoved, vTaken;
   int    vDir, vWeek;
   double vEntry, vStop, vTgt, vR;

   string GV(string k) { return Pfx() + StringFormat("%I64u_%s", magic, k); }

   bool Init(string t, ulong mg, double rk, int dn, int s0, int s1, bool d1, bool reg, int en, int md,
             double b, double bb, double rr_, double sa, double q)
     {
      tag = t; magic = mg; risk = rk; don = dn; sesS = s0; sesE = s1; useD1 = d1; useRegime = reg; eqN = en;
      eqMin = InpEqMinR; maxDay = md; sellMult = 1.0; be = b; beBuf = bb; rr = rr_; stopAtr = sa; quiet = q;
      pdDoneDay = -1; vOpen = false;
      trade.SetExpertMagicNumber(magic);
      hEma = iMA(_Symbol, _Period, InpTrendEMA, 0, MODE_EMA, PRICE_CLOSE);
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
      return s >= eqMin - 1e-9;
     }

   bool WeekOK(int wk)
     {
      if(InpWeekStopR >= 0) return true;
      if((int)GlobalVariableGet(GV("wk")) != wk) { GlobalVariableSet(GV("wk"), wk); GlobalVariableSet(GV("wkR"), 0); }
      return GlobalVariableGet(GV("wkR")) > InpWeekStopR + 1e-9;
     }

   bool DayOK()
     {
      if(maxDay <= 0) return true;
      int dk = DayKey(TimeCurrent());
      if((int)GlobalVariableGet(GV("dk")) != dk) { GlobalVariableSet(GV("dk"), dk); GlobalVariableSet(GV("dn"), 0); }
      return GlobalVariableGet(GV("dn")) < maxDay;
     }

   bool RegimeOK()
     {
      if(!useRegime || InpRegimeMax <= 0) return true;
      int nS = 96 * 5, nL = 96 * 60;
      double hi[], lo[], cl[];
      if(CopyHigh(_Symbol, _Period, 2, nL, hi) != nL || CopyLow(_Symbol, _Period, 2, nL, lo) != nL ||
         CopyClose(_Symbol, _Period, 3, nL, cl) != nL) return false;
      double sS = 0, sL = 0;
      for(int i = 0; i < nL; i++)
        {
         double tr = MathMax(hi[i], cl[i]) - MathMin(lo[i], cl[i]);
         sL += tr;
         if(i >= nL - nS) sS += tr;
        }
      return sL > 0 && (sS / nS) / (sL / nL) <= InpRegimeMax;
     }

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
            if(be > 0 && !vMoved && vDir * (px - vEntry) >= be * vR)
              { vStop = vEntry + vDir * beBuf * vR; vMoved = true; }
           }
         else
           {
            PushPaper(r);
            if(vTaken && (int)GlobalVariableGet(GV("wk")) == vWeek) GlobalVariableSet(GV("wkR"), GlobalVariableGet(GV("wkR")) + r);
            vOpen = false;
           }
        }
      ulong t = Ticket();
      if(t == 0 || be <= 0 || !PositionSelectByTicket(t)) return;
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl = PositionGetDouble(POSITION_SL), tp = PositionGetDouble(POSITION_TP);
      if(tp == 0) return;
      double R = MathAbs(tp - open) / rr;
      int dg = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
      if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
        {
         double lvl = NormalizeDouble(open + beBuf * R, dg);
         if(sl < lvl && SymbolInfoDouble(_Symbol, SYMBOL_BID) >= open + be * R) trade.PositionModify(t, lvl, tp);
        }
      else
        {
         double lvl = NormalizeDouble(open - beBuf * R, dg);
         if((sl == 0 || sl > lvl) && SymbolInfoDouble(_Symbol, SYMBOL_ASK) <= open - be * R) trade.PositionModify(t, lvl, tp);
        }
     }

   void OnBar(int hour, int doy, double atr)
     {
      if(risk <= 0) return;
      bool inSes = sesS < sesE ? (hour >= sesS && hour < sesE) : (hour >= sesS || hour < sesE);
      if(!inSes) return;
      int pdDir = 0;
      if(pdDoneDay != doy)
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
      double e1 = Buf(hEma, 1), eS = Buf(hEma, 1 + InpSlopeBars);
      if(e1 == EMPTY_VALUE || eS == EMPTY_VALUE) return;
      int dir = 0;
      if(c1 > up1 && c2 <= up2 && c1 > e1 && e1 > eS) dir = 1;
      else if(c1 < dn1 && c2 >= dn2 && c1 < e1 && e1 < eS) dir = -1;
      if(dir == 0) dir = pdDir;
      if(dir == 0 || (useD1 && D1Trend() != dir) || !RegimeOK() || !DayOK()) return;
      if(maxDay > 0) GlobalVariableSet(GV("dn"), GlobalVariableGet(GV("dn")) + 1);

      double dist = MathMax(stopAtr * atr, InpMinStop);
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID), ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      vOpen = true; vDir = dir; vR = dist; vMoved = false;
      vEntry = dir == 1 ? ask : bid;
      vStop = vEntry - dir * dist; vTgt = vEntry + dir * rr * dist;
      vWeek = WeekKey(TimeCurrent());
      bool isQuiet = quiet > 0 && c1 > 0 && atr / c1 * 100.0 < quiet;
      vTaken = EquityOK() && !isQuiet && WeekOK(vWeek);
      if(!vTaken || Ticket() != 0 || !AccountOK()) return;
      if(InpMaxSpreadPts > 0 && SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) > InpMaxSpreadPts) return;
      double lots = LotsForRisk(dist, dir == -1 ? risk * sellMult : risk);
      if(lots <= 0) { Print(tag, ": lot size below broker minimum for this risk - skipped"); return; }
      int dg = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
      string cm = "GoldAsianV18-" + tag;
      if(dir == 1) trade.Buy(lots, _Symbol, ask, NormalizeDouble(ask - dist, dg), NormalizeDouble(ask + rr * dist, dg), cm);
      else         trade.Sell(lots, _Symbol, bid, NormalizeDouble(bid + dist, dg), NormalizeDouble(bid - rr * dist, dg), cm);
     }
  };

Engine eng[3];

int OnInit()
  {
   if(_Period != PERIOD_M15) { Print("V18: attach to an M15 chart"); return INIT_PARAMETERS_INCORRECT; }
   if(AccountInfoInteger(ACCOUNT_MARGIN_MODE) != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
     { Print("V18 needs a hedging account (one position per engine)"); return INIT_FAILED; }
   for(long c = ChartFirst(); c >= 0; c = ChartNext(c))
      if(c != ChartID() && ChartGetString(c, CHART_EXPERT_NAME) == MQLInfoString(MQL_PROGRAM_NAME))
        { PrintFormat("V18 already runs on chart %I64d - one instance only", c); return INIT_FAILED; }
   hAtr = iATR(_Symbol, _Period, 14);
   hD1 = iMA(_Symbol, PERIOD_D1, InpD1TrendEMA, 0, MODE_EMA, PRICE_CLOSE);
   if(hAtr == INVALID_HANDLE || hD1 == INVALID_HANDLE ||
      !eng[0].Init("v5", InpMagic, InpV_Risk, 10, 0, 6, false, false, 0, 2, InpV_BETrigger, InpV_BEBuffer, InpV_RR,
                   InpV_StopATR, 0.0) ||
      !eng[1].Init("Asia", InpMagic + 1, InpA_Risk, 10, 0, 6, true, true, InpEqTrades, 0, InpA_BETrigger, InpA_BEBuffer,
                   InpA_RR, InpA_StopATR, InpA_QuietPct) ||
      !eng[2].Init("NY", InpMagic + 2, InpN_Risk, 15, 12, 15, true, true, InpEqTrades, 0, InpN_BETrigger, InpN_BEBuffer,
                   InpN_RR, InpN_StopATR, InpN_QuietPct))
      return INIT_FAILED;
   eng[0].sellMult = InpV_SellMult;
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   IndicatorRelease(hAtr); IndicatorRelease(hD1);
   for(int i = 0; i < 3; i++) IndicatorRelease(eng[i].hEma);
   GlobalVariablesFlush();
  }

void OnTick()
  {
   for(int i = 0; i < 3; i++) eng[i].OnTickManage();
   datetime t0 = iTime(_Symbol, _Period, 0);
   if(t0 == lastBar) return;
   lastBar = t0;
   if(Bars(_Symbol, _Period) < 96 * 60 + 10) return;
   MqlDateTime bt; TimeToStruct(iTime(_Symbol, _Period, 1), bt);
   double atr = Buf(hAtr, 1);
   if(atr == EMPTY_VALUE || atr <= 0) return;
   for(int i = 0; i < 3; i++) eng[i].OnBar(bt.hour, bt.day_of_year, atr);
  }
//+------------------------------------------------------------------+
