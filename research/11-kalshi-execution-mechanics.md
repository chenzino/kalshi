# Kalshi Execution Mechanics & Market Microstructure

## Fee Structure Deep Dive

### Exact Fee Formulas

**Taker Fee**: `ceil(0.07 × C × P × (1 - P))`
**Maker Fee**: `ceil(0.0175 × C × P × (1 - P))`

Where C = number of contracts, P = contract price in dollars (e.g., 0.50 for 50¢).

The parabolic P×(1-P) structure means fees are highest at 50¢ and decrease toward extremes.

### Fee Table by Price Level

| Contract Price | Taker Fee/Contract | Maker Fee/Contract | Round-Trip Cost (Maker) |
|---|---|---|---|
| 20¢ | 1.12¢ | 0.28¢ | 0.56¢ |
| 30¢ | 1.47¢ | 0.37¢ | 0.74¢ |
| 40¢ | 1.68¢ | 0.42¢ | 0.84¢ |
| 50¢ | 1.75¢ | 0.44¢ | 0.88¢ |
| 60¢ | 1.68¢ | 0.42¢ | 0.84¢ |
| 70¢ | 1.47¢ | 0.37¢ | 0.74¢ |
| 80¢ | 1.12¢ | 0.28¢ | 0.56¢ |

### Breakeven Edge After Fees

For our scalping strategy (buy and sell, maker both sides):
- At 50¢: Need 0.88¢ edge → **must gain at least 1 cent to profit**
- At 30¢ or 70¢: Need 0.74¢ edge → **1 cent gain nets 0.26¢ profit**
- At 20¢ or 80¢: Need 0.56¢ edge → **1 cent gain nets 0.44¢ profit**

**Critical insight**: At 50¢ (maximum gamma zone), fees eat 88% of a 1-cent gain. Our sweet spot is 25-40¢ or 60-75¢ where fees are lower but gamma is still meaningful.

### Taker vs Maker Fee Impact

If we take liquidity (market orders), the round-trip at 50¢ becomes 3.50¢ — **impossible to profit on 1-3 cent moves**. We MUST be makers.

**Adverse selection risk with limit orders**: Your orders fill disproportionately when informed traders agree prices favor them. In sports markets, this means your buy fills right before the team you bet on gives up a basket.

**Mitigation**: Only post limit orders when our model disagrees with market by 3+ cents. Cancel immediately on scoring events until new fair value is calculated.

## College Basketball Liquidity on Kalshi

### Volume Data (2026)

**NCAA CBB moneylines are Kalshi's single largest category**: 17% of all volume, ~$1.8 billion in a 30-day trailing period.

Per-game volumes:
- **Major conference matchup (e.g., Texas A&M vs Tennessee)**: $7.5 million in contracts
- **Close games**: $8-9M+ per contest
- **Mid-major / non-televised games**: Significantly less (likely $100K-$500K)

### Volume vs Handle

Critical distinction:
- **Volume** counts every matched trade (entry, exit, same-game churn)
- **Handle** = actual customer exposure
- **Basketball games**: 45-55% of volume equals handle
- So a $7.5M volume game = ~$3.4-4.1M in actual customer risk

### Liquidity Implications for Our Strategy

At $7.5M volume per major game with 45-55% handle ratio:
- Actual customer flow: ~$3.5M per game
- If game lasts 120 minutes (including stoppages): ~$29K/minute in flow
- Our 10-20 trades × 10 contracts × ~$0.40 average price = ~$40-80 per game
- **We are a microscopic fraction of volume** — no market impact concern
- But we ARE competing with other algorithmic traders for the same mispricings

### When Liquidity Dries Up

- Non-televised games: Much thinner books, wider spreads
- Blowouts: Volume collapses once outcome becomes certain
- Between halves: Some trading continues but reduced
- **Stick to nationally televised, competitive games**

## API Architecture & Rate Limits

### Protocol Options

| Protocol | Latency | Best For |
|---|---|---|
| REST API | 50-200ms | Order management, account info |
| WebSocket | 10-50ms | Real-time market data, orderbook |
| FIX 4.4 | <10ms | Lowest latency trading (requires TLS/SSL) |

### Rate Limit Tiers

| Tier | Read/sec | Write/sec | How to Get |
|---|---|---|---|
| Basic | 20 | 10 | Signup |
| Advanced | 30 | 30 | Application form |
| Premier | 100 | 100 | 3.75% of monthly exchange volume |
| Prime | 400 | 400 | 7.5% of monthly exchange volume |

Write limits apply to: CreateOrder, CancelOrder, AmendOrder, DecreaseOrder, BatchCreateOrders, BatchCancelOrders.

Batch cancel: each cancel counts as **0.2 transactions** (5x more efficient than individual cancels).

**For our strategy**: Basic tier (10 writes/sec) is sufficient. We're making 10-20 trades per game, not per second. Even with cancels, we'll use <1 write/sec on average.

### WebSocket Channels

**Public (no auth):**
- `ticker` — Price updates
- `trade` — Executed trades
- `market_lifecycle_v2` — Market state changes
- `multivariate` — Multi-market updates

**Private (auth required):**
- `orderbook_delta` — Incremental orderbook changes
- `fill` — Our order fills
- `market_positions` — Position updates
- `order_group_updates` — Order status changes

**Connection**: `wss://api.elections.kalshi.com/trade-api/ws/v2`
**Auth**: RSA-PSS signed headers (KALSHI-ACCESS-KEY, KALSHI-ACCESS-TIMESTAMP, KALSHI-ACCESS-SIGNATURE)

### Subscription Format

```json
{
  "id": 1,
  "cmd": "subscribe",
  "params": {
    "channels": ["ticker", "orderbook_delta"],
    "market_tickers": ["NCAAB-GAME-TICKER"]
  }
}
```

## Latency Chain Analysis

### End-to-End: Live Action → Order Fill

| Component | Latency | Controllable? |
|---|---|---|
| Live event occurs | 0ms | No |
| Score data feed update | 5-30 sec | No (ESPN/SportsDataIO delay) |
| Our API poll interval | 3-5 sec | Yes |
| Strategy computation | 5-50ms | Yes |
| Order transmission (WS) | 10-50ms | Partially |
| Kalshi matching engine | ~1ms | No |
| **Total** | **8-36 seconds** | |

### The Latency Paradox

**We are NOT in a latency race.** Here's why:

1. Our edge comes from **model quality**, not speed. We're betting that a 10-0 run moved the market 8 cents when it should have moved 3 cents. That mispricing persists for minutes, not milliseconds.

2. Data feed delay (5-30 sec) is the dominant bottleneck, and everyone faces it. The question isn't "who sees the score first" but "who has a better model for what it means."

3. Pro market makers on Kalshi likely have Sportradar feeds (15-20 sec) or even courtside scouts (~5 sec). We need to accept this and focus on **post-repricing** opportunities — buying after the initial reaction has happened but before full mean reversion.

4. **Our optimal entry is 30-120 seconds after a scoring event**, when the market has overreacted but the counter-run hasn't started yet. This is a feature, not a bug.

### Infrastructure

- **US East Coast VPS**: ~$20-50/month, ~1ms to Kalshi infrastructure
- **Python asyncio**: Sufficient for our event-driven strategy
- **WebSocket for data, REST for orders**: Best balance of latency and reliability

## Order Management Strategy

### Order Types

- **Limit orders**: Specify exact price, wait for fill (maker fees)
- **Market orders**: Immediate execution at best available price (taker fees)

For our strategy: **Always limit orders.** The 4x fee difference (1.75¢ taker vs 0.44¢ maker at 50¢) makes market orders unviable for small-edge scalping.

### Execution Flow

1. **Pre-game**: Set up WebSocket subscriptions, pull current orderbook
2. **Game start**: Monitor ticker channel for price updates
3. **Scoring event detected**:
   - Cancel all existing open orders immediately
   - Recalculate fair value with updated score/time
   - Wait 15-30 seconds for initial market reaction
   - If market price diverges from model by 3+ cents: place limit buy
4. **Position open**: Monitor for target (1-3 cent gain) or stop loss (3 cent loss)
5. **Exit**: Place limit sell at target price, cancel if stop triggered

### Handling Fast Markets

During scoring runs:
- **Auto-cancel threshold**: If market moves 2+ cents against our open order within 5 seconds, cancel immediately
- **Scoring event pause**: Pause all new orders for 10-15 seconds after each basket to let the book settle
- **Double-check**: Before placing any order, verify current best bid/ask from orderbook delta channel

## Competition on Kalshi

### Who Are We Competing Against?

1. **Retail bettors** (majority): Humans using the app, reacting emotionally to scoring runs. **These are our counterparties.**
2. **Semi-automated traders**: People with models but manual execution. Faster than retail, slower than us.
3. **Professional market makers**: Firms with Kalshi market maker program access, reduced fees, and sophisticated infrastructure. **These are our competition.**
4. **Prop trading firms**: Professional operations with advanced data feeds, multiple-screen setups, and deep pockets.

### Our Advantage Over Retail
- We don't panic during scoring runs
- We have a mathematical model, not "gut feel"
- We can monitor multiple games simultaneously
- We execute faster than a human checking their phone

### Our Disadvantage vs Pros
- They have faster data (Sportradar, courtside scouts)
- They have more capital (can post deeper limit orders)
- They have lower fees (market maker program)
- They have better models (proprietary research teams)

**Net assessment**: Our edge is over retail. We are picking up crumbs the pros leave behind because their minimum trade size is too large for 1-3 cent moves on small contract counts.

## Regulatory & Compliance

- Kalshi is CFTC-regulated (Designated Contract Market)
- Algorithmic trading is **explicitly allowed** under the API Developer Agreement
- Prohibited: insider trading, wash trading, front-running, market manipulation
- No explicit position limits published for standard accounts
- KYC/AML mandatory; all trades reported to CFTC daily
- 200+ insider trading investigations in 2025 (they're watching)

## Platform Interest

Kalshi pays **4% interest on account balances** and on positions, improving effective returns on capital sitting idle between trades.
