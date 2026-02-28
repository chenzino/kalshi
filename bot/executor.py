"""Trade execution engine for short-term volatility scalping.

Rules:
- 1-5 contracts per trade, max 95c each
- Max 5 open positions across multiple games
- Only KXNCAAMBGAME (men's moneyline)
- Min signal strength 5, min edge 3c after fees
- Orders expire after 60s if not filled
- Positions auto-close after 5 min max hold
- Exit: model edge gone > take profit +5c > stop loss -5c > time 5min
"""
import time
import json
import os
from datetime import datetime, timezone, timedelta
from bot.data_logger import log_trade
from bot.event_log import log_event

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
EST = timezone(timedelta(hours=-5))

# ── Execution Parameters ──────────────────────────────────────
MAX_CONTRACTS = 1      # Contracts per order (keep at 1, scale via repeat entries)
MAX_COST_CENTS = 95
MIN_SIGNAL_STRENGTH = 5  # Lowered from 6 to get more trades for learning
MAX_POSITIONS = 5      # Up from 3 - spread across multiple games
MIN_EDGE = 3           # Min edge (cents) to enter
ORDER_TIMEOUT = 60     # Cancel unfilled after 60s
STOP_LOSS = 5          # Hard stop at -5c
TAKE_PROFIT = 5        # Hard take at +5c
TIME_EXIT = 300        # 5 min max hold
EDGE_EXIT = -1         # Exit when model edge flips to -1c
FILL_CHECK_INTERVAL = 15  # Check fills every 15s
TICKER_COOLDOWN = 120  # 2 min between trades on same ticker (was 3)
GAME_COOLDOWN = 30     # 30s between trades on same game event (was 60)


class Position:
    """Tracks a single position from entry to exit."""
    def __init__(self, ticker, side, entry_price, order_id, signal):
        self.ticker = ticker
        self.side = side
        self.entry_price = entry_price
        self.order_id = order_id
        self.signal = signal
        self.entry_time = time.time()
        self.filled = False
        self.fill_price = None
        self.exit_price = None
        self.exit_reason = None
        self.pnl = None
        self.last_model_fv = signal.get("model_fv", 50)
        self.last_edge = signal.get("edge", 0)
        self.last_fill_check = 0
        self.edge_updates = 0  # Count of model updates received
        self.game_event = _extract_game_event(ticker)

    def to_dict(self):
        return {
            "ticker": self.ticker,
            "side": self.side,
            "entry_price": self.entry_price,
            "order_id": self.order_id,
            "strategy": self.signal.get("strategy", ""),
            "entry_time": self.entry_time,
            "filled": self.filled,
            "fill_price": self.fill_price,
            "exit_price": self.exit_price,
            "exit_reason": self.exit_reason,
            "pnl": self.pnl,
            "signal_edge": self.signal.get("edge", 0),
            "signal_strength": self.signal.get("strength", 0),
            "last_model_fv": self.last_model_fv,
            "last_edge": self.last_edge,
            "age": round(time.time() - self.entry_time),
        }


def _extract_game_event(ticker):
    """Extract game event from ticker: KXNCAAMBGAME-26FEB27MICHILL-MICH -> KXNCAAMBGAME-26FEB27MICHILL"""
    parts = ticker.rsplit("-", 1)
    return parts[0] if len(parts) == 2 else ticker


class Executor:
    def __init__(self, client, log_fn=None):
        self.client = client
        self.positions = {}      # ticker -> Position
        self.log = log_fn or (lambda msg: print(f"[EXEC] {msg}"))
        self.total_pnl = 0
        self.trade_count = 0
        self.enabled = True
        self.recent_tickers = {}  # ticker -> last_trade_time
        self.recent_events = {}   # game_event -> last_trade_time
        self._known_kalshi_tickers = set()  # Tickers with existing Kalshi positions
        self._load_existing_positions()

    def _load_existing_positions(self):
        """Load existing Kalshi positions on startup to prevent duplicates."""
        if not self.client:
            return
        try:
            pos = self.client.get_positions()
            for p in pos.get("market_positions", []):
                position = p.get("position", 0)
                if position != 0:
                    ticker = p["ticker"]
                    self._known_kalshi_tickers.add(ticker)
                    game_event = _extract_game_event(ticker)
                    self.recent_events[game_event] = time.time()
                    self.recent_tickers[ticker] = time.time()
            if self._known_kalshi_tickers:
                self.log(f"[EXEC] Found {len(self._known_kalshi_tickers)} existing positions on Kalshi")
        except Exception as e:
            self.log(f"[EXEC] Could not load existing positions: {e}")

    def on_signal(self, signal):
        """Evaluate a strategy signal for execution."""
        if not self.enabled or not self.client:
            return

        ticker = signal.get("ticker", "")
        strength = signal.get("strength", 0)
        edge = signal.get("edge", 0)
        side = signal.get("side", "yes")
        market_price = signal.get("market_price")

        # Gate: only strong signals with real edge
        if strength < MIN_SIGNAL_STRENGTH or edge < MIN_EDGE:
            return

        # Gate: only men's moneyline
        if "KXNCAAMBGAME" not in ticker:
            return

        # Gate: position limits
        if len(self.positions) >= MAX_POSITIONS:
            return

        # Gate: no doubling up on same ticker (in-memory or on Kalshi)
        if ticker in self.positions or ticker in self._known_kalshi_tickers:
            return

        # Gate: max 1 position per game event at a time (don't trade both sides)
        game_event = _extract_game_event(ticker)
        game_positions = sum(1 for p in self.positions.values() if p.game_event == game_event)
        if game_positions >= 1:
            return

        # Gate: ticker cooldown
        now = time.time()
        if now - self.recent_tickers.get(ticker, 0) < TICKER_COOLDOWN:
            return

        # Gate: game event cooldown (don't re-enter same game too fast)
        if now - self.recent_events.get(game_event, 0) < GAME_COOLDOWN:
            return

        # Gate: price sanity - avoid extreme prices with bad risk/reward
        if market_price is None or market_price < 10 or market_price > 90:
            return

        # Calculate our cost
        if side == "yes":
            our_price = min(market_price + 1, MAX_COST_CENTS)
        else:
            our_price = min(100 - market_price + 1, MAX_COST_CENTS)

        # Gate: don't pay more than 85c (risk/reward gets awful)
        if our_price > 85:
            return

        # Fee check (~1c each way conservative)
        if edge - 2 < 1:
            return

        self._place_order(ticker, side, our_price, signal)

    def _place_order(self, ticker, side, price, signal):
        """Place a limit order on Kalshi."""
        try:
            if side == "yes":
                result = self.client.create_order(
                    ticker=ticker, side="yes", type="limit",
                    count=MAX_CONTRACTS, yes_price=price,
                )
            else:
                result = self.client.create_order(
                    ticker=ticker, side="no", type="limit",
                    count=MAX_CONTRACTS, no_price=price,
                )

            order = result.get("order", result)
            order_id = order.get("order_id", "unknown")

            self.log(f"[TRADE] BUY {side.upper()} {ticker} @ {price}c | "
                     f"{signal.get('strategy')} edge={signal.get('edge')}c")

            pos = Position(ticker, side, price, order_id, signal)
            self.positions[ticker] = pos

            log_trade({
                "action": "open",
                "ticker": ticker, "side": side, "price": price,
                "order_id": order_id,
                "strategy": signal.get("strategy", ""),
                "edge": signal.get("edge", 0),
                "strength": signal.get("strength", 0),
                "game": signal.get("game_context", {}).get("name", ""),
            })

            log_event("trade_open", {
                "ticker": ticker, "side": side, "price": price,
                "strategy": signal.get("strategy", ""),
                "edge": signal.get("edge", 0),
            })

        except Exception as e:
            self.log(f"[TRADE] ORDER FAILED {ticker}: {e}")
            log_event("trade_error", {"ticker": ticker, "error": str(e)})

    def update_model_fv(self, ticker, model_fv, market_price):
        """Update model fair value for open position. Called every cycle from orchestrator."""
        pos = self.positions.get(ticker)
        if not pos or not pos.filled:
            return

        pos.last_model_fv = model_fv
        pos.edge_updates += 1

        # Current edge from our position's perspective
        if pos.side == "yes":
            pos.last_edge = model_fv - market_price
        else:
            pos.last_edge = market_price - model_fv

    def check_positions(self, current_prices=None):
        """Check all open positions. Called every cycle."""
        if not self.positions:
            return

        current_prices = current_prices or {}
        now = time.time()
        to_close = []

        # ── Fill detection (batch, throttled) ──
        unfilled = [t for t, p in self.positions.items() if not p.filled]
        if unfilled:
            should_check = any(
                now - self.positions[t].last_fill_check >= FILL_CHECK_INTERVAL
                for t in unfilled
            )
            if should_check:
                try:
                    fills = self.client.get_fills(params={"limit": 20})
                    fill_tickers = {f.get("ticker") for f in fills.get("fills", [])}
                    for ticker in unfilled:
                        pos = self.positions[ticker]
                        pos.last_fill_check = now
                        if ticker in fill_tickers:
                            pos.filled = True
                            pos.fill_price = pos.entry_price
                            self.log(f"[TRADE] FILLED {ticker} {pos.side} @ {pos.entry_price}c")
                except Exception:
                    pass

        # ── Position management ──
        for ticker, pos in self.positions.items():
            age = now - pos.entry_time

            # Unfilled: cancel after timeout
            if not pos.filled:
                if age > ORDER_TIMEOUT:
                    self.log(f"[TRADE] CANCEL unfilled {ticker} after {age:.0f}s")
                    try:
                        self.client.cancel_order(pos.order_id)
                    except Exception:
                        pass
                    to_close.append(ticker)
                continue

            # ── EXIT RULES (priority order) ──
            current_yes = current_prices.get(ticker, pos.entry_price)
            # Convert to position-side value: YES price stays, NO value = 100 - YES price
            if pos.side == "yes":
                current = current_yes
            else:
                current = 100 - current_yes
            pnl = current - pos.entry_price

            # 1. MODEL EXIT: edge has flipped (model says we're wrong now)
            if pos.edge_updates >= 2 and pos.last_edge <= EDGE_EXIT:
                self._exit_position(ticker, pos, current, "model_exit", pnl)
                to_close.append(ticker)
            # 2. TAKE PROFIT: lock in gains
            elif pnl >= TAKE_PROFIT:
                self._exit_position(ticker, pos, current, "take_profit", pnl)
                to_close.append(ticker)
            # 3. STOP LOSS: cut losses
            elif pnl <= -STOP_LOSS:
                self._exit_position(ticker, pos, current, "stop_loss", pnl)
                to_close.append(ticker)
            # 4. TIME EXIT: don't hold longer than 5 min
            elif age > TIME_EXIT:
                self._exit_position(ticker, pos, current, "time_exit", pnl)
                to_close.append(ticker)

        for t in to_close:
            game_event = _extract_game_event(t)
            self.recent_tickers[t] = now
            self.recent_events[game_event] = now
            del self.positions[t]

    def _exit_position(self, ticker, pos, exit_price, reason, pnl):
        """Close position by selling same side at market."""
        try:
            # Sell at floor price (1c) to get immediate fill like a market order
            price_arg = {"yes_price": 1} if pos.side == "yes" else {"no_price": 1}
            self.client.create_order(
                ticker=ticker, side=pos.side, action="sell", type="limit",
                count=MAX_CONTRACTS, **price_arg,
            )
        except Exception as e:
            self.log(f"[TRADE] EXIT FAILED {ticker}: {e}")

        pos.exit_price = exit_price
        pos.exit_reason = reason
        pos.pnl = pnl
        self.total_pnl += pnl
        self.trade_count += 1

        hold = round(time.time() - pos.entry_time)
        self.log(f"[TRADE] SELL {ticker} | {reason} | {hold}s hold | "
                 f"P&L: {pnl:+d}c | Session: {self.total_pnl:+d}c")

        log_trade({
            "action": "close",
            "ticker": ticker, "side": pos.side,
            "entry_price": pos.entry_price, "exit_price": exit_price,
            "pnl_cents": pnl, "exit_reason": reason,
            "hold_time": hold,
            "strategy": pos.signal.get("strategy", ""),
        })

        log_event("trade_close", {
            "ticker": ticker, "reason": reason, "pnl": pnl,
            "hold_time": hold,
            "total_pnl": self.total_pnl, "strategy": pos.signal.get("strategy", ""),
        })

    def get_status(self):
        return {
            "enabled": self.enabled,
            "open_positions": len(self.positions),
            "total_trades": self.trade_count,
            "total_pnl": self.total_pnl,
            "positions": {t: p.to_dict() for t, p in self.positions.items()},
        }
