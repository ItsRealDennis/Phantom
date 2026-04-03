"""Analytics — win rate, ROI, edge by strategy, equity curve."""

from datetime import datetime, timedelta

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


def get_paginated_signals(
    offset: int = 0,
    limit: int = 25,
    sort_by: str = "created_at",
    sort_dir: str = "desc",
    strategy: str | None = None,
    status: str | None = None,
    direction: str | None = None,
    ticker_search: str | None = None,
) -> dict:
    """Paginated signals with sorting and filtering."""
    allowed_sort = {"created_at", "ticker", "strategy", "confidence", "rr_ratio", "real_pnl", "status"}
    if sort_by not in allowed_sort:
        sort_by = "created_at"
    if sort_dir not in ("asc", "desc"):
        sort_dir = "desc"

    conditions = []
    params = []
    if strategy:
        conditions.append("strategy = ?")
        params.append(strategy)
    if status:
        if status == "settled":
            conditions.append("status IN ('won', 'lost', 'stopped')")
        else:
            conditions.append("status = ?")
            params.append(status)
    if direction:
        conditions.append("direction = ?")
        params.append(direction.upper())
    if ticker_search:
        conditions.append("ticker LIKE ?")
        params.append(f"%{ticker_search.upper()}%")

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    conn = get_connection()
    total = conn.execute(f"SELECT COUNT(*) as cnt FROM signals{where}", params).fetchone()["cnt"]
    rows = conn.execute(
        f"SELECT * FROM signals{where} ORDER BY {sort_by} {sort_dir} LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    conn.close()
    return {"signals": [dict(r) for r in rows], "total_count": total}


def get_detailed_strategy_breakdown() -> list[dict]:
    """Extended strategy stats with avg confidence, avg R:R, and P&L distribution."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            strategy,
            COUNT(*) as total,
            SUM(CASE WHEN passed_filter = 1 THEN 1 ELSE 0 END) as passed,
            SUM(CASE WHEN status = 'won' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN status IN ('lost', 'stopped') THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN status IN ('won', 'lost', 'stopped') THEN 1 ELSE 0 END) as settled,
            COALESCE(SUM(CASE WHEN status IN ('won', 'lost', 'stopped') THEN real_pnl ELSE 0 END), 0) as pnl,
            AVG(confidence) as avg_confidence,
            AVG(rr_ratio) as avg_rr
        FROM signals
        GROUP BY strategy
        ORDER BY pnl DESC
    """).fetchall()

    results = []
    for r in rows:
        settled = r["settled"]
        win_rate = (r["wins"] / settled * 100) if settled > 0 else 0

        # Get individual P&L values for distribution
        pnl_rows = conn.execute(
            "SELECT real_pnl FROM signals WHERE strategy = ? AND status IN ('won', 'lost', 'stopped') AND real_pnl IS NOT NULL",
            (r["strategy"],),
        ).fetchall()

        results.append({
            "strategy": r["strategy"],
            "total": r["total"],
            "passed": r["passed"],
            "wins": r["wins"],
            "losses": r["losses"],
            "settled": settled,
            "win_rate": round(win_rate, 1),
            "pnl": round(r["pnl"], 2),
            "avg_confidence": round(r["avg_confidence"], 1) if r["avg_confidence"] else 0,
            "avg_rr": round(r["avg_rr"], 2) if r["avg_rr"] else 0,
            "pnl_values": [row["real_pnl"] for row in pnl_rows],
        })
    conn.close()
    return results


def get_risk_metrics() -> dict:
    """Compute risk metrics: sharpe, drawdown, profit factor, streaks, etc."""
    conn = get_connection()

    # Daily P&L series
    daily_rows = conn.execute("""
        SELECT DATE(settled_at) as date, SUM(real_pnl) as daily_pnl
        FROM signals
        WHERE status IN ('won', 'lost', 'stopped') AND settled_at IS NOT NULL
        GROUP BY DATE(settled_at)
        ORDER BY date
    """).fetchall()

    # Individual trade P&L for avg win/loss
    trade_rows = conn.execute("""
        SELECT real_pnl, status FROM signals
        WHERE status IN ('won', 'lost', 'stopped') AND real_pnl IS NOT NULL
        ORDER BY settled_at
    """).fetchall()

    conn.close()

    daily_pnl = [{"date": r["date"], "pnl": round(r["daily_pnl"], 2)} for r in daily_rows]

    # Compute drawdown
    cumulative = STARTING_BANKROLL
    peak = STARTING_BANKROLL
    max_drawdown = 0
    max_drawdown_pct = 0
    drawdown_series = []
    for d in daily_pnl:
        cumulative += d["pnl"]
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        dd_pct = (dd / peak * 100) if peak > 0 else 0
        if dd_pct > max_drawdown_pct:
            max_drawdown_pct = dd_pct
            max_drawdown = dd
        drawdown_series.append({"date": d["date"], "drawdown_pct": round(dd_pct, 2)})

    # Avg win / avg loss / profit factor
    wins_pnl = [r["real_pnl"] for r in trade_rows if r["real_pnl"] and r["real_pnl"] > 0]
    losses_pnl = [abs(r["real_pnl"]) for r in trade_rows if r["real_pnl"] and r["real_pnl"] < 0]
    avg_win = sum(wins_pnl) / len(wins_pnl) if wins_pnl else 0
    avg_loss = sum(losses_pnl) / len(losses_pnl) if losses_pnl else 0
    gross_profit = sum(wins_pnl)
    gross_loss = sum(losses_pnl)
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0

    # Sharpe (simplified)
    daily_returns = [d["pnl"] for d in daily_pnl]
    if len(daily_returns) > 1:
        mean_ret = sum(daily_returns) / len(daily_returns)
        variance = sum((r - mean_ret) ** 2 for r in daily_returns) / len(daily_returns)
        std_ret = variance ** 0.5
        sharpe = (mean_ret / std_ret * (252 ** 0.5)) if std_ret > 0 else 0
    else:
        sharpe = 0

    # Streaks
    longest_win = longest_loss = current_win = current_loss = 0
    for r in trade_rows:
        if r["real_pnl"] and r["real_pnl"] > 0:
            current_win += 1
            current_loss = 0
            longest_win = max(longest_win, current_win)
        elif r["real_pnl"] and r["real_pnl"] < 0:
            current_loss += 1
            current_win = 0
            longest_loss = max(longest_loss, current_loss)

    return {
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown": round(max_drawdown, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "profit_factor": round(profit_factor, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "longest_win_streak": longest_win,
        "longest_loss_streak": longest_loss,
        "daily_pnl_series": daily_pnl,
        "drawdown_series": drawdown_series,
    }


def get_daily_pnl_series(days: int = 7) -> list[dict]:
    """Last N days of daily P&L for sparklines."""
    conn = get_connection()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute("""
        SELECT DATE(settled_at) as date, SUM(real_pnl) as pnl
        FROM signals
        WHERE status IN ('won', 'lost', 'stopped') AND settled_at IS NOT NULL AND DATE(settled_at) >= ?
        GROUP BY DATE(settled_at)
        ORDER BY date
    """, (cutoff,)).fetchall()
    conn.close()
    return [{"date": r["date"], "pnl": round(r["pnl"], 2)} for r in rows]
