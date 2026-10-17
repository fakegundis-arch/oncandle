//+------------------------------------------------------------------+
//|                                         GoldAsianBreakoutV5.mq5  |
//|  Gold Asian breakout v5 (results/gold/REPORT.md, section v5):     |
//|  settings CHOSEN ON 2026, checked on 2025 and Q4 2024.            |
//|  v5 defaults: Donchian 10, slope 16, stop 1.5 ATR, 4R, BE +1R ->  |
//|  +0.3R, max 2 trades/day, weekly stop -2R; daily-trend, vol cap   |
//|  and equity-curve filters OFF. Longs 12%, shorts 6%.              |
//|  v4 = v3 with side-dependent size: longs risk InpRiskPercent,     |
//|  shorts InpRiskPercent x InpShortRiskMult (shorts were weaker in  |
//|  Q4 2024, 2025 and 2026). Default 12% longs / 6% shorts.          |
//|  Attach to XAUUSD M15 on a GMT+0 server (Exness).                 |
//|  Signals = v2: Donchian(20) break with EMA(400) trend rising vs   |
//|  16 bars ago, or the first break of the previous day's high/low,  |
//|  new trades 00:00-06:00. Stop 1.5 ATR(14) (min $2), target 4R,    |
//|  stop to +0.3R at +1R. v3 adds drawdown control:                  |
//|   1. Daily trend: buy only if yesterday closed above the D1       |
//|      EMA(20), sell only if below.                                 |
//|   2. Volatility cap: skip if ATR(14) > 2 x its 100-bar median.    |
//|   3. Equity-curve filter: every signal is also traded on paper;   |
//|      a real trade is placed only if the last 10 paper trades sum  |
//|      to >= -2R.                                                   |
//|   4. Weekly stop: no new real trades for the rest of the week     |
//|      after this week's real trades lose 2R.                       |
//|  State (paper results, weekly R) is kept in terminal global       |
//|  variables, so it survives restarts.                              |
//+------------------------------------------------------------------+
#property copyright "oncandle"
#property version   "5.00"

#include <Trade/Trade.mqh>

input int    InpDonchian     = 10;    // Breakout lookback (bars)
input int    InpTrendEMA     = 400;   // Trend EMA (400 x M15 = 100 hours)
input bool   InpUsePrevDay   = true;  // Also trade the first break of the previous day's high/low
input int    InpSlopeBars    = 16;    // EMA must be rising/falling vs this many bars ago
input double InpStopATR      = 1.5;   // Stop = this x ATR(14)
input double InpMinStop      = 2.0;   // Minimum stop distance in price ($)
input double InpRR           = 4.0;   // Target = RR x stop
input double InpBETrigger    = 1.0;   // Move stop to break-even at this many R (0 = off)
input double InpBEBuffer     = 0.3;   // ...this many R past entry
input double InpRiskPercent  = 12.0;  // Risk per LONG trade, % of equity
input double InpShortRiskMult = 0.5;  // Short risk = this x InpRiskPercent
input int    InpSessionStart = 0;     // Server hour: first hour to open trades
input int    InpSessionEnd   = 6;     // Server hour: stop opening trades from this hour
input int    InpD1TrendEMA   = 0;     // Daily trend EMA (0 = off)
input double InpVolMax       = 0.0;   // Skip if ATR / median(ATR, 100 bars) above this (0 = off)
input int    InpEqTrades     = 0;     // Equity-curve filter: last N paper trades (0 = off)
input double InpEqMinR       = -2.0;  // ...must sum to at least this many R
input double InpWeekStopR    = -2.0;  // Weekly stop in R (0 = off)
input int    InpMaxSpreadPts = 0;     // Skip entries above this spread (points, 0 = off)
input int    InpMaxPerDay    = 2;     // Max real trades per day (0 = no limit)
input ulong  InpMagic        = 20261108;

CTrade   trade;
int      hEma = INVALID_HANDLE, hAtr = INVALID_HANDLE, hD1 = INVALID_HANDLE;
datetime lastBar = 0;
int      pdDoneDay = -1;

// paper trade (mirrors every signal, real or not)
bool   vOpen = false;
int    vDir = 0;
double vEntry = 0, vStop = 0, vTgt = 0, vR = 0;
bool   vMoved = false;
bool   realThis = false;            // was a real order placed for the current paper trade
double realRisk = 0;                // money at risk on the real trade

string GV(string k) { return StringFormat("GAB5_%I64u_%s", InpMagic, k); }

double Buf(int h, int s)
  {
   double v[1];
   if(CopyBuffer(h, 0, s, 1, v) != 1) return EMPTY_VALUE;
   return v[0];
  }

int WeekKey(datetime t)
  {
   MqlDateTime d; TimeToStruct(t, d);
   int dow = (d.day_of_week + 6) % 7;              // Monday = 0
   datetime monday = t - dow * 86400 - (d.hour * 3600 + d.min * 60 + d.sec);
   return (int)(monday / 86400);
  }

// ---- paper-trade history (ring of the last N results)
void PushPaper(double r)
  {
   int n = (int)GlobalVariableGet(GV("n"));
   GlobalVariableSet(GV(StringFormat("r%d", n % 100)), r);
   GlobalVariableSet(GV("n"), n + 1);
  }

bool EquityFilterOK()
  {
   if(InpEqTrades <= 0) return true;
   int n = (int)GlobalVariableGet(GV("n"));
   if(n < InpEqTrades) return true;                 // warm-up: not enough history yet
   double s = 0;
   for(int i = n - InpEqTrades; i < n; i++) s += GlobalVariableGet(GV(StringFormat("r%d", i % 100)));
   return s >= InpEqMinR;
  }

bool WeekOK()
  {
   if(InpWeekStopR >= 0) return true;
   int wk = WeekKey(TimeCurrent());
   if((int)GlobalVariableGet(GV("wk")) != wk) { GlobalVariableSet(GV("wk"), wk); GlobalVariableSet(GV("wkR"), 0); }
   return GlobalVariableGet(GV("wkR")) > InpWeekStopR;
  }

void AddWeekR(double r, datetime entryTime)
  {
   if(WeekKey(entryTime) != (int)GlobalVariableGet(GV("wk"))) return;
   GlobalVariableSet(GV("wkR"), GlobalVariableGet(GV("wkR")) + r);
  }

int OnInit()
  {
   trade.SetExpertMagicNumber(InpMagic);
   hEma = iMA(_Symbol, _Period, InpTrendEMA, 0, MODE_EMA, PRICE_CLOSE);
   hAtr = iATR(_Symbol, _Period, 14);
   if(InpD1TrendEMA > 0) hD1 = iMA(_Symbol, PERIOD_D1, InpD1TrendEMA, 0, MODE_EMA, PRICE_CLOSE);
   if(hEma == INVALID_HANDLE || hAtr == INVALID_HANDLE || (InpD1TrendEMA > 0 && hD1 == INVALID_HANDLE)) return INIT_FAILED;
   if(_Period != PERIOD_M15) Print("Warning: tested on M15 only");
   if(!GlobalVariableCheck(GV("n"))) GlobalVariableSet(GV("n"), 0);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason) { IndicatorRelease(hEma); IndicatorRelease(hAtr); if(hD1 != INVALID_HANDLE) IndicatorRelease(hD1); }

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

double LotsForRisk(double dist, double &riskMoney, double riskPct)
  {
   double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
   double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tv <= 0 || ts <= 0 || dist <= 0) return 0;
   double lots = AccountInfoDouble(ACCOUNT_EQUITY) * riskPct / 100.0 / (dist / ts * tv);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   lots = MathFloor(lots / step) * step;
   if(lots < SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN)) return 0;
   lots = MathMin(lots, SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX));
   riskMoney = lots * dist / ts * tv;
   return lots;
  }

// ---- paper trade management: same rules as the real trade (bid for longs, ask for shorts)
void ManagePaper()
  {
   if(!vOpen) return;
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID), ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double px = vDir == 1 ? bid : ask;
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
   vOpen = false;
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

// record the weekly R of a closed real trade
void OnTradeTransaction(const MqlTradeTransaction &tr, const MqlTradeRequest &rq, const MqlTradeResult &rs)
  {
   if(tr.type != TRADE_TRANSACTION_DEAL_ADD || !HistoryDealSelect(tr.deal)) return;
   if(HistoryDealGetInteger(tr.deal, DEAL_MAGIC) != (long)InpMagic) return;
   if(HistoryDealGetInteger(tr.deal, DEAL_ENTRY) != DEAL_ENTRY_OUT || realRisk <= 0) return;
   double pnl = HistoryDealGetDouble(tr.deal, DEAL_PROFIT) + HistoryDealGetDouble(tr.deal, DEAL_SWAP)
              + HistoryDealGetDouble(tr.deal, DEAL_COMMISSION);
   ulong pos = HistoryDealGetInteger(tr.deal, DEAL_POSITION_ID);
   datetime opened = TimeCurrent();
   if(HistorySelectByPosition(pos))
      for(int i = 0; i < HistoryDealsTotal(); i++)
        {
         ulong d = HistoryDealGetTicket(i);
         if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN) opened = (datetime)HistoryDealGetInteger(d, DEAL_TIME);
        }
   AddWeekR(pnl / realRisk, opened);
   realRisk = 0;
  }

bool VolOK(double atr)
  {
   if(InpVolMax <= 0) return true;
   double a[];
   if(CopyBuffer(hAtr, 0, 1, 100, a) != 100) return true;
   ArraySort(a);
   double med = (a[49] + a[50]) / 2.0;
   return med <= 0 || atr / med <= InpVolMax;
  }

int D1Trend()
  {
   if(InpD1TrendEMA <= 0) return 0;
   double e = Buf(hD1, 1), c = iClose(_Symbol, PERIOD_D1, 1);
   if(e == EMPTY_VALUE || c <= 0) return 0;
   return c > e ? 1 : (c < e ? -1 : 0);
  }

void OnTick()
  {
   ManagePaper();
   ulong ticket = 0;
   bool inPos = HasPosition(ticket);
   if(inPos) ManageBreakEven(ticket);

   datetime t0 = iTime(_Symbol, _Period, 0);
   if(t0 == lastBar) return;
   lastBar = t0;
   if(Bars(_Symbol, _Period) < InpTrendEMA + InpDonchian + 10) return;

   MqlDateTime bt; TimeToStruct(iTime(_Symbol, _Period, 1), bt);
   bool inSession = InpSessionStart < InpSessionEnd ? (bt.hour >= InpSessionStart && bt.hour < InpSessionEnd)
                                                    : (bt.hour >= InpSessionStart || bt.hour < InpSessionEnd);
   if(!inSession) return;

   int pdDir = 0;
   if(InpUsePrevDay && pdDoneDay != bt.day_of_year)
     {
      double c1b = iClose(_Symbol, _Period, 1);
      double pdh = iHigh(_Symbol, PERIOD_D1, 1), pdl = iLow(_Symbol, PERIOD_D1, 1);
      if(pdh > 0 && c1b > pdh)      pdDir = 1;
      else if(pdl > 0 && c1b < pdl) pdDir = -1;
      if(pdDir != 0) pdDoneDay = bt.day_of_year;
     }
   if(vOpen) return;                                // one (paper) trade at a time, as in the backtest

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
   if(dir == 0) dir = pdDir;
   if(dir == 0) return;
   int d1 = D1Trend();
   if(InpD1TrendEMA > 0 && d1 != dir) return;      // filters that define the signal (paper trades too)
   if(!VolOK(atr)) return;

   double dist = MathMax(InpStopATR * atr, InpMinStop);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID), ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   // open the paper trade
   vOpen = true; vDir = dir; vR = dist; vMoved = false;
   vEntry = dir == 1 ? ask : bid;
   vStop = vEntry - dir * dist; vTgt = vEntry + dir * InpRR * dist;

   // real trade only if the overlays allow it
   if(inPos || !EquityFilterOK() || !WeekOK()) return;
   if(InpMaxPerDay > 0)
     {
      MqlDateTime d; TimeToStruct(TimeCurrent(), d);
      int dk = d.year * 10000 + d.mon * 100 + d.day;
      if((int)GlobalVariableGet(GV("dk")) != dk) { GlobalVariableSet(GV("dk"), dk); GlobalVariableSet(GV("dn"), 0); }
      if(GlobalVariableGet(GV("dn")) >= InpMaxPerDay) return;
     }
   if(InpMaxSpreadPts > 0 && SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) > InpMaxSpreadPts) return;
   double riskMoney = 0;
   double lots = LotsForRisk(dist, riskMoney, dir == 1 ? InpRiskPercent : InpRiskPercent * InpShortRiskMult);
   if(lots <= 0) { Print("Lot size below broker minimum for this risk - skipped"); return; }
   int dg = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   bool ok = dir == 1 ? trade.Buy(lots, _Symbol, ask, NormalizeDouble(ask - dist, dg), NormalizeDouble(ask + InpRR * dist, dg), "GoldAsianV5")
                      : trade.Sell(lots, _Symbol, bid, NormalizeDouble(bid + dist, dg), NormalizeDouble(bid - InpRR * dist, dg), "GoldAsianV5");
   if(ok)
     {
      realRisk = riskMoney;
      if(InpMaxPerDay > 0) GlobalVariableSet(GV("dn"), GlobalVariableGet(GV("dn")) + 1);
     }
  }
//+------------------------------------------------------------------+
