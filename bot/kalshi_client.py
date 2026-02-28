"""Kalshi API client with RSA-PSS authentication."""
import time
import base64
import json
import requests
from urllib.parse import urlparse
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# Match official Kalshi starter code pattern
API_BASE = "https://api.elections.kalshi.com"
API_PREFIX = "/trade-api/v2"


class KalshiClient:
    def __init__(self, key_id, private_key_path, base_url=None):
        self.key_id = key_id
        self.host = base_url or API_BASE
        # Strip any path suffix from base_url if user passed full URL
        if "/trade-api" in self.host:
            self.host = self.host.split("/trade-api")[0]
        with open(private_key_path, "rb") as f:
            self.private_key = serialization.load_pem_private_key(f.read(), password=None)
        self.session = requests.Session()

    def _sign(self, timestamp_ms, method, full_path):
        """Sign request per Kalshi spec: message = {timestamp}{METHOD}{/trade-api/v2/path}"""
        # Strip query params for signing
        path_only = full_path.split("?")[0]
        message = f"{timestamp_ms}{method}{path_only}"
        signature = self.private_key.sign(
            message.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,  # Must be DIGEST_LENGTH per Kalshi docs
            ),
            hashes.SHA256()
        )
        return base64.b64encode(signature).decode("utf-8")

    def _headers(self, method, full_path):
        ts = str(int(time.time() * 1000))
        sig = self._sign(ts, method, full_path)
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": sig,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, method, path, params=None, json_body=None):
        """Make authenticated request. path is relative (e.g. /portfolio/balance)."""
        full_path = API_PREFIX + path  # e.g. /trade-api/v2/portfolio/balance
        url = self.host + full_path
        headers = self._headers(method.upper(), full_path)
        resp = self.session.request(method, url, headers=headers, params=params, json=json_body, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get(self, path, params=None):
        return self._request("GET", path, params=params)

    def post(self, path, body=None):
        return self._request("POST", path, json_body=body)

    def delete(self, path, body=None):
        return self._request("DELETE", path, json_body=body)

    # === Account ===
    def get_balance(self):
        return self.get("/portfolio/balance")

    def get_positions(self):
        return self.get("/portfolio/positions")

    # === Markets ===
    def get_markets(self, params=None):
        return self.get("/markets", params=params)

    def get_market(self, ticker):
        return self.get(f"/markets/{ticker}")

    def get_orderbook(self, ticker):
        return self.get(f"/markets/{ticker}/orderbook")

    def get_trades(self, ticker, params=None):
        return self.get(f"/markets/{ticker}/trades", params=params)

    # === Orders ===
    def create_order(self, ticker, side, action="buy", type="limit", count=1, yes_price=None, no_price=None,
                     expiration_ts=None, sell_position_floor=None, buy_max_cost=None):
        body = {
            "ticker": ticker,
            "action": action,
            "side": side,
            "type": type,
            "count": count,
        }
        if yes_price is not None:
            body["yes_price"] = yes_price
        if no_price is not None:
            body["no_price"] = no_price
        if expiration_ts is not None:
            body["expiration_ts"] = expiration_ts
        if sell_position_floor is not None:
            body["sell_position_floor"] = sell_position_floor
        if buy_max_cost is not None:
            body["buy_max_cost"] = buy_max_cost
        return self.post("/portfolio/orders", body)

    def cancel_order(self, order_id):
        return self.delete(f"/portfolio/orders/{order_id}")

    def get_orders(self, params=None):
        return self.get("/portfolio/orders", params=params)

    def get_fills(self, params=None):
        return self.get("/portfolio/fills", params=params)

    # === Events ===
    def get_events(self, params=None):
        return self.get("/events", params=params)

    def get_event(self, ticker):
        return self.get(f"/events/{ticker}")
