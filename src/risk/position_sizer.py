"""Bloom-Walters Kelly position sizing — identical math to BetByGPT."""

from src.config import FILTERS


# Max % of bankroll for a single position's total value (not just risk)
MAX_POSITION_VALUE_PCT = 0.10  # 10% of bankroll per position


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
    Caps both risk AND total position value to prevent oversized orders.
    """
    raw_kelly = kelly_criterion(confidence, rr_ratio)
    edge_shrinkage = FILTERS["edge_shrinkage"]
    max_risk_pct = FILTERS["max_position_pct"]

    shrunk_kelly = raw_kelly * edge_shrinkage
    final_pct = min(shrunk_kelly, max_risk_pct)

    dollar_risk = bankroll * final_pct

    risk_per_share = abs(entry_price - stop_loss)
    if risk_per_share == 0 or entry_price == 0:
        return {
            "kelly_pct": raw_kelly * 100,
            "shrunk_kelly_pct": shrunk_kelly * 100,
            "final_risk_pct": final_pct * 100,
            "dollar_risk": 0.0,
            "shares": 0,
            "position_value": 0.0,
        }

    # Shares from risk budget
    shares_from_risk = int(dollar_risk / risk_per_share)

    # Shares from position value cap (10% of bankroll)
    max_position_value = bankroll * MAX_POSITION_VALUE_PCT
    shares_from_value = int(max_position_value / entry_price)

    # Take the smaller of the two
    shares = min(shares_from_risk, shares_from_value)
    shares = max(shares, 1)  # At least 1 share

    position_value = shares * entry_price
    actual_risk = shares * risk_per_share

    return {
        "kelly_pct": round(raw_kelly * 100, 2),
        "shrunk_kelly_pct": round(shrunk_kelly * 100, 2),
        "final_risk_pct": round(final_pct * 100, 2),
        "dollar_risk": round(actual_risk, 2),
        "shares": shares,
        "position_value": round(position_value, 2),
    }


def adjust_stop_for_atr(
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    direction: str,
    atr: float,
) -> dict:
    """
    Clamp stop loss to 1x-3x ATR from entry.
    Recalculates take_profit to maintain original R:R ratio.
    """
    if atr <= 0:
        return {
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "stop_adjusted": False,
            "atr_multiple": 0,
        }

    original_stop_dist = abs(entry_price - stop_loss)
    original_tp_dist = abs(take_profit - entry_price)
    original_rr = original_tp_dist / original_stop_dist if original_stop_dist > 0 else 2.0

    min_stop = 1.0 * atr
    max_stop = 3.0 * atr

    adjusted_stop_dist = max(min(original_stop_dist, max_stop), min_stop)

    if direction == "LONG":
        new_stop = entry_price - adjusted_stop_dist
        new_tp = entry_price + adjusted_stop_dist * original_rr
    else:
        new_stop = entry_price + adjusted_stop_dist
        new_tp = entry_price - adjusted_stop_dist * original_rr

    return {
        "stop_loss": round(new_stop, 2),
        "take_profit": round(new_tp, 2),
        "stop_adjusted": abs(adjusted_stop_dist - original_stop_dist) > 0.01,
        "atr_multiple": round(adjusted_stop_dist / atr, 2),
    }
