#!/usr/bin/env python3
"""Analysis CLI for the Kalshi CBB trading system.

Usage:
    python3 analyze.py              # Today's summary
    python3 analyze.py signals      # Today's strategy signals
    python3 analyze.py prices       # Price data summary
    python3 analyze.py games        # Game data summary
    python3 analyze.py scan         # Run a live market scan now
    python3 analyze.py learn        # Run learning analysis on today's session
    python3 analyze.py report       # Show cumulative learnings across all sessions
    python3 analyze.py strategies   # Deep dive on strategy performance
    python3 analyze.py paper        # Paper trading P&L summary
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

    scan_dir = os.path.join(DATA_DIR, "scans")
    if os.path.exists(scan_dir):
        scan_files = glob.glob(os.path.join(scan_dir, f"*{date}*"))
        for sf in scan_files:
            entries = load_jsonl(sf)
            name = os.path.basename(sf)
            print(f"  Scans ({name}): {len(entries)} scans")

    # Learning data
    learn_path = os.path.join(DATA_DIR, "learning", "sessions", f"{date}.json")
    if os.path.exists(learn_path):
        with open(learn_path) as f:
            lr = json.load(f)
        paper = lr.get("paper_trades", {})
        print(f"\n  Learning: {lr.get('data_summary',{}).get('signals',0)} signals graded")
        print(f"  Paper P&L: {paper.get('total_net_pnl',0)}c ({paper.get('trades',0)} trades, "
              f"{paper.get('win_rate',0)}% win rate)")

    print(f"\n--- Historical Data ---")
    for subdir in ["games", "market_snapshots", "prices", "signals", "trades", "scans", "reports", "learning"]:
        path = os.path.join(DATA_DIR, subdir)
        if os.path.exists(path):
            total_files = 0
            total_size = 0
            for root, dirs, files in os.walk(path):
                total_files += len(files)
                total_size += sum(os.path.getsize(os.path.join(root, f)) for f in files)
            print(f"  {subdir}/: {total_files} files, {total_size/1024:.1f} KB")


def cmd_signals():
    """Show today's strategy signals."""
    date = today_str()
    filepath = os.path.join(DATA_DIR, "signals", f"{date}.jsonl")
    signals = load_jsonl(filepath)

    if not signals:
        print(f"No signals for {date}")
        return

    print(f"\n=== Strategy Signals for {date} ({len(signals)} total) ===\n")

    by_strategy = defaultdict(list)
    for s in signals:
        by_strategy[s.get("strategy", "unknown")].append(s)

    for strat, sigs in sorted(by_strategy.items()):
        avg_edge = sum(s.get("edge", 0) for s in sigs) / len(sigs)
        avg_strength = sum(s.get("strength", 0) for s in sigs) / len(sigs)
        print(f"  {strat}: {len(sigs)} signals, avg edge: {avg_edge:.1f}c, avg strength: {avg_strength:.1f}")
        for s in sigs[-5:]:
            ts = datetime.fromtimestamp(s["ts"], EST).strftime("%I:%M %p")
            mp = s.get("market_price", "?")
            fv = s.get("model_fv", "?")
            print(f"    [{ts}] {s['side'].upper()} | mkt={mp}c fv={fv}c | edge={s['edge']}c str={s['strength']} | {s['reason'][:55]}")
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

    by_ticker = defaultdict(list)
    for e in entries:
        by_ticker[e.get("ticker", "")].append(e)

    sorted_tickers = sorted(by_ticker.items(), key=lambda x: max(e.get("volume", 0) for e in x[1]), reverse=True)

    for ticker, snaps in sorted_tickers[:20]:
        prices = [s.get("last_price") or s.get("yes_bid") or 0 for s in snaps]
        vols = [s.get("volume", 0) for s in snaps]
        non_zero = [p for p in prices if p > 0]
        if non_zero:
            print(f"  {ticker[:55]}")
            print(f"    {len(snaps)} snaps | Vol: {max(vols):,} | Price: {min(non_zero)}-{max(non_zero)}c")


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
        print(f"    {len(snaps)} snapshots | Final: {last.get('away_score',0)}-{last.get('home_score',0)} "
              f"P{last.get('period','?')} {last.get('clock','?')}")


def cmd_scan():
    """Run a live market scan."""
    from bot.market_scanner import run_full_scan
    data = run_full_scan()
    s = data["summary"]
    print(f"\n{s['total_events']} events, {s['total_markets']} markets")
    print(f"Volume: {s['total_volume']:,}")
    print(f"Scan time: {s['scan_time']}s\n")

    today_tag = datetime.now(EST).strftime("%y%b%d").upper()
    today_events = [e for e in data["events"] if today_tag in e.get("event_ticker", "")]

    if today_events:
        print(f"--- Today's Events ({len(today_events)}) ---")
        for e in sorted(today_events, key=lambda x: sum(m.get("volume", 0) for m in x["markets"]), reverse=True)[:15]:
            vol = sum(m.get("volume", 0) for m in e["markets"])
            print(f"  {e['title']} | {e['series']} | {len(e['markets'])} mkts | vol={vol:,}")
    else:
        print("No events tagged for today")


def cmd_learn():
    """Run learning analysis on today's data."""
    from bot.learner import run_session_analysis
    report = run_session_analysis()
    if not report:
        print("No data to analyze yet. Run the system during games first.")
        return

    # Show detailed results
    print(f"\n--- Signal Grades ---")
    grades = report.get("signal_grades", [])
    grade_counts = defaultdict(int)
    for g in grades:
        grade_counts[g.get("grade", "unknown")] += 1
    for grade, count in sorted(grade_counts.items()):
        print(f"  {grade}: {count}")

    print(f"\n--- Model Calibration ---")
    cal = report.get("model_calibration", {})
    if cal.get("sigma_estimate"):
        print(f"  Observed sigma: {cal['sigma_estimate']} (current: 11.0)")
    if cal.get("bias") is not None:
        print(f"  Model bias: {cal['bias']:+.1f}c")

    recs = report.get("parameter_recommendations", {})
    if recs:
        print(f"\n--- Recommendations ---")
        for key, rec in recs.items():
            print(f"  {key}: {rec.get('reason', '')}")


def cmd_report():
    """Show cumulative learnings across all sessions."""
    from bot.learner import load_cumulative_learnings
    cum = load_cumulative_learnings()

    print(f"\n=== Cumulative Learnings ===")
    print(f"  Sessions analyzed: {cum['sessions_analyzed']}")
    print(f"  Total signals: {cum['total_signals']}")

    if cum.get("strategy_performance"):
        print(f"\n--- Strategy Performance (All Time) ---")
        for strat, perf in sorted(cum["strategy_performance"].items()):
            print(f"  {strat}:")
            print(f"    Signals: {perf.get('total_signals',0)} | Graded: {perf.get('total_graded',0)}")
            print(f"    Win rate: {perf.get('cumulative_win_rate',0)}% | "
                  f"Cumulative P&L: {perf.get('cumulative_pnl',0):.0f}c")

    pp = cum.get("paper_portfolio", {})
    if pp.get("trades", 0) > 0:
        print(f"\n--- Paper Portfolio ---")
        print(f"  Trades: {pp['trades']} | Wins: {pp['wins']} | Losses: {pp['losses']}")
        wr = round(pp['wins'] / max(1, pp['wins'] + pp['losses']) * 100, 1)
        print(f"  Win rate: {wr}% | Total P&L: {pp['total_pnl_cents']}c (${pp['total_pnl_cents']/100:.2f})")
        print(f"  Best trade: {pp['best_trade']}c | Worst: {pp['worst_trade']}c")

    sigma_obs = cum.get("model_calibration", {}).get("sigma_observations", [])
    if sigma_obs:
        print(f"\n--- Sigma Observations ---")
        for obs in sigma_obs[-5:]:
            print(f"  {obs['date']}: sigma={obs['sigma']}")
        avg_sigma = sum(o["sigma"] for o in sigma_obs) / len(sigma_obs)
        print(f"  Average observed sigma: {avg_sigma:.1f} (model uses 11.0)")

    params = cum.get("parameter_history", [])
    if params:
        print(f"\n--- Recent Parameter Recommendations ---")
        for p in params[-3:]:
            print(f"  {p['date']}:")
            for key, rec in p.get("recommendations", {}).items():
                print(f"    {key}: {rec.get('reason', '')}")


def cmd_strategies():
    """Deep dive on strategy performance."""
    print(f"\n=== Strategy Deep Dive ===\n")

    STRATEGIES = {
        "mean_reversion": {
            "description": "Fade extreme leads that should revert to the mean",
            "theory": "~25% of excess halftime lead reverts (beta=0.75). Market overweights current score.",
            "entry": "Lead >= 8pts, model edge >= 4c, 5-35 min remaining",
            "exit": "3-min hold or edge closes to < 1c",
            "risk": "Lead keeps growing (hot shooting), game flow changes",
        },
        "momentum": {
            "description": "Ride scoring runs before market catches up",
            "theory": "Market updates slowly during fast runs. 6+ pt run in ~60s = signal.",
            "entry": "6+ point run detected, model edge aligns with run direction",
            "exit": "Quick 1-2 min flip as market catches up",
            "risk": "Run ends immediately, market was already pricing it in",
        },
        "halftime_edge": {
            "description": "Trade halftime mispricings when model disagrees with market",
            "theory": "Halftime is a natural recalibration point. Market anchors to 1H performance.",
            "entry": "Start of 2nd half, model edge >= 4c",
            "exit": "5 min into 2H or edge closes",
            "risk": "Model sigma wrong, game pace changes in 2H",
        },
        "gamma_scalp": {
            "description": "Trade high-delta close games in final 8 minutes",
            "theory": "Gamma explosion: delta per point > 0.04 means huge swings per basket.",
            "entry": "Close game (lead <= 6), high delta, last 8 min, edge >= 2c",
            "exit": "Immediate on next score (capture the gamma move)",
            "risk": "Wrong side of the gamma — a basket against us is a big loss",
        },
        "spread_capture": {
            "description": "Provide liquidity on wide spreads where model has conviction",
            "theory": "Wide bid-ask spread = market maker opportunity if model FV is inside spread.",
            "entry": "Spread 5-25c, model FV inside spread, edge to nearest side >= 3c",
            "exit": "Fill as market maker, profit = spread capture minus fees",
            "risk": "Adverse selection — smart money takes our order before price moves against us",
        },
        "stale_line": {
            "description": "Snap up stale prices after score changes",
            "theory": "After a basket, price should adjust by ~delta*points_scored cents. If it doesn't move, it's stale.",
            "entry": "Score changed, price unmoved (< 2c change), expected move >= 3c",
            "exit": "Quick flip as line catches up",
            "risk": "Price was already correct (our delta estimate wrong)",
        },
    }

    # Load cumulative data
    from bot.learner import load_cumulative_learnings
    cum = load_cumulative_learnings()
    perf = cum.get("strategy_performance", {})

    for name, info in STRATEGIES.items():
        print(f"  [{name.upper()}]")
        print(f"  {info['description']}")
        print(f"  Theory: {info['theory']}")
        print(f"  Entry:  {info['entry']}")
        print(f"  Exit:   {info['exit']}")
        print(f"  Risk:   {info['risk']}")
        if name in perf:
            p = perf[name]
            print(f"  RESULTS: {p.get('total_signals',0)} signals | "
                  f"Win rate: {p.get('cumulative_win_rate',0)}% | "
                  f"P&L: {p.get('cumulative_pnl',0):.0f}c")
        else:
            print(f"  RESULTS: No data yet")
        print()


def cmd_paper():
    """Paper trading P&L summary."""
    # Check for session learning files
    learn_dir = os.path.join(DATA_DIR, "learning", "sessions")
    if not os.path.exists(learn_dir):
        print("No paper trading data. Run 'python3 analyze.py learn' after a session.")
        return

    print(f"\n=== Paper Trading Results ===\n")

    total_pnl = 0
    total_trades = 0

    for f in sorted(os.listdir(learn_dir)):
        if not f.endswith(".json"):
            continue
        with open(os.path.join(learn_dir, f)) as fh:
            report = json.load(fh)

        paper = report.get("paper_trades", {})
        date = f.replace(".json", "")
        trades = paper.get("trades", 0)
        net = paper.get("total_net_pnl", 0)
        wr = paper.get("win_rate", 0)

        total_pnl += net
        total_trades += trades

        print(f"  {date}: {trades} trades | Win rate: {wr}% | Net: {net:+.0f}c | Running: {total_pnl:+.0f}c")

        # Show by strategy
        by_strat = paper.get("by_strategy", {})
        for strat, data in sorted(by_strat.items()):
            print(f"    {strat}: {data['trades']}t | {data['win_rate']}% | {data['total_pnl']:+.0f}c")

    if total_trades > 0:
        print(f"\n  TOTAL: {total_trades} trades | Net P&L: {total_pnl:+.0f}c (${total_pnl/100:+.2f})")


def cmd_backtest():
    """Backtest strategies on historical data."""
    from bot.learner import run_session_analysis

    print("\n=== Full Backtest ===\n")

    # Find all dates with signal data
    signals_dir = os.path.join(DATA_DIR, "signals")
    if not os.path.exists(signals_dir):
        print("No signal data available yet.")
        return

    dates = sorted(f.replace(".jsonl", "") for f in os.listdir(signals_dir) if f.endswith(".jsonl"))

    if not dates:
        print("No signals to backtest.")
        return

    print(f"Found {len(dates)} sessions with signals\n")

    for date in dates:
        print(f"--- {date} ---")
        report = run_session_analysis(date)
        if report:
            strats = report.get("strategy_scores", {})
            for strat, score in sorted(strats.items()):
                print(f"  {strat}: grade={score['grade']} | "
                      f"win={score['win_rate']}% | sharpe={score['sharpe']} | "
                      f"pnl={score['total_pnl_5m']}c")
        print()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summary"

    commands = {
        "summary": cmd_summary,
        "signals": cmd_signals,
        "prices": cmd_prices,
        "games": cmd_games,
        "scan": cmd_scan,
        "learn": cmd_learn,
        "report": cmd_report,
        "strategies": cmd_strategies,
        "paper": cmd_paper,
        "backtest": cmd_backtest,
    }

    if cmd in commands:
        commands[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        print(f"Available: {', '.join(commands.keys())}")


if __name__ == "__main__":
    main()
