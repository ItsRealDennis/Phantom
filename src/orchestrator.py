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
from src.risk.position_sizer import size_position
from src.tracking.trade_logger import log_signal, get_bankroll
from src.config import STRATEGIES, VALID_TIMEFRAMES

logger = logging.getLogger(__name__)
console = Console()


def analyze_and_log(ticker: str, strategy: str, timeframe: str = "1d") -> dict:
    """
    Core pipeline: collect data -> Claude analysis -> filter -> size -> log.

    Returns dict with signal_id, passed, analysis, sizing, filter_reason.
    Called by both the CLI and the automation scanner.
    """
    ticker = ticker.upper()

    # Step 1: Collect market data
    market = collect_market_data(ticker, timeframe)

    # Step 2: Collect fundamentals & news
    try:
        fund_data = get_fundamentals(ticker)
        fund_summary = summarize_fundamentals(fund_data)
        news = get_news_headlines(ticker)
    except Exception as e:
        logger.warning("Fundamentals/news fetch failed for %s: %s", ticker, e)
        fund_data = {}
        fund_summary = "Unavailable"
        news = "Unavailable"

    # Step 3: Send to Claude
    analysis = analyze(
        ticker=ticker,
        strategy=strategy,
        timeframe=timeframe,
        ohlcv_summary=market["ohlcv_summary"],
        key_levels=market["key_levels"],
        volume_profile=market["volume_profile"],
        fundamentals_summary=fund_summary,
        news_headlines=news,
    )

    # Step 4: Apply filters
    passed, filter_reason = apply_filters(
        ticker=ticker,
        confidence=analysis["confidence"],
        rr_ratio=analysis["riskRewardRatio"],
        direction=analysis["direction"],
        sector=fund_data.get("sector", "Unknown"),
    )

    # Step 5: Position sizing (calculate even if filtered, for logging)
    bankroll = get_bankroll()
    sizing = size_position(
        confidence=analysis["confidence"],
        rr_ratio=analysis["riskRewardRatio"],
        bankroll=bankroll,
        entry_price=analysis["entry"],
        stop_loss=analysis["stopLoss"],
    )

    # Step 6: Log signal
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

    # Display analysis
    _display_analysis(analysis)

    # Display result
    if result["passed"]:
        console.print(Panel(
            f"[bold green]SIGNAL PASSED[/bold green] — ID #{result['signal_id']}\n"
            f"Direction: {analysis['direction']} | Confidence: {analysis['confidence']}%\n"
            f"Entry: ${analysis['entry']:.2f} | Stop: ${analysis['stopLoss']:.2f} | Target: ${analysis['takeProfit']:.2f}\n"
            f"Kelly: {sizing['kelly_pct']:.1f}% → Shrunk: {sizing['shrunk_kelly_pct']:.1f}% → Final: {sizing['final_risk_pct']:.1f}%\n"
            f"Risk: ${sizing['dollar_risk']:.2f} | Shares: {sizing['shares']} | Position: ${sizing['position_value']:.2f}" +
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
