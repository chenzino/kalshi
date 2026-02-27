#!/usr/bin/env python3
"""Quick analysis tool for reviewing collected data and strategy signals.

Usage:
    python3 analyze.py              # Today's summary
    python3 analyze.py signals      # Today's strategy signals
    python3 analyze.py prices       # Price data summary
    python3 analyze.py games        # Game data summary
    python3 analyze.py scan         # Run a live market scan now
    python3 analyze.py backtest     # Backtest strategies on collected data
"""
import sys
import os
import json
import glob
from datetime import datetime, timezone, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
EST = timezone(timedelta(hours=-5))


def today_str():
    return datetime.now(EST).strftime("%Y-%m-%d")


def load_jsonl(filepath):
    """Load a JSONL file."""
    if not os.path.exists(filepath):
        return []
    entries = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def cmd_summary():
    """Show today's data summary."""
    date = today_str()
    print(f"\n=== Data Summary for {date} ===\n")

    # Check all data directories
    dirs = {
        "Game snapshots": f"games/{date}.jsonl",
        "Market snapshots": f"market_snapshots/{date}.jsonl",
        "Price data": f"prices/{date}.jsonl",
        "Signals": f"signals/{date}.jsonl",
        "Trades": f"trades/{date}.jsonl",
    }

    for label, path in dirs.items():
        full = os.path.join(DATA_DIR, path)
        if os.path.exists(full):
            entries = load_jsonl(full)
            size_kb = os.path.getsize(full) / 1024
            print(f"  {label}: {len(entries)} entries ({size_kb:.1f} KB)")
        else:
            print(f"  {label}: no data")

    # Scan files
    scan_dir = os.path.join(DATA_DIR, "scans")
    if os.path.exists(scan_dir):
        scan_files = glob.glob(os.path.join(scan_dir, f"*{date}*"))
        for sf in scan_files:
            entries = load_jsonl(sf)
            name = os.path.basename(sf)
            print(f"  Scans ({name}): {len(entries)} scans")

    # Report
    report_path = os.path.join(DATA_DIR, "reports", f"{date}.json")
    if os.path.exists(report_path):
        with open(report_path) as f:
            report = json.load(f)
        print(f"\n  Daily report: {report.get('total_signals', 0)} signals, "
              f"{report.get('games_tracked', 0)} games, "
              f"{report.get('markets_tracked', 0)} markets")

    # Historical data
    print(f"\n--- Historical Data ---")
    for subdir in ["games", "market_snapshots", "prices", "signals", "trades", "scans", "reports"]:
        path = os.path.join(DATA_DIR, subdir)
        if os.path.exists(path):
            files = os.listdir(path)
            total_size = sum(os.path.getsize(os.path.join(path, f)) for f in files)
            print(f"  {subdir}/: {len(files)} files, {total_size/1024:.1f} KB")


def cmd_signals():
    """Show today's strategy signals."""
    date = today_str()
    filepath = os.path.join(DATA_DIR, "signals", f"{date}.jsonl")
    signals = load_jsonl(filepath)

    if not signals:
        print(f"No signals for {date}")
        return

    print(f"\n=== Strategy Signals for {date} ({len(signals)} total) ===\n")

    # Group by strategy
    by_strategy = defaultdict(list)
    for s in signals:
        by_strategy[s.get("strategy", "unknown")].append(s)

    for strat, sigs in sorted(by_strategy.items()):
        avg_edge = sum(s.get("edge", 0) for s in sigs) / len(sigs)
        avg_strength = sum(s.get("strength", 0) for s in sigs) / len(sigs)
        print(f"  {strat}: {len(sigs)} signals, avg edge: {avg_edge:.1f}c, avg strength: {avg_strength:.1f}")
        for s in sigs[-5:]:  # Last 5
            ctx = s.get("game_context", {})
            ts = datetime.fromtimestamp(s["ts"], EST).strftime("%I:%M %p")
            print(f"    [{ts}] {s['ticker'][:40]} | {s['side']} | edge={s['edge']}c | {s['reason'][:60]}")
        if len(sigs) > 5:
            print(f"    ... and {len(sigs) - 5} more")
        print()


def cmd_prices():
    """Show price data summary."""
    date = today_str()
    filepath = os.path.join(DATA_DIR, "prices", f"{date}.jsonl")
    entries = load_jsonl(filepath)

    if not entries:
        print(f"No price data for {date}")
        return

    print(f"\n=== Price Data for {date} ({len(entries)} snapshots) ===\n")

    # Group by ticker
    by_ticker = defaultdict(list)
    for e in entries:
        by_ticker[e.get("ticker", "")].append(e)

    # Sort by volume
    sorted_tickers = sorted(by_ticker.items(), key=lambda x: max(e.get("volume", 0) for e in x[1]), reverse=True)

    for ticker, snaps in sorted_tickers[:20]:
        prices = [s.get("last_price") or s.get("yes_bid") or 0 for s in snaps]
        vols = [s.get("volume", 0) for s in snaps]
        non_zero = [p for p in prices if p > 0]
        if non_zero:
            print(f"  {ticker[:50]}")
            print(f"    Snapshots: {len(snaps)} | Vol: {max(vols)} | Price: {min(non_zero)}-{max(non_zero)}")


def cmd_games():
    """Show game data summary."""
    date = today_str()
    filepath = os.path.join(DATA_DIR, "games", f"{date}.jsonl")
    entries = load_jsonl(filepath)

    if not entries:
        print(f"No game data for {date}")
        return

    print(f"\n=== Game Data for {date} ({len(entries)} snapshots) ===\n")

    by_game = defaultdict(list)
    for e in entries:
        by_game[e.get("espn_id") or e.get("name", "unknown")].append(e)

    for gid, snaps in by_game.items():
        first = snaps[0]
        last = snaps[-1]
        name = first.get("name", gid)
        print(f"  {name}")
        print(f"    Snapshots: {len(snaps)}")
        print(f"    Final: {last.get('away_score', 0)}-{last.get('home_score', 0)} "
              f"P{last.get('period', '?')} {last.get('clock', '?')}")


def cmd_scan():
    """Run a live market scan."""
    from bot.market_scanner import run_full_scan
    data = run_full_scan()
    s = data["summary"]
    print(f"\n{s['total_events']} events, {s['total_markets']} markets")
    print(f"Volume: {s['total_volume']:,}")
    print(f"Scan time: {s['scan_time']}s\n")

    # Show today's games with volume
    today_tag = datetime.now(EST).strftime("%y%b%d").upper()
    today_events = [e for e in data["events"] if today_tag in e.get("event_ticker", "")]

    if today_events:
        print(f"--- Today's Events ({len(today_events)}) ---")
        for e in sorted(today_events, key=lambda x: sum(m.get("volume", 0) for m in x["markets"]), reverse=True)[:15]:
            vol = sum(m.get("volume", 0) for m in e["markets"])
            print(f"  {e['title']} | {e['series']} | {len(e['markets'])} mkts | vol={vol}")
    else:
        print("No events tagged for today")


def cmd_backtest():
    """Backtest strategies on historical data."""
    print("\n=== Strategy Backtest ===\n")

    # Load all historical signals
    signals_dir = os.path.join(DATA_DIR, "signals")
    if not os.path.exists(signals_dir):
        print("No signal data available yet. Run the system during game time to collect data.")
        return

    all_signals = []
    for f in sorted(os.listdir(signals_dir)):
        if f.endswith(".jsonl"):
            signals = load_jsonl(os.path.join(signals_dir, f))
            all_signals.extend(signals)
            print(f"  {f}: {len(signals)} signals")

    if not all_signals:
        print("No signals to analyze.")
        return

    print(f"\nTotal signals: {len(all_signals)}")

    # Aggregate by strategy
    by_strat = defaultdict(list)
    for s in all_signals:
        by_strat[s.get("strategy", "unknown")].append(s)

    print("\n--- Strategy Breakdown ---")
    for strat, sigs in sorted(by_strat.items()):
        edges = [s.get("edge", 0) for s in sigs]
        strengths = [s.get("strength", 0) for s in sigs]
        print(f"  {strat}:")
        print(f"    Signals: {len(sigs)}")
        print(f"    Avg edge: {sum(edges)/len(edges):.1f}c")
        print(f"    Avg strength: {sum(strengths)/len(strengths):.1f}")
        print(f"    Max edge: {max(edges)}c")

        # Unique tickers
        tickers = set(s.get("ticker", "") for s in sigs)
        print(f"    Unique markets: {len(tickers)}")

    # Load price data to check if signals were correct
    prices_dir = os.path.join(DATA_DIR, "prices")
    if os.path.exists(prices_dir):
        print("\n--- Price Movement After Signals ---")
        print("(Requires multi-day data for full backtest)")

    print("\n[Backtest will improve as more data is collected]")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summary"

    commands = {
        "summary": cmd_summary,
        "signals": cmd_signals,
        "prices": cmd_prices,
        "games": cmd_games,
        "scan": cmd_scan,
        "backtest": cmd_backtest,
    }

    if cmd in commands:
        commands[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        print(f"Available: {', '.join(commands.keys())}")


if __name__ == "__main__":
    main()
