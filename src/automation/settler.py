"""Auto-settlement — check open trades against current prices for TP/SL/expiry.

Phase 2 upgrades:
  - Intraday high/low checks (catches stops hit mid-bar)
  - MAE/MFE tracking per trade
  - Per-strategy max hold times
  - Settlement method recording
"""

import logging
from datetime import datetime

import yfinance as yf

from src.config import TRADE_EXPIRY_DAYS, STRATEGY_MAX_HOLD, is_crypto, alpaca_to_yfinance
from src.tracking.trade_logger import get_open_trades, settle_trade, update_mae_mfe

logger = logging.getLogger(__name__)


def get_current_price(ticker: str) -> float:
    """Fetch the latest price for a ticker."""
    yf_sym = alpaca_to_yfinance(ticker) if is_crypto(ticker) else ticker
    tk = yf.Ticker(yf_sym)
    try:
        price = tk.fast_info.get("lastPrice")
    except Exception:
        price = None
    if price is None:
        price = tk.info.get("currentPrice") or tk.info.get("regularMarketPrice")
    if price is None:
        raise ValueError(f"No price available for {ticker}")
    return float(price)


def get_price_range_since(ticker: str, entry_time: str) -> dict:
    """
    Fetch current price + intraday high/low since entry.

    Uses 5-minute bars to detect if stop/target was breached mid-bar,
    even if the current price has since recovered.

    Returns {"current": float, "high": float, "low": float, "bars": int}
    """
    yf_sym = alpaca_to_yfinance(ticker) if is_crypto(ticker) else ticker
    tk = yf.Ticker(yf_sym)

    # Fetch intraday data — 5d of 5m bars covers up to 5 trading days
    try:
        df = tk.history(period="5d", interval="5m")
    except Exception:
        # Fallback: just get current price
        current = get_current_price(ticker)
        return {"current": current, "high": current, "low": current, "bars": 0}

    if df.empty:
        current = get_current_price(ticker)
        return {"current": current, "high": current, "low": current, "bars": 0}

    # Filter to bars since entry
    try:
        entry_dt = datetime.fromisoformat(entry_time)
        # Make entry_dt timezone-aware if df index is tz-aware
        if df.index.tz is not None and entry_dt.tzinfo is None:
            import pytz
            entry_dt = pytz.UTC.localize(entry_dt)
        df_since = df[df.index >= entry_dt]
        if df_since.empty:
            df_since = df  # Use all data if entry is before available bars
    except Exception:
        df_since = df

    current = float(df_since["Close"].iloc[-1])
    high = float(df_since["High"].max())
    low = float(df_since["Low"].min())
    bars = len(df_since)

    return {"current": current, "high": high, "low": low, "bars": bars}


def _compute_mae_mfe(trade: dict, price_range: dict) -> tuple[float, float, float]:
    """
    Compute MAE/MFE/HWM from price range.

    MAE = max adverse excursion (worst unrealized loss, as positive number)
    MFE = max favorable excursion (best unrealized gain, as positive number)
    HWM = high water mark (best price reached)
    """
    entry = trade["entry_price"]
    direction = trade["direction"]

    if direction == "LONG":
        mae = max(0, entry - price_range["low"])
        mfe = max(0, price_range["high"] - entry)
        hwm = price_range["high"]
    else:  # SHORT
        mae = max(0, price_range["high"] - entry)
        mfe = max(0, entry - price_range["low"])
        hwm = price_range["low"]  # For shorts, "high water" = lowest price

    return mae, mfe, hwm


def check_trade_outcome(trade: dict, price_range: dict) -> tuple[str, float, str] | None:
    """
    Check if a trade has hit TP, SL, or expired using intraday high/low.

    Returns (status, pnl, settlement_method) or None if trade is still active.
    Uses stop/target price for P&L when TP/SL hit (not current price).
    """
    direction = trade["direction"]
    entry = trade["entry_price"]
    stop = trade["stop_loss"]
    target = trade["take_profit"]
    position_size = trade["position_size"]

    risk_per_share = abs(entry - stop)
    if risk_per_share == 0 or not position_size:
        return None
    shares = int(position_size / risk_per_share)

    # Check stop loss using intraday low/high
    if direction == "LONG":
        if price_range["low"] <= stop:
            pnl = shares * (stop - entry)
            return ("stopped", round(pnl, 2), "stop_hit")
        if price_range["high"] >= target:
            pnl = shares * (target - entry)
            return ("won", round(pnl, 2), "target_hit")
    elif direction == "SHORT":
        if price_range["high"] >= stop:
            pnl = shares * (entry - stop)
            return ("stopped", round(pnl, 2), "stop_hit")
        if price_range["low"] <= target:
            pnl = shares * (entry - target)
            return ("won", round(pnl, 2), "target_hit")

    # Check expiry — use strategy-specific max hold time
    created = datetime.fromisoformat(trade["created_at"])
    max_hold_hours = STRATEGY_MAX_HOLD.get(
        trade["strategy"], TRADE_EXPIRY_DAYS * 24
    )
    age_hours = (datetime.now() - created).total_seconds() / 3600

    if age_hours > max_hold_hours:
        current = price_range["current"]
        if direction == "LONG":
            pnl = shares * (current - entry)
        else:
            pnl = shares * (entry - current)
        status = "won" if pnl > 0 else "lost"
        return (status, round(pnl, 2), "expired")

    return None


def auto_settle_open_trades() -> list[dict]:
    """
    Check all open trades against current prices with intraday H/L.
    Tracks MAE/MFE on every check. Settles any that hit TP, SL, or expired.
    Returns list of settlements made.
    """
    open_trades = get_open_trades()
    settlements = []

    for trade in open_trades:
        if not trade["passed_filter"]:
            continue

        try:
            price_range = get_price_range_since(
                trade["ticker"], trade["created_at"]
            )
        except Exception as e:
            logger.warning("Price fetch failed for %s: %s", trade["ticker"], e)
            continue

        # Update MAE/MFE on every check (even if trade stays open)
        try:
            mae, mfe, hwm = _compute_mae_mfe(trade, price_range)
            update_mae_mfe(trade["id"], mae, mfe, hwm)
        except Exception as e:
            logger.debug("MAE/MFE update failed for #%d: %s", trade["id"], e)

        outcome = check_trade_outcome(trade, price_range)
        if outcome is None:
            continue

        status, pnl, method = outcome
        notes = f"Auto-settled at ${price_range['current']:.2f} ({method})"

        try:
            settle_trade(
                trade["id"], status, pnl,
                notes=notes,
                exit_price=price_range["current"],
                settlement_method=method,
                settlement_price=price_range["current"],
                bars_held=price_range["bars"],
            )
            settlement = {
                "id": trade["id"],
                "ticker": trade["ticker"],
                "status": status,
                "pnl": pnl,
                "price": price_range["current"],
                "method": method,
            }
            settlements.append(settlement)
            logger.info(
                "Settled %s #%d as %s via %s — P&L: $%.2f",
                trade["ticker"], trade["id"], status, method, pnl,
            )
        except Exception as e:
            logger.error("Failed to settle trade #%d: %s", trade["id"], e)

    if settlements:
        logger.info("Auto-settlement: %d trades settled", len(settlements))
    else:
        logger.debug("Auto-settlement: no trades to settle")

    return settlements
