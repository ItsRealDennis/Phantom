"""Phantom — Paper trading signal validation system configuration."""

import os
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent

# DB path — override via PHANTOM_DB_DIR for Railway persistent volume
_db_dir = os.environ.get("PHANTOM_DB_DIR", "")
if _db_dir:
    DB_PATH = Path(_db_dir) / "trades.db"
else:
    DB_PATH = PROJECT_ROOT / "src" / "db" / "trades.db"

# API Keys
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "")

# Claude model for analysis
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# Paper bankroll
STARTING_BANKROLL = 10_000.00

# Trade filters — mirrors BetByGPT market_filters.py
FILTERS = {
    "min_confidence": 55,           # Below this = no trade
    "min_rr_ratio": 2.0,            # Minimum risk:reward ratio
    "max_position_pct": 0.015,      # 1.5% max bankroll risk per trade
    "max_open_positions": 5,         # Portfolio-level limit
    "max_sector_exposure": 0.30,     # No more than 30% in one sector
    "max_daily_loss_pct": 0.03,      # 3% daily loss = stop trading for the day
    "edge_shrinkage": 0.50,          # Halve the estimated edge for sizing
}

# Strategies available in Phase 1
STRATEGIES = ["mean_reversion", "breakout", "momentum"]

# Timeframes
VALID_TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d"]

# Automation settings
_watchlist_env = os.environ.get("PHANTOM_WATCHLIST", "")
SCAN_WATCHLIST = [t.strip() for t in _watchlist_env.split(",") if t.strip()] or None  # None = use DEFAULT_WATCHLIST
SCAN_TIMEFRAME = os.environ.get("PHANTOM_TIMEFRAME", "15m")
TRADE_EXPIRY_DAYS = int(os.environ.get("PHANTOM_EXPIRY_DAYS", "1"))
MAX_SIGNALS_PER_CYCLE = int(os.environ.get("PHANTOM_MAX_SIGNALS", "8"))

# Crypto settings
CRYPTO_ENABLED = os.environ.get("PHANTOM_CRYPTO", "true").lower() == "true"
CRYPTO_WATCHLIST = [
    # Major pairs (USD)
    "BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD", "DOGE/USD",
    "ADA/USD", "DOT/USD", "LINK/USD", "SHIB/USD",
    "LTC/USD", "BCH/USD", "BONK/USD", "ARB/USD",
    # Alts
    "FIL/USD", "CRV/USD", "BAT/USD",
]

# Symbol mapping: Alpaca uses "BTC/USD", yfinance uses "BTC-USD"
def alpaca_to_yfinance(symbol: str) -> str:
    """Convert Alpaca crypto symbol to yfinance format."""
    return symbol.replace("/", "-")

def yfinance_to_alpaca(symbol: str) -> str:
    """Convert yfinance crypto symbol to Alpaca format."""
    return symbol.replace("-", "/")

def is_crypto(symbol: str) -> bool:
    """Check if a symbol is crypto (contains / or -USD suffix)."""
    return "/" in symbol or symbol.endswith("-USD")

# Web
WEB_PORT = int(os.environ.get("PORT", "8000"))
