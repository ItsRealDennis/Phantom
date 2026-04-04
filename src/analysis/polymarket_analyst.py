"""Polymarket-specific Claude analyst — probability assessment for prediction markets."""

import json
import logging
from pathlib import Path

import anthropic

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

SYSTEM_PROMPT = """You are an expert prediction market analyst inside an automated trading system.
You think in terms of base rates, evidence quality, information efficiency, and expected value.
Your job is to estimate the TRUE probability of an event and identify mispricing.

Rules:
- You are trading BINARY OUTCOME CONTRACTS on Polymarket.
- YES tokens pay $1 if the event happens, $0 otherwise.
- NO tokens pay $1 if the event doesn't happen, $0 otherwise.
- Current market price = implied probability. Your edge = your probability - market price.
- Be calibrated. If you say 70%, events should happen ~70% of the time.
- Consider base rates FIRST, then update with specific evidence.
- Markets are reasonably efficient — you need genuine insight to beat them.
- A 5% edge is significant. Don't claim 20% edges casually.
- Factor in time to resolution — edge decays if you're early and right.
- Consider liquidity — can you actually get filled at this price?

OUTPUT FORMAT (JSON only, no markdown, no code fences):
{
  "direction": "YES" or "NO",
  "estimatedProbability": 0.65,
  "marketPrice": 0.55,
  "edge": 0.10,
  "confidence": 68,
  "size": 100,
  "reasoning": "2-3 sentences on why market is mispriced",
  "evidenceFor": ["list", "of", "evidence", "supporting", "YES"],
  "evidenceAgainst": ["list", "of", "evidence", "supporting", "NO"],
  "baseRate": "Historical base rate and reference class used",
  "catalysts": ["upcoming events that could move the price"],
  "risks": ["resolution ambiguity", "liquidity", "correlation"],
  "keyRisks": "1-2 sentence risk summary",
  "timeHorizon": "Expected time to resolution or exit"
}"""


def load_strategy_prompt(strategy: str) -> str:
    """Load strategy-specific prompt. Falls back to prediction_market.md."""
    prompt_file = PROMPTS_DIR / f"{strategy}.md"
    if not prompt_file.exists():
        prompt_file = PROMPTS_DIR / "prediction_market.md"
    return prompt_file.read_text()


def _format_price_history(history: list[dict]) -> str:
    """Format price history into readable text."""
    if not history:
        return "No price history available."

    # Sample at most 24 data points
    step = max(1, len(history) // 24)
    sampled = history[::step][-24:]

    lines = []
    for point in sampled:
        ts = point.get("t", point.get("timestamp", ""))
        price = point.get("p", point.get("price", ""))
        if ts and price:
            lines.append(f"  {ts}: {float(price):.3f}")

    return "\n".join(lines) if lines else "No parseable price history."


def build_user_prompt(
    market_context: dict,
    strategy: str,
    news_summary: str = "",
) -> str:
    """Build the user message with all collected market data."""
    strategy_context = load_strategy_prompt(strategy)

    price_history_text = _format_price_history(market_context.get("price_history_7d", []))

    return f"""{strategy_context}

---

Here is the collected data for this prediction market:

MARKET QUESTION: {market_context['question']}

DESCRIPTION: {market_context.get('description', 'N/A')}

CATEGORY: {market_context.get('category', 'Unknown')}
TAGS: {', '.join(market_context.get('tags', [])) or 'None'}

CURRENT PRICING:
YES Price (implied probability): {market_context['yes_price']:.3f} ({market_context['yes_price']:.1%})
NO Price: {market_context['no_price']:.3f} ({market_context['no_price']:.1%})
Best Bid: {market_context['best_bid']:.3f}
Best Ask: {market_context['best_ask']:.3f}
Spread: {market_context['spread']:.3f} ({market_context['spread']:.1%})
Bid Depth (top 5): ${market_context['bid_depth_5']:.0f}
Ask Depth (top 5): ${market_context['ask_depth_5']:.0f}

VOLUME & LIQUIDITY:
24h Volume: ${market_context['volume_24h']:,.0f}
Total Volume: ${market_context['total_volume']:,.0f}
Liquidity: ${market_context['liquidity']:,.0f}

PRICE MOVEMENT:
24h Change: {market_context['price_change_24h']:.3f if market_context.get('price_change_24h') is not None else 'N/A'}
Trend: {market_context.get('price_trend', 'unknown')}

PRICE HISTORY (7 days, hourly samples):
{price_history_text}

RESOLUTION DATE: {market_context.get('end_date', 'Unknown')}

RECENT NEWS/CONTEXT:
{news_summary or 'No additional context available.'}

Analyze this market and return your structured JSON probability assessment."""


def analyze_market(
    market_context: dict,
    strategy: str = "prediction_market",
    news_summary: str = "",
) -> dict:
    """Send market data to Claude, get probability assessment back."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_msg = build_user_prompt(
        market_context=market_context,
        strategy=strategy,
        news_summary=news_summary,
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
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw_text = "\n".join(lines)

    try:
        analysis = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned invalid JSON: {e}\nRaw response:\n{raw_text}")

    required = [
        "direction", "estimatedProbability", "marketPrice", "edge",
        "confidence", "reasoning", "evidenceFor", "evidenceAgainst",
        "risks", "keyRisks",
    ]
    missing = [f for f in required if f not in analysis]
    if missing:
        raise ValueError(f"Claude response missing fields: {missing}")

    # Ensure edge is positive and direction is consistent
    est_prob = analysis["estimatedProbability"]
    mkt_price = analysis["marketPrice"]
    if analysis["direction"] == "YES":
        analysis["edge"] = round(est_prob - mkt_price, 4)
    else:
        analysis["edge"] = round(mkt_price - est_prob, 4)

    return analysis
