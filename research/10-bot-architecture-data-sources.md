# Kalshi Live College Basketball Trading Engine: Comprehensive Research Report

**Date:** February 27, 2026
**Purpose:** Architecture and implementation guide for a production live trading system targeting college basketball moneyline contracts on Kalshi.

---

## 1. Real-Time College Basketball Data Sources

### Tier 1: Official / Enterprise-Grade

**Genius Sports / NCAA LiveStats**
- The NCAA's exclusive official data partner through 2032
- Powers 70,000+ games annually across all three NCAA divisions
- Used by CBS, ESPN, Big Ten Network, NBA teams
- In-stadium data capture by trained operators at courtside
- Latency: Fastest available (seconds behind live action)
- Access: Enterprise licensing only; contact Genius Sports sales directly
- URL: https://geniussports.com/sportstech/genius-for-college-sports/

**Sportradar NCAAMB API (v8)**
- Official B2B data provider with iScout in-stadium technology
- RESTful API returning JSON or XML
- Latency: 15-20 seconds behind TV broadcast for live stats; game state ~30-60 seconds behind broadcast
- API TTL refreshes every 2 seconds during live games
- Push feed available (webhook-based) for some products
- Historical data back to 2013 season
- Pricing: Custom; contact sales. Expect $500-$5,000+/month depending on usage
- URL: https://developer.sportradar.com/basketball/reference/ncaamb-overview

**SportsDataIO**
- Scores updated within 20-30 seconds of cable broadcast (and 20-30 seconds AHEAD of streaming broadcasts)
- Play-by-play in real-time with same latency profile
- API cache minimum 3 seconds; poll every 3-5 seconds for live games
- Free trial (never expires) with access to all endpoints
- Paid plans based on monthly request volume
- Live odds data pulled from sportsbooks with 5-second to 5-minute latency
- URL: https://sportsdata.io/ncaa-college-basketball-api

### Tier 2: Free / Unofficial

**ESPN Hidden API**
- Free, no authentication required
- Scoreboard endpoint: `site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard`
- Play-by-play: `site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/summary?event={gameId}`
- Add `groups=50&limit=365` to get all D1 games
- Latency: Estimated 15-45 seconds behind live action (community reports vary)
- Risk: Unofficial endpoints; can break without warning. No SLA or support
- URL: https://gist.github.com/akeaswaran/b48b02f1c94f873c6655e7129910fc3b

**NCAA API (henrygd/ncaa-api)**
- Free open-source API scraping ncaa.com for live scores, stats, standings
- URL: https://github.com/henrygd/ncaa-api

**The Odds API**
- Returns live and upcoming NCAA basketball odds from multiple bookmakers
- Free tier available with current odds data
- Useful for cross-referencing Kalshi prices against sportsbook lines
- URL: https://the-odds-api.com/sports-odds-data/ncaa-basketball-odds.html

### Recommendation for Our System

**Primary data feed:** SportsDataIO (reliable, documented, 20-30s latency, affordable)
**Backup / cross-validation:** ESPN Hidden API (free, decent latency)
**Odds reference:** The Odds API (free tier, multi-bookmaker consensus lines)
**Stretch goal:** Sportradar if volume justifies cost

---

## 2. KenPom and Advanced Analytics Integration

### KenPom Core Metrics

- **AdjO** (Adjusted Offensive Efficiency): Points scored per 100 possessions vs. average D1 defense
- **AdjD** (Adjusted Defensive Efficiency): Points allowed per 100 possessions vs. average D1 offense
- **AdjEM** (Adjusted Efficiency Margin): AdjO - AdjD; expected point differential per 100 possessions vs. average team
- **AdjT** (Adjusted Tempo): Expected possessions per 40 minutes
- **Luck**: Deviation between actual and expected winning percentage based on game scores

### Predicting Score Differential

The KenPom formula for predicting a specific game:

```
1. Estimate game tempo:
   predicted_possessions = (TeamA_AdjT * TeamB_AdjT) / League_Avg_AdjT

2. Estimate points per possession for each team:
   TeamA_PPP = (TeamA_AdjO * TeamB_AdjD) / League_Avg_Efficiency
   TeamB_PPP = (TeamB_AdjO * TeamA_AdjD) / League_Avg_Efficiency

3. Apply home court adjustment (+1.4% offense, -1.4% defense for home team; reverse for away)

4. Predicted score:
   TeamA_Score = TeamA_PPP * predicted_possessions / 100
   TeamB_Score = TeamB_PPP * predicted_possessions / 100

5. Predicted margin = TeamA_Score - TeamB_Score
```

### BartTorvik / T-Rank

- Similar methodology to KenPom with proprietary adjustments
- Data available via CSV/JSON exports updated constantly during season
- Game prediction endpoint available through cbbdata API
- URL: https://barttorvik.com

### Data Access Methods

**CBBData API** (Recommended):
- Flask/Python backend, updated every 15 minutes during season
- 26+ endpoints covering player stats, team analytics, game results, advanced metrics
- KenPom data accessible with matching subscription email
- BartTorvik data integrated natively
- Game predictions powered by BartTorvik models
- Free API key signup: https://cbbdata.aweatherman.com/

**KenPom Direct:**
- Subscription required ($19.99/year)
- No official API; data accessed through CBBData's authorized integration
- Kaggle has historical KenPom datasets: https://www.kaggle.com/datasets/aadhafun/kenpom-ratings-2025

**Python Tools:**
- `CBBpy` (PyPI): Scrapes play-by-play, boxscores from ESPN
- `cbbd` (PyPI): College basketball data from CollegeBasketballData.com
- `sportsdataverse-py`: ESPN API wrapper for play-by-play

### Usage for Pre-Game Priors

KenPom/BartTorvik efficiency ratings translate directly into pre-game win probabilities:
1. Calculate expected margin from efficiency ratings
2. Convert margin to win probability using a logistic function (standard deviation ~11 points for college basketball)
3. This becomes the prior probability that initializes our live model
4. Compare against Kalshi market price to identify pre-game edge

---

## 3. System Architecture

### High-Level Architecture (Text Diagram)

```
┌─────────────────────────────────────────────────────────────────┐
│                     MONITORING LAYER                             │
│  Grafana Dashboards | Prometheus Metrics | Alert Manager         │
└─────────────┬───────────────────────────────────┬───────────────┘
              │                                   │
┌─────────────▼───────────────────────────────────▼───────────────┐
│                     APPLICATION LAYER                            │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐     │
│  │ Data Ingestion│  │   Strategy   │  │  Order Management  │     │
│  │   Service     │  │    Engine    │  │      System        │     │
│  │              │  │              │  │                    │     │
│  │ - ESPN Poller │  │ - Win Prob   │  │ - Order Queue      │     │
│  │ - SportsData  │  │   Model      │  │ - Position Tracker │     │
│  │   Poller      │  │ - Edge Calc  │  │ - Fill Handler     │     │
│  │ - Odds API    │  │ - Kelly Size │  │ - Cancel Logic     │     │
│  │   Poller      │  │ - Signal Gen │  │ - Retry Logic      │     │
│  └──────┬───────┘  └──────┬───────┘  └────────┬───────────┘     │
│         │                 │                    │                  │
│  ┌──────▼─────────────────▼────────────────────▼───────────────┐ │
│  │                  EVENT BUS (asyncio)                         │ │
│  │  game_update | score_change | signal | order_fill | error   │ │
│  └──────┬─────────────────┬────────────────────┬───────────────┘ │
│         │                 │                    │                  │
│  ┌──────▼───────┐  ┌─────▼──────┐  ┌─────────▼──────────┐      │
│  │  Game State  │  │    Risk    │  │   Kalshi Gateway   │      │
│  │   Manager    │  │   Manager  │  │                    │      │
│  │              │  │            │  │ - REST Client      │      │
│  │ - Score      │  │ - Max Loss │  │ - WebSocket Client │      │
│  │ - Clock      │  │ - Position │  │ - Auth Handler     │      │
│  │ - Possession │  │   Limits   │  │ - Rate Limiter     │      │
│  │ - Fouls      │  │ - Circuit  │  │ - Reconnect Logic  │      │
│  │ - Runs       │  │   Breakers │  │                    │      │
│  └──────────────┘  └────────────┘  └────────────────────┘      │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
              │                                   │
┌─────────────▼───────────────────────────────────▼───────────────┐
│                      DATA LAYER                                  │
│  SQLite/Postgres | Redis (state cache) | Log Files               │
└─────────────────────────────────────────────────────────────────┘
```

### Recommended Tech Stack

**Primary: Python 3.11+ with asyncio**
- Most Kalshi bot examples use Python
- Rich ecosystem: `kalshi-python`, `websockets`, `aiohttp`, `numpy`, `pandas`
- `asyncio` handles concurrent WebSocket connections and polling loops naturally
- Adequate performance for our latency requirements (we are not HFT)

**Key Libraries:**
```
kalshi-python          # Official Kalshi Python client
websockets             # WebSocket connections
aiohttp                # Async HTTP for polling data feeds
numpy / scipy          # Win probability calculations
pandas                 # Data manipulation
redis                  # Fast state cache (game state, positions)
prometheus-client      # Metrics export
structlog              # Structured logging
pydantic               # Data validation for API responses
```

### Event-Driven vs. Polling

For our use case, **hybrid polling + event-driven** is optimal:

- **Poll** sports data APIs every 3-5 seconds (they don't offer WebSockets)
- **Subscribe** to Kalshi WebSocket channels for real-time orderbook and fill updates
- **Event bus** connects components: when a score change is detected by the poller, it emits a `score_change` event that triggers the strategy engine, which emits a `signal` event consumed by the order management system

### Disconnection and Recovery

```
Kalshi WebSocket disconnect:
  1. Cancel all open orders immediately (via REST fallback)
  2. Log disconnection with timestamp
  3. Reconnect with exponential backoff (1s, 2s, 4s, 8s, max 30s)
  4. Re-subscribe to all channels
  5. Reconcile state: fetch current positions/orders via REST
  6. Resume trading only after full state reconciliation

Data feed failure:
  1. Switch to backup data source (ESPN -> SportsDataIO or vice versa)
  2. If all feeds fail, enter "read-only" mode (no new orders)
  3. Alert immediately via Telegram/SMS
  4. Keep existing positions (do NOT panic-close on data outage)
```

---

## 4. Latency Analysis

### End-to-End Latency Chain

```
Live action on court
        │
        ▼ ~5-15 seconds (data operator / iScout capture)
Score appears in data API
        │
        ▼ ~3-5 seconds (our polling interval)
Our system detects score change
        │
        ▼ ~5-50 milliseconds (strategy calculation)
Trading signal generated
        │
        ▼ ~50-200 milliseconds (Kalshi REST order or WebSocket)
Order placed on Kalshi exchange
        │
        ▼ ~10-50 milliseconds (exchange matching)
Order filled (or resting in book)

TOTAL: ~8-21 seconds from live action to order placement
```

### Latency Budget Breakdown

| Component                    | Latency        | Controllable? |
|------------------------------|----------------|---------------|
| Live action to API update    | 5-30 seconds   | No            |
| API polling interval         | 3-5 seconds    | Yes           |
| Strategy computation         | 5-50 ms        | Yes           |
| Network to Kalshi            | 10-100 ms      | Partially     |
| Kalshi order processing      | 10-50 ms       | No            |
| **Total end-to-end**         | **~8-36 sec**  |               |

### Is This Acceptable for a 1-3 Cent Edge Strategy?

**Yes, but with caveats.** Our edge comes from having a better model of true win probability, not from being faster than everyone. The key insight:

1. Kalshi CBB markets have $8-9M+ volume per game in close contests
2. Market prices update based on participants trading manually AND algorithmically
3. After a scoring event, it takes the broader market 15-60 seconds to fully re-price
4. With a 20-30 second data delay and 5 second polling, we're competitive with most participants
5. We lose to: (a) people watching live TV and trading manually (<10s reaction), (b) institutional market makers with Genius Sports feeds (<5s reaction)

**The real edge is model quality, not speed.** If our win probability model is more accurate than what the market is pricing, we can place orders at prices that represent value even after the market partially adjusts. A 1-3 cent edge on a binary contract means our model disagrees with the market by 1-3 percentage points -- this is about calibration, not latency.

### Infrastructure Recommendation

- VPS on US East Coast (New York area) for minimum latency to Kalshi
- Dedicated Kalshi VPS providers offer ~1ms latency to exchange (e.g., newyorkcityservers.com)
- Cost: ~$20-50/month for adequate VPS

---

## 5. Position and Risk Management

### Real-Time P&L Tracking

```python
class PositionTracker:
    """Track per-game and portfolio-level positions."""

    def update_on_fill(self, fill_event):
        # Update position size, average entry price, realized P&L
        # Update unrealized P&L using current market mid-price
        # Emit metrics to Prometheus

    def mark_to_market(self, current_price):
        # unrealized_pnl = position_size * (current_price - avg_entry)
        # total_pnl = realized_pnl + unrealized_pnl

    def on_settlement(self, outcome):
        # Contract resolves to $1.00 or $0.00
        # Final P&L = position_size * (settlement - avg_entry)
```

### Risk Limits (Configurable Parameters)

```yaml
risk_limits:
  max_loss_per_game: 50.00          # Stop trading this game if down $50
  max_loss_per_day: 200.00          # Kill switch for the entire day
  max_position_per_game: 200        # Max 200 contracts per game
  max_concurrent_games: 5           # Trade at most 5 games simultaneously
  max_portfolio_exposure: 1000.00   # Total capital at risk across all games
  min_edge_threshold: 0.02          # Only trade if edge >= 2 cents
  max_edge_threshold: 0.15          # Suspicious if edge > 15 cents (likely bad data)
  kelly_fraction: 0.25              # Quarter-Kelly for position sizing
```

### Circuit Breakers

```
Level 1 - Game Circuit Breaker:
  Trigger: Loss > max_loss_per_game on any single game
  Action: Cancel all orders for that game, close position at market, blacklist game

Level 2 - Session Circuit Breaker:
  Trigger: Total day P&L < -max_loss_per_day
  Action: Cancel ALL orders, flatten all positions, halt trading for remainder of day

Level 3 - System Circuit Breaker:
  Trigger: Data feed failure, Kalshi API errors, latency spike > 10s
  Action: Cancel all orders, enter read-only mode, alert operator

Level 4 - Emergency Kill Switch:
  Trigger: Manual operator command (e.g., Telegram /kill command)
  Action: Immediately cancel all orders and flatten all positions
```

### Kelly Criterion Position Sizing

```
For a binary Kalshi contract:
  p = our estimated probability of YES
  q = 1 - p
  b = (payout / cost) - 1 = (1.00 / market_price) - 1

  Full Kelly: f* = (p * b - q) / b
  Quarter Kelly: f = f* / 4

  Position size (contracts) = f * bankroll / market_price

Example:
  Our model says p = 0.60, market price = 0.56 (4 cent edge)
  b = (1.00 / 0.56) - 1 = 0.786
  Full Kelly: f* = (0.60 * 0.786 - 0.40) / 0.786 = 0.092 (9.2% of bankroll)
  Quarter Kelly: f = 0.023 (2.3% of bankroll)
  With $5,000 bankroll: $115 risk -> ~205 contracts at 56 cents
```

### Handling System Failures Mid-Game

```
Scenario: Bot crashes during a live game with open positions

Recovery protocol:
  1. On restart, immediately query Kalshi REST API for:
     - Current positions (GET /portfolio/positions)
     - Open orders (GET /portfolio/orders)
     - Recent fills (GET /portfolio/fills)
  2. Reconstruct game state from data feed
  3. Recalculate current win probability
  4. If position is within risk limits, resume normal operation
  5. If position exceeds risk limits (due to price movement during downtime),
     begin orderly unwind
  6. Log gap period for post-mortem analysis
```

---

## 6. Live Game State Modeling

### Game State Object

```python
@dataclass
class GameState:
    game_id: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    period: int              # 1 = first half, 2 = second half, 3+ = OT
    clock_seconds: float     # Seconds remaining in current period
    total_seconds_remaining: float  # Computed total time left
    possession: str          # "home" or "away" or "unknown"
    home_fouls: int
    away_fouls: int
    home_timeouts: int
    away_timeouts: int
    is_timeout: bool
    is_halftime: bool
    last_score_time: float   # Timestamp of last scoring event
    scoring_run: int         # Current unanswered scoring run
    run_team: str            # Which team is on the run

    # Pre-game priors
    pre_game_spread: float
    home_kenpom_adjo: float
    home_kenpom_adjd: float
    away_kenpom_adjo: float
    away_kenpom_adjd: float
```

### Win Probability Model

Based on the Luke Benz ncaahoopR approach, adapted for our use case:

```
Model: Logistic regression with time-varying coefficients

Inputs:
  - score_differential (home - away)
  - pre_game_spread (from KenPom/BartTorvik or betting line)
  - seconds_remaining

Structure:
  - Separate logistic regression for each time interval
  - Wider intervals early game (100s), narrowing late (1-2s near end)
  - LOESS smoothing across time intervals for smooth coefficient functions

Key insight from research:
  "As the game progresses, the pregame line becomes less important in
   predicting win probability and the current score differential becomes
   increasingly more important."

Output: P(home_wins | score_diff, spread, time_remaining) in [0, 1]
```

### Scoring Run Detection

```python
def detect_scoring_run(game_state: GameState, events: List[ScoreEvent]):
    """Detect if a team is on a significant scoring run."""
    # Look at last N scoring events
    # A "run" = consecutive points by one team without opponent scoring
    # Significant thresholds: 7-0 run, 10-0 run, etc.

    # Why this matters for trading:
    # During a scoring run, the team on the run's win probability increases
    # faster than the market typically adjusts, creating momentary edge.
    # Conversely, after a long run, regression to the mean is likely,
    # creating a contrarian opportunity.
```

### Model Training Data

Train on historical play-by-play data with known outcomes:
1. For each game, at each time point, record (score_diff, spread, time_remaining, outcome)
2. Fit time-varying logistic regression
3. Calibrate: bin predictions into buckets, verify predicted probability matches observed win rate
4. Expected calibration error should be < 2% for a good model

---

## 7. Historical Data for Backtesting

### Data Sources

**BigDataBall** ($30-50 per dataset)
- Historical NCAA CBB game-by-game stats with betting odds
- Clean Excel/CSV format
- URL: https://www.bigdataball.com/datasets/ncaa/cbb-data/

**Sports Reference / College Basketball Reference**
- Free, comprehensive historical stats
- Box scores, play-by-play, game logs going back decades
- URL: https://www.sports-reference.com/cbb/

**hoopR Package (R) / sportsdataverse-py (Python)**
- ESPN-sourced play-by-play data
- Historical game data with shot-by-shot detail
- Free and open-source
- URL: https://hoopr.sportsdataverse.org/

**Sportradar Historical**
- Available back to 2013 season via API
- Same format as live feeds (good for simulation fidelity)

**KenPom Historical (via Kaggle)**
- Historical team ratings datasets
- URL: https://www.kaggle.com/datasets/aadhafun/kenpom-ratings-2025

**CBBData API**
- Game-by-game logs with advanced metrics dating back to 2008
- BartTorvik predictions included

### Simulating Kalshi Prices for Backtesting

Since historical Kalshi price data for CBB may not be available:

```
Approach 1: Synthetic Kalshi prices from sportsbook lines
  - Use historical sportsbook moneylines (from BigDataBall odds data)
  - Convert moneyline to implied probability (this approximates Kalshi price)
  - Add noise/spread to simulate bid-ask
  - Simulate price movement during game using win probability model

Approach 2: Win-probability-based price simulation
  - For each historical game's play-by-play:
    1. At each time point, calculate true win probability from our model
    2. Add market noise (mean 0, std ~2-3 cents) to create simulated market price
    3. Add latency delay (shift our model's updates forward by 20-30 seconds)
    4. Simulate order fills against this synthetic orderbook

Approach 3: Forward-looking paper trading
  - Run the bot in paper-trading mode against live Kalshi markets
  - Record every signal, simulated order, and what would have filled
  - Build a database of actual Kalshi price behavior over 2-4 weeks
  - Use this data for calibrated backtesting
```

**Recommendation:** Start with Approach 3 (paper trading) while building the historical simulation with Approach 1. Paper trading provides the most realistic test.

---

## 8. Open-Source Tools and Reference Implementations

### Kalshi-Specific Bots

| Project | URL | Relevance |
|---------|-----|-----------|
| Kalshi Quant TeleBot | https://github.com/yllvar/Kalshi-Quant-TeleBot | Enterprise-grade architecture, risk management, Telegram integration |
| Kalshi Deep Trading Bot | https://github.com/OctagonAI/kalshi-deep-trading-bot | Clean Kalshi API integration pattern |
| Kalshi AI Trading Bot | https://github.com/ryanfrigo/kalshi-ai-trading-bot | Multi-agent architecture, portfolio optimization |
| Kalshi-Poly Arbitrage | https://github.com/ImMike/polymarket-arbitrage | Cross-platform market monitoring for 10,000+ markets |
| Kalshi Interface | https://github.com/sswadkar/kalshi-interface | FastAPI dashboard, automated polling, RSA-PSS auth |

### College Basketball Analytics

| Project | URL | Relevance |
|---------|-----|-----------|
| ncaahoopR Win Probability | https://github.com/lbenz730/NCAA_Hoops_Play_By_Play | Gold standard CBB win probability model (R) |
| CBBpy | https://github.com/dcstats/CBBpy | Python scraper for NCAA basketball play-by-play |
| cbb_machine_learning | https://github.com/bszek213/cbb_machine_learning | ML predictions for D1 games (2010-2024) |
| cbbdata | https://github.com/andreweatherman/cbbdata | R package with 26+ endpoints for CBB data |
| cbbscraper | https://github.com/fattmarley/cbbscraper | Scrapes KenPom, BartTorvik, and FanDuel |

### Trading Infrastructure

| Project | URL | Relevance |
|---------|-----|-----------|
| AAT (Async Algo Trading) | https://github.com/AsyncAlgoTrading/aat | Event-driven asyncio trading framework (Python/C++) |
| Alpaca Scalping Example | https://github.com/alpacahq/example-scalping | Concurrent asyncio trading with WebSocket feeds |
| Freqtrade Dashboard | https://github.com/thraizz/freqtrade-dashboard | Grafana + Prometheus monitoring for trading bots |

### Academic Papers

- "A Logistic Regression/Markov Chain Model for NCAA Basketball" (Georgia Tech): https://www2.isye.gatech.edu/~jsokol/ncaa.pdf
- "Optimal Sports Betting Strategies in Practice": https://arxiv.org/pdf/2107.08827
- Yale NCAA Basketball Win Probability Model: https://sports.sites.yale.edu/ncaa-basketball-win-probability-model
- "Modified Kelly Criteria" (SFU): https://www.sfu.ca/~tswartz/papers/kelly.pdf

---

## 9. Monitoring and Observability

### Metrics to Track (Prometheus)

```python
# Trading Performance
trades_total = Counter('trades_total', 'Total trades', ['game', 'side', 'action'])
trade_pnl = Histogram('trade_pnl_cents', 'P&L per trade in cents')
position_size = Gauge('position_size', 'Current position', ['game', 'side'])
portfolio_pnl = Gauge('portfolio_pnl_dollars', 'Total portfolio P&L')
edge_at_entry = Histogram('edge_at_entry_cents', 'Edge when trade was placed')

# Model Performance
model_win_prob = Gauge('model_win_prob', 'Current model win probability', ['game'])
kalshi_market_price = Gauge('kalshi_price', 'Current Kalshi market price', ['game', 'side'])
model_vs_market_diff = Gauge('model_market_diff', 'Model - Market price', ['game'])

# System Health
data_feed_latency = Histogram('data_feed_latency_seconds', 'Time to receive data update')
kalshi_api_latency = Histogram('kalshi_api_latency_ms', 'Kalshi API response time')
websocket_disconnects = Counter('ws_disconnects_total', 'WebSocket disconnection count')
order_rejections = Counter('order_rejections_total', 'Order rejections', ['reason'])
polling_errors = Counter('polling_errors_total', 'Data feed polling errors', ['source'])
```

### Grafana Dashboard Panels

```
Row 1: Portfolio Overview
  - Total P&L (today, week, all-time) -- stat panels
  - P&L chart over time -- time series
  - Win rate percentage -- gauge

Row 2: Live Games
  - Active games with current positions -- table
  - Model probability vs. market price for each game -- time series overlay
  - Current edge by game -- bar chart

Row 3: Risk
  - Distance to circuit breaker thresholds -- gauge panels
  - Position size vs. limits -- bar chart
  - Max drawdown -- stat panel

Row 4: System Health
  - Data feed latency -- time series
  - Kalshi API response times -- histogram
  - WebSocket connection status -- state timeline
  - Error rate -- time series
```

### Alerting Rules

```yaml
alerts:
  - name: CircuitBreakerWarning
    condition: portfolio_pnl_dollars < -150  # 75% of daily limit
    severity: warning
    channel: telegram

  - name: CircuitBreakerTriggered
    condition: portfolio_pnl_dollars < -200
    severity: critical
    channel: [telegram, sms]

  - name: DataFeedDown
    condition: time_since_last_update > 30s
    severity: critical
    channel: telegram

  - name: KalshiWebSocketDown
    condition: ws_disconnects_total increase > 3 in 5m
    severity: critical
    channel: telegram

  - name: HighLatency
    condition: kalshi_api_latency_ms > 2000
    severity: warning
    channel: telegram

  - name: SuspiciousEdge
    condition: abs(model_market_diff) > 0.15
    severity: warning
    message: "Model disagrees with market by >15 cents -- possible bad data"
    channel: telegram

  - name: LowWinRate
    condition: win_rate_last_20_trades < 0.35
    severity: warning
    message: "Win rate has dropped below 35% over last 20 trades"
    channel: telegram
```

### Structured Logging Strategy

```python
import structlog

logger = structlog.get_logger()

# Every trading decision logged with full context
logger.info("signal_generated",
    game_id="DUKE-UNC-20260227",
    model_prob=0.62,
    market_price=0.57,
    edge=0.05,
    signal="BUY_YES",
    kelly_size=12,
    reason="post_scoring_run_adjustment"
)

logger.info("order_placed",
    game_id="DUKE-UNC-20260227",
    order_id="abc123",
    side="yes",
    action="buy",
    price=0.57,
    quantity=12,
    latency_ms=45
)

logger.info("order_filled",
    game_id="DUKE-UNC-20260227",
    order_id="abc123",
    fill_price=0.57,
    fill_quantity=12,
    position_after=12,
    unrealized_pnl=0.00
)
```

### Detecting Bad Trades in Real-Time

```
1. Track "edge decay" -- after placing a trade, monitor how the market moves:
   - If market moves toward our price: we were right (edge was real)
   - If market moves away: edge was illusory or we were adversely selected
   - Compute: avg_edge_decay_5min across last 10 trades
   - Alert if consistently negative (we are getting picked off)

2. Track "model calibration drift":
   - Bin recent model predictions into buckets (0.5-0.6, 0.6-0.7, etc.)
   - Compare predicted win rates to actual outcomes
   - Alert if calibration error exceeds 5% in any bucket

3. Track "fill quality":
   - Compare fill price to fair value 30 seconds after fill
   - If we're consistently paying too much (buying above fair value),
     our model or execution is too slow

4. Dead man's switch:
   - If no heartbeat received from bot process for 60 seconds,
     cancel all orders via separate watchdog process
```

---

## 10. Kalshi-Specific Implementation Details

### Kalshi API Summary

**REST API Base:** `https://api.elections.kalshi.com/trade-api/v2`
**WebSocket:** `wss://api.elections.kalshi.com/trade-api/ws/v2`
**Demo/Sandbox:** `https://demo-api.kalshi.co/trade-api/v2`
**Authentication:** RSA-PSS signed requests
**Documentation:** https://docs.kalshi.com

### Rate Limits

| Tier     | Read/sec | Write/sec | Qualification                        |
|----------|----------|-----------|--------------------------------------|
| Basic    | 20       | 10        | Automatic on signup                  |
| Advanced | 30       | 30        | Application form                     |
| Premier  | 100      | 100       | 3.75% of monthly exchange volume     |
| Prime    | 400      | 400       | 7.5% of monthly exchange volume      |

Batch cancellations count as 0.2 transactions each.
FIX 4.4 protocol available for lowest latency at highest tiers.

### WebSocket Channels

**Public (no auth):** ticker, trade, market_lifecycle_v2, multivariate
**Private (auth required):** orderbook_delta, fill, market_positions, communications, order_group_updates

### College Basketball Market Structure

- NCAA CBB moneylines are 17% of all Kalshi volume (~$1.8B trailing 30 days)
- Single-game markets with YES/NO contracts for each team
- Contracts trade between $0.01 and $0.99, settle at $1.00 or $0.00
- Active live trading during games drives majority of volume
- Close games generate $8-9M+ per contest
- Market maker liquidity incentives: ~$35,000/day platform-wide

### Order Types

- **Limit orders:** Specify exact price; rest in book until filled or canceled
- **Market orders:** Execute immediately at best available price

---

## 11. Implementation Roadmap

### Phase 1: Data Foundation (Week 1-2)
- Set up VPS on US East Coast
- Implement ESPN API poller with 5-second intervals
- Implement SportsDataIO poller as backup
- Build GameState data model
- Set up Redis for state caching
- Set up structured logging with structlog
- Build Kalshi API client with auth and rate limiting

### Phase 2: Model Development (Week 2-4)
- Collect historical play-by-play data via CBBpy / hoopR
- Pull KenPom/BartTorvik ratings via cbbdata API
- Train time-varying logistic regression win probability model
- Calibrate against historical outcomes
- Implement pre-game prior calculation from efficiency ratings
- Implement live win probability updates on score changes

### Phase 3: Strategy Engine (Week 3-5)
- Implement edge calculation (model_prob - market_price)
- Implement quarter-Kelly position sizing
- Build signal generation logic with configurable thresholds
- Implement scoring run detection
- Build order management system with cancel/replace logic

### Phase 4: Risk and Execution (Week 4-6)
- Implement all circuit breakers
- Implement position tracking and P&L calculation
- Build Kalshi WebSocket integration for fills and orderbook
- Implement reconnection and state reconciliation logic
- Build the watchdog / dead man's switch process

### Phase 5: Monitoring and Paper Trading (Week 5-7)
- Deploy Prometheus + Grafana stack
- Build monitoring dashboards
- Set up Telegram alerting
- Run in paper-trading mode for minimum 2 weeks
- Analyze paper trading results, calibrate model

### Phase 6: Live Trading (Week 7+)
- Start with minimal capital ($500)
- Trade 1-2 games per night
- Conservative risk limits
- Daily review of all trades
- Gradually increase capital and game count based on results

---

## 12. Key Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| ESPN API breaks/changes | Medium | High | Dual data feed (SportsDataIO backup) |
| Model miscalibration | Medium | High | Continuous calibration monitoring; paper trade first |
| Kalshi API downtime | Low | High | Cancel all orders on disconnect; position limits |
| Adverse selection by faster traders | High | Medium | Focus on model quality, not speed; trade smaller sizes |
| Scoring data delay > 60 seconds | Low | Medium | Anomaly detection on data freshness; pause trading |
| Regulatory changes to Kalshi sports markets | Low | High | Cannot mitigate; stay informed on CFTC actions |
| Overfit model on historical data | Medium | High | Cross-validation; out-of-sample testing; paper trading |
| Black swan game events (injury, technical foul, etc.) | Medium | Medium | Position limits; circuit breakers; quarter-Kelly sizing |

---

## Sources

- [ESPN Hidden API Documentation](https://gist.github.com/akeaswaran/b48b02f1c94f873c6655e7129910fc3b)
- [Sportradar NCAAMB API Basics](https://developer.sportradar.com/basketball/docs/ncaamb-ig-api-basics)
- [SportsDataIO NCAA Basketball API](https://sportsdata.io/ncaa-college-basketball-api)
- [SportsDataIO Refresh Rates and Timing](https://sportsdata.io/help/refresh-rates-feeds-and-timing)
- [The Odds API - NCAA Basketball](https://the-odds-api.com/sports-odds-data/ncaa-basketball-odds.html)
- [Genius Sports NCAA LiveStats](https://www.geniussports.com/customer-stories/ncaa-transforms-data-ecosystem-with-livestats/)
- [KenPom Ratings Explanation](https://kenpom.com/blog/ratings-explanation/)
- [KenPom Ratings Glossary](https://kenpom.com/blog/ratings-glossary/)
- [CBBData API](https://cbbdata.aweatherman.com/articles/release.html)
- [BartTorvik / toRvik](https://github.com/andreweatherman/toRvik)
- [ncaahoopR Win Probability Model](https://lukebenz.com/post/ncaahoopr_win_prob/)
- [Yale NCAA Basketball Win Probability Model](https://sports.sites.yale.edu/ncaa-basketball-win-probability-model)
- [Kalshi API Documentation](https://docs.kalshi.com/welcome)
- [Kalshi WebSocket Documentation](https://docs.kalshi.com/getting_started/quick_start_websockets)
- [Kalshi Rate Limits and Tiers](https://docs.kalshi.com/getting_started/rate_limits)
- [Kalshi Python Client](https://pypi.org/project/kalshi-python/)
- [College Basketball Biggest Sport at Kalshi](https://nexteventhorizon.substack.com/p/college-basketball-betting-is-biggest-sport-at-kalshi-before-march-madness)
- [Market Making on Prediction Markets Guide](https://newyorkcityservers.com/blog/prediction-market-making-guide)
- [Kalshi VPS - Low Latency](https://newyorkcityservers.com/kalshi-vps)
- [BigDataBall NCAA Data](https://www.bigdataball.com/datasets/ncaa/cbb-data/)
- [Sports Reference College Basketball](https://www.sports-reference.com/cbb/)
- [hoopR Package](https://hoopr.sportsdataverse.org/)
- [CBBpy PyPI](https://pypi.org/project/CBBpy/)
- [Kalshi Quant TeleBot](https://github.com/yllvar/Kalshi-Quant-TeleBot)
- [AAT - Async Algo Trading](https://github.com/AsyncAlgoTrading/aat)
- [NCAA Basketball Logistic Regression Model (Georgia Tech)](https://www2.isye.gatech.edu/~jsokol/ncaa.pdf)
- [Optimal Sports Betting Strategies](https://arxiv.org/pdf/2107.08827)
- [Kelly Criterion (Wikipedia)](https://en.wikipedia.org/wiki/Kelly_criterion)
- [Freqtrade Grafana Dashboard](https://github.com/thraizz/freqtrade-dashboard)
- [ESPN API Guide (sportsapis.dev)](https://sportsapis.dev/espn-api)
- [Kalshi API Complete Guide (Zuplo)](https://zuplo.com/learning-center/kalshi-api)
