//+------------------------------------------------------------------+
//|                                              SupplyDemandV2.mq5  |
//|  Supply & demand v2 (results/sd/REPORT.md; scripts/               |
//|  sd_v2_strategy.py). Found by an agent search on 2026 only.       |
//|  ZONE (chart bars, M15): a fair-value gap - demand when           |
//|  low[i] > high[i-2]: proximal = low[i], distal = low[i-2];        |
//|  supply mirrored. Height <= InpMaxHeight x ATR(14) of bar i-3.    |
//|  ACTIVATION: the impulse must break structure - a close beyond    |
//|  the last unbroken M15 swing (fractal, InpSwingL bars each side)  |
//|  as of bar i-2, among bars i-1 .. i+InpBosWindow (never before    |
//|  bar i's close). A touch before activation kills the zone.        |
//|  DAILY FILTER: daily fractal swings (InpDailyL bars each side):   |
//|  higher highs AND higher lows AND the last break up (mirrored     |
//|  for supply), read from the last completed daily bar.             |
//|  ENTRY: first touch of the proximal line within InpAgeBars bars   |
//|  after activation; a touch beyond the distal line or in the first |
//|  15 minutes after a market reopen cancels the zone. Stop          |
//|  InpBufATR x ATR beyond the distal line (at least InpMinStop),    |
//|  target InpRR x risk, stop to +0.1R after +InpBE R.               |
//|  One position at a time. Attach to XAUUSD M15, GMT+0 server.      |
//|  WARNING: 2025 (unseen) at 10% risk: $1,000 -> $336, -98.5%       |
//|  drawdown although the strategy made +30.6R (PF 1.37).            |
//+------------------------------------------------------------------+
#property copyright "oncandle"
#property version   "2.01"

#include <Trade/Trade.mqh>

input double InpRiskPct    = 10.0;  // % of balance risked per trade (see the warning above)
input double InpMaxHeight  = 1.0;   // max gap height (x ATR)
input int    InpSwingL     = 3;     // M15 swing: bars each side
input int    InpBosWindow  = 12;    // bars after the gap allowed to break structure
input int    InpDailyL     = 4;     // daily swing: bars each side
input double InpBufATR     = 0.25;  // stop beyond the distal line (x ATR)
input double InpMinStop    = 1.5;   // minimum risk distance (price units)
input double InpRR         = 12.0;  // target (x risk)
input double InpBE         = 1.0;   // stop to entry + 0.1R after this many R (0 = off)
input int    InpAgeBars    = 96;    // order valid this many bars after activation
input double InpReplaySpread = 0.25; // spread assumed when a restart replays bar lows (= the backtest cost)
input ulong  InpMagic      = 20261202;

struct Zone { datetime tGap; int dir; double prox, dist, atr, ref; bool active, used; datetime tAct; };
Zone     zones[];
datetime lastBar = 0, dailyFor = 0, exitMin = 0;
int      dTrend = 0, dHHHL = 0;
bool     needRebuild = true, hadPos = false;
CTrade   trade;

// fractal swing structure, same as sd_v2_strategy._structure: per bar (oldest first) trend (last break),
// hhhl (+1 higher highs and higher lows, -1 lower), last unbroken swing high / low (EMPTY_VALUE if broken)
void Structure(const double &h[], const double &l[], const double &c[], int L, int &trend[], int &hh[], double &osh[], double &osl[])
  {
   int n = ArraySize(h);
   ArrayResize(trend, n); ArrayResize(hh, n); ArrayResize(osh, n); ArrayResize(osl, n);
   double lastSH = EMPTY_VALUE, prevSH = EMPTY_VALUE, lastSL = EMPTY_VALUE, prevSL = EMPTY_VALUE;
   bool brokeH = true, brokeL = true; int tr = 0;
   for(int b = 0; b < n; b++)
     {
      int j = b - L;
      if(j >= L)
        {
         bool isH = true, isL = true;
         for(int q = j - L; q <= j + L; q++)
           {
            if(q == j) continue;
            if(h[q] > h[j] || (q < j && h[q] == h[j])) isH = false;
            if(l[q] < l[j] || (q < j && l[q] == l[j])) isL = false;
           }
         if(isH) { prevSH = lastSH; lastSH = h[j]; brokeH = false; }
         if(isL) { prevSL = lastSL; lastSL = l[j]; brokeL = false; }
        }
      if(!brokeH && c[b] > lastSH) { tr = 1; brokeH = true; }
      if(!brokeL && c[b] < lastSL) { tr = -1; brokeL = true; }
      trend[b] = tr;
      bool both = lastSH != EMPTY_VALUE && prevSH != EMPTY_VALUE && lastSL != EMPTY_VALUE && prevSL != EMPTY_VALUE;
      hh[b] = !both ? 0 : ((lastSH > prevSH && lastSL > prevSL) ? 1 : ((lastSH < prevSH && lastSL < prevSL) ? -1 : 0));
      osh[b] = brokeH ? EMPTY_VALUE : lastSH;
      osl[b] = brokeL ? EMPTY_VALUE : lastSL;
     }
  }

// `count` closed bars of `tf` ending at shift `last` (>= 1), oldest first
bool Closed(ENUM_TIMEFRAMES tf, int last, int count, double &h[], double &l[], double &c[], datetime &t[])
  {
   ArraySetAsSeries(h, false); ArraySetAsSeries(l, false); ArraySetAsSeries(c, false); ArraySetAsSeries(t, false);
   return CopyHigh(_Symbol, tf, last, count, h) == count && CopyLow(_Symbol, tf, last, count, l) == count &&
          CopyClose(_Symbol, tf, last, count, c) == count && CopyTime(_Symbol, tf, last, count, t) == count;
  }

// daily state from the last completed D1 bar; computed once per day, retried on every tick until the D1 series has today
void UpdateDaily()
  {
   datetime d0 = iTime(_Symbol, PERIOD_D1, 0);
   if(d0 != 0 && d0 == dailyFor) return;
   dTrend = 0; dHHHL = 0; dailyFor = 0;
   long today = (long)TimeCurrent() / 86400 * 86400;
   if(d0 == 0 || (long)d0 < today) return;                 // D1 not updated to today yet: no trades, retry
   double h[], l[], c[]; datetime t[];
   int n = MathMin(400, Bars(_Symbol, PERIOD_D1) - 1);
   if(n < 4 * InpDailyL + 4 || !Closed(PERIOD_D1, 1, n, h, l, c, t)) return;
   int tr[], hh[]; double osh[], osl[];
   Structure(h, l, c, InpDailyL, tr, hh, osh, osl);
   dTrend = tr[n - 1]; dHHHL = hh[n - 1]; dailyFor = d0;
  }

// ATR(14) of bar j (oldest-first arrays) = simple mean of the true range of bars j-13 .. j, as MT5 iATR and
// backtester.indicators.atr; from prices, so it also works inside OnInit / Rebuild (no indicator handle to wait for)
double AtrOf(const double &h[], const double &l[], const double &c[], int j)
  {
   if(j < 14) return 0;
   double s = 0;
   for(int k = j - 13; k <= j; k++) s += MathMax(h[k], c[k - 1]) - MathMin(l[k], c[k - 1]);
   return s / 14.0;
  }

// at the close of the bar at shift `sh` (1 live, more in Rebuild): activation of pending gaps, then a new gap at that bar;
// false when the bars could not be read (the caller replays later)
bool OnNewBar(int sh)
  {
   int n = 600;
   double h[], l[], c[]; datetime t[];
   if(Bars(_Symbol, _Period) < n + sh + 20 || !Closed(_Period, sh, n, h, l, c, t)) return false;
   int tr[], hh[]; double osh[], osl[];
   Structure(h, l, c, InpSwingL, tr, hh, osh, osl);
   int i = n - 1;                                   // the bar that just closed
   // pending zones: activation by this bar's close (window up to InpBosWindow bars after the gap bar)
   for(int z = 0; z < ArraySize(zones); z++)
     {
      if(zones[z].active || zones[z].used) continue;
      int age = iBarShift(_Symbol, _Period, zones[z].tGap, false) - sh;   // bars closed since the gap bar
      if(age > InpBosWindow) { zones[z].used = true; continue; }
      if(zones[z].dir * (c[i] - zones[z].ref) > 0) { zones[z].active = true; zones[z].tAct = t[i]; }
     }
   // new gap at bar i
   double a = AtrOf(h, l, c, i - 3);                // ATR(14) of bar i-3
   if(a <= 0) return true;
   Zone zn; zn.used = false; zn.active = false; zn.tGap = t[i]; zn.atr = a; zn.tAct = 0;
   if(l[i] > h[i - 2])      { zn.dir = 1;  zn.prox = l[i]; zn.dist = l[i - 2]; zn.ref = osh[i - 2]; }
   else if(h[i] < l[i - 2]) { zn.dir = -1; zn.prox = h[i]; zn.dist = h[i - 2]; zn.ref = osl[i - 2]; }
   else return true;
   if(MathAbs(zn.prox - zn.dist) > InpMaxHeight * a || zn.ref == EMPTY_VALUE) return true;
   // activation already by the close of bar i-1 or bar i (activation is never before bar i's close)
   if(zn.dir * (c[i - 1] - zn.ref) > 0 || zn.dir * (c[i] - zn.ref) > 0) { zn.active = true; zn.tAct = t[i]; }
   int m = ArraySize(zones); ArrayResize(zones, m + 1); zones[m] = zn;
   return true;
  }

bool Expired(Zone &z) { return z.active && iBarShift(_Symbol, _Period, z.tAct, false) > InpAgeBars; }

// after a restart (or bars that had no ticks here): replay the last bars - touches (from bar highs / lows at the
// backtest's spread) use zones up, closes activate and create them; false when the history is not ready yet
bool Rebuild()
  {
   ArrayResize(zones, 0);
   double sp = InpReplaySpread;
   for(int s = InpAgeBars + InpBosWindow + 5; s >= 0; s--)
     {
      double hi = iHigh(_Symbol, _Period, s), lo = iLow(_Symbol, _Period, s);
      for(int z = 0; z < ArraySize(zones); z++)
        {
         if(zones[z].used) continue;
         if(zones[z].active && iBarShift(_Symbol, _Period, zones[z].tAct, false) - s > InpAgeBars) { zones[z].used = true; continue; }
         if(zones[z].dir == 1 ? lo + sp <= zones[z].prox : hi >= zones[z].prox) zones[z].used = true;
        }
      if(s >= 1 && !OnNewBar(s)) { ArrayResize(zones, 0); return false; }
     }
   Prune();
   PrintFormat("SupplyDemandV2: %d zones after rebuild", ArraySize(zones));
   return true;
  }

void Prune()
  {
   int m = 0;
   for(int i = 0; i < ArraySize(zones); i++)
      if(!zones[i].used && !Expired(zones[i])) { if(m != i) zones[m] = zones[i]; m++; }
   ArrayResize(zones, m);
  }

bool HasPosition()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == (long)InpMagic) return true;
     }
   return false;
  }

// first 15 minutes after a pause of more than 30 minutes in M1 bars (weekend / daily break)
bool ReopenWindow()
  {
   datetime now = TimeCurrent();
   for(int q = 0; q < 16; q++)
     {
      datetime a = iTime(_Symbol, PERIOD_M1, q), b = iTime(_Symbol, PERIOD_M1, q + 1);
      if(a == 0 || b == 0) return false;
      if(now - a >= 15 * 60) return false;
      if(a - b > 30 * 60) return true;
     }
   return false;
  }

double Lots(double risk)
  {
   double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS), ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(tv <= 0 || ts <= 0 || risk <= 0 || step <= 0) return 0;
   double lots = MathFloor(AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPct / 100.0 / (risk / ts * tv) / step + 1e-9) * step;
   if(lots < SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN)) return 0;
   return MathMin(lots, SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX));
  }

void Enter(Zone &z)
  {
   int dg = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double stopLvl = z.dist - z.dir * InpBufATR * z.atr;
   double R = MathMax(z.dir * (z.prox - stopLvl), InpMinStop);
   double sl = NormalizeDouble(z.prox - z.dir * R, dg), tp = NormalizeDouble(z.prox + z.dir * InpRR * R, dg);
   double lots = Lots(R);
   if(lots <= 0) { Print("SupplyDemandV2: lot size below the broker minimum - zone skipped"); return; }
   bool ok = z.dir == 1 ? trade.Buy(lots, _Symbol, 0, sl, tp, "SDv2 demand") : trade.Sell(lots, _Symbol, 0, sl, tp, "SDv2 supply");
   if(!ok) PrintFormat("SupplyDemandV2: order failed, retcode %u", trade.ResultRetcode());
  }

void ManageBE()
  {
   if(InpBE <= 0) return;
   int dg = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != (long)InpMagic) continue;
      double open = PositionGetDouble(POSITION_PRICE_OPEN), sl = PositionGetDouble(POSITION_SL), tp = PositionGetDouble(POSITION_TP);
      double R = MathAbs(tp - sl) / (InpRR + 1.0);          // initial stop and target are R and InpRR x R from the line
      if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
        {
         double lvl = NormalizeDouble(open + 0.1 * R, dg);
         if(sl < lvl && SymbolInfoDouble(_Symbol, SYMBOL_BID) >= open + InpBE * R) trade.PositionModify(t, lvl, tp);
        }
      else
        {
         double lvl = NormalizeDouble(open - 0.1 * R, dg);
         if(sl > lvl && SymbolInfoDouble(_Symbol, SYMBOL_ASK) <= open - InpBE * R) trade.PositionModify(t, lvl, tp);
        }
     }
  }

int OnInit()
  {
   if(_Period != PERIOD_M15) { Print("SupplyDemandV2: attach to an M15 chart"); return INIT_PARAMETERS_INCORRECT; }
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetTypeFillingBySymbol(_Symbol);
   if(!MQLInfoInteger(MQL_TESTER) && MathAbs((long)(TimeTradeServer() - TimeGMT())) > 600)
      Print("SupplyDemandV2: WARNING - server time is not GMT+0; D1 bars and the daily filter will not match the backtest");
   needRebuild = true; dailyFor = 0; exitMin = 0;
   hadPos = HasPosition();
   return INIT_SUCCEEDED;                     // zones are rebuilt on the first tick, once the history is there
  }

void OnDeinit(const int reason) { }

void OnTick()
  {
   datetime t0 = iTime(_Symbol, _Period, 0);
   if(t0 == 0) return;
   if(needRebuild || t0 != lastBar)
     {
      int missed = needRebuild ? 0 : iBarShift(_Symbol, _Period, lastBar, false);   // 1 = exactly one bar closed
      if(!(missed == 1 && OnNewBar(1)))
         if(!Rebuild()) { needRebuild = true; return; }     // history not ready: no trading, retry on the next tick
      Prune();
      lastBar = t0; needRebuild = false;
     }
   UpdateDaily();
   ManageBE();
   bool pos = HasPosition();
   if(hadPos && !pos) exitMin = iTime(_Symbol, PERIOD_M1, 0);   // backtest: no entry in the minute a trade closed
   hadPos = pos;
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK), bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   for(int i = 0; i < ArraySize(zones); i++)
     {
      if(zones[i].used || Expired(zones[i])) continue;
      bool touched = zones[i].dir == 1 ? ask <= zones[i].prox : bid >= zones[i].prox;
      if(!touched) continue;
      zones[i].used = true;                                   // the first touch uses the zone up
      if(!zones[i].active) continue;                          // touched before the break of structure: dead
      bool through = zones[i].dir == 1 ? ask <= zones[i].dist : bid >= zones[i].dist;
      if(through || ReopenWindow()) continue;
      if(dTrend != zones[i].dir || dHHHL != zones[i].dir) continue;   // daily structure must agree at the fill
      if(!HasPosition() && iTime(_Symbol, PERIOD_M1, 0) != exitMin) { Enter(zones[i]); hadPos = HasPosition(); }
     }
  }
//+------------------------------------------------------------------+
