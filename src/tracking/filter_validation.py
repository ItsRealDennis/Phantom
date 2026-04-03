"""Filter validation — track filtered signal outcomes to measure filter effectiveness.

The critical question: "Are my filters improving edge, or filtering out winners?"
If filtered signals have HIGHER win rate than passed → filters are broken.
If filtered signals have LOWER win rate → filters are working.
"""

import logging
from datetime import datetime

from src.config import FILTER_VALIDATION, STRATEGY_MAX_HOLD, TRADE_EXPIRY_DAYS
from src.tracking.trade_logger import (
    get_connection,
    get_filtered_signals,
    settle_filtered_trade,
)

logger = logging.getLogger(__name__)


def settle_filtered_signals() -> list[dict]:
    """
    Check filtered signals against their proposed entry/stop/target.
    Uses same logic as settler but for hypothetical outcomes.
    Updates status to 'filtered_won' or 'filtered_lost'.
    """
    if not FILTER_VALIDATION["enabled"]:
        return []

    from src.automation.settler import get_price_range_since

    filtered = get_filtered_signals()
    settlements = []

    for signal in filtered:
        entry = signal["entry_price"]
        stop = signal["stop_loss"]
        target = signal["take_profit"]
        direction = signal["direction"]

        # Skip signals with no valid levels (e.g. circuit breaker filtered with 0 entry)
        if not entry or not stop or not target or entry == 0:
            continue

        try:
            price_range = get_price_range_since(
                signal["ticker"], signal["created_at"]
            )
        except Exception as e:
            logger.debug("Price fetch for filtered %s failed: %s", signal["ticker"], e)
            continue

        # Check if stop or target was hit
        outcome = _check_filtered_outcome(signal, price_range)
        if outcome is None:
            # Check expiry
            created = datetime.fromisoformat(signal["created_at"])
            max_hold_hours = STRATEGY_MAX_HOLD.get(
                signal["strategy"], TRADE_EXPIRY_DAYS * 24
            )
            age_hours = (datetime.now() - created).total_seconds() / 3600
            if age_hours <= max_hold_hours:
                continue  # Still within hold period
            # Expired — compute hypothetical P&L at current price
            current = price_range["current"]
            if direction == "LONG":
                hypo_pnl = current - entry
            else:
                hypo_pnl = entry - current
            status = "filtered_won" if hypo_pnl > 0 else "filtered_lost"
            notes = f"Expired at ${current:.2f}"
        else:
            status, hypo_pnl, notes = outcome

        try:
            settle_filtered_trade(signal["id"], status, round(hypo_pnl, 2), notes)
            settlements.append({
                "id": signal["id"],
                "ticker": signal["ticker"],
                "status": status,
                "hypo_pnl": round(hypo_pnl, 2),
            })
            logger.info(
                "Filter validation: %s #%d → %s (hypo P&L: $%.2f/share)",
                signal["ticker"], signal["id"], status, hypo_pnl,
            )
        except Exception as e:
            logger.debug("Failed to settle filtered #%d: %s", signal["id"], e)

    if settlements:
        logger.info("Filter validation: %d signals settled", len(settlements))

    return settlements


def _check_filtered_outcome(signal: dict, price_range: dict) -> tuple[str, float, str] | None:
    """Check if a filtered signal's hypothetical trade hit stop or target."""
    direction = signal["direction"]
    entry = signal["entry_price"]
    stop = signal["stop_loss"]
    target = signal["take_profit"]

    # Per-share P&L (no position sizing for filtered signals)
    if direction == "LONG":
        if price_range["low"] <= stop:
            pnl = stop - entry
            return ("filtered_lost", pnl, f"Stop hit at ${stop:.2f}")
        if price_range["high"] >= target:
            pnl = target - entry
            return ("filtered_won", pnl, f"Target hit at ${target:.2f}")
    elif direction == "SHORT":
        if price_range["high"] >= stop:
            pnl = entry - stop
            return ("filtered_lost", pnl, f"Stop hit at ${stop:.2f}")
        if price_range["low"] <= target:
            pnl = entry - target
            return ("filtered_won", pnl, f"Target hit at ${target:.2f}")

    return None


def get_filter_alpha() -> dict:
    """
    Compute filter alpha = passed_win_rate - filtered_win_rate.
    Positive alpha means filters are adding value.
    """
    conn = get_connection()

    # Passed signals win rate
    passed = conn.execute(
        """
        SELECT COUNT(*) as total,
               SUM(CASE WHEN status = 'won' THEN 1 ELSE 0 END) as wins
        FROM signals
        WHERE passed_filter = 1 AND status IN ('won', 'lost', 'stopped')
        """
    ).fetchone()

    # Filtered signals win rate
    filtered = conn.execute(
        """
        SELECT COUNT(*) as total,
               SUM(CASE WHEN status = 'filtered_won' THEN 1 ELSE 0 END) as wins
        FROM signals
        WHERE passed_filter = 0 AND status IN ('filtered_won', 'filtered_lost')
        """
    ).fetchone()

    conn.close()

    passed_total = passed["total"] or 0
    passed_wins = passed["wins"] or 0
    filtered_total = filtered["total"] or 0
    filtered_wins = filtered["wins"] or 0

    passed_wr = (passed_wins / passed_total * 100) if passed_total > 0 else 0
    filtered_wr = (filtered_wins / filtered_total * 100) if filtered_total > 0 else 0
    alpha = passed_wr - filtered_wr

    alert = (
        FILTER_VALIDATION["alert_negative_alpha"]
        and alpha < 0
        and filtered_total >= 10
    )

    if alert:
        logger.warning(
            "FILTER ALPHA NEGATIVE: passed %.1f%% vs filtered %.1f%% — filters may be hurting!",
            passed_wr, filtered_wr,
        )

    return {
        "passed_win_rate": round(passed_wr, 1),
        "filtered_win_rate": round(filtered_wr, 1),
        "filter_alpha": round(alpha, 1),
        "passed_count": passed_total,
        "filtered_count": filtered_total,
        "alert": alert,
    }


def get_filter_validation_detail() -> dict:
    """
    Detailed breakdown: per-filter-reason outcomes.
    Shows which filter reasons are correctly filtering losers vs removing winners.
    """
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT filter_reason, status, COUNT(*) as cnt
        FROM signals
        WHERE passed_filter = 0 AND status IN ('filtered_won', 'filtered_lost')
        GROUP BY filter_reason, status
        """
    ).fetchall()
    conn.close()

    # Group by filter reason
    reasons: dict[str, dict] = {}
    for row in rows:
        reason = row["filter_reason"] or "Unknown"
        if reason not in reasons:
            reasons[reason] = {"total": 0, "won": 0, "lost": 0}
        reasons[reason]["total"] += row["cnt"]
        if row["status"] == "filtered_won":
            reasons[reason]["won"] += row["cnt"]
        else:
            reasons[reason]["lost"] += row["cnt"]

    # Compute win rates
    detail = []
    for reason, data in reasons.items():
        wr = (data["won"] / data["total"] * 100) if data["total"] > 0 else 0
        detail.append({
            "filter_reason": reason,
            "total": data["total"],
            "would_have_won": data["won"],
            "would_have_lost": data["lost"],
            "hypothetical_win_rate": round(wr, 1),
        })

    # Sort by win rate descending (worst filters first — they filter out winners)
    detail.sort(key=lambda x: x["hypothetical_win_rate"], reverse=True)

    return {"by_reason": detail}
