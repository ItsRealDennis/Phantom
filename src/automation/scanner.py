"""Auto-scanner — run screeners on watchlist and analyze hits via Claude."""

import logging
import time

from src.collectors.screener import screen_mean_reversion, screen_breakout, screen_momentum, screen_crypto
from src.orchestrator import analyze_and_log
from src.config import SCAN_WATCHLIST, SCAN_TIMEFRAME, MAX_SIGNALS_PER_CYCLE

logger = logging.getLogger(__name__)


def run_scan_cycle(
    watchlist: list[str] | None = None,
    timeframe: str | None = None,
) -> list[dict]:
    """
    Run all screeners, deduplicate hits, analyze via Claude, return results.
    Caps at MAX_SIGNALS_PER_CYCLE Claude calls per run.
    """
    wl = watchlist or SCAN_WATCHLIST  # None falls through to DEFAULT_WATCHLIST in screener
    tf = timeframe or SCAN_TIMEFRAME

    logger.info("Scan cycle starting — watchlist: %s, timeframe: %s", wl or "default", tf)

    # Run all three screeners
    all_setups = []
    for name, screener_fn in [
        ("mean_reversion", screen_mean_reversion),
        ("breakout", screen_breakout),
        ("momentum", screen_momentum),
    ]:
        try:
            hits = screener_fn(watchlist=wl, timeframe=tf)
            logger.info("Screener %s found %d setups", name, len(hits))
            all_setups.extend(hits)
        except Exception as e:
            logger.error("Screener %s failed: %s", name, e)

    if not all_setups:
        logger.info("Scan cycle complete — no setups found")
        return []

    # Deduplicate by ticker (keep the first occurrence, which is highest-ranked per screener)
    seen_tickers = set()
    unique_setups = []
    for setup in all_setups:
        if setup["ticker"] not in seen_tickers:
            seen_tickers.add(setup["ticker"])
            unique_setups.append(setup)

    logger.info("After dedup: %d unique setups (cap: %d)", len(unique_setups), MAX_SIGNALS_PER_CYCLE)

    # Analyze each setup via Claude (capped)
    results = []
    for setup in unique_setups[:MAX_SIGNALS_PER_CYCLE]:
        try:
            result = analyze_and_log(
                ticker=setup["ticker"],
                strategy=setup["strategy"],
                timeframe=tf,
            )
            results.append(result)
            status = "PASSED" if result["passed"] else f"FILTERED ({result['filter_reason']})"
            logger.info(
                "Signal #%d: %s %s %s — %s",
                result["signal_id"], setup["ticker"], setup["strategy"],
                result["analysis"]["direction"], status,
            )
            # Brief pause between Claude calls to be respectful
            time.sleep(1)
        except Exception as e:
            logger.error("Analysis failed for %s (%s): %s", setup["ticker"], setup["strategy"], e)

    logger.info(
        "Scan cycle complete — %d setups analyzed, %d passed filters",
        len(results),
        sum(1 for r in results if r["passed"]),
    )

    return results


def run_crypto_scan(timeframe: str | None = None) -> list[dict]:
    """Run crypto screener and analyze hits via Claude. Runs 24/7."""
    tf = timeframe or SCAN_TIMEFRAME

    logger.info("Crypto scan starting — timeframe: %s", tf)

    crypto_setups = screen_crypto(timeframe=tf)
    if not crypto_setups:
        logger.info("Crypto scan complete — no setups found")
        return []

    logger.info("Crypto screener found %d setups (cap: %d)", len(crypto_setups), MAX_SIGNALS_PER_CYCLE)

    results = []
    for setup in crypto_setups[:MAX_SIGNALS_PER_CYCLE]:
        try:
            result = analyze_and_log(
                ticker=setup["ticker"],
                strategy=setup["strategy"],
                timeframe=tf,
            )
            results.append(result)
            status = "PASSED" if result["passed"] else f"FILTERED ({result['filter_reason']})"
            logger.info(
                "Crypto signal #%d: %s %s %s — %s",
                result["signal_id"], setup["ticker"], setup["strategy"],
                result["analysis"]["direction"], status,
            )
            time.sleep(1)
        except Exception as e:
            logger.error("Crypto analysis failed for %s: %s", setup["ticker"], e)

    logger.info(
        "Crypto scan complete — %d analyzed, %d passed",
        len(results), sum(1 for r in results if r["passed"]),
    )

    return results
