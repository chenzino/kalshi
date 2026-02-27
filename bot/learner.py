"""Continuous learning engine.

After each session, analyzes collected data to:
1. Grade signal accuracy - did our signals predict price movement correctly?
2. Calibrate the model - is our sigma/beta correct vs observed data?
3. Score strategies - which ones are actually profitable?
4. Track paper trades - virtual P&L as if we took every signal
5. Tune parameters - adjust thresholds based on what's working

Writes findings to data/learning/ for cross-session memory.
"""
import json
import os
import time
import math
from datetime import datetime, timezone, timedelta
from collections import defaultdict

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
LEARNING_DIR = os.path.join(DATA_DIR, "learning")
EST = timezone(timedelta(hours=-5))


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def _load_jsonl(filepath):
    if not os.path.exists(filepath):
        return []
    entries = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def _load_json(filepath):
    if not os.path.exists(filepath):
        return {}
    with open(filepath) as f:
        return json.load(f)


def _save_json(filepath, data):
    _ensure_dir(os.path.dirname(filepath))
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def load_cumulative_learnings():
    """Load the running learnings file that persists across sessions."""
    path = os.path.join(LEARNING_DIR, "cumulative.json")
    default = {
        "sessions_analyzed": 0,
        "total_signals": 0,
        "model_calibration": {
            "observed_wins_by_bucket": {},  # "50-60" -> {"wins": X, "total": Y}
            "sigma_observations": [],       # list of observed score volatilities
        },
        "strategy_performance": {},  # strategy -> {"signals","correct","profit_cents","avg_edge"}
        "paper_portfolio": {
            "total_pnl_cents": 0,
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "best_trade": 0,
            "worst_trade": 0,
        },
        "parameter_history": [],  # list of {"date", "sigma", "beta", "edge_threshold", ...}
        "market_observations": {
            "avg_spread_by_volume": {},  # volume bucket -> avg spread
            "settlement_accuracy": [],   # list of {"model_fv", "settled_at", "error"}
        },
        "last_updated": None,
    }
    existing = _load_json(path)
    # Merge defaults for any missing keys
    for k, v in default.items():
        if k not in existing:
            existing[k] = v
    return existing


def save_cumulative_learnings(data):
    data["last_updated"] = time.time()
    path = os.path.join(LEARNING_DIR, "cumulative.json")
    _save_json(path, data)


class SessionAnalyzer:
    """Analyze one session's data to extract learnings."""

    def __init__(self, date_str=None):
        self.date = date_str or datetime.now(EST).strftime("%Y-%m-%d")
        self.signals = _load_jsonl(os.path.join(DATA_DIR, "signals", f"{self.date}.jsonl"))
        self.prices = _load_jsonl(os.path.join(DATA_DIR, "prices", f"{self.date}.jsonl"))
        self.games = _load_jsonl(os.path.join(DATA_DIR, "games", f"{self.date}.jsonl"))
        self.snapshots = _load_jsonl(os.path.join(DATA_DIR, "market_snapshots", f"{self.date}.jsonl"))

        # Index prices by ticker -> sorted list
        self.price_index = defaultdict(list)
        for p in self.prices:
            self.price_index[p.get("ticker", "")].append(p)
        for k in self.price_index:
            self.price_index[k].sort(key=lambda x: x.get("ts", 0))

        # Index games by espn_id
        self.game_index = defaultdict(list)
        for g in self.games:
            gid = g.get("espn_id") or g.get("name", "")
            self.game_index[gid].append(g)

    def analyze(self):
        """Run full analysis and return report."""
        report = {
            "date": self.date,
            "data_summary": {
                "signals": len(self.signals),
                "price_snapshots": len(self.prices),
                "game_snapshots": len(self.games),
                "market_snapshots": len(self.snapshots),
                "unique_tickers": len(self.price_index),
                "games_tracked": len(self.game_index),
            },
            "signal_grades": self._grade_signals(),
            "strategy_scores": self._score_strategies(),
            "model_calibration": self._calibrate_model(),
            "paper_trades": self._paper_trade(),
            "market_insights": self._market_insights(),
            "parameter_recommendations": {},
        }

        # Generate parameter recommendations
        report["parameter_recommendations"] = self._recommend_params(report)
        return report

    def _grade_signals(self):
        """Grade each signal: did the price move in our predicted direction?"""
        grades = []
        for sig in self.signals:
            ticker = sig.get("ticker", "")
            sig_ts = sig.get("ts", 0)
            side = sig.get("side", "yes")
            prices = self.price_index.get(ticker, [])

            if not prices:
                grades.append({**sig, "grade": "no_data", "pnl_1m": None, "pnl_5m": None})
                continue

            # Find price at signal time
            entry_price = None
            for p in prices:
                if p["ts"] >= sig_ts:
                    entry_price = p.get("last_price") or p.get("yes_bid")
                    break
            if entry_price is None and prices:
                entry_price = prices[-1].get("last_price") or prices[-1].get("yes_bid")
            if not entry_price:
                grades.append({**sig, "grade": "no_price", "pnl_1m": None, "pnl_5m": None})
                continue

            # Find prices at +1min, +2min, +5min, +10min
            pnls = {}
            for label, offset in [("1m", 60), ("2m", 120), ("5m", 300), ("10m", 600)]:
                target_ts = sig_ts + offset
                future_price = None
                for p in prices:
                    if p["ts"] >= target_ts:
                        future_price = p.get("last_price") or p.get("yes_bid")
                        break
                if future_price is not None:
                    if side == "yes":
                        pnls[label] = future_price - entry_price
                    else:
                        pnls[label] = entry_price - future_price

            # Grade based on 5-minute outcome
            pnl_5m = pnls.get("5m")
            if pnl_5m is not None:
                if pnl_5m > 2:
                    grade = "strong_win"
                elif pnl_5m > 0:
                    grade = "win"
                elif pnl_5m == 0:
                    grade = "flat"
                elif pnl_5m > -2:
                    grade = "loss"
                else:
                    grade = "strong_loss"
            else:
                grade = "incomplete"

            grades.append({
                "ts": sig_ts,
                "strategy": sig.get("strategy"),
                "ticker": ticker,
                "side": side,
                "edge": sig.get("edge", 0),
                "strength": sig.get("strength", 0),
                "entry_price": entry_price,
                "pnl_1m": pnls.get("1m"),
                "pnl_2m": pnls.get("2m"),
                "pnl_5m": pnl_5m,
                "pnl_10m": pnls.get("10m"),
                "grade": grade,
            })

        return grades

    def _score_strategies(self):
        """Aggregate signal grades by strategy."""
        grades = self._grade_signals()
        by_strat = defaultdict(list)
        for g in grades:
            by_strat[g.get("strategy", "unknown")].append(g)

        scores = {}
        for strat, gs in by_strat.items():
            graded = [g for g in gs if g["pnl_5m"] is not None]
            wins = sum(1 for g in graded if (g.get("pnl_5m") or 0) > 0)
            losses = sum(1 for g in graded if (g.get("pnl_5m") or 0) < 0)
            total_pnl = sum(g.get("pnl_5m") or 0 for g in graded)
            avg_edge = sum(g.get("edge", 0) for g in gs) / max(1, len(gs))
            avg_pnl = total_pnl / max(1, len(graded))

            # Sharpe-like ratio: avg_pnl / std(pnl)
            pnls = [g.get("pnl_5m", 0) for g in graded if g.get("pnl_5m") is not None]
            if len(pnls) >= 2:
                mean_pnl = sum(pnls) / len(pnls)
                variance = sum((p - mean_pnl) ** 2 for p in pnls) / (len(pnls) - 1)
                std_pnl = math.sqrt(variance) if variance > 0 else 1
                sharpe = mean_pnl / std_pnl
            else:
                sharpe = 0

            scores[strat] = {
                "total_signals": len(gs),
                "graded": len(graded),
                "wins": wins,
                "losses": losses,
                "win_rate": round(wins / max(1, wins + losses) * 100, 1),
                "total_pnl_5m": round(total_pnl, 1),
                "avg_pnl_5m": round(avg_pnl, 1),
                "avg_edge_claimed": round(avg_edge, 1),
                "sharpe": round(sharpe, 2),
                "grade": "A" if sharpe > 1 else "B" if sharpe > 0.5 else "C" if sharpe > 0 else "D" if sharpe > -0.5 else "F",
            }

        return scores

    def _calibrate_model(self):
        """Check: does our model's predicted win probability match reality?"""
        calibration = {
            "buckets": {},       # FV bucket -> count that settled YES
            "sigma_estimate": None,
            "bias": None,
        }

        # We can't know true settlement from one session easily,
        # but we can track model FV vs market price convergence
        # If model says 70c and market ends at 65c, model was 5c high

        for ticker, history in self.price_index.items():
            if len(history) < 10:
                continue

            # Compare model FV to market across time
            model_fvs = [h.get("model_fv") for h in self.snapshots if h.get("ticker") == ticker and h.get("model_fv")]
            if not model_fvs:
                continue

            # Last known market price as proxy for settlement direction
            last_price = history[-1].get("last_price") or history[-1].get("yes_bid") or 50

            # Average model FV during the game
            avg_model = sum(model_fvs) / len(model_fvs)

            # Bucket by model FV
            bucket = f"{int(avg_model // 10) * 10}-{int(avg_model // 10) * 10 + 10}"
            if bucket not in calibration["buckets"]:
                calibration["buckets"][bucket] = {"count": 0, "sum_final_price": 0}
            calibration["buckets"][bucket]["count"] += 1
            calibration["buckets"][bucket]["sum_final_price"] += last_price

        # Calculate bias
        total_error = 0
        total_count = 0
        for bucket, data in calibration["buckets"].items():
            if data["count"] > 0:
                avg_final = data["sum_final_price"] / data["count"]
                bucket_mid = int(bucket.split("-")[0]) + 5
                total_error += (avg_final - bucket_mid) * data["count"]
                total_count += data["count"]

        if total_count > 0:
            calibration["bias"] = round(total_error / total_count, 2)

        # Estimate sigma from observed score volatility
        score_changes = []
        for gid, snaps in self.game_index.items():
            if len(snaps) < 10:
                continue
            for i in range(1, len(snaps)):
                dt = (snaps[i].get("ts", 0) - snaps[i-1].get("ts", 0)) / 60  # minutes
                if dt < 0.1:
                    continue
                lead_change = abs(snaps[i].get("lead", 0) - snaps[i-1].get("lead", 0))
                if dt > 0:
                    # Normalize to per-40-minutes
                    score_changes.append(lead_change / math.sqrt(dt / 40))

        if len(score_changes) > 10:
            avg_vol = sum(score_changes) / len(score_changes)
            # This gives us an empirical sigma estimate
            calibration["sigma_estimate"] = round(avg_vol * math.sqrt(40), 1)

        return calibration

    def _paper_trade(self):
        """Simulate taking every signal with strength >= 5 and track P&L."""
        trades = []
        total_pnl = 0
        wins = losses = 0

        for sig in self.signals:
            if sig.get("strength", 0) < 5:
                continue

            ticker = sig.get("ticker", "")
            side = sig.get("side", "yes")
            sig_ts = sig.get("ts", 0)
            prices = self.price_index.get(ticker, [])

            if not prices:
                continue

            # Entry: first price after signal
            entry = None
            for p in prices:
                if p["ts"] >= sig_ts:
                    entry = p.get("last_price") or p.get("yes_bid")
                    break
            if not entry:
                continue

            # Exit: price 3 minutes later (or best available)
            exit_price = None
            for p in prices:
                if p["ts"] >= sig_ts + 180:
                    exit_price = p.get("last_price") or p.get("yes_bid")
                    break
            if not exit_price:
                # Use last available
                exit_price = prices[-1].get("last_price") or prices[-1].get("yes_bid")
            if not exit_price:
                continue

            # Calculate P&L
            if side == "yes":
                pnl = exit_price - entry
            else:
                pnl = entry - exit_price

            # Fee estimate (maker rate)
            fee = max(1, round(0.0175 * (entry / 100) * (1 - entry / 100) * 100))
            net_pnl = pnl - fee * 2  # entry + exit fee

            total_pnl += net_pnl
            if net_pnl > 0:
                wins += 1
            elif net_pnl < 0:
                losses += 1

            trades.append({
                "ticker": ticker,
                "strategy": sig.get("strategy"),
                "side": side,
                "entry": entry,
                "exit": exit_price,
                "gross_pnl": pnl,
                "fees": fee * 2,
                "net_pnl": net_pnl,
                "edge_claimed": sig.get("edge", 0),
                "strength": sig.get("strength", 0),
            })

        return {
            "trades": len(trades),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / max(1, wins + losses) * 100, 1),
            "total_gross_pnl": sum(t["gross_pnl"] for t in trades),
            "total_fees": sum(t["fees"] for t in trades),
            "total_net_pnl": total_pnl,
            "avg_pnl_per_trade": round(total_pnl / max(1, len(trades)), 1),
            "best_trade": max((t["net_pnl"] for t in trades), default=0),
            "worst_trade": min((t["net_pnl"] for t in trades), default=0),
            "by_strategy": self._paper_trade_by_strategy(trades),
            "top_trades": sorted(trades, key=lambda t: t["net_pnl"], reverse=True)[:5],
            "worst_trades": sorted(trades, key=lambda t: t["net_pnl"])[:5],
        }

    def _paper_trade_by_strategy(self, trades):
        by_strat = defaultdict(list)
        for t in trades:
            by_strat[t["strategy"]].append(t)

        result = {}
        for strat, ts in by_strat.items():
            pnls = [t["net_pnl"] for t in ts]
            result[strat] = {
                "trades": len(ts),
                "total_pnl": sum(pnls),
                "avg_pnl": round(sum(pnls) / max(1, len(pnls)), 1),
                "win_rate": round(sum(1 for p in pnls if p > 0) / max(1, len(pnls)) * 100, 1),
            }
        return result

    def _market_insights(self):
        """Extract market structure observations."""
        insights = {
            "avg_spreads": {},
            "volume_leaders": [],
            "most_volatile": [],
        }

        for ticker, history in self.price_index.items():
            if len(history) < 5:
                continue
            spreads = [h.get("ask", 100) - h.get("bid", 0) for h in history
                       if h.get("ask") and h.get("bid")]
            prices = [h.get("last_price") or h.get("yes_bid") or 50 for h in history]
            vols = [h.get("volume", 0) for h in history]

            if spreads:
                avg_spread = sum(spreads) / len(spreads)
            else:
                avg_spread = 0

            price_range = max(prices) - min(prices) if prices else 0
            max_vol = max(vols) if vols else 0

            insights["avg_spreads"][ticker] = round(avg_spread, 1)

            if max_vol > 0:
                insights["volume_leaders"].append({"ticker": ticker, "volume": max_vol})
            if price_range >= 10:
                insights["most_volatile"].append({"ticker": ticker, "range": price_range, "snapshots": len(history)})

        insights["volume_leaders"].sort(key=lambda x: x["volume"], reverse=True)
        insights["volume_leaders"] = insights["volume_leaders"][:10]
        insights["most_volatile"].sort(key=lambda x: x["range"], reverse=True)
        insights["most_volatile"] = insights["most_volatile"][:10]

        return insights

    def _recommend_params(self, report):
        """Based on analysis, recommend parameter adjustments."""
        recs = {}

        # Sigma recommendation
        cal = report.get("model_calibration", {})
        if cal.get("sigma_estimate"):
            current_sigma = 11.0
            observed = cal["sigma_estimate"]
            if abs(observed - current_sigma) > 1:
                recs["sigma"] = {
                    "current": current_sigma,
                    "recommended": observed,
                    "reason": f"Observed volatility suggests sigma={observed} vs current {current_sigma}",
                }

        # Edge threshold recommendation
        paper = report.get("paper_trades", {})
        if paper.get("trades", 0) >= 5:
            if paper["win_rate"] > 65:
                recs["edge_threshold"] = {
                    "current": 3,
                    "recommended": 2,
                    "reason": f"High win rate ({paper['win_rate']}%) suggests we can lower threshold",
                }
            elif paper["win_rate"] < 40:
                recs["edge_threshold"] = {
                    "current": 3,
                    "recommended": 5,
                    "reason": f"Low win rate ({paper['win_rate']}%) suggests raising threshold",
                }

        # Strategy-specific recommendations
        strat_scores = report.get("strategy_scores", {})
        for strat, score in strat_scores.items():
            if score.get("graded", 0) >= 3:
                if score["grade"] in ("D", "F"):
                    recs[f"disable_{strat}"] = {
                        "reason": f"{strat} grade={score['grade']}, sharpe={score['sharpe']}, "
                                  f"win_rate={score['win_rate']}% — consider disabling",
                    }
                elif score["grade"] == "A":
                    recs[f"increase_{strat}"] = {
                        "reason": f"{strat} grade={score['grade']}, sharpe={score['sharpe']}, "
                                  f"win_rate={score['win_rate']}% — increase position size",
                    }

        # Model bias
        if cal.get("bias") is not None and abs(cal["bias"]) > 3:
            recs["model_bias"] = {
                "current_bias": cal["bias"],
                "reason": f"Model is biased by {cal['bias']:+.1f}c — adjust drift or sigma",
            }

        return recs


def run_session_analysis(date_str=None):
    """Run analysis for a session and update cumulative learnings."""
    analyzer = SessionAnalyzer(date_str)

    if not analyzer.signals and not analyzer.prices:
        print(f"[LEARNER] No data for {analyzer.date}")
        return None

    print(f"[LEARNER] Analyzing session {analyzer.date}...")
    report = analyzer.analyze()

    # Save session report
    _ensure_dir(os.path.join(LEARNING_DIR, "sessions"))
    _save_json(os.path.join(LEARNING_DIR, "sessions", f"{analyzer.date}.json"), report)

    # Update cumulative learnings
    cum = load_cumulative_learnings()
    cum["sessions_analyzed"] += 1
    cum["total_signals"] += report["data_summary"]["signals"]

    # Update strategy performance
    for strat, score in report.get("strategy_scores", {}).items():
        if strat not in cum["strategy_performance"]:
            cum["strategy_performance"][strat] = {
                "total_signals": 0, "total_graded": 0, "total_wins": 0,
                "total_losses": 0, "cumulative_pnl": 0,
            }
        sp = cum["strategy_performance"][strat]
        sp["total_signals"] += score.get("total_signals", 0)
        sp["total_graded"] += score.get("graded", 0)
        sp["total_wins"] += score.get("wins", 0)
        sp["total_losses"] += score.get("losses", 0)
        sp["cumulative_pnl"] += score.get("total_pnl_5m", 0)
        sp["cumulative_win_rate"] = round(
            sp["total_wins"] / max(1, sp["total_wins"] + sp["total_losses"]) * 100, 1)

    # Update paper portfolio
    paper = report.get("paper_trades", {})
    pp = cum["paper_portfolio"]
    pp["total_pnl_cents"] += paper.get("total_net_pnl", 0)
    pp["trades"] += paper.get("trades", 0)
    pp["wins"] += paper.get("wins", 0)
    pp["losses"] += paper.get("losses", 0)
    pp["best_trade"] = max(pp["best_trade"], paper.get("best_trade", 0))
    pp["worst_trade"] = min(pp["worst_trade"], paper.get("worst_trade", 0))

    # Track parameter recommendations
    recs = report.get("parameter_recommendations", {})
    if recs:
        cum["parameter_history"].append({
            "date": analyzer.date,
            "recommendations": recs,
        })

    # Track sigma observations
    sigma_est = report.get("model_calibration", {}).get("sigma_estimate")
    if sigma_est:
        cum["model_calibration"]["sigma_observations"].append({
            "date": analyzer.date,
            "sigma": sigma_est,
        })

    save_cumulative_learnings(cum)

    # Print summary
    ds = report["data_summary"]
    print(f"[LEARNER] Data: {ds['signals']} signals, {ds['price_snapshots']} prices, "
          f"{ds['games_tracked']} games")

    print(f"[LEARNER] Strategy Scores:")
    for strat, score in report.get("strategy_scores", {}).items():
        print(f"  {strat}: grade={score['grade']} | signals={score['total_signals']} | "
              f"win_rate={score['win_rate']}% | sharpe={score['sharpe']} | pnl={score['total_pnl_5m']}c")

    print(f"[LEARNER] Paper Trading:")
    print(f"  Trades: {paper.get('trades',0)} | Win rate: {paper.get('win_rate',0)}% | "
          f"Net P&L: {paper.get('total_net_pnl',0)}c")

    if recs:
        print(f"[LEARNER] Parameter Recommendations:")
        for key, rec in recs.items():
            print(f"  {key}: {rec.get('reason', '')}")

    return report
