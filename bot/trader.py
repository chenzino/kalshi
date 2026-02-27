"""Live trading engine for Kalshi college basketball markets."""
import time
import json
import os
import re
import traceback
from datetime import datetime
from dotenv import load_dotenv

from bot.kalshi_client import KalshiClient
from bot.espn_feed import get_live_games, get_todays_schedule
from bot.model import win_probability, fair_value_cents, mean_reversion_estimate, delta_per_point
from bot.data_logger import log_market_snapshot, log_trade, log_game_state, get_session_stats

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

# Config
MAX_CONTRACTS = int(os.getenv("MAX_CONTRACTS_PER_TRADE", "1"))
MAX_COST_CENTS = int(os.getenv("MAX_COST_PER_TRADE", "100"))  # $1 = 100 cents
EDGE_THRESHOLD = 3  # Minimum cents of edge to trade
STOP_LOSS_CENTS = 5  # Max loss per position
MAX_POSITIONS = 3  # Max simultaneous positions
POLL_INTERVAL = 15  # Seconds between polls
MIN_MINUTES_REMAINING = 3  # Don't trade final 3 minutes
MAX_MINUTES_REMAINING = 38  # Don't trade very start of game (let it develop)
PRICE_MIN = 20  # Don't trade below 20 cents
PRICE_MAX = 80  # Don't trade above 80 cents


class TradingEngine:
    def __init__(self):
        key_id = os.getenv("KALSHI_API_KEY_ID")
        key_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "kalshi_private_key.pem")
        base_url = os.getenv("KALSHI_BASE_URL", "https://api.elections.kalshi.com")

        self.client = KalshiClient(key_id, key_path, base_url)
        self.positions = {}  # ticker -> position info
        self.open_orders = {}  # order_id -> order info
        self.game_market_map = {}  # espn_game_id -> kalshi_ticker
        self.last_scores = {}  # espn_game_id -> (home_score, away_score)
        self.running = False
        self.cycle_count = 0
        self.auth_ok = False  # Track if API auth works
        self.auth_check_interval = 60  # Re-check auth every N cycles
        self.last_auth_check = 0

    def log(self, msg):
        ts = datetime.utcnow().strftime("%H:%M:%S")
        print(f"[{ts}] {msg}")

    def _check_auth(self):
        """Check if API auth works. Returns True if authenticated."""
        try:
            bal = self.client.get_balance()
            balance_cents = bal.get("balance", 0)
            if not self.auth_ok:
                self.log(f"API auth OK! Balance: ${balance_cents/100:.2f}")
            self.auth_ok = True
            return True
        except Exception as e:
            if self.auth_ok or self.last_auth_check == 0:
                self.log(f"API auth failed: {e}")
                self.log("Running in DATA-CAPTURE-ONLY mode (logging ESPN game data)")
            self.auth_ok = False
            return False

    def start(self):
        """Main loop."""
        self.running = True
        self.log("=== Kalshi CBB Trading Engine Started ===")

        # Check auth
        self._check_auth()
        self.last_auth_check = self.cycle_count

        self.log(f"Config: max_contracts={MAX_CONTRACTS}, max_cost=${MAX_COST_CENTS/100:.2f}, edge_threshold={EDGE_THRESHOLD}c")
        self.log(f"Trading range: {PRICE_MIN}-{PRICE_MAX}c, time: {MIN_MINUTES_REMAINING}-{MAX_MINUTES_REMAINING}min")
        self.log(f"Poll interval: {POLL_INTERVAL}s")
        self.log("")

        while self.running:
            try:
                # Periodically re-check auth
                if not self.auth_ok and (self.cycle_count - self.last_auth_check) >= self.auth_check_interval:
                    self._check_auth()
                    self.last_auth_check = self.cycle_count

                self.cycle()
            except KeyboardInterrupt:
                self.log("Shutting down...")
                self.running = False
                break
            except Exception as e:
                self.log(f"ERROR in cycle: {e}")
                traceback.print_exc()

            time.sleep(POLL_INTERVAL)

    def cycle(self):
        """One trading cycle: check games, check markets, find opportunities."""
        self.cycle_count += 1

        # 1. Get live games from ESPN
        live_games = get_live_games()

        if not live_games:
            if self.cycle_count % 20 == 1:  # Log every 5 min when no games
                self.log("No live CBB games. Waiting...")
            return

        # 2. For each live game, check for matching Kalshi market
        for game in live_games:
            try:
                self._process_game(game)
            except Exception as e:
                self.log(f"Error processing {game['name']}: {e}")

        # 3. Check and manage existing positions
        if self.auth_ok:
            self._manage_positions()

        # 4. Print periodic stats
        if self.cycle_count % 12 == 0:  # Every 3 minutes
            stats = get_session_stats()
            pos_count = len(self.positions)
            self.log(f"[STATS] Trades: {stats['trades']} | P&L: {stats['pnl_cents']}c (${stats.get('pnl_dollars', 0)}) | "
                     f"W/L: {stats['wins']}/{stats['losses']} | Positions: {pos_count}")

    def _find_kalshi_market(self, game):
        """Try to find a Kalshi market matching an ESPN game."""
        espn_id = game["espn_id"]

        # Check cache first
        if espn_id in self.game_market_map:
            ticker = self.game_market_map[espn_id]
            if ticker:
                return ticker
            return None

        # Search Kalshi for NCAAB markets
        try:
            # Kalshi CBB tickers follow patterns like NCAAB-<something>
            home_abbr = game["home"]["abbreviation"].upper()
            away_abbr = game["away"]["abbreviation"].upper()

            result = self.client.get_events(params={
                "series_ticker": "NCAAB",
                "status": "open",
                "with_nested_markets": "true",
            })

            events = result.get("events", [])
            for event in events:
                title = (event.get("title", "") + " " + event.get("sub_title", "")).upper()
                # Try to match team names
                home_name = game["home"]["name"].upper()
                away_name = game["away"]["name"].upper()

                # Check if both team names or abbreviations appear
                home_match = home_abbr in title or any(w in title for w in home_name.split() if len(w) > 3)
                away_match = away_abbr in title or any(w in title for w in away_name.split() if len(w) > 3)

                if home_match and away_match:
                    markets = event.get("markets", [])
                    for m in markets:
                        if m.get("status") == "active":
                            ticker = m.get("ticker")
                            self.game_market_map[espn_id] = ticker
                            self.log(f"[MATCH] {game['name']} -> {ticker}")
                            return ticker

        except Exception as e:
            self.log(f"[SEARCH] Error finding market for {game['name']}: {e}")

        # Cache miss
        self.game_market_map[espn_id] = None
        return None

    def _process_game(self, game):
        """Process a single live game: log data, check for trading opportunity."""
        espn_id = game["espn_id"]

        # Log game state
        log_game_state(game)

        # Detect score changes
        prev = self.last_scores.get(espn_id)
        self.last_scores[espn_id] = (game["home_score"], game["away_score"])

        score_changed = prev and prev != (game["home_score"], game["away_score"])

        # Calculate model fair value (home team perspective)
        lead = game["lead"]  # positive = home leads
        mins = game["minutes_remaining"]
        model_fv = fair_value_cents(lead, mins, home=True, pregame_spread=0)
        delta = delta_per_point(lead, mins)
        reversion = mean_reversion_estimate(lead, 0, mins)

        # Log game info even without Kalshi market
        if self.cycle_count % 4 == 1 or score_changed:  # Every minute or on score change
            self.log(f"[GAME] {game['name']} | {game['away_score']}-{game['home_score']} | "
                     f"{game['clock']} P{game['period']} | FV: {model_fv}c | "
                     f"Delta: {delta:.3f}/pt | Reversion: {reversion:+.1f}pts")

        # If no auth, just capture ESPN data
        if not self.auth_ok:
            return

        # Try to find Kalshi market
        ticker = self._find_kalshi_market(game)

        if not ticker:
            return

        # Get market data
        try:
            market = self.client.get_market(ticker)
            market_data = market.get("market", market)
            orderbook = self.client.get_orderbook(ticker)
        except Exception as e:
            self.log(f"[MARKET] Error fetching {ticker}: {e}")
            return

        # Parse market price
        yes_price = market_data.get("yes_bid", 0)
        yes_ask = market_data.get("yes_ask", 100)
        mid_price = (yes_price + yes_ask) / 2 if yes_price and yes_ask else 50
        last_price = market_data.get("last_price", mid_price)

        # Log market snapshot
        log_market_snapshot(ticker, {
            "yes_bid": yes_price,
            "yes_ask": yes_ask,
            "last_price": last_price,
            "model_fv": model_fv,
            "lead": lead,
            "minutes_remaining": mins,
            "period": game["period"],
            "home_score": game["home_score"],
            "away_score": game["away_score"],
            "orderbook": orderbook,
        })

        edge = model_fv - last_price
        self.log(f"[MKT] {ticker} | Market: {last_price}c | FV: {model_fv}c | Edge: {edge:+d}c")

        # Check trading conditions
        if not self._should_trade(game, model_fv, last_price, yes_price, yes_ask):
            return

        # Execute trade
        self._evaluate_trade(game, ticker, model_fv, yes_price, yes_ask, last_price, orderbook)

    def _should_trade(self, game, model_fv, market_price, bid, ask):
        """Check if trading conditions are met."""
        mins = game["minutes_remaining"]

        # Time window check
        if mins < MIN_MINUTES_REMAINING or mins > MAX_MINUTES_REMAINING:
            return False

        # Price range check
        if market_price < PRICE_MIN or market_price > PRICE_MAX:
            return False

        # Edge check
        edge = abs(model_fv - market_price)
        if edge < EDGE_THRESHOLD:
            return False

        # Position limit
        if len(self.positions) >= MAX_POSITIONS:
            return False

        # Don't double up on same game
        espn_id = game["espn_id"]
        for pos in self.positions.values():
            if pos.get("espn_id") == espn_id:
                return False

        # Spread check (don't trade if spread is too wide)
        if ask and bid and (ask - bid) > 6:
            return False

        return True

    def _evaluate_trade(self, game, ticker, model_fv, bid, ask, last_price, orderbook):
        """Evaluate and potentially execute a trade."""
        edge = model_fv - last_price

        # Determine side
        if edge > 0:
            # Model says price should be higher -> buy YES
            side = "yes"
            # Place limit at bid + 1 (improve the bid)
            our_price = min(bid + 1, model_fv - 1)
            our_price = max(our_price, PRICE_MIN)
        else:
            # Model says price should be lower -> buy NO (equivalent to sell YES)
            side = "no"
            # Buy NO at (100 - ask) + 1
            no_price = 100 - ask if ask else 50
            our_price = min(no_price + 1, (100 - model_fv) - 1)
            our_price = max(our_price, PRICE_MIN)

        # Cost check
        if our_price > MAX_COST_CENTS:
            return

        # Ensure minimum edge after fees
        # Maker fee = ceil(0.0175 * P * (1-P)) per contract
        fee_per_contract = max(1, round(0.0175 * (our_price/100) * (1 - our_price/100) * 100))
        net_edge = abs(edge) - fee_per_contract * 2  # Round trip
        if net_edge < 1:
            self.log(f"[SKIP] Edge {abs(edge)}c too small after fees ({fee_per_contract}c each way)")
            return

        self.log(f"[TRADE] Placing {side.upper()} limit @ {our_price}c on {ticker} "
                 f"(edge: {abs(edge)}c, net after fees: {net_edge}c)")

        try:
            if side == "yes":
                result = self.client.create_order(
                    ticker=ticker,
                    side="yes",
                    type="limit",
                    count=MAX_CONTRACTS,
                    yes_price=our_price,
                )
            else:
                result = self.client.create_order(
                    ticker=ticker,
                    side="no",
                    type="limit",
                    count=MAX_CONTRACTS,
                    no_price=our_price,
                )

            order = result.get("order", result)
            order_id = order.get("order_id", "unknown")

            self.log(f"[ORDER] Created order {order_id}: {side} {MAX_CONTRACTS}x @ {our_price}c")

            # Track position
            self.positions[ticker] = {
                "ticker": ticker,
                "espn_id": game["espn_id"],
                "game_name": game["name"],
                "side": side,
                "entry_price": our_price,
                "count": MAX_CONTRACTS,
                "order_id": order_id,
                "entry_time": time.time(),
                "model_fv_at_entry": model_fv,
                "target_exit": our_price + EDGE_THRESHOLD if side == "yes" else our_price - EDGE_THRESHOLD,
                "stop_loss": our_price - STOP_LOSS_CENTS if side == "yes" else our_price + STOP_LOSS_CENTS,
                "filled": False,
            }

            log_trade({
                "action": "open",
                "ticker": ticker,
                "side": side,
                "price": our_price,
                "count": MAX_CONTRACTS,
                "model_fv": model_fv,
                "market_price": last_price,
                "edge": abs(edge),
                "game": game["name"],
                "score": f"{game['away_score']}-{game['home_score']}",
                "minutes_remaining": game["minutes_remaining"],
            })

        except Exception as e:
            self.log(f"[ERROR] Order failed: {e}")

    def _manage_positions(self):
        """Check existing positions for exit signals."""
        to_remove = []

        for ticker, pos in self.positions.items():
            try:
                market = self.client.get_market(ticker)
                market_data = market.get("market", market)

                current_price = market_data.get("last_price", 50)

                # Check if our order was filled by checking positions
                if not pos.get("filled"):
                    # Check actual positions
                    try:
                        positions = self.client.get_positions()
                        for p in positions.get("market_positions", []):
                            if p.get("ticker") == ticker:
                                pos["filled"] = True
                                self.log(f"[FILL] Order filled on {ticker}")
                                break
                    except:
                        pass

                    # If order is >2 minutes old and not filled, cancel it
                    if time.time() - pos["entry_time"] > 120 and not pos.get("filled"):
                        self.log(f"[CANCEL] Canceling unfilled order on {ticker}")
                        try:
                            self.client.cancel_order(pos["order_id"])
                        except:
                            pass
                        to_remove.append(ticker)
                        continue

                # If filled, check exit conditions
                if pos.get("filled"):
                    entry = pos["entry_price"]
                    side = pos["side"]

                    if side == "yes":
                        pnl = current_price - entry
                    else:
                        pnl = entry - current_price  # NO side

                    # Take profit
                    if pnl >= EDGE_THRESHOLD:
                        self.log(f"[EXIT] Taking profit on {ticker}: +{pnl}c")
                        self._close_position(ticker, pos, pnl)
                        to_remove.append(ticker)

                    # Stop loss
                    elif pnl <= -STOP_LOSS_CENTS:
                        self.log(f"[EXIT] Stop loss on {ticker}: {pnl}c")
                        self._close_position(ticker, pos, pnl)
                        to_remove.append(ticker)

                    # Time-based exit (5 min max hold)
                    elif time.time() - pos["entry_time"] > 300:
                        self.log(f"[EXIT] Time exit on {ticker}: {pnl}c")
                        self._close_position(ticker, pos, pnl)
                        to_remove.append(ticker)

            except Exception as e:
                self.log(f"[ERROR] Managing {ticker}: {e}")

        for t in to_remove:
            del self.positions[t]

    def _close_position(self, ticker, pos, pnl_cents):
        """Close a position."""
        try:
            # Sell our position
            close_side = "no" if pos["side"] == "yes" else "yes"
            self.client.create_order(
                ticker=ticker,
                side=close_side,
                type="market",
                count=pos["count"],
            )
            self.log(f"[CLOSED] {ticker}: P&L = {pnl_cents:+d}c")
        except Exception as e:
            self.log(f"[ERROR] Closing {ticker}: {e}")

        log_trade({
            "action": "close",
            "ticker": ticker,
            "side": pos["side"],
            "entry_price": pos["entry_price"],
            "pnl_cents": pnl_cents,
            "hold_time_sec": round(time.time() - pos["entry_time"]),
            "game": pos["game_name"],
        })


def run():
    """Entry point."""
    engine = TradingEngine()
    engine.start()
