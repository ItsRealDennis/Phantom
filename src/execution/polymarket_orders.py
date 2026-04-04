"""Polymarket order manager — submit buy/sell orders via CLOB client."""

import logging
import time

from src.execution.polymarket_client import get_client, is_polymarket_enabled

logger = logging.getLogger(__name__)


def submit_order(
    token_id: str,
    side: str,
    price: float,
    size: float,
    tick_size: str = "0.01",
    neg_risk: bool = False,
) -> dict:
    """
    Submit a limit order to the Polymarket CLOB.

    Args:
        token_id: The ERC1155 token ID (YES or NO token)
        side: "BUY" or "SELL"
        price: Limit price (0-1)
        size: Number of shares
        tick_size: Market tick size (default "0.01")
        neg_risk: Whether this is a negative risk market

    Returns:
        {success: True, order_id, status} on success
        {success: False, error: str} on failure
    """
    if not is_polymarket_enabled():
        return {"success": False, "error": "Polymarket not enabled"}

    client = get_client()
    if not client:
        return {"success": False, "error": "Polymarket client not available"}

    try:
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY, SELL

        order_side = BUY if side.upper() == "BUY" else SELL

        response = client.create_and_post_order(
            OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side=order_side,
            ),
            options={
                "tick_size": tick_size,
                "neg_risk": neg_risk,
            },
            order_type=OrderType.GTC,
        )

        order_id = response.get("orderID", response.get("order_id", ""))
        status = response.get("status", "unknown")

        result = {
            "success": True,
            "order_id": order_id,
            "status": status,
            "response": response,
        }

        logger.info(
            "Polymarket order: %s %s %.0f shares @ %.3f — ID: %s",
            side, token_id[:12] + "...", size, price, order_id,
        )

        return result

    except Exception as e:
        error_msg = str(e)
        logger.error("Polymarket order failed: %s", error_msg)

        # Retry once on transient errors
        if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
            logger.info("Retrying Polymarket order...")
            time.sleep(2)
            try:
                response = client.create_and_post_order(
                    OrderArgs(
                        token_id=token_id,
                        price=price,
                        size=size,
                        side=order_side,
                    ),
                    options={
                        "tick_size": tick_size,
                        "neg_risk": neg_risk,
                    },
                    order_type=OrderType.GTC,
                )
                return {
                    "success": True,
                    "order_id": response.get("orderID", ""),
                    "status": response.get("status", "unknown"),
                    "response": response,
                }
            except Exception as retry_e:
                logger.error("Polymarket retry failed: %s", retry_e)
                return {"success": False, "error": f"Retry failed: {retry_e}"}

        return {"success": False, "error": error_msg}


def cancel_order(order_id: str) -> bool:
    """Cancel a Polymarket order."""
    client = get_client()
    if not client:
        return False

    try:
        client.cancel(order_id=order_id)
        logger.info("Polymarket order %s canceled", order_id)
        return True
    except Exception as e:
        logger.error("Failed to cancel Polymarket order %s: %s", order_id, e)
        return False


def cancel_all_orders() -> bool:
    """Cancel all open Polymarket orders."""
    client = get_client()
    if not client:
        return False

    try:
        client.cancel_all()
        logger.info("All Polymarket orders canceled")
        return True
    except Exception as e:
        logger.error("Failed to cancel all Polymarket orders: %s", e)
        return False


def get_open_orders() -> list[dict]:
    """Get all open orders on Polymarket."""
    client = get_client()
    if not client:
        return []

    try:
        orders = client.get_orders()
        return orders if isinstance(orders, list) else []
    except Exception as e:
        logger.error("Failed to get Polymarket orders: %s", e)
        return []


def get_trades() -> list[dict]:
    """Get recent trades on Polymarket."""
    client = get_client()
    if not client:
        return []

    try:
        trades = client.get_trades()
        return trades if isinstance(trades, list) else []
    except Exception as e:
        logger.error("Failed to get Polymarket trades: %s", e)
        return []
