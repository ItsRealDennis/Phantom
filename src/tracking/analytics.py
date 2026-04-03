"""Analytics — win rate, ROI, edge by strategy, equity curve."""

from src.tracking.trade_logger import get_connection
from src.config import STARTING_BANKROLL


def get_overall_stats() -> dict:
    conn = get_connection()

    total = conn.execute("SELECT COUNT(*) as cnt FROM signals").fetchone()["cnt"]
    passed = conn.execute(
        "SELECT COUNT(*) as cnt FROM signals WHERE passed_filter = 1"
    ).fetchone()["cnt"]
    filtered = total - passed

    settled = conn.execute(
        "SELECT COUNT(*) as cnt FROM signals WHERE status IN ('won', 'lost', 'stopped', 'expired')"
    ).fetchone()["cnt"]
    wins = conn.execute(
        "SELECT COUNT(*) as cnt FROM signals WHERE status = 'won'"
    ).fetchone()["cnt"]
    losses = conn.execute(
        "SELECT COUNT(*) as cnt FROM signals WHERE status IN ('lost', 'stopped')"
    ).fetchone()["cnt"]
    open_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM signals WHERE status = 'open'"
    ).fetchone()["cnt"]

    total_pnl = conn.execute(
        "SELECT COALESCE(SUM(real_pnl), 0) as pnl FROM signals WHERE status IN ('won', 'lost', 'stopped')"
    ).fetchone()["pnl"]

    total_risked = conn.execute(
        """SELECT COALESCE(SUM(position_size), 0) as total
        FROM signals WHERE passed_filter = 1 AND status IN ('won', 'lost', 'stopped')"""
    ).fetchone()["total"]

    conn.close()

    win_rate = (wins / settled * 100) if settled > 0 else 0
    roi = (total_pnl / total_risked * 100) if total_risked > 0 else 0

    return {
        "total_signals": total,
        "passed_filter": passed,
        "filtered_out": filtered,
        "settled": settled,
        "wins": wins,
        "losses": losses,
        "open": open_count,
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "roi": round(roi, 1),
        "bankroll": round(STARTING_BANKROLL + total_pnl, 2),
    }


def get_strategy_breakdown() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            strategy,
            COUNT(*) as total,
            SUM(CASE WHEN passed_filter = 1 THEN 1 ELSE 0 END) as passed,
            SUM(CASE WHEN status = 'won' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN status IN ('lost', 'stopped') THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN status IN ('won', 'lost', 'stopped') THEN 1 ELSE 0 END) as settled,
            COALESCE(SUM(CASE WHEN status IN ('won', 'lost', 'stopped') THEN real_pnl ELSE 0 END), 0) as pnl
        FROM signals
        GROUP BY strategy
        ORDER BY pnl DESC
    """).fetchall()
    conn.close()

    results = []
    for r in rows:
        settled = r["settled"]
        win_rate = (r["wins"] / settled * 100) if settled > 0 else 0
        results.append({
            "strategy": r["strategy"],
            "total": r["total"],
            "passed": r["passed"],
            "wins": r["wins"],
            "losses": r["losses"],
            "settled": settled,
            "win_rate": round(win_rate, 1),
            "pnl": round(r["pnl"], 2),
        })
    return results


def get_equity_curve() -> list[tuple[str, float]]:
    """Returns list of (date, cumulative_pnl) for equity curve."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT DATE(settled_at) as date, SUM(real_pnl) as daily_pnl
        FROM signals
        WHERE status IN ('won', 'lost', 'stopped') AND settled_at IS NOT NULL
        GROUP BY DATE(settled_at)
        ORDER BY date
    """).fetchall()
    conn.close()

    curve = []
    cumulative = STARTING_BANKROLL
    for r in rows:
        cumulative += r["daily_pnl"]
        curve.append((r["date"], round(cumulative, 2)))
    return curve


def get_filtered_outcomes() -> dict:
    """Check how filtered signals would have performed (filter validation)."""
    conn = get_connection()

    # Filtered signals that were later settled (manually marked)
    rows = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'won' THEN 1 ELSE 0 END) as would_have_won,
            SUM(CASE WHEN status IN ('lost', 'stopped') THEN 1 ELSE 0 END) as would_have_lost
        FROM signals
        WHERE passed_filter = 0 AND status IN ('won', 'lost', 'stopped')
    """).fetchone()
    conn.close()

    total = rows["total"]
    return {
        "total_tracked": total,
        "would_have_won": rows["would_have_won"],
        "would_have_lost": rows["would_have_lost"],
        "hypothetical_win_rate": round(
            rows["would_have_won"] / total * 100, 1
        ) if total > 0 else 0,
    }


def get_recent_signals(limit: int = 10) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
