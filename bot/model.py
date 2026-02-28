"""Win probability model for college basketball using Brownian motion."""
import math
from scipy.stats import norm

# College basketball parameters (from research)
GAME_LENGTH_MIN = 40  # 40 minutes of game time
SIGMA = 12.0  # Standard deviation for final margin (11 too tight for mid-majors)
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

    # Drift from pregame spread or home advantage
    # When pregame_spread is provided (from DraftKings), it already includes home court
    # Only add HOME_ADVANTAGE when we don't have a real pregame spread
    if pregame_spread != 0:
        # Pregame spread already includes home court, use directly
        # Dampen large spreads: model over-applies drift for big mismatches
        # Small spreads (±4) are reliable. Large spreads have more model error.
        abs_spread = abs(pregame_spread)
        if abs_spread <= 4:
            dampen = 1.0
        elif abs_spread <= 8:
            dampen = 1.0 - 0.1 * (abs_spread - 4)  # 1.0 → 0.6 linearly
        else:
            dampen = 0.5  # Hard cap at 50% for very large spreads
        expected_remaining_margin = pregame_spread * t_frac * dampen
    else:
        # No pregame spread available, use home court as proxy
        home_drift = HOME_ADVANTAGE * t_frac if home else -HOME_ADVANTAGE * t_frac
        expected_remaining_margin = home_drift

    # Current effective lead including expected remaining drift
    effective_lead = lead + expected_remaining_margin

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


def spread_probability(lead, minutes_remaining, spread_line, home=True, pregame_spread=0):
    """Calculate probability that home team wins by more than spread_line points.

    For a Kalshi spread market "TEAM wins by X+", this calculates P(final_margin > X).

    Args:
        lead: Current point differential (positive = home leads)
        minutes_remaining: Minutes remaining
        spread_line: The spread line (e.g., 1 means home wins by >1)
        home: Whether calculating for home team
        pregame_spread: Expected final margin from pregame line
    Returns:
        Probability as float 0-1
    """
    if minutes_remaining <= 0:
        return 1.0 if lead > spread_line else 0.0

    t_frac = minutes_remaining / GAME_LENGTH_MIN
    if pregame_spread != 0:
        expected_remaining = pregame_spread * t_frac
    else:
        expected_remaining = (HOME_ADVANTAGE * t_frac) if home else (-HOME_ADVANTAGE * t_frac)
    effective_lead = lead + expected_remaining

    sigma_remaining = SIGMA * math.sqrt(t_frac)
    if sigma_remaining < 0.01:
        return 1.0 if effective_lead > spread_line else 0.0

    # P(final_lead > spread_line) = P(final_lead - spread_line > 0)
    z = (effective_lead - spread_line) / sigma_remaining
    return float(norm.cdf(z))


def spread_fair_value(lead, minutes_remaining, spread_line, home=True, pregame_spread=0):
    """Return fair value in cents for a spread market."""
    p = spread_probability(lead, minutes_remaining, spread_line, home, pregame_spread)
    return max(1, min(99, round(p * 100)))


def total_probability(home_score, away_score, minutes_remaining, total_line, pregame_total=None):
    """Calculate probability that total points exceed total_line.

    Uses Brownian motion on total scoring pace.

    Args:
        home_score, away_score: Current scores
        minutes_remaining: Minutes remaining
        total_line: The total line (e.g., 157 = over 157 total points)
        pregame_total: Expected total from O/U line (default: use pace estimate)
    Returns:
        Probability of going over as float 0-1
    """
    current_total = home_score + away_score
    minutes_played = GAME_LENGTH_MIN - minutes_remaining

    if minutes_remaining <= 0:
        return 1.0 if current_total > total_line else 0.0

    if minutes_played <= 0:
        # Game hasn't started, use pregame total or default
        expected_total = pregame_total or 155  # Average NCAAB total
        pace_sigma = 12.0  # Typical standard deviation of total points
        z = (expected_total - total_line) / pace_sigma
        return float(norm.cdf(z))

    # Current scoring pace (points per minute)
    pace = current_total / minutes_played

    # Project remaining points at current pace
    projected_remaining = pace * minutes_remaining
    projected_total = current_total + projected_remaining

    # If we have pregame total, blend current pace with pregame expectation
    if pregame_total:
        pregame_remaining = pregame_total - current_total
        # Weight current pace more as game progresses
        game_weight = minutes_played / GAME_LENGTH_MIN
        blended_remaining = (projected_remaining * game_weight +
                           pregame_remaining * (1 - game_weight))
        projected_total = current_total + blended_remaining

    # Variance scales with remaining time
    # Total points sigma is about 12 for full game
    TOTAL_SIGMA = 12.0
    t_frac = minutes_remaining / GAME_LENGTH_MIN
    sigma_remaining = TOTAL_SIGMA * math.sqrt(t_frac)

    if sigma_remaining < 0.01:
        return 1.0 if projected_total > total_line else 0.0

    z = (projected_total - total_line) / sigma_remaining
    return float(norm.cdf(z))


def total_fair_value(home_score, away_score, minutes_remaining, total_line, pregame_total=None):
    """Return fair value in cents for a total points market."""
    p = total_probability(home_score, away_score, minutes_remaining, total_line, pregame_total)
    return max(1, min(99, round(p * 100)))


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
