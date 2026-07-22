"""
GoldHybrid AI -- backtest_gold.py

Gold spot (XAU/USD) spread betting backtest engine using the live TrendSurfer
indicator suite and the exact Lancelot (pre_checks_gold) hard-filter entry gate.

Strategy  : SSL Cloud + RSI + MACD + TMO + Chande MO + Money Flow
Timeframes: Daily (trend filter) + 1h (confirmation) + 5m (entry timing)

Gold mechanics:
  Spread betting P&L = points_moved x stake_per_point
  Stake per point    = fixed GBP 0.67 / point  (matches live sizing)
  Spread cost        = 0.3 point x stake_per_point per trade (constant)
  Gold is a ~23h Mon-Fri market with a daily break 21:00-22:00 UTC.
  No new entries after 20:30 UTC; force close on the daily/weekend break.

Liquidity periods (UTC, LIVE boundaries copied verbatim from data_feed_gold):
  ASIAN    21:00-08:00  (thin -- tighter RSI 60/40)
  LONDON   08:00-13:00
  OVERLAP  13:00-17:00
  NEW_YORK 17:00-20:30
  CLOSING  20:30-21:00  (no entries)
  CLOSED   21:00-22:00 daily break + weekend

Entry gate replicates pre_checks_gold order for a new entry:
  market-open / near-close, liquidity/Asian flag, daily SSL trend filter,
  1h SSL agreement, 1h RSI confirmation (the TESTED veto), 5m TMO momentum,
  not-choppy, 5m candle confirms. EIA-Wednesday (15:00-16:00 UTC) is FLAGGED
  and reported separately -- live pre_checks_gold does not block it, so neither
  do we.

This job runs the FULL pipeline TWICE on the same fetched data:
  BASELINE : LONG 1h RSI >= 55, SHORT <= 45
  RELAXED  : LONG 1h RSI >= 52, SHORT <= 48
(Asian tightening stays 60/40 in both configs.)

Output:
  logs/backtest_gold_results.txt  -- full baseline-vs-relaxed report + verdict
  logs/backtest_gold_trades.csv   -- every trade in both configs
"""

import csv
import logging
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore", category=FutureWarning, module="yfinance")

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("GoldHybrid.Backtest")

# ── Constants (match live) ──────────────────────────────────────────────────────

STARTING_CAPITAL_GBP = 1000.0
STAKE_PER_POINT      = 0.67     # GBP per point -- fixed live stake (~0.90 oz)
STOP_POINTS          = 30.0     # trailing stop distance in gold points ($/oz) -- matches live
TAKE_PROFIT_POINTS   = 150.0    # take-profit ceiling in gold points -- matches live
SPREAD_POINTS        = 0.3      # constant per-trade spread cost (points)

LOGS_DIR = Path(__file__).parent / "logs"

GOLD_TICKER_PRIMARY  = "GC=F"      # COMEX gold futures
GOLD_TICKER_FALLBACK = "XAUUSD=X"  # spot XAU/USD

# ── Liquidity period constants (UTC) -- copied verbatim from data_feed_gold ─────

ASIAN    = "ASIAN"        # 21:00-08:00 UTC -- lower liquidity, choppier
LONDON   = "LONDON"       # 08:00-13:00 UTC -- good liquidity, trends start
OVERLAP  = "OVERLAP"      # 13:00-17:00 UTC -- London+NY overlap, most active
NEW_YORK = "NEW_YORK"     # 17:00-20:30 UTC -- high volume
CLOSING  = "CLOSING"      # 20:30-21:00 UTC -- pre-close, no entries
CLOSED   = "CLOSED"       # 21:00-22:00 daily break + weekend

LIQUIDITY_PERIODS = [ASIAN, LONDON, OVERLAP, NEW_YORK]

DAILY_BREAK_START_MIN = 21 * 60   # 21:00 UTC
DAILY_BREAK_END_MIN   = 22 * 60   # 22:00 UTC
NO_ENTRY_AFTER_MIN    = 20 * 60 + 30   # 20:30 UTC -- no new entries within 30m of close

# ── Entry-gate thresholds (match pre_checks_gold) ──────────────────────────────

MIN_TMO_FOR_ENTRY       = 0.3
CHOPPY_RSI_THRESHOLD    = 5.0
CHOPPY_TMO_THRESHOLD    = 0.5
CHOPPY_SIGNALS_REQUIRED = 2

# EIA petroleum inventory window (caution flag only -- Wednesdays 15:00-16:00 UTC)
EIA_WEEKDAY   = 2          # Wednesday
EIA_START_MIN = 15 * 60    # 15:00 UTC
EIA_END_MIN   = 16 * 60    # 16:00 UTC


# ── Entry-gate configuration (the parameter under test) ────────────────────────

@dataclass
class GateConfig:
    """1h RSI veto thresholds. Asian tightening stays 60/40 in every config."""
    name:            str
    rsi_long_normal: float
    rsi_short_normal: float
    rsi_long_asian:  float = 60.0
    rsi_short_asian: float = 40.0


BASELINE = GateConfig("BASELINE", rsi_long_normal=55.0, rsi_short_normal=45.0)
RELAXED  = GateConfig("RELAXED",  rsi_long_normal=52.0, rsi_short_normal=48.0)


# ── Market hours / liquidity logic (verbatim from data_feed_gold) ──────────────

def is_market_open(ts_utc: datetime) -> bool:
    wd = ts_utc.weekday()          # Mon=0 .. Sun=6
    hm = ts_utc.hour * 60 + ts_utc.minute
    if wd == 5:                    # Saturday -- closed all day
        return False
    if wd == 6:                    # Sunday -- opens 22:00 UTC
        return hm >= DAILY_BREAK_END_MIN
    if wd == 4:                    # Friday -- closes 21:00 UTC for the week
        return hm < DAILY_BREAK_START_MIN
    if DAILY_BREAK_START_MIN <= hm < DAILY_BREAK_END_MIN:
        return False
    return True


def get_liquidity_period(ts_utc: datetime) -> str:
    if not is_market_open(ts_utc):
        return CLOSED
    hm = ts_utc.hour * 60 + ts_utc.minute
    if hm >= 21 * 60 or hm < 8 * 60:      # 21:00-08:00 (break already filtered out)
        return ASIAN
    if hm < 13 * 60:                       # 08:00-13:00
        return LONDON
    if hm < 17 * 60:                       # 13:00-17:00
        return OVERLAP
    if hm < 20 * 60 + 30:                  # 17:00-20:30
        return NEW_YORK
    return CLOSING                         # 20:30-21:00


def is_eia_window(ts_utc: datetime) -> bool:
    """EIA petroleum inventory caution window -- Wednesdays 15:00-16:00 UTC."""
    if ts_utc.weekday() != EIA_WEEKDAY:
        return False
    hm = ts_utc.hour * 60 + ts_utc.minute
    return EIA_START_MIN <= hm < EIA_END_MIN


# ── Indicator functions (identical suite to data_feed_gold) ────────────────────

def _calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0).ewm(com=period - 1, min_periods=period).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=period - 1, min_periods=period).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _calc_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ema_fast    = series.ewm(span=fast, adjust=False).mean()
    ema_slow    = series.ewm(span=slow, adjust=False).mean()
    macd_line   = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({
        "macd":      macd_line,
        "signal":    signal_line,
        "histogram": macd_line - signal_line,
    })


def _calc_ssl_cloud(df: pd.DataFrame, period: int = 10) -> pd.DataFrame:
    sma_high = df["high"].rolling(period).mean()
    sma_low  = df["low"].rolling(period).mean()
    hlv      = pd.Series(
        np.where(df["close"] > sma_high, 1,
        np.where(df["close"] < sma_low, -1, np.nan)),
        index=df.index,
    ).ffill()
    ssl_up   = np.where(hlv < 0, sma_low,  sma_high)
    ssl_down = np.where(hlv < 0, sma_high, sma_low)
    return pd.DataFrame({
        "ssl_up":   ssl_up,
        "ssl_down": ssl_down,
        "ssl_bull": ssl_up > ssl_down,
    }, index=df.index)


def _calc_tmo(df: pd.DataFrame, length: int = 14, calc_length: int = 5) -> pd.DataFrame:
    mom    = np.sign(df["close"] - df["open"]).rolling(length).sum()
    main   = mom.ewm(span=calc_length, adjust=False).mean()
    smooth = main.ewm(span=calc_length, adjust=False).mean()
    return pd.DataFrame({"tmo_main": main, "tmo_smooth": smooth}, index=df.index)


def _calc_chande(df: pd.DataFrame, period: int = 20) -> pd.Series:
    diff   = df["close"].diff()
    up_sum = diff.clip(lower=0).rolling(period).sum()
    dn_sum = (-diff.clip(upper=0)).rolling(period).sum()
    denom  = (up_sum + dn_sum).replace(0, np.nan)
    return (100 * (up_sum - dn_sum) / denom).rename("chande_mo")


def _calc_money_flow(df: pd.DataFrame, period: int = 14) -> pd.Series:
    tp  = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"].replace(0, np.nan)
    mfv = tp * vol * np.sign(df["close"] - df["open"])
    return (mfv.rolling(period).sum() / vol.rolling(period).sum().replace(0, np.nan)
            ).rename("money_flow")


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Apply all 6 indicators to an OHLCV DataFrame. Returns enriched copy."""
    if df.empty:
        return df
    df = df.copy()
    df["rsi"]            = _calc_rsi(df["close"])
    macd_df              = _calc_macd(df["close"])
    df["macd"]           = macd_df["macd"]
    df["macd_signal"]    = macd_df["signal"]
    df["macd_histogram"] = macd_df["histogram"]
    ssl_df               = _calc_ssl_cloud(df)
    df["ssl_up"]         = ssl_df["ssl_up"]
    df["ssl_down"]       = ssl_df["ssl_down"]
    df["ssl_bull"]       = ssl_df["ssl_bull"]
    tmo_df               = _calc_tmo(df)
    df["tmo_main"]       = tmo_df["tmo_main"]
    df["tmo_smooth"]     = tmo_df["tmo_smooth"]
    df["chande_mo"]      = _calc_chande(df)
    df["money_flow"]     = _calc_money_flow(df)
    return df


# ── Entry-gate checks (faithful to pre_checks_gold, RSI parameterised) ─────────

def _derive_direction(bar_1h: pd.Series) -> str:
    """Live _derive_direction with proposed_direction='BOTH': 1h SSL sets bias."""
    return "LONG" if bar_1h.get("ssl_bull") else "SHORT"


def _daily_trend_ok(bar_1d: Optional[pd.Series], direction: str) -> bool:
    """Daily SSL bias. BULL: LONG only. BEAR: SHORT only. NEUTRAL/NaN: both."""
    if bar_1d is None:
        return True
    ssl_1d = bar_1d.get("ssl_bull")
    if pd.isna(ssl_1d):
        return True
    if ssl_1d and direction == "SHORT":
        return False
    if not ssl_1d and direction == "LONG":
        return False
    return True


def _ssl_agreement_ok(bar_1h: pd.Series, direction: str) -> bool:
    """1h SSL must agree with the proposed direction."""
    ssl_1h = bar_1h.get("ssl_bull")
    if pd.isna(ssl_1h):
        return False
    if direction == "LONG" and not ssl_1h:
        return False
    if direction == "SHORT" and ssl_1h:
        return False
    return True


def _1h_rsi_ok(bar_1h: pd.Series, direction: str, is_asian: bool, cfg: GateConfig) -> bool:
    """1h RSI veto (the tested filter). Parameterised via GateConfig."""
    rsi_1h = bar_1h.get("rsi")
    if pd.isna(rsi_1h):
        return True   # matches live: missing RSI passes
    long_min  = cfg.rsi_long_asian  if is_asian else cfg.rsi_long_normal
    short_max = cfg.rsi_short_asian if is_asian else cfg.rsi_short_normal
    if direction == "LONG" and rsi_1h < long_min:
        return False
    if direction == "SHORT" and rsi_1h > short_max:
        return False
    return True


def _tmo_momentum_ok(bar_1h: pd.Series, bar_5m: pd.Series) -> bool:
    """5m TMO must show momentum: > +0.3 for a bull setup, < -0.3 for a bear setup."""
    ssl_bull = bar_1h.get("ssl_bull")
    tmo_5m   = bar_5m.get("tmo_main")
    if pd.isna(ssl_bull) or pd.isna(tmo_5m):
        return True
    if ssl_bull and tmo_5m < MIN_TMO_FOR_ENTRY:
        return False
    if not ssl_bull and tmo_5m > -MIN_TMO_FOR_ENTRY:
        return False
    return True


def _not_choppy_ok(bar_1h: pd.Series, bar_5m: pd.Series) -> bool:
    """Block if RSI and TMO are both near-neutral (>=2 choppy signals)."""
    choppy = 0
    rsi_5m = bar_5m.get("rsi")
    if pd.notna(rsi_5m) and abs(rsi_5m - 50) <= CHOPPY_RSI_THRESHOLD:
        choppy += 1
    tmo_5m = bar_5m.get("tmo_main")
    if pd.notna(tmo_5m) and abs(tmo_5m) <= CHOPPY_TMO_THRESHOLD:
        choppy += 1
    rsi_1h = bar_1h.get("rsi")
    if pd.notna(rsi_1h) and abs(rsi_1h - 50) <= CHOPPY_RSI_THRESHOLD:
        choppy += 1
    return choppy < CHOPPY_SIGNALS_REQUIRED


def _candle_confirmed_ok(bar_1h: pd.Series, bar_5m: pd.Series) -> bool:
    """Last 5m candle must be green for a bull setup, red for a bear setup."""
    ssl_bull    = bar_1h.get("ssl_bull")
    open_price  = bar_5m.get("open")
    close_price = bar_5m.get("close")
    if pd.isna(ssl_bull) or pd.isna(open_price) or pd.isna(close_price):
        return True
    candle_green = close_price >= open_price
    if ssl_bull and not candle_green:
        return False
    if not ssl_bull and candle_green:
        return False
    return True


# ── Timeframe alignment helper ─────────────────────────────────────────────────

def _last_bar_at(df: pd.DataFrame, ts) -> Optional[pd.Series]:
    mask = df.index <= ts
    if not mask.any():
        return None
    return df[mask].iloc[-1]


# ── Trade record ───────────────────────────────────────────────────────────────

@dataclass
class GoldTrade:
    """One gold spread bet. P&L = pnl_pts x fixed stake."""

    direction:        str
    entry_price:      float
    entry_time:       object = field(default=None)
    liquidity_period: str    = field(default="")
    is_asian:         bool   = field(default=False)
    is_eia:           bool   = field(default=False)

    def __post_init__(self):
        self.stake      = STAKE_PER_POINT
        self.trail_best = self.entry_price
        if self.direction == "LONG":
            self.stop_loss   = self.entry_price - STOP_POINTS
            self.take_profit = self.entry_price + TAKE_PROFIT_POINTS
        else:
            self.stop_loss   = self.entry_price + STOP_POINTS
            self.take_profit = self.entry_price - TAKE_PROFIT_POINTS
        self.exit_price  = None
        self.exit_time   = None
        self.exit_reason = None
        self.pnl_pts     = None
        self.pnl_gbp     = None

    def update_trailing_stop(self, price: float) -> None:
        if self.direction == "LONG" and price > self.trail_best:
            self.trail_best = price
            new_sl = price - STOP_POINTS
            if new_sl > self.stop_loss:
                self.stop_loss = new_sl
        elif self.direction == "SHORT" and price < self.trail_best:
            self.trail_best = price
            new_sl = price + STOP_POINTS
            if new_sl < self.stop_loss:
                self.stop_loss = new_sl

    def close(self, price: float, reason: str) -> None:
        self.exit_price  = price
        self.exit_reason = reason
        self.pnl_pts     = (price - self.entry_price) if self.direction == "LONG" \
                           else (self.entry_price - price)
        self.pnl_gbp     = self.pnl_pts * self.stake


# ── Yahoo Finance data fetching ────────────────────────────────────────────────

def _yf_download(ticker: str, interval: str, period: str) -> pd.DataFrame:
    df = yf.download(ticker, period=period, interval=interval,
                     progress=False, auto_adjust=True)
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [c.lower() for c in df.columns]
    df = df.rename(columns={"adj close": "close"})
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    if "volume" not in df.columns:
        df["volume"] = 0.0
    df["volume"] = df["volume"].fillna(0.0)
    df.sort_index(inplace=True)
    return df.dropna(subset=["close"])


def fetch_historical_data() -> tuple:
    """
    Fetch 1d/2y, 1h/90d, 5m/60d for gold. GC=F primary; if 5m yields too few
    bars, fall back to XAUUSD=X for all three timeframes.
    Returns (df_1d, df_1h, df_5m, ticker_used).
    """
    log.info("Fetching gold historical data from Yahoo Finance...")

    for ticker in (GOLD_TICKER_PRIMARY, GOLD_TICKER_FALLBACK):
        log.info("  Trying ticker %s ...", ticker)
        df_5m = _yf_download(ticker, "5m", "60d")
        log.info("    5m/60d : %d bars", len(df_5m))
        if len(df_5m) < 500:
            log.warning("    Too few 5m bars for %s -- trying next ticker.", ticker)
            continue
        df_1h = _yf_download(ticker, "1h", "90d")
        df_1d = _yf_download(ticker, "1d", "2y")
        log.info("    1h/90d : %d bars", len(df_1h))
        log.info("    1d/2y  : %d bars", len(df_1d))
        if df_1h.empty or df_1d.empty:
            log.warning("    Missing 1h/1d for %s -- trying next ticker.", ticker)
            continue
        log.info("  Using %s [5m %s -> %s]", ticker,
                 df_5m.index[0].strftime("%Y-%m-%d %H:%M"),
                 df_5m.index[-1].strftime("%Y-%m-%d %H:%M"))
        return (add_indicators(df_1d), add_indicators(df_1h),
                add_indicators(df_5m), ticker)

    raise RuntimeError(
        "Could not obtain usable gold intraday data from Yahoo Finance "
        f"({GOLD_TICKER_PRIMARY} and {GOLD_TICKER_FALLBACK} both too sparse)."
    )


# ── Single backtest run (one gate config) ──────────────────────────────────────

def run_single_backtest(cfg: GateConfig, df_1d: pd.DataFrame, df_1h: pd.DataFrame,
                        df_5m: pd.DataFrame) -> tuple:
    """Replay df_5m bar by bar under one gate config. Returns (stats, trades)."""
    log.info("")
    log.info("=" * 64)
    log.info("  %s  |  1h RSI veto  LONG>=%.0f  SHORT<=%.0f  (Asian %.0f/%.0f)",
             cfg.name, cfg.rsi_long_normal, cfg.rsi_short_normal,
             cfg.rsi_long_asian, cfg.rsi_short_asian)
    log.info("=" * 64)

    capital       = STARTING_CAPITAL_GBP
    current_trade: Optional[GoldTrade] = None
    completed     = []

    for ts, bar in df_5m.iterrows():
        ts_py = ts.to_pydatetime()
        period = get_liquidity_period(ts_py)

        # ── Force close on daily break / weekend / pre-close ──────────────────
        is_force_close = period in (CLOSED, CLOSING)

        if current_trade is not None and is_force_close:
            _finalise(current_trade, float(bar["close"]), ts, "SESSION_CLOSE")
            capital += current_trade._net_pnl
            completed.append(current_trade)
            current_trade = None
            continue

        # ── Manage open trade ─────────────────────────────────────────────────
        if current_trade is not None:
            high = float(bar["high"])
            low  = float(bar["low"])
            exit_reason = exit_px = None

            if current_trade.direction == "LONG":
                current_trade.update_trailing_stop(high)
                if low <= current_trade.stop_loss:
                    exit_reason, exit_px = "STOP_LOSS", current_trade.stop_loss
                elif high >= current_trade.take_profit:
                    exit_reason, exit_px = "TAKE_PROFIT", current_trade.take_profit
            else:
                current_trade.update_trailing_stop(low)
                if high >= current_trade.stop_loss:
                    exit_reason, exit_px = "STOP_LOSS", current_trade.stop_loss
                elif low <= current_trade.take_profit:
                    exit_reason, exit_px = "TAKE_PROFIT", current_trade.take_profit

            if exit_reason:
                _finalise(current_trade, exit_px, ts, exit_reason)
                capital += current_trade._net_pnl
                completed.append(current_trade)
                current_trade = None
            continue

        # ── Entry gate (pre_checks_gold order) ────────────────────────────────
        if not is_market_open(ts_py):
            continue
        if period in (CLOSED, CLOSING):
            continue
        # near-close: no new entries after 20:30 UTC
        hm = ts_py.hour * 60 + ts_py.minute
        if NO_ENTRY_AFTER_MIN <= hm < 21 * 60:
            continue

        is_asian = period == ASIAN

        bar_1h = _last_bar_at(df_1h, ts)
        bar_1d = _last_bar_at(df_1d, ts)
        if bar_1h is None or pd.isna(bar_1h.get("ssl_bull")):
            continue

        direction = _derive_direction(bar_1h)

        if not _daily_trend_ok(bar_1d, direction):
            continue
        if not _ssl_agreement_ok(bar_1h, direction):
            continue
        if not _1h_rsi_ok(bar_1h, direction, is_asian, cfg):
            continue
        if not _tmo_momentum_ok(bar_1h, bar):
            continue
        if not _not_choppy_ok(bar_1h, bar):
            continue
        if not _candle_confirmed_ok(bar_1h, bar):
            continue

        # ── Open trade ────────────────────────────────────────────────────────
        current_trade = GoldTrade(
            direction        = direction,
            entry_price      = float(bar["close"]),
            entry_time       = ts,
            liquidity_period = period,
            is_asian         = is_asian,
            is_eia           = is_eia_window(ts_py),
        )

    # ── Force close any trade still open at end of data ────────────────────────
    if current_trade is not None:
        _finalise(current_trade, float(df_5m.iloc[-1]["close"]),
                  df_5m.index[-1], "BACKTEST_END")
        capital += current_trade._net_pnl
        completed.append(current_trade)

    stats = _compute_stats(cfg, completed, capital, df_5m)
    return stats, completed


def _finalise(trade: GoldTrade, exit_px: float, ts, reason: str) -> None:
    trade.close(exit_px, reason)
    trade.exit_time = ts
    trade._cost_gbp = SPREAD_POINTS * trade.stake
    trade._net_pnl  = trade.pnl_gbp - trade._cost_gbp


# ── Statistics ─────────────────────────────────────────────────────────────────

def _subset_stats(trades: list) -> dict:
    wins = [t for t in trades if getattr(t, "_net_pnl", 0) > 0]
    return {
        "count":    len(trades),
        "wins":     len(wins),
        "win_rate": (len(wins) / len(trades) * 100) if trades else 0.0,
        "net_pnl":  sum(getattr(t, "_net_pnl", 0) for t in trades),
    }


def _max_drawdown(completed: list) -> float:
    """Peak-to-trough drawdown in GBP over the equity curve."""
    equity = STARTING_CAPITAL_GBP
    peak   = equity
    max_dd = 0.0
    for t in completed:
        equity += getattr(t, "_net_pnl", 0)
        peak    = max(peak, equity)
        max_dd  = max(max_dd, peak - equity)
    return max_dd


def _compute_stats(cfg: GateConfig, completed: list, final_capital: float,
                   df_5m: pd.DataFrame) -> dict:
    total   = len(completed)
    wins    = [t for t in completed if getattr(t, "_net_pnl", 0) > 0]
    losses  = [t for t in completed if getattr(t, "_net_pnl", 0) <= 0]

    net_pnl  = sum(getattr(t, "_net_pnl", 0) for t in completed)
    win_rate = len(wins) / total * 100 if total else 0.0
    avg_win  = (sum(getattr(t, "_net_pnl", 0) for t in wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(getattr(t, "_net_pnl", 0) for t in losses) / len(losses)) if losses else 0.0

    exit_counts: dict = defaultdict(int)
    for t in completed:
        exit_counts[t.exit_reason or "UNKNOWN"] += 1

    by_direction = {d: _subset_stats([t for t in completed if t.direction == d])
                    for d in ("LONG", "SHORT")}
    by_liquidity = {p: _subset_stats([t for t in completed if t.liquidity_period == p])
                    for p in LIQUIDITY_PERIODS}
    eia_stats     = _subset_stats([t for t in completed if t.is_eia])
    non_eia_stats = _subset_stats([t for t in completed if not t.is_eia])

    period_days = max((df_5m.index[-1] - df_5m.index[0]).days, 1)

    return {
        "cfg_name":       cfg.name,
        "cfg":            cfg,
        "total":          total,
        "wins":           len(wins),
        "losses":         len(losses),
        "win_rate":       win_rate,
        "net_pnl":        net_pnl,
        "final_capital":  final_capital,
        "avg_win":        avg_win,
        "avg_loss":       avg_loss,
        "max_drawdown":   _max_drawdown(completed),
        "exit_counts":    dict(exit_counts),
        "by_direction":   by_direction,
        "by_liquidity":   by_liquidity,
        "eia":            eia_stats,
        "non_eia":        non_eia_stats,
        "period_days":    period_days,
    }


# ── Verdict ────────────────────────────────────────────────────────────────────

def decide_verdict(base: dict, relax: dict) -> tuple:
    """
    IMPLEMENT if RELAXED: win rate >= 50% AND more trades AND no significant
    drawdown increase (<= 15% worse). Otherwise DEFER. Returns (implement, reasons).
    """
    reasons = []
    wr_ok = relax["win_rate"] >= 50.0
    reasons.append(
        f"RELAXED win rate {relax['win_rate']:.1f}% "
        f"{'>=' if wr_ok else '<'} 50% -> {'PASS' if wr_ok else 'FAIL'}")

    trades_ok = relax["total"] > base["total"]
    reasons.append(
        f"RELAXED trades {relax['total']} vs baseline {base['total']} "
        f"({'more' if trades_ok else 'not more'}) -> {'PASS' if trades_ok else 'FAIL'}")

    dd_limit = base["max_drawdown"] * 1.15 + 1e-9
    dd_ok = relax["max_drawdown"] <= dd_limit
    reasons.append(
        f"RELAXED max drawdown GBP {relax['max_drawdown']:.2f} vs baseline "
        f"GBP {base['max_drawdown']:.2f} (limit +15% = GBP {base['max_drawdown']*1.15:.2f}) "
        f"-> {'PASS' if dd_ok else 'FAIL'}")

    implement = wr_ok and trades_ok and dd_ok
    return implement, reasons


# ── Output: side-by-side table ─────────────────────────────────────────────────

def _fmt_sub(s: dict) -> str:
    return f"{s['count']:>4}  {s['win_rate']:>5.1f}%  GBP {s['net_pnl']:>+9.2f}"


def build_report(base: dict, relax: dict, implement: bool, reasons: list,
                 ticker: str, df_5m: pd.DataFrame) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p_start = df_5m.index[0].strftime("%Y-%m-%d")
    p_end   = df_5m.index[-1].strftime("%Y-%m-%d")
    L = []

    def line(x=""):
        L.append(x)

    line("=" * 78)
    line("  GoldHybrid AI -- backtest_gold.py  |  BASELINE vs RELAXED 1h-RSI veto")
    line(f"  Generated : {now_str}")
    line(f"  Data      : yfinance {ticker}  |  5m {p_start} -> {p_end} "
         f"({base['period_days']} days)")
    line(f"  Account   : GBP {STARTING_CAPITAL_GBP:.0f}  |  stake GBP {STAKE_PER_POINT:.2f}/pt "
         f"|  stop {STOP_POINTS:.0f}pt  |  TP {TAKE_PROFIT_POINTS:.0f}pt  |  spread {SPREAD_POINTS}pt")
    line("  BASELINE  : LONG 1h RSI >= 55, SHORT <= 45   (Asian 60/40)")
    line("  RELAXED   : LONG 1h RSI >= 52, SHORT <= 48   (Asian 60/40)")
    line("=" * 78)
    line("")

    W = 30
    line(f"  {'METRIC':<26} {'BASELINE':>{W}} {'RELAXED':>{W}}")
    line("  " + "-" * (26 + W * 2))

    def row(label, bval, rval):
        line(f"  {label:<26} {bval:>{W}} {rval:>{W}}")

    row("Total trades", base["total"], relax["total"])
    row("Wins / Losses",
        f"{base['wins']} / {base['losses']}",
        f"{relax['wins']} / {relax['losses']}")
    row("Overall win rate", f"{base['win_rate']:.1f}%", f"{relax['win_rate']:.1f}%")
    row("Net P&L (GBP)", f"{base['net_pnl']:+.2f}", f"{relax['net_pnl']:+.2f}")
    row("Final capital (GBP)", f"{base['final_capital']:.2f}", f"{relax['final_capital']:.2f}")
    row("Max drawdown (GBP)", f"{base['max_drawdown']:.2f}", f"{relax['max_drawdown']:.2f}")
    row("Avg winner (GBP)", f"{base['avg_win']:+.2f}", f"{relax['avg_win']:+.2f}")
    row("Avg loser (GBP)", f"{base['avg_loss']:+.2f}", f"{relax['avg_loss']:+.2f}")

    line("")
    line("  -- Win rate by DIRECTION  (trades / win% / net P&L) --")
    for d in ("LONG", "SHORT"):
        row(f"    {d}", _fmt_sub(base["by_direction"][d]),
            _fmt_sub(relax["by_direction"][d]))

    line("")
    line("  -- Win rate by LIQUIDITY PERIOD  (trades / win% / net P&L) --")
    for p in LIQUIDITY_PERIODS:
        row(f"    {p}", _fmt_sub(base["by_liquidity"][p]),
            _fmt_sub(relax["by_liquidity"][p]))

    line("")
    line("  -- EIA-Wednesday (15:00-16:00 UTC) performance, tracked separately --")
    row("    EIA window", _fmt_sub(base["eia"]), _fmt_sub(relax["eia"]))
    row("    Non-EIA", _fmt_sub(base["non_eia"]), _fmt_sub(relax["non_eia"]))
    line("    NOTE: live pre_checks_gold does NOT block the EIA window; flagged only.")

    line("")
    line("  -- Exit reason breakdown --")
    for reason in ("STOP_LOSS", "TAKE_PROFIT", "SESSION_CLOSE", "BACKTEST_END"):
        row(f"    {reason}",
            base["exit_counts"].get(reason, 0),
            relax["exit_counts"].get(reason, 0))

    line("")
    line("=" * 78)
    line("  VERDICT -- relax 1h RSI veto (55/45 -> 52/48)?")
    line("  Rule: IMPLEMENT iff RELAXED win rate >= 50% AND more trades AND")
    line("        no significant drawdown increase (<= +15% vs baseline).")
    line("=" * 78)
    for r in reasons:
        line(f"  - {r}")
    line("")
    if implement:
        line("  >> DECISION: IMPLEMENT -- relaxation validated. pre_checks_gold updated")
        line("     (RSI_LONG_NORMAL 55->52, RSI_SHORT_NORMAL 45->48).")
    else:
        line("  >> DECISION: DEFER -- relaxation not justified on this sample.")
        line("     pre_checks_gold left unchanged.")
    line("=" * 78)
    return "\n".join(L)


def save_trades_csv(all_runs: list) -> None:
    path = LOGS_DIR / "backtest_gold_trades.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "config", "trade_no", "direction", "liquidity_period",
            "is_asian", "is_eia", "entry_time", "exit_time",
            "entry_price", "exit_price", "pnl_pts",
            "stake_gbp_per_pt", "gross_pnl_gbp", "cost_gbp", "net_pnl_gbp",
            "exit_reason",
        ])
        for cfg_name, trades in all_runs:
            for i, t in enumerate(trades, 1):
                w.writerow([
                    cfg_name, i, t.direction, t.liquidity_period,
                    "YES" if t.is_asian else "no",
                    "YES" if t.is_eia else "no",
                    t.entry_time.strftime("%Y-%m-%d %H:%M") if t.entry_time else "",
                    t.exit_time.strftime("%Y-%m-%d %H:%M") if t.exit_time else "",
                    f"{t.entry_price:.2f}",
                    f"{t.exit_price:.2f}" if t.exit_price is not None else "",
                    f"{t.pnl_pts:.2f}" if t.pnl_pts is not None else "",
                    f"{t.stake:.4f}",
                    f"{t.pnl_gbp:.2f}" if t.pnl_gbp is not None else "",
                    f"{getattr(t, '_cost_gbp', 0):.4f}",
                    f"{getattr(t, '_net_pnl', 0):.2f}",
                    t.exit_reason or "",
                ])
    log.info("Trades CSV saved -> %s", path)


# ── Entry point ────────────────────────────────────────────────────────────────

def run_backtest() -> None:
    LOGS_DIR.mkdir(exist_ok=True)
    log.info("GoldHybrid AI -- Gold spot backtest  (BASELINE vs RELAXED 1h RSI veto)")

    df_1d, df_1h, df_5m, ticker = fetch_historical_data()

    base_stats,  base_trades  = run_single_backtest(BASELINE, df_1d, df_1h, df_5m)
    relax_stats, relax_trades = run_single_backtest(RELAXED,  df_1d, df_1h, df_5m)

    implement, reasons = decide_verdict(base_stats, relax_stats)

    report = build_report(base_stats, relax_stats, implement, reasons, ticker, df_5m)
    print()
    print(report)

    results_path = LOGS_DIR / "backtest_gold_results.txt"
    results_path.write_text(report, encoding="utf-8")
    log.info("Results saved -> %s", results_path)

    save_trades_csv([(BASELINE.name, base_trades), (RELAXED.name, relax_trades)])

    # Emit a machine-readable verdict marker for the caller.
    print()
    print(f"VERDICT_DECISION: {'IMPLEMENT' if implement else 'DEFER'}")

    log.info("Backtest complete.")


if __name__ == "__main__":
    run_backtest()
