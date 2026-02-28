"""Trade execution engine for short-term volatility scalping.

Position sizing: target consistent ~50c risk per trade regardless of price.
Cheap contracts (20c) = buy 2-3. Expensive (70c) = buy 1.
All P&L measured as % return on capital deployed.

Exit rules (priority):
1. Model exit: edge flipped, get out
2. Take profit: +15% return
3. Trailing stop: gave back 5% from peak
4. Stop loss: -10% return
5. Time exit: 5 min max hold
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
TARGET_POSITION_CENTS = 60  # Target ~60c ($0.60) per position
MAX_COST_CENTS = 85         # Don't pay more than 85c per contract
MIN_SIGNAL_STRENGTH = 5
MAX_POSITIONS = 8           # Spread across many games
MIN_EDGE = 3                # Min edge (cents) to enter
ORDER_TIMEOUT = 45          # Cancel unfilled after 45s
STOP_LOSS_PCT = 10          # -10% of capital deployed
TAKE_PROFIT_PCT = 15        # +15% of capital deployed
TRAILING_STOP_PCT = 5       # Give back at most 5% from peak
TRAILING_ACTIVATE_PCT = 8   # Trailing stop kicks in at +8%
TIME_EXIT = 300             # 5 min max hold
EDGE_EXIT = -1              # Exit when model edge flips to -1c
FILL_CHECK_INTERVAL = 15
TICKER_COOLDOWN = 60        # 1 min between trades on same ticker
GAME_COOLDOWN = 20          # 20s between trades on same game event


class Position:
    """Tracks a single position from entry to exit."""
    def __init__(self, ticker, side, entry_price, contracts, order_id, signal):
        self.ticker = ticker
        self.side = side
        self.entry_price = entry_price  # Per-contract cost in cents
        self.contracts = contracts
        self.total_cost = entry_price * contracts  # Total capital deployed
        self.order_id = order_id
        self.signal = signal
        self.entry_time = time.time()
        self.filled = False
        self.fill_price = None
        self.exit_price = None
        self.exit_reason = None
        self.pnl = None
        self.pnl_pct = None
        self.last_model_fv = signal.get("model_fv", 50)
        self.last_edge = signal.get("edge", 0)
        self.last_fill_check = 0
        self.edge_updates = 0
        self.game_event = _extract_game_event(ticker)
        self.peak_pnl_pct = 0.0  # High water mark (%)

    def to_dict(self):
        return {
            "ticker": self.ticker,
            "side": self.side,
            "entry_price": self.entry_price,
            "contracts": self.contracts,
            "total_cost": self.total_cost,
            "order_id": self.order_id,
            "strategy": self.signal.get("strategy", ""),
            "entry_time": self.entry_time,
            "filled": self.filled,
            "fill_price": self.fill_price,
            "exit_price": self.exit_price,
            "exit_reason": self.exit_reason,
            "pnl": self.pnl,
            "pnl_pct": self.pnl_pct,
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


def _calc_contracts(price_cents, target=TARGET_POSITION_CENTS):
    """Calculate how many contracts to buy for consistent position sizing.
    Target ~60c deployed per position. Cheap = more contracts, expensive = 1."""
    if price_cents <= 0:
        return 1
    n = max(1, round(target / price_cents))
    return min(n, 3)  # Cap at 3 contracts per position


class Executor:
    def __init__(self, client, log_fn=None):
        self.client = client
        self.positions = {}      # ticker -> Position
        self.log = log_fn or (lambda msg: print(f"[EXEC] {msg}"))
        self.total_pnl = 0       # cents
        self.total_invested = 0  # cents deployed (for ROI tracking)
        self.trade_count = 0
        self.enabled = True
        self.recent_tickers = {}
        self.recent_events = {}
        self._known_kalshi_tickers = set()
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

        if strength < MIN_SIGNAL_STRENGTH or edge < MIN_EDGE:
            return

        if "KXNCAAMBGAME" not in ticker:
            return

        if len(self.positions) >= MAX_POSITIONS:
            return

        if ticker in self.positions or ticker in self._known_kalshi_tickers:
            return

        game_event = _extract_game_event(ticker)
        game_positions = sum(1 for p in self.positions.values() if p.game_event == game_event)
        if game_positions >= 1:
            return

        now = time.time()
        if now - self.recent_tickers.get(ticker, 0) < TICKER_COOLDOWN:
            return
        if now - self.recent_events.get(game_event, 0) < GAME_COOLDOWN:
            return

        # Price sanity
        if market_price is None or market_price < 10 or market_price > 90:
            return

        # Calculate per-contract cost
        if side == "yes":
            unit_price = min(market_price + 1, MAX_COST_CENTS)
        else:
            unit_price = min(100 - market_price + 1, MAX_COST_CENTS)

        if unit_price > MAX_COST_CENTS or unit_price < 10:
            return

        # Fee check (~1c each way conservative)
        if edge - 2 < 1:
            return

        # Dynamic position sizing: target consistent capital per trade
        contracts = _calc_contracts(unit_price)

        self._place_order(ticker, side, unit_price, contracts, signal)

    def _place_order(self, ticker, side, price, contracts, signal):
        """Place a limit order on Kalshi."""
        try:
            if side == "yes":
                result = self.client.create_order(
                    ticker=ticker, side="yes", type="limit",
                    count=contracts, yes_price=price,
                )
            else:
                result = self.client.create_order(
                    ticker=ticker, side="no", type="limit",
                    count=contracts, no_price=price,
                )

            order = result.get("order", result)
            order_id = order.get("order_id", "unknown")
            total = price * contracts

            self.log(f"[TRADE] BUY {contracts}x {side.upper()} {ticker} @ {price}c "
                     f"(${total/100:.2f}) | {signal.get('strategy')} edge={signal.get('edge')}c")

            pos = Position(ticker, side, price, contracts, order_id, signal)
            self.positions[ticker] = pos

            log_trade({
                "action": "open",
                "ticker": ticker, "side": side, "price": price,
                "contracts": contracts, "total_cost": total,
                "order_id": order_id,
                "strategy": signal.get("strategy", ""),
                "edge": signal.get("edge", 0),
                "strength": signal.get("strength", 0),
                "game": signal.get("game_context", {}).get("name", ""),
            })

            log_event("trade_open", {
                "ticker": ticker, "side": side, "price": price,
                "contracts": contracts, "total_cost": total,
                "strategy": signal.get("strategy", ""),
                "edge": signal.get("edge", 0),
            })

        except Exception as e:
            self.log(f"[TRADE] ORDER FAILED {ticker}: {e}")
            log_event("trade_error", {"ticker": ticker, "error": str(e)})

    def update_model_fv(self, ticker, model_fv, market_price):
        """Update model fair value for open position."""
        pos = self.positions.get(ticker)
        if not pos or not pos.filled:
            return

        pos.last_model_fv = model_fv
        pos.edge_updates += 1

        if pos.side == "yes":
            pos.last_edge = model_fv - market_price
        else:
            pos.last_edge = market_price - model_fv

    def check_positions(self, current_prices=None):
        """Check all open positions. All exits use % return on capital."""
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
                            self.log(f"[TRADE] FILLED {ticker} {pos.contracts}x "
                                     f"{pos.side} @ {pos.entry_price}c")
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

            # ── EXIT RULES (all %-based) ──
            current_yes = current_prices.get(ticker, pos.entry_price)
            if pos.side == "yes":
                current = current_yes
            else:
                current = 100 - current_yes

            pnl_per = current - pos.entry_price  # Per-contract P&L in cents
            pnl_total = pnl_per * pos.contracts   # Total P&L in cents
            pnl_pct = (pnl_per / pos.entry_price * 100) if pos.entry_price > 0 else 0

            # Track high water mark
            if pnl_pct > pos.peak_pnl_pct:
                pos.peak_pnl_pct = pnl_pct

            # 1. MODEL EXIT: edge has flipped
            if pos.edge_updates >= 2 and pos.last_edge <= EDGE_EXIT:
                self._exit_position(ticker, pos, current, "model_exit", pnl_total, pnl_pct)
                to_close.append(ticker)
            # 2. TAKE PROFIT: +15% return
            elif pnl_pct >= TAKE_PROFIT_PCT:
                self._exit_position(ticker, pos, current, "take_profit", pnl_total, pnl_pct)
                to_close.append(ticker)
            # 3. TRAILING STOP: once +8%, don't give back more than 5%
            elif pos.peak_pnl_pct >= TRAILING_ACTIVATE_PCT and pnl_pct <= pos.peak_pnl_pct - TRAILING_STOP_PCT:
                self._exit_position(ticker, pos, current, "trailing_stop", pnl_total, pnl_pct)
                to_close.append(ticker)
            # 4. STOP LOSS: -10% return
            elif pnl_pct <= -STOP_LOSS_PCT:
                self._exit_position(ticker, pos, current, "stop_loss", pnl_total, pnl_pct)
                to_close.append(ticker)
            # 5. TIME EXIT: 5 min max hold
            elif age > TIME_EXIT:
                self._exit_position(ticker, pos, current, "time_exit", pnl_total, pnl_pct)
                to_close.append(ticker)

        for t in to_close:
            game_event = _extract_game_event(t)
            self.recent_tickers[t] = now
            self.recent_events[game_event] = now
            del self.positions[t]

    def _exit_position(self, ticker, pos, exit_price, reason, pnl_total, pnl_pct):
        """Close position by selling same side at market."""
        try:
            price_arg = {"yes_price": 1} if pos.side == "yes" else {"no_price": 1}
            self.client.create_order(
                ticker=ticker, side=pos.side, action="sell", type="limit",
                count=pos.contracts, **price_arg,
            )
        except Exception as e:
            self.log(f"[TRADE] EXIT FAILED {ticker}: {e}")

        pos.exit_price = exit_price
        pos.exit_reason = reason
        pos.pnl = pnl_total
        pos.pnl_pct = round(pnl_pct, 1)
        self.total_pnl += pnl_total
        self.total_invested += pos.total_cost
        self.trade_count += 1

        hold = round(time.time() - pos.entry_time)
        self.log(f"[TRADE] SELL {pos.contracts}x {ticker} | {reason} | {hold}s | "
                 f"P&L: {pnl_total:+d}c ({pnl_pct:+.1f}%) | Session: {self.total_pnl:+d}c")

        log_trade({
            "action": "close",
            "ticker": ticker, "side": pos.side,
            "entry_price": pos.entry_price, "exit_price": exit_price,
            "contracts": pos.contracts, "total_cost": pos.total_cost,
            "pnl_cents": pnl_total, "pnl_pct": round(pnl_pct, 1),
            "exit_reason": reason, "hold_time": hold,
            "strategy": pos.signal.get("strategy", ""),
        })

        log_event("trade_close", {
            "ticker": ticker, "reason": reason,
            "pnl": pnl_total, "pnl_pct": round(pnl_pct, 1),
            "contracts": pos.contracts, "hold_time": hold,
            "total_pnl": self.total_pnl, "strategy": pos.signal.get("strategy", ""),
        })

    def get_status(self):
        roi = (self.total_pnl / self.total_invested * 100) if self.total_invested > 0 else 0
        return {
            "enabled": self.enabled,
            "open_positions": len(self.positions),
            "total_trades": self.trade_count,
            "total_pnl": self.total_pnl,
            "total_invested": self.total_invested,
            "session_roi_pct": round(roi, 1),
            "positions": {t: p.to_dict() for t, p in self.positions.items()},
        }
