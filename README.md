# Kalshi Basketball Live Trading Engine

Quantitative research and (eventually) automated trading system for Kalshi basketball prediction markets.

## Research

See `/research/` for comprehensive mathematical foundations:

1. **Market Structure** — Kalshi API, order book, fees, regulatory
2. **Binary Option Mathematics** — Pricing theory, Greeks, Brownian motion
3. **Win Probability Models** — Logistic regression, Markov chains, benchmarks
4. **Mean Reversion Strategy** — Scoring dynamics, Four Factors, regression
5. **Scalping Strategy** — Kelly criterion, position sizing, execution framework
6. **Time Decay & Gamma** — Sensitivity analysis, implied volatility, gamma scalping
7. **Scoring Runs** — Run prediction, detection algorithms, counter-run trading

## Strategy Summary

Trade moneyline markets (0-100¢) during live college basketball and NBA games. Exploit mean reversion and market overreaction to scoring runs. Target 1-3 cent gains per trade across the 20-85% price range with short holding horizons.

## Roadmap

- [x] Phase 1: Mathematical research & strategy development
- [ ] Phase 2: Backtesting framework with historical data
- [ ] Phase 3: Kalshi API integration (demo environment)
- [ ] Phase 4: Live paper trading
- [ ] Phase 5: Live trading with real capital

## Architecture (Planned)

```
┌─────────────────┐    ┌──────────────┐    ┌─────────────┐
│  Data Feeds      │───▶│  Win Prob     │───▶│  Signal      │
│  (scores, time,  │    │  Model        │    │  Generator   │
│   possession)    │    │  (fair value) │    │  (edge calc) │
└─────────────────┘    └──────────────┘    └──────┬──────┘
                                                   │
┌─────────────────┐    ┌──────────────┐    ┌──────▼──────┐
│  Risk Manager    │◀──│  Order        │◀──│  Position    │
│  (Kelly, stops,  │    │  Executor     │    │  Sizer       │
│   portfolio)     │    │  (Kalshi API) │    │  (Kelly/4)   │
└─────────────────┘    └──────────────┘    └─────────────┘
```
