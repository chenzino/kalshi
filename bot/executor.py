"""Trade execution engine.

Converts strategy signals into real orders on Kalshi.
Manages position lifecycle: entry -> monitoring -> exit.

Safety constraints:
- Max 1 contract per trade
- Max 95c per contract
- Max 3 open positions
- Only trades moneyline markets (game winner)
- Minimum signal strength of 6 to execute
- Auto-cancels unfilled orders after 90s
- Model-aware exits: exit when edge flips or evaporates
- Fallback stop loss at -8c, take profit at +6c
- Time exit at 8 min max hold
"""
import time
import json
import os
from datetime import datetime, timezone, timedelta
from bot.data_logger import log_trade
from bot.event_log import log_event

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
EST = timezone(timedelta(hours=-5))

# Execution parameters
MAX_CONTRACTS = 1
MAX_COST_CENTS = 95    # Max price to pay per contract
MIN_SIGNAL_STRENGTH = 6
MAX_POSITIONS = 3
MIN_EDGE = 3           # Min edge (cents) after fees to execute
ORDER_TIMEOUT = 90     # Cancel unfilled orders after 90s
STOP_LOSS = 8          # Hard stop at -8c (model exit should trigger first)
TAKE_PROFIT = 6        # Hard take at +6c (model exit should trigger first)
TIME_EXIT = 480        # Hard time exit at 8 min
EDGE_EXIT_THRESHOLD = -1  # Exit when model edge flips to -1c or worse
FILL_CHECK_INTERVAL = 30  # Check fills every 30s (not every cycle)


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
        self.edge_history = []  # Track edge over time for trend

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
        }


class Executor:
    def __init__(self, client, log_fn=None):
        self.client = client
        self.positions = {}  # ticker -> Position
        self.log = log_fn or (lambda msg: print(f"[EXEC] {msg}"))
        self.total_pnl = 0
        self.trade_count = 0
        self.enabled = True
        self.recent_tickers = {}  # ticker -> last_trade_time (cooldown)
        self.TICKER_COOLDOWN = 300  # Don't re-enter same ticker within 5 min

    def on_signal(self, signal):
        """Evaluate a strategy signal for execution."""
        if not self.enabled or not self.client:
            return

        ticker = signal.get("ticker", "")
        strength = signal.get("strength", 0)
        edge = signal.get("edge", 0)
        side = signal.get("side", "yes")
        market_price = signal.get("market_price")
        strategy = signal.get("strategy", "")

        # Filter: only strong signals
        if strength < MIN_SIGNAL_STRENGTH:
            return

        if edge < MIN_EDGE:
            return

        # Filter: only moneyline
        if "GAME" not in ticker and "WINNER" not in ticker:
            return

        # Position limit
        if len(self.positions) >= MAX_POSITIONS:
            return

        # No doubling up
        if ticker in self.positions:
            return

        # Ticker cooldown - don't re-enter recently exited tickers
        last_trade = self.recent_tickers.get(ticker, 0)
        if time.time() - last_trade < self.TICKER_COOLDOWN:
            return

        # Price sanity
        if market_price is None or market_price < 5 or market_price > 95:
            return

        # Calculate our limit price (post at the bid/ask to be a maker)
        if side == "yes":
            our_price = min(market_price + 1, MAX_COST_CENTS)
        else:
            our_price = min(100 - market_price + 1, MAX_COST_CENTS)

        # Fee check: Kalshi maker fee = 0 for makers, taker fee varies
        # Conservative: assume we pay ~1c each way
        fee_roundtrip = 2
        net_edge = edge - fee_roundtrip
        if net_edge < 1:
            return

        self._place_order(ticker, side, our_price, signal)

    def _place_order(self, ticker, side, price, signal):
        """Place a limit order."""
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

            self.log(f"[TRADE] ORDER {side.upper()} {ticker} @ {price}c | "
                     f"{signal.get('strategy')} edge={signal.get('edge')}c str={signal.get('strength')}")

            pos = Position(ticker, side, price, order_id, signal)
            self.positions[ticker] = pos

            log_trade({
                "action": "open",
                "ticker": ticker,
                "side": side,
                "price": price,
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
        """Update the model fair value for an open position. Called from orchestrator."""
        pos = self.positions.get(ticker)
        if not pos or not pos.filled:
            return

        pos.last_model_fv = model_fv

        # Calculate current edge from model's perspective
        if pos.side == "yes":
            pos.last_edge = model_fv - market_price
        else:
            pos.last_edge = market_price - model_fv

        pos.edge_history.append((time.time(), pos.last_edge))

    def check_positions(self, current_prices=None):
        """Check all open positions for fills, exits, timeouts."""
        if not self.positions:
            return

        current_prices = current_prices or {}
        now = time.time()
        to_close = []

        # Batch fill check: use get_fills API (single call for all positions)
        unfilled = [t for t, p in self.positions.items() if not p.filled]
        if unfilled:
            # Only check fills periodically to save API calls
            should_check = any(
                now - self.positions[t].last_fill_check >= FILL_CHECK_INTERVAL
                for t in unfilled
            )
            if should_check:
                try:
                    fills = self.client.get_fills(params={"limit": 20})
                    fill_tickers = set()
                    for f in fills.get("fills", []):
                        fill_tickers.add(f.get("ticker"))

                    for ticker in unfilled:
                        pos = self.positions[ticker]
                        pos.last_fill_check = now
                        if ticker in fill_tickers:
                            pos.filled = True
                            pos.fill_price = pos.entry_price
                            self.log(f"[TRADE] FILLED {ticker} {pos.side} @ {pos.entry_price}c")
                except Exception:
                    pass

        for ticker, pos in self.positions.items():
            age = now - pos.entry_time

            # Unfilled order management
            if not pos.filled:
                if age > ORDER_TIMEOUT:
                    self.log(f"[TRADE] CANCEL unfilled {ticker} after {age:.0f}s")
                    try:
                        self.client.cancel_order(pos.order_id)
                    except Exception:
                        pass
                    to_close.append(ticker)
                continue

            # Filled position exit logic
            current = current_prices.get(ticker, pos.entry_price)

            if pos.side == "yes":
                pnl = current - pos.entry_price
            else:
                pnl = pos.entry_price - current

            # 1. Model-based exit: edge has evaporated or flipped
            if len(pos.edge_history) >= 2 and pos.last_edge <= EDGE_EXIT_THRESHOLD:
                self._exit_position(ticker, pos, current, "model_exit", pnl)
                to_close.append(ticker)
            # 2. Hard take profit
            elif pnl >= TAKE_PROFIT:
                self._exit_position(ticker, pos, current, "take_profit", pnl)
                to_close.append(ticker)
            # 3. Hard stop loss
            elif pnl <= -STOP_LOSS:
                self._exit_position(ticker, pos, current, "stop_loss", pnl)
                to_close.append(ticker)
            # 4. Time exit
            elif age > TIME_EXIT:
                self._exit_position(ticker, pos, current, "time_exit", pnl)
                to_close.append(ticker)

        for t in to_close:
            self.recent_tickers[t] = now  # Mark cooldown
            del self.positions[t]

    def _exit_position(self, ticker, pos, exit_price, reason, pnl):
        """Close a position with a limit order (save on spread)."""
        try:
            # Use limit order at current price to avoid market order spread cost
            close_side = "no" if pos.side == "yes" else "yes"
            if close_side == "yes":
                result = self.client.create_order(
                    ticker=ticker, side="yes", type="limit",
                    count=MAX_CONTRACTS, yes_price=max(1, exit_price - 1),
                )
            else:
                result = self.client.create_order(
                    ticker=ticker, side="no", type="limit",
                    count=MAX_CONTRACTS, no_price=max(1, 100 - exit_price - 1),
                )
        except Exception as e:
            # Fallback to market order if limit fails
            try:
                self.client.create_order(
                    ticker=ticker, side=close_side, type="market",
                    count=MAX_CONTRACTS,
                )
            except Exception as e2:
                self.log(f"[TRADE] EXIT FAILED {ticker}: {e2}")

        pos.exit_price = exit_price
        pos.exit_reason = reason
        pos.pnl = pnl
        self.total_pnl += pnl
        self.trade_count += 1

        self.log(f"[TRADE] EXIT {ticker} | {reason} | P&L: {pnl:+d}c | Total: {self.total_pnl:+d}c")

        log_trade({
            "action": "close",
            "ticker": ticker,
            "side": pos.side,
            "entry_price": pos.entry_price,
            "exit_price": exit_price,
            "pnl_cents": pnl,
            "exit_reason": reason,
            "hold_time": round(time.time() - pos.entry_time),
            "strategy": pos.signal.get("strategy", ""),
        })

        log_event("trade_close", {
            "ticker": ticker, "reason": reason, "pnl": pnl,
            "total_pnl": self.total_pnl, "strategy": pos.signal.get("strategy", ""),
        })

    def get_status(self):
        """Return current execution status."""
        return {
            "enabled": self.enabled,
            "open_positions": len(self.positions),
            "total_trades": self.trade_count,
            "total_pnl": self.total_pnl,
            "positions": {t: p.to_dict() for t, p in self.positions.items()},
        }
