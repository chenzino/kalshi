# NCAA College Basketball Dynamics for Kalshi Live Trading

## Executive Summary

This report documents the structural, statistical, and strategic characteristics of NCAA Division I men's college basketball that are specifically relevant to live trading of Kalshi moneyline binary contracts (0-100 cent). College basketball differs fundamentally from the NBA in pace, variance, talent distribution, and game dynamics -- all of which create distinct opportunities and risks for live contract trading. The core thesis: college basketball's higher variance, fewer possessions, and greater talent gaps produce wider and more frequent mispricings in live markets compared to professional basketball.

---

## 1. NCAA Scoring Dynamics and Possession Structure

### Possessions Per Game

College basketball averages approximately **68 possessions per game** per team (KenPom, 2019-2025 seasons), compared to ~100 possessions in the NBA. This is the single most important structural difference for live trading:

- **Fewer possessions = higher variance per possession**
- Each possession represents ~1.47% of total possessions (1/68) vs ~1.0% in NBA (1/100)
- A 5-possession cold streak in college represents ~7.4% of the game; in the NBA it is ~5%

The range across Division I is enormous:

| Tempo Category | Possessions/Game | Example Teams | Typical Final Score |
|---------------|-----------------|---------------|-------------------|
| Ultra-Slow | 58-62 | Virginia, Wisconsin | 55-62 |
| Below Average | 63-66 | Texas Tech, Houston | 63-68 |
| Average | 67-70 | Most D-I teams | 70-75 |
| Above Average | 71-74 | Duke, Kansas | 75-82 |
| Ultra-Fast | 75-82 | Gonzaga, Arkansas | 82-92 |

### Shot Clock Impact (30-sec vs NBA 24-sec)

The 6-second difference in shot clock creates meaningful downstream effects:

- **Longer possessions** enable more ball movement and half-court offense
- **Fewer transition opportunities** in slower-paced games
- **Reset rule**: After an offensive rebound, the shot clock resets to **20 seconds** (vs 14 in NBA), further compressing pace differences
- The shot clock was reduced from 35 to 30 seconds in 2015-16, which increased scoring by ~3-4 points per game league-wide

### Points Per Possession (PPP) Variance

Average Division I offensive efficiency is approximately **1.00-1.05 points per possession** (adjusted). The standard deviation of single-team scoring is **7.3-7.9 points per game** (remarkably consistent across seasons and teams, per The Only Colors analysis of 11,000+ games, 2004-2018).

Using the binomial approximation with ~56 adjusted shot attempts per game and ~50% effective FG percentage:

**sigma = sqrt(n * p * (1-p)) = sqrt(56 * 0.5 * 0.5) = 3.74 made shots = ~7.48 points**

This aligns perfectly with observed data. The combined game scoring margin standard deviation is:

**sigma_margin = sqrt(7.5^2 + 7.5^2) = 10.6 points**

This means:
- 68% of games finish within 10.6 points of the true spread
- 95% finish within 21.2 points
- 5% of games have margins exceeding 21+ points from the spread

### Conference-Level Tempo Differences (2024-25 Data)

| Conference | Avg Adj. Tempo | Avg PPP (Offense) | Style |
|-----------|---------------|-------------------|-------|
| Big East | 67-69 | 1.05-1.08 | Moderate pace, strong offense |
| Big 12 | 66-68 | 1.03-1.06 | Physical, defensive-minded |
| SEC | 68-71 | 1.04-1.07 | Rising tempo, athletic |
| Big Ten | 65-68 | 1.02-1.05 | Grind-it-out, half-court |
| ACC | 67-70 | 1.03-1.06 | Balanced |
| WCC | 69-72 | 1.04-1.08 | Pace-and-space (Gonzaga effect) |

**Trading implication**: In slow-tempo conference games (Big Ten, Big 12), scoring droughts of 3-5 minutes are common and create overreaction in live markets. A team down 6 in a 62-possession game at the 12-minute mark is in far less trouble than the market often prices.

---

## 2. Win Probability Models: Methodology and Accuracy

### KenPom In-Game Win Probability

Ken Pomeroy's model is the gold standard for college basketball analytics. His in-game win probability system uses:

**Inputs:**
1. Current score differential
2. Time remaining (seconds)
3. Possession (which team has the ball, +/- 0.5 adjustment)
4. Pre-game efficiency margin differential (AdjEM_A - AdjEM_B)
5. Game location (home/away/neutral)

**Pre-game prediction formula:**
```
PointDiff = (AdjEM_A - AdjEM_B) * (AdjT_A + AdjT_B) / 200
WinProb = NORM.DIST(PointDiff, 0, 11, TRUE)
```

The standard deviation of 11 is the empirically observed sigma for NCAA game outcomes. This means KenPom's pre-game predictions produce a normal distribution of outcomes centered on the predicted margin with sigma=11.

**Calibration**: The model identified 17 cases in a single season where teams had less than 1% win probability and still won. KenPom notes the model "tends to underestimate certainty at cases above 98%," which is conservative by design.

### Yale YUSAG Model

The Yale Undergraduate Sports Analytics Group developed a transparent model using:

- **280 separate logistic regressions** -- one for each time interval
  - 10-second intervals from 40:00 to 1:00 remaining
  - 2-second intervals from 1:00 to 0:30 remaining
  - 1-second intervals from 0:30 to 0:00 remaining
- **Inputs**: Score differential + pre-game win probability (as team strength proxy)
- **Does NOT factor in possession** (a known limitation)
- Trained on complete play-by-play data across multiple seasons

**Why 280 separate regressions?** A single logistic regression performed poorly near game end because non-zero score differentials become deterministic as time approaches zero. The segmented approach handles this discontinuity.

**Accuracy comparison** (Marquette vs Providence, Jan 2018, critical moment):
- YUSAG: 1.21% win probability
- KenPom: 3.1%
- Bart Torvik: 2.7%

### Bart Torvik T-Rank

Bart Torvik's system is an offshoot of KenPom but uses the "Barthag" methodology (a Pythagorean-style calculation) rather than KenPom's additive adjusted efficiency margins. The systems produce similar but not identical pre-game predictions and in-game probabilities.

### ESPN BPI (Basketball Power Index)

ESPN's BPI uses game-level data to calculate team strength metrics and produces both pre-game predictions and in-game win probability. It is less transparent than KenPom or T-Rank but covers all D-I games.

**Trading implication**: The divergence between models (e.g., 1.2% vs 3.1% at the same game state) represents the uncertainty band that live markets must price through. When Kalshi contracts trade near these extremes, the "true" probability is genuinely uncertain, creating both risk and opportunity.

---

## 3. Home Court Advantage

### Quantified Home Court Advantage

Home court advantage in college basketball is approximately **3.5 points nationally** (BoydsBets analysis, 2006-2025, in-conference games). This is significantly larger than the NBA's ~2.5 point advantage.

**By context:**
- Non-conference home games: ~3.3 points advantage
- Conference home games: ~2.9 points advantage (familiarity effect reduces it)
- Tournament/neutral site: 0 points (by definition)

### Conference-Specific Home Court Advantage

| Conference | True HCA (points) | Ranking |
|-----------|-------------------|---------|
| Big 12 | +5.34 | 1st |
| MEAC | +4.69 | 2nd |
| Summit | +4.00 | 3rd (tied) |
| Big Ten | +4.00 | 3rd (tied) |
| WAC | +3.99 | 5th |
| SEC | ~3.5 | Middle |
| ACC | ~3.2 | Middle |
| Patriot | +0.82 | Lowest |
| MAAC | +1.68 | 2nd lowest |

The Big 12 has the strongest home court advantage in the nation, likely driven by factors including altitude (several programs at elevation), travel distances, and passionate fan bases in smaller cities.

### Extreme Individual Team Advantages

| Team | Home Record | Home PPG Margin | Road PPG Margin | True Advantage |
|------|------------|----------------|----------------|---------------|
| Denver | 57-17 | +9.18 | -4.87 | 7.03 pts |
| Arkansas | - | - | - | 6.63 pts |
| Oklahoma State | - | - | - | 6.52 pts |
| Kansas | 72-4 | +17.28 | +6.93 | 5.18 pts |
| Duke | 62-11 | +11.74 | +4.34 | 3.70 pts |

**Key insight**: Home court advantage is driven more by **travel distance, time zone changes, and altitude** than by crowd noise. Denver's 7.03-point advantage is the largest in D-I, heavily influenced by its 5,280-foot elevation.

### Tournament Neutral Site Adjustment

When games move to neutral sites (conference tournaments, NCAA tournament), home court advantage drops to approximately zero. However, "soft" home court effects persist:
- Games played near one team's campus still show a ~1-2 point advantage
- Fan travel and familiarity with the venue matter
- First/second round NCAA tournament sites near a higher seed's campus create pseudo-home advantages

**Trading implication**: When pricing live contracts in regular season games, a home team trailing by 5 at halftime has roughly the same win probability as a road team trailing by 2-3. In tournament games, this adjustment disappears entirely. Failing to account for venue correctly is a common mispricing source.

---

## 4. Tempo and Style Effects on Variance

### The Variance-Tempo Relationship

This is a critical concept for live trading: **slower-paced games have higher per-possession variance but lower total-game variance, while faster-paced games have lower per-possession variance but the total outcome is "regression-to-the-mean" driven.**

However, the strategic dynamic is more nuanced:

- In a **60-possession game** (Virginia-style), each possession is worth ~1.67% of total possessions
- In an **78-possession game** (Gonzaga-style), each possession is worth ~1.28%
- The Central Limit Theorem means more possessions produce outcomes closer to expected values
- Therefore: **slow-tempo games produce more upsets and more volatile live pricing**

### Harvard Sports Analysis Finding

Harvard's analysis directly tested whether slow tempo aids NCAA tournament upsets. Their finding: slower-paced games are associated with higher upset frequency because fewer possessions mean less opportunity for the better team's talent advantage to manifest in the final score.

### The Virginia vs. Gonzaga Paradigm

| Metric | Virginia (Slow) | Gonzaga (Fast) |
|--------|----------------|----------------|
| Possessions/game | 58-62 | 74-78 |
| Typical final score | 55-62 | 82-90 |
| Scoring drought frequency | Very high | Low |
| Points per scoring drought (3+ min) | 0-2 | Rare |
| Live market volatility | Extreme swings | Gradual moves |
| Upset vulnerability | Higher | Lower |

**Trading implication**: In a slow Virginia-style game, a 6-point lead with 8 minutes left might represent only 6-8 remaining possessions worth of scoring opportunities. The win probability is higher than markets typically price because there simply are not enough possessions for the trailing team to close the gap. Conversely, 6 points in a Gonzaga game with 8 minutes left represents 12-15 possessions -- much more time for reversion.

This is the single most exploitable dynamic for live Kalshi trading: **markets undervalue tempo when pricing mid-game leads and deficits**.

---

## 5. March Madness and Tournament Dynamics

### Single-Elimination Psychology

NCAA tournament games exhibit different dynamics than regular season:
- Higher stakes amplify coaching adjustments at halftime
- Players perform at non-typical effort levels (for better or worse)
- Fatigue from compressed schedules (potential games every 2 days)
- Neutral sites eliminate home court advantage
- "Brand-name" teams are systematically overpriced by the public

### Historical Upset Frequency by Seed (Round of 64, 1985-2025)

| Matchup | Higher Seed Win% | Lower Seed Upset% | Implied Moneyline |
|---------|-----------------|-------------------|-------------------|
| 1 vs 16 | 99.3% | 0.7% | ~$0.99 / $0.01 |
| 2 vs 15 | 93.1% | 6.9% | ~$0.93 / $0.07 |
| 3 vs 14 | 85.0% | 15.0% | ~$0.85 / $0.15 |
| 4 vs 13 | 79.3% | 20.7% | ~$0.79 / $0.21 |
| 5 vs 12 | 64.3% | 35.7% | ~$0.64 / $0.36 |
| 6 vs 11 | 62.9% | 37.1% | ~$0.63 / $0.37 |
| 7 vs 10 | 60.7% | 39.3% | ~$0.61 / $0.39 |
| 8 vs 9 | 49.3% | 50.7% | ~$0.49 / $0.51 |

**Key trading insight**: The 5/12 matchup is notoriously volatile. A 12-seed wins more than one-third of the time. The 8/9 matchup is effectively a coin flip (the 9-seed actually has a slight historical edge at 50.7%). These matchups create the highest-volume live trading opportunities during the tournament.

### Beyond the First Round

When lower seeds advance, they continue to be dangerous:
- 12-seeds who win Round 1 win Round 2 **38.6%** of the time
- 13-seeds who win Round 1 win Round 2 **18.2%** of the time
- 14-seeds who win Round 1 win Round 2 **8.7%** of the time

### Tournament vs. Regular Season Market Pricing

Tournament games are priced differently because:
1. **No home court adjustment** (neutral sites)
2. **Public betting volume surges** -- casual bettors overvalue recognizable programs
3. **Compressed schedules** -- fatigue, especially for teams playing conference tournament games before the NCAA tournament
4. **Matchup novelty** -- teams rarely face non-conference opponents, creating information asymmetry
5. **Single-elimination pressure** -- behavioral effects (tightening up, uncharacteristic play) are real but difficult to model

---

## 6. Free Throw and Foul Dynamics

### The Bonus Structure (Critical NCAA-Specific Rule)

| Foul Count (per half) | Result |
|----------------------|--------|
| 1-6 fouls | No free throws on non-shooting fouls |
| 7th-9th foul | **One-and-one** (must make 1st to attempt 2nd) |
| 10th+ foul | **Double bonus** (2 shots guaranteed) |

This differs fundamentally from the NBA (team fouls reset quarterly, penalty is always 2 shots after the 4th foul per quarter).

### Implications for Live Trading

**The one-and-one is a variance amplifier:**
- Expected points on a one-and-one: For a 70% FT shooter, E[points] = 0.70 * (1 + 0.70) = 1.19 points
- Expected points on double bonus: 0.70 * 2 = 1.40 points
- Expected points if the shooter misses the front end: 0 points + live ball rebound opportunity for the defense

The front end miss of a one-and-one creates a **zero-point possession with a fast break opportunity** for the opposing team. This is a 2-3 point swing in expected value. In late-game situations during the bonus (fouls 7-9), this creates enormous volatility.

### End-of-Game Fouling Strategy

- College teams enter the bonus **earlier** (7th foul vs NBA's 5th per quarter)
- The one-and-one (fouls 7-9) makes intentional fouling more attractive for trailing teams because the front-end miss rate is meaningful (~25-30% for average FT shooters)
- Once in the double bonus (10th foul), the dynamics shift to resemble the NBA
- College players are generally **worse free throw shooters** than NBA players (D-I average ~70% vs NBA ~77%), amplifying the variance

**Trading implication**: In late college games, the transition from bonus to double-bonus is a regime change. When a team is in the one-and-one, the trailing team has a structurally higher comeback probability than markets typically price, because the one-and-one creates more zero-point possessions for the leading team.

---

## 7. Key Differences from NBA for Trading Purposes

### Structural Comparison

| Factor | NCAA | NBA | Trading Impact |
|--------|------|-----|---------------|
| Game length | 40 minutes | 48 minutes | 20% fewer minutes = faster contract expiry |
| Possessions/game | ~68 | ~100 | 32% fewer possessions = higher variance |
| Shot clock | 30 seconds | 24 seconds | Slower pace, longer droughts |
| Halves/Quarters | 2 halves | 4 quarters | One halftime break vs three quarter breaks |
| Free throw rules | Bonus at 7, double at 10 | Penalty at 5/quarter | More variance in foul situations |
| Home court advantage | ~3.5 points | ~2.5 points | Larger location adjustment needed |
| Talent distribution | Extreme inequality | Relatively balanced | More blowouts AND more upsets |
| Number of teams | 362 D-I teams | 30 teams | Less public information, more mispricing |
| Overtime | 5 minutes | 5 minutes | Same structure |
| Player fouls | 5 fouls to foul out | 6 fouls | Key players lost earlier |
| Three-point line | 22'1.75" | 23'9" | Slightly easier threes, more variance from deep |

### Information Asymmetry Advantage

With 362 Division I teams, sportsbooks and prediction markets have significantly less coverage of mid-major and low-major teams. This creates:
- **Early-season mispricing**: Preseason ratings rely heavily on recruiting rankings, which are less predictive for mid-majors
- **Conference tournament value**: Mid-major conference tournament games are among the most mispriced events in all of sports betting
- **Roster turnover**: Transfer portal activity creates massive uncertainty in team quality year-to-year

### Scoring Profile Differences

- College average score: ~70-74 points per team per game
- NBA average score: ~110-115 points per team per game
- College 3-point attempt rate: ~35-38% of field goal attempts
- NBA 3-point attempt rate: ~40-42% of field goal attempts

The lower scoring in college means each made basket shifts win probability more dramatically. A 3-pointer in a 65-60 college game (cutting a 5-point lead to 2) shifts win probability by more than the same shot in a 110-105 NBA game, because the remaining scoring opportunities are fewer.

---

## 8. Specific Data Points for Model Calibration

### Average Margin of Victory

- **Median margin of victory**: 11 points (college basketball)
- **Most common margin**: 2-5 points (with 3 being the single most frequent)
- **Blowout threshold (90th percentile)**: 30+ points
- **One in six games** (16.7%) finishes within 3 points

### Standard Deviation of Outcomes

- **Single team scoring SD**: 7.3-7.9 points per game
- **Game margin SD**: ~10.0-10.6 points
- **KenPom model SD**: 11 points (used for pre-game predictions)
- Approximately **68%** of games finish within 10 points of the true spread
- Approximately **5%** of games have margins exceeding 21+ points from spread

### Comeback Probabilities (College Basketball)

| Deficit at Halftime | Home Team Comeback% | Away Team Comeback% |
|--------------------|--------------------|--------------------|
| 2 points | ~48% | ~42% |
| 5 points | ~35% | ~28% |
| 10 points | ~28% | ~15% |
| 15 points | ~15% | ~8% |
| 20+ points | ~5-8% | ~3-5% |

The "comeback effect" (DRatings analysis, 60,000+ games) shows that trailing teams outperform their talent-based expectation by approximately **2.75 additional points** in the second half, attributed to:
- Coaching adjustments
- Referee bias toward the trailing team
- Psychological factors (leading team relaxes, trailing team intensifies)
- This effect is consistent regardless of home/away status
- **The effect plateaus at 20-point deficits** -- beyond 20, no additional comeback boost is observed

### Bill James Safe Lead Formula

**(Lead - 3 +/- 0.5)^2 > Seconds Remaining**

(Add 0.5 if leading team has ball, subtract 0.5 if trailing team has ball)

| Lead | With Ball | Without Ball | "Safe" Time |
|------|-----------|-------------|-------------|
| 10 pts | (6.5)^2 = 42 sec | (7.5)^2 = 56 sec | < 1 minute |
| 15 pts | (11.5)^2 = 132 sec | (12.5)^2 = 156 sec | ~2:12 - 2:36 |
| 17 pts | (13.5)^2 = 182 sec | (14.5)^2 = 210 sec | ~3:02 - 3:30 |
| 20 pts | (16.5)^2 = 272 sec | (17.5)^2 = 306 sec | ~4:32 - 5:06 |

"Safe" means the probability of a comeback is negligible (<1%). This formula is useful for identifying when Kalshi contracts should trade near $0.99/$0.01.

### Scoring Runs (10-0 Runs)

From Evan Miyakawa's analysis:
- Teams with at least one 10-0 run win **71%** of the time
- Teams with more 10-0 runs than their opponent win **81%** of the time
- Teams with two 10-0 runs in a game win **88%** of the time
- A 15-0 run correlates with winning **86%** of the time
- A 20-0 run correlates with winning **91%** of the time
- Average D-I game features approximately 1-2 scoring runs of 10+ unanswered points

**Trading implication**: When a 10-0 run occurs mid-game, the market tends to overreact. The run itself is often a random cluster (consistent with Poisson process scoring models, per Schilling 2019), and the opponent's subsequent scoring is independent of the run. Buying the trailing team's contract during or immediately after a 10-0 run is a high-expected-value trade when the run shifts contracts beyond the true probability change.

### Win Probability at Specific Game States

Approximate win probabilities for the leading team (equal-strength teams):

| Lead | 20 min left | 10 min left | 5 min left | 2 min left |
|------|------------|------------|-----------|-----------|
| 1 pt | 54% | 58% | 63% | 70% |
| 3 pts | 58% | 65% | 73% | 82% |
| 5 pts | 63% | 72% | 81% | 90% |
| 8 pts | 70% | 80% | 89% | 96% |
| 10 pts | 74% | 85% | 93% | 98% |
| 15 pts | 83% | 93% | 98% | 99.5% |
| 20 pts | 90% | 97% | 99.5% | 99.9% |

These must be adjusted for team strength differential. A 10-point underdog leading by 5 at the half has roughly the same win probability as an equal-strength team leading by 5 minus the expected regression (i.e., ~leading by 0).

---

## 9. Regime-Specific Trading Strategies

### Early Game (20:00 - 12:00 remaining in 2nd half)

- Contracts should trade close to pre-game implied probability unless the score differential exceeds 1 SD (~10 points)
- Scoring runs are common and largely random; market overreaction creates buy opportunities
- Tempo identification is critical: count possessions in the first half to calibrate expected remaining possessions

### Mid-Game (12:00 - 5:00 remaining)

- Win probability begins to diverge meaningfully from pre-game pricing
- The comeback effect is strongest here -- trailing teams have a structural boost
- Bonus/double-bonus status matters: check team foul counts
- Star player foul trouble (4 fouls = sitting) can create 5-10% win probability swings

### Late Game (5:00 - 0:00 remaining)

- Win probability becomes highly non-linear -- small scoring events create large probability shifts
- Free throw shooting skill of specific players becomes dominant
- Intentional fouling regime begins at ~2:00 with one-and-one/double-bonus dynamics
- The Bill James safe lead formula is useful for identifying extreme contract values
- Timeouts remaining matter for the trailing team's ability to manage clock

---

## Sources

- [KenPom In-Game Win Probabilities](https://kenpom.com/blog/ingame-win-probabilities/)
- [KenPom Win Probability for Every College Game](https://kenpom.com/blog/win-probability-for-every-college-game/)
- [KenPom Win Probability for Grown-ups](https://kenpom.com/blog/win-probability-for-grownups/)
- [KenPom Ratings Explanation](https://kenpom.com/blog/ratings-explanation/)
- [Yale YUSAG Improving College Basketball Win Probability Model](https://sports.sites.yale.edu/improving-college-basketball-win-probability-model)
- [Yale YUSAG NCAA Basketball Win Probability Model](https://sports.sites.yale.edu/ncaa-basketball-win-probability-model)
- [The Variance of College Basketball (The Only Colors)](https://www.theonlycolors.com/2020/4/27/21226073/the-variance-of-college-basketball-how-big-is-it-and-where-does-it-come-from)
- [Comeback Probabilities (Professor MJ)](https://www.professormj.com/pages/comeback-probabilities)
- [The Comeback Effect in Basketball (DRatings)](https://www.dratings.com/the-comeback-effect-in-basketball/)
- [Home Court Advantage in College Basketball (BoydsBets)](https://www.boydsbets.com/college-basketball-home-court-advantage/)
- [Determining College Basketball's True Home Court Advantage (VSiN)](https://vsin.com/college-basketball/determining-college-basketballs-true-home-court-advantage/)
- [KenPom: Mining Point Spread Data - Home Court Advantage](https://kenpom.com/blog/mining-point-spread-data-home-court-advantage/)
- [Bill James Safe Lead Formula (Slate)](https://slate.com/news-and-politics/2009/03/bill-james-shares-his-method-to-determine-when-a-college-basketball-game-is-out-of-reach.html)
- [NCAA Tournament Records by Seed](https://www.printyourbrackets.com/ncaa-tournament-records-by-seed.html)
- [NCAA.com History of Seeds in March Madness](https://www.ncaa.com/news/basketball-men/article/2026-02-10/history-1-seed-vs-16-seed-march-madness)
- [Evan Miyakawa: The Power of the 10-0 Run](https://blog.evanmiya.com/p/the-power-of-the-10-0-run)
- [Is Basketball a Game of Runs? (Schilling, 2019)](https://arxiv.org/pdf/1903.08716)
- [Harvard Sports Analysis: Does Slow Tempo Aid NCAA Tournament Upsets?](https://harvardsportsanalysis.wordpress.com/2010/02/11/putting-theories-to-the-test-does-slow-tempo-aid-ncaa-tournament-upsets/)
- [FiveThirtyEight: Is Virginia Too Slow?](https://fivethirtyeight.com/features/is-virginia-too-slow/)
- [NCAA/NFHS Major Basketball Rules Differences (2024-25)](https://ncaaorg.s3.amazonaws.com/championships/sports/basketball/rules/common/2024-25PRXBB_MajorRulesDifferences.pdf)
- [NCAA vs NBA Key Differences for Bettors (SportsBettingDime)](https://www.sportsbettingdime.com/guides/how-to/the-differences-between-betting-on-ncaa-and-nba/)
- [College Basketball Key Numbers (BoydsBets)](https://www.boydsbets.com/college-basketball-key-numbers/)
- [Georgia Tech Logistic Regression/Markov Chain Model for NCAA](https://www2.isye.gatech.edu/~jsokol/ncaa.pdf)
- [Predictive Analytics in College Basketball (Data Action Lab)](https://www.data-action-lab.com/2021/11/21/predictive-analytics-in-college-basketball/)
- [TeamRankings.com NCAA Possessions Per Game](https://www.teamrankings.com/ncaa-basketball/stat/possessions-per-game)
- [Warren Nolan Advanced Stats - Pace](https://www.warrennolan.com/basketball/2025/stats-adv-pace)
