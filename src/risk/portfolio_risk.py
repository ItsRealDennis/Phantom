"""Portfolio-level risk management — exposure caps, daily limits."""

from src.config import FILTERS, STARTING_BANKROLL
from src.tracking.trade_logger import get_connection


def get_sector_exposure() -> dict[str, float]:
    """Get current dollar exposure by sector (from open trades)."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT ticker, position_size
        FROM signals
        WHERE status = 'open' AND passed_filter = 1
        """
    ).fetchall()
    conn.close()

    exposure = {}
    for row in rows:
        ticker = row["ticker"]
        size = row["position_size"] or 0
        exposure[ticker] = size

    return exposure


def get_portfolio_summary() -> dict:
    """Summary of current portfolio state — uses Alpaca data when available."""
    from src.execution.alpaca_client import is_alpaca_enabled, get_account_info

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

    # Use Alpaca account data when available
    alpaca_connected = False
    if is_alpaca_enabled():
        account = get_account_info()
        if account:
            alpaca_connected = True
            bankroll = account["equity"]
            buying_power = account["buying_power"]
            cash = account["cash"]
        else:
            bankroll = STARTING_BANKROLL + total_pnl
            buying_power = None
            cash = None
    else:
        bankroll = STARTING_BANKROLL + total_pnl
        buying_power = None
        cash = None

    result = {
        "open_positions": open_trades,
        "max_positions": FILTERS["max_open_positions"],
        "total_exposure": round(total_exposure, 2),
        "bankroll": round(bankroll, 2),
        "total_pnl": round(total_pnl, 2),
        "roi_pct": round((total_pnl / STARTING_BANKROLL) * 100, 2) if STARTING_BANKROLL > 0 else 0,
        "execution_mode": "alpaca" if alpaca_connected else "paper",
    }

    if buying_power is not None:
        result["buying_power"] = round(buying_power, 2)
    if cash is not None:
        result["cash"] = round(cash, 2)

    return result
