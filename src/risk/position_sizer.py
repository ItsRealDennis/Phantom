"""Bloom-Walters Kelly position sizing — identical math to BetByGPT.

Phase 2 additions: drawdown scaling, VIX-based vol scaling, strategy decay.
"""

import logging

from src.config import FILTERS, POSITION_SIZER_V2

logger = logging.getLogger(__name__)


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
    cb_size_multiplier: float = 1.0,
    strategy: str | None = None,
) -> dict:
    """
    Calculate position size using Bloom-Walters Kelly.
    Caps both risk AND total position value to prevent oversized orders.

    Phase 2: applies drawdown, VIX, and strategy decay multipliers.
    """
    raw_kelly = kelly_criterion(confidence, rr_ratio)
    edge_shrinkage = FILTERS["edge_shrinkage"]
    max_risk_pct = FILTERS["max_position_pct"]

    shrunk_kelly = raw_kelly * edge_shrinkage
    final_pct = min(shrunk_kelly, max_risk_pct)

    # Phase 2: regime-aware scaling
    drawdown_mult = _get_drawdown_multiplier(bankroll)
    vix_mult = _get_vix_multiplier()
    strategy_mult = _get_strategy_decay_multiplier(strategy) if strategy else 1.0
    combined_mult = min(cb_size_multiplier, drawdown_mult, vix_mult, strategy_mult)

    final_pct *= combined_mult

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
            "combined_multiplier": round(combined_mult, 3),
            "multiplier_breakdown": {
                "circuit_breaker": round(cb_size_multiplier, 3),
                "drawdown": round(drawdown_mult, 3),
                "vix": round(vix_mult, 3),
                "strategy_decay": round(strategy_mult, 3),
            },
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
        "combined_multiplier": round(combined_mult, 3),
        "multiplier_breakdown": {
            "circuit_breaker": round(cb_size_multiplier, 3),
            "drawdown": round(drawdown_mult, 3),
            "vix": round(vix_mult, 3),
            "strategy_decay": round(strategy_mult, 3),
        },
    }


def _get_drawdown_multiplier(bankroll: float) -> float:
    """Lookup current drawdown tier and return sizing multiplier."""
    from src.risk.circuit_breakers import _get_current_drawdown
    try:
        dd_pct, _, _ = _get_current_drawdown()
    except Exception:
        return 1.0

    # Walk tiers from most severe to least
    for tier_dd, tier_mult in sorted(POSITION_SIZER_V2["drawdown_scale"], reverse=True):
        if dd_pct >= tier_dd:
            return tier_mult
    return 1.0


def _get_vix_multiplier() -> float:
    """Compute VIX-based sizing multiplier."""
    from src.risk.circuit_breakers import get_vix_price
    try:
        vix = get_vix_price()
    except Exception:
        return 1.0

    threshold = POSITION_SIZER_V2["vix_scale_threshold"]
    factor = POSITION_SIZER_V2["vix_scale_factor"]

    if vix <= threshold:
        return 1.0

    # Reduce by factor per VIX point above threshold
    reduction = (vix - threshold) * factor
    return max(0.10, 1.0 - reduction)  # Floor at 10%


def _get_strategy_decay_multiplier(strategy: str) -> float:
    """If a strategy's rolling win rate is below all-time, scale down."""
    if not POSITION_SIZER_V2["strategy_decay_enabled"]:
        return 1.0

    from src.tracking.trade_logger import get_connection

    conn = get_connection()

    # All-time win rate for this strategy
    all_time = conn.execute(
        """
        SELECT COUNT(*) as total,
               SUM(CASE WHEN status = 'won' THEN 1 ELSE 0 END) as wins
        FROM signals
        WHERE strategy = ? AND status IN ('won', 'lost', 'stopped') AND passed_filter = 1
        """,
        (strategy,),
    ).fetchone()

    # Rolling win rate (last 20)
    recent = conn.execute(
        """
        SELECT status FROM signals
        WHERE strategy = ? AND status IN ('won', 'lost', 'stopped') AND passed_filter = 1
        ORDER BY settled_at DESC
        LIMIT 20
        """,
        (strategy,),
    ).fetchall()
    conn.close()

    if not all_time or all_time["total"] < 10 or len(recent) < 10:
        return 1.0  # Not enough data

    all_time_wr = all_time["wins"] / all_time["total"]
    rolling_wins = sum(1 for r in recent if r["status"] == "won")
    rolling_wr = rolling_wins / len(recent)

    if all_time_wr == 0:
        return 1.0

    # Ratio of rolling to all-time
    ratio = rolling_wr / all_time_wr
    if ratio >= 0.8:
        return 1.0  # Healthy — no decay
    elif ratio >= 0.5:
        return 0.75  # Mild decay
    else:
        return 0.50  # Significant decay


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
