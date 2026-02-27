"""Main orchestrator for the Kalshi CBB trading system.

Manages daily schedule:
- 6:00 PM EST: Wake up, pre-game scan, load today's slate
- 6:00 PM - 1:00 AM EST: Live monitoring, data capture, trading
- 1:00 AM EST: Post-session analysis, strategy reports, sleep

All times in EST (UTC-5).
"""
import time
import json
import os
import traceback
from datetime import datetime, timezone, timedelta

from bot.market_scanner import run_full_scan, scan_live_markets, save_market_prices, save_scan
from bot.espn_feed import get_live_games, get_todays_schedule
from bot.model import win_probability, fair_value_cents, delta_per_point, mean_reversion_estimate
from bot.data_logger import log_game_state, log_market_snapshot, get_session_stats
from bot.strategy import StrategyEngine

EST = timezone(timedelta(hours=-5))
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# Schedule (EST)
WAKE_HOUR = 18    # 6 PM
SLEEP_HOUR = 1    # 1 AM (next day)

# Intervals (seconds)
FULL_SCAN_INTERVAL = 300     # Full market scan every 5 min
LIVE_POLL_INTERVAL = 15      # Live game poll every 15s
PRICE_SNAP_INTERVAL = 30     # Price snapshot every 30s during games
ESPN_POLL_INTERVAL = 15      # ESPN poll every 15s


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def est_now():
    return datetime.now(EST)


def is_active_window():
    """Check if we're in the 6pm-1am EST window."""
    now = est_now()
    hour = now.hour
    # Active: 18:00 - 23:59 and 00:00 - 00:59
    return hour >= WAKE_HOUR or hour < SLEEP_HOUR


class Orchestrator:
    def __init__(self):
        self.strategy = StrategyEngine()
        self.last_full_scan = 0
        self.last_price_snap = 0
        self.last_espn_poll = 0
        self.cycle_count = 0
        self.session_start = None
        self.today_events = {}    # event_ticker -> event data
        self.today_markets = {}   # ticker -> latest market data
        self.live_games = []
        self.game_histories = {}  # espn_id -> list of snapshots
        self.auth_ok = False

        # Try to load Kalshi client for authenticated ops
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
            from bot.kalshi_client import KalshiClient
            key_id = os.getenv("KALSHI_API_KEY_ID")
            key_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "kalshi_private_key.pem")
            base_url = os.getenv("KALSHI_BASE_URL", "https://api.elections.kalshi.com")
            self.client = KalshiClient(key_id, key_path, base_url)
        except Exception as e:
            self.log(f"Kalshi client init failed: {e}")
            self.client = None

    def log(self, msg):
        ts = est_now().strftime("%I:%M:%S %p")
        print(f"[{ts}] {msg}")

    def check_auth(self):
        """Try authenticated API call."""
        if not self.client:
            return False
        try:
            bal = self.client.get_balance()
            if not self.auth_ok:
                self.log(f"AUTH OK! Balance: ${bal.get('balance', 0)/100:.2f}")
            self.auth_ok = True
            return True
        except:
            if not self.auth_ok:
                pass  # Don't spam
            self.auth_ok = False
            return False

    def run(self):
        """Main loop - runs forever, active during 6pm-1am EST."""
        self.log("=== Kalshi CBB System Starting ===")
        self.check_auth()
        if not self.auth_ok:
            self.log("Auth not available - running in DATA COLLECTION mode")
        self.log(f"Active window: {WAKE_HOUR}:00 - {SLEEP_HOUR}:00 EST")

        while True:
            try:
                if is_active_window():
                    if not self.session_start:
                        self._start_session()
                    self._active_cycle()
                else:
                    if self.session_start:
                        self._end_session()
                    self._sleep_cycle()
            except KeyboardInterrupt:
                self.log("Shutting down...")
                if self.session_start:
                    self._end_session()
                break
            except Exception as e:
                self.log(f"ERROR: {e}")
                traceback.print_exc()
                time.sleep(30)

    def _start_session(self):
        """Initialize a new trading session."""
        self.session_start = time.time()
        self.cycle_count = 0
        self.game_histories = {}
        now = est_now()
        self.log(f"\n{'='*60}")
        self.log(f"SESSION START - {now.strftime('%A %B %d, %Y %I:%M %p EST')}")
        self.log(f"{'='*60}")

        # Check auth
        self.check_auth()

        # Pre-game scan
        self.log("Running pre-game market scan...")
        scan = run_full_scan()
        s = scan["summary"]
        self.log(f"Found {s['total_events']} events, {s['total_markets']} markets, volume: {s['total_volume']:,}")

        # Cache today's events
        for event in scan["events"]:
            self.today_events[event["event_ticker"]] = event
            for m in event["markets"]:
                self.today_markets[m["ticker"]] = m

        # ESPN schedule
        schedule = get_todays_schedule()
        live_count = sum(1 for g in schedule if g["state"] == "in")
        pre_count = sum(1 for g in schedule if g["state"] == "pre")
        post_count = sum(1 for g in schedule if g["state"] == "post")
        self.log(f"ESPN: {len(schedule)} games ({pre_count} pre, {live_count} live, {post_count} final)")

        self.log("")

    def _end_session(self):
        """End trading session, run analysis."""
        self.log(f"\n{'='*60}")
        self.log("SESSION ENDING - Running post-session analysis...")
        self.log(f"{'='*60}")

        duration = (time.time() - self.session_start) / 3600
        self.log(f"Session duration: {duration:.1f} hours, {self.cycle_count} cycles")

        # Run strategy analysis on today's data
        try:
            report = self.strategy.daily_report()
            if report:
                self._save_daily_report(report)
                self.log(f"Daily report saved")
        except Exception as e:
            self.log(f"Report error: {e}")

        # Session stats
        stats = get_session_stats()
        self.log(f"Trading stats: {json.dumps(stats)}")

        # Game history summary
        self.log(f"Games tracked: {len(self.game_histories)}")
        for gid, history in self.game_histories.items():
            if history:
                first = history[0]
                last = history[-1]
                self.log(f"  {first.get('name',gid)}: {len(history)} snapshots, "
                         f"final {last.get('away_score',0)}-{last.get('home_score',0)}")

        self.session_start = None
        self.log("Session ended. Sleeping until next active window.\n")

    def _active_cycle(self):
        """One cycle during active hours."""
        self.cycle_count += 1
        now = time.time()

        # Full market scan every 5 minutes
        if now - self.last_full_scan >= FULL_SCAN_INTERVAL:
            try:
                scan = run_full_scan()
                for event in scan["events"]:
                    self.today_events[event["event_ticker"]] = event
                    for m in event["markets"]:
                        self.today_markets[m["ticker"]] = m
                self.last_full_scan = now
            except Exception as e:
                self.log(f"Scan error: {e}")

        # ESPN live games poll
        if now - self.last_espn_poll >= ESPN_POLL_INTERVAL:
            try:
                self.live_games = get_live_games()
                self.last_espn_poll = now

                for game in self.live_games:
                    gid = game["espn_id"]

                    # Track game history
                    if gid not in self.game_histories:
                        self.game_histories[gid] = []
                    self.game_histories[gid].append(game)

                    # Log game state
                    log_game_state(game)

                    # Calculate model values
                    lead = game["lead"]
                    mins = game["minutes_remaining"]
                    fv = fair_value_cents(lead, mins, home=True)
                    delta = delta_per_point(lead, mins)
                    rev = mean_reversion_estimate(lead, 0, mins)

                    # Find matching Kalshi markets
                    matched = self._match_game_to_markets(game)

                    if matched:
                        for m in matched:
                            ticker = m["ticker"]
                            market_price = m.get("last_price") or m.get("yes_bid") or 50
                            edge = fv - market_price

                            log_market_snapshot(ticker, {
                                "yes_bid": m.get("yes_bid"),
                                "yes_ask": m.get("yes_ask"),
                                "last_price": m.get("last_price"),
                                "volume": m.get("volume", 0),
                                "model_fv": fv,
                                "lead": lead,
                                "minutes_remaining": mins,
                                "period": game["period"],
                                "home_score": game["home_score"],
                                "away_score": game["away_score"],
                                "edge": edge,
                                "delta": round(delta, 4),
                            })

                            # Feed to strategy engine
                            self.strategy.on_price_update(ticker, m, game, fv, edge)

                    # Periodic game log
                    if self.cycle_count % 4 == 1:
                        mkt_str = ""
                        if matched:
                            mp = matched[0].get("last_price") or matched[0].get("yes_bid") or "?"
                            mkt_str = f" | Mkt: {mp}c | Edge: {fv - (mp if isinstance(mp, int) else 50):+d}c"
                        self.log(f"[GAME] {game['name']} | {game['away_score']}-{game['home_score']} | "
                                 f"{game['clock']} P{game['period']} | FV: {fv}c | Δ: {delta:.3f}/pt{mkt_str}")

            except Exception as e:
                self.log(f"ESPN poll error: {e}")

        # Price snapshots for all active markets
        if now - self.last_price_snap >= PRICE_SNAP_INTERVAL:
            try:
                active = [m for m in self.today_markets.values()
                          if m.get("status") == "active" and m.get("volume", 0) > 0]
                if active:
                    save_market_prices(active)
                self.last_price_snap = now
            except Exception as e:
                self.log(f"Price snap error: {e}")

        # Re-check auth periodically
        if not self.auth_ok and self.cycle_count % 120 == 0:
            self.check_auth()

        # Periodic stats
        if self.cycle_count % 60 == 0:  # Every ~15 min
            n_games = len(self.live_games)
            n_markets = len(self.today_markets)
            n_tracked = len(self.game_histories)
            self.log(f"[STATUS] Games: {n_games} live, {n_tracked} tracked | "
                     f"Markets: {n_markets} | Auth: {'OK' if self.auth_ok else 'NO'}")

        time.sleep(LIVE_POLL_INTERVAL)

    def _sleep_cycle(self):
        """Sleep until next active window."""
        now = est_now()
        # Calculate time until 6 PM EST
        target = now.replace(hour=WAKE_HOUR, minute=0, second=0, microsecond=0)
        if now.hour >= SLEEP_HOUR:
            # It's after 1 AM, wake at 6 PM today
            pass
        else:
            # Shouldn't happen but just in case
            target = target - timedelta(days=1)

        if target <= now:
            target += timedelta(days=1)

        wait_secs = (target - now).total_seconds()
        wait_hours = wait_secs / 3600

        if self.cycle_count == 0 or wait_hours > 1:
            self.log(f"Outside active window. Next session at {target.strftime('%I:%M %p EST')} "
                     f"({wait_hours:.1f} hours)")

        # Sleep in chunks so we can catch KeyboardInterrupt
        sleep_chunk = min(300, wait_secs)  # 5 min chunks
        time.sleep(sleep_chunk)

    def _match_game_to_markets(self, game):
        """Match an ESPN game to Kalshi markets using team abbreviations."""
        home_abbr = game["home"]["abbreviation"].upper()
        away_abbr = game["away"]["abbreviation"].upper()
        home_name = game["home"]["name"].upper()
        away_name = game["away"]["name"].upper()

        matched = []
        for ticker, m in self.today_markets.items():
            # Moneyline markets have team abbr in ticker
            ticker_upper = ticker.upper()
            if home_abbr in ticker_upper or away_abbr in ticker_upper:
                # Verify it's a game market (not spread/total)
                series = m.get("series", "")
                if "GAME" in series or "WINNER" in series:
                    matched.append(m)

        return matched

    def _save_daily_report(self, report):
        """Save daily strategy report."""
        path = os.path.join(DATA_DIR, "reports")
        _ensure_dir(path)
        date_str = est_now().strftime("%Y-%m-%d")
        filepath = os.path.join(path, f"{date_str}.json")
        with open(filepath, "w") as f:
            json.dump(report, f, indent=2)


def run():
    """Entry point."""
    orch = Orchestrator()
    orch.run()
