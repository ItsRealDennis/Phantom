"""Auto-settlement — check open trades against current prices for TP/SL/expiry."""

import logging
from datetime import datetime

import yfinance as yf

from src.config import TRADE_EXPIRY_DAYS
from src.tracking.trade_logger import get_open_trades, settle_trade

logger = logging.getLogger(__name__)


def get_current_price(ticker: str) -> float:
    """Fetch the latest price for a ticker."""
    tk = yf.Ticker(ticker)
    try:
        price = tk.fast_info.get("lastPrice")
    except Exception:
        price = None
    if price is None:
        price = tk.info.get("currentPrice") or tk.info.get("regularMarketPrice")
    if price is None:
        raise ValueError(f"No price available for {ticker}")
    return float(price)


def check_trade_outcome(trade: dict, current_price: float) -> tuple[str, float] | None:
    """
    Check if a trade has hit TP, SL, or expired.

    Returns (status, pnl) or None if trade is still active.
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

    if direction == "LONG":
        if current_price <= stop:
            pnl = shares * (stop - entry)
            return ("stopped", round(pnl, 2))
        if current_price >= target:
            pnl = shares * (target - entry)
            return ("won", round(pnl, 2))
    elif direction == "SHORT":
        if current_price >= stop:
            pnl = shares * (entry - stop)
            return ("stopped", round(pnl, 2))
        if current_price <= target:
            pnl = shares * (entry - target)
            return ("won", round(pnl, 2))

    # Check expiry
    created = datetime.fromisoformat(trade["created_at"])
    age_days = (datetime.now() - created).days
    if age_days > TRADE_EXPIRY_DAYS:
        if direction == "LONG":
            pnl = shares * (current_price - entry)
        else:
            pnl = shares * (entry - current_price)
        status = "won" if pnl > 0 else "lost"
        return (status, round(pnl, 2))

    return None


def auto_settle_open_trades() -> list[dict]:
    """
    Check all open trades against current prices.
    Settles any that hit TP, SL, or expired.
    Returns list of settlements made.
    """
    open_trades = get_open_trades()
    settlements = []

    for trade in open_trades:
        if not trade["passed_filter"]:
            continue

        try:
            current_price = get_current_price(trade["ticker"])
        except Exception as e:
            logger.warning("Price fetch failed for %s: %s", trade["ticker"], e)
            continue

        outcome = check_trade_outcome(trade, current_price)
        if outcome is None:
            continue

        status, pnl = outcome
        notes = f"Auto-settled at ${current_price:.2f}"

        try:
            settle_trade(trade["id"], status, pnl, notes)
            settlement = {
                "id": trade["id"],
                "ticker": trade["ticker"],
                "status": status,
                "pnl": pnl,
                "price": current_price,
            }
            settlements.append(settlement)
            logger.info(
                "Settled %s #%d as %s — P&L: $%.2f",
                trade["ticker"], trade["id"], status, pnl,
            )
        except Exception as e:
            logger.error("Failed to settle trade #%d: %s", trade["id"], e)

    if settlements:
        logger.info("Auto-settlement: %d trades settled", len(settlements))
    else:
        logger.debug("Auto-settlement: no trades to settle")

    return settlements
