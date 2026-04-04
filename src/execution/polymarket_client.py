"""Polymarket CLOB client — lazy initialization, graceful fallback to paper mode."""

import logging
import os

from src.config import (
    POLYMARKET_PRIVATE_KEY,
    POLYMARKET_FUNDER,
    POLYMARKET_HOST,
    POLYMARKET_CHAIN_ID,
    POLYMARKET_ENABLED,
)

logger = logging.getLogger(__name__)

_client = None
_initialized = False


def is_polymarket_enabled() -> bool:
    """Check if Polymarket trading is configured and enabled."""
    return POLYMARKET_ENABLED and bool(POLYMARKET_PRIVATE_KEY)


def get_client():
    """Lazy-init the Polymarket CLOB client. Returns None if unavailable."""
    global _client, _initialized

    if _initialized:
        return _client

    _initialized = True

    if not is_polymarket_enabled():
        logger.info("Polymarket not enabled (set POLYMARKET_PRIVATE_KEY + PHANTOM_POLYMARKET=true)")
        return None

    try:
        from py_clob_client.client import ClobClient

        # Create temp client to derive API credentials
        temp_client = ClobClient(
            POLYMARKET_HOST,
            key=POLYMARKET_PRIVATE_KEY,
            chain_id=POLYMARKET_CHAIN_ID,
        )
        api_creds = temp_client.create_or_derive_api_creds()

        # Create authenticated client
        _client = ClobClient(
            POLYMARKET_HOST,
            key=POLYMARKET_PRIVATE_KEY,
            chain_id=POLYMARKET_CHAIN_ID,
            creds=api_creds,
            signature_type=0,  # EOA wallet
            funder=POLYMARKET_FUNDER or None,
        )

        logger.info("Polymarket CLOB client initialized (host: %s)", POLYMARKET_HOST)
        return _client

    except ImportError:
        logger.warning("py-clob-client not installed — pip install py-clob-client")
        return None
    except Exception as e:
        logger.error("Polymarket client init failed: %s", e)
        return None


def get_api_client():
    """Get a read-only client for market data (no auth needed)."""
    try:
        from py_clob_client.client import ClobClient
        return ClobClient(POLYMARKET_HOST, chain_id=POLYMARKET_CHAIN_ID)
    except ImportError:
        return None
    except Exception as e:
        logger.error("Polymarket read client failed: %s", e)
        return None
