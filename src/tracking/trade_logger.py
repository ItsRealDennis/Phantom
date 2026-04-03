"""Trade logger — logs every signal (passed AND filtered) to SQLite."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from src.config import DB_PATH


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
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        ),
    )
    signal_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return signal_id


def settle_trade(signal_id: int, status: str, real_pnl: float, notes: str = ""):
    """Mark a trade as won/lost/stopped/expired."""
    assert status in ("won", "lost", "stopped", "expired"), f"Invalid status: {status}"
    conn = get_connection()
    conn.execute(
        """
        UPDATE signals
        SET status = ?, settled_at = ?, real_pnl = ?, notes = ?
        WHERE id = ? AND status = 'open'
        """,
        (status, datetime.now().isoformat(), real_pnl, notes, signal_id),
    )
    conn.commit()
    conn.close()


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
    """Current bankroll = starting + total realized P&L."""
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


# Initialize DB on import
init_db()
