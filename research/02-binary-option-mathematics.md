# Binary Option Mathematics & Pricing Theory

## Cash-or-Nothing Option Pricing (Black-Scholes Adaptation)

**C = Q × e^(-rT) × N(d₂)**

Where:
- Q = payoff amount ($1 in a 0-100 market)
- r = risk-free rate
- T = time to expiration
- N(d₂) = risk-neutral probability of expiring in-the-money
- d₂ = (ln(S/K) + (r - σ²/2)T) / (σ√T)

### Price = Implied Probability
In a 0-100 market: **Price = Implied Probability (as percentage)**
- Market price of 65 → 65% probability of YES
- p = Price / 100

## The Greeks for Binary Options

### Delta (Δ)
Δ = φ × e^(-r_d τ) / (S × σ × √τ) × n(d₂)

- Sensitivity to underlying price changes
- Approaches infinity near expiration for ATM options
- Binary delta has same shape as vanilla call gamma

### Gamma (Γ)
Γ = -φ × e^(-r_d τ) / (S² × σ² × τ) × n(d₂) × d₁

- Rate of change of delta
- Extremely high near expiration
- **This is the key Greek for live sports trading** — late-game score changes create massive probability swings

### Theta (Θ) — Time Decay
- Time decay accelerates dramatically approaching expiration
- Final 3 days: ATM options lose 50-70% of value
- Same-day (0DTE) options: extreme theta decay
- **In sports**: as game clock runs down, uncertainty collapses, theta crushes remaining time value

### Vega (ν)
- Sensitivity to implied volatility
- Sports markets exhibit volatility smile: higher implied vol at extreme probabilities

## Risk-Neutral Pricing Framework

**Price = [p_up × Value_up + (1-p_up) × Value_down] × e^(-r×Δt)**

p_up = (e^(r×Δt) - d) / (u - d)

## Brownian Motion Model for Basketball (Stern, 1994)

Score differential Δ(t) follows Brownian motion with drift:

**dΔ = μ dt + σ dW**

Where:
- μ = drift (home advantage, ~0.3-0.5 pts/min)
- σ = volatility (~0.8-1.0 pts/min)
- dW = Wiener process increment

### Win Probability from Brownian Motion

**P(Home Wins) = Φ((Δ₀ + μT) / √(σ²T))**

Where:
- Φ = normal CDF
- Δ₀ = current score differential
- T = time remaining

### Variance Properties
- Variance grows linearly with time (Brownian motion property)
- After T minutes with σ = 1.0: std dev = √T
- After 10 min: std dev ≈ 3.16 points
- After 48 min: std dev ≈ 6.93 points

## Win Probability Sensitivity Table

| Time Remaining | Lead = 0 | Lead = 3 | Lead = 8 |
|---|---|---|---|
| 10 min | 3-4% per point | 2-2.5% per point | 0.5-1% per point |
| 3 min | 5-7% per point | 3-4% per point | 1-2% per point |
| 30 sec | 10-15% per point | 5-8% per point | 2-3% per point |

## Time-as-Parameter Formula

**Win Probability ≈ Φ((Δ - K(T)) / σ(T))**

- σ(T) → 0 as T → 0 (certain outcome)
- Denominator shrinks, making same lead more decisive
- **This is the gamma explosion effect**

## Monte Carlo Simulation

```
For i = 1 to N:
  For t = 0 to T_remaining:
    Δ(t+dt) = Δ(t) + μ×dt + σ×√dt × Normal(0,1)
  Count: if Δ(T_remaining) > 0: home wins
Win Probability ≈ (wins) / N
```

N = 10,000 typical. Can incorporate regime switches, variable μ/σ by quarter.
