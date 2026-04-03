"""Fetch OHLCV, volume, key levels, and technical indicators for a ticker."""

import yfinance as yf
import pandas as pd
from datetime import datetime


def fetch_ohlcv(ticker: str, timeframe: str = "1d", lookback_days: int = 60) -> pd.DataFrame:
    """Fetch OHLCV data for a ticker. Handles crypto symbol conversion."""
    from src.config import is_crypto, alpaca_to_yfinance
    # Convert Alpaca crypto format (BTC/USD) to yfinance format (BTC-USD)
    yf_ticker = alpaca_to_yfinance(ticker) if is_crypto(ticker) else ticker
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
        "4h": "1h",
        "1d": "1d",
    }

    period = period_map.get(timeframe, "60d")
    interval = interval_map.get(timeframe, "1d")

    tk = yf.Ticker(yf_ticker)
    df = tk.history(period=period, interval=interval)

    if df.empty:
        raise ValueError(f"No data returned for {ticker} ({yf_ticker}) at {timeframe}")

    if timeframe == "4h":
        df = df.resample("4h").agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }).dropna()

    return df


def compute_indicators(df: pd.DataFrame, timeframe: str = "1d") -> dict:
    """Compute technical indicators from OHLCV data."""
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]
    current_price = float(close.iloc[-1])

    indicators = {}

    # --- RSI(14) ---
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    rsi_val = float(rsi.iloc[-1]) if len(rsi.dropna()) > 0 else 50.0
    indicators["rsi_14"] = round(rsi_val, 1)
    indicators["rsi_label"] = "overbought" if rsi_val > 70 else "oversold" if rsi_val < 30 else "neutral"

    # --- MACD(12, 26, 9) ---
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line
    indicators["macd_line"] = round(float(macd_line.iloc[-1]), 3)
    indicators["macd_signal"] = round(float(signal_line.iloc[-1]), 3)
    indicators["macd_histogram"] = round(float(histogram.iloc[-1]), 3)
    # Cross detection
    if len(histogram) >= 2:
        prev_hist = float(histogram.iloc[-2])
        curr_hist = float(histogram.iloc[-1])
        if prev_hist <= 0 and curr_hist > 0:
            indicators["macd_cross"] = "bullish"
        elif prev_hist >= 0 and curr_hist < 0:
            indicators["macd_cross"] = "bearish"
        else:
            indicators["macd_cross"] = "none"
    else:
        indicators["macd_cross"] = "none"

    # --- ATR(14) ---
    high_low = high - low
    high_close = (high - close.shift()).abs()
    low_close = (low - close.shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.ewm(span=14, adjust=False).mean()
    atr_val = float(atr.iloc[-1])
    indicators["atr_14"] = round(atr_val, 2)
    indicators["atr_pct"] = round((atr_val / current_price) * 100, 2) if current_price > 0 else 0

    # --- VWAP (intraday only) ---
    if timeframe in ("5m", "15m", "1h"):
        try:
            today_mask = df.index.date == df.index[-1].date()
            today_df = df[today_mask]
            if len(today_df) > 0:
                typical = (today_df["High"] + today_df["Low"] + today_df["Close"]) / 3
                cum_tp_vol = (typical * today_df["Volume"]).cumsum()
                cum_vol = today_df["Volume"].cumsum()
                vwap_series = cum_tp_vol / cum_vol
                vwap_val = float(vwap_series.iloc[-1])
                indicators["vwap"] = round(vwap_val, 2)
                indicators["vwap_distance_pct"] = round(((current_price - vwap_val) / vwap_val) * 100, 2)
            else:
                indicators["vwap"] = None
                indicators["vwap_distance_pct"] = None
        except Exception:
            indicators["vwap"] = None
            indicators["vwap_distance_pct"] = None
    else:
        indicators["vwap"] = None
        indicators["vwap_distance_pct"] = None

    # --- Bollinger Bands(20, 2) ---
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    bb_upper = sma20 + 2 * std20
    bb_lower = sma20 - 2 * std20
    bb_range = bb_upper - bb_lower
    pct_b = (close - bb_lower) / bb_range
    indicators["bb_upper"] = round(float(bb_upper.iloc[-1]), 2) if pd.notna(bb_upper.iloc[-1]) else None
    indicators["bb_lower"] = round(float(bb_lower.iloc[-1]), 2) if pd.notna(bb_lower.iloc[-1]) else None
    indicators["bb_pct_b"] = round(float(pct_b.iloc[-1]), 2) if pd.notna(pct_b.iloc[-1]) else 0.5

    # --- EMA 9 ---
    ema9 = close.ewm(span=9, adjust=False).mean()
    ema9_val = float(ema9.iloc[-1])
    indicators["ema_9"] = round(ema9_val, 2)
    if len(ema9) >= 4:
        slope = float(ema9.iloc[-1]) - float(ema9.iloc[-3])
        if slope > 0.01 * current_price:
            indicators["ema_9_slope"] = "rising"
        elif slope < -0.01 * current_price:
            indicators["ema_9_slope"] = "falling"
        else:
            indicators["ema_9_slope"] = "flat"
    else:
        indicators["ema_9_slope"] = "flat"

    # --- Recent swing highs/lows ---
    swing_highs = []
    swing_lows = []
    n = min(len(df) - 1, 30)
    for i in range(2, n):
        idx = -i
        if (float(high.iloc[idx]) > float(high.iloc[idx - 1]) and
                float(high.iloc[idx]) > float(high.iloc[idx + 1])):
            swing_highs.append(round(float(high.iloc[idx]), 2))
        if (float(low.iloc[idx]) < float(low.iloc[idx - 1]) and
                float(low.iloc[idx]) < float(low.iloc[idx + 1])):
            swing_lows.append(round(float(low.iloc[idx]), 2))
    indicators["swing_highs"] = swing_highs[:3]
    indicators["swing_lows"] = swing_lows[:3]

    return indicators


def compute_key_levels(df: pd.DataFrame, num_levels: int = 5) -> dict:
    """Compute simple support/resistance from recent pivots."""
    close = df["Close"].iloc[-1]
    recent_high = float(df["High"].tail(20).max())
    recent_low = float(df["Low"].tail(20).min())

    last_high = float(df["High"].iloc[-1])
    last_low = float(df["Low"].iloc[-1])
    last_close = float(df["Close"].iloc[-1])
    pivot = (last_high + last_low + last_close) / 3

    r1 = 2 * pivot - last_low
    s1 = 2 * pivot - last_high
    r2 = pivot + (last_high - last_low)
    s2 = pivot - (last_high - last_low)

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


def summarize_ohlcv(df: pd.DataFrame, last_n: int = 25) -> str:
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
    indicators = compute_indicators(df, timeframe)

    return {
        "ticker": ticker.upper(),
        "timeframe": timeframe,
        "ohlcv_df": df,
        "ohlcv_summary": ohlcv_summary,
        "key_levels": key_levels,
        "volume_profile": volume_profile,
        "indicators": indicators,
    }
