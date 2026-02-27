# Kalshi Market Structure & API Research

## Binary Contract Specifications

- **Price Range**: Contracts price from $0.01 (1 cent) to $0.99 (99 cents), representing market-implied probability
- **Tick Size**: Minimum price increment is $0.01 (one cent)
- **Binary Resolution**: YES/NO contracts settle at exactly $1.00 for correct predictions or $0.00 for incorrect
- **Probability Interpretation**: A 68-cent YES contract = market estimates 68% likelihood
- **Payout Structure**: Max loss = purchase price; potential gain = $1 - purchase price
- **Paired Contracts**: Each market has YES and NO contract pairs

## Basketball Market Types

- Single-game moneyline markets: "Will [Team] win [Game]?"
- Point spreads
- Totals (Over/Under)
- Player props
- Coverage: NFL, NBA, NCAA football and basketball, MLB, NHL, soccer, tennis, esports

## Order Book Structure

- **Quote-Driven Market**: Decentralized, price quotes 1¢ to 99¢
- **Maker/Taker Model**: Makers declare side/price/quantity, takers match most generous offer
- **Price Priority**: Orders execute by price first, then time priority
- **Bid-Ask Example**: Best YES bid 42¢, implied ask (from NO side) 44¢ = 2¢ spread
- **Real-time Updates**: WebSocket API streams continuous order book updates

## Kalshi API Architecture

### Protocol Support
- **REST API**: `https://trading-api.kalshi.com/trade-api/v2`
- **WebSocket**: Real-time streaming for lower latency
- **FIX 4.4**: Lowest-latency protocol option (requires TLS/SSL)
- **Demo Environment**: `https://demo-api.kalshi.co/trade-api/v2`

### Key Endpoints
- Market data (individual markets, candlesticks, order books, trades)
- Order placement, modification, cancellation
- Portfolio management
- Fill tracking and execution confirmation

### Authentication
- `KALSHI-ACCESS-KEY`: Key ID
- `KALSHI-ACCESS-TIMESTAMP`: Request timestamp in ms
- `KALSHI-ACCESS-SIGNATURE`: RSA-PSS signed hash (SHA-256)
- Sign path WITHOUT query parameters

### Rate Limits
- 429 error responses for excess requests
- Implement exponential backoff
- Higher limits available via advanced access request
- Better suited for medium-frequency or event-driven strategies

### SDKs
- Python SDK (official): type-safe models, automatic signing
- TypeScript SDK (official)
- Docs: docs.kalshi.com

## Fee Structure

- Transaction-based: fee on expected earnings, not contract cost
- **Maker orders**: Lower fees (liquidity provision incentive)
- **Taker orders**: Higher fees for immediate execution
- **Price-based variation**: Lowest fees at 1-5¢ or 95-99¢; highest at 50¢
- Max commission: up to $0.02 per contract / up to 2% on positions
- No cancellation fees

## Live Trading Characteristics

- Markets remain open during games
- Contract prices fluctuate real-time as game events unfold
- Can cash out positions anytime before settlement
- **Recent liquidity**: $403M single-day NFL volume (Jan 4, 2026), nearly $2B NFL playoffs
- 24M+ users via Robinhood/Coinbase integration

## Regulatory Framework (CFTC)

- First CFTC-regulated prediction market exchange (Designated Contract Market)
- **Prohibited**: Insider trading, wash trading, front-running, money pass, market manipulation
- KYC/AML mandatory; all trades reported to CFTC daily
- Algorithmic trading: **allowed** under ToS, FIX connections require TLS/SSL
- 200+ insider trading investigations in past year
