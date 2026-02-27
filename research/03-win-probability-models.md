# Live Win Probability Models for Basketball

## Core Input Variables

- **Score differential (Δ)**: Current point spread
- **Time remaining (T)**: Seconds/minutes left
- **Possession**: Which team has ball
- **Pace of play**: Possessions per game
- **Pre-game spread**: Vegas line / team rating
- **Possession count**: Completed possessions

## Model Approaches

### A. Logistic Regression (Primary Method)

**P(Home Wins | Δ, T) = 1 / (1 + e^(-β₀ - β₁×Δ - β₂×f(T)))**

Yale NCAA model uses 280 separate logistic regressions:
- 1 per 10-second interval (40 min to 1 min remaining)
- 1 per 2-second interval (60-30 sec remaining)
- 1 per 1-second interval (0-30 sec remaining)

This captures the non-linear effect: late-game leads are exponentially more decisive.

### B. Locally-Weighted Logistic Regression (LOESS)

- Fits local logistic models around current game state
- Weights observations by similarity to current state
- Uses point spread as team strength measure
- Inputs: point differential, time remaining, possession

### C. Markov Chain Models

Game modeled as transitions between discrete states:
- Possession team
- Score differential
- Time remaining (discretized)

Transition matrix P defines: P(state_j | state_i)

Win probability calculated via matrix multiplication of remaining transitions.

### D. LRMC (Logistic Regression/Markov Chain Hybrid)

- Logistic regression models possession outcomes
- Markov chain built between states from regression coefficients
- Outperformed AP polls, RPI, and Sagarin for tournament predictions

## Pre-Game Spread Integration

Vegas spread = prior probability:
- Encodes market assessment of team strength differential
- Used as baseline adjustment before incorporating live game state
- P_home = function(current_spread, time_remaining)

## Critical Win Probability Benchmarks

### Halftime Lead Data
- Team ahead at halftime wins **74.8%** of the time
- Home +10 at halftime: ~85% win probability
- Away +10 at halftime: ~72% win probability
- 4-point halftime lead: ~70%
- 6-point halftime lead: ~80%

### The "Losing at Halftime" Paradox
- Teams down 1 at halftime have HIGHER win % than teams up 1
- Effect: +2% NCAA, +6% NBA vs expected
- **Implication for trading**: Small halftime deficits may be UNDERPRICED

### First Quarter Benchmarks
- Home +2 after Q1: 51.7% win probability
- Road +2 after Q1: only 39.2%
- Home -6 after Q1: 41.5% comeback probability

### Late Game Benchmarks
- 15-point lead, 5 min left: ~94.4%
- 5-point lead, 10 min left: ~71.9%
- 20-point deficit before half: ~7% comeback rate

## Home Court Advantage

- NBA: 61.55% home win rate
- College: 68.7% home win rate (12,465 D-I games since 2017-18)
- Tied game (college): home team has 55% win probability
- Point advantage: 3.2 to 4.68 ± 0.28 points

## Model Accuracy

- Best models achieve 92.3% precision and 92.5% overall accuracy
- Simple models often outperform complex ones (overfitting risk)
- Closing lines significantly more accurate than opening lines
- Sharp bettors win ~55%; square bettors win ~48%

## Elo Rating System

**P(A Wins) = 1 / (1 + 10^((Elo_B - Elo_A)/400))**

- K factor: 20-30 for sports
- Predicts NBA outcomes with 64-68% accuracy
- Simple, self-adjusting, real-time updatable
