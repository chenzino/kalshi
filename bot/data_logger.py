"""Data capture and logging for market analysis."""
import json
import os
import time
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def log_market_snapshot(ticker, data):
    """Log a market orderbook/price snapshot."""
    path = os.path.join(DATA_DIR, "market_snapshots")
    _ensure_dir(path)
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    filepath = os.path.join(path, f"{date_str}.jsonl")
    entry = {
        "ts": time.time(),
        "ticker": ticker,
        **data,
    }
    with open(filepath, "a") as f:
        f.write(json.dumps(entry) + "\n")

def log_trade(trade_data):
    """Log a trade we made."""
    path = os.path.join(DATA_DIR, "trades")
    _ensure_dir(path)
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    filepath = os.path.join(path, f"{date_str}.jsonl")
    entry = {
        "ts": time.time(),
        **trade_data,
    }
    with open(filepath, "a") as f:
        f.write(json.dumps(entry) + "\n")

def log_game_state(game_data):
    """Log a game state snapshot from ESPN."""
    path = os.path.join(DATA_DIR, "games")
    _ensure_dir(path)
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    filepath = os.path.join(path, f"{date_str}.jsonl")
    entry = {
        "ts": time.time(),
        **game_data,
    }
    with open(filepath, "a") as f:
        f.write(json.dumps(entry) + "\n")

def get_todays_trades():
    """Read today's trade log."""
    path = os.path.join(DATA_DIR, "trades")
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    filepath = os.path.join(path, f"{date_str}.jsonl")
    if not os.path.exists(filepath):
        return []
    trades = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line:
                trades.append(json.loads(line))
    return trades

def get_session_stats():
    """Get summary stats for today's trading session."""
    trades = get_todays_trades()
    if not trades:
        return {"trades": 0, "pnl": 0, "wins": 0, "losses": 0}

    total_pnl = 0
    wins = losses = 0
    for t in trades:
        pnl = t.get("pnl_cents", 0)
        total_pnl += pnl
        if pnl > 0:
            wins += 1
        elif pnl < 0:
            losses += 1

    return {
        "trades": len(trades),
        "pnl_cents": total_pnl,
        "pnl_dollars": round(total_pnl / 100, 2),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / max(1, wins + losses) * 100, 1),
    }
