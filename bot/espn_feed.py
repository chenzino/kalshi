"""ESPN hidden API client for live college basketball scores and odds."""
import requests
import time
import json
from datetime import datetime, timezone, timedelta

# groups=50 = ALL Division 1 (not just top 25/featured)
ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?groups=50&limit=200"
ESPN_GAME = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/summary"

# Cache pickcenter data per game (fetched once from summary endpoint)
_pickcenter_cache = {}  # espn_id -> {"spread": float, "fetched": timestamp}


def _fetch_pickcenter(game_id):
    """Fetch pregame spread from ESPN game summary (pickcenter).
    The scoreboard endpoint doesn't include odds for non-featured games,
    but the per-game summary endpoint has pickcenter data from DraftKings."""
    if game_id in _pickcenter_cache:
        return _pickcenter_cache[game_id].get("spread", 0)

    try:
        resp = requests.get(ESPN_GAME, params={"event": game_id}, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        pc = data.get("pickcenter", [])
        if pc:
            spread_val = pc[0].get("spread", 0)
            # ESPN spread is negative for the favorite (e.g. -12.5 = favored by 12.5)
            # Our convention: positive = home favored
            # ESPN spread is from home perspective, so negate to get our convention
            pregame_spread = -spread_val
            _pickcenter_cache[game_id] = {
                "spread": pregame_spread,
                "details": pc[0].get("details", ""),
                "over_under": pc[0].get("overUnder", 0),
                "fetched": time.time(),
            }
            return pregame_spread
    except Exception:
        pass

    _pickcenter_cache[game_id] = {"spread": 0, "fetched": time.time()}
    return 0


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
            result["home_spread"] = spread_val  # positive = underdog
            result["away_spread"] = -spread_val
        else:
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

    # Parse odds/lines from ESPN scoreboard data (DraftKings)
    odds = _parse_odds(competition)

    # Pregame spread: positive = home favored
    pregame_spread = 0
    if "home_spread_line" in odds:
        pregame_spread = -odds["home_spread_line"]
    elif "home_spread" in odds:
        pregame_spread = -odds["home_spread"]

    # If scoreboard didn't include odds, try pickcenter from summary endpoint
    game_id = event.get("id")
    if pregame_spread == 0 and game_id and state == "in":
        pregame_spread = _fetch_pickcenter(game_id)

    game = {
        "espn_id": game_id,
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


EST = timezone(timedelta(hours=-5))

# Average CBB game length ~2 hours
GAME_DURATION_HOURS = 2.5  # Buffer for OT, delays


def _parse_game_window(data):
    """Parse game window from ESPN scoreboard response.
    Returns (wake_time, sleep_time, has_active) where has_active means
    there are live or pre-game events."""
    events = data.get("events", [])
    if not events:
        return None, None, False

    start_times = []
    has_live = False
    has_pre = False

    for event in events:
        date_str = event.get("date", "")
        state = event.get("competitions", [{}])[0].get(
            "status", {}).get("type", {}).get("state", "")

        if state == "in":
            has_live = True
        if state == "pre":
            has_pre = True

        if date_str:
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                start_times.append(dt.astimezone(EST))
            except Exception:
                pass

    if not start_times:
        return None, None, False

    earliest = min(start_times)
    latest_start = max(start_times)

    wake_time = earliest - timedelta(minutes=15)
    sleep_time = latest_start + timedelta(hours=GAME_DURATION_HOURS, minutes=30)

    return wake_time, sleep_time, (has_live or has_pre)


def get_game_window():
    """Get the next game window: (first_start, last_end) as EST datetimes.

    Checks multiple dates to handle ESPN's scoreboard rollover timing:
    1. Default scoreboard (may still show yesterday late at night)
    2. Today with explicit date
    3. Tomorrow if all today's games are done
    Returns (None, None) if no upcoming games found.
    """
    now = datetime.now(EST)

    # Check default scoreboard first (usually today, but lags near midnight)
    try:
        resp = requests.get(ESPN_SCOREBOARD, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        wake, sleep, has_active = _parse_game_window(data)
        if wake and has_active:
            return wake, sleep
    except Exception:
        pass

    # Check today with explicit date (handles midnight rollover gap)
    today_str = now.strftime("%Y%m%d")
    try:
        url = f"{ESPN_SCOREBOARD}&dates={today_str}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        wake, sleep, has_active = _parse_game_window(data)
        if wake and (has_active or (sleep and sleep > now)):
            return wake, sleep
    except Exception:
        pass

    # All today's games are done - check tomorrow
    tomorrow = now + timedelta(days=1)
    tmrw_str = tomorrow.strftime("%Y%m%d")
    try:
        url = f"{ESPN_SCOREBOARD}&dates={tmrw_str}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        wake, sleep, _ = _parse_game_window(data)
        if wake:
            return wake, sleep
    except Exception:
        pass

    return None, None
