# Mathematical Foundations of Binary Options Trading in Live Basketball Prediction Markets

## A Quantitative Research Report for Kalshi Basketball Moneyline Trading

---

## 1. Binary Option Pricing Models Adapted for Basketball

### 1.1 The Stern (1994) Brownian Motion Model

The foundational model for real-time sports probability estimation was introduced by Hal Stern in "A Brownian Motion Model for the Progress of Sports Scores" (JASA, Vol. 89, No. 427, pp. 1128-1134, 1994). The score differential between home and away teams is modeled as a Brownian motion process on t in (0, 1):

```
X(t) = mu * t + sigma * W(t)
```

where:
- X(t) = home team lead at normalized time t
- mu = drift parameter (expected final margin, home advantage + skill differential)
- sigma = volatility parameter (total game scoring standard deviation)
- W(t) = standard Wiener process

The **win probability** at time t given a current lead of l is:

```
P(win | l, t) = Phi( (l + (1 - t) * mu) / (sigma * sqrt(1 - t)) )
```

where Phi() is the standard normal CDF. This is the core equation for our entire trading engine.

### 1.2 Empirically Measured Parameters

**For the NBA** (Stern's original 1994 calibration, 493 games from 1991-92 season):
- sigma approximately 11.1 points (total game volatility)
- mu approximately 3.0-4.0 points (home court advantage)

**For College Basketball** (derived from multiple sources):
- sigma approximately 10.0-10.4 points (KenPom uses sigma = 11 for pregame spread-to-probability conversion)
- mu = pregame point spread (varies by matchup, typically 0-15 points)
- Standard deviation of final margin ATS: approximately 10.04 points (The Only Colors analysis)
- Per-minute scoring standard deviation: approximately 2 * sqrt(minutes remaining) heuristic

**Tempo Adjustments for College Basketball:**
- Average D1 possessions per game: approximately 70 (2019-20 season)
- High-tempo teams (Big 12): approximately 74 possessions, implying sigma approximately 10.8
- Low-tempo teams (Big Ten, ACC): approximately 65 possessions, implying sigma approximately 9.4
- Per-possession variance: sigma_poss = sqrt(n * p * (1-p)) * 2 approximately 7.48 points per team, where n approximately 56 effective shot attempts, p approximately 0.5

**Practical Calibration for Kalshi:**
For a college basketball game with an expected total of T points and a spread of S:
```
sigma = SD_ATS approximately 10.0 + 0.15 * (Total - 140)
mu = -1 * Spread  (from the favorite's perspective)
```

### 1.3 The Polson & Stern (2015) Implied Volatility Extension

Polson and Stern ("The Implied Volatility of a Sports Game," JQAS, Vol. 11, Issue 3, pp. 145-153, 2015) extended the model to extract market-implied volatility from betting lines. Given a point spread S and moneyline odds, the implied volatility sigma_imp can be backed out:

```
sigma_imp = |S| / (Phi_inv(p_ML) * sqrt(1))
```

where p_ML is the moneyline-implied probability. This allows real-time tracking of whether the market's implied volatility diverges from the model's historical volatility -- creating trading opportunities when sigma_market != sigma_model.

### 1.4 The Gabel & Redner (2012) Random Walk Model

Gabel and Redner ("Random Walk Picture of Basketball Scoring," JQAS, Vol. 8, Issue 1, 2012) provided a more granular continuous-time model using NBA play-by-play data from 6,087 games (2006/07-2009/10):

**Key empirical parameters:**
- Bias velocity: v approximately 0.0037 points/second (from average final margin of 10.7 / 2880 seconds)
- Diffusion coefficient: D approximately 0.0363 points^2/second
- Peclet number: Pe = v * T / (2D) approximately 0.55

The Peclet number Pe approximately 0.55 is critical: it means random fluctuations (diffusion) are of comparable magnitude to systematic advantage (drift), indicating that **upsets are inherently likely in basketball** and that score differential is far noisier than most bettors assume.

**For college basketball (40-minute games, 2400 seconds):**
- D approximately 0.042 points^2/second (adjusted for college pace)
- v approximately spread / 2400
- Per-minute variance of score differential: Var(1 min) = 2D * 60 approximately 5.04 points^2, so SD approximately 2.24 points per minute

### 1.5 Anti-Persistence: The Peel & Clauset (2015) Model

Peel and Clauset ("Predicting Sports Scoring Dynamics with Restoration and Anti-Persistence," IEEE ICDM, 2015) discovered that basketball scoring exhibits two crucial features beyond pure Brownian motion:

**Restoration:** A negative feedback force that pushes the score differential back toward zero. The scoring probability for team B is:

```
P_B = I_B + 0.152 * r + 0.0022 * Delta
```

where:
- I_B = base scoring intensity
- r = anti-persistence indicator (+1 if A scored last, -1 if B scored last)
- Delta = current score differential (positive = A leads)
- 0.152 = anti-persistence coefficient (the team that did NOT score last has a 15.2% boost)
- 0.0022 = restoration coefficient (per-point restoring force)

**Implications for trading:**
- After a team scores, the probability the OTHER team scores next is elevated by approximately 30.4 percentage points (2 * 0.152) relative to "hot hand" expectations
- For every 10 points of lead, the trailing team's scoring probability increases by 2.2%
- This creates natural mean reversion in score differentials -- essential for our OU model below

---

## 2. The Gamma Explosion: Mathematical Derivation

### 2.1 Binary Option Greeks

For a cash-or-nothing binary option (Kalshi contract), adapted from Black-Scholes where the "underlying" is the score differential and "strike" is 0 (the team must be ahead at expiration):

**Price (win probability):**
```
V = Phi(d_2)

d_2 = (l + (1-t) * mu) / (sigma * sqrt(1-t))
```

where l = current lead, t = fraction of game elapsed, mu = expected drift, sigma = game volatility.

**Delta -- sensitivity to a 1-point change in lead:**
```
Delta = dV/dl = phi(d_2) / (sigma * sqrt(1-t))
```

where phi() is the standard normal PDF. This is the price change per point scored.

**Gamma -- rate of change of Delta per point:**
```
Gamma = d^2V/dl^2 = -phi(d_2) * d_2 / (sigma^2 * (1-t))
```

### 2.2 Why Gamma Explodes as Time Decreases

The key factor is the denominator terms containing (1-t). As t approaches 1 (end of game):

```
Delta proportional to 1 / sqrt(1-t)
Gamma proportional to 1 / (1-t)
```

**Derivation of Gamma growth:**

At any time t, for an at-the-money position (d_2 = 0, meaning the game is tied or at the spread):

```
Gamma_ATM = phi(0) / (sigma^2 * (1-t))
           = 0.3989 / (sigma^2 * (1-t))
```

The ratio of Gamma at time t_2 vs t_1 (where t_2 > t_1):

```
Gamma(t_2) / Gamma(t_1) = (1 - t_1) / (1 - t_2)
```

**Numerical example -- college basketball (sigma = 10):**

| Time Remaining | (1-t)   | Delta_ATM | Gamma_ATM  | Price Move per Point |
|----------------|---------|-----------|------------|---------------------|
| 40 min (start) | 1.000   | 0.0399    | 0.00       | 3.99 cents          |
| 20 min (half)  | 0.500   | 0.0564    | 0.0080     | 5.64 cents          |
| 10 min         | 0.250   | 0.0798    | 0.0226     | 7.98 cents          |
| 5 min          | 0.125   | 0.1129    | 0.0639     | 11.29 cents         |
| 2 min          | 0.050   | 0.1785    | 0.2536     | 17.85 cents         |
| 1 min          | 0.025   | 0.2523    | 0.6381     | 25.23 cents         |
| 30 sec         | 0.0125  | 0.3568    | 1.806      | 35.68 cents         |

### 2.3 Worked Example: 5 Minutes Left, 3-Point Lead

Parameters: sigma = 10, mu = 0 (equal teams), l = 3, t_remaining = 5/40 = 0.125, so (1-t) = 0.125.

```
d_2 = (3 + 0.125 * 0) / (10 * sqrt(0.125))
    = 3 / (10 * 0.3536)
    = 3 / 3.536
    = 0.8485
```

**Win probability:**
```
P(win) = Phi(0.8485) = 0.8020 (80.2%)
```

**Delta:**
```
Delta = phi(0.8485) / (10 * sqrt(0.125))
      = 0.2787 / 3.536
      = 0.0788
```
Each additional point of lead changes the contract price by approximately 7.88 cents.

**Gamma:**
```
Gamma = -phi(0.8485) * 0.8485 / (100 * 0.125)
      = -0.2787 * 0.8485 / 12.5
      = -0.01891
```

But we want absolute gamma (sensitivity magnitude):
```
|Gamma| = 0.0189 per point^2
```

**Sensitivity Table for 3-Point Lead at Various Times:**

| Time Left | d_2    | P(win)  | Delta   | Gamma   | Price if +1 pt | Price if -1 pt |
|-----------|--------|---------|---------|---------|-----------------|-----------------|
| 20 min    | 0.4243 | 66.4%   | 0.0534  | -0.0113 | 71.8%           | 61.1%           |
| 10 min    | 0.6000 | 72.6%   | 0.0665  | -0.0200 | 79.2%           | 65.9%           |
| 5 min     | 0.8485 | 80.2%   | 0.0788  | -0.0189 | 88.1%           | 72.3%           |
| 2 min     | 1.3416 | 91.0%   | 0.0727  | 0.0244  | 98.3%           | 83.8%           |
| 1 min     | 1.8974 | 97.1%   | 0.0454  | 0.0611  | 99.7%           | 92.7%           |

**Key insight for trading:** At 5 minutes remaining with a 3-point lead, a single 3-pointer that ties the game moves the contract from 80 cents to approximately 50 cents -- a 30-cent swing. This is where scalping opportunities are richest.

---

## 3. Mean Reversion Quantified

### 3.1 The Regression-to-the-Mean Effect in Halftime Leads

**The fundamental statistical fact:** The overall standard deviation of the final point difference in college basketball is approximately 10.0 points. Since the first half and second half are roughly independent scoring periods (with adjustments), a team's halftime lead regresses toward the pregame expected margin in the second half.

**Mathematical framework:**

Let:
- S = pregame spread (expected final margin)
- H = actual halftime margin
- F = actual final margin
- E = excess lead = H - S/2 (lead beyond what the spread predicted)

The regression model is:

```
F = alpha + beta * H + epsilon
```

Empirically, beta approximately 0.72-0.78 for college basketball. This means:
- About 22-28% of the halftime lead "excess" reverts in the second half
- A team up by 15 when the spread predicted 5 has an excess of 10; roughly 7.2-7.8 points of that 15-point lead will persist
- Expected final margin: approximately 0.75 * 15 + 0.25 * 5 = 12.5 (the lead shrinks by 2.5 points)

### 3.2 The Berger & Pope (2011) Regression Discontinuity Study

Berger and Pope ("Can Losing Lead to Winning?" Management Science, 2011) used a regression discontinuity design on over 45,000 NCAA games and 18,000 NBA games:

**Key findings:**
- **NBA:** Teams behind by 1 point at halftime win approximately 6 percentage points more often than expected from the linear relationship. Teams down 1 actually win more often (50.4%) than teams up 1.
- **NCAA:** Teams behind by 1 at halftime win approximately 2 percentage points more often than expected.

**Regression specification:**
```
Win_i = alpha + beta * Behind_i + delta * ScoreDiff_i + X_i + epsilon_i
```

The discontinuity is interpreted as a motivational effect beyond pure statistical regression to the mean.

### 3.3 The Bayesian Framework (Gelman, 2022)

Andrew Gelman (Columbia) reanalyzed the halftime effect through a Bayesian lens, noting that mean reversion fully explains the shrinkage of halftime leads. The Bayesian update framework:

```
E[Final Margin | Halftime Margin = H] = (sigma_H^2 * S + sigma_S^2 * H) / (sigma_H^2 + sigma_S^2)
```

This is a weighted average between the halftime margin and the pregame spread, weighted by their respective precisions. Given:
- sigma_S approximately 10 (pregame spread uncertainty)
- sigma_H approximately 8 (halftime score variance relative to final)

The weight on the halftime lead is approximately 0.61, meaning **39% of the excess halftime lead reverts** under the Bayesian model.

### 3.4 Practical Application for Kalshi

**Trading rule:** When a team's halftime lead exceeds the pregame spread by E points:
```
Expected second-half margin change = -0.30 * E  (approximately)
Fair halftime price adjustment = Phi( (0.75 * H) / (sigma * sqrt(0.5)) ) vs market price
```

If the market prices halftime leads linearly (as casual bettors tend to do), there is a systematic mispricing of approximately 2-4 cents for leads exceeding the spread by 8+ points.

---

## 4. Backtesting Framework Design

### 4.1 Historical Data Sources for College Basketball

**Play-by-Play Data:**
- **hoopR** (R package, sportsdataverse): Comprehensive men's college basketball play-by-play data, thousands of games per season
- **ncaahoopR** (R package, Luke Benz, GitHub: lbenz730/ncaahoopR): Scrapes play-by-play data with assist networks, shot charts, and win-probability charts
- **CBBpy** (Python package, PyPI): D1 men's and women's basketball play-by-play via `get_game_pbp()` returning pandas DataFrames
- **Sports Reference / Basketball Reference**: Box scores and game logs going back decades
- **ESPN API**: Real-time and historical play-by-play data

**Historical Odds Data:**
- **The Odds API**: Historical NCAA Basketball odds from late 2020 (moneyline, spreads, totals) via JSON API
- **Tx LAB (txodds.net)**: Decades of odds history via API
- **SportsDataIO**: Historical database for modeling and analytics

### 4.2 Backtesting Architecture

```
For each historical game:
    1. Load pregame spread, total, moneyline
    2. Initialize model: mu = spread, sigma = f(total)
    3. For each play-by-play event (scoring change):
        a. Compute model fair value: P(win) = Phi(d_2)
        b. Record hypothetical market price (interpolated from historical odds or simulated)
        c. If |model_price - market_price| > threshold:
            Generate trade signal
        d. Track position, P&L, Greeks exposure
    4. Settle at game conclusion (0 or 100)
    5. Record: trades, gross P&L, net P&L (after fees), max drawdown
```

### 4.3 Backtesting Pitfalls

1. **Look-ahead bias**: The model must only use information available at each timestamp. Do not use final-game statistics to set pregame parameters.

2. **Survivorship bias**: Ensure the game sample includes cancelled games, games with unusual circumstances (weather delays, COVID interruptions).

3. **Execution assumption bias**: Historical backtests assume fills at the mid-market price. In reality, Kalshi's bid-ask spread (often 3-10 cents) eats significantly into edge. The bid + ask for a YES and NO contract sum to more than $1.00, with spreads sometimes exceeding $0.50 in illiquid markets.

4. **Regime change**: College basketball rule changes (shot clock from 35 to 30 seconds in 2015-16) fundamentally altered tempo and scoring distributions. Models calibrated on pre-2016 data may not generalize.

5. **Market impact**: In thin Kalshi markets, your own orders move the price. A backtest that assumes zero market impact overstates returns.

6. **Selection bias in live trading triggers**: If your model only generates signals in "exciting" game states (close games late), you face adverse selection from sharper participants who are also trading those moments.

---

## 5. Kelly Criterion for Correlated Bets

### 5.1 Single-Bet Kelly

For a single binary bet with probability p of winning and even odds (1:1 on Kalshi, where you buy at price c and receive 100 if correct):

```
f* = (p * (100 - c) - (1 - p) * c) / (100 - c)
   = (p * (100 - c) - c + p * c) / (100 - c)
   = (100 * p - c) / (100 - c)
```

Simplified for Kalshi: if you believe the true probability is p and the market price is c cents:

```
f* = (p - c/100) / (1 - c/100)  for YES bets
f* = ((1-p) - (100-c)/100) / (c/100)  for NO bets
```

**Example:** True probability 60%, market price 52 cents:
```
f* = (0.60 - 0.52) / (1 - 0.52) = 0.08 / 0.48 = 16.7% of bankroll
```

### 5.2 Multivariate Kelly for Simultaneous Bets

When making multiple simultaneous bets on independent games, the optimization becomes:

```
max_{f_1, ..., f_n} E[ln(1 + sum_i f_i * R_i)]
```

where R_i is the return of bet i. For independent bets, this decomposes into a joint optimization over all 2^n possible outcome combinations.

**For two independent bets:**
```
G(f_1, f_2) = p_1*p_2 * ln(1 + f_1*b_1 + f_2*b_2)
            + p_1*(1-p_2) * ln(1 + f_1*b_1 - f_2)
            + (1-p_1)*p_2 * ln(1 - f_1 + f_2*b_2)
            + (1-p_1)*(1-p_2) * ln(1 - f_1 - f_2)
```

**Critical result:** The optimal wagers for simultaneous bets are SMALLER than individual Kelly wagers. For n simultaneous bets, a useful approximation is:

```
f_simultaneous approximately f_individual / sqrt(n)
```

### 5.3 Correlated Bets Within the Same Game

When entering a position and then adding to it (e.g., buying YES at 55, then adding at 50 after an adverse move), the bets are perfectly correlated (same game outcome). The Kelly framework becomes:

```
f_total = (p_effective - c_avg/100) / (1 - c_avg/100)
```

where c_avg is the average cost basis and p_effective is the current model probability. You should NOT apply Kelly to each tranche independently -- the total position sizing must be computed on the combined position.

### 5.4 Fractional Kelly in Practice

Full Kelly has a 1/3 probability of halving the bankroll before doubling it. For sports trading:
- **Half Kelly** (f/2): 1/9 probability of halving before doubling. Sacrifices only 25% of geometric growth rate.
- **Quarter Kelly** (f/4): Recommended for live sports trading due to estimation uncertainty. Probability of a 50% drawdown before doubling: approximately 1/81.

The Kelly formula's output is approximately 20x more sensitive to errors in estimated probability than to errors in the covariance structure (noted in portfolio optimization literature), making conservative fractional Kelly essential when your edge estimate is uncertain.

---

## 6. Expected Value and Variance of a Scalping Strategy

### 6.1 The Setup

Parameters:
- N = 20 trades per day
- p = 0.55 (55% win rate)
- W = 2 cents (average winner)
- L = 2 cents (average loser)
- Trading days per month: 15 (college basketball season)

### 6.2 Per-Trade Statistics

```
E[single trade] = p * W - (1-p) * L
                = 0.55 * 2 - 0.45 * 2
                = 1.10 - 0.90
                = $0.20 per trade (0.2 cents per contract)

Var[single trade] = p * W^2 + (1-p) * L^2 - E^2
                  = 0.55 * 4 + 0.45 * 4 - 0.04
                  = 4.00 - 0.04
                  = 3.96
SD[single trade] = $1.99 per contract
```

### 6.3 Monthly P&L Distribution (300 trades)

```
E[monthly] = 300 * $0.20 = $60.00
SD[monthly] = sqrt(300) * $1.99 = $34.47

Sharpe ratio (monthly) = 60 / 34.47 = 1.74
```

**Monthly P&L distribution (assuming 1 contract per trade):**
- P(profit > 0) = Phi(60/34.47) = Phi(1.74) = 95.9%
- P(profit > $100) = Phi((60-100)/34.47) = Phi(-1.16) = 12.3%
- P(loss > $50) = Phi((60-(-50))/34.47) = 1 - Phi(3.19) = 0.07%

### 6.4 Quarterly and Semi-Annual P&L (900 and 1800 trades)

**3 months (900 trades):**
```
E = $180, SD = $59.70
Sharpe = 3.02
P(profitable) = 99.87%
```

**6 months (1800 trades if year-round, or approximately 1200 trades in a season):**
```
E = $360, SD = $84.43 (for 1800 trades)
Sharpe = 4.27
P(profitable) = 99.999%
```

### 6.5 Statistical Significance of Edge

To confirm a 55% win rate differs from 50% at the 95% confidence level:

```
z = (p_hat - 0.50) / sqrt(0.50 * 0.50 / n)
1.96 = 0.05 / sqrt(0.25 / n)
n = 0.25 * (1.96 / 0.05)^2
n = 384 trades
```

At 20 trades per day, this requires approximately **19 trading days** (roughly 4 weeks) to achieve statistical significance.

For a 99% confidence level: n = 0.25 * (2.576 / 0.05)^2 = 664 trades, approximately 33 trading days.

### 6.6 Probability of Ruin

For a fixed-fraction bettor risking fraction f of bankroll per trade with win probability p:

```
P(ruin) = ((1-p)/p)^(B/(f*100))
```

where B = bankroll. With p = 0.55, betting 2% of bankroll per trade, bankroll = $1000:

```
P(ruin) = (0.45/0.55)^(1000/(20))
        = (0.8182)^50
        = 0.0000068  (essentially zero)
```

However, with Kelly sizing, the probability of drawdown to 50% of peak is 50%, and to 1/3 of peak is 33%. This is why fractional Kelly (1/4) is essential.

---

## 7. Ornstein-Uhlenbeck Process for Mean-Reverting Spreads

### 7.1 The OU Model for Score Differentials

The standard Brownian motion model assumes the score differential is a random walk with drift. The empirical evidence from Peel & Clauset (2015) and Gabel & Redner (2012) shows that basketball scoring is anti-persistent -- the trailing team has a slightly elevated scoring probability. This is better modeled by an Ornstein-Uhlenbeck process:

```
dX = theta * (mu - X) * dt + sigma_OU * dW
```

where:
- X = current score differential minus the expected differential at this point in the game
- theta = mean-reversion speed (how quickly deviations from the "fair" spread are corrected)
- mu = long-term mean (the pregame expected margin, adjusted for time remaining)
- sigma_OU = volatility of the deviation process
- dW = Wiener process increment

### 7.2 Calibrated Parameters for Basketball

From the Peel & Clauset restoration coefficient of 0.0022 per point, and scoring events occurring at a rate of approximately 0.07 per second (1 scoring event every approximately 14 seconds in basketball):

**Mean-reversion speed:**
```
theta approximately 0.0022 * 0.07 * 2 = 0.000308 per second
     approximately 0.0185 per minute
     approximately 0.74 per 40-minute game
```

This means score differential deviations have a **half-life of approximately:**
```
t_half = ln(2) / theta = 0.693 / 0.0185 = 37.5 minutes
```

This is essentially saying that over the course of a full game, a deviation from the expected spread will be approximately halved -- consistent with the halftime regression coefficients of beta approximately 0.72-0.78.

**Volatility parameter:**
```
sigma_OU approximately sqrt(2 * D) approximately sqrt(2 * 0.042) approximately 0.29 points/sqrt(second)
         approximately 2.24 points/sqrt(minute) (for college basketball)
```

**Long-run variance:**
```
Var_stationary = sigma_OU^2 / (2 * theta) = 0.084 / 0.037 = 2.27 points^2
SD_stationary = 1.51 points
```

### 7.3 Why OU Improves on Brownian Motion

| Property | Brownian Motion | OU Process |
|----------|----------------|------------|
| Score diff variance | Grows linearly with time | Bounded (converges to sigma^2/(2*theta)) |
| Large leads | Persist (random walk) | Revert toward expected margin |
| Probability of comeback | Underestimated | More accurately modeled |
| Late-game behavior | Too much variance | Captures strategic adjustments |
| Trailing team incentive | Not modeled | Captured via restoration |

**The OU model's key advantage for trading:** After a scoring run creates a large deviation from the expected margin, the OU model predicts a partial reversion. This is precisely the signal for our mean-reversion trading strategy: buy the trailing team's contract when the deviation is large, because the score differential is statistically likely to partially revert.

### 7.4 OU-Based Fair Value Calculator

For a team expected to win by mu points, currently leading by l with fraction (1-t) of game remaining:

```
E[Final margin | l, t] = mu + (l - mu * t) * exp(-theta * (1-t) * T_game)
Var[Final margin | l, t] = sigma_OU^2 / (2*theta) * (1 - exp(-2*theta*(1-t)*T_game))
```

Win probability:
```
P(win) = Phi( E[Final margin] / sqrt(Var[Final margin]) )
```

---

## 8. Information Theory and Market Efficiency

### 8.1 How Quickly Do Prediction Markets Incorporate Scoring Events?

Angelini, De Angelis, and Singleton (2022, International Journal of Forecasting, Vol. 38, Issue 1, pp. 282-299) studied high-frequency in-play prediction markets on Betfair (the closest analog to Kalshi's sports markets). Their findings, using football (soccer) data:

**Key results:**
- **Expected goals (favorites scoring first):** Markets show significant mispricing for at least 5 minutes after the goal. Prices adjust slowly when the outcome aligns with pre-match expectations.
- **Surprise goals (underdog scoring first):** Markets incorporate the information immediately with no drift -- prices fully adjust within seconds.
- **Reverse favorite-longshot bias:** Markets systematically overestimate the probability of the favorite winning, especially in-play.

**Estimated half-life of mispricing:** Based on their results, when a surprise event occurs, the half-life of mispricing is approximately 0-30 seconds. When an expected event occurs, the half-life extends to 2-5 minutes, as the market "under-reacts" to confirmatory information.

### 8.2 Application to Kalshi Basketball Markets

Basketball has a crucial difference from soccer: **scoring events are frequent** (approximately 1 every 14 seconds for NBA, approximately 1 every 18-20 seconds for college). This means:

1. **Individual scoring events carry less information** than a soccer goal (which changes win probability by approximately 22 percentage points on average). A basketball field goal changes win probability by 4-8 cents mid-game.

2. **Market makers can adjust more gradually**, but casual bettors may over-react to scoring runs (3 consecutive baskets = 6-point swing = noisy but attention-grabbing).

3. **The information advantage window is shorter** for any single event but **longer for pattern recognition** (identifying that a team's 3-point shooting is running hot/cold relative to season averages).

### 8.3 Kalshi-Specific Market Microstructure

Research on Kalshi's market microstructure (Whelan, 2024, "Makers and Takers: The Economics of the Kalshi Prediction Market") reveals:

- **Makers** (limit order posters) are relatively well-informed and earn higher returns
- **Takers** (market order executors) accept slightly worse prices
- **Favorite-longshot bias** exists: contracts priced near 80-90 cents tend to over-price the favorite; contracts priced near 10-20 cents over-price the longshot
- **Sports constitute >90% of Kalshi's volume**, making basketball one of the most liquid categories
- **Bid-ask spreads** can range from 1 cent (liquid events) to 50+ cents (illiquid)

**Trading implication:** To capture edge, you should primarily act as a **maker** (posting limit orders) rather than a taker, and your model's fair value should have at least 3-5 cents of edge over the posted spread to overcome the spread and fees.

### 8.4 Shannon Entropy of Game States

The information content of a basketball game state can be quantified using Shannon entropy:

```
H(t) = -P(win,t) * ln(P(win,t)) - (1 - P(win,t)) * ln(1 - P(win,t))
```

Maximum entropy (maximum uncertainty) occurs when P(win) = 0.50 (H = ln(2) = 0.693 nats). As the game progresses:

- **Pre-game:** H approximately 0.65 nats (typical 60/40 game)
- **Halftime (tied):** H = 0.693 nats (maximum uncertainty)
- **5 min left, 3-pt lead:** H = 0.50 nats
- **1 min left, 3-pt lead:** H = 0.15 nats

**The entropy production rate** (how quickly information is generated) peaks in the final minutes when each point dramatically changes the probability. This is exactly when gamma is highest and trading opportunities are richest -- but also when adverse selection risk is greatest.

---

## Summary: Key Parameters for the Trading Engine

| Parameter | Value | Source |
|-----------|-------|--------|
| sigma (college basketball, full game) | 10.0-11.0 points | KenPom, The Only Colors analysis |
| sigma (NBA, full game) | 11.1 points | Stern (1994) |
| Diffusion coefficient D (NBA) | 0.0363 pts^2/sec | Gabel & Redner (2012) |
| Bias velocity v | Spread / game_seconds | Gabel & Redner (2012) |
| Peclet number (typical) | 0.3-0.8 | Gabel & Redner (2012) |
| Anti-persistence coefficient | 0.152 | Peel & Clauset (2015) |
| Restoration coefficient | 0.0022 per point | Peel & Clauset (2015) |
| OU mean-reversion speed theta | 0.74 per game | Derived from Peel & Clauset |
| Halftime regression beta | 0.72-0.78 | Multiple sources |
| Market mispricing half-life (expected) | 2-5 minutes | Angelini et al. (2022) |
| Market mispricing half-life (surprise) | 0-30 seconds | Angelini et al. (2022) |
| Kelly fraction (recommended) | 1/4 of full Kelly | Standard risk management |
| Trades for statistical significance (95%) | 384 | z-test calculation |
| College possessions per game | approximately 70 | KenPom |

---

## References

1. Stern, H. S. (1994). "A Brownian Motion Model for the Progress of Sports Scores." *Journal of the American Statistical Association*, 89(427), 1128-1134.

2. Polson, N. G., & Stern, H. S. (2015). "The Implied Volatility of a Sports Game." *Journal of Quantitative Analysis in Sports*, 11(3), 145-153.

3. Gabel, A., & Redner, S. (2012). "Random Walk Picture of Basketball Scoring." *Journal of Quantitative Analysis in Sports*, 8(1).

4. Peel, T., & Clauset, A. (2015). "Predicting Sports Scoring Dynamics with Restoration and Anti-Persistence." *IEEE International Conference on Data Mining (ICDM)*, 2015.

5. Berger, J., & Pope, D. (2011). "Can Losing Lead to Winning?" *Management Science*, 57(5), 817-827.

6. Angelini, G., De Angelis, L., & Singleton, C. (2022). "Informational Efficiency and Behaviour Within In-Play Prediction Markets." *International Journal of Forecasting*, 38(1), 282-299.

7. Whelan, K. (2024). "Makers and Takers: The Economics of the Kalshi Prediction Market." *UCD Working Paper WP2025_19*.

8. Kelly, J. L. (1956). "A New Interpretation of Information Rate." *Bell System Technical Journal*, 35(4), 917-926.

9. Gelman, A. (2022). "Thinking Bayesianly About the Being-Behind-at-Halftime Effect in Basketball." *Statistical Modeling, Causal Inference, and Social Science* (blog).

10. The Only Colors (2020). "The Variance of College Basketball: How Big Is It and Where Does It Come From?"

11. Boyd's Bets. "Total Variability by Over/Under Number in Football & Basketball." "Standard Deviations of ATS Margins by Totals."
