# GoldHybrid A.I. — Albion Trading Desk
**Version:** 1.1.0 | **Port:** 5043 | **Status:** Paper Trading | **Part of:** Hybrid Desk

Part of the Albion Trading Desk — a multi-system AI paper trading operation built by Nick, running on a dedicated Dell Optiplex (Windows 11 Pro).

**Market:** Gold XAU — Capital.com
**Broker:** Capital.com demo (account Z6CJSM, £1,000 virtual)
**Theme:** Gold #FFD700

## What GoldHybrid is — a SURGICAL hybrid (not a Lancelot-entry hybrid)
GoldHybrid is **GoldTrader v1.3.0 with two evidence-based changes** from Gaius
Commission 006 (22 Jul 2026). Unlike FTSEHybrid / USHybrid / NikkeiHybrid — which hand
entry entirely to Lancelot — **Arthur still gates every entry here** and still manages
exits. The Hybrid Desk means "the best evidence-based version of each system," not one
fixed architecture. The two changes:

1. **RSI ceiling relaxed (the primary fix).** Commission 006 proved GoldTrader's missed
   winners were Arthur's own RSI>70 veto on LONGs during trend-confirmed rallies (the
   22 Jul rally GoldBenchmark banked at +£35.58). GoldHybrid raises the LONG RSI ceiling
   from 70 → **80 when daily AND 1h SSL are both BULL** (a rising RSI in an SSL-confirmed
   uptrend is momentum, not a reversal). Above 80 = overbought regardless of trend.
   SHORT RSI floor (<30) unchanged — the finding was LONG-specific. Implemented as a
   live per-tick ceiling in Arthur's REGIME block plus explicit prompt guidance (there
   was never a mechanical ceiling — the veto was Arthur's judgment).
2. **Morgan floor — warning + MANUAL reset (v1.1.0, was automatic in v1.0.0).** Morgan
   tracks freely and MAY drop below 50 (a genuine learning signal). When it does, the
   dashboard shows a "⚠️ MORGAN BELOW FLOOR" warning + a "RESET MORGAN TO 50" button, and
   the Archie Brief flags it. Nick reviews the phantom/trade evidence and consciously
   resets (via `/api/reset-morgan`, applied live). NOT an automatic clamp — an auto-floor
   silently hid drops and removed Nick's visibility/control. Desk-wide principle for
   hybrids: Morgan warning + manual reset, never an automatic floor.

Everything else is identical to GoldTrader: Arthur entry+exit, 30pt stop / 50pt target /
0.3 spread, session 22:00-21:00 UTC, Asian SHORT filter, Morgan SHORT gate ≥60,
Guinevere, Profit Protection Ladder, **full phantom logging** (Arthur still makes entry
decisions, so STAY_OUT phantoms remain meaningful), 5-min polling (Commission 006:
1-min polling ≈ 0 benefit on Gold). Dashboard on http://localhost:5043.

## The Team (Arthurian Naming)
| Role | Name | Function |
|------|------|----------|
| AI Brain | Arthur | Claude AI decision engine |
| Data Feed | Merlin | Market data and indicators |
| Pre-checks | Lancelot | Entry validation |
| Broker | Excalibur | Capital.com connector |
| Calendar | Guinevere | Economic calendar filter |
| Performance | Morgan | P&L tracker + confidence |
| Watchdog | Galahad | Auto-restart |
| Notifier | Percival | Pushover alerts |
| Trader | Stanley | Paper trade execution |

## Phantom P&L Tracker
Records every STAY OUT decision with hindsight scoring. Feeds the STAY OUT QUALITY panel and Morgan's confidence. Data saved to: logs/phantom_trades.csv
