"""Fetch OHLCV, volume, and key levels for a ticker via yfinance."""

import yfinance as yf
import pandas as pd
from datetime import datetime


def fetch_ohlcv(ticker: str, timeframe: str = "1d", lookback_days: int = 60) -> pd.DataFrame:
    """Fetch OHLCV data for a ticker. Returns a DataFrame."""
    period_map = {
        "5m": "5d",
        "15m": "5d",
        "1h": "30d",
        "4h": "60d",
        "1d": f"{lookback_days}d",
    }
    interval_map = {
        "5m": "5m",
        "15m": "15m",
        "1h": "1h",
        "4h": "1h",  # yfinance doesn't support 4h, we'll resample
        "1d": "1d",
    }

    period = period_map.get(timeframe, "60d")
    interval = interval_map.get(timeframe, "1d")

    tk = yf.Ticker(ticker)
    df = tk.history(period=period, interval=interval)

    if df.empty:
        raise ValueError(f"No data returned for {ticker} at {timeframe}")

    # Resample to 4h if needed
    if timeframe == "4h":
        df = df.resample("4h").agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }).dropna()

    return df


def compute_key_levels(df: pd.DataFrame, num_levels: int = 5) -> dict:
    """Compute simple support/resistance from recent pivots."""
    highs = df["High"].values
    lows = df["Low"].values
    close = df["Close"].iloc[-1]

    # Recent high/low
    recent_high = float(df["High"].tail(20).max())
    recent_low = float(df["Low"].tail(20).min())

    # Simple pivot points from last bar
    last_high = float(df["High"].iloc[-1])
    last_low = float(df["Low"].iloc[-1])
    last_close = float(df["Close"].iloc[-1])
    pivot = (last_high + last_low + last_close) / 3

    r1 = 2 * pivot - last_low
    s1 = 2 * pivot - last_high
    r2 = pivot + (last_high - last_low)
    s2 = pivot - (last_high - last_low)

    # SMA levels
    sma_20 = float(df["Close"].tail(20).mean()) if len(df) >= 20 else None
    sma_50 = float(df["Close"].tail(50).mean()) if len(df) >= 50 else None

    return {
        "current_price": float(close),
        "recent_high_20": recent_high,
        "recent_low_20": recent_low,
        "pivot": round(pivot, 2),
        "r1": round(r1, 2),
        "r2": round(r2, 2),
        "s1": round(s1, 2),
        "s2": round(s2, 2),
        "sma_20": round(sma_20, 2) if sma_20 else None,
        "sma_50": round(sma_50, 2) if sma_50 else None,
    }


def summarize_ohlcv(df: pd.DataFrame, last_n: int = 10) -> str:
    """Create a text summary of recent price action for Claude."""
    recent = df.tail(last_n)
    lines = []
    for idx, row in recent.iterrows():
        ts = idx.strftime("%Y-%m-%d %H:%M") if hasattr(idx, "strftime") else str(idx)
        change_pct = ((row["Close"] - row["Open"]) / row["Open"]) * 100
        lines.append(
            f"{ts} | O:{row['Open']:.2f} H:{row['High']:.2f} "
            f"L:{row['Low']:.2f} C:{row['Close']:.2f} V:{int(row['Volume']):,} "
            f"({change_pct:+.2f}%)"
        )
    return "\n".join(lines)


def get_volume_profile(df: pd.DataFrame) -> str:
    """Simple volume analysis."""
    avg_vol = df["Volume"].mean()
    recent_vol = df["Volume"].tail(5).mean()
    vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0

    if vol_ratio > 1.5:
        vol_desc = "ELEVATED"
    elif vol_ratio > 1.1:
        vol_desc = "ABOVE AVERAGE"
    elif vol_ratio > 0.8:
        vol_desc = "NORMAL"
    else:
        vol_desc = "BELOW AVERAGE"

    return (
        f"Avg volume: {int(avg_vol):,} | Recent 5-bar avg: {int(recent_vol):,} | "
        f"Ratio: {vol_ratio:.2f}x ({vol_desc})"
    )


def collect_market_data(ticker: str, timeframe: str = "1d") -> dict:
    """Main entry point — collect all market data for a ticker."""
    df = fetch_ohlcv(ticker, timeframe)
    key_levels = compute_key_levels(df)
    ohlcv_summary = summarize_ohlcv(df)
    volume_profile = get_volume_profile(df)

    return {
        "ticker": ticker.upper(),
        "timeframe": timeframe,
        "ohlcv_df": df,
        "ohlcv_summary": ohlcv_summary,
        "key_levels": key_levels,
        "volume_profile": volume_profile,
    }
