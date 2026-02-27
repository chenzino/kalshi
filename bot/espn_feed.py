"""ESPN hidden API client for live college basketball scores."""
import requests
import time
import json
from datetime import datetime, timezone

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"
ESPN_GAME = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/summary"

def get_live_games():
    """Get all currently live college basketball games."""
    try:
        resp = requests.get(ESPN_SCOREBOARD, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[ESPN] Error fetching scoreboard: {e}")
        return []

    games = []
    for event in data.get("events", []):
        competition = event.get("competitions", [{}])[0]
        status = competition.get("status", {})
        state = status.get("type", {}).get("state", "")

        # We want in-progress games
        if state != "in":
            continue

        competitors = competition.get("competitors", [])
        if len(competitors) != 2:
            continue

        home = away = None
        for c in competitors:
            team_data = {
                "id": c.get("id"),
                "name": c.get("team", {}).get("displayName", ""),
                "abbreviation": c.get("team", {}).get("abbreviation", ""),
                "score": int(c.get("score", 0)),
                "home": c.get("homeAway") == "home",
                "rank": c.get("curatedRank", {}).get("current", 99),
            }
            if team_data["home"]:
                home = team_data
            else:
                away = team_data

        if not home or not away:
            continue

        # Parse clock
        clock_str = status.get("displayClock", "0:00")
        period = status.get("period", 1)
        try:
            parts = clock_str.split(":")
            if len(parts) == 2:
                mins, secs = int(parts[0]), int(parts[1])
            else:
                mins, secs = 0, 0
        except:
            mins, secs = 0, 0

        # Calculate minutes remaining
        # College basketball: 2 halves of 20 min each
        # Overtime: 5 min periods
        if period <= 2:
            clock_minutes = mins + secs / 60
            if period == 1:
                minutes_remaining = 20 + clock_minutes  # First half + clock
            else:
                minutes_remaining = clock_minutes  # Second half clock
        else:
            # Overtime
            minutes_remaining = mins + secs / 60

        games.append({
            "espn_id": event.get("id"),
            "name": f"{away['name']} @ {home['name']}",
            "home": home,
            "away": away,
            "home_score": home["score"],
            "away_score": away["score"],
            "lead": home["score"] - away["score"],  # Positive = home leads
            "period": period,
            "clock": clock_str,
            "minutes_remaining": round(minutes_remaining, 1),
            "status": state,
            "timestamp": time.time(),
        })

    return games


def get_game_detail(game_id):
    """Get detailed game info including play-by-play."""
    try:
        resp = requests.get(ESPN_GAME, params={"event": game_id}, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[ESPN] Error fetching game {game_id}: {e}")
        return None


def get_todays_schedule():
    """Get today's full schedule (pre, in-progress, and completed)."""
    try:
        resp = requests.get(ESPN_SCOREBOARD, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[ESPN] Error: {e}")
        return []

    schedule = []
    for event in data.get("events", []):
        competition = event.get("competitions", [{}])[0]
        status = competition.get("status", {})
        state = status.get("type", {}).get("state", "")
        competitors = competition.get("competitors", [])

        home_name = away_name = ""
        for c in competitors:
            if c.get("homeAway") == "home":
                home_name = c.get("team", {}).get("displayName", "")
            else:
                away_name = c.get("team", {}).get("displayName", "")

        schedule.append({
            "id": event.get("id"),
            "name": f"{away_name} @ {home_name}",
            "state": state,
            "start": event.get("date", ""),
        })

    return schedule
