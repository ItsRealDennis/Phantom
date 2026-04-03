"""Dashboard — CLI display of all performance metrics."""

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.columns import Columns

from src.tracking.analytics import (
    get_overall_stats,
    get_strategy_breakdown,
    get_equity_curve,
    get_filtered_outcomes,
    get_recent_signals,
)
from src.config import STARTING_BANKROLL

console = Console()


@click.command()
@click.option("--recent", "-n", default=10, help="Number of recent signals to show")
def dashboard(recent: int):
    """Display the Phantom trading dashboard."""

    console.print(Panel(
        "[bold cyan]PHANTOM[/bold cyan] — Paper Trading Dashboard",
        border_style="cyan",
    ))

    # Overall stats
    stats = get_overall_stats()
    _display_overview(stats)

    # Strategy breakdown
    strategies = get_strategy_breakdown()
    if strategies:
        _display_strategy_table(strategies)

    # Filter validation
    filtered = get_filtered_outcomes()
    if filtered["total_tracked"] > 0:
        _display_filter_validation(filtered)

    # Equity curve (ASCII)
    curve = get_equity_curve()
    if curve:
        _display_equity_curve(curve)

    # Recent signals
    signals = get_recent_signals(recent)
    if signals:
        _display_recent_signals(signals)
    else:
        console.print("\n[dim]No signals yet. Run the orchestrator to generate signals.[/dim]")


def _display_overview(stats: dict):
    pnl_color = "green" if stats["total_pnl"] >= 0 else "red"

    overview = (
        f"Signals: {stats['total_signals']} total | "
        f"{stats['passed_filter']} passed | "
        f"{stats['filtered_out']} filtered | "
        f"{stats['open']} open\n"
        f"Settled: {stats['settled']} | "
        f"Wins: {stats['wins']} | "
        f"Losses: {stats['losses']} | "
        f"Win Rate: [bold]{stats['win_rate']}%[/bold]\n"
        f"P&L: [{pnl_color}]${stats['total_pnl']:+,.2f}[/{pnl_color}] | "
        f"ROI: [{pnl_color}]{stats['roi']:+.1f}%[/{pnl_color}] | "
        f"Bankroll: ${stats['bankroll']:,.2f}"
    )

    console.print(Panel(overview, title="Overview", border_style="cyan"))


def _display_strategy_table(strategies: list[dict]):
    table = Table(title="Strategy Breakdown", border_style="cyan")
    table.add_column("Strategy", style="bold")
    table.add_column("Signals", justify="right")
    table.add_column("Passed", justify="right")
    table.add_column("Settled", justify="right")
    table.add_column("W", justify="right")
    table.add_column("L", justify="right")
    table.add_column("Win%", justify="right")
    table.add_column("P&L", justify="right")

    for s in strategies:
        pnl_str = f"${s['pnl']:+,.2f}"
        pnl_style = "green" if s["pnl"] >= 0 else "red"
        wr_style = "green" if s["win_rate"] >= 55 else ("yellow" if s["win_rate"] >= 50 else "red")

        table.add_row(
            s["strategy"],
            str(s["total"]),
            str(s["passed"]),
            str(s["settled"]),
            str(s["wins"]),
            str(s["losses"]),
            f"[{wr_style}]{s['win_rate']}%[/{wr_style}]",
            f"[{pnl_style}]{pnl_str}[/{pnl_style}]",
        )

    console.print(table)


def _display_filter_validation(filtered: dict):
    console.print(Panel(
        f"Filtered signals tracked: {filtered['total_tracked']}\n"
        f"Would have won: {filtered['would_have_won']} | "
        f"Would have lost: {filtered['would_have_lost']}\n"
        f"Hypothetical win rate: {filtered['hypothetical_win_rate']}%\n"
        f"[dim](Lower than main win rate = filter is working)[/dim]",
        title="Filter Validation",
        border_style="yellow",
    ))


def _display_equity_curve(curve: list[tuple[str, float]]):
    """Simple ASCII equity curve."""
    if len(curve) < 2:
        return

    values = [v for _, v in curve]
    min_val = min(values)
    max_val = max(values)
    val_range = max_val - min_val if max_val != min_val else 1

    width = min(60, len(curve))
    height = 10

    # Resample if too many points
    if len(curve) > width:
        step = len(curve) / width
        sampled = [curve[int(i * step)] for i in range(width)]
    else:
        sampled = curve

    lines = []
    lines.append(f"  ${max_val:>10,.2f} ┤")

    for row in range(height - 1, -1, -1):
        threshold = min_val + (val_range * row / height)
        line = "             │"
        for _, val in sampled:
            if val >= threshold:
                line += "█"
            else:
                line += " "
        lines.append(line)

    lines.append(f"  ${min_val:>10,.2f} ┤{'─' * len(sampled)}")
    lines.append(f"              {sampled[0][0]}{'─' * (len(sampled) - 20)}{sampled[-1][0]}" if len(sampled) > 20 else "")

    curve_text = "\n".join(lines)
    console.print(Panel(curve_text, title="Equity Curve", border_style="cyan"))


def _display_recent_signals(signals: list[dict]):
    table = Table(title="Recent Signals", border_style="cyan")
    table.add_column("ID", style="bold")
    table.add_column("Date")
    table.add_column("Ticker")
    table.add_column("Strategy")
    table.add_column("Dir")
    table.add_column("Conf")
    table.add_column("Entry")
    table.add_column("R:R")
    table.add_column("Filter")
    table.add_column("Status")
    table.add_column("P&L")

    for s in signals:
        status = s["status"]
        if status == "won":
            status_style = "[green]WON[/green]"
        elif status in ("lost", "stopped"):
            status_style = f"[red]{status.upper()}[/red]"
        elif status == "open":
            status_style = "[cyan]OPEN[/cyan]"
        elif status == "filtered":
            status_style = "[dim]FILTERED[/dim]"
        else:
            status_style = status

        filter_str = "[green]PASS[/green]" if s["passed_filter"] else f"[yellow]NO[/yellow]"
        pnl_str = f"${s['real_pnl']:+,.2f}" if s["real_pnl"] is not None else "-"
        pnl_color = "green" if (s["real_pnl"] or 0) >= 0 else "red"

        table.add_row(
            str(s["id"]),
            s["created_at"][:10] if s["created_at"] else "",
            s["ticker"],
            s["strategy"],
            s["direction"],
            f"{s['confidence']}%",
            f"${s['entry_price']:.2f}",
            f"{s['rr_ratio']:.2f}",
            filter_str,
            status_style,
            f"[{pnl_color}]{pnl_str}[/{pnl_color}]" if s["real_pnl"] is not None else "-",
        )

    console.print(table)


if __name__ == "__main__":
    dashboard()
