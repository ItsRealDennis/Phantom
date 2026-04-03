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
from src.automation.settler import auto_settle_open_trades

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
    """Trigger auto-settlement in a background thread."""
    thread = threading.Thread(target=auto_settle_open_trades, daemon=True)
    thread.start()
    return {"status": "settlement_started"}
