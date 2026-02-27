"""Win probability model for college basketball using Brownian motion."""
import math
from scipy.stats import norm

# College basketball parameters (from research)
GAME_LENGTH_MIN = 40  # 40 minutes of game time
SIGMA = 11.0  # KenPom standard deviation for final margin
HOME_ADVANTAGE = 3.5  # Average home court advantage in points

def win_probability(lead, minutes_remaining, home=True, pregame_spread=0):
    """Calculate win probability using Brownian motion model.

    P(win) = Phi((lead + drift * time_remaining) / (sigma * sqrt(time_remaining / game_length)))

    Args:
        lead: Current point differential (positive = our team leads)
        minutes_remaining: Minutes of game time remaining
        home: Whether our team is at home
        pregame_spread: Expected final margin from pre-game rating (positive = our team favored)
    Returns:
        Win probability as float 0-1
    """
    if minutes_remaining <= 0:
        return 1.0 if lead > 0 else (0.5 if lead == 0 else 0.0)

    # Time fraction remaining
    t_frac = minutes_remaining / GAME_LENGTH_MIN

    # Home court advantage: add expected remaining advantage
    home_drift = HOME_ADVANTAGE * t_frac if home else -HOME_ADVANTAGE * t_frac

    # Drift: expected points per minute remaining based on pre-game spread
    expected_remaining_margin = pregame_spread * t_frac

    # Current effective lead including expected remaining drift + home advantage
    effective_lead = lead + expected_remaining_margin + home_drift

    # Standard deviation scales with sqrt of remaining time fraction
    sigma_remaining = SIGMA * math.sqrt(t_frac)

    if sigma_remaining < 0.01:
        return 1.0 if effective_lead > 0 else (0.5 if effective_lead == 0 else 0.0)

    z = effective_lead / sigma_remaining
    return float(norm.cdf(z))


def fair_value_cents(lead, minutes_remaining, home=True, pregame_spread=0):
    """Return fair value in Kalshi cents (0-99)."""
    p = win_probability(lead, minutes_remaining, home, pregame_spread)
    return max(1, min(99, round(p * 100)))


def delta_per_point(lead, minutes_remaining, pregame_spread=0):
    """How much does win probability change per point scored?"""
    p_current = win_probability(lead, minutes_remaining, pregame_spread=pregame_spread)
    p_plus = win_probability(lead + 1, minutes_remaining, pregame_spread=pregame_spread)
    return p_plus - p_current


def mean_reversion_estimate(current_lead, pregame_spread, minutes_remaining):
    """Estimate expected lead change due to mean reversion.

    Uses beta = 0.72-0.78 regression coefficient from research.
    Excess lead beyond pregame expectation partially reverts.
    """
    # How much of the game has been played
    t_played = GAME_LENGTH_MIN - minutes_remaining
    if t_played <= 0:
        return 0

    # Expected lead at this point in the game
    expected_lead = pregame_spread * (t_played / GAME_LENGTH_MIN)

    # Excess lead
    excess = current_lead - expected_lead

    # Reversion coefficient (from Bayesian framework research)
    beta = 0.75  # ~25% of excess reverts

    # Expected reversion over remaining game
    expected_reversion = -excess * (1 - beta) * (minutes_remaining / GAME_LENGTH_MIN)

    return expected_reversion


def detect_scoring_run(score_log, window=5):
    """Detect if a scoring run is happening.

    Args:
        score_log: List of (timestamp, team, points) recent scoring events
        window: Number of recent events to consider
    Returns:
        (run_team, run_points, run_events) or None if no significant run
    """
    if len(score_log) < 3:
        return None

    recent = score_log[-window:]

    # Count consecutive scores by one team
    teams = [e[1] for e in recent]
    points = [e[2] for e in recent]

    # Check if one team dominates recent scoring
    team_points = {}
    for t, p in zip(teams, points):
        team_points[t] = team_points.get(t, 0) + p

    if len(team_points) < 2:
        # One team scored all recent points
        dominant = list(team_points.keys())[0]
        return (dominant, team_points[dominant], len(recent))

    sorted_teams = sorted(team_points.items(), key=lambda x: x[1], reverse=True)
    run_diff = sorted_teams[0][1] - sorted_teams[1][1]

    if run_diff >= 8:
        return (sorted_teams[0][0], run_diff, len(recent))

    return None
