"""Comprehensive NCAAB market data scanner.

Collects price data from ALL open college basketball markets on Kalshi:
- Moneyline (game winner)
- Spread markets
- Total points markets
- First half markets

Runs on public API endpoints (no auth needed for market data).
"""
import requests
import time
import json
import os
from datetime import datetime

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"

# All NCAAB series we care about
NCAAB_SERIES = [
    "KXNCAAMBGAME",       # Men's game winner (moneyline)
    "KXNCAABGAME",        # College basketball game
    "KXNCAAMBSPREAD",     # Men's spread
    "KXNCAAMBTOTAL",      # Men's total points
    "KXNCAAMB1HSPREAD",   # Men's 1st half spread
    "KXNCAAMB1HWINNER",   # Men's 1st half winner
    "KXNCAAMB1HTOTAL",    # Men's 1st half total
    "KXNCAAWBGAME",       # Women's game winner
    "KXNCAAWBSPREAD",     # Women's spread
    "KXNCAAWBTOTAL",      # Women's total points
]

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def fetch_events(series_ticker, status="open"):
    """Fetch all events for a series."""
    try:
        resp = requests.get(f"{API_BASE}/events", params={
            "series_ticker": series_ticker,
            "status": status,
            "with_nested_markets": "true",
            "limit": 200,
        }, timeout=15)
        resp.raise_for_status()
        return resp.json().get("events", [])
    except Exception as e:
        print(f"[SCANNER] Error fetching {series_ticker}: {e}")
        return []


def fetch_orderbook(ticker):
    """Fetch orderbook for a single market."""
    try:
        resp = requests.get(f"{API_BASE}/markets/{ticker}/orderbook", timeout=10)
        resp.raise_for_status()
        return resp.json().get("orderbook", resp.json())
    except Exception as e:
        return None


def fetch_market(ticker):
    """Fetch single market details."""
    try:
        resp = requests.get(f"{API_BASE}/markets/{ticker}", timeout=10)
        resp.raise_for_status()
        return resp.json().get("market", resp.json())
    except Exception as e:
        return None


def scan_all_ncaab():
    """Scan ALL NCAAB markets and return structured data."""
    ts = time.time()
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    results = {
        "timestamp": ts,
        "date": date_str,
        "events": [],
        "markets": [],
        "summary": {},
    }

    total_events = 0
    total_markets = 0
    total_volume = 0

    for i, series in enumerate(NCAAB_SERIES):
        if i > 0:
            time.sleep(0.5)  # Rate limit between series
        events = fetch_events(series)
        if not events:
            continue

        for event in events:
            event_ticker = event.get("event_ticker", "")
            title = event.get("title", "")
            sub_title = event.get("sub_title", "")

            event_data = {
                "event_ticker": event_ticker,
                "series": series,
                "title": title,
                "sub_title": sub_title,
                "markets": [],
            }

            for market in event.get("markets", []):
                ticker = market.get("ticker", "")
                market_data = {
                    "ticker": ticker,
                    "event_ticker": event_ticker,
                    "series": series,
                    "subtitle": market.get("subtitle", ""),
                    "yes_bid": market.get("yes_bid"),
                    "yes_ask": market.get("yes_ask"),
                    "last_price": market.get("last_price"),
                    "volume": market.get("volume", 0),
                    "open_interest": market.get("open_interest", 0),
                    "status": market.get("status", ""),
                    "close_time": market.get("close_time", ""),
                    "result": market.get("result", ""),
                }

                event_data["markets"].append(market_data)
                results["markets"].append(market_data)
                total_markets += 1
                total_volume += market.get("volume", 0)

            results["events"].append(event_data)
            total_events += 1

    results["summary"] = {
        "total_events": total_events,
        "total_markets": total_markets,
        "total_volume": total_volume,
        "series_scanned": len(NCAAB_SERIES),
        "scan_time": round(time.time() - ts, 2),
    }

    return results


def scan_live_markets():
    """Quick scan of just today's markets with orderbook data for live trading."""
    ts = time.time()
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    today_tag = datetime.utcnow().strftime("%y%b%d").upper()  # e.g. 26FEB27

    live_data = []

    for series in NCAAB_SERIES:
        events = fetch_events(series)
        for event in events:
            event_ticker = event.get("event_ticker", "")
            # Only today's events
            if today_tag not in event_ticker:
                continue

            for market in event.get("markets", []):
                ticker = market.get("ticker", "")
                if market.get("status") != "active":
                    continue

                # Get fresh orderbook
                ob = fetch_orderbook(ticker)

                live_data.append({
                    "ts": ts,
                    "ticker": ticker,
                    "event_ticker": event_ticker,
                    "series": series,
                    "title": event.get("title", ""),
                    "subtitle": market.get("subtitle", ""),
                    "yes_bid": market.get("yes_bid"),
                    "yes_ask": market.get("yes_ask"),
                    "last_price": market.get("last_price"),
                    "volume": market.get("volume", 0),
                    "open_interest": market.get("open_interest", 0),
                    "orderbook": ob,
                })

    return live_data


def save_scan(data, scan_type="full"):
    """Save scan results to JSONL file."""
    path = os.path.join(DATA_DIR, "scans")
    _ensure_dir(path)
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    filepath = os.path.join(path, f"{scan_type}_{date_str}.jsonl")
    with open(filepath, "a") as f:
        f.write(json.dumps(data) + "\n")
    return filepath


def save_market_prices(markets):
    """Save individual market price snapshots for time-series analysis."""
    path = os.path.join(DATA_DIR, "prices")
    _ensure_dir(path)
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    filepath = os.path.join(path, f"{date_str}.jsonl")
    ts = time.time()
    with open(filepath, "a") as f:
        for m in markets:
            entry = {
                "ts": ts,
                "ticker": m.get("ticker", ""),
                "series": m.get("series", ""),
                "yes_bid": m.get("yes_bid"),
                "yes_ask": m.get("yes_ask"),
                "last_price": m.get("last_price"),
                "volume": m.get("volume", 0),
            }
            f.write(json.dumps(entry) + "\n")
    return filepath


def run_full_scan():
    """Run a full scan, save results, and return summary."""
    print(f"[SCANNER] Starting full NCAAB market scan...")
    data = scan_all_ncaab()
    save_scan(data, "full")
    save_market_prices(data["markets"])

    s = data["summary"]
    print(f"[SCANNER] Done: {s['total_events']} events, {s['total_markets']} markets, "
          f"vol={s['total_volume']}, took {s['scan_time']}s")
    return data


if __name__ == "__main__":
    data = run_full_scan()
    print(json.dumps(data["summary"], indent=2))
