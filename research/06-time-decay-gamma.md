# Time Decay & Gamma Effects in Live Sports Markets

## The Gamma Explosion

As game time decreases, gamma increases dramatically for near-tied games.

### Key Property
**σ(T) → 0 as T → 0**

The uncertainty parameter shrinks toward zero as time expires, meaning the same score differential maps to increasingly extreme probabilities.

### Win Probability Sensitivity by Time

| Time Remaining | Tied Game | 3-pt Lead | 8-pt Lead |
|---|---|---|---|
| 10 min | 3-4% per point | 2-2.5% per point | 0.5-1% per point |
| 3 min | 5-7% per point | 3-4% per point | 1-2% per point |
| 30 sec | 10-15% per point | 5-8% per point | 2-3% per point |

### What This Means for Trading

A single basket (2-3 points) with 30 seconds left in a tied game moves the market **20-45 cents**. That same basket with 10 minutes left moves it **6-12 cents**.

## Time Decay (Theta) in Sports Markets

### Analogy to Options
- **0DTE (same-day expiration)**: Games finishing within hours exhibit extreme theta
- **ATM straddle losing 50-70% of value** in final period with no price movement
- Time decay is severe: rapid time value loss for uncertain outcomes

### Theta Works FOR You When:
- You're long the leading team's probability
- The lead is maintained as clock runs down
- Each tick of the clock adds certainty to your position

### Theta Works AGAINST You When:
- You're long the trailing team's probability
- You need a scoring event to profit
- Time is running out for your thesis to play out

## The Theta-Gamma Trade-off

### For Scalpers in Final Minutes:
1. **Theta** (time decay) works in your favor if long the leader
2. **Gamma** amplifies P&L on score changes
3. Net effect: "gamma scalping" opportunity

### Example Trade
- Buy YES at 52¢ (high uncertainty, near-tied game)
- Score changes induce volatility → market moves to 58¢
- Sell at 58¢ → 6 cent gain (11.5% return)
- Holding time: 30 seconds to 2 minutes

## Implied Volatility in Sports Markets

### Volatility Smile
Sports markets exhibit characteristic shape:
- **ATM (50%)**: Moderate implied volatility
- **OTM/ITM (20% or 80%)**: Higher implied volatility
- Reflects market pricing of tail risks

### Volatility Regimes by Game Phase

| Phase | Implied Vol | Market Behavior |
|---|---|---|
| Pre-game | Moderate | Stable, slow drift |
| Tip-off to 10 min | Rising | Initial uncertainty resolution |
| Mid-game | Peak | Maximum information flow |
| Under 5 min | Declining (if blowout) or Peak (if close) | Depends on score |
| Final minute | Extreme for close games, near-zero for blowouts | Binary outcomes |

## Practical Gamma Scalping Strategy

### Setup
1. Identify games where score is within 5 points with 5-10 minutes remaining
2. Market should be in 40-60% range (maximum gamma)
3. Wait for a scoring event that moves market 3+ cents

### Execution
1. After scoring event moves market away from model fair value
2. Enter position betting on partial reversion
3. Target 1-3 cent gain
4. Stop loss: 3 cents against you OR next scoring event against you

### Why This Works
- Gamma amplifies moves: each basket matters more
- Markets overshoot on emotional/reactive trading
- Mean reversion still operates (teams trade baskets)
- Short holding time limits exposure

## Garbage Time Thresholds

### When to STOP Trading

**Cleaning the Glass definition**:
- Q4: Lead ≥ 25 (min 12-9), ≥ 20 (min 9-6), ≥ 10 (remainder)
- Two or fewer starters combined on floor

**KenPom threshold**:
- 18-point lead: correlation between remaining margin and subsequent outcomes = 0
- At this point, game outcome is deterministic

**82games.com**:
- Lead ≥ (10 + 1 point per minute remaining)

### Trading Cutoffs
- **Stop trading when**: Lead > 15 with < 5 min remaining
- **Definitely stop when**: Lead > 20 at any point in 4th quarter
- **Exception**: If market still prices underdog at > 15%, there may be edge
