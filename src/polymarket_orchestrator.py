"""Polymarket orchestrator — scan → analyze → filter → size → execute → log."""

import logging

from src.collectors.polymarket_data import collect_market_context
from src.collectors.polymarket_scanner import run_polymarket_scan
from src.analysis.polymarket_analyst import analyze_market
from src.tracking.trade_logger import (
    log_signal, get_bankroll, count_open_positions, has_open_position,
)
from src.risk.circuit_breakers import check_circuit_breakers
from src.config import POLYMARKET_FILTERS, POLYMARKET_MAX_SIGNALS

logger = logging.getLogger(__name__)


def _calculate_kelly(confidence: float, edge: float, market_price: float, direction: str) -> dict:
    """
    Kelly Criterion for binary outcomes.

    For prediction markets:
      Kelly fraction = (p * b - q) / b
      where p = estimated prob of winning, b = net odds, q = 1-p

    For buying YES at price P with estimated prob E:
      Win payout: $1 - P per share (if correct)
      Loss: P per share (if wrong)
      b = (1 - P) / P
      p = E

    For buying NO at price (1-P) with estimated prob (1-E):
      Win payout: P per share
      Loss: 1-P per share
      b = P / (1-P)
      p = 1-E
    """
    shrinkage = POLYMARKET_FILTERS["edge_shrinkage"]
    max_risk_pct = POLYMARKET_FILTERS["max_position_pct"]

    if direction == "YES":
        p = confidence / 100.0  # Probability of YES
        cost_per_share = market_price
        payout_per_share = 1.0 - market_price
    else:
        p = 1.0 - (confidence / 100.0)  # Probability of NO winning = 1 - P(YES)
        # When buying NO: we think YES prob < market, so we estimate P(NO) = 1 - our_est
        p = 1.0 - (confidence / 100.0)
        # Actually: confidence is our estimate that the trade wins
        # If direction=NO, our estimated prob of NO = confidence/100
        p = confidence / 100.0
        cost_per_share = 1.0 - market_price
        payout_per_share = market_price

    if cost_per_share <= 0 or payout_per_share <= 0:
        return {"kelly_pct": 0, "shrunk_kelly_pct": 0, "final_risk_pct": 0,
                "dollar_risk": 0, "shares": 0, "cost_per_share": 0}

    b = payout_per_share / cost_per_share  # Net odds
    q = 1.0 - p

    raw_kelly = (p * b - q) / b if b > 0 else 0
    raw_kelly = max(0, raw_kelly)

    shrunk_kelly = raw_kelly * shrinkage
    final_risk_pct = min(shrunk_kelly, max_risk_pct)

    return {
        "kelly_pct": round(raw_kelly * 100, 2),
        "shrunk_kelly_pct": round(shrunk_kelly * 100, 2),
        "final_risk_pct": round(final_risk_pct * 100, 2),
        "cost_per_share": cost_per_share,
        "payout_per_share": payout_per_share,
    }


def analyze_and_log_market(market: dict, strategy: str) -> dict:
    """
    Core Polymarket pipeline: collect context → Claude analysis → filter → size → log.

    Args:
        market: Market dict from Gamma API
        strategy: One of 'mispricing', 'event_catalyst', 'momentum'

    Returns:
        Dict with signal_id, passed, analysis, sizing, order result.
    """
    question = market.get("question", "Unknown")
    condition_id = market.get("conditionId", market.get("condition_id", ""))
    slug = market.get("slug", condition_id[:20])

    # Use slug as "ticker" for Polymarket signals
    ticker = f"PM:{slug}"

    # Step 0: Circuit breaker check
    cb_status = check_circuit_breakers()
    if not cb_status["trading_allowed"]:
        cb_reasons = "; ".join(cb_status["reasons"])
        logger.warning("Circuit breaker halted for %s: %s", ticker, cb_reasons)
        signal_id = log_signal(
            ticker=ticker, strategy=f"pm_{strategy}", timeframe="event",
            direction="N/A", confidence=0, entry_price=0, stop_loss=0,
            take_profit=1.0, rr_ratio=0, reasoning="Circuit breaker halted",
            confluences=[], warnings=cb_status["reasons"], key_risks="",
            kelly_pct=None, position_size=None, passed_filter=False,
            filter_reason=f"Circuit breaker: {cb_reasons}",
        )
        return {
            "signal_id": signal_id, "ticker": ticker, "strategy": strategy,
            "passed": False, "filter_reason": f"Circuit breaker: {cb_reasons}",
            "analysis": None, "sizing": None, "order": None,
        }

    # Step 0b: Position limits
    if count_open_positions() >= POLYMARKET_FILTERS["max_open_positions"]:
        reason = f"At max positions ({POLYMARKET_FILTERS['max_open_positions']})"
        signal_id = log_signal(
            ticker=ticker, strategy=f"pm_{strategy}", timeframe="event",
            direction="N/A", confidence=0, entry_price=0, stop_loss=0,
            take_profit=1.0, rr_ratio=0, reasoning="Position limit reached",
            confluences=[], warnings=[], key_risks="",
            kelly_pct=None, position_size=None, passed_filter=False,
            filter_reason=reason,
        )
        return {
            "signal_id": signal_id, "ticker": ticker, "strategy": strategy,
            "passed": False, "filter_reason": reason,
            "analysis": None, "sizing": None, "order": None,
        }

    # Step 0c: Duplicate check
    if has_open_position(ticker):
        reason = f"Already have position in {ticker}"
        signal_id = log_signal(
            ticker=ticker, strategy=f"pm_{strategy}", timeframe="event",
            direction="N/A", confidence=0, entry_price=0, stop_loss=0,
            take_profit=1.0, rr_ratio=0, reasoning="Duplicate position",
            confluences=[], warnings=[], key_risks="",
            kelly_pct=None, position_size=None, passed_filter=False,
            filter_reason=reason,
        )
        return {
            "signal_id": signal_id, "ticker": ticker, "strategy": strategy,
            "passed": False, "filter_reason": reason,
            "analysis": None, "sizing": None, "order": None,
        }

    # Step 1: Collect market context
    context = collect_market_context(market)
    if "error" in context:
        logger.error("Failed to collect context for %s: %s", ticker, context["error"])
        return {
            "signal_id": None, "ticker": ticker, "strategy": strategy,
            "passed": False, "filter_reason": f"Data error: {context['error']}",
            "analysis": None, "sizing": None, "order": None,
        }

    # Step 2: Claude analysis
    analysis = analyze_market(
        market_context=context,
        strategy=strategy,
    )

    direction = analysis["direction"]  # "YES" or "NO"
    edge = analysis["edge"]
    confidence = analysis["confidence"]
    est_prob = analysis["estimatedProbability"]
    market_price = context["yes_price"]

    # For signal logging, map to price-based fields
    if direction == "YES":
        entry_price = market_price
        take_profit = 1.0
        stop_loss = 0.0
        rr_ratio = (1.0 - market_price) / market_price if market_price > 0 else 0
    else:
        entry_price = 1.0 - market_price
        take_profit = 1.0
        stop_loss = 0.0
        rr_ratio = market_price / (1.0 - market_price) if market_price < 1 else 0

    # Step 3: Apply filters
    passed = True
    filter_reason = None

    if confidence < POLYMARKET_FILTERS["min_confidence"]:
        passed = False
        filter_reason = f"Low confidence: {confidence}% < {POLYMARKET_FILTERS['min_confidence']}%"

    elif edge < POLYMARKET_FILTERS["min_edge"]:
        passed = False
        filter_reason = f"Insufficient edge: {edge:.1%} < {POLYMARKET_FILTERS['min_edge']:.1%}"

    elif context["spread"] > 0.05:
        passed = False
        filter_reason = f"Wide spread: {context['spread']:.1%}"

    elif context["volume_24h"] < POLYMARKET_FILTERS["min_volume"]:
        passed = False
        filter_reason = f"Low volume: ${context['volume_24h']:.0f}"

    # Step 4: Position sizing (Kelly for binary outcomes)
    sizing = _calculate_kelly(confidence, edge, market_price, direction)
    bankroll = get_bankroll()

    dollar_risk = bankroll * (sizing["final_risk_pct"] / 100.0)
    shares = int(dollar_risk / sizing["cost_per_share"]) if sizing["cost_per_share"] > 0 else 0
    total_cost = shares * sizing["cost_per_share"]

    sizing["dollar_risk"] = round(dollar_risk, 2)
    sizing["shares"] = shares
    sizing["total_cost"] = round(total_cost, 2)
    sizing["position_value"] = round(total_cost, 2)

    # Step 5: Log signal
    signal_id = log_signal(
        ticker=ticker,
        strategy=f"pm_{strategy}",
        timeframe="event",
        direction=direction,
        confidence=confidence,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        rr_ratio=round(rr_ratio, 2),
        reasoning=analysis["reasoning"],
        confluences=analysis.get("evidenceFor", []),
        warnings=analysis.get("risks", []),
        key_risks=analysis["keyRisks"],
        kelly_pct=sizing["kelly_pct"],
        position_size=sizing["dollar_risk"] if passed else None,
        passed_filter=passed,
        filter_reason=filter_reason,
    )

    # Step 6: Execute order if passed
    order_result = None
    if passed:
        from src.execution.polymarket_client import is_polymarket_enabled
        if is_polymarket_enabled():
            from src.execution.polymarket_orders import submit_order
            from src.tracking.trade_logger import update_alpaca_ids

            # Determine which token to buy
            if direction == "YES":
                token_id = context["yes_token_id"]
                order_price = market_price
            else:
                token_id = context["no_token_id"]
                order_price = 1.0 - market_price

            order_result = submit_order(
                token_id=token_id,
                side="BUY",
                price=order_price,
                size=shares,
                tick_size=context.get("tick_size", "0.01"),
                neg_risk=context.get("neg_risk", False),
            )

            if order_result.get("success"):
                update_alpaca_ids(
                    signal_id=signal_id,
                    order_id=order_result["order_id"],
                    tp_order_id=None,
                    sl_order_id=None,
                    shares=shares,
                )
                logger.info("Polymarket order placed for signal #%d: %s %s", signal_id, direction, ticker)
            else:
                logger.warning(
                    "Polymarket order failed for signal #%d: %s — paper mode",
                    signal_id, order_result.get("error"),
                )

    return {
        "signal_id": signal_id,
        "ticker": ticker,
        "strategy": strategy,
        "passed": passed,
        "filter_reason": filter_reason,
        "analysis": analysis,
        "sizing": sizing,
        "order": order_result,
        "market_context": {
            "question": context["question"],
            "yes_price": context["yes_price"],
            "edge": edge,
            "volume_24h": context["volume_24h"],
        },
    }


def run_polymarket_cycle():
    """
    Full Polymarket scan cycle — called by scheduler.

    Scans for interesting markets → analyzes top hits → filters → executes.
    """
    logger.info("=== Polymarket scan cycle starting ===")

    hits = run_polymarket_scan()
    if not hits:
        logger.info("No Polymarket hits this cycle")
        return []

    # Limit Claude API calls
    hits = hits[:POLYMARKET_MAX_SIGNALS]
    logger.info("Analyzing %d Polymarket markets...", len(hits))

    results = []
    for hit in hits:
        try:
            result = analyze_and_log_market(
                market=hit["market"],
                strategy=hit["strategy"],
            )
            results.append(result)

            if result["passed"]:
                logger.info(
                    "PASSED: %s | %s | Edge: %.1f%% | Confidence: %d%%",
                    result["ticker"],
                    result["analysis"]["direction"],
                    result["analysis"]["edge"] * 100,
                    result["analysis"]["confidence"],
                )
        except Exception as e:
            logger.error("Failed to analyze %s: %s", hit.get("market", {}).get("slug", "?"), e)

    passed = [r for r in results if r["passed"]]
    logger.info(
        "=== Polymarket cycle done: %d analyzed, %d passed ===",
        len(results), len(passed),
    )
    return results
