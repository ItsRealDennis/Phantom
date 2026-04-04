"""Screener — scan for setups with indicator-gated filtering."""

import yfinance as yf
import pandas as pd
from src.collectors.market_data import fetch_ohlcv, compute_indicators
from src.config import CRYPTO_WATCHLIST, CRYPTO_ENABLED


# Expanded watchlist — liquid day-trading names
DEFAULT_WATCHLIST = [
    # Mega caps
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    # High-vol tech
    "AMD", "NFLX", "CRM", "ORCL", "AVGO", "COIN", "MARA", "SMCI",
    "PLTR", "SOFI", "RIVN", "LCID", "NIO", "SNAP", "ROKU", "SQ",
    # ETFs
    "SPY", "QQQ", "IWM", "SOXL", "TQQQ",
]


def screen_mean_reversion(watchlist: list[str] | None = None, timeframe: str = "1d") -> list[dict]:
    """Find mean reversion setups: RSI extreme + Bollinger Band breach + SMA deviation."""
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

            indicators = compute_indicators(df, timeframe)
            rsi = indicators["rsi_14"]
            bb_pct_b = indicators["bb_pct_b"]

            # LONG: oversold (RSI < 35, below lower BB, >2% below SMA20)
            if deviation < -2.0 and rsi < 35 and bb_pct_b < 0.15:
                setups.append({
                    "ticker": ticker,
                    "strategy": "mean_reversion",
                    "deviation_pct": round(deviation, 2),
                    "direction": "LONG",
                    "price": round(float(close), 2),
                    "sma20": round(float(sma20), 2),
                    "rsi": round(rsi, 1),
                    "bb_pct_b": round(bb_pct_b, 2),
                })

            # SHORT: overbought (RSI > 65, above upper BB, >2% above SMA20)
            if deviation > 2.0 and rsi > 65 and bb_pct_b > 0.85:
                setups.append({
                    "ticker": ticker,
                    "strategy": "mean_reversion",
                    "deviation_pct": round(deviation, 2),
                    "direction": "SHORT",
                    "price": round(float(close), 2),
                    "sma20": round(float(sma20), 2),
                    "rsi": round(rsi, 1),
                    "bb_pct_b": round(bb_pct_b, 2),
                })
        except Exception:
            continue

    return sorted(setups, key=lambda x: abs(x["deviation_pct"]), reverse=True)


def screen_breakout(watchlist: list[str] | None = None, timeframe: str = "1d") -> list[dict]:
    """Find breakouts: price break + volume surge + MACD + BB squeeze + ATR expansion."""
    tickers = watchlist or DEFAULT_WATCHLIST
    setups = []

    for ticker in tickers:
        try:
            df = fetch_ohlcv(ticker, timeframe)
            if len(df) < 21:
                continue

            close = df["Close"].iloc[-1]

            # Exclude current bar from breakout level — avoids chasing
            high_20 = df["High"].iloc[-21:-1].max()
            low_20 = df["Low"].iloc[-21:-1].min()

            # Use the actual breakout bar's volume, not a 3-bar average
            breakout_vol = df["Volume"].iloc[-1]
            avg_vol = df["Volume"].iloc[-21:-1].mean()
            vol_ratio = breakout_vol / avg_vol if avg_vol > 0 else 1

            indicators = compute_indicators(df, timeframe)
            macd_hist = indicators["macd_histogram"]

            # Bollinger Bandwidth squeeze check: bandwidth must be below its 20-bar median
            bb_upper = indicators.get("bb_upper")
            bb_lower = indicators.get("bb_lower")
            bb_squeeze = False
            if bb_upper and bb_lower:
                sma20 = df["Close"].rolling(20).mean()
                std20 = df["Close"].rolling(20).std()
                bw_series = (2 * 2 * std20 / sma20)  # bandwidth as % of SMA
                if len(bw_series.dropna()) >= 20:
                    bw_now = float(bw_series.iloc[-1])
                    bw_median = float(bw_series.dropna().tail(20).median())
                    bb_squeeze = bw_now <= bw_median

            # ATR expansion: current ATR > ATR from 5 bars ago
            atr_series = df["High"] - df["Low"]  # simplified TR for comparison
            atr_expanding = False
            if len(atr_series) >= 6:
                atr_now = float(atr_series.tail(3).mean())
                atr_prev = float(atr_series.iloc[-6:-3].mean())
                atr_expanding = atr_now > atr_prev

            # LONG breakout: close above prior 20-bar high + volume 1.5x + MACD + squeeze or ATR
            if (close > high_20 and vol_ratio > 1.5 and macd_hist > 0
                    and (bb_squeeze or atr_expanding)):
                setups.append({
                    "ticker": ticker,
                    "strategy": "breakout",
                    "direction": "LONG",
                    "price": round(float(close), 2),
                    "level": round(float(high_20), 2),
                    "vol_ratio": round(vol_ratio, 2),
                    "macd_hist": round(macd_hist, 3),
                    "bb_squeeze": bb_squeeze,
                    "atr_expanding": atr_expanding,
                })

            # SHORT breakout: close below prior 20-bar low + volume 1.5x + MACD + squeeze or ATR
            if (close < low_20 and vol_ratio > 1.5 and macd_hist < 0
                    and (bb_squeeze or atr_expanding)):
                setups.append({
                    "ticker": ticker,
                    "strategy": "breakout",
                    "direction": "SHORT",
                    "price": round(float(close), 2),
                    "level": round(float(low_20), 2),
                    "vol_ratio": round(vol_ratio, 2),
                    "macd_hist": round(macd_hist, 3),
                    "bb_squeeze": bb_squeeze,
                    "atr_expanding": atr_expanding,
                })
        except Exception:
            continue

    return sorted(setups, key=lambda x: x["vol_ratio"], reverse=True)


def screen_momentum(watchlist: list[str] | None = None, timeframe: str = "1d") -> list[dict]:
    """Find momentum setups: trend + MACD + RSI sweet spot + EMA9 confirms."""
    tickers = watchlist or DEFAULT_WATCHLIST
    setups = []

    for ticker in tickers:
        try:
            df = fetch_ohlcv(ticker, timeframe)
            if len(df) < 20:
                continue

            close = df["Close"].iloc[-1]
            close_10 = df["Close"].iloc[-10] if len(df) >= 10 else df["Close"].iloc[0]
            momentum_10d = ((close - close_10) / close_10) * 100

            if len(df) >= 5:
                recent_2 = df["Close"].tail(2).mean()
                prior_3 = df["Close"].iloc[-5:-2].mean()
                pullback = ((recent_2 - prior_3) / prior_3) * 100
            else:
                pullback = 0

            indicators = compute_indicators(df, timeframe)
            macd_hist = indicators["macd_histogram"]
            rsi = indicators["rsi_14"]
            ema9 = indicators["ema_9"]

            # LONG: momentum + MACD positive + RSI 40-70 + above EMA9 + pullback
            if (momentum_10d > 3 and macd_hist > 0 and
                    40 < rsi < 70 and close > ema9 and -3 < pullback < 0):
                setups.append({
                    "ticker": ticker,
                    "strategy": "momentum",
                    "direction": "LONG",
                    "price": round(float(close), 2),
                    "momentum_10d": round(momentum_10d, 2),
                    "pullback_pct": round(pullback, 2),
                    "rsi": round(rsi, 1),
                    "macd_hist": round(macd_hist, 3),
                })

            # SHORT: negative momentum + MACD negative + RSI 30-60 + below EMA9 + bounce
            if (momentum_10d < -3 and macd_hist < 0 and
                    30 < rsi < 60 and close < ema9 and 0 < pullback < 3):
                setups.append({
                    "ticker": ticker,
                    "strategy": "momentum",
                    "direction": "SHORT",
                    "price": round(float(close), 2),
                    "momentum_10d": round(momentum_10d, 2),
                    "pullback_pct": round(pullback, 2),
                    "rsi": round(rsi, 1),
                    "macd_hist": round(macd_hist, 3),
                })
        except Exception:
            continue

    return sorted(setups, key=lambda x: abs(x["momentum_10d"]), reverse=True)


# --- Crypto Screeners ---
# Same strategies but tuned for 24/7 crypto markets

def screen_crypto(timeframe: str = "15m") -> list[dict]:
    """Run all three strategies on the crypto watchlist. Returns combined setups."""
    if not CRYPTO_ENABLED:
        return []

    all_setups = []
    all_setups.extend(screen_mean_reversion(watchlist=CRYPTO_WATCHLIST, timeframe=timeframe))
    all_setups.extend(screen_breakout(watchlist=CRYPTO_WATCHLIST, timeframe=timeframe))
    all_setups.extend(screen_momentum(watchlist=CRYPTO_WATCHLIST, timeframe=timeframe))

    # Deduplicate by ticker
    seen = set()
    unique = []
    for s in all_setups:
        if s["ticker"] not in seen:
            seen.add(s["ticker"])
            unique.append(s)

    return unique
