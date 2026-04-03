"""Bloom-Walters Kelly position sizing — identical math to BetByGPT."""

from src.config import FILTERS


def kelly_criterion(confidence: float, rr_ratio: float) -> float:
    """
    Calculate Kelly percentage.

    Trading equivalent of BetByGPT's Kelly:
        p = confidence (e.g. 0.60)
        b = reward / risk ratio (e.g. takeProfit distance / stopLoss distance)
        Kelly% = (p * b - (1 - p)) / b

    Returns the raw Kelly fraction (before shrinkage/caps).
    """
    p = confidence / 100.0
    b = rr_ratio
    q = 1 - p

    if b <= 0:
        return 0.0

    kelly = (p * b - q) / b

    # Kelly can be negative (no edge) — clamp to 0
    return max(kelly, 0.0)


def size_position(
    confidence: float,
    rr_ratio: float,
    bankroll: float,
    entry_price: float,
    stop_loss: float,
) -> dict:
    """
    Calculate position size using Bloom-Walters Kelly.

    Returns dict with kelly_pct, shrunk_kelly, dollar_risk, shares, position_value.
    """
    raw_kelly = kelly_criterion(confidence, rr_ratio)
    edge_shrinkage = FILTERS["edge_shrinkage"]
    max_risk_pct = FILTERS["max_position_pct"]

    # Apply edge shrinkage (assume 50% overconfident)
    shrunk_kelly = raw_kelly * edge_shrinkage

    # Cap at max position percentage
    final_pct = min(shrunk_kelly, max_risk_pct)

    # Dollar amount at risk
    dollar_risk = bankroll * final_pct

    # Risk per share (distance to stop)
    risk_per_share = abs(entry_price - stop_loss)
    if risk_per_share == 0:
        return {
            "kelly_pct": raw_kelly * 100,
            "shrunk_kelly_pct": shrunk_kelly * 100,
            "final_risk_pct": final_pct * 100,
            "dollar_risk": 0.0,
            "shares": 0,
            "position_value": 0.0,
        }

    shares = int(dollar_risk / risk_per_share)
    position_value = shares * entry_price

    return {
        "kelly_pct": round(raw_kelly * 100, 2),
        "shrunk_kelly_pct": round(shrunk_kelly * 100, 2),
        "final_risk_pct": round(final_pct * 100, 2),
        "dollar_risk": round(dollar_risk, 2),
        "shares": shares,
        "position_value": round(position_value, 2),
    }
