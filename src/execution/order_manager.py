"""Order manager — submit bracket orders to Alpaca."""

import logging
import time

from src.execution.alpaca_client import get_client, is_alpaca_enabled

logger = logging.getLogger(__name__)


def submit_bracket_order(signal: dict) -> dict:
    """
    Submit a bracket order (market entry + stop loss + take profit) to Alpaca.

    Uses MARKET order for instant fill, with bracket legs for SL and TP.
    This is day-trading mode — get in immediately, let the bracket manage exits.

    Args:
        signal: dict with keys: signal_id, ticker, timeframe, analysis, sizing

    Returns:
        {success: True, order_id, tp_order_id, sl_order_id} on success
        {success: False, error: str} on failure
    """
    if not is_alpaca_enabled():
        return {"success": False, "error": "Alpaca not enabled"}

    client = get_client()
    if not client:
        return {"success": False, "error": "Alpaca client not available"}

    analysis = signal["analysis"]
    sizing = signal["sizing"]
    ticker = signal["ticker"]
    timeframe = signal.get("timeframe", "15m")

    from src.config import is_crypto

    shares = sizing["shares"]
    crypto = is_crypto(ticker)

    # Crypto can use fractional qty; stocks need integer >= 1
    if not crypto and shares <= 0:
        return {"success": False, "error": f"Invalid share count: {shares}"}

    stop_price = round(analysis["stopLoss"], 2)
    tp_price = round(analysis["takeProfit"], 2)
    direction = analysis["direction"]

    # Crypto always uses GTC (trades 24/7). Stocks: DAY for intraday, GTC for daily.
    if crypto:
        tif_str = "gtc"
    else:
        tif_str = "day" if timeframe in ("5m", "15m", "1h") else "gtc"

    try:
        from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
        from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

        side = OrderSide.BUY if direction == "LONG" else OrderSide.SELL
        tif = TimeInForce.DAY if tif_str == "day" else TimeInForce.GTC

        # Market order with bracket = instant entry, SL + TP attached
        request = MarketOrderRequest(
            symbol=ticker,
            qty=shares,
            side=side,
            time_in_force=tif,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=tp_price),
            stop_loss=StopLossRequest(stop_price=stop_price),
        )

        order = client.submit_order(order_data=request)

        # Extract leg order IDs
        tp_order_id = None
        sl_order_id = None
        if order.legs:
            for leg in order.legs:
                is_stop = hasattr(leg, 'stop_price') and leg.stop_price is not None
                if is_stop:
                    sl_order_id = str(leg.id)
                else:
                    tp_order_id = str(leg.id)

        result = {
            "success": True,
            "order_id": str(order.id),
            "tp_order_id": tp_order_id,
            "sl_order_id": sl_order_id,
            "status": order.status.value if hasattr(order.status, 'value') else str(order.status),
        }

        logger.info(
            "MARKET bracket order: %s %s %d shares (SL: $%.2f, TP: $%.2f) — ID: %s",
            direction, ticker, shares, stop_price, tp_price, order.id,
        )

        return result

    except Exception as e:
        error_msg = str(e)
        logger.error("Alpaca order failed for %s: %s", ticker, error_msg)

        # Retry once on transient errors
        if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
            logger.info("Retrying order for %s...", ticker)
            time.sleep(2)
            try:
                order = client.submit_order(order_data=request)
                tp_order_id = None
                sl_order_id = None
                if order.legs:
                    for i, leg in enumerate(order.legs):
                        if i == 0:
                            tp_order_id = str(leg.id)
                        else:
                            sl_order_id = str(leg.id)
                return {
                    "success": True,
                    "order_id": str(order.id),
                    "tp_order_id": tp_order_id,
                    "sl_order_id": sl_order_id,
                    "status": order.status.value if hasattr(order.status, 'value') else str(order.status),
                }
            except Exception as retry_e:
                logger.error("Retry failed for %s: %s", ticker, retry_e)
                return {"success": False, "error": f"Retry failed: {retry_e}"}

        return {"success": False, "error": error_msg}


def cancel_order(order_id: str) -> bool:
    """Cancel a specific Alpaca order."""
    client = get_client()
    if not client:
        return False

    try:
        client.cancel_order_by_id(order_id)
        logger.info("Order %s canceled", order_id)
        return True
    except Exception as e:
        logger.error("Failed to cancel order %s: %s", order_id, e)
        return False
