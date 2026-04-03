"""Alpaca Trading Client — singleton with graceful fallback."""

import logging
from functools import lru_cache

from src.config import ALPACA_API_KEY, ALPACA_SECRET_KEY

logger = logging.getLogger(__name__)

_client = None
_initialized = False


def is_alpaca_enabled() -> bool:
    """Check if Alpaca API keys are configured."""
    return bool(ALPACA_API_KEY) and bool(ALPACA_SECRET_KEY)


def get_client():
    """
    Get the Alpaca TradingClient singleton. Returns None if keys not set.
    Lazy initialization — only imports alpaca-py when actually needed.
    """
    global _client, _initialized

    if _initialized:
        return _client

    _initialized = True

    if not is_alpaca_enabled():
        logger.info("Alpaca not configured — running in paper-only mode")
        return None

    try:
        from alpaca.trading.client import TradingClient

        _client = TradingClient(
            api_key=ALPACA_API_KEY,
            secret_key=ALPACA_SECRET_KEY,
            paper=True,
        )
        # Test connectivity
        _client.get_account()
        logger.info("Alpaca paper trading client connected")
        return _client
    except Exception as e:
        logger.error("Failed to initialize Alpaca client: %s", e)
        _client = None
        return None


def get_account_info() -> dict | None:
    """Get Alpaca account data: equity, buying_power, cash, etc."""
    client = get_client()
    if not client:
        return None

    try:
        account = client.get_account()
        return {
            "equity": float(account.equity),
            "cash": float(account.cash),
            "buying_power": float(account.buying_power),
            "portfolio_value": float(account.portfolio_value),
            "day_pnl": float(account.equity) - float(account.last_equity),
            "status": account.status.value if hasattr(account.status, 'value') else str(account.status),
            "currency": account.currency,
        }
    except Exception as e:
        logger.error("Failed to get Alpaca account info: %s", e)
        return None


def get_positions() -> list[dict]:
    """Get all open Alpaca positions."""
    client = get_client()
    if not client:
        return []

    try:
        positions = client.get_all_positions()
        return [
            {
                "symbol": p.symbol,
                "qty": float(p.qty),
                "side": p.side.value if hasattr(p.side, 'value') else str(p.side),
                "market_value": float(p.market_value),
                "cost_basis": float(p.cost_basis),
                "unrealized_pl": float(p.unrealized_pl),
                "unrealized_plpc": float(p.unrealized_plpc),
                "current_price": float(p.current_price),
                "avg_entry_price": float(p.avg_entry_price),
            }
            for p in positions
        ]
    except Exception as e:
        logger.error("Failed to get Alpaca positions: %s", e)
        return []
