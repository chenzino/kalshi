# Scalping & Position Sizing Strategy

## Our Edge Model

### The Strategy (User-Defined Constraints)
1. Trade moneyline markets (0-100 cents, binary resolution)
2. Time remaining is a critical factor — changes more impactful as game progresses
3. Games trend around the mean — exploit regression toward opening line
4. Live trading only (in-play markets)
5. **Target**: Many trades, small gains, 20-85% price range, 1-3 cent increases (2-15% gains per trade)
6. Short holding horizons

### Expected Value Calculation

For a 1-3 cent edge on $1 market:

**EV = (p × payout) - ((1-p) × stake)**

Example — True probability 51.5%, market price 50¢:
- EV = (0.515 × $0.50) - (0.485 × $0.50) = $0.015 per contract
- 1000 trades × $0.015 = $15 profit

For a 3-cent edge (buy at 50, fair value 53):
- EV = (0.53 × $0.50) - (0.47 × $0.50) = $0.03 per contract
- 1000 trades × $0.03 = $30 profit

## Kelly Criterion for Binary Outcomes

**f = (bp - q) / b**

Where:
- f = fraction of bankroll to bet
- p = true probability of winning
- q = 1 - p
- b = net odds (payout / stake)

### Example
- True probability: 55%, market at 50¢
- b = $0.50 / $0.50 = 1.0
- f = (1.0 × 0.55 - 0.45) / 1.0 = **10%**

### Fractional Kelly (RECOMMENDED)

| Kelly Fraction | Bet Size | Risk of Halving Before Doubling |
|---|---|---|
| Full Kelly | 10% | 33% |
| 1/2 Kelly | 5% | 11% |
| 1/4 Kelly | 2.5% | ~3% |

**Use 1/4 to 1/2 Kelly** — protects against estimation errors, reduces volatility.

## Scalping Execution Framework

### Entry Signals (BUY)
1. Market drops 3+ cents on scoring run against our team
2. Our model shows fair value is 3+ cents above current price
3. Team's in-game shooting % is significantly below season average (regression expected)
4. Time remaining is sufficient for regression (> 3 minutes)
5. Score differential still within 2 standard deviations of pre-game spread

### Exit Signals (SELL)
1. Market recovers 1-3 cents from entry (target hit)
2. Score changes unfavorably (stop loss)
3. Holding period exceeds target horizon
4. Model fair value drops below entry price

### Stop Loss Rules
- Max loss per trade: 3-5 cents
- Max loss per game: 10% of session bankroll
- Max concurrent positions: 3-5

## Market Microstructure

### Order Flow Analysis
**Order Flow Imbalance (OFI) = (Buy Orders - Sell Orders) / Total Orders**

- Positive OFI predicts upward price movement (R² = 0.25)
- Can detect sharp/smart money flow
- Widening spreads indicate uncertainty

### Bid-Ask Spread Dynamics
- Tight spreads during major events (2¢ common)
- Spreads widen after scoring events (uncertainty spike)
- Tighten again as market digests information
- **Effective Spread = 2 × |Trade Price - Mid-Quote|**

### Execution Strategy
- **Limit orders preferred** (maker fees lower than taker)
- Place limit buy slightly above best bid
- Place limit sell slightly below best ask
- If market moves favorably before fill, chase with market order

## The Gamma Scalping Opportunity

### Theta-Gamma Trade-off
As game progresses:
- **Theta** (time decay) works in favor if long probability in leading team
- **Gamma** amplifies P&L on score changes

### Optimal Trading Windows

| Game Phase | Time Left | Strategy | Risk |
|---|---|---|---|
| Early game | 30-40 min | Mean reversion, wide stops | Low gamma, high uncertainty |
| Mid game | 10-30 min | Best window: enough time for reversion, moderate gamma | Balanced |
| Late game | 3-10 min | Gamma scalping, tight stops | High gamma, fast moves |
| Final minutes | < 3 min | Very selective, only clear mispricings | Extreme gamma |
| Garbage time | Blowout | Do not trade | No edge |

### Sweet Spot: 20-85% Price Range
- Below 20%: Low liquidity, wide spreads, hard to exit
- Above 85%: Minimal upside (3-15 cents max), high risk of upset
- **20-50%**: Best for buying — maximum upside on mean reversion
- **50-85%**: Best for selling — capture regression from overextended leads

## Portfolio Approach

### Diversification Rules
- Trade multiple games simultaneously
- Different games = near-independent bets (correlation 0.0-0.05)
- Same game multiple entries = correlated (reduce size)
- Target 10-20 trades per session across 3-5 games

### Risk Management
- Max 2% of bankroll per trade (1/4 Kelly)
- Max 10% of bankroll per game
- Max 25% of bankroll deployed at any time
- Track P&L in real-time, stop trading session if down 15%
