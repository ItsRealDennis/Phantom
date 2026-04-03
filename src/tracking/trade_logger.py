"""Trade logger — logs every signal (passed AND filtered) to SQLite."""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from src.config import DB_PATH

logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ticker TEXT NOT NULL,
            strategy TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            direction TEXT NOT NULL,
            confidence REAL NOT NULL,
            entry_price REAL NOT NULL,
            stop_loss REAL NOT NULL,
            take_profit REAL NOT NULL,
            rr_ratio REAL NOT NULL,
            reasoning TEXT,
            confluences TEXT,
            warnings TEXT,
            key_risks TEXT,
            kelly_pct REAL,
            position_size REAL,
            passed_filter BOOLEAN NOT NULL,
            filter_reason TEXT,
            status TEXT DEFAULT 'open',
            settled_at TIMESTAMP,
            real_pnl REAL,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS daily_summary (
            date TEXT PRIMARY KEY,
            signals_generated INTEGER DEFAULT 0,
            signals_passed INTEGER DEFAULT 0,
            trades_settled INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            daily_pnl REAL DEFAULT 0.0,
            cumulative_pnl REAL DEFAULT 0.0
        );

        CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker);
        CREATE INDEX IF NOT EXISTS idx_signals_strategy ON signals(strategy);
        CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
        CREATE INDEX IF NOT EXISTS idx_signals_passed ON signals(passed_filter);
    """)
    conn.close()

    # Run migrations
    _migrate_alpaca_columns()
    _migrate_phase2_columns()


def _migrate_alpaca_columns():
    """Add Alpaca-related columns if they don't exist. Idempotent."""
    conn = get_connection()
    new_columns = [
        ("alpaca_order_id", "TEXT"),
        ("alpaca_tp_order_id", "TEXT"),
        ("alpaca_sl_order_id", "TEXT"),
        ("alpaca_status", "TEXT"),
        ("fill_price", "REAL"),
        ("exit_price", "REAL"),
        ("shares", "INTEGER"),
        ("execution_mode", "TEXT DEFAULT 'paper'"),
    ]
    for col_name, col_type in new_columns:
        try:
            conn.execute(f"ALTER TABLE signals ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass  # Column already exists
    conn.commit()
    conn.close()


def _migrate_phase2_columns():
    """Add Phase 2 columns and tables. Idempotent."""
    conn = get_connection()

    # New columns on signals table
    new_columns = [
        ("max_adverse_excursion", "REAL"),
        ("max_favorable_excursion", "REAL"),
        ("high_water_mark", "REAL"),
        ("settlement_method", "TEXT"),
        ("settlement_price", "REAL"),
        ("bars_held", "INTEGER"),
        ("sector", "TEXT DEFAULT 'Unknown'"),
        ("beta", "REAL"),
    ]
    for col_name, col_type in new_columns:
        try:
            conn.execute(f"ALTER TABLE signals ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Circuit breaker log table
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS circuit_breaker_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            breaker_type TEXT NOT NULL,
            trigger_value REAL,
            threshold REAL,
            action_taken TEXT NOT NULL,
            resumed_at TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_cb_type ON circuit_breaker_log(breaker_type);
        CREATE INDEX IF NOT EXISTS idx_cb_triggered ON circuit_breaker_log(triggered_at);

        CREATE TABLE IF NOT EXISTS daily_snapshots (
            date TEXT PRIMARY KEY,
            bankroll REAL,
            peak_bankroll REAL,
            drawdown_pct REAL,
            signals_generated INTEGER DEFAULT 0,
            signals_passed INTEGER DEFAULT 0,
            signals_filtered INTEGER DEFAULT 0,
            trades_settled INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            daily_pnl REAL DEFAULT 0.0,
            cumulative_pnl REAL DEFAULT 0.0,
            open_positions INTEGER DEFAULT 0,
            total_risk_pct REAL DEFAULT 0.0,
            vix_close REAL
        );
    """)

    conn.commit()
    conn.close()


def log_signal(
    ticker: str,
    strategy: str,
    timeframe: str,
    direction: str,
    confidence: float,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    rr_ratio: float,
    reasoning: str,
    confluences: list,
    warnings: list,
    key_risks: str,
    kelly_pct: float | None,
    position_size: float | None,
    passed_filter: bool,
    filter_reason: str | None = None,
    sector: str = "Unknown",
    beta: float | None = None,
) -> int:
    """Log a signal to the database. Returns the signal ID."""
    conn = get_connection()
    cursor = conn.execute(
        """
        INSERT INTO signals (
            ticker, strategy, timeframe, direction, confidence,
            entry_price, stop_loss, take_profit, rr_ratio,
            reasoning, confluences, warnings, key_risks,
            kelly_pct, position_size, passed_filter, filter_reason,
            status, sector, beta
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticker.upper(),
            strategy,
            timeframe,
            direction,
            confidence,
            entry_price,
            stop_loss,
            take_profit,
            rr_ratio,
            reasoning,
            json.dumps(confluences),
            json.dumps(warnings),
            key_risks,
            kelly_pct,
            position_size,
            passed_filter,
            filter_reason,
            "open" if passed_filter else "filtered",
            sector,
            beta,
        ),
    )
    signal_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return signal_id


def settle_trade(
    signal_id: int,
    status: str,
    real_pnl: float,
    notes: str = "",
    exit_price: float | None = None,
    settlement_method: str | None = None,
    settlement_price: float | None = None,
    bars_held: int | None = None,
):
    """Mark a trade as won/lost/stopped/expired/canceled/rejected."""
    valid = ("won", "lost", "stopped", "expired", "canceled", "rejected")
    assert status in valid, f"Invalid status: {status}. Must be one of {valid}"
    conn = get_connection()
    conn.execute(
        """
        UPDATE signals
        SET status = ?, settled_at = ?, real_pnl = ?, notes = ?,
            exit_price = COALESCE(?, exit_price),
            settlement_method = COALESCE(?, settlement_method),
            settlement_price = COALESCE(?, settlement_price),
            bars_held = COALESCE(?, bars_held)
        WHERE id = ? AND status = 'open'
        """,
        (
            status, datetime.now().isoformat(), real_pnl, notes,
            exit_price, settlement_method, settlement_price, bars_held,
            signal_id,
        ),
    )
    conn.commit()
    conn.close()


# --- Alpaca-specific helpers ---

def update_alpaca_ids(
    signal_id: int,
    order_id: str,
    tp_order_id: str | None,
    sl_order_id: str | None,
    shares: int,
):
    """Store Alpaca order IDs and set execution_mode to 'alpaca'."""
    conn = get_connection()
    conn.execute(
        """
        UPDATE signals
        SET alpaca_order_id = ?, alpaca_tp_order_id = ?, alpaca_sl_order_id = ?,
            shares = ?, execution_mode = 'alpaca'
        WHERE id = ?
        """,
        (order_id, tp_order_id, sl_order_id, shares, signal_id),
    )
    conn.commit()
    conn.close()


def update_alpaca_status(
    signal_id: int,
    alpaca_status: str,
    fill_price: float | None = None,
    exit_price: float | None = None,
):
    """Update Alpaca sync status and fill prices."""
    conn = get_connection()
    conn.execute(
        """
        UPDATE signals
        SET alpaca_status = ?,
            fill_price = COALESCE(?, fill_price),
            exit_price = COALESCE(?, exit_price)
        WHERE id = ?
        """,
        (alpaca_status, fill_price, exit_price, signal_id),
    )
    conn.commit()
    conn.close()


def get_open_alpaca_trades() -> list[dict]:
    """Get open signals that have Alpaca orders."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM signals
        WHERE status = 'open' AND alpaca_order_id IS NOT NULL
        ORDER BY created_at DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_open_paper_trades() -> list[dict]:
    """Get open signals without Alpaca orders (paper-only mode)."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM signals
        WHERE status = 'open' AND alpaca_order_id IS NULL AND passed_filter = 1
        ORDER BY created_at DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Existing helpers ---

def get_open_trades() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM signals WHERE status = 'open' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_signals(limit: int = 100) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def has_open_position(ticker: str) -> bool:
    """Check if there's already an open position for this ticker."""
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM signals WHERE ticker = ? AND status = 'open'",
        (ticker.upper(),),
    ).fetchone()
    conn.close()
    return row["cnt"] > 0


def count_open_positions() -> int:
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM signals WHERE status = 'open'"
    ).fetchone()
    conn.close()
    return row["cnt"]


def get_daily_pnl(date: str | None = None) -> float:
    """Get total P&L for settled trades on a given date."""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    row = conn.execute(
        """
        SELECT COALESCE(SUM(real_pnl), 0.0) as pnl
        FROM signals
        WHERE DATE(settled_at) = ? AND status IN ('won', 'lost', 'stopped')
        """,
        (date,),
    ).fetchone()
    conn.close()
    return row["pnl"]


def get_bankroll() -> float:
    """Current bankroll — Alpaca equity if connected, else starting + realized P&L."""
    from src.execution.alpaca_client import is_alpaca_enabled, get_account_info

    if is_alpaca_enabled():
        account = get_account_info()
        if account:
            return account["equity"]

    from src.config import STARTING_BANKROLL
    conn = get_connection()
    row = conn.execute(
        """
        SELECT COALESCE(SUM(real_pnl), 0.0) as total_pnl
        FROM signals
        WHERE status IN ('won', 'lost', 'stopped')
        """
    ).fetchone()
    conn.close()
    return STARTING_BANKROLL + row["total_pnl"]


def get_signal_by_id(signal_id: int) -> dict | None:
    """Get a single signal by ID with full details."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_mae_mfe(signal_id: int, mae: float, mfe: float, hwm: float):
    """Update MAE/MFE/high-water-mark for a trade. Only updates if more extreme."""
    conn = get_connection()
    conn.execute(
        """
        UPDATE signals
        SET max_adverse_excursion = CASE
                WHEN max_adverse_excursion IS NULL THEN ?
                WHEN ? > max_adverse_excursion THEN ?
                ELSE max_adverse_excursion
            END,
            max_favorable_excursion = CASE
                WHEN max_favorable_excursion IS NULL THEN ?
                WHEN ? > max_favorable_excursion THEN ?
                ELSE max_favorable_excursion
            END,
            high_water_mark = CASE
                WHEN high_water_mark IS NULL THEN ?
                WHEN ? > high_water_mark THEN ?
                ELSE high_water_mark
            END
        WHERE id = ?
        """,
        (mae, mae, mae, mfe, mfe, mfe, hwm, hwm, hwm, signal_id),
    )
    conn.commit()
    conn.close()


def get_filtered_signals() -> list[dict]:
    """Get signals that were filtered out but still need outcome tracking."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM signals
        WHERE status = 'filtered'
        ORDER BY created_at DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def settle_filtered_trade(signal_id: int, status: str, hypothetical_pnl: float, notes: str = ""):
    """Settle a filtered signal for validation tracking. Uses filtered_won/filtered_lost status."""
    valid = ("filtered_won", "filtered_lost")
    assert status in valid, f"Invalid filtered status: {status}. Must be one of {valid}"
    conn = get_connection()
    conn.execute(
        """
        UPDATE signals
        SET status = ?, settled_at = ?, real_pnl = ?, notes = ?
        WHERE id = ? AND status = 'filtered'
        """,
        (status, datetime.now().isoformat(), hypothetical_pnl, notes, signal_id),
    )
    conn.commit()
    conn.close()


# Initialize DB on import
init_db()
