"""Portfolio-level risk management — exposure caps, daily limits."""

from src.config import FILTERS
from src.tracking.trade_logger import get_connection


def get_sector_exposure() -> dict[str, float]:
    """Get current dollar exposure by sector (from open trades)."""
    conn = get_connection()
    # We store sector in notes or derive from ticker — for now, simple count
    rows = conn.execute(
        """
        SELECT ticker, position_size
        FROM signals
        WHERE status = 'open' AND passed_filter = 1
        """
    ).fetchall()
    conn.close()

    # Group by sector would need a lookup — for Phase 1, just track position count
    exposure = {}
    for row in rows:
        ticker = row["ticker"]
        size = row["position_size"] or 0
        exposure[ticker] = size

    return exposure


def get_portfolio_summary() -> dict:
    """Summary of current portfolio state."""
    conn = get_connection()

    open_trades = conn.execute(
        "SELECT COUNT(*) as cnt FROM signals WHERE status = 'open'"
    ).fetchone()["cnt"]

    total_exposure = conn.execute(
        """
        SELECT COALESCE(SUM(position_size), 0) as total
        FROM signals WHERE status = 'open' AND passed_filter = 1
        """
    ).fetchone()["total"]

    total_pnl = conn.execute(
        """
        SELECT COALESCE(SUM(real_pnl), 0) as pnl
        FROM signals WHERE status IN ('won', 'lost', 'stopped')
        """
    ).fetchone()["pnl"]

    conn.close()

    from src.config import STARTING_BANKROLL

    bankroll = STARTING_BANKROLL + total_pnl

    return {
        "open_positions": open_trades,
        "max_positions": FILTERS["max_open_positions"],
        "total_exposure": round(total_exposure, 2),
        "bankroll": round(bankroll, 2),
        "total_pnl": round(total_pnl, 2),
        "roi_pct": round((total_pnl / STARTING_BANKROLL) * 100, 2) if STARTING_BANKROLL > 0 else 0,
    }
