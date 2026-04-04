"""Polymarket data collector — fetch markets, events, prices, orderbooks via Gamma API."""

import logging
from datetime import datetime, timezone

import requests

from src.config import POLYMARKET_GAMMA_HOST, POLYMARKET_HOST

logger = logging.getLogger(__name__)

# Gamma API (public market data — no auth needed)
GAMMA_BASE = POLYMARKET_GAMMA_HOST
# CLOB API (orderbook data)
CLOB_BASE = POLYMARKET_HOST


def _gamma_get(endpoint: str, params: dict = None) -> dict | list | None:
    """GET request to Gamma API."""
    try:
        resp = requests.get(f"{GAMMA_BASE}{endpoint}", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error("Gamma API error (%s): %s", endpoint, e)
        return None


def _clob_get(endpoint: str, params: dict = None) -> dict | list | None:
    """GET request to CLOB API (public endpoints)."""
    try:
        resp = requests.get(f"{CLOB_BASE}{endpoint}", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error("CLOB API error (%s): %s", endpoint, e)
        return None


def list_markets(
    limit: int = 50,
    active: bool = True,
    closed: bool = False,
    order: str = "volume24hr",
    ascending: bool = False,
) -> list[dict]:
    """Fetch markets from Gamma API with filtering."""
    params = {
        "limit": limit,
        "active": str(active).lower(),
        "closed": str(closed).lower(),
        "order": order,
        "ascending": str(ascending).lower(),
    }
    result = _gamma_get("/markets", params)
    return result if isinstance(result, list) else []


def get_market(condition_id: str) -> dict | None:
    """Get a single market by condition ID."""
    return _gamma_get(f"/markets/{condition_id}")


def get_market_by_slug(slug: str) -> dict | None:
    """Get a market by its URL slug."""
    markets = _gamma_get("/markets", {"slug": slug})
    if markets and isinstance(markets, list) and len(markets) > 0:
        return markets[0]
    return None


def list_events(
    limit: int = 50,
    active: bool = True,
    closed: bool = False,
    order: str = "volume24hr",
    ascending: bool = False,
    tag: str = None,
) -> list[dict]:
    """Fetch events from Gamma API."""
    params = {
        "limit": limit,
        "active": str(active).lower(),
        "closed": str(closed).lower(),
        "order": order,
        "ascending": str(ascending).lower(),
    }
    if tag:
        params["tag"] = tag
    result = _gamma_get("/events", params)
    return result if isinstance(result, list) else []


def get_event(event_id: str) -> dict | None:
    """Get a single event by ID."""
    return _gamma_get(f"/events/{event_id}")


def get_event_by_slug(slug: str) -> dict | None:
    """Get an event by URL slug."""
    events = _gamma_get("/events", {"slug": slug})
    if events and isinstance(events, list) and len(events) > 0:
        return events[0]
    return None


def get_orderbook(token_id: str) -> dict | None:
    """Get the orderbook for a token from the CLOB."""
    return _clob_get("/book", {"token_id": token_id})


def get_midpoint(token_id: str) -> float | None:
    """Get midpoint price for a token."""
    result = _clob_get("/midpoint", {"token_id": token_id})
    if result and "mid" in result:
        return float(result["mid"])
    return None


def get_spread(token_id: str) -> dict | None:
    """Get bid/ask spread for a token."""
    return _clob_get("/spread", {"token_id": token_id})


def get_last_trade_price(token_id: str) -> float | None:
    """Get last trade price for a token."""
    result = _clob_get("/last-trade-price", {"token_id": token_id})
    if result and "price" in result:
        return float(result["price"])
    return None


def get_price_history(token_id: str, interval: str = "1d", fidelity: int = 60) -> list[dict]:
    """Get price history for a token. interval: 1d, 1w, 1m, 3m, all. fidelity: seconds."""
    result = _clob_get("/prices-history", {
        "tokenID": token_id,
        "interval": interval,
        "fidelity": fidelity,
    })
    if result and "history" in result:
        return result["history"]
    return result if isinstance(result, list) else []


def collect_market_context(market: dict) -> dict:
    """
    Collect full context for a Polymarket market for Claude analysis.

    Args:
        market: Market dict from Gamma API (must include tokens, question, etc.)

    Returns:
        Dict with all data Claude needs for analysis.
    """
    question = market.get("question", "Unknown")
    description = market.get("description", "")
    end_date = market.get("endDate", "")
    category = market.get("category", "Unknown")
    tags = market.get("tags", [])

    # Extract token IDs
    tokens = market.get("tokens", [])
    yes_token = None
    no_token = None
    for t in tokens:
        outcome = t.get("outcome", "").upper()
        if outcome == "YES":
            yes_token = t
        elif outcome == "NO":
            no_token = t

    if not yes_token:
        return {"error": "No YES token found", "market": market}

    yes_token_id = yes_token.get("token_id", "")
    yes_price = float(yes_token.get("price", 0))

    # Get orderbook depth
    orderbook = get_orderbook(yes_token_id) if yes_token_id else None
    bid_depth = 0
    ask_depth = 0
    best_bid = 0
    best_ask = 1
    spread = 0

    if orderbook:
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])
        if bids:
            best_bid = float(bids[0].get("price", 0))
            bid_depth = sum(float(b.get("size", 0)) for b in bids[:5])
        if asks:
            best_ask = float(asks[0].get("price", 1))
            ask_depth = sum(float(a.get("size", 0)) for a in asks[:5])
        spread = best_ask - best_bid

    # Get price history
    price_history = get_price_history(yes_token_id, interval="1w", fidelity=3600)

    # Volume data
    volume_24h = float(market.get("volume24hr", 0))
    total_volume = float(market.get("volume", 0))
    liquidity = float(market.get("liquidity", 0))

    # Price movement analysis
    price_change_24h = None
    price_trend = "unknown"
    if price_history and len(price_history) >= 2:
        recent_prices = [float(p.get("p", p.get("price", 0))) for p in price_history[-24:] if p]
        if len(recent_prices) >= 2:
            price_change_24h = recent_prices[-1] - recent_prices[0]
            if len(recent_prices) >= 6:
                first_half = sum(recent_prices[:len(recent_prices)//2]) / (len(recent_prices)//2)
                second_half = sum(recent_prices[len(recent_prices)//2:]) / (len(recent_prices) - len(recent_prices)//2)
                if second_half > first_half + 0.02:
                    price_trend = "rising"
                elif second_half < first_half - 0.02:
                    price_trend = "falling"
                else:
                    price_trend = "stable"

    return {
        "question": question,
        "description": description,
        "category": category,
        "tags": tags,
        "end_date": end_date,
        "yes_price": yes_price,
        "no_price": 1 - yes_price,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "bid_depth_5": bid_depth,
        "ask_depth_5": ask_depth,
        "volume_24h": volume_24h,
        "total_volume": total_volume,
        "liquidity": liquidity,
        "price_change_24h": price_change_24h,
        "price_trend": price_trend,
        "price_history_7d": price_history[-168:] if price_history else [],  # Last 7 days hourly
        "yes_token_id": yes_token_id,
        "no_token_id": no_token.get("token_id", "") if no_token else "",
        "condition_id": market.get("conditionId", market.get("condition_id", "")),
        "market_slug": market.get("slug", ""),
        "neg_risk": market.get("negRisk", False),
        "tick_size": market.get("minimum_tick_size", "0.01"),
    }
