"""Trade filter — confidence threshold, min R:R, ATR validation, portfolio limits, circuit breakers."""

from src.config import FILTERS
from src.tracking.trade_logger import (
    count_open_positions,
    get_daily_pnl,
    get_bankroll,
    has_open_position,
)


def apply_filters(
    ticker: str,
    confidence: float,
    rr_ratio: float,
    direction: str,
    sector: str = "Unknown",
    atr: float = None,
    entry: float = None,
    stop_loss: float = None,
) -> tuple[bool, str | None, dict]:
    """
    Apply all trade filters. Returns (passed, reason_if_filtered, context).

    Context dict includes cb_size_multiplier and warnings for downstream use.
    Claude proposes, rules dispose.
    """
    # 0. Circuit breaker check (first gate — halts everything)
    from src.risk.circuit_breakers import check_circuit_breakers
    cb_status = check_circuit_breakers()
    if not cb_status["trading_allowed"]:
        reasons = "; ".join(cb_status["reasons"])
        return False, f"Circuit breaker: {reasons}", {"cb_size_multiplier": 0.0, "warnings": cb_status["warnings"]}

    ctx = {
        "cb_size_multiplier": cb_status["size_multiplier"],
        "warnings": cb_status["warnings"],
    }

    # 1. One position per ticker
    if has_open_position(ticker):
        return False, f"Already have open position in {ticker}", ctx

    # 2. Minimum confidence
    if confidence < FILTERS["min_confidence"]:
        return False, f"Confidence {confidence}% below minimum {FILTERS['min_confidence']}%", ctx

    # 3. Minimum risk:reward
    if rr_ratio < FILTERS["min_rr_ratio"]:
        return False, f"R:R {rr_ratio:.2f} below minimum {FILTERS['min_rr_ratio']}", ctx

    # 3b. ATR-based stop validation — reject if stop is inside 0.5x ATR (noise)
    if atr and atr > 0 and entry and stop_loss:
        stop_distance = abs(entry - stop_loss)
        atr_multiple = stop_distance / atr
        if atr_multiple < 0.5:
            return False, f"Stop too tight ({atr_multiple:.1f}x ATR, min 0.5x)", ctx

    # 4. Max open positions
    open_count = count_open_positions()
    if open_count >= FILTERS["max_open_positions"]:
        return False, f"At max positions ({open_count}/{FILTERS['max_open_positions']})", ctx

    # 5. Daily loss limit
    bankroll = get_bankroll()
    daily_pnl = get_daily_pnl()
    max_daily_loss = bankroll * FILTERS["max_daily_loss_pct"]
    if daily_pnl < 0 and abs(daily_pnl) >= max_daily_loss:
        return False, f"Daily loss limit hit (${daily_pnl:.2f} / -${max_daily_loss:.2f})", ctx

    return True, None, ctx
