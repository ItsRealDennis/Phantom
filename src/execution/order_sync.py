"""Order sync — poll Alpaca for fill status, replace yfinance-based settlement."""

import logging
from datetime import datetime

from src.execution.alpaca_client import get_client, is_alpaca_enabled
from src.tracking.trade_logger import (
    get_open_alpaca_trades,
    get_open_paper_trades,
    settle_trade,
    update_alpaca_status,
)
from src.automation.settler import auto_settle_open_trades as paper_settle
from src.config import TRADE_EXPIRY_DAYS

logger = logging.getLogger(__name__)


def sync_alpaca_orders() -> list[dict]:
    """
    Sync all open Alpaca trades by checking order status.
    Settles trades when TP or SL fills, cancels expired entries.
    """
    client = get_client()
    if not client:
        return []

    trades = get_open_alpaca_trades()
    if not trades:
        return []

    settlements = []

    for trade in trades:
        order_id = trade["alpaca_order_id"]
        try:
            order = client.get_order_by_id(order_id)
        except Exception as e:
            logger.warning("Failed to fetch order %s for %s: %s", order_id, trade["ticker"], e)
            continue

        order_status = order.status.value if hasattr(order.status, 'value') else str(order.status)
        entry_fill_price = float(order.filled_avg_price) if order.filled_avg_price else None

        # Update the raw Alpaca status
        update_alpaca_status(trade["id"], order_status, fill_price=entry_fill_price)

        # Entry order rejected or canceled
        if order_status in ("canceled", "expired", "rejected"):
            settle_trade(trade["id"], "canceled", 0.0, notes=f"Alpaca entry {order_status}")
            settlements.append({
                "id": trade["id"],
                "ticker": trade["ticker"],
                "status": "canceled",
                "pnl": 0.0,
            })
            logger.info("Trade #%d (%s) entry %s", trade["id"], trade["ticker"], order_status)
            continue

        # Entry not yet filled — check for expiry
        if order_status in ("new", "accepted", "pending_new"):
            created = datetime.fromisoformat(trade["created_at"])
            age_days = (datetime.now() - created).days
            if age_days > TRADE_EXPIRY_DAYS:
                # Cancel the unfilled order
                try:
                    client.cancel_order_by_id(order_id)
                    settle_trade(trade["id"], "expired", 0.0, notes="Entry never filled, canceled after expiry")
                    settlements.append({
                        "id": trade["id"],
                        "ticker": trade["ticker"],
                        "status": "expired",
                        "pnl": 0.0,
                    })
                    logger.info("Trade #%d (%s) expired — entry never filled", trade["id"], trade["ticker"])
                except Exception as e:
                    logger.error("Failed to cancel expired order %s: %s", order_id, e)
            continue

        # Entry filled — check the exit legs
        if order_status == "filled" and not order.legs:
            # Bracket parent filled with no legs = shouldn't happen, but handle it
            logger.warning("Trade #%d filled but no legs found", trade["id"])
            continue

        if order.legs:
            result = _check_bracket_legs(trade, order, entry_fill_price)
            if result:
                settlements.append(result)

    if settlements:
        logger.info("Alpaca sync: %d trades settled", len(settlements))
    else:
        logger.debug("Alpaca sync: no settlements")

    return settlements


def _check_bracket_legs(trade: dict, order, entry_fill_price: float | None) -> dict | None:
    """Check bracket order legs for TP/SL fills."""
    shares = trade["shares"] or 0
    direction = trade["direction"]

    for leg in order.legs:
        leg_status = leg.status.value if hasattr(leg.status, 'value') else str(leg.status)

        if leg_status != "filled":
            continue

        leg_fill_price = float(leg.filled_avg_price) if leg.filled_avg_price else None
        if not leg_fill_price or not entry_fill_price:
            continue

        # Determine if this is TP or SL leg
        is_stop = hasattr(leg, 'stop_price') and leg.stop_price is not None
        has_limit_only = hasattr(leg, 'limit_price') and leg.limit_price and not is_stop

        if direction == "LONG":
            pnl = shares * (leg_fill_price - entry_fill_price)
        else:
            pnl = shares * (entry_fill_price - leg_fill_price)

        pnl = round(pnl, 2)

        if is_stop:
            status = "stopped"
        elif has_limit_only:
            status = "won"
        else:
            # Fallback: determine by P&L
            status = "won" if pnl > 0 else "stopped"

        settle_trade(
            trade["id"], status, pnl,
            notes=f"Alpaca fill @ ${leg_fill_price:.2f}",
            exit_price=leg_fill_price,
        )

        logger.info(
            "Trade #%d (%s) %s — entry: $%.2f, exit: $%.2f, P&L: $%.2f",
            trade["id"], trade["ticker"], status,
            entry_fill_price, leg_fill_price, pnl,
        )

        return {
            "id": trade["id"],
            "ticker": trade["ticker"],
            "status": status,
            "pnl": pnl,
            "entry_fill": entry_fill_price,
            "exit_fill": leg_fill_price,
        }

    return None


def sync_all_open_trades() -> list[dict]:
    """
    Combined sync: Alpaca trades via API, paper trades via yfinance.
    Called by the scheduler.
    """
    results = []

    # Sync Alpaca orders
    if is_alpaca_enabled():
        alpaca_results = sync_alpaca_orders()
        results.extend(alpaca_results)

    # Settle paper-only trades via yfinance (existing settler logic)
    paper_results = paper_settle()
    results.extend(paper_results)

    return results
