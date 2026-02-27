"""Trade execution engine.

Converts strategy signals into real orders on Kalshi.
Manages position lifecycle: entry -> monitoring -> exit.

Safety constraints:
- Max 1 contract per trade
- Max $1 (100c) per trade
- Max 3 open positions
- Only trades moneyline markets (game winner)
- Minimum signal strength of 6 to execute
- Auto-cancels unfilled orders after 2 min
- Stop loss at -5c, take profit at +3c, time exit at 5 min
"""
import time
import json
import os
from datetime import datetime, timezone, timedelta
from bot.data_logger import log_trade

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
EST = timezone(timedelta(hours=-5))

# Execution parameters
MAX_CONTRACTS = 1
MAX_COST_CENTS = 95    # Max price to pay per contract
MIN_SIGNAL_STRENGTH = 6
MAX_POSITIONS = 3
MIN_EDGE = 3           # Min edge after fees to execute
ORDER_TIMEOUT = 120    # Cancel unfilled orders after 2 min
STOP_LOSS = 5          # Close at -5c
TAKE_PROFIT = 3        # Close at +3c
TIME_EXIT = 300        # Close after 5 min hold


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


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
        }


class Executor:
    def __init__(self, client, log_fn=None):
        self.client = client
        self.positions = {}  # ticker -> Position
        self.log = log_fn or (lambda msg: print(f"[EXEC] {msg}"))
        self.total_pnl = 0
        self.trade_count = 0
        self.enabled = True

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

        # Filter: only moneyline for now (safest, most liquid)
        if "GAME" not in ticker and "WINNER" not in ticker:
            return

        # Position limit
        if len(self.positions) >= MAX_POSITIONS:
            return

        # No doubling up
        if ticker in self.positions:
            return

        # Price sanity
        if market_price is None or market_price < 5 or market_price > 95:
            return

        # Calculate our limit price
        if side == "yes":
            # Buy YES: place limit slightly above bid
            our_price = min(market_price + 1, MAX_COST_CENTS)
        else:
            # Buy NO: our NO price = 100 - (market_yes_price - 1)
            our_price = min(100 - market_price + 1, MAX_COST_CENTS)

        # Fee check: maker fee = ceil(0.0175 * P * (1-P))
        fee = max(1, round(0.0175 * (our_price / 100) * (1 - our_price / 100) * 100))
        net_edge = edge - fee * 2  # Round trip
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

            self.log(f"ORDER {side.upper()} {ticker} @ {price}c | "
                     f"strategy={signal.get('strategy')} edge={signal.get('edge')}c "
                     f"str={signal.get('strength')}")

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

        except Exception as e:
            self.log(f"ORDER FAILED {ticker}: {e}")

    def check_positions(self, current_prices=None):
        """Check all open positions for fills, exits, timeouts."""
        if not self.positions:
            return

        current_prices = current_prices or {}
        to_close = []

        for ticker, pos in self.positions.items():
            now = time.time()
            age = now - pos.entry_time

            # Check if filled
            if not pos.filled:
                try:
                    positions = self.client.get_positions()
                    for p in positions.get("market_positions", []):
                        if p.get("ticker") == ticker:
                            qty = p.get("position", 0) if pos.side == "yes" else p.get("position", 0)
                            if qty != 0:
                                pos.filled = True
                                pos.fill_price = pos.entry_price
                                self.log(f"FILLED {ticker} {pos.side} @ {pos.entry_price}c")
                                break
                except Exception:
                    pass

                # Cancel unfilled orders after timeout
                if age > ORDER_TIMEOUT and not pos.filled:
                    self.log(f"CANCEL unfilled {ticker} after {age:.0f}s")
                    try:
                        self.client.cancel_order(pos.order_id)
                    except Exception:
                        pass
                    to_close.append(ticker)
                    continue

            # If filled, check exit conditions
            if pos.filled:
                current = current_prices.get(ticker, pos.entry_price)

                if pos.side == "yes":
                    pnl = current - pos.entry_price
                else:
                    pnl = pos.entry_price - current

                # Take profit
                if pnl >= TAKE_PROFIT:
                    self._exit_position(ticker, pos, current, "take_profit", pnl)
                    to_close.append(ticker)
                # Stop loss
                elif pnl <= -STOP_LOSS:
                    self._exit_position(ticker, pos, current, "stop_loss", pnl)
                    to_close.append(ticker)
                # Time exit
                elif age > TIME_EXIT:
                    self._exit_position(ticker, pos, current, "time_exit", pnl)
                    to_close.append(ticker)

        for t in to_close:
            del self.positions[t]

    def _exit_position(self, ticker, pos, exit_price, reason, pnl):
        """Close a position."""
        try:
            close_side = "no" if pos.side == "yes" else "yes"
            self.client.create_order(
                ticker=ticker, side=close_side, type="market",
                count=MAX_CONTRACTS,
            )
        except Exception as e:
            self.log(f"EXIT FAILED {ticker}: {e}")

        pos.exit_price = exit_price
        pos.exit_reason = reason
        pos.pnl = pnl
        self.total_pnl += pnl
        self.trade_count += 1

        self.log(f"EXIT {ticker} | {reason} | P&L: {pnl:+d}c | Total: {self.total_pnl:+d}c")

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

    def get_status(self):
        """Return current execution status."""
        return {
            "enabled": self.enabled,
            "open_positions": len(self.positions),
            "total_trades": self.trade_count,
            "total_pnl": self.total_pnl,
            "positions": {t: p.to_dict() for t, p in self.positions.items()},
        }
