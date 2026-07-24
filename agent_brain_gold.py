"""
GoldHybrid AI -- agent_brain_gold.py  (Arthur)
Claude AI brain for Gold spot spread betting decisions.
Called only after Lancelot pre-checks have passed.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import anthropic
import pandas as pd
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

_ENV_PATH = BASE_DIR / ".env"
if _ENV_PATH.exists():
    load_dotenv(dotenv_path=_ENV_PATH)
else:
    load_dotenv()

log    = logging.getLogger("GoldHybrid.Arthur")
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

MODEL      = "claude-sonnet-4-6"   # same model as the rest of the Blackpool suite
MAX_TOKENS = 2000

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Arthur, the AI trading brain for GoldHybrid AI.
Your job is to analyse Gold (XAU) market conditions and decide whether to
ENTER_LONG, ENTER_SHORT, HOLD an existing position, EXIT, or STAY_OUT.

PHILOSOPHY -- BIDIRECTIONAL, SESSION- AND MACRO-AWARE
GoldHybrid is a bidirectional system trading Gold (XAU/USD) spot via Capital.com.
Trade WITH the session direction -- LONG for bounces in the downtrend, SHORT when
the trend resumes. Gold is highly macro-sensitive; session, regime and Guinevere
sentiment all matter. Spread-bet profits are TAX FREE in the UK -- capital
preservation matters. NEVER hold overnight -- force close at 20:45 UTC.

DIRECTION AWARENESS (current regime is given in the market data below)
The daily SSL sets the direction symmetrically -- assess LONG and SHORT with EQUAL
weight (23 Jul 2026: no Morgan SHORT gate, no direction preference).
- Daily SSL BULL  -> look for LONG bounce/trend setups.
- Daily SSL BEAR  -> look for SHORT setups (trend resumption).
SHORTs take the SAME confidence bar, pre-checks and sizing as LONGs. The SSL alignment
tells you the direction; you assess QUALITY, not direction preference.

SESSION AWARENESS (CRITICAL -- current session is given below)
- LONDON (07:45-16:30 UTC): PRIMARY session -- trends develop here, good for both
  directions. The desk's best Gold trade (+£44.97) was a London SHORT.
- NY (13:30-21:00 UTC): Good for both directions; follow momentum.
- ASIAN (00:00-07:45 UTC): thinner liquidity, but trade it on the same terms as any
  other session. If the SSL aligns BEAR in the Asian session, take the SHORT; if it
  aligns BULL, take the LONG. No session-based direction preference either way.

MACRO AWARENESS
Gold is highly macro-sensitive:
- DXY weakening      -> bullish for Gold -> supports LONGs.
- DXY strengthening  -> bearish for Gold -> supports SHORTs.
- Rising Treasury yields -> bearish for Gold -> supports SHORTs.
- Geopolitical risk / risk-off -> bullish for Gold -> supports LONGs.
- Guinevere sentiment reflects the current macro tone -- factor it into confidence.
  A BULLISH Guinevere score in a LONG session adds conviction; a BEARISH score in a
  SHORT session adds conviction.

ARTHUR_EXIT VALIDATION
ARTHUR_EXIT is a loss-mitigation tool -- trust it completely. All three prior
ARTHUR_EXITs were correct decisions: Gold rose after every exit. The issue was entry
timing, not exit logic. When a live trade genuinely turns against you, EXIT decisively
-- do not fight it hoping for a reversal.

POINT CONVENTION
1 point = approximately $1/oz. Stop = 30 points ($30/oz). Target = 50 points ($50/oz).
Stake = ~£0.67 per point. Never scale, multiply or divide these by any factor.

PROFIT LADDER (active -- reference its status in HOLD reasoning)
  Step 1: floating profit >= £8  -> floor £6  guaranteed
  Step 2: floating profit >= £16 -> floor £13 guaranteed
  Step 3: floating profit >= £25 -> floor £21 guaranteed
Once a rung locks, the position cannot close below that floor.

DIRECTION SYMMETRY (hard rule)
There is NO SHORT gate. SHORT and LONG are assessed on identical terms -- same
confidence bar, same pre-checks, same sizing. Do not add caution to a SHORT that you
would not add to the mirror-image LONG. Morgan confidence is context for BOTH
directions equally, not a SHORT-specific brake.

CORE IDENTITY / TIMEFRAMES
Three timeframes: daily (trend/direction), 1-hour (confirmation), 5-minute (entry).
Both LONG and SHORT are viable. P&L is made in USD and converted to GBP at the live
GBPUSD rate (given below). Position ~0.90 oz, stake ~£0.67/pt, spread ~0.30pt (negligible).

GOLD MARKET CHARACTER
Gold moves on USD strength, Fed decisions, inflation (CPI), geopolitical risk, and
central-bank buying. Safe haven: rises on fear/risk-off, falls on risk-on. Average
daily range ~$50-75 (40-60 points); a 30-point stop is sensible room.

CALENDAR (CRITICAL)
US NFP, Fed decisions and US CPI are HARD BLOCKS -- never trade within 30 minutes.
The first 15 minutes of the NY open (13:30-13:45 UTC) is also a hard block. Guinevere
flags active blocks -- respect them.

INDICATOR HIERARCHY
TIER 1 -- PRIMARY: daily SSL (direction), 1h SSL (must agree), 1h RSI (>55 bull /
  <45 bear; same thresholds every session). TIER 2: MACD histogram, TMO. TIER 3: Chande MO, Money Flow.
5-MINUTE ENTRY: last candle GREEN for LONG / RED for SHORT; 5m TMO > +0.3 LONG / < -0.3
SHORT. Lancelot now also requires the 5m SSL to agree with the direction.

RSI CEILING/FLOOR -- SYMMETRIC (GoldHybrid -- Gaius Commission 006, made symmetric 23 Jul 2026)
RSI should confirm momentum, and the trend-confirmed relaxation now applies EQUALLY
to both directions:
- LONGs: preferred range 50-70. When daily AND 1h SSL are BOTH BULL (strong trend
  confirmation), RSI up to 80 is ACCEPTABLE -- a rising RSI in an SSL-confirmed uptrend
  is momentum, not a reversal, and Gold's safe-haven rallies routinely run RSI into the
  70s. Above 80, treat as overbought regardless of trend. Below 70 always preferred.
- SHORTs (mirror image): preferred range 30-50. When daily AND 1h SSL are BOTH BEAR,
  RSI down to 20 is ACCEPTABLE -- a falling RSI in an SSL-confirmed downtrend is
  momentum, not a reversal. Below 20, treat as oversold regardless of trend. Above 30
  always preferred.
Do NOT reflexively STAY_OUT of a trend-confirmed entry merely because RSI is in the
70-80 (LONG) or 20-30 (SHORT) extension band -- that is exactly the missed-move failure
this correction fixes. Everything here is symmetric: no direction is favoured.

SELF PERFORMANCE AWARENESS (Morgan) -- CONTEXT ONLY
Morgan confidence is context; it does NOT change your entry threshold. Assess setups
the SAME way at any Morgan score of 30 or above -- do NOT raise the bar or demand
"exceptional" setups when Morgan is low. Below 30 the SYSTEM (not you) hard-blocks new
entries automatically and Gaius intervenes, so you will not be asked to enter there.

HARD RULES -- NEVER VIOLATE
1.  Check the daily SSL + regime first -- it sets the direction today (BULL->LONG, BEAR->SHORT).
2.  1h AND 5m SSL must agree with the intended direction before any entry.
3.  Assess LONG and SHORT on identical terms -- no SHORT gate, no direction preference.
4.  Trade every session on the same terms -- no Asian-session SHORT caution.
5.  Never enter within 30 min of NFP/Fed/CPI, nor the first 15 min of NY open.
6.  Never hold overnight -- force close by 20:45 UTC; no new entries after 20:30 UTC.
7.  30-point stop gives room -- do NOT exit on noise; but EXIT decisively when a trade
    genuinely turns (ARTHUR_EXIT is trusted -- see above).
8.  When in doubt -- STAY OUT. A STAY_OUT is often the BEST decision.
9.  Morgan is context only -- do NOT raise your entry bar at low Morgan (>=30). The
    system hard-blocks new entries below 30 on its own.

REQUIRED OUTPUT -- valid JSON only. No markdown, no preamble.
{
  "decision": "ENTER_LONG | ENTER_SHORT | HOLD | EXIT | STAY_OUT",
  "confidence": 0-100,
  "liquidity_bias": "ASIAN_CAUTION | LONDON_ACTIVE | NY_TRENDING | OVERLAP_OPTIMAL | CLOSING_AVOID",
  "reasoning": "2-4 sentences explaining your decision",
  "warnings": ["list of concerns"],
  "checklist": {
    "trend_aligned": true,
    "momentum_confirmed": true,
    "liquidity_good": true,
    "calendar_clear": true,
    "not_near_close": true,
    "high_conviction": true
  },
  "calendar_assessment": "brief comment on upcoming gold events",
  "liquidity_assessment": "brief comment on the current session"
}"""


# ── Format indicators for Arthur ──────────────────────────────────────────────

_SESSION_QUALITY = {
    "LONDON":   "PRIMARY session -- trends develop here; good for both directions.",
    "OVERLAP":  "London/NY overlap -- most active; good for both directions.",
    "NEW_YORK": "high volume; good for both directions.",
    "ASIAN":    "thinner liquidity; trade on the same terms as any session (both directions).",
    "CLOSING":  "pre-close -- no new entries.",
    "CLOSED":   "market closed.",
}


def _regime_block(bar_1d, bar_1h, proposed_direction, morgan_confidence, liquidity_period) -> str:
    """Live regime / session block for Arthur (bidirectional, no SHORT gate 23 Jul).
    GoldHybrid (Gaius Commission 006, made symmetric 23 Jul 2026): computes the live
    trend-confirmed RSI extension band for BOTH directions -- LONG ceiling 70 normally,
    80 when daily AND 1h SSL both BULL; SHORT floor 30 normally, 20 when daily AND 1h
    SSL both BEAR. A rising/falling RSI in an SSL-confirmed trend is momentum, not a
    reversal."""
    ssl_1d = "BULL" if (bar_1d is not None and bar_1d.get("ssl_bull")) else \
             ("BEAR" if bar_1d is not None else "N/A")
    ssl_1h = "BULL" if (bar_1h is not None and bar_1h.get("ssl_bull")) else \
             ("BEAR" if bar_1h is not None else "N/A")
    mc = 50.0 if morgan_confidence is None else float(morgan_confidence)
    direction = proposed_direction or "BOTH"
    bull_confirmed = (ssl_1d == "BULL" and ssl_1h == "BULL")
    bear_confirmed = (ssl_1d == "BEAR" and ssl_1h == "BEAR")
    long_ceiling = 80 if bull_confirmed else 70
    short_floor  = 20 if bear_confirmed else 30
    long_note = ("daily+1h SSL both BULL -> momentum uptrend" if bull_confirmed
                 else "no dual-SSL trend confirmation -> standard ceiling")
    short_note = ("daily+1h SSL both BEAR -> momentum downtrend" if bear_confirmed
                  else "no dual-SSL trend confirmation -> standard floor")
    return (
        "REGIME (current)\n"
        f"  Daily SSL:         {ssl_1d}\n"
        f"  1h SSL:            {ssl_1h}\n"
        f"  Regime direction:  {direction}   (what to look for this session)\n"
        f"  Morgan confidence: {mc:.1f}/100   (context for BOTH directions equally)\n"
        f"  Direction rule:    symmetric -- LONG and SHORT on identical terms, no SHORT gate\n"
        f"  LONG RSI ceiling:  {long_ceiling}   ({long_note}; above {long_ceiling} treat as overbought)\n"
        f"  SHORT RSI floor:   {short_floor}   ({short_note}; below {short_floor} treat as oversold)\n"
        f"  Session quality:   {liquidity_period} -- {_SESSION_QUALITY.get(liquidity_period, '')}"
    )


def _format_indicators(bar_1d, bar_1h, bar_5m, current_price, liquidity_period,
                       gbpusd_rate, current_trade=None,
                       calendar_context=None, perf_context=None,
                       news_context=None, morgan_confidence=None,
                       proposed_direction=None) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    regime_block = _regime_block(bar_1d, bar_1h, proposed_direction, morgan_confidence, liquidity_period)

    def _f(v, dp=2):
        if v is None or pd.isna(v):
            return "N/A"
        return f"{float(v):.{dp}f}"

    candle_colour = "GREEN" if bar_5m.get("close", 0) >= bar_5m.get("open", 0) else "RED"
    ssl_1d = "BULL" if (bar_1d is not None and bar_1d.get("ssl_bull")) else ("BEAR" if bar_1d is not None else "N/A")
    ssl_1h = "BULL" if bar_1h.get("ssl_bull") else "BEAR"
    ssl_5m = "BULL" if bar_5m.get("ssl_bull") else "BEAR"

    position_text = "None -- no open position"
    if current_trade is not None:
        pts = (current_price - current_trade.entry_price) if current_trade.direction == "LONG" \
              else (current_trade.entry_price - current_price)
        position_text = (
            f"OPEN {current_trade.direction} | entry=${current_trade.entry_price:,.2f} | "
            f"current=${current_price:,.2f} | pts_from_entry={pts:+.1f} | "
            f"stop=${current_trade.stop_loss:,.2f} | target=${current_trade.take_profit:,.2f} | "
            f"size={current_trade.size_oz:.2f}oz | stake=£{current_trade.stake:.4f}/pt | "
            f"{current_trade.liquidity_period}"
        )

    if current_trade is not None and getattr(current_trade, "ladder_step", 0):
        position_text += (
            " | PROFIT LADDER ACTIVE: floor locked at £%.2f (step %d). Position cannot "
            "close below this floor unless a gap event occurs -- factor this into your "
            "HOLD reasoning." % (getattr(current_trade, "ladder_floor_gbp", 0.0),
                                 int(getattr(current_trade, "ladder_step", 0))))

    return f"""Please analyse the current Gold (XAU) market conditions.

TIME AND PRICE
  Time (UTC):        {now}
  Liquidity Period:  {liquidity_period}
  Gold (XAU/USD):    ${current_price:,.2f} per oz
  GBPUSD rate:       {gbpusd_rate:.4f}  (for USD->GBP P&L conversion)

{regime_block}

DAILY CHART (Trend Direction -- sets allowed direction for today)
  SSL Cloud:        {ssl_1d}
  RSI (14):         {_f(bar_1d.get('rsi') if bar_1d is not None else None, 1)}
  TMO Main:         {_f(bar_1d.get('tmo_main') if bar_1d is not None else None, 3)}
  Chande MO (20):   {_f(bar_1d.get('chande_mo') if bar_1d is not None else None, 1)}

1-HOUR CHART (Trend Confirmation)
  SSL Cloud:        {ssl_1h}
  RSI (14):         {_f(bar_1h.get('rsi'), 1)}
  MACD Histogram:   {_f(bar_1h.get('macd_histogram'), 3)}
  TMO Main:         {_f(bar_1h.get('tmo_main'), 3)}
  TMO Smooth:       {_f(bar_1h.get('tmo_smooth'), 3)}
  Chande MO (20):   {_f(bar_1h.get('chande_mo'), 1)}
  Money Flow (14):  {_f(bar_1h.get('money_flow'), 2)}

5-MINUTE CHART (Entry Timing)
  SSL Cloud:        {ssl_5m}
  RSI (14):         {_f(bar_5m.get('rsi'), 1)}
  MACD Histogram:   {_f(bar_5m.get('macd_histogram'), 3)}
  TMO Main:         {_f(bar_5m.get('tmo_main'), 3)}
  TMO Smooth:       {_f(bar_5m.get('tmo_smooth'), 3)}
  Chande MO (20):   {_f(bar_5m.get('chande_mo'), 1)}
  Money Flow (14):  {_f(bar_5m.get('money_flow'), 2)}
  Last Candle:      {candle_colour} (close={_f(bar_5m.get('close'), 2)} open={_f(bar_5m.get('open'), 2)})

CURRENT POSITION
  {position_text}

{calendar_context if calendar_context else 'GOLD ECONOMIC CALENDAR\n  No calendar data available.'}

{perf_context if perf_context else 'SELF PERFORMANCE AWARENESS\n  No performance data yet -- first trading session.'}

{news_context if news_context else 'GUINEVERE NEWS SENTIMENT (Gold)\n  No news data available.'}

Reference the Guinevere news sentiment in your reasoning when it is a
significant factor for the decision.

Please provide your analysis and trading decision in the required JSON format."""


# ── Main decision function ────────────────────────────────────────────────────

def get_trading_decision(bar_1h, bar_5m, current_price, liquidity_period,
                         bar_1d=None, current_trade=None,
                         calendar_context=None, perf_context=None,
                         gbpusd_rate: float = 1.27, news_context=None,
                         morgan_confidence=None, proposed_direction=None) -> dict:
    """
    Send indicator data to Arthur (Claude) and receive a trading decision.
    Only call this AFTER Lancelot pre-checks have passed.
    """
    log.info("Sending indicators to Arthur...")

    user_message = _format_indicators(
        bar_1d, bar_1h, bar_5m, current_price, liquidity_period,
        gbpusd_rate, current_trade, calendar_context, perf_context, news_context,
        morgan_confidence, proposed_direction,
    )

    for attempt in range(2):
        try:
            response = client.messages.create(
                model      = MODEL,
                max_tokens = MAX_TOKENS,
                system     = SYSTEM_PROMPT,
                messages   = [{"role": "user", "content": user_message}],
            )
            if response.stop_reason == "max_tokens":
                log.warning("Arthur hit max_tokens -- JSON may be truncated")

            raw_text = response.content[0].text.strip()
            if raw_text.startswith("```"):
                raw_text = "\n".join(l for l in raw_text.split("\n")
                                     if not l.strip().startswith("```")).strip()
            try:
                decision = json.loads(raw_text)
            except json.JSONDecodeError as exc:
                log.error("Arthur returned invalid JSON (attempt %d/2): %s", attempt + 1, exc)
                if attempt == 0:
                    continue
                return _safe_stay_out("Arthur returned invalid JSON -- staying out for safety")

            decision["timestamp"]        = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            decision["tokens_used"]      = response.usage.input_tokens + response.usage.output_tokens
            decision["current_price"]    = current_price
            decision["liquidity_period"] = liquidity_period
            decision["gbpusd_rate"]      = gbpusd_rate

            log.info("Arthur decision: %s | confidence=%s | tokens=%d",
                     decision.get("decision"), decision.get("confidence"),
                     decision.get("tokens_used", 0))
            return decision

        except anthropic.APIError as exc:
            log.error("Anthropic API error: %s", exc)
            return _safe_stay_out(f"API error: {str(exc)}")
        except Exception as exc:
            log.error("Unexpected error calling Arthur: %s", exc)
            return _safe_stay_out(f"Unexpected error: {str(exc)}")

    return _safe_stay_out("Arthur failed after all attempts")


def _safe_stay_out(reason: str) -> dict:
    return {
        "decision":             "STAY_OUT",
        "confidence":           0,
        "liquidity_bias":       "ASIAN_CAUTION",
        "reasoning":            reason,
        "warnings":             [reason],
        "checklist":            {},
        "calendar_assessment":  "",
        "liquidity_assessment": "",
        "timestamp":            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "tokens_used":          0,
    }


def format_decision_for_display(decision: dict) -> str:
    """Format Arthur's decision for terminal display."""
    d         = decision.get("decision", "UNKNOWN")
    conf      = decision.get("confidence", "--")
    bias      = decision.get("liquidity_bias", "--")
    reasoning = decision.get("reasoning", "No reasoning")
    warnings  = decision.get("warnings", [])
    tokens    = decision.get("tokens_used", 0)
    ts        = decision.get("timestamp", "")
    price     = decision.get("current_price", 0) or 0
    lines = [
        "=" * 60,
        "  GoldHybrid AI -- Arthur's Decision",
        f"  {ts}",
        "=" * 60,
        f"  Decision:        {d}",
        f"  Confidence:      {conf}/100",
        f"  Liquidity Bias:  {bias}",
        f"  Gold Price:      ${price:,.2f}",
        f"  Liquidity:       {decision.get('liquidity_period', '--')}",
        "",
        "  Reasoning:",
        f"  {reasoning}",
        "",
    ]
    if warnings:
        lines.append("  Warnings:")
        for w in warnings:
            lines.append(f"    - {w}")
        lines.append("")
    if decision.get("calendar_assessment"):
        lines.append(f"  Calendar:  {decision.get('calendar_assessment')}")
    if decision.get("liquidity_assessment"):
        lines.append(f"  Liquidity: {decision.get('liquidity_assessment')}")
    cl = decision.get("checklist", {})
    if cl:
        lines.append("  Checklist:")
        for k, v in cl.items():
            lines.append(f"    [{'PASS' if v else 'FAIL'}] {k.replace('_', ' ').title()}")
    lines.append(f"  Tokens used: {tokens}")
    lines.append("=" * 60)
    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    log.info("Arthur self-test -- calling Claude with a bullish Gold setup...")
    bar_1d = pd.Series({"ssl_bull": True, "rsi": 58.0, "tmo_main": 1.5, "chande_mo": 25.0})
    bar_1h = pd.Series({"ssl_bull": True, "rsi": 62.0, "macd_histogram": 8.5,
                        "tmo_main": 2.1, "tmo_smooth": 1.5, "chande_mo": 45.0, "money_flow": 150.0})
    bar_5m = pd.Series({"ssl_bull": True, "rsi": 58.0, "macd_histogram": 2.5,
                        "tmo_main": 0.8, "tmo_smooth": 0.5, "chande_mo": 30.0, "money_flow": 80.0,
                        "open": 4150.0, "close": 4160.0})
    decision = get_trading_decision(
        bar_1h=bar_1h, bar_5m=bar_5m, current_price=4160.0,
        liquidity_period="OVERLAP", bar_1d=bar_1d, gbpusd_rate=1.3376,
    )
    print(format_decision_for_display(decision))
    log.info("Arthur self-test complete.")
