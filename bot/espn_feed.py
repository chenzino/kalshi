"""ESPN hidden API client for live college basketball scores and odds."""
import requests
import time
import json
from datetime import datetime, timezone

# groups=50 = ALL Division 1 (not just top 25/featured)
ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?groups=50&limit=200"
ESPN_GAME = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/summary"


def _parse_odds(competition):
    """Extract DraftKings odds from ESPN competition data."""
    odds_list = competition.get("odds", [])
    if not odds_list:
        return {}

    odds = odds_list[0]  # First provider (DraftKings)
    result = {}

    # Spread (from awayTeamOdds perspective since details shows favorite)
    spread_val = odds.get("spread")
    if spread_val is not None:
        # Determine which team is favored
        away_fav = odds.get("awayTeamOdds", {}).get("favorite", False)
        if away_fav:
            # Away team is favored by spread_val points
            # Home spread = +spread_val (they're underdogs)
            result["home_spread"] = spread_val  # positive = underdog
            result["away_spread"] = -spread_val
        else:
            # Home team favored
            result["home_spread"] = -spread_val
            result["away_spread"] = spread_val

    result["over_under"] = odds.get("overUnder")
    result["details"] = odds.get("details", "")

    # Moneyline odds
    ml = odds.get("moneyline", {})
    home_ml = ml.get("home", {}).get("close", {}).get("odds", "")
    away_ml = ml.get("away", {}).get("close", {}).get("odds", "")
    if home_ml:
        result["home_moneyline"] = home_ml
    if away_ml:
        result["away_moneyline"] = away_ml

    # Point spread with open/close
    ps = odds.get("pointSpread", {})
    home_line = ps.get("home", {}).get("close", {}).get("line", "")
    if home_line:
        try:
            result["home_spread_line"] = float(home_line)
        except (ValueError, TypeError):
            pass

    return result


def _parse_game(event, state_filter=None):
    """Parse a single ESPN event into game data."""
    competition = event.get("competitions", [{}])[0]
    status = competition.get("status", {})
    state = status.get("type", {}).get("state", "")

    if state_filter and state != state_filter:
        return None

    competitors = competition.get("competitors", [])
    if len(competitors) != 2:
        return None

    home = away = None
    for c in competitors:
        team_data = {
            "id": c.get("id"),
            "name": c.get("team", {}).get("displayName", ""),
            "abbreviation": c.get("team", {}).get("abbreviation", ""),
            "shortDisplayName": c.get("team", {}).get("shortDisplayName", ""),
            "score": int(c.get("score", 0) or 0),
            "home": c.get("homeAway") == "home",
            "rank": c.get("curatedRank", {}).get("current", 99),
        }
        if team_data["home"]:
            home = team_data
        else:
            away = team_data

    if not home or not away:
        return None

    # Parse clock
    clock_str = status.get("displayClock", "0:00")
    period = status.get("period", 1)
    try:
        parts = clock_str.split(":")
        if len(parts) == 2:
            mins, secs = int(parts[0]), int(parts[1])
        else:
            mins, secs = 0, 0
    except Exception:
        mins, secs = 0, 0

    # Calculate minutes remaining
    if period <= 2:
        clock_minutes = mins + secs / 60
        if period == 1:
            minutes_remaining = 20 + clock_minutes
        else:
            minutes_remaining = clock_minutes
    else:
        minutes_remaining = mins + secs / 60

    # Parse odds/lines from ESPN (DraftKings)
    odds = _parse_odds(competition)

    # Pregame spread: positive = home favored
    # ESPN gives spread from favorite perspective, convert to home-relative
    pregame_spread = 0
    if "home_spread_line" in odds:
        # home_spread_line is from home team's perspective (negative = favored)
        pregame_spread = -odds["home_spread_line"]  # Flip: now positive = home favored
    elif "home_spread" in odds:
        pregame_spread = -odds["home_spread"]

    game = {
        "espn_id": event.get("id"),
        "name": f"{away['name']} @ {home['name']}",
        "home": home,
        "away": away,
        "home_score": home["score"],
        "away_score": away["score"],
        "lead": home["score"] - away["score"],
        "period": period,
        "clock": clock_str,
        "minutes_remaining": round(minutes_remaining, 1),
        "status": state,
        "timestamp": time.time(),
        "pregame_spread": pregame_spread,
        "odds": odds,
    }

    return game


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
        game = _parse_game(event, state_filter="in")
        if game:
            games.append(game)

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
    """Get today's full schedule with odds (pre, in-progress, and completed)."""
    try:
        resp = requests.get(ESPN_SCOREBOARD, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[ESPN] Error: {e}")
        return []

    schedule = []
    for event in data.get("events", []):
        game = _parse_game(event)
        if game:
            schedule.append({
                "id": game["espn_id"],
                "name": game["name"],
                "state": game["status"],
                "start": event.get("date", ""),
                "pregame_spread": game["pregame_spread"],
                "odds": game["odds"],
                "home_score": game["home_score"],
                "away_score": game["away_score"],
            })

    return schedule
