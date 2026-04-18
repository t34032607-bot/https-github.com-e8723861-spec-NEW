"""
Hybrid DCA + Infinity Grid Trading Bot
Combines Dollar-Cost Averaging with dynamic grid trading for crypto assets.

Features:
- Paper trading mode for safe testing
- Position tracking and risk management
- DCA with staged buy levels
- Profit release on gains
- Drawdown protection
- Comprehensive audit logging
- Environment variable secrets management
"""

import time
import json
import os
import threading
import logging
import math
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple, Any
import websocket

# ====================== IMPORT FROM YOUR MAIN FILE ======================
from your_powertrader_file import (
    CryptoAPITrading,
    _load_gui_settings,
    _read_long_dca_signal,
    _record_trade,
    load_secrets_from_env,
    DCA_LEVELS,
    DCA_MULTIPLIER,
    MAX_DCA_BUYS_PER_24H,
    START_ALLOC_PCT,
    TRADE_START_LEVEL,
    PM_START_PCT_NO_DCA,
    PM_START_PCT_WITH_DCA,
    TRAILING_GAP_PCT
)

# Default runtime configuration
MONITOR_INTERVAL_SEC = 1.0

# ====================== LOGGING SETUP ======================
def setup_logging(base: str):
    """Setup comprehensive logging with audit trail"""
    log_format = '%(asctime)s | %(name)s | %(levelname)-8s | %(message)s'
    
    # Main bot log
    logger = logging.getLogger("HybridDCAInfinityGrid")
    logger.setLevel(logging.DEBUG)
    
    # File handler for main log
    fh = logging.FileHandler(f"hybrid_dca_grid_{base}.log")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter(log_format))
    
    # Audit trail handler (all trades and significant actions)
    audit_handler = logging.FileHandler(f"audit_trail_{base}.log")
    audit_handler.setLevel(logging.WARNING)
    audit_handler.setFormatter(logging.Formatter(log_format))
    
    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(log_format))
    
    logger.addHandler(fh)
    logger.addHandler(audit_handler)
    logger.addHandler(ch)
    
    return logger

logger = None  # Set during __init__

# ====================== POSITION TRACKING ======================
class PositionTracker:
    """Tracks positions, cost basis, and profit/loss"""
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.base = symbol.split("-")[0].upper()
        self.positions: Dict[str, Any] = {}
        self.trade_history: List[Dict[str, Any]] = []
        self.peak_value: float = 0.0
        self.highest_price: float = 0.0
        
        self.state_file = f"position_tracker_{self.base}.json"
        self._load_state()
    
    def add_position(self, qty: float, price: float, side: str = "buy", tag: str = ""):
        """Record a position entry"""
        position_id = f"{self.base}_{int(time.time() * 1000)}"
        
        position = {
            "id": position_id,
            "symbol": self.symbol,
            "qty": qty,
            "entry_price": price,
            "entry_time": time.time(),
            "side": side.lower(),
            "tag": tag,
            "realized_pnl": 0.0,
        }
        
        self.positions[position_id] = position
        self.trade_history.append(position)
        self._save_state()
        return position_id
    
    def close_position(self, position_id: str, exit_price: float, tag: str = ""):
        """Close a position and record PnL"""
        if position_id not in self.positions:
            return None
        
        pos = self.positions[position_id]
        if pos["side"] == "buy":
            pnl = (exit_price - pos["entry_price"]) * pos["qty"]
            pnl_pct = ((exit_price - pos["entry_price"]) / pos["entry_price"]) * 100
        else:
            pnl = (pos["entry_price"] - exit_price) * pos["qty"]
            pnl_pct = ((pos["entry_price"] - exit_price) / pos["entry_price"]) * 100
        
        pos["exit_price"] = exit_price
        pos["exit_time"] = time.time()
        pos["realized_pnl"] = pnl
        pos["realized_pnl_pct"] = pnl_pct
        pos["close_tag"] = tag
        
        self._save_state()
        return pos
    
    def get_unrealized_pnl(self, current_price: float) -> Tuple[float, float]:
        """Calculate total unrealized PnL and percentage"""
        total_pnl = 0.0
        total_cost = 0.0
        total_value = 0.0
        
        for pos_id, pos in self.positions.items():
            if "exit_price" in pos:
                continue  # Skip closed positions
            
            cost = pos["entry_price"] * pos["qty"]
            current_value = current_price * pos["qty"]
            
            if pos["side"] == "buy":
                pnl = current_value - cost
            else:
                pnl = cost - current_value
            
            total_pnl += pnl
            total_cost += cost
            total_value += current_value
        
        pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0
        return total_pnl, pnl_pct
    
    def get_avg_cost_basis(self) -> float:
        """Get weighted average cost basis of open positions"""
        total_qty = 0.0
        total_cost = 0.0
        
        for pos in self.positions.values():
            if "exit_price" not in pos and pos["side"] == "buy":
                qty = pos["qty"]
                cost = pos["entry_price"] * qty
                total_qty += qty
                total_cost += cost
        
        return total_cost / total_qty if total_qty > 0 else 0.0
    
    def _save_state(self):
        """Persist position state to file"""
        try:
            data = {
                "positions": self.positions,
                "trade_history": self.trade_history,
                "last_updated": time.time(),
            }
            with open(self.state_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Position state save failed: {e}")
    
    def _load_state(self):
        """Load position state from file"""
        if os.path.isfile(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                self.positions = data.get("positions", {})
                self.trade_history = data.get("trade_history", [])
                logger.info(f"Loaded position tracking state ({len(self.positions)} open positions)")
            except Exception as e:
                logger.warning(f"Position state load failed: {e}")

# ====================== MAIN BOT CLASS ======================
class HybridDCAInfinityGrid:
    """Main bot implementing hybrid DCA + grid trading"""
    
    def __init__(self, symbol: str = "BTC-USD", paper_trading: bool = True):
        global logger
        
        self.symbol = symbol
        self.base = symbol.split("-")[0].upper()
        self.binance_symbol = self.base + "USDT"
        self.paper_trading = paper_trading
        
        # Setup logging
        logger = setup_logging(self.base)
        self.logger = logger
        
        logger.info(f"{'='*60}")
        logger.info(f"Initializing Hybrid DCA + Infinity Grid Bot")
        logger.info(f"Symbol: {symbol} | Paper Trading: {paper_trading}")
        logger.info(f"{'='*60}")
        
        # API Client
        secrets = load_secrets_from_env()
        self.api = CryptoAPITrading(
            api_key=secrets.get("api_key"),
            api_secret=secrets.get("api_secret"),
            paper_trading=paper_trading
        )
        self._display_account_balance()
        
        self.state_file = f"hybrid_state_{self.base}.json"
        self.settings = self._load_settings()
        self.monitor_interval = float(self.settings.get("monitor_interval_sec", MONITOR_INTERVAL_SEC))
        
        # Position tracking
        self.position_tracker = PositionTracker(symbol)
        
        # State variables
        self.target_usd_exposure: float = 0.0
        self.peak_exposure: float = 0.0
        self.lower_price_floor: float = 0.0
        self.active_orders: Dict[str, dict] = {}
        self.dca_stages_triggered: List[int] = []
        self.last_rebalance_ts: float = 0.0
        self.daily_trades: int = 0
        self.daily_reset_ts: float = time.time()
        self.last_price: float = 0.0
        self.highest_price: float = 0.0
        
        # Runtime state
        self.running = False
        self.monitor_thread = None
        self.price_ws = None
        self.symbol_info = self._fetch_symbol_info()
        self.last_profit_release_ts: float = 0.0
        
        self._load_state()

    def _fetch_symbol_info(self) -> dict:
        """Fetch symbol precision info"""
        try:
            resp = self.api.make_api_request("GET", f"/api/v3/exchangeInfo?symbol={self.binance_symbol}")
            if resp and "symbols" in resp:
                for s in resp["symbols"]:
                    if s["symbol"] == self.binance_symbol:
                        filters = {f["filterType"]: f for f in s.get("filters", [])}
                        return {
                            "stepSize": float(filters.get("LOT_SIZE", {}).get("stepSize", 0.000001)),
                            "tickSize": float(filters.get("PRICE_FILTER", {}).get("tickSize", 0.01)),
                        }
        except Exception as e:
            logger.warning(f"Symbol info fetch failed: {e}")
        return {"stepSize": 0.000001, "tickSize": 0.01}

    def _round_qty(self, qty: float) -> float:
        """Round quantity to valid step size"""
        if qty <= 0:
            return 0.0
        step = self.symbol_info["stepSize"]
        return math.floor(qty / step) * step

    def _round_price(self, price: float) -> float:
        """Round price to valid tick size"""
        tick = self.symbol_info["tickSize"]
        return round(price / tick) * tick

    def _format_decimal(self, value: float, is_price: bool = False) -> str:
        """Format decimal value for Binance API with appropriate precision"""
        from decimal import Decimal
        
        if is_price:
            size = self.symbol_info["tickSize"]
        else:
            size = self.symbol_info["stepSize"]
        
        # Calculate decimal places from size using Decimal for accuracy
        try:
            d = Decimal(str(size))
            decimals = -int(d.as_tuple().exponent) if d.as_tuple().exponent else 0
        except:
            decimals = 8  # Fallback
        
        # Format value with the appropriate precision
        return f"{value:.{decimals}f}"

    def _load_settings(self) -> dict:
        """Load all bot settings"""
        base = _load_gui_settings()
        return {
            "enabled": True,
            "min_signal_level": base.get("trade_start_level", TRADE_START_LEVEL),
            "target_usd_pct": 0.08,  # % of account to allocate
            "base_grid_spacing_pct": 0.9,  # Grid spacing as % of price
            "num_grids": 10,  # Number of grid levels
            "profit_release_threshold_pct": 4.0,  # Take profit when gain % exceeds this
            "profit_release_pct": 0.30,  # Release this % of position
            "max_drawdown_pct": 20.0,  # Stop if drawdown exceeds this
            "lower_floor_pct": 0.78,  # Don't buy below this % of highest price
            "max_daily_trades": 15,  # Max trades per day
            "start_allocation_pct": base.get("start_allocation_pct", START_ALLOC_PCT),
            "dca_multiplier": base.get("dca_multiplier", DCA_MULTIPLIER),
            "dca_levels": base.get("dca_levels", DCA_LEVELS),
            "max_dca_buys_per_24h": base.get("max_dca_buys_per_24h", MAX_DCA_BUYS_PER_24H),
            "monitor_interval_sec": base.get("monitor_interval_sec", MONITOR_INTERVAL_SEC),
        }

    def _start_price_websocket(self):
        """Start websocket for real-time price updates"""
        def on_message(ws, message):
            try:
                data = json.loads(message)
                if 'c' in data:  # last price
                    price = float(data['c'])
                    self.last_price = price
                    if price > self.highest_price:
                        self.highest_price = price
                        logger.debug(f"📈 New peak: ${price:.4f}")
            except Exception as e:
                logger.error(f"WS message error: {e}")

        def on_error(ws, error):
            logger.error(f"WS error: {error}")

        def on_close(ws, close_status_code, close_msg):
            logger.info("Price WS closed")

        def on_open(ws):
            logger.info("Price WS opened")

        self.price_ws = websocket.WebSocketApp(
            f"wss://stream.binance.com:9443/ws/{self.binance_symbol.lower()}@ticker",
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open
        )
        ws_thread = threading.Thread(target=self.price_ws.run_forever, daemon=True)
        ws_thread.start()

    def _save_state(self):
        """Persist bot state to file"""
        try:
            data = {
                "target_usd_exposure": self.target_usd_exposure,
                "lower_price_floor": self.lower_price_floor,
                "dca_stages_triggered": self.dca_stages_triggered,
                "highest_price": self.highest_price,
                "last_updated": time.time(),
            }
            with open(self.state_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"State save failed: {e}")

    def _display_account_balance(self):
        """Show spot account balance when API keys are loaded"""
        try:
            acct = self.api.get_account()
            if isinstance(acct, dict):
                buying_power = float(acct.get("buying_power", 0.0))
                cash = float(acct.get("cash", buying_power))
                total_value = float(acct.get("total_account_value", buying_power))

                logger.info(f"📊 Spot Balance Loaded | Buying Power: ${buying_power:.2f} | Cash: ${cash:.2f} | Total: ${total_value:.2f}")
                print("\n💰 Spot Account Balance:")
                print(f"  Available USD: ${buying_power:.2f}")
                print(f"  Cash: ${cash:.2f}")
                print(f"  Total Account Value: ${total_value:.2f}\n")
                return buying_power

        except Exception as e:
            logger.warning(f"Account balance display failed: {e}")

        logger.warning("Unable to load account balance")
        return 0.0

    def _prompt_trade_amount(self, buying_power: float) -> float:
        """Ask the user how much USD to trade with"""
        default_amount = buying_power * self.settings.get("target_usd_pct", 0.08)

        while True:
            try:
                raw = input(
                    f"Enter trade amount in USD (max ${buying_power:.2f}) or percent (e.g. 10%): "
                ).strip()

                if raw == "":
                    print(f"Using default trade amount: ${default_amount:.2f}\n")
                    return min(default_amount, buying_power)

                if raw.endswith("%"):
                    pct = float(raw[:-1].strip()) / 100.0
                    amount = buying_power * pct
                else:
                    amount = float(raw)

                if amount <= 0:
                    print("Amount must be greater than 0.")
                    continue
                if amount > buying_power:
                    print("Amount cannot exceed available buying power.")
                    continue

                return amount
            except ValueError:
                print("Invalid value. Enter a dollar amount or percentage like 10%.")

    def _load_state(self):
        """Load bot state from file"""
        if os.path.isfile(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                self.target_usd_exposure = float(data.get("target_usd_exposure", 0.0))
                self.lower_price_floor = float(data.get("lower_price_floor", 0.0))
                self.dca_stages_triggered = data.get("dca_stages_triggered", [])
                self.highest_price = float(data.get("highest_price", 0.0))
                logger.info(f"Loaded hybrid bot state from {self.state_file}")
            except Exception as e:
                logger.warning(f"Hybrid state load failed: {e}")

    def start(self):
        """Start the bot"""
        if self.running:
            return
        
        self.running = True
        logger.warning(f"🚀 STARTING BOT: {self.symbol} | Mode: {'PAPER' if self.paper_trading else 'LIVE'}")

        try:
            # Get initial price
            buy_p, sell_p, mid_p = self.api.get_price([self.symbol])
            current_price = buy_p.get(self.symbol) or sell_p.get(self.symbol) or 0
            
            if not current_price or current_price <= 0:
                logger.error("❌ No price data available - cannot start")
                self.running = False
                return
            
            self.last_price = current_price
            self.highest_price = max(self.highest_price, current_price)

            # Get account info
            acct = self.api.get_account()
            buying_power = float(acct.get("buying_power", 0)) if isinstance(acct, dict) else 0
            
            if buying_power <= 0:
                logger.error("❌ No buying power - cannot start")
                self.running = False
                return
            
            # Ask how much to trade with
            self.target_usd_exposure = self._prompt_trade_amount(buying_power)
            self.peak_exposure = self.target_usd_exposure
            self.lower_price_floor = current_price * self.settings["lower_floor_pct"]

            logger.info(f"Initial price: ${current_price:.4f}")
            logger.info(f"Buying power: ${buying_power:.2f}")
            logger.info(f"Target exposure: ${self.target_usd_exposure:.2f}")
            logger.info(f"Lower floor: ${self.lower_price_floor:.2f}")

            # Initial buy
            initial_usd = self.target_usd_exposure * self.settings["start_allocation_pct"]
            qty = self._round_qty(initial_usd / current_price)
            if qty > 0:
                self._place_limit_order("BUY", current_price, qty, tag="INITIAL")
                self.position_tracker.add_position(qty, current_price, "buy", "INITIAL")
            
            # Place grid orders
            self._place_grid_orders(current_price)
            self._save_state()

            # Start price websocket for real-time updates
            self._start_price_websocket()

            # Start monitoring
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=False)
            self.monitor_thread.start()
            
            logger.warning(f"✅ BOT STARTED successfully")

        except Exception as e:
            logger.error(f"❌ Failed to start bot: {e}", exc_info=True)
            self.running = False

    def _monitor_loop(self):
        """Main monitoring loop - runs continuously"""
        error_count = 0
        max_errors = 10
        
        while self.running:
            try:
                now = time.time()
                
                # Reset daily counter
                if now - self.daily_reset_ts > 86400:
                    self.daily_trades = 0
                    self.daily_reset_ts = now
                    logger.info("📊 Daily trade counter reset")

                # Get current price (now from websocket)
                current_price = self.last_price
                
                if current_price <= 0:
                    logger.warning("⚠️  No price data - skipping cycle")
                    time.sleep(self.monitor_interval)
                    continue
                
                # self.last_price already updated by WS
                # if current_price > self.highest_price:
                #     self.highest_price = current_price
                #     logger.info(f"📈 New peak: ${current_price:.4f}")  # Moved to WS

                # Check signal
                signal = _read_long_dca_signal(self.base)
                logger.debug(f"Signal level: {signal:.1f}")
                
                if signal < self.settings["min_signal_level"]:
                    logger.debug(f"Signal too low ({signal} < {self.settings['min_signal_level']}) - skipping trades")
                    time.sleep(self.monitor_interval)
                    continue

                # Main logic
                self._handle_dca(current_price)
                self._check_profit_release(current_price)
                
                drawdown = self._check_drawdown(current_price)
                logger.debug(f"Drawdown: {drawdown:.2f}%")
                
                if drawdown > self.settings["max_drawdown_pct"]:
                    logger.error(f"❌ MAX DRAWDOWN REACHED: {drawdown:.2f}% > {self.settings['max_drawdown_pct']}%")
                    self.stop()
                    break
                
                # Save state periodically
                if now - self.last_rebalance_ts > 300:  # Every 5 min
                    self._save_state()
                    self.last_rebalance_ts = now
                
                error_count = 0  # Reset error count on successful cycle
                time.sleep(self.monitor_interval)
                
            except Exception as e:
                error_count += 1
                logger.error(f"Monitor loop error ({error_count}/{max_errors}): {e}", exc_info=True)
                
                if error_count >= max_errors:
                    logger.critical(f"❌ Too many errors - stopping bot")
                    self.stop()
                    break
                
                time.sleep(self.monitor_interval)

    def _handle_dca(self, current_price: float):
        """Handle DCA buy logic"""
        try:
            if self.daily_trades >= self.settings["max_daily_trades"]:
                logger.debug("Daily trade limit reached")
                return
            
            if len(self.dca_stages_triggered) >= len(self.settings["dca_levels"]):
                logger.debug("All DCA levels triggered")
                return
            
            # Calculate unrealized PnL %
            unrealized_pnl, unrealized_pct = self.position_tracker.get_unrealized_pnl(current_price)
            logger.debug(f"Unrealized PnL: {unrealized_pct:.2f}% (${unrealized_pnl:.2f})")
            
            # Check each DCA level
            for level in self.settings["dca_levels"]:
                if level not in self.dca_stages_triggered and unrealized_pct <= level:
                    # Calculate DCA position size
                    num_triggered = len(self.dca_stages_triggered)
                    size_multiplier = self.settings["dca_multiplier"] ** num_triggered
                    dca_usd = self.target_usd_exposure * (self.settings["start_allocation_pct"] * size_multiplier)
                    
                    qty = self._round_qty(dca_usd / current_price)
                    if qty > 0:
                        logger.warning(f"📍 DCA TRIGGER at {level}%: Buying {qty:.6f} @ ${current_price:.4f}")
                        order_id = self._place_limit_order("BUY", current_price, qty, tag=f"DCA_{level}")
                        if order_id:
                            self.position_tracker.add_position(qty, current_price, "buy", f"DCA_{level}")
                            self.dca_stages_triggered.append(level)
                    break
                    
        except Exception as e:
            logger.error(f"DCA handling error: {e}", exc_info=True)

    def _check_profit_release(self, current_price: float):
        """Check and execute profit-taking"""
        try:
            unrealized_pnl, unrealized_pct = self.position_tracker.get_unrealized_pnl(current_price)
            
            if unrealized_pct < self.settings["profit_release_threshold_pct"]:
                return
            
            # Time-based profit release (prevent too frequent selling)   
            if time.time() - self.last_profit_release_ts < 300:  # Min 5 min between releases
                return
            
            # Calculate total position size from open buy positions
            total_position_qty = 0.0
            for pos_id, pos in self.position_tracker.positions.items():
                if "exit_price" not in pos and pos["side"] == "buy":
                    total_position_qty += pos["qty"]
            
            if total_position_qty <= 0:
                logger.warning("No open positions to take profit from")
                return
            
            # Calculate quantity to sell (percentage of position)
            sell_qty = total_position_qty * self.settings["profit_release_pct"]
            sell_qty = self._round_qty(sell_qty)
            
            if sell_qty <= 0:
                logger.warning(f"Calculated sell quantity too small: {sell_qty}")
                return
            
            logger.warning(f"💰 PROFIT RELEASE: {unrealized_pct:.2f}% gain - selling {sell_qty:.6f} {self.base} (${sell_qty * current_price:.2f})")
            
            # Place market sell order for profit-taking
            order_id = self._place_market_order("SELL", sell_qty, tag="PROFIT_TAKE")
            
            if order_id:
                # Record the profit-taking in position tracker
                # Note: In a real implementation, this would be updated when the order fills
                # For now, we'll mark a portion of positions as closed at current price
                closed_qty = 0.0
                for pos_id, pos in list(self.position_tracker.positions.items()):
                    if closed_qty >= sell_qty:
                        break
                    if "exit_price" not in pos and pos["side"] == "buy":
                        remaining_qty = pos["qty"]
                        close_qty = min(remaining_qty, sell_qty - closed_qty)
                        
                        if close_qty > 0:
                            # Create a partial close record
                            partial_pos = pos.copy()
                            partial_pos["qty"] = close_qty
                            self.position_tracker.close_position(pos_id, current_price, "PROFIT_TAKE")
                            
                            # Reduce original position
                            pos["qty"] -= close_qty
                            if pos["qty"] <= 0:
                                del self.position_tracker.positions[pos_id]
                            
                            closed_qty += close_qty
                
                self.last_profit_release_ts = time.time()
                logger.info(f"✅ Profit release executed: Sold {sell_qty:.6f} {self.base} @ ${current_price:.4f}")
            else:
                logger.error("Failed to place profit-taking sell order")
            
        except Exception as e:
            logger.error(f"Profit release error: {e}", exc_info=True)

    def _check_drawdown(self, current_price: float) -> float:
        """Calculate current drawdown from peak"""
        if self.highest_price <= 0:
            return 0.0
        
        drawdown_pct = ((self.highest_price - current_price) / self.highest_price) * 100
        return max(0.0, drawdown_pct)

    def _place_limit_order(self, side: str, price: float, qty: float, tag: str = "GRID") -> Optional[str]:
        """Place a limit order"""
        try:
            price = self._round_price(price)
            qty = self._round_qty(qty)
            
            if qty <= 0:
                logger.warning(f"Invalid qty for order: {qty}")
                return None

            params = {
                "symbol": self.binance_symbol,
                "side": side.upper(),
                "type": "LIMIT",
                "timeInForce": "GTC",
                "quantity": self._format_decimal(qty, is_price=False),
                "price": self._format_decimal(price, is_price=True),
            }

            resp = self.api.make_api_request("POST", "/api/v3/order", json.dumps(params))
            if resp and "orderId" in resp:
                order_id = str(resp["orderId"])
                self.active_orders[order_id] = {
                    "side": side.lower(),
                    "price": price,
                    "qty": qty,
                    "ts": time.time(),
                    "tag": tag
                }
                logger.info(f"[{tag}] ORDER: {side.upper()} {qty:.6f} @ ${price:.4f}")
                self.daily_trades += 1
                return order_id
            else:
                logger.warning(f"Order response missing orderId: {resp}")
                
        except Exception as e:
            logger.error(f"Order placement error: {e}", exc_info=True)
        
        return None

    def _place_market_order(self, side: str, qty: float, tag: str = "MARKET") -> Optional[str]:
        """Place a market order"""
        try:
            qty = self._round_qty(qty)
            
            if qty <= 0:
                logger.warning(f"Invalid qty for market order: {qty}")
                return None

            params = {
                "symbol": self.binance_symbol,
                "side": side.upper(),
                "type": "MARKET",
                "quantity": self._format_decimal(qty, is_price=False),
            }

            resp = self.api.make_api_request("POST", "/api/v3/order", json.dumps(params))
            if resp and "orderId" in resp:
                order_id = str(resp["orderId"])
                executed_qty = float(resp.get("executedQty", qty))
                avg_price = float(resp.get("avgPrice", 0)) if "avgPrice" in resp else 0
                
                self.active_orders[order_id] = {
                    "side": side.lower(),
                    "price": avg_price,
                    "qty": executed_qty,
                    "ts": time.time(),
                    "tag": tag
                }
                logger.info(f"[{tag}] MARKET ORDER: {side.upper()} {executed_qty:.6f} @ ${avg_price:.4f}")
                self.daily_trades += 1
                return order_id
            else:
                logger.warning(f"Market order response missing orderId: {resp}")
                
        except Exception as e:
            logger.error(f"Market order placement error: {e}", exc_info=True)
        
        return None

    def _place_grid_orders(self, current_price: float):
        """Place grid buy/sell orders"""
        try:
            self._cancel_all_orders()
            
            spacing = self.settings["base_grid_spacing_pct"]
            step = current_price * (spacing / 100.0)
            
            for i in range(1, self.settings["num_grids"] + 1):
                buy_price = self._round_price(current_price - i * step)
                sell_price = self._round_price(current_price + i * step)
                
                # Buy grid
                if buy_price > self.lower_price_floor:
                    qty_buy = self._round_qty((self.target_usd_exposure / self.settings["num_grids"]) / buy_price)
                    if qty_buy > 0:
                        self._place_limit_order("BUY", buy_price, qty_buy, tag="GRID_BUY")
                
                # Sell grid
                qty_sell = self._round_qty((self.target_usd_exposure / self.settings["num_grids"]) / sell_price)
                if qty_sell > 0:
                    self._place_limit_order("SELL", sell_price, qty_sell, tag="GRID_SELL")
                    
        except Exception as e:
            logger.error(f"Grid order error: {e}", exc_info=True)

    def _cancel_all_orders(self):
        """Cancel all active orders"""
        try:
            for oid in list(self.active_orders.keys()):
                try:
                    self.api.make_api_request("DELETE", f"/api/v3/order?symbol={self.binance_symbol}&orderId={oid}")
                except Exception:
                    pass
            self.active_orders.clear()
        except Exception as e:
            logger.error(f"Cancel all orders error: {e}", exc_info=True)

    def stop(self):
        """Stop the bot gracefully"""
        if not self.running:
            return
        
        self.running = False
        logger.warning(f"⛔ STOPPING BOT: {self.symbol}")
        
        try:
            if self.price_ws:
                self.price_ws.close()
            self._cancel_all_orders()
            self._save_state()
            logger.info(f"Saved final state")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}", exc_info=True)
        
        logger.warning(f"🛑 BOT STOPPED")

# ====================== ENTRY POINT ======================
if __name__ == "__main__":
    # Load environment variables
    paper_mode = os.environ.get("PAPER_TRADING", "true").lower() == "true"
    symbol = os.environ.get("TRADING_SYMBOL", "BTC-USD")
    
    bot = HybridDCAInfinityGrid(symbol=symbol, paper_trading=paper_mode)
    
    try:
        bot.start()
        while bot.running:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        bot.stop()
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        bot.stop()
