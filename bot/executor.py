"""Trade execution engine for short-term volatility scalping.

Position sizing: target 6% of bankroll per position.
Scales automatically as balance grows. Cheap contracts = more, expensive = fewer.
All P&L measured as % return on capital deployed.

Exit rules (adaptive, learned from past trades):
1. Model exit: edge flipped, get out
2. Take profit: default +15% return (adjusted by learner)
3. Trailing stop: gave back 5% from peak (adjusted by learner)
4. Stop loss: default -10% return (adjusted by learner)
5. Time exit: 5 min max hold (adjusted by learner)
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
TARGET_BANKROLL_PCT = 10    # Target 10% of bankroll per position - aggressive
MIN_ENTRY_PRICE = 25        # Don't buy contracts below 25c (gaps kill you)
MAX_COST_CENTS = 75         # Don't pay more than 75c per contract
MIN_SIGNAL_STRENGTH = 5
MAX_POSITIONS = 5           # Fewer, higher-conviction positions
MIN_EDGE = 6                # Min edge (cents) to enter - need room for fees + spread
MAX_EDGE = 18               # Max edge - beyond this model is wrong, not right
MIN_MINUTES_REMAINING = 8   # No new trades under 8 min left in 2nd half
ORDER_TIMEOUT = 45          # Cancel unfilled after 45s
FILL_CHECK_INTERVAL = 15
TICKER_COOLDOWN = 120       # 2 min between trades on same ticker
GAME_COOLDOWN = 300         # 5 min between trades on same game (stop re-entering after stops)
MAX_LOSS_PER_CONTRACT = 8   # Absolute cent cap on loss per contract

# ── Default Exit Parameters (overridden by adaptive tuner) ────
DEFAULT_EXITS = {
    "stop_loss_pct": 15,        # -15% of capital (wider to survive noise)
    "take_profit_pct": 15,      # +15% of capital deployed
    "trailing_stop_pct": 5,     # Give back at most 5% from peak
    "trailing_activate_pct": 8, # Trailing stop kicks in at +8%
    "time_exit": 300,           # 5 min max hold
    "edge_exit": -1,            # Exit when model edge flips to -1c
}

# Series whitelist - ONLY men's full-game moneyline
ALLOWED_SERIES = "KXNCAAMBGAME"

TUNED_PARAMS_FILE = os.path.join(DATA_DIR, "learning", "tuned_exits.json")


class Position:
    """Tracks a single position from entry to exit with full context."""
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

        # Rich context for learning
        ctx = signal.get("game_context", {})
        self.entry_context = {
            "strategy": signal.get("strategy", ""),
            "edge": signal.get("edge", 0),
            "strength": signal.get("strength", 0),
            "model_fv": signal.get("model_fv", 50),
            "market_price": signal.get("market_price", 50),
            "minutes_remaining": ctx.get("minutes_remaining", 40),
            "period": ctx.get("period", 1),
            "lead": ctx.get("lead", 0),
            "score": ctx.get("score", "0-0"),
            "game": ctx.get("name", ""),
        }
        self.edge_trajectory = []  # list of (ts, edge, model_fv, market_price)
        self.pnl_trajectory = []   # list of (ts, pnl_pct)

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


def _calc_contracts(price_cents, target_cents):
    """Calculate how many contracts to buy for consistent position sizing.
    Cheap = more contracts, expensive = 1. Cap at 3."""
    if price_cents <= 0 or target_cents <= 0:
        return 1
    n = max(1, round(target_cents / price_cents))
    return min(n, 5)  # Up to 5 contracts for cheap ones


def _load_tuned_exits():
    """Load adaptive exit parameters from disk, or use defaults."""
    try:
        if os.path.exists(TUNED_PARAMS_FILE):
            with open(TUNED_PARAMS_FILE) as f:
                tuned = json.load(f)
            # Merge with defaults (in case new params added)
            merged = {**DEFAULT_EXITS, **tuned.get("exits", {})}
            return merged
    except Exception:
        pass
    return dict(DEFAULT_EXITS)


def _save_tuned_exits(exits, reason=""):
    """Save tuned exit parameters to disk."""
    os.makedirs(os.path.dirname(TUNED_PARAMS_FILE), exist_ok=True)
    with open(TUNED_PARAMS_FILE, "w") as f:
        json.dump({"exits": exits, "updated": time.time(), "reason": reason}, f, indent=2)


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
        self._bankroll = 0       # cents, refreshed periodically
        self._bankroll_ts = 0
        self._target_position = 60  # cents, computed from bankroll
        self.exits = _load_tuned_exits()
        self.closed_trades = []  # in-memory list for adaptive tuning
        self._load_existing_positions()
        self._refresh_bankroll()

    def _refresh_bankroll(self):
        """Fetch balance from Kalshi and compute target position size."""
        if not self.client:
            return
        now = time.time()
        if now - self._bankroll_ts < 60:  # Cache for 60s
            return
        try:
            bal = self.client.get_balance()
            self._bankroll = bal.get("balance", 0)  # cents
            self._bankroll_ts = now
            # Target position = 6% of bankroll
            self._target_position = max(30, round(self._bankroll * TARGET_BANKROLL_PCT / 100))
            # Don't exceed 150c per position even with large bankroll
            self._target_position = min(self._target_position, 150)
        except Exception:
            pass

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

        # Edge sanity: too-large edge means model is wrong, not a real opportunity
        if edge > MAX_EDGE:
            return

        # Time cutoff: no new entries under 8 min remaining
        ctx = signal.get("game_context", {})
        mins_left = ctx.get("minutes_remaining", 40)
        if mins_left < MIN_MINUTES_REMAINING:
            return

        # Strict series check - ONLY men's full-game moneyline
        if not ticker.startswith(ALLOWED_SERIES):
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

        # Price range: avoid extremes where a single tick = huge % move
        if market_price is None or market_price < MIN_ENTRY_PRICE or market_price > (100 - MIN_ENTRY_PRICE):
            return

        # Calculate per-contract cost
        if side == "yes":
            unit_price = min(market_price + 1, MAX_COST_CENTS)
        else:
            unit_price = min(100 - market_price + 1, MAX_COST_CENTS)

        if unit_price > MAX_COST_CENTS or unit_price < MIN_ENTRY_PRICE:
            return

        # Fee check (~1c each way conservative)
        if edge - 2 < 1:
            return

        # Bankroll-based position sizing
        self._refresh_bankroll()
        contracts = _calc_contracts(unit_price, self._target_position)

        # Don't risk more than total exposure limit (60% of bankroll)
        current_exposure = sum(p.total_cost for p in self.positions.values())
        new_exposure = unit_price * contracts
        max_exposure = self._bankroll * 0.60 if self._bankroll > 0 else 500
        if current_exposure + new_exposure > max_exposure:
            return

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

            ctx = signal.get("game_context", {})
            log_trade({
                "action": "open",
                "ticker": ticker, "side": side, "price": price,
                "contracts": contracts, "total_cost": total,
                "order_id": order_id,
                "strategy": signal.get("strategy", ""),
                "edge": signal.get("edge", 0),
                "strength": signal.get("strength", 0),
                "model_fv": signal.get("model_fv", 0),
                "market_price": signal.get("market_price", 0),
                "game": ctx.get("name", ""),
                "minutes_remaining": ctx.get("minutes_remaining", 0),
                "period": ctx.get("period", 0),
                "lead": ctx.get("lead", 0),
                "score": ctx.get("score", ""),
                "bankroll": self._bankroll,
                "target_position": self._target_position,
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
        """Update model fair value for open position. Tracks trajectory."""
        pos = self.positions.get(ticker)
        if not pos or not pos.filled:
            return

        pos.last_model_fv = model_fv
        pos.edge_updates += 1

        if pos.side == "yes":
            pos.last_edge = model_fv - market_price
            current = market_price
        else:
            pos.last_edge = market_price - model_fv
            current = 100 - market_price

        # Track trajectories for learning
        now = time.time()
        pos.edge_trajectory.append((now, pos.last_edge, model_fv, market_price))
        pnl_pct = ((current - pos.entry_price) / pos.entry_price * 100) if pos.entry_price > 0 else 0
        pos.pnl_trajectory.append((now, round(pnl_pct, 1)))

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

            # ── EXIT RULES (all %-based, adaptive params) ──
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

            # Use adaptive exit params
            ex = self.exits

            # 1. MODEL EXIT: edge has flipped
            if pos.edge_updates >= 2 and pos.last_edge <= ex["edge_exit"]:
                self._exit_position(ticker, pos, current, "model_exit", pnl_total, pnl_pct)
                to_close.append(ticker)
            # 2. TAKE PROFIT
            elif pnl_pct >= ex["take_profit_pct"]:
                self._exit_position(ticker, pos, current, "take_profit", pnl_total, pnl_pct)
                to_close.append(ticker)
            # 3. TRAILING STOP
            elif pos.peak_pnl_pct >= ex["trailing_activate_pct"] and pnl_pct <= pos.peak_pnl_pct - ex["trailing_stop_pct"]:
                self._exit_position(ticker, pos, current, "trailing_stop", pnl_total, pnl_pct)
                to_close.append(ticker)
            # 4. STOP LOSS (% or absolute cent cap, whichever triggers first)
            elif pnl_pct <= -ex["stop_loss_pct"] or pnl_per <= -MAX_LOSS_PER_CONTRACT:
                self._exit_position(ticker, pos, current, "stop_loss", pnl_total, pnl_pct)
                to_close.append(ticker)
            # 5. TIME EXIT
            elif age > ex["time_exit"]:
                self._exit_position(ticker, pos, current, "time_exit", pnl_total, pnl_pct)
                to_close.append(ticker)

        for t in to_close:
            game_event = _extract_game_event(t)
            pos = self.positions[t]
            self.recent_tickers[t] = now
            # After a stop loss, cool off the entire game for 10 min
            if pos.exit_reason == "stop_loss":
                self.recent_events[game_event] = now + 300  # Extra 5 min on top of GAME_COOLDOWN
            else:
                self.recent_events[game_event] = now
            del self.positions[t]

    def _exit_position(self, ticker, pos, exit_price, reason, pnl_total, pnl_pct):
        """Close position by selling same side at market. Records full context."""
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
        bankroll_pct = round(self._target_position / max(1, self._bankroll) * 100, 1) if self._bankroll else 0
        self.log(f"[TRADE] SELL {pos.contracts}x {ticker} | {reason} | {hold}s | "
                 f"P&L: {pnl_total:+d}c ({pnl_pct:+.1f}%) | Session: {self.total_pnl:+d}c")

        # Rich trade context for learning
        trade_record = {
            "action": "close",
            "ticker": ticker, "side": pos.side,
            "entry_price": pos.entry_price, "exit_price": exit_price,
            "contracts": pos.contracts, "total_cost": pos.total_cost,
            "pnl_cents": pnl_total, "pnl_pct": round(pnl_pct, 1),
            "exit_reason": reason, "hold_time": hold,
            "peak_pnl_pct": round(pos.peak_pnl_pct, 1),
            "strategy": pos.signal.get("strategy", ""),
            "bankroll": self._bankroll,
            "bankroll_pct": bankroll_pct,
            "entry_context": pos.entry_context,
            "exit_params": dict(self.exits),
            "edge_at_exit": pos.last_edge,
            "edge_updates": pos.edge_updates,
            "edge_trajectory": pos.edge_trajectory[-10:],  # Last 10 readings
            "pnl_trajectory": pos.pnl_trajectory[-10:],
        }

        log_trade(trade_record)
        self.closed_trades.append(trade_record)

        log_event("trade_close", {
            "ticker": ticker, "reason": reason,
            "pnl": pnl_total, "pnl_pct": round(pnl_pct, 1),
            "contracts": pos.contracts, "hold_time": hold,
            "total_pnl": self.total_pnl, "strategy": pos.signal.get("strategy", ""),
        })

        # Run adaptive tuning every 10 closed trades
        if len(self.closed_trades) >= 10 and len(self.closed_trades) % 5 == 0:
            self._tune_exits()

    def _tune_exits(self):
        """Analyze recent closed trades and adjust exit parameters.

        Rules:
        - Stop losses: if >60% of stops would have recovered to breakeven
          within 2 min (from pnl_trajectory), widen stop by 2%
        - Take profits: if avg peak after TP is >5% higher, raise TP by 3%
        - Time exits: if avg pnl of time exits is positive, extend by 60s;
          if negative, shorten by 30s
        - Trailing: if trailing stops avg pnl > TP avg pnl, tighten activation
        """
        trades = self.closed_trades[-30:]  # Look at last 30 trades
        if len(trades) < 10:
            return

        by_reason = {}
        for t in trades:
            r = t.get("exit_reason", "unknown")
            if r not in by_reason:
                by_reason[r] = []
            by_reason[r].append(t)

        changed = False
        new_exits = dict(self.exits)

        # Analyze stop losses
        stops = by_reason.get("stop_loss", [])
        if len(stops) >= 3:
            avg_stop_pnl = sum(t["pnl_pct"] for t in stops) / len(stops)
            # Check if stops had trajectory data showing recovery
            recovered = 0
            for t in stops:
                traj = t.get("pnl_trajectory", [])
                if len(traj) >= 2:
                    # Did price recover after hitting stop level?
                    min_pnl = min(p[1] for p in traj)
                    last_pnl = traj[-1][1]
                    if last_pnl > min_pnl + 3:
                        recovered += 1
            recovery_rate = recovered / len(stops)
            if recovery_rate > 0.5 and new_exits["stop_loss_pct"] < 20:
                new_exits["stop_loss_pct"] = min(20, new_exits["stop_loss_pct"] + 2)
                changed = True
                self.log(f"[TUNE] Widened stop loss to -{new_exits['stop_loss_pct']}% "
                         f"({recovery_rate:.0%} of stops recovered)")

        # Analyze take profits - are we leaving money on the table?
        tps = by_reason.get("take_profit", [])
        if len(tps) >= 3:
            avg_peak = sum(t.get("peak_pnl_pct", 0) for t in tps) / len(tps)
            avg_exit = sum(t["pnl_pct"] for t in tps) / len(tps)
            if avg_peak > avg_exit + 5 and new_exits["take_profit_pct"] < 30:
                new_exits["take_profit_pct"] = min(30, new_exits["take_profit_pct"] + 3)
                changed = True
                self.log(f"[TUNE] Raised take profit to +{new_exits['take_profit_pct']}% "
                         f"(avg peak was {avg_peak:.1f}% vs exit {avg_exit:.1f}%)")

        # Analyze time exits
        time_exits = by_reason.get("time_exit", [])
        if len(time_exits) >= 3:
            avg_pnl = sum(t["pnl_pct"] for t in time_exits) / len(time_exits)
            if avg_pnl > 2 and new_exits["time_exit"] < 600:
                new_exits["time_exit"] = min(600, new_exits["time_exit"] + 60)
                changed = True
                self.log(f"[TUNE] Extended time exit to {new_exits['time_exit']}s "
                         f"(time exits avg +{avg_pnl:.1f}%)")
            elif avg_pnl < -3 and new_exits["time_exit"] > 120:
                new_exits["time_exit"] = max(120, new_exits["time_exit"] - 30)
                changed = True
                self.log(f"[TUNE] Shortened time exit to {new_exits['time_exit']}s "
                         f"(time exits avg {avg_pnl:.1f}%)")

        # Analyze trailing stops vs take profits
        trails = by_reason.get("trailing_stop", [])
        if len(trails) >= 2 and len(tps) >= 2:
            avg_trail_pnl = sum(t["pnl_pct"] for t in trails) / len(trails)
            avg_tp_pnl = sum(t["pnl_pct"] for t in tps) / len(tps)
            if avg_trail_pnl > avg_tp_pnl and new_exits["trailing_activate_pct"] > 4:
                new_exits["trailing_activate_pct"] = max(4, new_exits["trailing_activate_pct"] - 1)
                changed = True
                self.log(f"[TUNE] Tightened trailing activation to +{new_exits['trailing_activate_pct']}% "
                         f"(trailing avg {avg_trail_pnl:.1f}% > TP avg {avg_tp_pnl:.1f}%)")

        if changed:
            self.exits = new_exits
            _save_tuned_exits(new_exits, f"auto-tuned after {len(trades)} trades")
            log_event("exit_tuned", new_exits)

    def get_status(self):
        roi = (self.total_pnl / self.total_invested * 100) if self.total_invested > 0 else 0
        return {
            "enabled": self.enabled,
            "open_positions": len(self.positions),
            "total_trades": self.trade_count,
            "total_pnl": self.total_pnl,
            "total_invested": self.total_invested,
            "session_roi_pct": round(roi, 1),
            "bankroll": self._bankroll,
            "target_position": self._target_position,
            "bankroll_pct_per_trade": round(self._target_position / max(1, self._bankroll) * 100, 1) if self._bankroll else 0,
            "exit_params": dict(self.exits),
            "positions": {t: p.to_dict() for t, p in self.positions.items()},
        }
