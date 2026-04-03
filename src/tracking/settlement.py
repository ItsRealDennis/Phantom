"""Settlement — mark trades as won/lost/stopped, calculate P&L."""

import click
from rich.console import Console
from rich.table import Table

from src.tracking.trade_logger import get_open_trades, settle_trade, get_connection

console = Console()


@click.command()
@click.option("--id", "signal_id", type=int, default=None, help="Settle a specific signal by ID")
@click.option("--status", type=click.Choice(["won", "lost", "stopped", "expired"]), help="Outcome")
@click.option("--exit-price", type=float, default=None, help="Actual exit price (calculates P&L)")
@click.option("--pnl", type=float, default=None, help="Manual P&L override")
@click.option("--notes", default="", help="Settlement notes")
@click.option("--list", "list_open", is_flag=True, help="List all open trades")
def settle(signal_id, status, exit_price, pnl, notes, list_open):
    """Settle open trades or list them."""
    if list_open or (signal_id is None and status is None):
        _list_open_trades()
        return

    if signal_id is None:
        console.print("[red]Provide --id to settle a specific trade.[/red]")
        return

    if status is None:
        console.print("[red]Provide --status (won/lost/stopped/expired).[/red]")
        return

    # Look up the trade
    conn = get_connection()
    row = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
    conn.close()

    if row is None:
        console.print(f"[red]Signal #{signal_id} not found.[/red]")
        return

    if row["status"] != "open":
        console.print(f"[yellow]Signal #{signal_id} is already '{row['status']}'.[/yellow]")
        return

    # Calculate P&L
    if pnl is not None:
        real_pnl = pnl
    elif exit_price is not None:
        # P&L based on position size and price movement
        risk_per_share = abs(row["entry_price"] - row["stop_loss"])
        if risk_per_share > 0 and row["position_size"]:
            shares = int(row["position_size"] / risk_per_share)
            if row["direction"] == "LONG":
                real_pnl = shares * (exit_price - row["entry_price"])
            else:
                real_pnl = shares * (row["entry_price"] - exit_price)
        else:
            real_pnl = 0.0
    else:
        # Estimate P&L from outcome
        if status == "won":
            real_pnl = row["position_size"] * row["rr_ratio"] if row["position_size"] else 0
        elif status in ("lost", "stopped"):
            real_pnl = -(row["position_size"] or 0)
        else:
            real_pnl = 0.0

    settle_trade(signal_id, status, real_pnl, notes)

    color = "green" if real_pnl >= 0 else "red"
    console.print(
        f"[{color}]Signal #{signal_id} ({row['ticker']}) settled as {status.upper()} "
        f"— P&L: ${real_pnl:+,.2f}[/{color}]"
    )


def _list_open_trades():
    """Display all open trades."""
    trades = get_open_trades()
    if not trades:
        console.print("[dim]No open trades.[/dim]")
        return

    table = Table(title="Open Trades", border_style="cyan")
    table.add_column("ID", style="bold")
    table.add_column("Date")
    table.add_column("Ticker")
    table.add_column("Strategy")
    table.add_column("Dir")
    table.add_column("Conf")
    table.add_column("Entry")
    table.add_column("Stop")
    table.add_column("Target")
    table.add_column("R:R")
    table.add_column("Risk $")

    for t in trades:
        table.add_row(
            str(t["id"]),
            t["created_at"][:16] if t["created_at"] else "",
            t["ticker"],
            t["strategy"],
            t["direction"],
            f"{t['confidence']}%",
            f"${t['entry_price']:.2f}",
            f"${t['stop_loss']:.2f}",
            f"${t['take_profit']:.2f}",
            f"{t['rr_ratio']:.2f}",
            f"${t['position_size']:.2f}" if t["position_size"] else "-",
        )

    console.print(table)


if __name__ == "__main__":
    settle()
