"""Orchestrator — scan -> analyze -> filter -> log. The core loop."""

import logging
import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.collectors.market_data import collect_market_data
from src.collectors.fundamentals import get_fundamentals, summarize_fundamentals, get_news_headlines
from src.analysis.claude_analyst import analyze
from src.risk.trade_filter import apply_filters
from src.risk.position_sizer import size_position, adjust_stop_for_atr
from src.tracking.trade_logger import log_signal, get_bankroll
from src.config import STRATEGIES, VALID_TIMEFRAMES, FILTERS

logger = logging.getLogger(__name__)
console = Console()


def analyze_and_log(ticker: str, strategy: str, timeframe: str = "1d") -> dict:
    """
    Core pipeline: collect data -> Claude analysis -> filter -> size -> log.

    Returns dict with signal_id, passed, analysis, sizing, filter_reason.
    Called by both the CLI and the automation scanner.
    """
    ticker = ticker.upper()

    # Step 0: Circuit breaker pre-check (skip Claude call if halted)
    from src.risk.circuit_breakers import check_circuit_breakers
    cb_status = check_circuit_breakers()
    if not cb_status["trading_allowed"]:
        cb_reasons = "; ".join(cb_status["reasons"])
        logger.warning("Circuit breaker halted for %s: %s", ticker, cb_reasons)
        signal_id = log_signal(
            ticker=ticker, strategy=strategy, timeframe=timeframe,
            direction="N/A", confidence=0, entry_price=0, stop_loss=0,
            take_profit=0, rr_ratio=0, reasoning="Circuit breaker halted",
            confluences=[], warnings=cb_status["reasons"], key_risks="",
            kelly_pct=None, position_size=None, passed_filter=False,
            filter_reason=f"Circuit breaker: {cb_reasons}",
        )
        return {
            "signal_id": signal_id, "ticker": ticker, "strategy": strategy,
            "passed": False, "filter_reason": f"Circuit breaker: {cb_reasons}",
            "analysis": None, "sizing": None, "order": None,
        }

    # Step 0b: Quick position limit check (save Claude API cost)
    from src.tracking.trade_logger import count_open_positions, has_open_position
    if count_open_positions() >= FILTERS["max_open_positions"]:
        reason = f"At max positions ({FILTERS['max_open_positions']})"
        signal_id = log_signal(
            ticker=ticker, strategy=strategy, timeframe=timeframe,
            direction="N/A", confidence=0, entry_price=0, stop_loss=0,
            take_profit=0, rr_ratio=0, reasoning="Position limit reached",
            confluences=[], warnings=[], key_risks="",
            kelly_pct=None, position_size=None, passed_filter=False,
            filter_reason=reason,
        )
        return {
            "signal_id": signal_id, "ticker": ticker, "strategy": strategy,
            "passed": False, "filter_reason": reason,
            "analysis": None, "sizing": None, "order": None,
        }

    # Step 0c: Quick duplicate ticker check
    if has_open_position(ticker):
        reason = f"Already have open position in {ticker}"
        signal_id = log_signal(
            ticker=ticker, strategy=strategy, timeframe=timeframe,
            direction="N/A", confidence=0, entry_price=0, stop_loss=0,
            take_profit=0, rr_ratio=0, reasoning="Duplicate position",
            confluences=[], warnings=[], key_risks="",
            kelly_pct=None, position_size=None, passed_filter=False,
            filter_reason=reason,
        )
        return {
            "signal_id": signal_id, "ticker": ticker, "strategy": strategy,
            "passed": False, "filter_reason": reason,
            "analysis": None, "sizing": None, "order": None,
        }

    # Step 1: Collect market data
    market = collect_market_data(ticker, timeframe)

    # Step 1b: Extract indicators
    indicators = market.get("indicators", {})

    # Step 2: Collect fundamentals & news
    from src.config import is_crypto, alpaca_to_yfinance
    is_intraday = timeframe in ("5m", "15m", "1h")
    crypto = is_crypto(ticker)

    if crypto:
        # Crypto has no fundamentals — skip to save tokens and avoid errors
        fund_data = {}
        fund_summary = "Cryptocurrency — no fundamental data applicable"
        yf_sym = alpaca_to_yfinance(ticker)
        try:
            news = get_news_headlines(yf_sym)
        except Exception:
            news = "No crypto news available"
    else:
        try:
            fund_data = get_fundamentals(ticker)
            fund_summary = summarize_fundamentals(fund_data, mode="intraday" if is_intraday else "daily")
            news = get_news_headlines(ticker)
        except Exception as e:
            logger.warning("Fundamentals/news fetch failed for %s: %s", ticker, e)
            fund_data = {}
            fund_summary = "Unavailable"
            news = "Unavailable"

    # Step 3: Send to Claude (with indicators)
    analysis = analyze(
        ticker=ticker,
        strategy=strategy,
        timeframe=timeframe,
        ohlcv_summary=market["ohlcv_summary"],
        key_levels=market["key_levels"],
        volume_profile=market["volume_profile"],
        fundamentals_summary=fund_summary,
        news_headlines=news,
        indicators=indicators,
    )

    # Step 3b: Adjust stops with ATR (clamp to 1-3x ATR)
    atr = indicators.get("atr_14", 0)
    if atr > 0:
        adjusted = adjust_stop_for_atr(
            entry_price=analysis["entry"],
            stop_loss=analysis["stopLoss"],
            take_profit=analysis["takeProfit"],
            direction=analysis["direction"],
            atr=atr,
        )
        if adjusted["stop_adjusted"]:
            logger.info(
                "%s stop adjusted: $%.2f → $%.2f (%.1fx ATR)",
                ticker, analysis["stopLoss"], adjusted["stop_loss"], adjusted["atr_multiple"],
            )
            analysis["stopLoss"] = adjusted["stop_loss"]
            analysis["takeProfit"] = adjusted["take_profit"]
            # Recalculate R:R with adjusted levels
            stop_dist = abs(analysis["entry"] - adjusted["stop_loss"])
            tp_dist = abs(adjusted["take_profit"] - analysis["entry"])
            analysis["riskRewardRatio"] = round(tp_dist / stop_dist, 2) if stop_dist > 0 else 0

    # Step 4: Apply filters (with circuit breaker context)
    passed, filter_reason, filter_ctx = apply_filters(
        ticker=ticker,
        confidence=analysis["confidence"],
        rr_ratio=analysis["riskRewardRatio"],
        direction=analysis["direction"],
        sector=fund_data.get("sector", "Unknown"),
        atr=atr,
        entry=analysis["entry"],
        stop_loss=analysis["stopLoss"],
    )

    # Step 4b: Portfolio risk check (only if passed filter)
    if passed:
        from src.risk.portfolio_risk import check_portfolio_risk
        port_check = check_portfolio_risk(
            ticker=ticker,
            direction=analysis["direction"],
            dollar_risk=0,  # Will be computed after sizing; check direction/correlation/beta now
        )
        if not port_check["approved"]:
            passed = False
            filter_reason = f"Portfolio risk: {'; '.join(port_check['reasons'])}"
            logger.info("Portfolio risk blocked %s: %s", ticker, filter_reason)

    # Step 5: Position sizing (with Phase 2 multipliers)
    bankroll = get_bankroll()
    cb_size_mult = filter_ctx.get("cb_size_multiplier", 1.0)
    sizing = size_position(
        confidence=analysis["confidence"],
        rr_ratio=analysis["riskRewardRatio"],
        bankroll=bankroll,
        entry_price=analysis["entry"],
        stop_loss=analysis["stopLoss"],
        cb_size_multiplier=cb_size_mult,
        strategy=strategy,
    )

    # Step 5b: Re-check position limit right before logging (prevents race condition
    # where multiple signals pass the filter in the same scan cycle)
    if passed:
        from src.tracking.trade_logger import count_open_positions
        current_open = count_open_positions()
        if current_open >= FILTERS["max_open_positions"]:
            passed = False
            filter_reason = f"Position limit reached during scan ({current_open}/{FILTERS['max_open_positions']})"

    # Step 6: Log signal (with sector and beta)
    signal_id = log_signal(
        ticker=ticker,
        strategy=strategy,
        timeframe=timeframe,
        direction=analysis["direction"],
        confidence=analysis["confidence"],
        entry_price=analysis["entry"],
        stop_loss=analysis["stopLoss"],
        take_profit=analysis["takeProfit"],
        rr_ratio=analysis["riskRewardRatio"],
        reasoning=analysis["reasoning"],
        confluences=analysis["confluences"],
        warnings=analysis["warnings"],
        key_risks=analysis["keyRisks"],
        kelly_pct=sizing["kelly_pct"],
        position_size=sizing["dollar_risk"] if passed else None,
        passed_filter=passed,
        filter_reason=filter_reason,
        sector=fund_data.get("sector", "Unknown"),
        beta=fund_data.get("beta"),
    )

    # Step 7: Submit to Alpaca if enabled and signal passed
    order_result = None
    if passed:
        from src.execution.alpaca_client import is_alpaca_enabled
        if is_alpaca_enabled():
            from src.execution.order_manager import submit_bracket_order
            from src.tracking.trade_logger import update_alpaca_ids

            order_result = submit_bracket_order({
                "signal_id": signal_id,
                "ticker": ticker,
                "timeframe": timeframe,
                "analysis": analysis,
                "sizing": sizing,
            })
            if order_result.get("success"):
                update_alpaca_ids(
                    signal_id=signal_id,
                    order_id=order_result["order_id"],
                    tp_order_id=order_result.get("tp_order_id"),
                    sl_order_id=order_result.get("sl_order_id"),
                    shares=sizing["shares"],
                )
                logger.info("Alpaca bracket order placed for signal #%d", signal_id)
            else:
                logger.warning(
                    "Alpaca order failed for signal #%d: %s — falling back to paper mode",
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
    }


@click.command()
@click.option("--ticker", "-t", required=True, help="Ticker symbol (e.g. AAPL)")
@click.option(
    "--strategy", "-s", required=True,
    type=click.Choice(STRATEGIES + ["earnings_play"], case_sensitive=False),
    help="Strategy type",
)
@click.option(
    "--timeframe", "-tf", default="1d",
    type=click.Choice(VALID_TIMEFRAMES, case_sensitive=False),
    help="Timeframe for analysis",
)
def run(ticker: str, strategy: str, timeframe: str):
    """Analyze a ticker and generate a trading signal."""
    console.print(Panel(
        f"[bold cyan]PHANTOM[/bold cyan] — Signal Validator\n"
        f"Ticker: [bold]{ticker.upper()}[/bold] | Strategy: [bold]{strategy}[/bold] | TF: [bold]{timeframe}[/bold]",
        border_style="cyan",
    ))

    console.print("\n[dim]Collecting data and analyzing...[/dim]")
    try:
        result = analyze_and_log(ticker, strategy, timeframe)
    except Exception as e:
        console.print(f"[red]Failed: {e}[/red]")
        sys.exit(1)

    analysis = result["analysis"]
    sizing = result["sizing"]

    # If circuit breaker halted, analysis will be None
    if analysis is None:
        console.print(Panel(
            f"[bold red]CIRCUIT BREAKER[/bold red] — Trading halted\n"
            f"Reason: {result['filter_reason']}\n"
            f"[dim](Signal logged for tracking — no Claude analysis performed)[/dim]",
            border_style="red",
        ))
        return

    # Display analysis
    _display_analysis(analysis)

    # Display result
    if result["passed"]:
        mult_info = ""
        if sizing.get("combined_multiplier", 1.0) < 1.0:
            mult_info = f"\n[dim]Size multiplier: {sizing['combined_multiplier']:.2f}x[/dim]"
        console.print(Panel(
            f"[bold green]SIGNAL PASSED[/bold green] — ID #{result['signal_id']}\n"
            f"Direction: {analysis['direction']} | Confidence: {analysis['confidence']}%\n"
            f"Entry: ${analysis['entry']:.2f} | Stop: ${analysis['stopLoss']:.2f} | Target: ${analysis['takeProfit']:.2f}\n"
            f"Kelly: {sizing['kelly_pct']:.1f}% → Shrunk: {sizing['shrunk_kelly_pct']:.1f}% → Final: {sizing['final_risk_pct']:.1f}%\n"
            f"Risk: ${sizing['dollar_risk']:.2f} | Shares: {sizing['shares']} | Position: ${sizing['position_value']:.2f}"
            + mult_info +
            (f"\n[bold cyan]Alpaca order: {result['order']['order_id']}[/bold cyan]" if result.get("order", {}).get("success") else "") +
            (f"\n[yellow]Alpaca failed: {result['order']['error']}[/yellow]" if result.get("order") and not result["order"].get("success") else ""),
            border_style="green",
        ))
    else:
        console.print(Panel(
            f"[bold yellow]SIGNAL FILTERED[/bold yellow] — ID #{result['signal_id']}\n"
            f"Reason: {result['filter_reason']}\n"
            f"Direction: {analysis['direction']} | Confidence: {analysis['confidence']}%\n"
            f"Entry: ${analysis['entry']:.2f} | Stop: ${analysis['stopLoss']:.2f} | Target: ${analysis['takeProfit']:.2f}\n"
            f"[dim](Signal logged for tracking — will still measure outcome)[/dim]",
            border_style="yellow",
        ))


def _display_analysis(analysis: dict):
    """Pretty-print Claude's analysis."""
    table = Table(title="Claude Analysis", border_style="cyan")
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Direction", analysis["direction"])
    table.add_row("Confidence", f"{analysis['confidence']}%")
    table.add_row("Entry", f"${analysis['entry']:.2f}")
    table.add_row("Stop Loss", f"${analysis['stopLoss']:.2f}")
    table.add_row("Take Profit", f"${analysis['takeProfit']:.2f}")
    table.add_row("R:R Ratio", f"{analysis['riskRewardRatio']:.2f}")
    table.add_row("Reasoning", analysis["reasoning"])

    confluences = ", ".join(analysis["confluences"]) if analysis["confluences"] else "None"
    table.add_row("Confluences", confluences)

    warnings = ", ".join(analysis["warnings"]) if analysis["warnings"] else "None"
    table.add_row("Warnings", warnings)

    table.add_row("Key Risks", analysis["keyRisks"])

    console.print(table)


if __name__ == "__main__":
    run()
