"""Live status feed for dashboard integration.

Writes a status.json file that the Express dashboard can serve.
Updated every cycle during active hours.
"""
import json
import os
import time
from datetime import datetime, timezone, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
EST = timezone(timedelta(hours=-5))


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def write_status(orchestrator, next_session=None):
    """Write current system status to JSON for dashboard consumption."""
    now = datetime.now(EST)

    status = {
        "updated_at": time.time(),
        "updated_at_str": now.strftime("%I:%M:%S %p EST"),
        "date": now.strftime("%Y-%m-%d"),
        "session_active": orchestrator.session_start is not None,
        "auth_ok": orchestrator.auth_ok,
        "cycle_count": orchestrator.cycle_count,
    }

    if next_session:
        status["next_session"] = next_session

    # Balance
    if orchestrator.auth_ok and orchestrator.client:
        try:
            bal = orchestrator.client.get_balance()
            status["balance_cents"] = bal.get("balance", 0)
            status["balance"] = f"${bal.get('balance', 0)/100:.2f}"
        except:
            status["balance"] = "unknown"
    else:
        status["balance"] = "no auth"

    # Live games
    status["live_games"] = []
    for game in orchestrator.live_games:
        from bot.model import fair_value_cents, delta_per_point
        lead = game.get("lead", 0)
        mins = game.get("minutes_remaining", 40)
        fv = fair_value_cents(lead, mins)
        delta = delta_per_point(lead, mins)

        gdata = {
            "name": game.get("name", ""),
            "home_score": game.get("home_score", 0),
            "away_score": game.get("away_score", 0),
            "clock": game.get("clock", ""),
            "period": game.get("period", 0),
            "minutes_remaining": mins,
            "model_fv": fv,
            "delta_per_point": round(delta, 4),
        }

        # Find matched market price
        matched = orchestrator._match_game_to_markets(game)
        if matched:
            m = matched[0]
            mp = m.get("last_price") or m.get("yes_bid") or 0
            gdata["market_price"] = mp
            gdata["edge"] = fv - mp
            gdata["ticker"] = m.get("ticker", "")

        status["live_games"].append(gdata)

    # Executor status
    status["executor"] = orchestrator.executor.get_status()

    # Strategy signals (last 10)
    recent_signals = orchestrator.strategy.signals[-10:]
    status["recent_signals"] = [s.to_dict() for s in recent_signals]

    # Session duration
    if orchestrator.session_start:
        duration = (time.time() - orchestrator.session_start) / 3600
        status["session_hours"] = round(duration, 1)

    # Markets tracked
    status["markets_tracked"] = len(orchestrator.today_markets)
    status["games_tracked"] = len(orchestrator.game_histories)

    # Write to file
    filepath = os.path.join(DATA_DIR, "live_status.json")
    _ensure_dir(DATA_DIR)
    with open(filepath, "w") as f:
        json.dump(status, f, indent=2)

    return status
