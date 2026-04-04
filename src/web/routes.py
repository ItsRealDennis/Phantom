"""API routes and dashboard serving."""

import threading
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, JSONResponse

from src.tracking.analytics import (
    get_overall_stats,
    get_strategy_breakdown,
    get_equity_curve,
    get_filtered_outcomes,
    get_recent_signals,
    get_paginated_signals,
    get_detailed_strategy_breakdown,
    get_risk_metrics,
    get_daily_pnl_series,
    get_rolling_strategy_metrics,
)
from src.tracking.trade_logger import get_open_trades, get_signal_by_id, get_connection
from src.risk.portfolio_risk import get_portfolio_summary, get_sector_exposure
from src.automation.scheduler import get_scheduler_status
from src.automation.scanner import run_scan_cycle, run_crypto_scan
from src.execution.order_sync import sync_all_open_trades
from src.execution.alpaca_client import is_alpaca_enabled, get_account_info, get_positions, get_client
from src.execution.order_manager import cancel_order

router = APIRouter()

TEMPLATES_DIR = Path(__file__).parent / "templates"


# --- Health ---

@router.get("/health")
def health():
    return {"status": "ok"}


# --- Dashboard ---

@router.get("/", response_class=HTMLResponse)
def dashboard():
    html_file = TEMPLATES_DIR / "index.html"
    return HTMLResponse(content=html_file.read_text())


@router.get("/legacy", response_class=HTMLResponse)
def legacy_dashboard():
    html_file = TEMPLATES_DIR / "dashboard.html"
    return HTMLResponse(content=html_file.read_text())


# --- API endpoints ---

@router.get("/api/overview")
def api_overview():
    return get_overall_stats()


@router.get("/api/strategies")
def api_strategies():
    return get_strategy_breakdown()


@router.get("/api/signals")
def api_signals(limit: int = Query(default=20, ge=1, le=200)):
    return get_recent_signals(limit)


@router.get("/api/signals/paginated")
def api_signals_paginated(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    sort_by: str = Query(default="created_at"),
    sort_dir: str = Query(default="desc"),
    strategy: str | None = Query(default=None),
    status: str | None = Query(default=None),
    direction: str | None = Query(default=None),
    ticker: str | None = Query(default=None),
):
    return get_paginated_signals(offset, limit, sort_by, sort_dir, strategy, status, direction, ticker)


@router.get("/api/signals/{signal_id}")
def api_signal_detail(signal_id: int):
    signal = get_signal_by_id(signal_id)
    if not signal:
        return JSONResponse(status_code=404, content={"error": "Signal not found"})
    return signal


@router.get("/api/strategies/detailed")
def api_strategies_detailed():
    return get_detailed_strategy_breakdown()


@router.get("/api/risk/metrics")
def api_risk_metrics():
    return get_risk_metrics()


@router.get("/api/daily-pnl")
def api_daily_pnl(days: int = Query(default=7, ge=1, le=90)):
    return get_daily_pnl_series(days)


@router.get("/api/open-trades")
def api_open_trades():
    return get_open_trades()


@router.get("/api/equity-curve")
def api_equity_curve():
    return get_equity_curve()


@router.get("/api/portfolio")
def api_portfolio():
    return get_portfolio_summary()


@router.get("/api/filter-validation")
def api_filter_validation():
    return get_filtered_outcomes()


# --- Phase 2 endpoints ---

@router.get("/api/circuit-breakers")
def api_circuit_breakers():
    """Current circuit breaker status + active events."""
    from src.risk.circuit_breakers import check_circuit_breakers, get_active_breakers
    return {
        "status": check_circuit_breakers(),
        "active_events": get_active_breakers(),
    }


@router.post("/api/circuit-breakers/{breaker_id}/resume")
def api_resume_breaker(breaker_id: int):
    """Manually resume a tripped circuit breaker."""
    from src.risk.circuit_breakers import resume_breaker
    resume_breaker(breaker_id)
    return {"status": "resumed", "id": breaker_id}


@router.get("/api/risk/portfolio-detail")
def api_portfolio_risk_detail():
    """Full portfolio risk dashboard data: sectors, beta, direction, total risk."""
    from src.risk.portfolio_risk import check_portfolio_risk
    summary = get_portfolio_summary()
    sectors = get_sector_exposure()

    # Direction balance
    conn = get_connection()
    direction_rows = conn.execute(
        """
        SELECT direction, COUNT(*) as cnt, COALESCE(SUM(position_size), 0) as exposure
        FROM signals WHERE status = 'open' AND passed_filter = 1
        GROUP BY direction
        """
    ).fetchall()
    conn.close()
    direction_balance = {r["direction"]: {"count": r["cnt"], "exposure": round(r["exposure"], 2)} for r in direction_rows}

    return {
        "summary": summary,
        "sector_exposure": sectors,
        "direction_balance": direction_balance,
    }


@router.get("/api/strategies/health")
def api_strategy_health():
    """Rolling strategy metrics + health status."""
    return get_rolling_strategy_metrics()


@router.get("/api/filter-validation/detailed")
def api_filter_validation_detailed():
    """Detailed filter validation with per-reason breakdown + alpha."""
    from src.tracking.filter_validation import get_filter_alpha, get_filter_validation_detail
    return {
        "alpha": get_filter_alpha(),
        "detail": get_filter_validation_detail(),
    }


@router.get("/api/open-trades/live")
def api_open_trades_live():
    """Open positions with live P&L computed from current prices."""
    from src.automation.settler import get_current_price
    trades = get_open_trades()
    for t in trades:
        if t.get("passed_filter"):
            try:
                price = get_current_price(t["ticker"])
                risk_per_share = abs(t["entry_price"] - t["stop_loss"])
                shares = int(t["position_size"] / risk_per_share) if risk_per_share > 0 and t["position_size"] else 0
                if t["direction"] == "LONG":
                    t["live_pnl"] = round(shares * (price - t["entry_price"]), 2)
                else:
                    t["live_pnl"] = round(shares * (t["entry_price"] - price), 2)
                t["current_price"] = round(price, 2)
            except Exception:
                t["live_pnl"] = None
                t["current_price"] = None
    return trades


@router.get("/api/snapshots")
def api_snapshots(days: int = Query(default=30, ge=1, le=365)):
    """Daily snapshots for trend analysis."""
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM daily_snapshots WHERE date >= ? ORDER BY date", (cutoff,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/api/scheduler/status")
def api_scheduler_status():
    return get_scheduler_status()


# --- Manual triggers ---

@router.post("/api/scan/trigger")
def trigger_scan():
    """Trigger both stock and crypto scans in background threads."""
    threading.Thread(target=run_scan_cycle, daemon=True).start()
    threading.Thread(target=run_crypto_scan, daemon=True).start()
    return {"status": "scan_started", "scans": ["stocks", "crypto"]}


@router.post("/api/settle/trigger")
def trigger_settle():
    """Trigger combined settlement (Alpaca + paper) in a background thread."""
    thread = threading.Thread(target=sync_all_open_trades, daemon=True)
    thread.start()
    return {"status": "settlement_started"}


@router.post("/api/sync/trigger")
def trigger_sync():
    """Trigger order sync (alias for settle)."""
    thread = threading.Thread(target=sync_all_open_trades, daemon=True)
    thread.start()
    return {"status": "sync_started"}


# --- Alpaca endpoints ---

@router.get("/api/alpaca/status")
def alpaca_status():
    """Check if Alpaca is connected."""
    enabled = is_alpaca_enabled()
    if not enabled:
        return {"enabled": False, "connected": False, "account_status": None}

    account = get_account_info()
    return {
        "enabled": True,
        "connected": account is not None,
        "account_status": account.get("status") if account else None,
    }


@router.get("/api/alpaca/account")
def alpaca_account():
    """Get Alpaca account info."""
    if not is_alpaca_enabled():
        return JSONResponse(status_code=503, content={"error": "Alpaca not configured"})

    account = get_account_info()
    if not account:
        return JSONResponse(status_code=503, content={"error": "Alpaca connection failed"})

    return account


@router.get("/api/alpaca/positions")
def alpaca_positions():
    """Get live Alpaca positions."""
    return get_positions()


@router.post("/api/alpaca/cancel/{order_id}")
def alpaca_cancel(order_id: str):
    """Cancel a specific Alpaca order."""
    success = cancel_order(order_id)
    if success:
        return {"status": "canceled", "order_id": order_id}
    return JSONResponse(status_code=400, content={"error": "Failed to cancel order"})


@router.post("/api/alpaca/cancel-all")
def alpaca_cancel_all():
    """Cancel ALL open Alpaca orders."""
    client = get_client()
    if not client:
        return JSONResponse(status_code=503, content={"error": "Alpaca not connected"})
    try:
        client.cancel_orders()
        return {"status": "all_canceled"}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


# --- Polymarket ---

@router.post("/api/polymarket/scan")
def polymarket_scan_now():
    """Trigger a Polymarket scan cycle."""
    from src.config import POLYMARKET_ENABLED
    if not POLYMARKET_ENABLED:
        return JSONResponse(status_code=503, content={"error": "Polymarket not enabled"})

    def _run():
        from src.polymarket_orchestrator import run_polymarket_cycle
        run_polymarket_cycle()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"status": "polymarket_scan_started"}


@router.get("/api/polymarket/markets")
def polymarket_markets(limit: int = Query(20, ge=1, le=100)):
    """Get active Polymarket markets."""
    from src.collectors.polymarket_data import list_markets
    markets = list_markets(limit=limit, active=True)
    return markets


@router.get("/api/polymarket/signals")
def polymarket_signals(limit: int = Query(50, ge=1, le=200)):
    """Get Polymarket signals (PM: prefixed tickers)."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM signals WHERE ticker LIKE 'PM:%'
        ORDER BY created_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/api/trades/expire-all")
def expire_all_open():
    """Force-expire all open trades. Use to reset for a fresh start."""
    from src.tracking.trade_logger import get_open_trades, settle_trade
    trades = get_open_trades()
    count = 0
    for t in trades:
        settle_trade(t["id"], "expired", 0.0, notes="Manual reset")
        count += 1
    # Also cancel Alpaca orders
    client = get_client()
    if client:
        try:
            client.cancel_orders()
        except Exception:
            pass
    return {"status": "expired", "count": count}
