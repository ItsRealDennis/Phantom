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
)
from src.tracking.trade_logger import get_open_trades
from src.risk.portfolio_risk import get_portfolio_summary
from src.automation.scheduler import get_scheduler_status
from src.automation.scanner import run_scan_cycle
from src.execution.order_sync import sync_all_open_trades
from src.execution.alpaca_client import is_alpaca_enabled, get_account_info, get_positions
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


@router.get("/api/scheduler/status")
def api_scheduler_status():
    return get_scheduler_status()


# --- Manual triggers ---

@router.post("/api/scan/trigger")
def trigger_scan():
    """Trigger a scan cycle in a background thread."""
    thread = threading.Thread(target=run_scan_cycle, daemon=True)
    thread.start()
    return {"status": "scan_started"}


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
