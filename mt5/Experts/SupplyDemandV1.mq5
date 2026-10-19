//+------------------------------------------------------------------+
//|                                              SupplyDemandV1.mq5  |
//|  Supply & demand v1 (results/sd/REPORT.md; backtester/sd.py,      |
//|  scripts/sd_v1.py). Chosen on 2026 only.                          |
//|  Zone (chart bars, default M15): a BASE of 1..InpMaxBase small    |
//|  candles (range <= InpBaseATR x ATR) and one LEG-OUT candle       |
//|  (range >= InpLegATR x ATR, body >= half its range) closing       |
//|  beyond the base; ATR(14) of the bar before the leg-out.          |
//|   demand: proximal = highest base body, distal = lowest low of    |
//|           base + leg-out;  supply: mirror image.                  |
//|  Only reversal bases by default (drop-base-rally, rally-base-     |
//|  drop: the candle before the base points against the leg-out).    |
//|  Each zone is traded once: the FIRST time the ask (demand) / bid  |
//|  (supply) reaches the entry line, within InpAgeBars bars. If a    |
//|  position is already open, that touch uses the zone up. Stop      |
//|  A first touch that is already beyond the distal line (a gap      |
//|  through the zone) or comes in the first 15 minutes after a       |
//|  market reopen cancels the zone instead. Stop                     |
//|  InpBufATR x ATR beyond the distal line (at least InpMinStop),    |
//|  target InpRR x the risk. One position at a time.                 |
//|  Attach to XAUUSD M15 (Exness, server time UTC).                  |
//+------------------------------------------------------------------+
#property copyright "oncandle"
#property version   "1.00"

#include <Trade/Trade.mqh>

input double InpRiskPct   = 2.0;    // % of balance risked per trade
input double InpBaseATR   = 0.75;   // base candle max range (x ATR)
input int    InpMaxBase   = 3;      // max base candles
input double InpLegATR    = 1.25;   // leg-out min range (x ATR)
input double InpMaxHeight = 1.5;    // max zone height (x ATR)
input int    InpPattern   = 1;      // 0 = all bases, 1 = reversal only, 2 = continuation only
input int    InpTrend     = 2;      // 0 = none, 1 = with EMA(200) of chart bars, 2 = with yesterday's D1 close vs EMA(20)
input bool   InpEntryMid  = true;   // false = entry at the proximal line, true = at the zone middle
input double InpBufATR    = 0.25;   // stop beyond the distal line (x ATR)
input double InpMinStop   = 1.5;    // minimum stop distance (price units)
input double InpRR        = 4.0;    // target (x risk)
input double InpBE        = 1.0;    // >0: stop to entry + 0.1R after this many R (0 = off)
input int    InpAgeBars   = 24;     // zone valid for this many bars after the leg-out
input bool   InpSession   = false;  // true: trade first touches only 07:00-20:00 UTC (other touches use the zone up)
input ulong  InpMagic     = 20261201;

struct Zone { datetime t; int dir; double prox, dist, lvl, atr; bool used; };
Zone     zones[];
int      hAtr = INVALID_HANDLE, hEma = INVALID_HANDLE, hD1 = INVALID_HANDLE;
datetime lastBar = 0;
CTrade   trade;

bool HasPosition()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == (long)InpMagic) return true;
     }
   return false;
  }

double AtrAt(int shift)
  {
   double v[1];
   if(CopyBuffer(hAtr, 0, shift, 1, v) != 1) return 0;
   return v[0];
  }

int TrendAt(int legShift)
  {
   if(InpTrend == 1)
     {
      double v[1];
      if(CopyBuffer(hEma, 0, legShift, 1, v) != 1) return 0;
      double c = iClose(_Symbol, _Period, legShift);
      return c > v[0] ? 1 : (c < v[0] ? -1 : 0);
     }
   if(InpTrend == 2)
     {
      int ds = iBarShift(_Symbol, PERIOD_D1, iTime(_Symbol, _Period, legShift), false) + 1;   // the day before
      double v[1];
      if(ds < 1 || CopyBuffer(hD1, 0, ds, 1, v) != 1) return 0;
      double c = iClose(_Symbol, PERIOD_D1, ds);
      return c > v[0] ? 1 : (c < v[0] ? -1 : 0);
     }
   return 0;
  }

// zone whose leg-out candle is the bar at `s` (s >= 1); returns false if there is none
bool ZoneAt(int s, Zone &z)
  {
   double a = AtrAt(s + 1);
   if(a <= 0) return false;
   double o = iOpen(_Symbol, _Period, s), h = iHigh(_Symbol, _Period, s), l = iLow(_Symbol, _Period, s), c = iClose(_Symbol, _Period, s);
   double rng = h - l;
   if(rng < InpLegATR * a || MathAbs(c - o) < 0.5 * rng) return false;
   int d = c > o ? 1 : -1;
   int cnt = 0;
   while(cnt <= 6 && iHigh(_Symbol, _Period, s + 1 + cnt) - iLow(_Symbol, _Period, s + 1 + cnt) <= InpBaseATR * a) cnt++;
   if(cnt == 0 || cnt > InpMaxBase) return false;
   double hi = -DBL_MAX, lo = DBL_MAX, btop = -DBL_MAX, bbot = DBL_MAX;
   for(int q = s + 1; q <= s + cnt; q++)
     {
      double qo = iOpen(_Symbol, _Period, q), qc = iClose(_Symbol, _Period, q);
      hi = MathMax(hi, iHigh(_Symbol, _Period, q)); lo = MathMin(lo, iLow(_Symbol, _Period, q));
      btop = MathMax(btop, MathMax(qo, qc)); bbot = MathMin(bbot, MathMin(qo, qc));
     }
   double prox, dist;
   if(d == 1) { if(c <= hi) return false; prox = btop; dist = MathMin(lo, l); }
   else       { if(c >= lo) return false; prox = bbot; dist = MathMax(hi, h); }
   if(d * (prox - dist) <= 0 || MathAbs(prox - dist) > InpMaxHeight * a) return false;
   int k = s + cnt + 1;
   double ko = iOpen(_Symbol, _Period, k), kc = iClose(_Symbol, _Period, k);
   int pat = kc == ko ? 0 : ((kc > ko) == (d == 1) ? 2 : 1);
   if(InpPattern != 0 && pat != InpPattern) return false;
   if(InpTrend != 0 && TrendAt(s) != d) return false;
   z.t = iTime(_Symbol, _Period, s); z.dir = d; z.prox = prox; z.dist = dist; z.atr = a; z.used = false;
   z.lvl = InpEntryMid ? (prox + dist) / 2.0 : prox;
   return true;
  }

void AddZone(Zone &z)
  {
   int n = ArraySize(zones);
   ArrayResize(zones, n + 1);
   zones[n] = z;
  }

// zone still valid: no more than InpAgeBars bars after its leg-out bar
bool Alive(Zone &z) { return !z.used && iBarShift(_Symbol, _Period, z.t, false) <= InpAgeBars; }

void Prune()
  {
   int m = 0;
   for(int i = 0; i < ArraySize(zones); i++)
      if(Alive(zones[i])) { if(m != i) zones[m] = zones[i]; m++; }
   ArrayResize(zones, m);
  }

// after a restart: rebuild the zones of the last InpAgeBars bars and mark those already touched
void Rebuild()
  {
   ArrayResize(zones, 0);
   double sp = SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID);
   for(int s = InpAgeBars; s >= 1; s--)
     {
      Zone z;
      if(!ZoneAt(s, z)) continue;
      for(int q = s - 1; q >= 0 && !z.used; q--)
         z.used = z.dir == 1 ? iLow(_Symbol, _Period, q) + sp <= z.lvl : iHigh(_Symbol, _Period, q) >= z.lvl;
      if(!z.used) AddZone(z);
     }
   PrintFormat("SupplyDemandV1: %d live zones after rebuild", ArraySize(zones));
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
   double px = z.dir == 1 ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double stopLvl = z.dist - z.dir * InpBufATR * z.atr;
   double R = MathMax(z.dir * (px - stopLvl), InpMinStop);
   double lots = Lots(R);
   if(lots <= 0) { Print("SupplyDemandV1: lot size below the broker minimum - zone skipped"); return; }
   double sl = NormalizeDouble(px - z.dir * R, dg), tp = NormalizeDouble(px + z.dir * InpRR * R, dg);
   bool ok = z.dir == 1 ? trade.Buy(lots, _Symbol, 0, sl, tp, "SDv1 demand") : trade.Sell(lots, _Symbol, 0, sl, tp, "SDv1 supply");
   if(!ok) PrintFormat("SupplyDemandV1: order failed, retcode %u", trade.ResultRetcode());
  }

void ManageBE()
  {
   if(InpBE <= 0) return;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != (long)InpMagic) continue;
      double open = PositionGetDouble(POSITION_PRICE_OPEN), sl = PositionGetDouble(POSITION_SL), tp = PositionGetDouble(POSITION_TP);
      double R = MathAbs(tp - open) / InpRR;
      int dg = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
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
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetTypeFillingBySymbol(_Symbol);
   hAtr = iATR(_Symbol, _Period, 14);
   hEma = iMA(_Symbol, _Period, 200, 0, MODE_EMA, PRICE_CLOSE);
   hD1 = iMA(_Symbol, PERIOD_D1, 20, 0, MODE_EMA, PRICE_CLOSE);
   if(hAtr == INVALID_HANDLE || hEma == INVALID_HANDLE || hD1 == INVALID_HANDLE) return INIT_FAILED;
   if(Bars(_Symbol, _Period) > InpAgeBars + 30) Rebuild();
   lastBar = iTime(_Symbol, _Period, 0);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   IndicatorRelease(hAtr); IndicatorRelease(hEma); IndicatorRelease(hD1);
  }

// first 15 minutes after a pause of more than 30 minutes in M1 bars (weekend / daily break): spreads are wide
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

void OnTick()
  {
   datetime t0 = iTime(_Symbol, _Period, 0);
   if(t0 != lastBar)
     {
      lastBar = t0;
      Zone z;
      if(Bars(_Symbol, _Period) > 30 && ZoneAt(1, z)) AddZone(z);
      Prune();
     }
   ManageBE();
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK), bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   MqlDateTime now; TimeToStruct(TimeCurrent(), now);
   bool inSession = !InpSession || (now.hour >= 7 && now.hour < 20);
   for(int i = 0; i < ArraySize(zones); i++)
     {
      if(!Alive(zones[i])) continue;
      bool touched = zones[i].dir == 1 ? ask <= zones[i].lvl : bid >= zones[i].lvl;
      if(!touched) continue;
      zones[i].used = true;                       // first touch uses the zone up, traded or not
      bool through = zones[i].dir == 1 ? ask <= zones[i].dist : bid >= zones[i].dist;
      if(through || ReopenWindow()) continue;     // gapped through the zone / reopen spread: cancelled
      if(inSession && !HasPosition()) Enter(zones[i]);
     }
  }
//+------------------------------------------------------------------+
