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

# Polymarket
POLYMARKET_PRIVATE_KEY = os.environ.get("POLYMARKET_PRIVATE_KEY", "")
POLYMARKET_FUNDER = os.environ.get("POLYMARKET_FUNDER", "")  # Wallet address
POLYMARKET_ENABLED = os.environ.get("PHANTOM_POLYMARKET", "false").lower() == "true"
POLYMARKET_HOST = "https://clob.polymarket.com"
POLYMARKET_GAMMA_HOST = "https://gamma-api.polymarket.com"
POLYMARKET_CHAIN_ID = 137  # Polygon

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
# Polymarket settings
POLYMARKET_FILTERS = {
    "min_confidence": 60,           # Higher bar — prediction markets are efficient
    "min_edge": 0.05,               # 5% minimum edge (our prob vs market price)
    "max_open_positions": 5,
    "max_position_pct": 0.02,       # 2% max bankroll risk per market
    "max_daily_loss_pct": 0.03,
    "min_volume": 1000,             # Min $1K total volume on market
    "min_liquidity": 500,           # Min $500 on best bid/ask
    "edge_shrinkage": 0.50,
}
POLYMARKET_STRATEGIES = ["mispricing", "event_catalyst", "momentum"]
POLYMARKET_SCAN_INTERVAL_MIN = 30   # Scan every 30 min
POLYMARKET_MAX_SIGNALS = int(os.environ.get("PHANTOM_PM_MAX_SIGNALS", "6"))
POLYMARKET_CATEGORIES = [
    "politics", "crypto", "sports", "economics", "tech", "science", "culture",
]

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

# --- Phase 2: Circuit Breakers ---
CIRCUIT_BREAKERS = {
    "daily_loss_pause_pct": 0.03,       # 3% daily loss = pause all trading
    "consecutive_loss_pause": 3,         # 3 consecutive losses = pause
    "drawdown_tiers": [                  # (drawdown_pct, size_multiplier)
        (0.05, 0.50),                    # 5% DD -> half size
        (0.10, 0.25),                    # 10% DD -> quarter size
        (0.15, 0.00),                    # 15% DD -> stop trading
    ],
    "vix_threshold": 30.0,              # VIX above 30 = reduce size by 50%
    "vix_halt": 40.0,                   # VIX above 40 = stop trading
    "rolling_win_rate_floor": 0.35,     # Below 35% win rate on last 20 = pause
    "rolling_window": 20,               # Number of recent trades for rolling metrics
}

# --- Phase 2: Portfolio Risk ---
PORTFOLIO_RISK = {
    "max_correlated_positions": 3,       # Max positions with pairwise corr > threshold
    "correlation_threshold": 0.70,       # Pearson correlation threshold
    "correlation_lookback_days": 30,     # Days of price data for correlation
    "max_portfolio_beta": 2.0,           # Total portfolio weighted beta cap
    "max_same_direction": 4,             # Max positions in same direction
    "max_total_risk_pct": 0.06,          # 6% of bankroll at risk across all positions
}

# --- Phase 2: Position Sizer v2 ---
POSITION_SIZER_V2 = {
    "drawdown_scale": [                  # (drawdown_pct, multiplier)
        (0.00, 1.00),
        (0.05, 0.50),
        (0.10, 0.25),
    ],
    "vix_scale_threshold": 20.0,         # Above this VIX, start scaling down
    "vix_scale_factor": 0.02,            # Reduce size by 2% per VIX point above threshold
    "strategy_decay_enabled": True,      # Enable strategy confidence decay
}

# --- Phase 2: Strategy Max Hold Times (hours) ---
STRATEGY_MAX_HOLD = {
    "mean_reversion": 8,
    "breakout": 48,
    "momentum": 72,
    "earnings_play": 24,
    # Polymarket strategies — hold until resolution or max hold
    "mispricing": 168,        # 7 days
    "event_catalyst": 72,     # 3 days
    "pm_momentum": 48,        # 2 days (prediction market momentum)
}

# --- Phase 2: Filter Validation ---
FILTER_VALIDATION = {
    "enabled": True,
    "alert_negative_alpha": True,        # Alert if filter alpha goes negative
}

# Web
WEB_PORT = int(os.environ.get("PORT", "8000"))
