"""Circuit breakers — automated kill switches that halt or reduce trading.

Checks run BEFORE any new signal is approved. If tripped, the system pauses
signal generation entirely or reduces position sizes.
"""

import logging
from datetime import datetime, timedelta

import yfinance as yf

from src.config import CIRCUIT_BREAKERS, STARTING_BANKROLL
from src.tracking.trade_logger import get_connection, get_bankroll, get_daily_pnl

logger = logging.getLogger(__name__)

# VIX cache to avoid hammering yfinance
_vix_cache: dict = {"value": None, "fetched_at": None}
_VIX_CACHE_TTL = 300  # 5 minutes


def check_circuit_breakers() -> dict:
    """
    Run all circuit breaker checks.

    Returns {
        "trading_allowed": bool,
        "size_multiplier": float (0.0 to 1.0),
        "reasons": list[str],      # why trading is halted
        "warnings": list[str],     # non-blocking warnings
    }
    """
    reasons = []
    warnings = []
    size_multiplier = 1.0

    # 1. Daily loss check
    halted, reason = _check_daily_loss()
    if halted:
        reasons.append(reason)

    # 2. Consecutive losses
    halted, reason = _check_consecutive_losses()
    if halted:
        reasons.append(reason)

    # 3. Drawdown tier
    dd_mult, reason = _check_drawdown_tier()
    if dd_mult == 0.0:
        reasons.append(reason)
    elif dd_mult < 1.0:
        size_multiplier = min(size_multiplier, dd_mult)
        warnings.append(reason)

    # 4. VIX check
    halted, vix_mult, reason = _check_vix()
    if halted:
        reasons.append(reason)
    elif vix_mult < 1.0:
        size_multiplier = min(size_multiplier, vix_mult)
        if reason:
            warnings.append(reason)

    # 5. Rolling win rate
    halted, reason = _check_rolling_win_rate()
    if halted:
        reasons.append(reason)

    trading_allowed = len(reasons) == 0

    # Log any new trips
    if not trading_allowed:
        for reason in reasons:
            logger.warning("Circuit breaker TRIPPED: %s", reason)

    return {
        "trading_allowed": trading_allowed,
        "size_multiplier": size_multiplier if trading_allowed else 0.0,
        "reasons": reasons,
        "warnings": warnings,
    }


def _check_daily_loss() -> tuple[bool, str | None]:
    """Check if daily realized loss exceeds threshold."""
    bankroll = get_bankroll()
    daily_pnl = get_daily_pnl()
    max_loss = bankroll * CIRCUIT_BREAKERS["daily_loss_pause_pct"]

    if daily_pnl < 0 and abs(daily_pnl) >= max_loss:
        reason = f"Daily loss ${daily_pnl:.2f} exceeds -{CIRCUIT_BREAKERS['daily_loss_pause_pct']*100:.0f}% limit (${-max_loss:.2f})"
        log_circuit_breaker_event("daily_loss", abs(daily_pnl), max_loss, "pause")
        return True, reason
    return False, None


def _check_consecutive_losses() -> tuple[bool, str | None]:
    """Check last N trades for consecutive losses."""
    limit = CIRCUIT_BREAKERS["consecutive_loss_pause"]
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT status FROM signals
        WHERE status IN ('won', 'lost', 'stopped') AND passed_filter = 1
        ORDER BY settled_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()

    if len(rows) < limit:
        return False, None

    all_losses = all(r["status"] in ("lost", "stopped") for r in rows)
    if all_losses:
        reason = f"{limit} consecutive losses — pausing trading"
        log_circuit_breaker_event("consecutive_losses", float(limit), float(limit), "pause")
        return True, reason
    return False, None


def _check_drawdown_tier() -> tuple[float, str | None]:
    """Check current drawdown and return size multiplier per tier."""
    dd_pct, current, peak = _get_current_drawdown()

    # Walk through tiers from most severe to least
    for tier_dd, tier_mult in sorted(CIRCUIT_BREAKERS["drawdown_tiers"], reverse=True):
        if dd_pct >= tier_dd:
            if tier_mult == 0.0:
                reason = f"Drawdown {dd_pct*100:.1f}% exceeds {tier_dd*100:.0f}% — FULL STOP"
                log_circuit_breaker_event("drawdown", dd_pct, tier_dd, "full_stop")
                return 0.0, reason
            else:
                reason = f"Drawdown {dd_pct*100:.1f}% exceeds {tier_dd*100:.0f}% — sizing at {tier_mult*100:.0f}%"
                return tier_mult, reason

    return 1.0, None


def _check_vix() -> tuple[bool, float, str | None]:
    """Fetch VIX and check against thresholds. Returns (halt, multiplier, reason)."""
    try:
        vix = get_vix_price()
    except Exception as e:
        logger.debug("VIX fetch failed: %s — skipping VIX check", e)
        return False, 1.0, None

    if vix >= CIRCUIT_BREAKERS["vix_halt"]:
        reason = f"VIX at {vix:.1f} exceeds halt threshold ({CIRCUIT_BREAKERS['vix_halt']:.0f}) — HALTING"
        log_circuit_breaker_event("vix", vix, CIRCUIT_BREAKERS["vix_halt"], "halt")
        return True, 0.0, reason

    if vix >= CIRCUIT_BREAKERS["vix_threshold"]:
        reason = f"VIX at {vix:.1f} above {CIRCUIT_BREAKERS['vix_threshold']:.0f} — reducing size 50%"
        return False, 0.50, reason

    return False, 1.0, None


def _check_rolling_win_rate() -> tuple[bool, str | None]:
    """Check rolling win rate over last N settled trades."""
    window = CIRCUIT_BREAKERS["rolling_window"]
    floor = CIRCUIT_BREAKERS["rolling_win_rate_floor"]

    conn = get_connection()
    rows = conn.execute(
        """
        SELECT status FROM signals
        WHERE status IN ('won', 'lost', 'stopped') AND passed_filter = 1
        ORDER BY settled_at DESC
        LIMIT ?
        """,
        (window,),
    ).fetchall()
    conn.close()

    if len(rows) < window:
        return False, None  # Not enough data yet

    wins = sum(1 for r in rows if r["status"] == "won")
    win_rate = wins / len(rows)

    if win_rate < floor:
        reason = f"Rolling win rate {win_rate*100:.1f}% (last {window}) below {floor*100:.0f}% floor"
        log_circuit_breaker_event("rolling_winrate", win_rate, floor, "pause")
        return True, reason
    return False, None


def _get_current_drawdown() -> tuple[float, float, float]:
    """Returns (drawdown_pct, current_bankroll, peak_bankroll)."""
    current = get_bankroll()

    # Try daily_snapshots for peak
    conn = get_connection()
    row = conn.execute(
        "SELECT MAX(peak_bankroll) as peak FROM daily_snapshots"
    ).fetchone()
    conn.close()

    peak = row["peak"] if row and row["peak"] else None

    if peak is None:
        # Fallback: compute from equity curve
        peak = _compute_peak_bankroll()

    # Peak must be at least current or starting
    peak = max(peak, current, STARTING_BANKROLL)

    dd_pct = (peak - current) / peak if peak > 0 else 0.0
    return max(0.0, dd_pct), current, peak


def _compute_peak_bankroll() -> float:
    """Compute peak bankroll from cumulative P&L history."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT real_pnl, settled_at FROM signals
        WHERE status IN ('won', 'lost', 'stopped') AND passed_filter = 1
        ORDER BY settled_at ASC
        """
    ).fetchall()
    conn.close()

    running = STARTING_BANKROLL
    peak = STARTING_BANKROLL
    for row in rows:
        running += (row["real_pnl"] or 0)
        peak = max(peak, running)
    return peak


# --- VIX utility ---

def get_vix_price() -> float:
    """Fetch current VIX from yfinance with caching."""
    now = datetime.now()
    if _vix_cache["value"] is not None and _vix_cache["fetched_at"] is not None:
        age = (now - _vix_cache["fetched_at"]).total_seconds()
        if age < _VIX_CACHE_TTL:
            return _vix_cache["value"]

    tk = yf.Ticker("^VIX")
    try:
        price = tk.fast_info.get("lastPrice")
    except Exception:
        price = None
    if price is None:
        price = tk.info.get("regularMarketPrice", 20.0)

    _vix_cache["value"] = float(price)
    _vix_cache["fetched_at"] = now
    return _vix_cache["value"]


# --- Logging & queries ---

def log_circuit_breaker_event(
    breaker_type: str, trigger_value: float, threshold: float, action: str
):
    """Log a circuit breaker trip to the database."""
    conn = get_connection()
    # Avoid duplicate logging for the same breaker type within 1 hour
    row = conn.execute(
        """
        SELECT id FROM circuit_breaker_log
        WHERE breaker_type = ? AND resumed_at IS NULL
            AND triggered_at > datetime('now', '-1 hour')
        LIMIT 1
        """,
        (breaker_type,),
    ).fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO circuit_breaker_log (breaker_type, trigger_value, threshold, action_taken)
            VALUES (?, ?, ?, ?)
            """,
            (breaker_type, trigger_value, threshold, action),
        )
        conn.commit()
    conn.close()


def get_active_breakers() -> list[dict]:
    """Get currently active (not yet resumed) circuit breaker events."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT * FROM circuit_breaker_log
        WHERE resumed_at IS NULL
        ORDER BY triggered_at DESC
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def resume_breaker(breaker_id: int):
    """Mark a circuit breaker event as resumed."""
    conn = get_connection()
    conn.execute(
        "UPDATE circuit_breaker_log SET resumed_at = ? WHERE id = ?",
        (datetime.now().isoformat(), breaker_id),
    )
    conn.commit()
    conn.close()
