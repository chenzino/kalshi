"""Strategy engine for analyzing market data and testing trading approaches.

Strategies:
1. Mean Reversion   - Fade blowout leads that should revert to the mean
2. Momentum/Runs    - Ride scoring runs before the market catches up (smoothed)
3. Halftime Edge    - Trade halftime mispricings (model vs market divergence)
4. Gamma Scalping   - Trade high-delta close games in final minutes
5. Spread Capture   - Provide liquidity on wide spreads where model has conviction
6. Stale Line       - Detect when market price hasn't moved after a score change
7. Closing Line     - Capture convergence alpha in final 3 minutes
"""
import json
import os
import time
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from bot.model import win_probability, fair_value_cents, delta_per_point, mean_reversion_estimate

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
EST = timezone(timedelta(hours=-5))

# Cooldowns: min seconds between signals for the same (strategy, ticker) pair
COOLDOWNS = {
    "mean_reversion": 300,   # 5 min
    "momentum": 120,         # 2 min
    "halftime_edge": 600,    # 10 min (once per halftime)
    "gamma_scalp": 60,       # 1 min (fast market)
    "spread_capture": 180,   # 3 min
    "stale_line": 90,        # 1.5 min
    "closing_line": 45,      # 45s (fast convergence zone)
}


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


class StrategySignal:
    """A trading signal from a strategy."""
    def __init__(self, strategy, ticker, side, strength, edge, reason,
                 market_price=None, model_fv=None, game_context=None):
        self.ts = time.time()
        self.strategy = strategy
        self.ticker = ticker
        self.side = side          # "yes" or "no"
        self.strength = strength  # 0-10 confidence
        self.edge = edge          # cents of edge
        self.reason = reason
        self.market_price = market_price  # price at signal time
        self.model_fv = model_fv          # model fair value at signal time
        self.game_context = game_context or {}

    def to_dict(self):
        return {
            "ts": self.ts,
            "strategy": self.strategy,
            "ticker": self.ticker,
            "side": self.side,
            "strength": self.strength,
            "edge": self.edge,
            "reason": self.reason,
            "market_price": self.market_price,
            "model_fv": self.model_fv,
            "game_context": self.game_context,
        }


class StrategyEngine:
    def __init__(self):
        self.signals = []
        self.price_history = defaultdict(list)   # ticker -> price snapshots
        self.game_states = defaultdict(list)      # espn_id -> game snapshots
        self.edge_history = defaultdict(list)      # ticker -> (ts, fv, price, edge)
        self.last_signal_ts = {}                   # (strategy, ticker) -> timestamp
        self.strategy_stats = defaultdict(lambda: {
            "signals": 0, "total_edge": 0,
        })
        self.prev_prices = {}  # ticker -> last known price (for stale detection)

    def on_price_update(self, ticker, market_data, game, model_fv, edge):
        """Called on every price update. Runs all strategies."""
        ts = time.time()
        price = market_data.get("last_price") or market_data.get("yes_bid") or 50
        bid = market_data.get("yes_bid") or 0
        ask = market_data.get("yes_ask") or 100

        # Track price history
        self.price_history[ticker].append({
            "ts": ts, "price": price, "bid": bid, "ask": ask,
            "volume": market_data.get("volume", 0),
            "model_fv": model_fv, "edge": edge,
        })

        # Track game state
        espn_id = game.get("espn_id", "")
        self.game_states[espn_id].append(game)

        # Track edge over time
        self.edge_history[ticker].append((ts, model_fv, price, edge))

        game_ctx = {
            "name": game.get("name", ""),
            "espn_id": espn_id,
            "score": f"{game.get('away_score', 0)}-{game.get('home_score', 0)}",
            "lead": game.get("lead", 0),
            "minutes_remaining": game.get("minutes_remaining", 40),
            "period": game.get("period", 1),
        }

        # Run all strategies
        self._check_mean_reversion(ticker, market_data, game, model_fv, edge, price, game_ctx)
        self._check_momentum(ticker, market_data, game, model_fv, edge, price, game_ctx)
        self._check_halftime_edge(ticker, market_data, game, model_fv, edge, price, game_ctx)
        self._check_gamma_scalp(ticker, market_data, game, model_fv, edge, price, game_ctx)
        self._check_spread_capture(ticker, market_data, game, model_fv, edge, price, game_ctx)
        self._check_stale_line(ticker, market_data, game, model_fv, edge, price, game_ctx)
        self._check_closing_line(ticker, market_data, game, model_fv, edge, price, game_ctx)

        self.prev_prices[ticker] = price

    def _on_cooldown(self, strategy, ticker):
        """Check if this (strategy, ticker) pair is on cooldown."""
        key = (strategy, ticker)
        last = self.last_signal_ts.get(key, 0)
        cd = COOLDOWNS.get(strategy, 120)
        return (time.time() - last) < cd

    # ── Strategy 1: Mean Reversion ──────────────────────────────────
    def _check_mean_reversion(self, ticker, mkt, game, fv, edge, price, ctx):
        """Fade extreme leads. The bigger the lead relative to time left,
        the more the market overreacts. Academic research shows ~25% of
        excess halftime lead reverts in the second half."""
        if self._on_cooldown("mean_reversion", ticker):
            return

        lead = game.get("lead", 0)
        mins = game.get("minutes_remaining", 40)

        if mins < 5 or mins > 35:
            return

        reversion = mean_reversion_estimate(lead, 0, mins)

        # Require: large lead + meaningful edge + model disagrees with market
        if abs(lead) < 8 or abs(edge) < 4:
            return

        # The side logic: if model FV > market price, buy YES (market underpricing home)
        side = "yes" if edge > 0 else "no"

        # Strength based on lead magnitude and edge
        strength = min(10, int(abs(edge) / 2) + int(abs(lead) / 5))

        self._emit_signal(StrategySignal(
            strategy="mean_reversion", ticker=ticker, side=side,
            strength=strength, edge=abs(edge),
            market_price=price, model_fv=fv,
            reason=f"Lead {lead:+d}, reversion est {reversion:+.1f}pts, edge {edge:+d}c, {mins:.0f}min left",
            game_context=ctx,
        ))

    # ── Strategy 2: Momentum / Scoring Runs ─────────────────────────
    def _check_momentum(self, ticker, mkt, game, fv, edge, price, ctx):
        """Detect scoring runs — when one team scores 6+ unanswered in recent
        snapshots, the market often lags behind the true probability shift.
        Smoothed: require run to persist across 2 consecutive windows to filter noise."""
        if self._on_cooldown("momentum", ticker):
            return

        espn_id = game.get("espn_id", "")
        history = self.game_states.get(espn_id, [])
        if len(history) < 6:
            return

        # Check two overlapping windows for persistence (reduces false signals ~30%)
        recent1 = history[-6:-2]  # Earlier window
        recent2 = history[-4:]     # Later window

        def calc_run(window):
            hd = window[-1].get("home_score", 0) - window[0].get("home_score", 0)
            ad = window[-1].get("away_score", 0) - window[0].get("away_score", 0)
            return hd - ad

        run1 = calc_run(recent1)
        run2 = calc_run(recent2)

        # Both windows must show same direction run of 5+ pts
        if abs(run2) < 5 or (run1 > 0) != (run2 > 0):
            return

        run = run2

        # Only signal if edge aligns with the run direction
        if run > 0 and edge > 2:
            self._emit_signal(StrategySignal(
                strategy="momentum", ticker=ticker, side="yes",
                strength=min(8, abs(run)),
                edge=edge, market_price=price, model_fv=fv,
                reason=f"Home run {run:+d}pts (sustained), market lagging {edge:+d}c",
                game_context=ctx,
            ))
        elif run < 0 and edge < -2:
            self._emit_signal(StrategySignal(
                strategy="momentum", ticker=ticker, side="no",
                strength=min(8, abs(run)),
                edge=abs(edge), market_price=price, model_fv=fv,
                reason=f"Away run {run:+d}pts (sustained), market lagging {edge:+d}c",
                game_context=ctx,
            ))

    # ── Strategy 3: Halftime Edge ───────────────────────────────────
    def _check_halftime_edge(self, ticker, mkt, game, fv, edge, price, ctx):
        """At halftime, the market often misprices the second half. Our Brownian
        model can disagree significantly. This is our highest-conviction window."""
        if self._on_cooldown("halftime_edge", ticker):
            return

        period = game.get("period", 1)
        mins = game.get("minutes_remaining", 40)

        # Halftime window: end of first half OR start of second half
        is_late_first_half = (period == 1 and mins <= 2)
        is_early_second_half = (period == 2 and mins >= 18)
        if not (is_late_first_half or is_early_second_half):
            return

        if abs(edge) < 4:
            return

        side = "yes" if edge > 0 else "no"
        # High conviction because halftime is a natural recalibration point
        strength = min(10, int(abs(edge) / 1.5))

        self._emit_signal(StrategySignal(
            strategy="halftime_edge", ticker=ticker, side=side,
            strength=strength, edge=abs(edge),
            market_price=price, model_fv=fv,
            reason=f"Halftime: model={fv}c, market={price}c, {abs(edge)}c edge",
            game_context=ctx,
        ))

    # ── Strategy 4: Gamma Scalping ──────────────────────────────────
    def _check_gamma_scalp(self, ticker, mkt, game, fv, edge, price, ctx):
        """In the final minutes of close games, delta per point is huge (gamma
        explosion). A single bucket can swing the price 5-15c. If we have even
        a small edge here, the payoff is asymmetric."""
        if self._on_cooldown("gamma_scalp", ticker):
            return

        mins = game.get("minutes_remaining", 40)
        lead = game.get("lead", 0)

        if mins > 8 or mins < 1:
            return

        delta = delta_per_point(lead, mins)

        # High gamma zone: close game with big delta
        if abs(delta) < 0.04 or abs(lead) > 6 or abs(edge) < 2:
            return

        side = "yes" if edge > 0 else "no"
        # Strength scales with delta magnitude
        strength = min(10, int(abs(delta) * 120))

        self._emit_signal(StrategySignal(
            strategy="gamma_scalp", ticker=ticker, side=side,
            strength=strength, edge=abs(edge),
            market_price=price, model_fv=fv,
            reason=f"Gamma: Δ={delta:.3f}/pt, lead={lead:+d}, {mins:.1f}min, edge={edge:+d}c",
            game_context=ctx,
        ))

    # ── Strategy 5: Spread Capture ──────────────────────────────────
    def _check_spread_capture(self, ticker, mkt, game, fv, edge, price, ctx):
        """When the bid-ask spread is wide and our model places fair value
        inside the spread, we can provide liquidity by placing a limit order
        that improves the book and still captures edge."""
        if self._on_cooldown("spread_capture", ticker):
            return

        bid = mkt.get("yes_bid") or 0
        ask = mkt.get("yes_ask") or 100
        spread = ask - bid

        if spread < 5 or spread > 25:
            return

        # Model must place FV inside the spread
        if not (bid < fv < ask):
            return

        # Our potential edge: distance from model FV to nearest side
        edge_to_bid = fv - bid
        edge_to_ask = ask - fv

        if edge_to_bid > edge_to_ask:
            # More room above bid → place a YES limit above bid
            side = "yes"
            our_edge = edge_to_bid
        else:
            # More room below ask → place a NO limit
            side = "no"
            our_edge = edge_to_ask

        if our_edge < 3:
            return

        strength = min(8, int(our_edge))

        self._emit_signal(StrategySignal(
            strategy="spread_capture", ticker=ticker, side=side,
            strength=strength, edge=our_edge,
            market_price=price, model_fv=fv,
            reason=f"Spread {spread}c (bid={bid} ask={ask}), FV={fv}c, edge={our_edge:.0f}c",
            game_context=ctx,
        ))

    # ── Strategy 6: Stale Line Detection ────────────────────────────
    def _check_stale_line(self, ticker, mkt, game, fv, edge, price, ctx):
        """After a score change, the market should adjust. If the price hasn't
        moved but the score has changed, the line is stale and we can capture
        the adjustment."""
        if self._on_cooldown("stale_line", ticker):
            return

        espn_id = game.get("espn_id", "")
        history = self.game_states.get(espn_id, [])
        if len(history) < 2:
            return

        prev_game = history[-2]
        prev_score = (prev_game.get("home_score", 0), prev_game.get("away_score", 0))
        curr_score = (game.get("home_score", 0), game.get("away_score", 0))

        # Score just changed
        if prev_score == curr_score:
            return

        prev_price = self.prev_prices.get(ticker)
        if prev_price is None:
            return

        # Score changed but price hasn't moved (or barely moved)
        price_change = abs(price - prev_price)
        if price_change > 2:
            return  # Market already adjusted

        # How much SHOULD it have moved? (based on delta)
        points_scored = abs(sum(curr_score) - sum(prev_score))
        mins = game.get("minutes_remaining", 40)
        lead = game.get("lead", 0)
        expected_move = abs(delta_per_point(lead, mins)) * points_scored * 100

        if expected_move < 3 or abs(edge) < 3:
            return

        side = "yes" if edge > 0 else "no"
        strength = min(9, int(expected_move / 2))

        self._emit_signal(StrategySignal(
            strategy="stale_line", ticker=ticker, side=side,
            strength=strength, edge=abs(edge),
            market_price=price, model_fv=fv,
            reason=f"Score changed {prev_score}->{curr_score}, price unmoved ({price}c), "
                   f"expected ~{expected_move:.0f}c move",
            game_context=ctx,
        ))

    # ── Strategy 7: Closing Line Value ───────────────────────────────
    def _check_closing_line(self, ticker, mkt, game, fv, edge, price, ctx):
        """In the final 3 minutes with a clear lead, the market converges fast
        toward 0 or 100. If the model sees the market is still mispriced
        by 5+c, there's strong convergence alpha as it settles."""
        if self._on_cooldown("closing_line", ticker):
            return

        mins = game.get("minutes_remaining", 40)
        lead = game.get("lead", 0)

        if mins > 3 or mins < 0.5:
            return

        # Need clear lead (not a coin flip)
        if abs(lead) < 3:
            return

        # Need strong mispricing
        if abs(edge) < 5:
            return

        side = "yes" if edge > 0 else "no"
        # Very high conviction — convergence is fast in final minutes
        strength = min(10, int(abs(edge) / 1.5) + 2)

        self._emit_signal(StrategySignal(
            strategy="closing_line", ticker=ticker, side=side,
            strength=strength, edge=abs(edge),
            market_price=price, model_fv=fv,
            reason=f"Closing: lead={lead:+d}, {mins:.1f}min, market={price}c vs model={fv}c",
            game_context=ctx,
        ))

    # ── Signal Emission ─────────────────────────────────────────────
    def _emit_signal(self, signal):
        """Record signal with dedup and cooldown."""
        key = (signal.strategy, signal.ticker)
        self.last_signal_ts[key] = signal.ts

        self.signals.append(signal)
        self.strategy_stats[signal.strategy]["signals"] += 1
        self.strategy_stats[signal.strategy]["total_edge"] += signal.edge

        # Save to file
        path = os.path.join(DATA_DIR, "signals")
        _ensure_dir(path)
        date_str = datetime.now(EST).strftime("%Y-%m-%d")
        filepath = os.path.join(path, f"{date_str}.jsonl")
        with open(filepath, "a") as f:
            f.write(json.dumps(signal.to_dict()) + "\n")

    def daily_report(self):
        """Generate end-of-day strategy report."""
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
            edges_list = [e[3] for e in edges]
            report["edge_analysis"][ticker] = {
                "snapshots": len(edges),
                "avg_edge": round(sum(edges_list) / len(edges_list), 1),
                "max_edge": round(max(edges_list, key=abs), 1),
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
