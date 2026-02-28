"""Strategy engine for short-term volatility scalping on Kalshi moneyline.

Core idea: model says fair value is X, market says Y. If |X-Y| is big enough, trade.
The model can favor EITHER side - favorite or underdog. We trade whatever has edge.

Strategies:
1. Edge Scalp       - Pure model vs market mispricing (works for any team)
2. Momentum         - Ride scoring runs before market catches up
3. Halftime Edge    - Trade halftime mispricings
4. Gamma Scalp      - High-delta close games in final minutes
5. Stale Line       - Market hasn't moved after score change
6. Closing Line     - Convergence alpha in final 3 minutes
"""
import json
import os
import time
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from bot.model import win_probability, fair_value_cents, delta_per_point, mean_reversion_estimate

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
EST = timezone(timedelta(hours=-5))

# Cooldowns: seconds between signals for same (strategy, ticker) pair
COOLDOWNS = {
    "edge_scalp": 90,        # 1.5 min - core strategy, trade often
    "momentum": 60,          # 1 min
    "halftime_edge": 180,    # 3 min
    "gamma_scalp": 45,       # 45s (fast market)
    "stale_line": 45,        # 45s
    "closing_line": 30,      # 30s (convergence zone)
}


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


class StrategySignal:
    """A trading signal."""
    def __init__(self, strategy, ticker, side, strength, edge, reason,
                 market_price=None, model_fv=None, game_context=None):
        self.ts = time.time()
        self.strategy = strategy
        self.ticker = ticker
        self.side = side          # "yes" or "no"
        self.strength = strength  # 0-10 confidence
        self.edge = edge          # cents of edge
        self.reason = reason
        self.market_price = market_price
        self.model_fv = model_fv
        self.game_context = game_context or {}

    def to_dict(self):
        return {
            "ts": self.ts, "strategy": self.strategy,
            "ticker": self.ticker, "side": self.side,
            "strength": self.strength, "edge": self.edge,
            "reason": self.reason, "market_price": self.market_price,
            "model_fv": self.model_fv, "game_context": self.game_context,
        }


class StrategyEngine:
    def __init__(self):
        self.signals = []
        self.price_history = defaultdict(list)
        self.game_states = defaultdict(list)
        self.edge_history = defaultdict(list)
        self.last_signal_ts = {}
        self.strategy_stats = defaultdict(lambda: {"signals": 0, "total_edge": 0})
        self.prev_prices = {}

    def on_price_update(self, ticker, market_data, game, model_fv, edge):
        """Called every cycle per market. Runs all strategies."""
        ts = time.time()
        price = market_data.get("last_price") or market_data.get("yes_bid") or 50
        bid = market_data.get("yes_bid") or 0
        ask = market_data.get("yes_ask") or 100

        self.price_history[ticker].append({
            "ts": ts, "price": price, "bid": bid, "ask": ask,
            "volume": market_data.get("volume", 0),
            "model_fv": model_fv, "edge": edge,
        })

        espn_id = game.get("espn_id", "")
        self.game_states[espn_id].append(game)
        self.edge_history[ticker].append((ts, model_fv, price, edge))

        ctx = {
            "name": game.get("name", ""),
            "espn_id": espn_id,
            "score": f"{game.get('away_score', 0)}-{game.get('home_score', 0)}",
            "lead": game.get("lead", 0),
            "minutes_remaining": game.get("minutes_remaining", 40),
            "period": game.get("period", 1),
        }

        # Run all strategies
        self._check_edge_scalp(ticker, market_data, game, model_fv, edge, price, ctx)
        self._check_momentum(ticker, market_data, game, model_fv, edge, price, ctx)
        self._check_halftime_edge(ticker, market_data, game, model_fv, edge, price, ctx)
        self._check_gamma_scalp(ticker, market_data, game, model_fv, edge, price, ctx)
        self._check_stale_line(ticker, market_data, game, model_fv, edge, price, ctx)
        self._check_closing_line(ticker, market_data, game, model_fv, edge, price, ctx)

        self.prev_prices[ticker] = price

    def _on_cooldown(self, strategy, ticker):
        key = (strategy, ticker)
        last = self.last_signal_ts.get(key, 0)
        cd = COOLDOWNS.get(strategy, 120)
        return (time.time() - last) < cd

    # ── Strategy 1: Edge Scalp (replaces mean_reversion) ─────────
    def _check_edge_scalp(self, ticker, mkt, game, fv, edge, price, ctx):
        """Pure model edge. If model says this market is mispriced by 4+c,
        trade it. Works for EITHER side - favorites or underdogs.
        This is the bread-and-butter: model is smarter than market."""
        if self._on_cooldown("edge_scalp", ticker):
            return

        mins = game.get("minutes_remaining", 40)
        if mins < 2 or mins > 38:  # Skip very end (closing_line handles) and very start
            return

        # Skip games with huge pregame spreads - model unreliable there
        spread = game.get("pregame_spread", 0)
        if abs(spread) > 8:
            return

        if abs(edge) < 4 or abs(edge) > 20:
            return  # Skip tiny edges AND suspiciously large ones (model error)

        # Need price history to confirm edge is persistent (not just noise)
        # Require at least 3 readings to avoid dumping on startup
        history = self.edge_history.get(ticker, [])
        if len(history) < 3:
            return  # Wait for warmup
        recent_edges = [h[3] for h in history[-3:]]
        # Edge should be consistently in same direction
        if not all(e > 0 for e in recent_edges) and not all(e < 0 for e in recent_edges):
            return

        side = "yes" if edge > 0 else "no"
        strength = min(10, int(abs(edge) / 2) + 3)

        self._emit_signal(StrategySignal(
            strategy="edge_scalp", ticker=ticker, side=side,
            strength=strength, edge=abs(edge),
            market_price=price, model_fv=fv,
            reason=f"Model {fv}c vs market {price}c = {edge:+d}c edge, {mins:.0f}min left",
            game_context=ctx,
        ))

    # ── Strategy 2: Momentum / Scoring Runs ──────────────────────
    def _check_momentum(self, ticker, mkt, game, fv, edge, price, ctx):
        """Scoring runs - market lags behind reality. Works for favorite
        pulling away OR underdog making a run."""
        if self._on_cooldown("momentum", ticker):
            return

        espn_id = game.get("espn_id", "")
        history = self.game_states.get(espn_id, [])
        if len(history) < 4:
            return

        recent = history[-4:]
        home_run = recent[-1].get("home_score", 0) - recent[0].get("home_score", 0)
        away_run = recent[-1].get("away_score", 0) - recent[0].get("away_score", 0)
        net_run = home_run - away_run  # positive = home outscoring

        if abs(net_run) < 5:
            return

        # Edge must align with run direction
        if net_run > 0 and edge > 2:
            side = "yes"
        elif net_run < 0 and edge < -2:
            side = "no"
        else:
            return

        strength = min(9, int(abs(net_run) / 2) + int(abs(edge) / 3))

        self._emit_signal(StrategySignal(
            strategy="momentum", ticker=ticker, side=side,
            strength=strength, edge=abs(edge),
            market_price=price, model_fv=fv,
            reason=f"Run {net_run:+d}pts, market lagging {edge:+d}c",
            game_context=ctx,
        ))

    # ── Strategy 3: Halftime Edge ────────────────────────────────
    def _check_halftime_edge(self, ticker, mkt, game, fv, edge, price, ctx):
        """Halftime is a recalibration point. Market often overweights
        1st half performance. Model disagrees = high conviction trade."""
        if self._on_cooldown("halftime_edge", ticker):
            return

        period = game.get("period", 1)
        mins = game.get("minutes_remaining", 40)

        is_halftime = (period == 1 and mins <= 2) or (period == 2 and mins >= 18)
        if not is_halftime:
            return

        # Skip big spreads - model unreliable, halftime_edge was -16c tonight on these
        spread = game.get("pregame_spread", 0)
        if abs(spread) > 8:
            return

        if abs(edge) < 4 or abs(edge) > 15:
            return  # Cap at 15c - larger is model error

        side = "yes" if edge > 0 else "no"
        strength = min(10, int(abs(edge) / 1.5))

        self._emit_signal(StrategySignal(
            strategy="halftime_edge", ticker=ticker, side=side,
            strength=strength, edge=abs(edge),
            market_price=price, model_fv=fv,
            reason=f"Halftime: model={fv}c vs market={price}c, {abs(edge)}c edge",
            game_context=ctx,
        ))

    # ── Strategy 4: Gamma Scalp ──────────────────────────────────
    def _check_gamma_scalp(self, ticker, mkt, game, fv, edge, price, ctx):
        """Final minutes of close games: 1 basket = 5-15c price swing.
        Small edge + high delta = asymmetric payoff."""
        if self._on_cooldown("gamma_scalp", ticker):
            return

        mins = game.get("minutes_remaining", 40)
        lead = game.get("lead", 0)

        if mins > 8 or mins < 1:
            return

        delta = delta_per_point(lead, mins)

        if abs(delta) < 0.04 or abs(lead) > 8 or abs(edge) < 3 or abs(edge) > 15:
            return

        side = "yes" if edge > 0 else "no"
        strength = min(10, int(abs(delta) * 100) + int(abs(edge) / 2))

        self._emit_signal(StrategySignal(
            strategy="gamma_scalp", ticker=ticker, side=side,
            strength=strength, edge=abs(edge),
            market_price=price, model_fv=fv,
            reason=f"Gamma: delta={delta:.3f}/pt, lead={lead:+d}, {mins:.1f}min, edge={edge:+d}c",
            game_context=ctx,
        ))

    # ── Strategy 5: Stale Line ───────────────────────────────────
    def _check_stale_line(self, ticker, mkt, game, fv, edge, price, ctx):
        """Score changed but market price didn't move. Free money."""
        if self._on_cooldown("stale_line", ticker):
            return

        espn_id = game.get("espn_id", "")
        history = self.game_states.get(espn_id, [])
        if len(history) < 2:
            return

        prev = history[-2]
        prev_total = prev.get("home_score", 0) + prev.get("away_score", 0)
        curr_total = game.get("home_score", 0) + game.get("away_score", 0)

        if curr_total == prev_total:
            return  # No score change

        prev_price = self.prev_prices.get(ticker)
        if prev_price is None:
            return

        if abs(price - prev_price) > 2:
            return  # Market already moved

        mins = game.get("minutes_remaining", 40)
        lead = game.get("lead", 0)
        expected_move = abs(delta_per_point(lead, mins)) * abs(curr_total - prev_total) * 100

        if expected_move < 3 or abs(edge) < 3:
            return

        side = "yes" if edge > 0 else "no"
        strength = min(9, int(expected_move / 2) + 2)

        self._emit_signal(StrategySignal(
            strategy="stale_line", ticker=ticker, side=side,
            strength=strength, edge=abs(edge),
            market_price=price, model_fv=fv,
            reason=f"Score +{abs(curr_total-prev_total)}pts, price stuck at {price}c, expected ~{expected_move:.0f}c move",
            game_context=ctx,
        ))

    # ── Strategy 6: Closing Line ─────────────────────────────────
    def _check_closing_line(self, ticker, mkt, game, fv, edge, price, ctx):
        """Final 3 min with a lead: market converges fast to 0/100.
        If still mispriced by 5+c, strong convergence alpha."""
        if self._on_cooldown("closing_line", ticker):
            return

        mins = game.get("minutes_remaining", 40)
        lead = game.get("lead", 0)

        if mins > 3 or mins < 0.5 or abs(lead) < 3 or abs(edge) < 5:
            return

        side = "yes" if edge > 0 else "no"
        strength = min(10, int(abs(edge) / 1.5) + 2)

        self._emit_signal(StrategySignal(
            strategy="closing_line", ticker=ticker, side=side,
            strength=strength, edge=abs(edge),
            market_price=price, model_fv=fv,
            reason=f"Closing: lead={lead:+d}, {mins:.1f}min, model={fv}c vs market={price}c",
            game_context=ctx,
        ))

    # ── Signal Emission ──────────────────────────────────────────
    def _emit_signal(self, signal):
        key = (signal.strategy, signal.ticker)
        self.last_signal_ts[key] = signal.ts

        self.signals.append(signal)
        self.strategy_stats[signal.strategy]["signals"] += 1
        self.strategy_stats[signal.strategy]["total_edge"] += signal.edge

        path = os.path.join(DATA_DIR, "signals")
        _ensure_dir(path)
        date_str = datetime.now(EST).strftime("%Y-%m-%d")
        filepath = os.path.join(path, f"{date_str}.jsonl")
        with open(filepath, "a") as f:
            f.write(json.dumps(signal.to_dict()) + "\n")

    def daily_report(self):
        date_str = datetime.now(EST).strftime("%Y-%m-%d")
        report = {
            "date": date_str,
            "generated_at": time.time(),
            "total_signals": len(self.signals),
            "strategies": {},
            "games_tracked": len(self.game_states),
            "markets_tracked": len(self.price_history),
            "edge_analysis": {},
            "price_movements": {},
        }

        for name, stats in self.strategy_stats.items():
            report["strategies"][name] = {
                "signals": stats["signals"],
                "avg_edge": round(stats["total_edge"] / max(1, stats["signals"]), 1),
            }

        for ticker, edges in self.edge_history.items():
            if len(edges) < 5:
                continue
            el = [e[3] for e in edges]
            report["edge_analysis"][ticker] = {
                "snapshots": len(edges),
                "avg_edge": round(sum(el) / len(el), 1),
                "max_edge": round(max(el, key=abs), 1),
            }

        for ticker, history in self.price_history.items():
            if len(history) < 3:
                continue
            prices = [h["price"] for h in history]
            report["price_movements"][ticker] = {
                "snapshots": len(history),
                "price_range": [min(prices), max(prices)],
                "price_change": prices[-1] - prices[0],
            }

        return report
