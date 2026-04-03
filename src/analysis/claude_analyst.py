"""Send collected market context to Claude, get structured analysis back."""

import json
from pathlib import Path

import anthropic

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL

PROMPTS_DIR = Path(__file__).parent / "prompts"

SYSTEM_PROMPT = """You are an experienced intraday trader inside an automated signal system.
You think in terms of price action, volume, momentum, and key levels — not fundamentals.
Your job is to analyze a setup and output a probability estimate with TIGHT intraday levels.

Rules:
- You are DAY TRADING. Trades last minutes to hours, not days.
- Entry = current price (the system uses market orders for instant fill)
- Set stop loss TIGHT: 0.5-2% from entry. No wide stops — this is intraday.
- Set take profit with minimum 1.5:1 reward-to-risk. Aim for 2:1+ when momentum is strong.
- Estimate PROBABILITY of reaching take-profit before stop-loss within the trading session
- Be decisive. If the setup is there, confidence should reflect it (55-70%). Don't hedge everything to 50%.
- Look for: momentum continuation, VWAP bounces, breakout retests, exhaustion reversals
- Avoid: low volume chop, mid-range no-man's-land, pre-earnings binary risk

OUTPUT FORMAT (JSON only, no markdown, no code fences):
{
  "direction": "LONG" or "SHORT",
  "confidence": 58,
  "entry": 185.20,
  "stopLoss": 183.50,
  "takeProfit": 188.60,
  "riskRewardRatio": 2.0,
  "reasoning": "2-3 sentences on the intraday edge",
  "confluences": ["list", "of", "supporting", "factors"],
  "warnings": ["list", "of", "red", "flags"],
  "keyRisks": "1-2 sentence risk summary"
}"""


def load_strategy_prompt(strategy: str) -> str:
    """Load the strategy-specific prompt template."""
    prompt_file = PROMPTS_DIR / f"{strategy}.md"
    if not prompt_file.exists():
        raise ValueError(
            f"No prompt template for strategy '{strategy}'. "
            f"Available: {[p.stem for p in PROMPTS_DIR.glob('*.md')]}"
        )
    return prompt_file.read_text()


def build_user_prompt(
    ticker: str,
    strategy: str,
    timeframe: str,
    ohlcv_summary: str,
    key_levels: dict,
    volume_profile: str,
    fundamentals_summary: str,
    news_headlines: str,
) -> str:
    """Build the user message with all collected data."""
    strategy_context = load_strategy_prompt(strategy)

    return f"""{strategy_context}

---

Here is the collected data for this setup:

TICKER: {ticker}
STRATEGY: {strategy}
TIMEFRAME: {timeframe}

PRICE DATA (recent bars):
{ohlcv_summary}

KEY LEVELS:
Current Price: {key_levels.get('current_price')}
Recent 20-bar High: {key_levels.get('recent_high_20')}
Recent 20-bar Low: {key_levels.get('recent_low_20')}
Pivot: {key_levels.get('pivot')}
R1: {key_levels.get('r1')} | R2: {key_levels.get('r2')}
S1: {key_levels.get('s1')} | S2: {key_levels.get('s2')}
SMA 20: {key_levels.get('sma_20')} | SMA 50: {key_levels.get('sma_50')}

VOLUME: {volume_profile}

FUNDAMENTALS:
{fundamentals_summary}

RECENT NEWS:
{news_headlines}

Analyze this setup and return your structured JSON assessment."""


def analyze(
    ticker: str,
    strategy: str,
    timeframe: str,
    ohlcv_summary: str,
    key_levels: dict,
    volume_profile: str,
    fundamentals_summary: str,
    news_headlines: str,
) -> dict:
    """Send data to Claude, parse structured response."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_msg = build_user_prompt(
        ticker=ticker,
        strategy=strategy,
        timeframe=timeframe,
        ohlcv_summary=ohlcv_summary,
        key_levels=key_levels,
        volume_profile=volume_profile,
        fundamentals_summary=fundamentals_summary,
        news_headlines=news_headlines,
    )

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw_text = response.content[0].text.strip()

    # Strip markdown code fences if Claude wraps the JSON
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        # Remove first line (```json or ```) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw_text = "\n".join(lines)

    try:
        analysis = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned invalid JSON: {e}\nRaw response:\n{raw_text}")

    # Validate required fields
    required = [
        "direction", "confidence", "entry", "stopLoss",
        "takeProfit", "riskRewardRatio", "reasoning",
        "confluences", "warnings", "keyRisks",
    ]
    missing = [f for f in required if f not in analysis]
    if missing:
        raise ValueError(f"Claude response missing fields: {missing}")

    return analysis
