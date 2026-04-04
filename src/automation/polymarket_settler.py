"""Polymarket trade settler — check resolution status and settle binary outcomes."""

import logging
from datetime import datetime, timezone

from src.collectors.polymarket_data import get_market, get_midpoint
from src.tracking.trade_logger import (
    get_open_trades, settle_trade, update_mae_mfe, get_connection,
)
from src.config import STRATEGY_MAX_HOLD

logger = logging.getLogger(__name__)


def _parse_market_slug(ticker: str) -> str:
    """Extract market slug from PM:slug ticker format."""
    if ticker.startswith("PM:"):
        return ticker[3:]
    return ticker


def _is_polymarket_trade(trade: dict) -> bool:
    """Check if a trade is a Polymarket trade."""
    return trade.get("ticker", "").startswith("PM:") or (
        trade.get("strategy", "").startswith("pm_")
    )


def settle_polymarket_trades():
    """
    Check all open Polymarket trades for resolution or exit conditions.

    Settlement conditions:
    1. Market resolved → settle as won/lost based on outcome
    2. Max hold time exceeded → settle at current market price
    3. Price moved significantly against us → paper stop-out
    """
    open_trades = get_open_trades()
    pm_trades = [t for t in open_trades if _is_polymarket_trade(t)]

    if not pm_trades:
        return

    logger.info("Checking %d open Polymarket trades for settlement", len(pm_trades))

    for trade in pm_trades:
        try:
            _check_and_settle(trade)
        except Exception as e:
            logger.error("Error settling PM trade #%d: %s", trade["id"], e)


def _check_and_settle(trade: dict):
    """Check a single Polymarket trade for settlement."""
    signal_id = trade["id"]
    ticker = trade["ticker"]
    slug = _parse_market_slug(ticker)
    direction = trade["direction"]
    entry_price = trade["entry_price"]
    strategy = trade.get("strategy", "pm_mispricing")

    # Fetch current market state
    # Try to find market by slug via Gamma API
    from src.collectors.polymarket_data import get_market_by_slug, list_markets
    market = get_market_by_slug(slug)

    if not market:
        logger.debug("Could not fetch market for %s", ticker)
        return

    # Check if market is resolved
    is_closed = market.get("closed", False)
    is_resolved = market.get("resolved", False)

    if is_resolved or is_closed:
        _settle_resolved(trade, market)
        return

    # Get current price for MAE/MFE tracking
    tokens = market.get("tokens", [])
    current_yes_price = None
    for t in tokens:
        if t.get("outcome", "").upper() == "YES":
            current_yes_price = float(t.get("price", 0))

    if current_yes_price is None:
        return

    # Calculate current P&L
    if direction == "YES":
        current_value = current_yes_price
        cost = entry_price
    else:
        current_value = 1.0 - current_yes_price
        cost = entry_price  # entry_price for NO = 1 - yes_price at entry

    pnl_per_share = current_value - cost
    shares = trade.get("shares", 0) or (trade.get("position_size", 0) / cost if cost > 0 else 0)
    unrealized_pnl = pnl_per_share * shares

    # Update MAE/MFE
    mae = max(0, -pnl_per_share)
    mfe = max(0, pnl_per_share)
    hwm = current_value
    update_mae_mfe(signal_id, mae, mfe, hwm)

    # Check max hold time
    created_at = trade.get("created_at", "")
    if created_at:
        try:
            created = datetime.fromisoformat(created_at)
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            hours_held = (now - created).total_seconds() / 3600

            # Get strategy-specific max hold
            base_strategy = strategy.replace("pm_", "")
            max_hold = STRATEGY_MAX_HOLD.get(base_strategy, STRATEGY_MAX_HOLD.get(strategy, 168))

            if hours_held >= max_hold:
                # Expire at current price
                real_pnl = round(unrealized_pnl, 2)
                status = "won" if real_pnl > 0 else "lost"
                settle_trade(
                    signal_id=signal_id,
                    status=status,
                    real_pnl=real_pnl,
                    notes=f"Max hold time ({max_hold}h) expired. Current price: {current_yes_price:.3f}",
                    exit_price=current_value,
                    settlement_method="polymarket_expiry",
                    settlement_price=current_yes_price,
                )
                logger.info(
                    "PM trade #%d expired after %dh: %s $%.2f",
                    signal_id, int(hours_held), status, real_pnl,
                )
        except (ValueError, TypeError):
            pass


def _settle_resolved(trade: dict, market: dict):
    """Settle a trade where the market has resolved."""
    signal_id = trade["id"]
    direction = trade["direction"]
    entry_price = trade["entry_price"]
    shares = trade.get("shares", 0) or 1

    # Determine winning outcome
    tokens = market.get("tokens", [])
    winning_outcome = None
    for t in tokens:
        winner = t.get("winner", False)
        if winner:
            winning_outcome = t.get("outcome", "").upper()

    if winning_outcome is None:
        # Try resolution value
        resolution = market.get("resolution", "")
        if resolution:
            winning_outcome = resolution.upper()

    if winning_outcome is None:
        logger.warning("PM trade #%d: market resolved but no winner found", signal_id)
        return

    # Did we win?
    we_won = (direction == winning_outcome)

    if we_won:
        # Won: payout is $1 per share, cost was entry_price
        pnl_per_share = 1.0 - entry_price
        status = "won"
    else:
        # Lost: payout is $0, cost was entry_price
        pnl_per_share = -entry_price
        status = "lost"

    real_pnl = round(pnl_per_share * shares, 2)

    settle_trade(
        signal_id=signal_id,
        status=status,
        real_pnl=real_pnl,
        notes=f"Market resolved: {winning_outcome}. Direction: {direction}.",
        exit_price=1.0 if we_won else 0.0,
        settlement_method="polymarket_resolution",
        settlement_price=1.0 if we_won else 0.0,
    )

    logger.info(
        "PM trade #%d resolved: %s (we said %s) → %s $%.2f",
        signal_id, winning_outcome, direction, status, real_pnl,
    )
