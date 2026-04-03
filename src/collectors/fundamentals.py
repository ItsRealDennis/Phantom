"""Fetch fundamental data and news for a ticker."""

import yfinance as yf
from datetime import datetime


def get_fundamentals(ticker: str) -> dict:
    """Fetch key fundamental data via yfinance."""
    tk = yf.Ticker(ticker)
    info = tk.info

    # Extract what's useful for short-term trading context
    return {
        "market_cap": info.get("marketCap"),
        "sector": info.get("sector", "Unknown"),
        "industry": info.get("industry", "Unknown"),
        "pe_ratio": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "earnings_date": _get_next_earnings(tk),
        "avg_volume": info.get("averageVolume"),
        "beta": info.get("beta"),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        "short_ratio": info.get("shortRatio"),
    }


def _get_next_earnings(tk) -> str | None:
    """Try to get the next earnings date."""
    try:
        cal = tk.calendar
        if cal is not None and not cal.empty:
            return str(cal.iloc[0, 0]) if hasattr(cal, "iloc") else str(cal)
    except Exception:
        pass
    return None


def summarize_fundamentals(data: dict) -> str:
    """Create a text summary for Claude."""
    lines = []
    if data.get("sector"):
        lines.append(f"Sector: {data['sector']} | Industry: {data.get('industry', 'N/A')}")
    if data.get("market_cap"):
        cap = data["market_cap"]
        if cap >= 1e12:
            cap_str = f"${cap/1e12:.1f}T"
        elif cap >= 1e9:
            cap_str = f"${cap/1e9:.1f}B"
        else:
            cap_str = f"${cap/1e6:.0f}M"
        lines.append(f"Market Cap: {cap_str}")
    if data.get("pe_ratio"):
        lines.append(f"P/E: {data['pe_ratio']:.1f} | Forward P/E: {data.get('forward_pe', 'N/A')}")
    if data.get("beta"):
        lines.append(f"Beta: {data['beta']:.2f}")
    if data.get("earnings_date"):
        lines.append(f"Next Earnings: {data['earnings_date']}")
    if data.get("short_ratio"):
        lines.append(f"Short Ratio: {data['short_ratio']:.1f}")
    if data.get("fifty_two_week_high") and data.get("fifty_two_week_low"):
        lines.append(
            f"52W Range: ${data['fifty_two_week_low']:.2f} - ${data['fifty_two_week_high']:.2f}"
        )

    return "\n".join(lines) if lines else "No fundamental data available."


def get_news_headlines(ticker: str, max_headlines: int = 5) -> str:
    """Fetch recent news headlines via yfinance."""
    tk = yf.Ticker(ticker)
    try:
        news = tk.news
        if not news:
            return "No recent news available."
        lines = []
        for item in news[:max_headlines]:
            title = item.get("title", item.get("content", {}).get("title", "No title"))
            pub = item.get("publisher", item.get("content", {}).get("provider", {}).get("displayName", ""))
            lines.append(f"- {title} ({pub})")
        return "\n".join(lines)
    except Exception:
        return "News fetch failed."
