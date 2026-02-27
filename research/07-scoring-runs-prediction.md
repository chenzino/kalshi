# Scoring Runs: Prediction, Detection, and Trading

## The Core Question

Basketball is a game of runs. A 10-0 run can flip a market from 65¢ to 45¢ in two minutes. Can we predict when runs will happen, and more importantly, can we trade the aftermath?

## What the Data Says About Runs

### Statistical Properties of Scoring Runs

**Key finding from 8,370 professional games**: In-game runs rarely provide additional increase in win probability above baseline.

This means:
- A 10-0 run does NOT mean the running team will continue to dominate
- The market OVERREACTS to runs because humans see momentum, not regression
- **This is our primary edge**: trading against run-driven market moves

### Run Probability (Geometric Distribution)

If each possession has probability p of scoring:
- **P(k-point run) = p^(k/avg_pts_per_scoring_possession)**
- Streak probability: p^k where k = consecutive scoring possessions

For a team scoring on 50% of possessions:
- 3 consecutive scores: 0.5³ = 12.5%
- 4 consecutive scores: 0.5⁴ = 6.25%
- 5 consecutive scores: 0.5⁵ = 3.13%

These runs happen every game, but they're NOT predictive of continued runs.

### What Causes Runs

1. **Random variance** (primary driver): Teams score on ~50% of possessions. Random clustering creates runs that feel meaningful but are statistically expected.

2. **Lineup changes**: Bench units entering can shift scoring rates temporarily. This is the most legitimate, predictable cause.

3. **Foul trouble**: Key player picks up 3rd/4th foul, sits, team goes on run against weaker lineup.

4. **Tactical adjustments**: Zone defense switch, press, tempo change. These effects are real but temporary (opponent adjusts).

5. **Fatigue**: Late in halves, tired teams allow runs. Predictable based on timeout patterns and rotation timing.

6. **The "hot hand" debate**: Research is now mixed — there IS a small hot hand effect (~1.5-2% increase in shooting after makes), but it's much smaller than perception suggests. Markets overweight it dramatically.

## Detecting Runs in Real-Time

### Run Detection Algorithm

```
Define: run = consecutive possessions where one team outscores the other

Track:
- last_N_possessions (N = 5-8)
- scoring_rate_team_A = points_A / possessions_A (last N)
- scoring_rate_team_B = points_B / possessions_B (last N)
- run_differential = points_A - points_B (last N possessions)

Signal: |run_differential| > threshold (e.g., 8+ point swing in 5 possessions)
```

### Run Context Indicators

When a run is detected, evaluate:

1. **Is there a lineup explanation?**
   - Star player on bench → run is partially "real" (continues until player returns)
   - Full strength lineup → run is likely regression-bound

2. **Is there a tactical explanation?**
   - New defensive scheme → opponent will adjust in 2-3 possessions
   - Press/trap → effective for 1-2 possessions, then broken

3. **Shooting percentage during run?**
   - If run is driven by 5/5 three-point shooting → STRONG regression expected
   - If run is driven by layups/free throws → more sustainable

4. **Pace during run?**
   - If trailing team is playing faster → more possessions = more opportunity for regression
   - If leading team slowing down → fewer possessions = run may stall naturally

## Trading Runs

### The Counter-Run Trade (Primary Strategy)

**Setup**: Team B goes on an 8-0 or 10-0 run. Market moves 8-15 cents against Team A.

**Thesis**: The run will regress. Team A's true probability has NOT changed by 8-15%.

**Entry**:
1. Wait for run to reach 8+ points
2. Buy Team A (now underpriced)
3. Entry price should be 3-5 cents below your model's fair value

**Exit**:
1. Market recovers 2-3 cents → take profit
2. Team A scores → partial recovery → evaluate for hold or exit
3. Run extends to 14+ → stop loss, thesis may be wrong

**Sizing**: 1/4 Kelly based on your edge estimate

### The Run Continuation Trade (Secondary Strategy)

**When runs ARE predictive** (less common but higher edge):

1. **Lineup mismatch identified**: Team A's bench lineup is significantly weaker. When they enter, bet Team B.
2. **Foul trouble**: Star has 4 fouls in 3rd quarter. Bet opponent for next 5-8 minutes.
3. **Injury**: Key player limps off. Market may not fully price this immediately.

### Timing the Counter-Run Entry

**Don't buy immediately when a run starts**. Runs have momentum in the short term.

Optimal timing:
- Wait for first timeout during the run (TV timeout or called timeout)
- Wait for a substitution (lineup change often breaks runs)
- Wait for the run to reach 8-10 points (market has overreacted enough to create edge)
- Wait for Team A to get one "answer" basket (shows they're not completely dead)

### Media Timeouts as Run Breakers

Research finding: TV timeouts cause an **11.2% decline** in subsequent scoring by the momentum team.

**Trading implication**:
- If a run is happening and a media timeout is approaching (every 4 minutes of game clock in college), the run is likely to break
- Buy the team that's getting run on right before the media timeout
- Expected value: market recovers 1-3 cents post-timeout as run stalls

## The Momentum Illusion

### Why Markets Overreact to Runs

1. **Recency bias**: Humans weight recent events too heavily
2. **Narrative construction**: "Team B has all the momentum" — compelling story, poor predictor
3. **Availability heuristic**: Easy to recall games where runs continued; forget the majority where they didn't
4. **Anchoring**: Market anchors to the run rather than the pre-game fundamentals

### What Actually Predicts the Rest of the Game

After controlling for score differential and time remaining:
- **Pre-game spread** remains the best predictor of remaining game outcome
- **Current run** adds almost zero predictive value (coefficient ~0.001)
- **Team quality** (season stats) matters more than in-game momentum
- **Home court** remains a constant advantage regardless of runs

## Practical Run Trading Framework

### Decision Tree

```
Run detected (8+ point swing in < 3 minutes)
├── Is there a lineup/injury explanation?
│   ├── YES → Run may be partially real. Smaller counter-bet or skip.
│   └── NO → Strong counter-run trade signal.
├── What's driving the scoring?
│   ├── Hot shooting (3s, mid-range) → STRONG regression expected. Large counter-bet.
│   └── Layups/FTs/turnovers → Moderate regression. Standard counter-bet.
├── Time remaining?
│   ├── > 10 min → Plenty of time for regression. Enter counter-run trade.
│   ├── 3-10 min → Enter but with tighter stops (gamma increasing).
│   └── < 3 min → Skip. Not enough time for regression to play out.
└── Market price after run?
    ├── Still in 20-80% range → Tradeable.
    └── Outside 20-80% → Skip (poor risk/reward).
```

### Expected Win Rate
- Counter-run trades in 20-80% range: ~55-60% win rate
- Average gain on winners: 2-3 cents
- Average loss on losers: 2-3 cents
- Edge: 10-20% of trades × 2-3 cent gain = positive EV over time
- Need 200+ trades per month for edge to materialize reliably
