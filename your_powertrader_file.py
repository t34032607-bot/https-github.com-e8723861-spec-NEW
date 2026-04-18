"""
PowerTrader API Stub Module
Provides mock implementation of CryptoAPITrading and supporting functions
for hybrid DCA grid trading bot.
"""

import os
import json
import logging
import time
import hmac
import hashlib
import ssl
import urllib.parse
import urllib.request
from typing import Dict, List, Tuple, Optional, Any

logger = logging.getLogger("PowerTraderStub")

# ============= CONFIGURATION CONSTANTS =============
DCA_LEVELS = [-5, -10, -15, -20]  # % drop levels for DCA triggers
DCA_MULTIPLIER = 1.5  # Multiply size by this factor per DCA level
MAX_DCA_BUYS_PER_24H = 5  # Maximum DCA buys in 24 hours
START_ALLOC_PCT = 0.3  # Initial allocation as % of target
TRADE_START_LEVEL = 5  # Minimum signal level to start trading
PM_START_PCT_NO_DCA = 2.0  # Profit target without DCA
PM_START_PCT_WITH_DCA = 3.0  # Profit target with active DCA
TRAILING_GAP_PCT = 0.5  # Trailing stop gap percentage

# Storage for portfolio state
_PORTFOLIO_STATE = {
    "positions": {},  # {symbol: {"qty": float, "cost_basis": float, "entry_price": float}}
    "trades": [],  # List of all executed trades
    "api_calls_count": 0,
}

# ============= API CONFIGURATION =============
class CryptoAPITrading:
    """Mock/Stub implementation of cryptocurrency API trading class"""

    BINANCE_API_BASE = "https://api.binance.com"
    RECV_WINDOW_MS = 5000

    def __init__(self, api_key: str = None, api_secret: str = None, paper_trading: bool = True):
        """
        Initialize trading API client
        
        Args:
            api_key: API key (from env var CRYPTO_API_KEY if not provided)
            api_secret: API secret (from env var CRYPTO_API_SECRET if not provided)
            paper_trading: If True, use simulated account (safe for testing)
        """
        self.api_key = api_key or os.environ.get("CRYPTO_API_KEY")
        self.api_secret = api_secret or os.environ.get("CRYPTO_API_SECRET")
        self.paper_trading = paper_trading
        self.api_type = "spot"
        self.base_url = self.BINANCE_API_BASE

        # Simulated account state for paper trading
        self.simulated_balance = 10.0  # $10 starting capital
        self.simulated_positions = {}  # {symbol: qty}

        if self.paper_trading:
            logger.info(f"✅ PAPER TRADING MODE ENABLED - Starting balance: ${self.simulated_balance}")
        else:
            if not self.api_key or not self.api_secret:
                logger.warning(
                    "Live trading requested but CRYPTO_API_KEY/CRYPTO_API_SECRET are missing. "
                    "Falling back to PAPER TRADING mode."
                )
                self.paper_trading = True
                logger.info(f"✅ PAPER TRADING MODE ENABLED - Starting balance: ${self.simulated_balance}")
            else:
                logger.warning("⚠️  LIVE TRADING MODE - Using real API keys")

    def make_api_request(self, method: str, endpoint: str, data: str = None) -> Dict[str, Any]:
        """
        Make authenticated API request
        
        Args:
            method: HTTP method (GET, POST, DELETE)
            endpoint: API endpoint path
            data: JSON string of request body
            
        Returns:
            Response dict
        """
        _PORTFOLIO_STATE["api_calls_count"] += 1

        if self.paper_trading:
            return self._simulate_api_call(method, endpoint, data)

        return self._send_binance_request(method, endpoint, data)

    def _send_binance_request(self, method: str, endpoint: str, data: str = None) -> Dict[str, Any]:
        """Send a signed request to Binance spot API."""
        method = method.upper()
        parsed = urllib.parse.urlparse(endpoint)
        path = parsed.path
        params = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))

        if data:
            try:
                body_params = json.loads(data)
                if isinstance(body_params, dict):
                    params.update({k: str(v) for k, v in body_params.items() if v is not None})
            except Exception:
                logger.warning("Unable to parse request body as JSON; sending raw body string")

        # Only add auth parameters for private endpoints
        is_private_endpoint = not (
            path.startswith("/api/v3/time") or 
            path.startswith("/api/v3/exchangeInfo") or
            path.startswith("/api/v3/ticker")
        )
        
        if is_private_endpoint:
            params["timestamp"] = str(int(time.time() * 1000))
            params["recvWindow"] = str(self.RECV_WINDOW_MS)

        if is_private_endpoint:
            query_string = urllib.parse.urlencode(params)
            signature = hmac.new(
                self.api_secret.encode("utf-8"),
                query_string.encode("utf-8"),
                hashlib.sha256
            ).hexdigest()
            full_query = f"{query_string}&signature={signature}"
            url = f"{self.base_url}{path}?{full_query}"

            headers = {
                "X-MBX-APIKEY": self.api_key,
                "Content-Type": "application/x-www-form-urlencoded",
            }
        else:
            # Public endpoints don't need signature or API key
            if params:
                query_string = urllib.parse.urlencode(params)
                url = f"{self.base_url}{path}?{query_string}"
            else:
                url = f"{self.base_url}{path}"
            
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
            }

        request_data = None
        if method in ("POST", "PUT"):
            # For order endpoints, parameters go in URL query string, not body
            if "/order" in path:
                url = f"{self.base_url}{path}?{full_query}"
            else:
                request_data = full_query.encode("utf-8")
                url = f"{self.base_url}{path}"

        request = urllib.request.Request(url, data=request_data, method=method, headers=headers)

        try:
            with urllib.request.urlopen(request, timeout=15, context=ssl.create_default_context()) as response:
                body = response.read().decode("utf-8")
                return json.loads(body)
        except urllib.error.HTTPError as http_err:
            body = http_err.read().decode("utf-8")
            logger.error(f"Binance API HTTPError {http_err.code}: {body}")
            raise
        except Exception as e:
            logger.error(f"Binance API request failed: {e}")
            raise

    def _simulate_api_call(self, method: str, endpoint: str, data: str = None) -> Dict[str, Any]:
        """Simulate API responses for paper trading"""
        
        # Server time endpoint
        if "/time" in endpoint:
            import time as time_module
            return {
                "serverTime": int(time_module.time() * 1000)
            }
        
        # exchangeInfo endpoint
        if "exchangeInfo" in endpoint:
            symbol = "BTCUSDT"
            return {
                "symbols": [{
                    "symbol": symbol,
                    "filters": [
                        {"filterType": "LOT_SIZE", "stepSize": "0.000001"},
                        {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                    ]
                }]
            }
        
        # Order placement
        if method == "POST" and "/order" in endpoint:
            try:
                params = json.loads(data) if data else {}
                order_id = _PORTFOLIO_STATE["api_calls_count"]
                return {
                    "orderId": order_id,
                    "symbol": params.get("symbol"),
                    "side": params.get("side"),
                    "price": params.get("price"),
                    "quantity": params.get("quantity"),
                    "status": "NEW",
                }
            except Exception as e:
                logger.error(f"Order simulation error: {e}")
                return {}
        
        # Order cancellation
        if method == "DELETE" and "/order" in endpoint:
            return {"status": "CANCELED"}
        
        return {}

    def get_price(self, symbols: List[str]) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float]]:
        """
        Get current prices for symbols
        
        Args:
            symbols: List of symbol strings (e.g., ["BTC-USD", "ETH-USD"])
            
        Returns:
            Tuple of (buy_prices, sell_prices, mid_prices) dicts
        """
        buy_prices = {}
        sell_prices = {}
        mid_prices = {}

        if self.paper_trading:
            mock_prices = {
                "BTC": 45000,
                "ETH": 2500,
                "SOL": 120,
            }
            for sym in symbols:
                base = sym.split("-")[0].upper()
                price = mock_prices.get(base, 1000)
                buy_prices[sym] = price * 0.999
                sell_prices[sym] = price * 1.001
                mid_prices[sym] = price
            return buy_prices, sell_prices, mid_prices

        for sym in symbols:
            base = sym.split("-")[0].upper()
            binance_symbol = f"{base}USDT"
            resp = self._send_public_request(f"/api/v3/ticker/bookTicker?symbol={binance_symbol}")
            if isinstance(resp, dict) and resp.get("symbol") == binance_symbol:
                bid = float(resp.get("bidPrice", 0.0))
                ask = float(resp.get("askPrice", 0.0))
                buy_prices[sym] = ask
                sell_prices[sym] = bid
                mid_prices[sym] = (bid + ask) / 2 if bid and ask else ask or bid
            else:
                buy_prices[sym] = 0.0
                sell_prices[sym] = 0.0
                mid_prices[sym] = 0.0

        return buy_prices, sell_prices, mid_prices

    def _send_public_request(self, endpoint: str) -> Dict[str, Any]:
        """Send a public Binance API request (no signature required)."""
        url = f"{self.base_url}{endpoint}"
        request = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=15, context=ssl.create_default_context()) as response:
                body = response.read().decode("utf-8")
                return json.loads(body)
        except urllib.error.HTTPError as http_err:
            body = http_err.read().decode("utf-8")
            logger.error(f"Binance public API HTTPError {http_err.code}: {body}")
            raise
        except Exception as e:
            logger.error(f"Binance public API request failed: {e}")
            raise

    def get_account(self) -> Dict[str, Any]:
        """Get account information"""
        if self.paper_trading:
            return {
                "buying_power": self.simulated_balance,
                "cash": self.simulated_balance,
                "total_account_value": self.simulated_balance,
                "positions": self.simulated_positions,
            }

        resp = self._send_binance_request("GET", "/api/v3/account")
        balances = resp.get("balances", []) if isinstance(resp, dict) else []
        usdt_balance = 0.0
        positions = {}

        for item in balances:
            asset = item.get("asset")
            free = float(item.get("free", 0))
            locked = float(item.get("locked", 0))
            total = free + locked
            if total > 0:
                positions[asset] = {
                    "free": free,
                    "locked": locked,
                    "total": total,
                }
            if asset == "USDT":
                usdt_balance = free

        return {
            "buying_power": usdt_balance,
            "cash": usdt_balance,
            "total_account_value": usdt_balance,
            "positions": positions,
        }

    def get_position(self, symbol: str) -> Dict[str, Any]:
        """Get position for a symbol"""
        if self.paper_trading:
            return {
                "symbol": symbol,
                "qty": self.simulated_positions.get(symbol, 0),
                "avg_fill_price": 0,
                "unrealized_pl": 0,
            }

        asset = symbol.split("-")[0].upper()
        resp = self._send_binance_request("GET", "/api/v3/account")
        balances = resp.get("balances", []) if isinstance(resp, dict) else []
        position = next((item for item in balances if item.get("asset") == asset), None)
        if position:
            return {
                "symbol": symbol,
                "qty": float(position.get("free", 0)) + float(position.get("locked", 0)),
                "avg_fill_price": 0,
                "unrealized_pl": 0,
            }
        return {
            "symbol": symbol,
            "qty": 0,
            "avg_fill_price": 0,
            "unrealized_pl": 0,
        }

# ============= UTILITY FUNCTIONS =============

def _load_gui_settings() -> Dict[str, Any]:
    """Load GUI configuration settings (stub)"""
    try:
        settings_file = os.environ.get("SETTINGS_FILE", "gui_settings.json")
        if os.path.exists(settings_file):
            with open(settings_file, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Could not load GUI settings: {e}")
    
    # Return defaults
    return {
        "trade_start_level": TRADE_START_LEVEL,
        "start_allocation_pct": START_ALLOC_PCT,
        "dca_multiplier": DCA_MULTIPLIER,
        "dca_levels": DCA_LEVELS,
        "max_dca_buys_per_24h": MAX_DCA_BUYS_PER_24H,
    }

def _read_long_dca_signal(base: str) -> float:
    """
    Read DCA signal level for base asset
    
    Returns:
        Signal strength (0-100), or negative value for unrealized loss %
    """
    # In production, would read from signal analysis or network
    # For now, return mock data
    return 25.0  # Neutral signal

def _record_trade(side: str, symbol: str, qty: float, price: float, 
                 tag: str = "", order_id: str = "") -> Dict[str, Any]:
    """
    Record executed trade to ledger
    
    Args:
        side: "buy" or "sell"
        symbol: Trading pair symbol
        qty: Quantity executed
        price: Execution price
        tag: Trade tag ("GRID_BUY", "DCA_-5", etc.)
        order_id: Broker order ID
        
    Returns:
        Trade record dict
    """
    import time
    
    trade = {
        "timestamp": time.time(),
        "side": side.lower(),
        "symbol": symbol,
        "qty": qty,
        "price": price,
        "notional": qty * price,
        "tag": tag,
        "order_id": order_id,
    }
    
    _PORTFOLIO_STATE["trades"].append(trade)
    
    logger.info(
        f"Trade recorded | {side.upper()} {qty:.6f} {symbol} @ {price:.4f} "
        f"({tag}) Order: {order_id}"
    )
    
    return trade

def get_portfolio_state() -> Dict[str, Any]:
    """Get current portfolio state"""
    return _PORTFOLIO_STATE

def reset_portfolio_state() -> None:
    """Reset portfolio state (for testing)"""
    global _PORTFOLIO_STATE
    _PORTFOLIO_STATE = {
        "positions": {},
        "trades": [],
        "api_calls_count": 0,
    }

# ============= ENVIRONMENT SETUP =============

def load_secrets_from_env() -> Dict[str, str]:
    """
    Load API secrets from environment variables
    
    Required env vars:
    - CRYPTO_API_KEY
    - CRYPTO_API_SECRET
    - PAPER_TRADING (true/false)
    """
    secrets = {
        "api_key": os.environ.get("CRYPTO_API_KEY"),
        "api_secret": os.environ.get("CRYPTO_API_SECRET"),
        "paper_trading": os.environ.get("PAPER_TRADING", "true").lower() == "true",
    }
    
    if not secrets["api_key"] or not secrets["api_secret"]:
        logger.warning("API credentials not in environment - using paper trading defaults")
        secrets["paper_trading"] = True
    
    return secrets
