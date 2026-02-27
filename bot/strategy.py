"""Strategy engine for analyzing market data and testing trading approaches.

Strategies tracked:
1. Mean Reversion - Fade blowout leads when model says price should revert
2. Momentum/Runs - Detect scoring runs and trade in run direction before market catches up
3. Live Spread Arbitrage - Compare live spread markets to model fair value
4. Half-time Edge - Trade at halftime when model disagrees with market
5. Gamma Scalping - Trade high-delta situations near end of game
"""
import json
import os
import time
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from bot.model import win_probability, fair_value_cents, delta_per_point, mean_reversion_estimate

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
EST = timezone(timedelta(hours=-5))


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


class StrategySignal:
    """A trading signal from a strategy."""
    def __init__(self, strategy, ticker, side, strength, edge, reason, game_context=None):
        self.ts = time.time()
        self.strategy = strategy
        self.ticker = ticker
        self.side = side          # "yes" or "no"
        self.strength = strength  # 0-10 confidence
        self.edge = edge          # cents of edge
        self.reason = reason
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
            "game_context": self.game_context,
        }


class StrategyEngine:
    def __init__(self):
        self.signals = []                  # All signals generated
        self.price_history = defaultdict(list)  # ticker -> list of price snapshots
        self.game_states = defaultdict(list)    # espn_id -> list of game snapshots
        self.edge_history = defaultdict(list)   # ticker -> list of (ts, model_fv, market_price, edge)
        self.strategy_stats = defaultdict(lambda: {
            "signals": 0,
            "correct": 0,
            "total_edge": 0,
            "outcomes": [],
        })

    def on_price_update(self, ticker, market_data, game, model_fv, edge):
        """Called on every price update. Runs all strategies."""
        ts = time.time()
        price = market_data.get("last_price") or market_data.get("yes_bid") or 50
        bid = market_data.get("yes_bid") or 0
        ask = market_data.get("yes_ask") or 100

        # Track price history
        self.price_history[ticker].append({
            "ts": ts,
            "price": price,
            "bid": bid,
            "ask": ask,
            "volume": market_data.get("volume", 0),
            "model_fv": model_fv,
            "edge": edge,
        })

        # Track game state
        espn_id = game.get("espn_id", "")
        self.game_states[espn_id].append(game)

        # Track edge over time
        self.edge_history[ticker].append((ts, model_fv, price, edge))

        # Run strategies
        game_ctx = {
            "name": game.get("name", ""),
            "score": f"{game.get('away_score', 0)}-{game.get('home_score', 0)}",
            "lead": game.get("lead", 0),
            "minutes_remaining": game.get("minutes_remaining", 40),
            "period": game.get("period", 1),
        }

        self._check_mean_reversion(ticker, market_data, game, model_fv, edge, game_ctx)
        self._check_momentum(ticker, market_data, game, model_fv, edge, game_ctx)
        self._check_halftime_edge(ticker, market_data, game, model_fv, edge, game_ctx)
        self._check_gamma_scalp(ticker, market_data, game, model_fv, edge, game_ctx)
        self._check_spread_value(ticker, market_data, game, model_fv, edge, game_ctx)

    def _check_mean_reversion(self, ticker, mkt, game, fv, edge, ctx):
        """Strategy 1: Fade extreme leads that should revert."""
        lead = game.get("lead", 0)
        mins = game.get("minutes_remaining", 40)

        if mins < 5 or mins > 35:
            return

        reversion = mean_reversion_estimate(lead, 0, mins)

        # Signal when lead is extreme and market hasn't priced in reversion
        if abs(lead) >= 10 and abs(edge) >= 4:
            # Fade the leader - buy the underdog
            side = "no" if edge > 0 else "yes"
            if lead > 0 and edge < -4:
                side = "no"  # Home team leads too much, buy NO
            elif lead < 0 and edge > 4:
                side = "yes"  # Away team leads, market underprices home

            strength = min(10, int(abs(edge) / 2))
            signal = StrategySignal(
                strategy="mean_reversion",
                ticker=ticker,
                side=side,
                strength=strength,
                edge=abs(edge),
                reason=f"Lead {lead:+d}, reversion est {reversion:+.1f}pts, edge {edge:+d}c",
                game_context=ctx,
            )
            self._emit_signal(signal)

    def _check_momentum(self, ticker, mkt, game, fv, edge, ctx):
        """Strategy 2: Trade with scoring runs before market catches up."""
        espn_id = game.get("espn_id", "")
        history = self.game_states.get(espn_id, [])

        if len(history) < 4:
            return

        # Check score changes over last few snapshots
        recent = history[-4:]
        home_delta = recent[-1].get("home_score", 0) - recent[0].get("home_score", 0)
        away_delta = recent[-1].get("away_score", 0) - recent[0].get("away_score", 0)
        run = home_delta - away_delta  # Positive = home on a run

        if abs(run) >= 6:
            # Significant run detected
            price = mkt.get("last_price") or 50
            # If home is on a run and market hasn't moved enough
            if run > 0 and edge > 2:
                signal = StrategySignal(
                    strategy="momentum",
                    ticker=ticker,
                    side="yes",
                    strength=min(8, abs(run)),
                    edge=edge,
                    reason=f"Home run {run:+d}pts in {len(recent)} snaps, market lagging by {edge:+d}c",
                    game_context=ctx,
                )
                self._emit_signal(signal)
            elif run < 0 and edge < -2:
                signal = StrategySignal(
                    strategy="momentum",
                    ticker=ticker,
                    side="no",
                    strength=min(8, abs(run)),
                    edge=abs(edge),
                    reason=f"Away run {run:+d}pts in {len(recent)} snaps, market lagging by {edge:+d}c",
                    game_context=ctx,
                )
                self._emit_signal(signal)

    def _check_halftime_edge(self, ticker, mkt, game, fv, edge, ctx):
        """Strategy 3: Trade at halftime when model disagrees with market."""
        period = game.get("period", 1)
        mins = game.get("minutes_remaining", 40)

        # Halftime window: period 2 just started or period 1 just ended
        if not (period == 2 and mins >= 19 and mins <= 20.5):
            return

        if abs(edge) < 5:
            return

        side = "yes" if edge > 0 else "no"
        strength = min(10, int(abs(edge) / 2))
        signal = StrategySignal(
            strategy="halftime_edge",
            ticker=ticker,
            side=side,
            strength=strength,
            edge=abs(edge),
            reason=f"Halftime edge: model={fv}c vs market, {abs(edge)}c mispricing",
            game_context=ctx,
        )
        self._emit_signal(signal)

    def _check_gamma_scalp(self, ticker, mkt, game, fv, edge, ctx):
        """Strategy 4: Trade high-delta situations near end of game."""
        mins = game.get("minutes_remaining", 40)
        lead = game.get("lead", 0)

        if mins > 8 or mins < 2:
            return

        delta = delta_per_point(lead, mins)

        # High gamma zone: close game, late in the game
        if abs(delta) >= 0.05 and abs(lead) <= 5 and abs(edge) >= 3:
            side = "yes" if edge > 0 else "no"
            strength = min(10, int(abs(delta) * 100))
            signal = StrategySignal(
                strategy="gamma_scalp",
                ticker=ticker,
                side=side,
                strength=strength,
                edge=abs(edge),
                reason=f"High gamma: delta={delta:.3f}/pt, lead={lead:+d}, {mins:.1f}min left",
                game_context=ctx,
            )
            self._emit_signal(signal)

    def _check_spread_value(self, ticker, mkt, game, fv, edge, ctx):
        """Strategy 5: Wide spread = market maker opportunity."""
        bid = mkt.get("yes_bid") or 0
        ask = mkt.get("yes_ask") or 100
        spread = ask - bid

        if spread < 4 or spread > 20:
            return

        # If model price is between bid and ask, we can improve the book
        if bid < fv < ask and abs(edge) >= 2:
            side = "yes" if fv - bid > ask - fv else "no"
            our_edge = min(fv - bid, ask - fv)
            if our_edge >= 3:
                signal = StrategySignal(
                    strategy="spread_value",
                    ticker=ticker,
                    side=side,
                    strength=min(7, int(our_edge)),
                    edge=our_edge,
                    reason=f"Wide spread {spread}c (bid={bid} ask={ask}), model={fv}c, can improve by {our_edge}c",
                    game_context=ctx,
                )
                self._emit_signal(signal)

    def _emit_signal(self, signal):
        """Record and log a strategy signal."""
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
        """Generate end-of-day analysis report."""
        date_str = datetime.now(EST).strftime("%Y-%m-%d")

        report = {
            "date": date_str,
            "generated_at": time.time(),
            "total_signals": len(self.signals),
            "strategies": {},
            "games_tracked": len(self.game_states),
            "markets_tracked": len(self.price_history),
            "edge_analysis": {},
        }

        # Strategy breakdown
        for name, stats in self.strategy_stats.items():
            report["strategies"][name] = {
                "signals": stats["signals"],
                "avg_edge": round(stats["total_edge"] / max(1, stats["signals"]), 1),
            }

        # Edge analysis - how did model FV compare to market over time?
        for ticker, edges in self.edge_history.items():
            if len(edges) < 5:
                continue
            edges_list = [e[3] for e in edges]
            avg_edge = sum(edges_list) / len(edges_list)
            max_edge = max(edges_list, key=abs)
            report["edge_analysis"][ticker] = {
                "snapshots": len(edges),
                "avg_edge": round(avg_edge, 1),
                "max_edge": round(max_edge, 1),
                "edge_std": round(self._std(edges_list), 1),
            }

        # Price movement analysis
        report["price_movements"] = {}
        for ticker, history in self.price_history.items():
            if len(history) < 3:
                continue
            prices = [h["price"] for h in history]
            volumes = [h["volume"] for h in history]
            report["price_movements"][ticker] = {
                "snapshots": len(history),
                "price_range": [min(prices), max(prices)],
                "price_change": prices[-1] - prices[0],
                "max_volume": max(volumes),
                "avg_model_edge": round(sum(h["edge"] for h in history) / len(history), 1),
            }

        return report

    @staticmethod
    def _std(values):
        if len(values) < 2:
            return 0
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
        return variance ** 0.5
