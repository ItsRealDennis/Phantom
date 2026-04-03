"""Simple screener — scan for setups matching strategy criteria."""

import yfinance as yf
import pandas as pd
from src.collectors.market_data import fetch_ohlcv


# Default watchlist — common liquid tickers
DEFAULT_WATCHLIST = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    "AMD", "SPY", "QQQ", "IWM", "NFLX", "CRM", "ORCL", "AVGO",
]


def screen_mean_reversion(watchlist: list[str] | None = None, timeframe: str = "1d") -> list[dict]:
    """Find tickers showing mean reversion setups (extended from SMA20)."""
    tickers = watchlist or DEFAULT_WATCHLIST
    setups = []

    for ticker in tickers:
        try:
            df = fetch_ohlcv(ticker, timeframe)
            if len(df) < 20:
                continue

            close = df["Close"].iloc[-1]
            sma20 = df["Close"].tail(20).mean()
            deviation = ((close - sma20) / sma20) * 100

            if abs(deviation) > 3:  # >3% from SMA20
                setups.append({
                    "ticker": ticker,
                    "strategy": "mean_reversion",
                    "deviation_pct": round(deviation, 2),
                    "direction": "LONG" if deviation < 0 else "SHORT",
                    "price": round(float(close), 2),
                    "sma20": round(float(sma20), 2),
                })
        except Exception:
            continue

    return sorted(setups, key=lambda x: abs(x["deviation_pct"]), reverse=True)


def screen_breakout(watchlist: list[str] | None = None, timeframe: str = "1d") -> list[dict]:
    """Find tickers near 20-day highs/lows with volume expansion."""
    tickers = watchlist or DEFAULT_WATCHLIST
    setups = []

    for ticker in tickers:
        try:
            df = fetch_ohlcv(ticker, timeframe)
            if len(df) < 20:
                continue

            close = df["Close"].iloc[-1]
            high_20 = df["High"].tail(20).max()
            low_20 = df["Low"].tail(20).min()
            avg_vol = df["Volume"].tail(20).mean()
            recent_vol = df["Volume"].tail(3).mean()
            vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1

            # Near 20-day high with volume
            pct_from_high = ((high_20 - close) / high_20) * 100
            pct_from_low = ((close - low_20) / low_20) * 100

            if pct_from_high < 1.0 and vol_ratio > 1.2:
                setups.append({
                    "ticker": ticker,
                    "strategy": "breakout",
                    "direction": "LONG",
                    "price": round(float(close), 2),
                    "level": round(float(high_20), 2),
                    "pct_from_level": round(pct_from_high, 2),
                    "vol_ratio": round(vol_ratio, 2),
                })
            elif pct_from_low < 1.0 and vol_ratio > 1.2:
                setups.append({
                    "ticker": ticker,
                    "strategy": "breakout",
                    "direction": "SHORT",
                    "price": round(float(close), 2),
                    "level": round(float(low_20), 2),
                    "pct_from_level": round(pct_from_low, 2),
                    "vol_ratio": round(vol_ratio, 2),
                })
        except Exception:
            continue

    return sorted(setups, key=lambda x: x["vol_ratio"], reverse=True)


def screen_momentum(watchlist: list[str] | None = None, timeframe: str = "1d") -> list[dict]:
    """Find tickers with strong recent momentum + pullback."""
    tickers = watchlist or DEFAULT_WATCHLIST
    setups = []

    for ticker in tickers:
        try:
            df = fetch_ohlcv(ticker, timeframe)
            if len(df) < 20:
                continue

            # 10-day return
            close = df["Close"].iloc[-1]
            close_10 = df["Close"].iloc[-10] if len(df) >= 10 else df["Close"].iloc[0]
            momentum_10d = ((close - close_10) / close_10) * 100

            # Recent pullback (last 2 days vs prior 3)
            if len(df) >= 5:
                recent_2 = df["Close"].tail(2).mean()
                prior_3 = df["Close"].iloc[-5:-2].mean()
                pullback = ((recent_2 - prior_3) / prior_3) * 100
            else:
                pullback = 0

            # Strong momentum with a small pullback = entry opportunity
            if momentum_10d > 5 and -3 < pullback < 0:
                setups.append({
                    "ticker": ticker,
                    "strategy": "momentum",
                    "direction": "LONG",
                    "price": round(float(close), 2),
                    "momentum_10d": round(momentum_10d, 2),
                    "pullback_pct": round(pullback, 2),
                })
            elif momentum_10d < -5 and 0 < pullback < 3:
                setups.append({
                    "ticker": ticker,
                    "strategy": "momentum",
                    "direction": "SHORT",
                    "price": round(float(close), 2),
                    "momentum_10d": round(momentum_10d, 2),
                    "pullback_pct": round(pullback, 2),
                })
        except Exception:
            continue

    return sorted(setups, key=lambda x: abs(x["momentum_10d"]), reverse=True)
