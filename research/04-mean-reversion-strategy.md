# Mean Reversion & Scoring Dynamics

## Mathematical Basis

**Total Performance = Skill + Luck**

If a team leads by 10 at halftime but expected lead is 5 (from pre-game rating), the 5-point "excess" is attributable to luck and will partially revert.

### Quantifying Expected Reversion (Bayesian Framework)

1. **Prior**: Team A should lead by X based on pre-game rating
2. **Observed**: Team A leads by X + ΔX at halftime
3. **Posterior**: Expected second-half lead = X + β×ΔX, where **β < 1**

**β (reversion coefficient): 0.3 to 0.6**
- 60-70% of halftime excess tends to persist
- Higher remaining time → more regression
- Lower confidence in observed performance → more regression

## Shooting Percentage Reversion

| Metric | Season Average | Stabilization |
|---|---|---|
| FG% | 44-48% | ~50 shots minimum |
| 3P% | ~35% | Higher variance, slower to stabilize |
| FT% | Most stable | Carries across games |
| TOV% | ~13-14% | Reverts to season average |

## In-Game Scoring Runs

**Critical finding**: Coefficient on size of current scoring run = ~0.001 (NOT statistically significant)

- Scoring runs do NOT predict immediate future scoring
- Contradicts "hot hand" intuition
- Timeouts show 11.2% decline in scoring by momentum team
- But: unclear if this is timeout effect or regression to mean

## Scoring Run Frequency & Impact

- 10-point run in Q1: highest observed effect at 8.2% win probability increase
- In-game runs rarely provide additional win probability above baseline
- Home team runs that tie games don't generate higher win probabilities than baselines

## Four Factors (Basketball Success Metrics)

1. **eFG%**: (FG + 0.5 × 3P) / FGA — most important
2. **TOV%**: TOV / (FGA + 0.44 × FTA + TOV)
3. **ORB%**: ORB / (ORB + Opp DRB)
4. **FT Rate**: Free throw attempt rate

These factors regress toward season averages within games, creating trading opportunities when current-game performance deviates significantly.

## Trading Implications

### When to Buy (Mean Reversion Play)
- Team B on a 10-0 run, market overreacts
- Team A's shooting well below season average (regression expected)
- Score differential exceeds what pre-game spread implies
- Early in game (more time for regression)

### When to Avoid Mean Reversion
- Late game (< 3 min) — insufficient time for regression
- When performance difference reflects genuine matchup advantage
- When key player injured (fundamental shift, not luck)
- Garbage time (18+ point leads with significant time)

## College Basketball Scoring Dynamics

- **Average possessions**: ~70 per game (range: 55-90)
- **Points per possession**: ~0.994 average
- **Scoring std dev**: ~13.22 points (mean = 71)
- **Shot clock**: 30 sec (college) vs 24 sec (NBA)
- **Pace variation**: Virginia (slow, ~60 possessions) vs Gonzaga (fast, ~74)
- **3-point variance**: "Live by the three, die by the three" — 3pt-heavy teams show higher scoring variance
