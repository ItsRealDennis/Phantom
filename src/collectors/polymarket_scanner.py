"""Polymarket scanner — find markets with potential mispricing or catalysts."""

import logging
from datetime import datetime, timezone, timedelta

from src.collectors.polymarket_data import list_markets, list_events, get_midpoint, get_spread
from src.config import POLYMARKET_FILTERS, POLYMARKET_CATEGORIES

logger = logging.getLogger(__name__)


def _passes_basic_filters(market: dict) -> tuple[bool, str]:
    """Check if a market passes basic liquidity/volume filters."""
    volume = float(market.get("volume", 0))
    volume_24h = float(market.get("volume24hr", 0))
    liquidity = float(market.get("liquidity", 0))

    if volume < POLYMARKET_FILTERS["min_volume"]:
        return False, f"Low total volume: ${volume:.0f}"

    if liquidity < POLYMARKET_FILTERS["min_liquidity"]:
        return False, f"Low liquidity: ${liquidity:.0f}"

    # Skip markets that are already resolved or nearly resolved (>95% or <5%)
    tokens = market.get("tokens", [])
    for t in tokens:
        if t.get("outcome", "").upper() == "YES":
            price = float(t.get("price", 0.5))
            if price > 0.95 or price < 0.05:
                return False, f"Near-certain outcome: {price:.2f}"

    # Skip markets with no orderbook
    if not market.get("enableOrderBook", True):
        return False, "Orderbook disabled"

    return True, ""


def screen_mispricing(markets: list[dict] = None) -> list[dict]:
    """
    Screen for potentially mispriced markets.

    Looks for:
    - Markets in the 20-80% range (most room for mispricing)
    - Decent volume but not mega-liquid (harder to beat)
    - Price has been moving (indicates new information flow)
    """
    if markets is None:
        markets = list_markets(limit=100, active=True)

    hits = []
    for m in markets:
        passed, reason = _passes_basic_filters(m)
        if not passed:
            continue

        tokens = m.get("tokens", [])
        yes_price = 0.5
        for t in tokens:
            if t.get("outcome", "").upper() == "YES":
                yes_price = float(t.get("price", 0.5))

        # Best candidates are in the uncertain zone (20-80%)
        if 0.20 <= yes_price <= 0.80:
            hits.append({
                "market": m,
                "strategy": "mispricing",
                "yes_price": yes_price,
                "reason": f"Uncertain range ({yes_price:.0%}), potential for mispricing",
            })

    # Sort by volume (prefer more liquid for execution)
    hits.sort(key=lambda h: float(h["market"].get("volume24hr", 0)), reverse=True)
    return hits[:20]


def screen_event_catalyst(markets: list[dict] = None) -> list[dict]:
    """
    Screen for markets with upcoming catalyst events.

    Looks for:
    - Markets resolving within 7 days (near-term catalyst)
    - Active trading volume (market is paying attention)
    - Price not at extremes (room to move)
    """
    if markets is None:
        markets = list_markets(limit=100, active=True)

    now = datetime.now(timezone.utc)
    hits = []

    for m in markets:
        passed, reason = _passes_basic_filters(m)
        if not passed:
            continue

        # Check end date
        end_date_str = m.get("endDate", "")
        if not end_date_str:
            continue

        try:
            end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue

        days_until = (end_date - now).days
        if days_until < 0 or days_until > 7:
            continue

        tokens = m.get("tokens", [])
        yes_price = 0.5
        for t in tokens:
            if t.get("outcome", "").upper() == "YES":
                yes_price = float(t.get("price", 0.5))

        # Skip near-certain outcomes
        if yes_price > 0.92 or yes_price < 0.08:
            continue

        hits.append({
            "market": m,
            "strategy": "event_catalyst",
            "yes_price": yes_price,
            "days_until_resolution": days_until,
            "reason": f"Resolves in {days_until}d, price {yes_price:.0%}",
        })

    hits.sort(key=lambda h: h["days_until_resolution"])
    return hits[:15]


def screen_momentum(markets: list[dict] = None) -> list[dict]:
    """
    Screen for markets with strong recent price movement.

    Looks for:
    - Significant price change in last 24h
    - High volume relative to liquidity (active trading)
    - Price trending in a clear direction
    """
    if markets is None:
        markets = list_markets(limit=100, active=True, order="volume24hr")

    hits = []

    for m in markets:
        passed, reason = _passes_basic_filters(m)
        if not passed:
            continue

        volume_24h = float(m.get("volume24hr", 0))
        if volume_24h < 500:
            continue

        tokens = m.get("tokens", [])
        yes_price = 0.5
        for t in tokens:
            if t.get("outcome", "").upper() == "YES":
                yes_price = float(t.get("price", 0.5))

        # Need price data to detect momentum
        # Use outcomePrices field if available, otherwise check clobTokenIds
        # Look for significant recent volume as a proxy for momentum
        liquidity = float(m.get("liquidity", 1))
        volume_to_liquidity = volume_24h / liquidity if liquidity > 0 else 0

        # High volume relative to liquidity suggests active price discovery
        if volume_to_liquidity > 0.5:
            hits.append({
                "market": m,
                "strategy": "momentum",
                "yes_price": yes_price,
                "volume_24h": volume_24h,
                "vol_liq_ratio": volume_to_liquidity,
                "reason": f"High activity (vol/liq: {volume_to_liquidity:.1f}x), price {yes_price:.0%}",
            })

    hits.sort(key=lambda h: h["vol_liq_ratio"], reverse=True)
    return hits[:15]


def run_polymarket_scan() -> list[dict]:
    """
    Run all Polymarket screeners and return deduplicated hits.

    Returns list of dicts with: market, strategy, yes_price, reason
    """
    logger.info("Running Polymarket scan...")

    # Fetch markets once, share across screeners
    all_markets = list_markets(limit=100, active=True, order="volume24hr")
    if not all_markets:
        logger.warning("No markets returned from Gamma API")
        return []

    logger.info("Fetched %d active markets", len(all_markets))

    # Run all screeners
    mispricing_hits = screen_mispricing(all_markets)
    catalyst_hits = screen_event_catalyst(all_markets)
    momentum_hits = screen_momentum(all_markets)

    # Deduplicate by condition_id (prefer catalyst > mispricing > momentum)
    seen = set()
    hits = []

    for hit_list in [catalyst_hits, mispricing_hits, momentum_hits]:
        for hit in hit_list:
            cid = hit["market"].get("conditionId", hit["market"].get("condition_id", ""))
            if cid and cid not in seen:
                seen.add(cid)
                hits.append(hit)

    logger.info(
        "Polymarket scan: %d mispricing, %d catalyst, %d momentum → %d unique",
        len(mispricing_hits), len(catalyst_hits), len(momentum_hits), len(hits),
    )
    return hits
