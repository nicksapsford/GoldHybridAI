## [1.0.0] - 2026-07-22  —  GoldHybrid fork (surgical hybrid)
### Added — GoldHybrid, Hybrid Desk system (port 5043), cloned from GoldTrader v1.3.0
Implements Gaius Commission 006 (Gold System Review). A SURGICAL hybrid: Arthur STILL
gates entry and manages exits (NOT a Lancelot-entry hybrid like FTSE/US/Nikkei). Two
evidence-based changes; everything else identical to GoldTrader v1.3.0.

- **RSI ceiling relaxed (primary fix).** `agent_brain_gold.py`: the LONG RSI ceiling is
  now 70 normally but **80 when daily AND 1h SSL are both BULL** (trend-confirmed
  momentum). Implemented as (a) a live per-tick "LONG RSI ceiling" line computed in
  `_regime_block` (now takes `bar_1h`) and injected into Arthur's REGIME AND GATE block,
  and (b) explicit "RSI CEILING FOR LONGs" guidance in the system prompt. NB there was
  never a mechanical RSI>70 gate — Commission 006 established the veto was Arthur's own
  judgment, so the fix targets his reasoning. SHORT RSI floor (<30) unchanged.
- **Morgan floor at 50 (insurance).** `performance_gold.py`: `_apply_phantom_delta`
  (the single point all reported-confidence paths flow through, and from which the band
  label is derived) now floors at `MORGAN_FLOOR = 50`, so Morgan can never enter the LOW
  band after short-term losses. Adds `morgan_floor_active()` + `morgan_floored`/
  `morgan_raw` to the perf dict; dashboard shows "MORGAN FLOOR: 50 ACTIVE (raw N)".
- Port 5043, Gold #FFD700 theme (unchanged). Phantom logging + 5/10/15/30/60/120min
  columns retained. Appears automatically on HybridRoundTable (5050). Repo
  nicksapsford/GoldHybridAI. Backtest/analysis-provisional — GoldHybrid P&L vs
  GoldTrader P&L isolates the value of the two changes.

## [1.2.7] - 2026-07-20
### Added -- Snag 19: recent phantom rows in the Archie Brief
- The Archie Brief now lists the **last 5 phantom rows** (newest first) directly under
  the STAY OUT QUALITY summary, so Archie sees overnight phantom activity inline without
  a separate PHANTOM-page screenshot. Columns: Date/Time (UTC), Direction, Confidence,
  1hr Move, Verdict. PENDING rows shown as PENDING; empty -> "No phantom data yet".
  Display only -- reads the same stay_out_quality decisions; no logic/threshold change.

## [1.2.6] - 2026-07-19
### Changed -- Macro Sentiment Live Reload (required before go-live)
- `get_macro()` now re-reads `macro_sentiment.json` fresh from disk on every Arthur
  consultation instead of caching for 5 min at startup. Changing the macro flag on
  RoundTable (e.g. NEUTRAL -> RISK_OFF) now takes effect on the next consultation --
  within one candle interval, NO restart, open positions unaffected.
- A 5-second debounce coalesces the several get_macro() calls made within a single
  consultation (fetch_sentiment / format_news_context / regime_block) so it doesn't
  hammer disk. Weighting logic unchanged -- overlay still feeds Arthur as context +
  directional sentiment only; Arthur makes every call.

## [1.2.5] - 2026-07-19
### Added -- dedicated PHANTOM page (desk rollout, template CryptoTrader v1.7.3)
- New **PHANTOM &rarr;** header button opens page 4: "PHANTOM TRADES -- Stay Out Quality"
  with a summary (Quality %% / Correct / Wrong / Neutral / Net Saved / Net Missed) and a
  clean **last-20** table (newest first): Date/Time UTC | Direction | Entry Price |
  Confidence | 1hr Move | colour-coded Verdict. Back to Dashboard + Trading nav.
- The right-panel Stay Out Quality card is now a **compact** clickable summary that opens
  the full page. Standardised to the last 20 rows (was 10). Display only -- reads the same
  get_stay_out_quality() data; no threshold/logic/recording change.

## [1.2.4] - 2026-07-18
### Changed -- Guinevere moved to a dedicated page (display only)
- The full Guinevere section (news sentiment + keyword editor) now lives on a dedicated
  page reached via a **GUINEVERE** button in the header (same pattern as P&L), with a
  "Back to Dashboard" link. This fixes the editor overlapping the main grid and the
  ADD BEARISH button falling below the visible area in the narrow right panel.
- The main dashboard right panel now shows a **compact** Guinevere summary (sentiment +
  score + top headline) that opens the full page on click. No trading-logic change.

## [1.2.3] - 2026-07-18
### Added -- Macro Sentiment Overlay reader (Guinevere Part 4)
- **`get_macro()` / `get_macro_adjustment()` / `get_macro_context()`** in `guinevere_news.py`:
  read RoundTable's `logs/macro_sentiment.json` (5-min cache) and apply this system's macro
  nudge to the final Guinevere sentiment score (RISK_ON -1, RISK_OFF +2, CRISIS +3).
- Macro flag + this system's adjustment now appear in Arthur's prompt context.
- CRISIS raises Arthur's confidence bar by 10 (trade more conservatively) desk-wide.

## [1.2.2] - 2026-07-18
### Added -- Guinevere live keyword editor (Guinevere Part 3)
- **Dashboard keyword editor** below the Guinevere news panel: BULLISH / BEARISH
  sections with removable pills, per-section add inputs, and a Save button. Edits
  apply LIVE -- Guinevere re-reads `logs/guinevere_keywords.json` every 5 min, no restart.
- **New `/api/keywords` route** (GET current lists, POST to save) in `dashboard_gold.py`.
- **`save_keywords()` + `_log_keyword_change()`** in `guinevere_news.py`: dedupes/strips,
  writes the keywords file, refreshes the 5-min cache immediately, and logs every
  add/remove to `logs/guinevere_keyword_changes.log`
  (`[ISO8601Z] ADDED/REMOVED "kw" (BULLISH|BEARISH) by Nick`).
- "Keywords last updated" indicator shows the last save timestamp (UTC). Data-only
  files (`logs/`, gitignored); no trading-rule change, no backtest required.

## [1.2.1] - 2026-07-18
### Changed -- phantom verdict threshold (System 5 Review desk-wide, Rec 1 pattern)
- **`VERDICT_THRESHOLD` 10 -> 6** ($/oz, 1hr window). 10 sat above Gold's median hourly move
  (~7pt), classifying only ~27%%. Re-scored 78 rows: CORRECT 16/WRONG 5/NEUTRAL 57 ->
  28/13/37 (52.6%% classified, 20 changed). Data-only (logs/, gitignored).
  No trading-rule change; no backtest required. Verdict threshold mis-scaling was assessed
  desk-wide on 18 Jul; see the OilTrader v1.1.18 fix that established this pattern.

## [1.2.0] - 2026-07-18
### Changed -- GoldHybrid System 3 Review: bidirectional + session/macro aware
Backtest-provisional; 4-week review. Nick sign-off confirmed. Evolutionary -- adds
capability (LONG bounces, session/Morgan gating) without altering what already works
(30pt stop, spread 0.3, ARTHUR_EXIT, Morgan learning -- all confirmed unchanged).

- **Bidirectional (Change 1):** direction now driven by the daily SSL + Morgan regime
  in `main_goldhybrid` -- BULL daily -> LONG; BEAR + Morgan >= 60 -> SHORT; BEAR +
  Morgan < 60 -> cautious bounce LONGs. `check_daily_trend_filter` no longer blocks
  LONGs in a BEAR daily (recovers the missed +94pt of 9 Jul); it only blocks SHORTs in
  a BULL daily. `check_ssl_agreement` now requires **1h AND 5m** SSL to agree with the
  direction (blocks shorting into a 5m bounce -- the Asian failure mode). New
  **Morgan SHORT gate (>= 60)** blocks SHORTs below threshold (60, not FTSE's 65 --
  Gold SHORTs are directionally correct, just need timing).
- **Session filter (Change 2):** session context (London primary / NY elevated / Asian
  high-caution for SHORTs) is passed to Arthur and enforced via the prompt; Lancelot's
  existing Asian RSI tightening (60/40) remains the hard backstop.
- **Risk (Change 3):** `TAKE_PROFIT_POINTS` 150 -> **50** (150 never hit; best move 67pt;
  50pt = 1.67:1 R:R). Stop 30 and spread 0.3 unchanged.
- **Profit ladder (Change 4):** recalibrated for the 30pt/50pt profile to
  **£8->£6, £16->£13, £25->£21** (Step 4 removed).
- **Guinevere logging (Change 5):** `guinevere_score` is now written to phantom rows
  (`build_snapshot(guinevere_score=...)`) from the cached sentiment fetch -- previously
  blank on all Gold phantom rows.
- **Arthur prompt (Change 6):** rewritten for bidirectional trading -- philosophy,
  direction awareness, session awareness, macro awareness, ARTHUR_EXIT validation,
  point convention (30/50), profit ladder, SHORT gating. Live regime/session/Morgan
  values injected per tick; `get_trading_decision` gained `morgan_confidence` +
  `proposed_direction`.

## [1.1.8] - 2026-07-16
### Fixed
- Snag 9: confidence bar could display 50 when the real Morgan score was 0. The
  dashboard read `perf.confidence_score || 50`, and JS treats 0 as falsy, so a
  legitimate 0 was replaced by the 50 fallback. Changed to
  `(perf.confidence_score != null ? perf.confidence_score : 50)` -- 0 now shows as
  0; 50 is used only when the value is genuinely absent. In practice only GasTrader
  showed the wrong value (the only system with a 0 score, from a 5-loss streak); the
  latent bug was in all 6 dashboards. RoundTable was already correct.

## [1.1.7] - 2026-07-16
### Added
- Job 1 (Gaius Commission 001, Priority 1): indicator snapshot at signal time in
  phantom_trades.csv. 17 columns APPENDED to the right of the existing 14-col schema
  (existing positions unchanged): ssl_daily/1hr/5min, rsi_daily/1hr/5min,
  tmo_1hr/5min, macd_1hr/5min, chande_mo_1hr/5min, money_flow_1hr/5min, morgan_score,
  session, guinevere_score. Captured from values Merlin already fetched for Arthur
  (no new data fetch) via phantom_tracker.build_snapshot() -> record_decision(indicators=).
  The snapshot build is wrapped in its own try/except so a failure can never stop a
  phantom row being written. phantom_tracker now migrates an older 14-col file in place
  on first use (old rows keep positions; new columns blank). Chronicle & Gaius read by
  column name and are unaffected. (guinevere_score currently blank pending a safe cached
  source -- column reserved.)

# GoldHybrid AI Changelog

## [1.1.6] - 2026-07-14
### Fixed
- Morgan confidence (perf.confidence_score) now included in the lightweight always-running
  dashboard push (_push_dashboard_live), so /api/state exposes it in ALL market states --
  including the 21:00-22:00 UTC break. Previously perf was only pushed on full candle ticks
  (skipped when the market is closed), so RoundTable / Gaius / Chronicle showed null
  confidence out of hours. Matches CryptoTrader (performance in every push).

## [1.1.5] - 2026-07-14
### Added
- Guinevere news sentiment integration (Currents API), replicating the Oil/Gas
  architecture with Gold-specific keywords (Fed/CPI/PCE/geopolitical/safe-haven/
  DXY etc.). New guinevere_news.py: 5-min cached fetch, keyword scoring, ±8
  direction-aware confidence adjustment (soft, never blocks), logs to
  logs/guinevere_sentiment.csv (same schema as Oil/Gas).
- Soft Fed/CPI/NFP caution windows (context flags for Arthur, NOT hard blocks --
  calendar_gold already hard-blocks at release times; reuses its date logic).
- Arthur prompt (agent_brain_gold.py) now includes Guinevere sentiment, score,
  top headlines, caution window and the ±8 rule.
- GoldHybrid dashboard: GUINEVERE NEWS card + /api/news route (gold theme).
- CURRENTS_API_KEY added to GoldHybrid .env (shared with Oil/Gas; .env not committed).

## [1.1.4] - 2026-07-13
### Fixed
- Bug C (desk-wide): "Locked P&L" now only shows once the trailing stop trails to break-even (genuine secured profit); until then "---" instead of an if-stopped loss figure.

## [1.1.3] - 2026-07-12
### Fixed
- Log timestamps now emitted in UTC (logging.Formatter.converter = time.gmtime; datefmt suffixed " UTC") across main, watchdog and dashboard. Previously local/BST, causing a +1h mismatch vs the UTC CSV artefacts (phantom_trades.csv etc.).
### Added
- ALBION STANDING RULE comment blocks baked into the logging setup and the log/analysis modules (phantom_tracker.py, performance_gold.py, dashboard stay-out reader): all timestamps are UTC, never BST/local.

## [1.1.2] - 2026-07-11
### Added
- Silent launcher (pythonw -- no console windows); output to logs/console.log with daily rotation (7 days kept)
- Launcher now starts the dashboard + watchdog silently (was cmd windows)

## [1.1.1] - 2026-07-11
### Added
- Morgan confidence persistence (performance_gold.py). A CSV audit trail in logs/morgan_confidence.csv (fields timestamp,confidence,level,reason) records every confidence change: save_confidence(confidence, reason='tick') appends a row (level HIGH>=65 / LOW<=35 / else MEDIUM, header written when new, best-effort try/except) and load_confidence() returns the last row's confidence float (or None). set_confidence(value, reason='update') now also appends to the CSV after the existing JSON persist (JSON store retained). On startup main_goldhybrid.py calls load_confidence() after the phantom poller/watchdog hook and, if a value is present, set_confidence(saved, reason='restore') so Morgan's confidence is restored on restart instead of resetting to the 50.0 baseline. get_stay_out_adjustment() and all trading logic unchanged.

## [1.1.0] - 2026-07-11
### Added
- Morgan individual phantom feedback (performance_gold.py). A persistent per-verdict confidence store in logs/morgan_confidence.json (get_confidence/set_confidence, default 50.0, clamped 0-100, guarded by _morgan_lock). apply_phantom_verdict_feedback() scores each judged phantom verdict: NEUTRAL -> 0.0; raw = clamp(abs(pnl_1hr)/50, 0.5, 2.0); CORRECT -> +raw, WRONG -> -raw. A MorganPhantomPoller daemon thread (process_new_phantom_verdicts, 300s) drains phantom_tracker.get_unprocessed_verdicts(), applies feedback to running confidence, then mark_processed([timestamps]); started from main after the phantom resolve/watchdog hook. The (get_confidence() - 50.0) delta is folded once into the reported confidence in _compute_confidence, after get_stay_out_adjustment() (which is unchanged) to avoid double-counting.
### Audit
- Arthur prompt (agent_brain_gold.py) audited for hardcoded win-rate/historical/backtest percentages: CLEAN. No such figures present; the only percentage ("30-point stop is ~50% of the daily range") is a position-sizing ratio, not a performance claim. No reset needed.

## [1.0.9] - 2026-07-11
### Added
- 7 flat status fields merged into /api/state (and thus available to any /api/status-style consumer): lancelot_status, lancelot_fails, lancelot_fail_reasons, arthur_decision, arthur_confidence, arthur_consulted, locked_pnl. Derived read-only from existing decision/pre_checks/panel_mode/current_trade via compute_status_fields(); wrapped in try/except so /api/state never 500s. locked_pnl is the GBP P&L locked in if the stop is hit (points*stake_per_point, no gbpusd multiply). No trading logic / pre-checks / confidence changed.
### Fixed
- Compact Open Position panel — Entry/Stop/Target (and sibling) rows now use a two-column layout (fixed ~120px label column, value immediately after) instead of full-width space-between, so labels and values read together.

## [1.0.8] - 2026-07-10
### Fixed
- Staggered Capital.com API startup delay (15s + jitter) to prevent 429 rate limits on shared demo account (Z6CJSM)

## [1.0.7] - 2026-07-09
### Added
- phantom_tracker.start_watchdog() — continuous daemon thread that runs resolve_stale_pending() every 15 min, so stale PENDING rows resolve dynamically without a restart. Idempotent (single thread per process). Started in main after startup resolution.
### Changed
- backtest_gold.py sizing corrected to live values (stop 30pt / target 150pt, was 45/225). Rerun confirms Fix 3 holds: RELAXED (52/48) 53.4% win rate vs BASELINE (55/45) 52.6%, trades 116 vs 114, drawdown unchanged (£89.98). 1h RSI relaxation retained.

## [1.0.6] - 2026-07-09
### Added
- backtest_gold.py — Gold spot (XAU/USD, GC=F) spread-betting backtest engine. Reimplements the full 6-indicator suite and replays 5m bars through Lancelot's exact hard-filter entry gate. Runs the pipeline twice (BASELINE vs RELAXED 1h RSI veto) on identical data with side-by-side breakdowns by direction, liquidity period (Asian/London/Overlap/NY) and EIA-Wednesday, plus net P&L, max drawdown and avg win/loss. Writes logs/backtest_gold_results.txt and logs/backtest_gold_trades.csv.
### Changed
- 1h RSI veto relaxed 55->52 (LONG) / 45->48 (SHORT) in pre_checks_gold.py, backtest-validated. On 72 days of GC=F 5m data the relaxed gate raised trade count (67->69) and win rate (62.7%->63.8%) with no drawdown increase (GBP 69.34 unchanged). Asian-session tightening (60/40) and the indicator-scoring 55/45 in data_feed_gold are unchanged.

## [1.0.5] - 2026-07-09
### Fixed
- Morgan quality score now excludes NEUTRAL decisions from the denominator (only CORRECT/WRONG judged)
- Morgan penalty minimum raised from 5 to 8 judged decisions before firing
### Notes
- 1-hour RSI veto relaxation (Fix 3) NOT applied: no backtest script exists for GoldHybrid to validate it. Deferred for Nick's decision.

## [1.0.2] - 2026-07-08
### Fixed
- STAY OUT QUALITY panel now ignores PENDING rows in the quality score (matches Morgan's get_summary)
### Changed
- README rewritten with Albion Trading Desk branding and team roster

## [1.0.1] - 2026-07-08
### Added
- phantom_tracker.py — STAY OUT decision recorder
- Morgan STAY OUT quality integration
- Main loop hook for STAY OUT recording

## v1.0.0 -- 7 Jul 2026
### Added
- Initial build (21 files, 5,017 lines)
- Gold spot spread betting via Capital.com
- Epic: GOLD | Stop: 30pts | Stake: £0.67/pt
- Liquidity period awareness (Asian/London/NY/Overlap)
- 23-hour market (daily break 21:00-22:00 UTC)
- Arthurian team, port 5043, gold theme #FFD700
