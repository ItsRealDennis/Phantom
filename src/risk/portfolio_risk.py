"""Portfolio-level risk management — exposure caps, correlation, beta, direction balance."""

import logging
from datetime import datetime

import yfinance as yf

from src.config import FILTERS, STARTING_BANKROLL, PORTFOLIO_RISK
from src.tracking.trade_logger import get_connection, get_bankroll

logger = logging.getLogger(__name__)

# Correlation cache — avoids repeated downloads
_corr_cache: dict = {"data": None, "tickers": None, "fetched_at": None}
_CORR_CACHE_TTL = 3600  # 1 hour


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


# --- Phase 2: Pre-trade portfolio risk checks ---

def check_portfolio_risk(ticker: str, direction: str, dollar_risk: float) -> dict:
    """
    Pre-trade portfolio risk check. Run before approving a new signal.

    Returns {
        "approved": bool,
        "reasons": list[str],
        "warnings": list[str],
        "total_risk_pct": float,
        "portfolio_beta": float,
    }
    """
    reasons = []
    warnings = []
    total_risk_pct = 0.0
    portfolio_beta = 0.0

    # 1. Correlation guard
    approved, reason = _check_correlation_guard(ticker)
    if not approved:
        reasons.append(reason)
    elif reason:
        warnings.append(reason)

    # 2. Beta exposure
    approved, beta, reason = _check_beta_exposure(ticker)
    portfolio_beta = beta
    if not approved:
        reasons.append(reason)
    elif reason:
        warnings.append(reason)

    # 3. Direction balance
    approved, reason = _check_direction_balance(direction)
    if not approved:
        reasons.append(reason)
    elif reason:
        warnings.append(reason)

    # 4. Total risk
    approved, risk_pct, reason = _check_total_risk(dollar_risk)
    total_risk_pct = risk_pct
    if not approved:
        reasons.append(reason)

    return {
        "approved": len(reasons) == 0,
        "reasons": reasons,
        "warnings": warnings,
        "total_risk_pct": round(total_risk_pct, 4),
        "portfolio_beta": round(portfolio_beta, 2),
    }


def _check_correlation_guard(ticker: str) -> tuple[bool, str | None]:
    """Check if adding this ticker would exceed max correlated positions."""
    open_tickers = _get_open_tickers()
    if len(open_tickers) < 2:
        return True, None  # Not enough positions to worry about correlation

    try:
        correlations = _compute_pairwise_correlations(
            open_tickers + [ticker],
            PORTFOLIO_RISK["correlation_lookback_days"],
        )
    except Exception as e:
        logger.debug("Correlation computation failed: %s — skipping", e)
        return True, None

    threshold = PORTFOLIO_RISK["correlation_threshold"]
    max_corr = PORTFOLIO_RISK["max_correlated_positions"]

    # Count how many existing positions are highly correlated with the new ticker
    high_corr_count = 0
    high_corr_pairs = []
    for other in open_tickers:
        pair = tuple(sorted([ticker, other]))
        corr = correlations.get(pair, 0.0)
        if abs(corr) >= threshold:
            high_corr_count += 1
            high_corr_pairs.append(f"{other} ({corr:.2f})")

    if high_corr_count >= max_corr:
        return False, f"{ticker} highly correlated with {', '.join(high_corr_pairs)} — exceeds max {max_corr}"

    if high_corr_count > 0:
        return True, f"Correlation alert: {ticker} correlated with {', '.join(high_corr_pairs)}"

    return True, None


def _check_beta_exposure(ticker: str) -> tuple[bool, float, str | None]:
    """Check if adding this ticker would push portfolio beta above cap."""
    max_beta = PORTFOLIO_RISK["max_portfolio_beta"]

    # Get current portfolio beta
    open_positions = _get_open_positions_with_size()
    current_beta = 0.0

    for pos in open_positions:
        beta = _get_ticker_beta(pos["ticker"])
        weight = pos["position_size"] / max(sum(p["position_size"] for p in open_positions), 1)
        direction_sign = 1.0 if pos["direction"] == "LONG" else -1.0
        current_beta += beta * weight * direction_sign

    # Add new ticker's contribution (estimate with equal weight)
    new_beta = _get_ticker_beta(ticker)
    total_positions = len(open_positions) + 1
    estimated_new_weight = 1.0 / total_positions
    projected_beta = current_beta * (1 - estimated_new_weight) + new_beta * estimated_new_weight

    if abs(projected_beta) > max_beta:
        return False, abs(projected_beta), f"Portfolio beta would be {projected_beta:.2f} (max {max_beta:.1f})"

    return True, abs(projected_beta), None


def _check_direction_balance(direction: str) -> tuple[bool, str | None]:
    """Check same-direction position count and net exposure."""
    max_same = PORTFOLIO_RISK["max_same_direction"]

    conn = get_connection()
    rows = conn.execute(
        """
        SELECT direction, COUNT(*) as cnt FROM signals
        WHERE status = 'open' AND passed_filter = 1
        GROUP BY direction
        """
    ).fetchall()
    conn.close()

    counts = {r["direction"]: r["cnt"] for r in rows}
    same_count = counts.get(direction, 0)

    if same_count >= max_same:
        return False, f"Already {same_count} {direction} positions (max {max_same})"

    # Warn if >80% one direction
    total = sum(counts.values())
    if total > 0 and same_count > 0:
        pct = (same_count + 1) / (total + 1)  # +1 for the new trade
        if pct > 0.80:
            return True, f"Warning: {pct*100:.0f}% exposure would be {direction}"

    return True, None


def _check_total_risk(dollar_risk: float) -> tuple[bool, float, str | None]:
    """Check if total risk across all positions exceeds cap."""
    max_risk_pct = PORTFOLIO_RISK["max_total_risk_pct"]
    bankroll = get_bankroll()

    conn = get_connection()
    row = conn.execute(
        """
        SELECT COALESCE(SUM(position_size), 0) as total_risk
        FROM signals WHERE status = 'open' AND passed_filter = 1
        """
    ).fetchone()
    conn.close()

    current_risk = row["total_risk"]
    projected_risk = current_risk + dollar_risk
    risk_pct = projected_risk / bankroll if bankroll > 0 else 0

    if risk_pct > max_risk_pct:
        return False, risk_pct, f"Total risk {risk_pct*100:.1f}% would exceed {max_risk_pct*100:.0f}% cap"

    return True, risk_pct, None


# --- Helpers ---

def _get_open_tickers() -> list[str]:
    """Get list of tickers with open positions."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT ticker FROM signals WHERE status = 'open' AND passed_filter = 1"
    ).fetchall()
    conn.close()
    return [r["ticker"] for r in rows]


def _get_open_positions_with_size() -> list[dict]:
    """Get open positions with size and direction info."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT ticker, direction, position_size FROM signals
        WHERE status = 'open' AND passed_filter = 1
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _get_ticker_beta(ticker: str) -> float:
    """Get beta for a ticker. Try yfinance info, fallback to 1.0."""
    from src.config import is_crypto
    if is_crypto(ticker):
        return 1.5  # Crypto is high-beta by nature

    try:
        tk = yf.Ticker(ticker)
        beta = tk.info.get("beta")
        if beta is not None:
            return float(beta)
    except Exception:
        pass
    return 1.0  # Default beta


def _compute_pairwise_correlations(tickers: list[str], lookback_days: int = 30) -> dict:
    """
    Compute pairwise Pearson correlations between tickers.
    Returns {(tickerA, tickerB): corr_value} for all pairs.
    Uses batch yf.download for efficiency. Cached for 1 hour.
    """
    import pandas as pd
    from src.config import is_crypto, alpaca_to_yfinance

    sorted_tickers = sorted(set(tickers))
    cache_key = tuple(sorted_tickers)

    now = datetime.now()
    if (_corr_cache["tickers"] == cache_key
            and _corr_cache["data"] is not None
            and _corr_cache["fetched_at"] is not None
            and (now - _corr_cache["fetched_at"]).total_seconds() < _CORR_CACHE_TTL):
        return _corr_cache["data"]

    # Convert symbols for yfinance
    yf_tickers = []
    ticker_map = {}
    for t in sorted_tickers:
        yf_sym = alpaca_to_yfinance(t) if is_crypto(t) else t
        yf_tickers.append(yf_sym)
        ticker_map[yf_sym] = t

    if len(yf_tickers) < 2:
        return {}

    # Batch download
    df = yf.download(yf_tickers, period=f"{lookback_days}d", interval="1d", progress=False)

    if df.empty:
        return {}

    # Extract close prices
    if isinstance(df.columns, pd.MultiIndex):
        closes = df["Close"]
    else:
        closes = df[["Close"]]
        closes.columns = [yf_tickers[0]]

    # Compute returns and correlation
    returns = closes.pct_change().dropna()
    corr_matrix = returns.corr()

    # Build result dict with original ticker names
    result = {}
    for i, t1 in enumerate(corr_matrix.columns):
        for j, t2 in enumerate(corr_matrix.columns):
            if i < j:
                orig1 = ticker_map.get(t1, t1)
                orig2 = ticker_map.get(t2, t2)
                pair = tuple(sorted([orig1, orig2]))
                result[pair] = round(corr_matrix.iloc[i, j], 3)

    # Cache
    _corr_cache["data"] = result
    _corr_cache["tickers"] = cache_key
    _corr_cache["fetched_at"] = now

    return result
