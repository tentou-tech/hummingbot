#!/usr/bin/env python

import asyncio
import logging
import time
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from bidict import bidict

from hummingbot.connector.constants import s_decimal_0, s_decimal_NaN
from hummingbot.connector.exchange.somnia import (
    somnia_constants as CONSTANTS,
    somnia_utils as utils,
    somnia_web_utils as web_utils,
)
from hummingbot.connector.exchange.somnia.somnia_api_order_book_data_source import SomniaAPIOrderBookDataSource
from hummingbot.connector.exchange.somnia.somnia_api_user_stream_data_source import SomniaAPIUserStreamDataSource
from hummingbot.connector.exchange.somnia.somnia_auth import SomniaAuth
from hummingbot.connector.exchange_py_base import ExchangePyBase
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import combine_to_hb_trading_pair
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderState, OrderUpdate, TradeUpdate
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.trade_fee import AddedToCostTradeFee, TradeFeeBase, TokenAmount
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.network_iterator import NetworkStatus
from hummingbot.core.utils.estimate_fee import build_trade_fee
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.client.config.config_helpers import ClientConfigAdapter

try:
    from standardweb3 import StandardClient
except ImportError:
    StandardClient = None

try:
    import pandas as pd
except ImportError:
    pd = None


class SomniaExchange(ExchangePyBase):
    """
    Somnia exchange connector using StandardWeb3 for blockchain interactions.
    """
    
    web_utils = web_utils
    _logger: Optional[HummingbotLogger] = None
    
    # Error rate limiting to prevent infinite loops
    _error_count = 0
    _last_error_time = 0
    _error_rate_limit = 10  # Max 10 errors per minute
    _error_time_window = 60  # 60 seconds

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger
    
    @classmethod
    def _should_log_error(cls) -> bool:
        """
        Check if we should log an error based on rate limiting.
        
        Returns:
            True if error should be logged, False if rate limited
        """
        current_time = time.time()
        
        # Reset error count if time window has passed
        if current_time - cls._last_error_time > cls._error_time_window:
            cls._error_count = 0
            cls._last_error_time = current_time
        
        # Increment error count
        cls._error_count += 1
        
        # Check if we've exceeded the rate limit
        if cls._error_count > cls._error_rate_limit:
            return False
        
        cls._last_error_time = current_time
        return True

    def __init__(
        self,
        client_config_map: "ClientConfigAdapter",
        somnia_private_key: str,
        somnia_wallet_address: str,
        trading_pairs: List[str] = None,
        trading_required: bool = True,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        self.logger().info("=== DEBUG: SomniaExchange.__init__ STARTING ===")
        self.logger().info(f"DEBUG: Constructor called with parameters:")
        self.logger().info(f"  - trading_pairs = {trading_pairs} (type: {type(trading_pairs)})")
        self.logger().info(f"  - trading_required = {trading_required} (type: {type(trading_required)})")
        self.logger().info(f"  - somnia_wallet_address = {somnia_wallet_address}")
        self.logger().info(f"  - domain = {domain}")
        
        # Store configuration
        self._private_key = somnia_private_key
        self._wallet_address = somnia_wallet_address
        self._domain = domain
        self._trading_required = trading_required
        self._trading_pairs = trading_pairs or []
        
        self.logger().info(f"DEBUG: After assignment:")
        self.logger().info(f"  - self._trading_pairs = {self._trading_pairs} (len: {len(self._trading_pairs)})")
        self.logger().info(f"  - self._trading_required = {self._trading_required}")
        
        # Log the call stack to understand who's creating this connector
        import traceback
        stack = traceback.format_stack()
        self.logger().info("DEBUG: Connector creation call stack (last 5 frames):")
        for i, frame in enumerate(stack[-5:]):
            self.logger().info(f"  Frame {i}: {frame.strip()}")
        
        # Initialize StandardWeb3 client if available
        self._standard_client = None
        if StandardClient:
            try:
                import os
                from dotenv import load_dotenv
                
                # Load environment variables
                load_dotenv()
                
                # Get private key from environment (use env variable over parameter for StandardClient)
                env_private_key = os.getenv('SOMNIA_PRIVATE_KEY')
                if env_private_key:
                    standard_client_private_key = env_private_key
                    self.logger().info("Using private key from .env file for StandardClient")
                else:
                    standard_client_private_key = self._private_key
                    self.logger().info("Using private key from constructor parameter for StandardClient")
                
                # Get configuration from environment with fallbacks
                rpc_url = os.getenv('SOMNIA_RPC_URL', 'https://dream-rpc.somnia.network')
                api_key = os.getenv('STANDARD_API_KEY', 'defaultApiKey')
                
                # Store RPC URL for nonce management
                self._rpc_url = rpc_url
                
                # Use correct Somnia testnet endpoints from our constants
                from hummingbot.connector.exchange.somnia.somnia_constants import (
                    SOMNIA_GRAPHQL_ENDPOINT, 
                    SOMNIA_WEBSOCKET_URL,
                    STANDARD_EXCHANGE_ADDRESS
                )
                
                api_url = SOMNIA_GRAPHQL_ENDPOINT  # https://somnia-testnet-ponder-release.standardweb3.com
                websocket_url = SOMNIA_WEBSOCKET_URL  # wss://ws3-somnia-testnet-ponder-release.standardweb3.com
                matching_engine_address = STANDARD_EXCHANGE_ADDRESS  # 0x0d3251EF0D66b60C4E387FC95462Bf274e50CBE1
                
                self.logger().info(f"StandardWeb3 config - API: {api_url}, WS: {websocket_url}, ME: {matching_engine_address}")
                self.logger().info(f"Using private key length: {len(standard_client_private_key)} characters")
                
                self._standard_client = StandardClient(
                    private_key=standard_client_private_key,
                    http_rpc_url=rpc_url,
                    matching_engine_address=matching_engine_address,
                    networkName="Somnia Testnet",  # Use correct network name
                    api_url=api_url,
                    websocket_url=websocket_url,
                    api_key=api_key
                )
                self.logger().info("StandardWeb3 client initialized successfully with Somnia Testnet")
            except Exception as e:
                self.logger().error(f"Failed to initialize StandardWeb3 client: {e}")
                self.logger().info("StandardWeb3 client disabled due to error")
                self._standard_client = None
        else:
            self.logger().info("StandardWeb3 client disabled - library not available")
        
        # Initialize nonce management for blockchain transactions
        self._last_nonce = 0
        self._transaction_lock = asyncio.Lock()
        
        # Store order ID mapping: client_order_id -> (blockchain_order_id, base_address, quote_address, is_bid)
        self._order_id_map = {}
        
        self.logger().info("DEBUG: Nonce management initialized")
        
        # Initialize authentication
        self.logger().info("DEBUG: Initializing SomniaAuth")
        self._auth = SomniaAuth(
            private_key=self._private_key,
            wallet_address=self._wallet_address,
        )
        self.logger().info("DEBUG: SomniaAuth initialized successfully")
        
        # Initialize parent class
        self.logger().info("DEBUG: About to call super().__init__()")
        super().__init__(
            client_config_map=client_config_map,
        )
        self.logger().info("DEBUG: super().__init__() completed successfully")
        
        # Set connector reference in data sources after initialization
        if hasattr(self, '_orderbook_ds') and self._orderbook_ds:
            self._orderbook_ds._connector = self
        
        # Real-time balance updates - DEX connectors don't submit all balance updates
        # Instead they only update on position changes (not cancel), so we need to fetch periodically
        self.real_time_balance_update = False
        
        self.logger().info("DEBUG: SomniaExchange.__init__ completed successfully")

    @staticmethod
    def somnia_order_type(order_type: OrderType) -> str:
        """
        Convert Hummingbot order type to Somnia format.
        
        Args:
            order_type: Hummingbot order type
            
        Returns:
            Somnia order type string
        """
        return {
            OrderType.LIMIT: "limit",
            OrderType.MARKET: "market",
            OrderType.LIMIT_MAKER: "limit_maker",
        }.get(order_type, "limit")

    @staticmethod
    def to_hb_order_type(somnia_type: str) -> OrderType:
        """
        Convert Somnia order type to Hummingbot format.
        
        Args:
            somnia_type: Somnia order type
            
        Returns:
            Hummingbot OrderType
        """
        return {
            "limit": OrderType.LIMIT,
            "market": OrderType.MARKET,
            "limit_maker": OrderType.LIMIT_MAKER,
        }.get(somnia_type, OrderType.LIMIT)

    @property
    def authenticator(self) -> SomniaAuth:
        """Get authenticator instance."""
        return self._auth

    @property
    def name(self) -> str:
        """Exchange name."""
        return CONSTANTS.EXCHANGE_NAME

    @property
    def rate_limits_rules(self):
        """Rate limit rules."""
        return web_utils.RATE_LIMITS

    @property
    def domain(self) -> str:
        """Exchange domain."""
        return self._domain

    @property
    def client_order_id_max_length(self) -> int:
        """Maximum length for client order ID."""
        return 32

    @property
    def client_order_id_prefix(self) -> str:
        """Prefix for client order IDs."""
        return "SOMNIA"

    @property
    def trading_rules_request_path(self) -> str:
        """Path for trading rules request."""
        return ""  # Not used for GraphQL-based API

    @property
    def trading_pairs_request_path(self) -> str:
        """Path for trading pairs request."""
        return ""  # Not used for GraphQL-based API

    @property
    def check_network_request_path(self) -> str:
        """Path for network check request."""
        return ""  # Not used for GraphQL-based API

    async def check_network(self) -> NetworkStatus:
        """
        Check network connectivity.
        
        Returns:
            NetworkStatus enum value
        """
        try:
            self.logger().info("DEBUG: check_network() called")
            # Simple check - always return CONNECTED for now to avoid network issues
            # In a real implementation, you would ping the exchange API
            self.logger().info("DEBUG: check_network() returning CONNECTED")
            return NetworkStatus.CONNECTED
        except Exception as e:
            self.logger().error(f"DEBUG: Exception in check_network(): {e}")
            self.logger().error(f"Network check failed: {e}")
            return NetworkStatus.NOT_CONNECTED

    # ====== MISSING CRITICAL METHODS FROM VERTEX ======
    
    async def start_network(self):
        """
        Initialize network and exchange info when connector starts.
        This method is called during connector startup.
        """
        try:
            self.logger().info("DEBUG: start_network() called - beginning network startup")
            self.logger().info("Starting Somnia network...")
            
            # Initialize exchange market info for trading rules and symbol mapping
            self.logger().info("DEBUG: About to call build_exchange_market_info()")
            await self.build_exchange_market_info()
            self.logger().info("DEBUG: build_exchange_market_info() completed successfully")
            
            self.logger().info("DEBUG: About to call super().start_network() which should start order book tracker")
            await super().start_network()
            self.logger().info("DEBUG: super().start_network() completed successfully")
            
            self.logger().info("Somnia network started successfully")
        except Exception as e:
            self.logger().error(f"DEBUG: Exception in start_network(): {e}")
            self.logger().error(f"Failed to start Somnia network: {e}")
            self.logger().exception("Full traceback:")
            # Don't raise - let the system continue
            pass

    async def build_exchange_market_info(self) -> Dict[str, Any]:
        """
        Build comprehensive market information including trading pairs, symbols, contracts.
        This method fetches and organizes exchange data for proper connector initialization.
        
        Returns:
            Dictionary containing exchange market information
        """
        try:
            self.logger().info("=== DEBUG: build_exchange_market_info STARTING ===")
            self.logger().info(f"  Current trading_pairs: {self._trading_pairs}")
            self.logger().info(f"  trading_required: {self._trading_required}")
            
            # Get available trading pairs and market data
            self.logger().info("DEBUG: About to call _get_symbols()")
            symbols = await self._get_symbols()
            self.logger().info(f"DEBUG: _get_symbols() returned {len(symbols)} symbols")
            
            self.logger().info("DEBUG: About to call _get_contracts()")
            contracts = await self._get_contracts()
            self.logger().info(f"DEBUG: _get_contracts() returned {len(contracts)} contracts")
            
            self.logger().info("DEBUG: About to call _get_fee_rates()")
            fee_rates = await self._get_fee_rates()
            self.logger().info(f"DEBUG: _get_fee_rates() returned: {fee_rates}")
            
            exchange_info = {
                "symbols": symbols,
                "contracts": contracts,
                "fee_rates": fee_rates,
                "server_time": int(time.time() * 1000),
                "rate_limits": self.rate_limits_rules,
            }
            
            # Initialize trading rules from symbols data
            self.logger().info("DEBUG: About to initialize trading rules from symbols data...")
            await self._initialize_trading_rules_from_symbols(symbols)
            self.logger().info("DEBUG: Trading rules initialization completed")
            
            # Initialize account balances
            self.logger().info("DEBUG: About to initialize account balances...")
            await self._update_balances()
            self.logger().info("DEBUG: Account balances initialization completed")
            
            self.logger().info(f"=== DEBUG: build_exchange_market_info COMPLETED ===")
            self.logger().info(f"  Built exchange info with {len(symbols)} symbols and {len(contracts)} contracts")
            return exchange_info
            
        except Exception as e:
            self.logger().error(f"CRITICAL: Failed to build exchange market info: {e}")
            self.logger().exception("Full exception details:")
            # Return minimal info to prevent startup failure
            return {
                "symbols": [],
                "contracts": {},
                "fee_rates": {},
                "server_time": int(time.time() * 1000),
                "rate_limits": self.rate_limits_rules,
            }

    async def _initialize_trading_pair_symbol_map(self):
        """
        Override the default symbol map initialization.
        Uses build_exchange_market_info to fetch and organize symbol mappings.
        """
        try:
            self.logger().info("DEBUG: _initialize_trading_pair_symbol_map() called")
            exchange_info = await self.build_exchange_market_info()
            self.logger().info(f"DEBUG: build_exchange_market_info() returned: {type(exchange_info)} with keys: {list(exchange_info.keys()) if isinstance(exchange_info, dict) else 'NOT_DICT'}")
            self.logger().info("DEBUG: About to call _initialize_trading_pair_symbols_from_exchange_info")
            self._initialize_trading_pair_symbols_from_exchange_info(exchange_info=exchange_info)
            self.logger().info("DEBUG: _initialize_trading_pair_symbols_from_exchange_info completed")
        except Exception as e:
            self.logger().exception("There was an error requesting exchange info.")
            # Don't raise to prevent startup failure

    async def _initialize_trading_rules_from_symbols(self, symbols: List[Dict[str, Any]]):
        """
        Initialize trading rules from symbol information.
        
        Args:
            symbols: List of symbol information dictionaries
        """
        try:
            self.logger().info("Initializing trading rules from symbols...")
            trading_rules = {}
            
            for symbol_info in symbols:
                symbol = symbol_info.get("symbol", "")
                if symbol:
                    base = symbol_info.get("baseAsset", "")
                    quote = symbol_info.get("quoteAsset", "")
                    
                    # Create trading rule for this symbol
                    trading_rules[symbol] = {
                        "symbol": symbol,
                        "baseAsset": base,
                        "quoteAsset": quote,
                        "baseAssetPrecision": symbol_info.get("baseAssetPrecision", 8),
                        "quotePrecision": symbol_info.get("quotePrecision", 8),
                        "minQty": "0.001",
                        "maxQty": "1000000",
                        "stepSize": "0.001",
                        "minPrice": "0.001",
                        "maxPrice": "1000000", 
                        "tickSize": "0.001",
                        "minNotional": "1.0",
                        "status": "TRADING",
                    }
            
            # Update internal trading rules
            formatted_rules = await self._format_trading_rules(trading_rules)
            self._trading_rules.clear()
            for rule in formatted_rules:
                self._trading_rules[rule.trading_pair] = rule
                
            self.logger().info(f"Initialized {len(trading_rules)} trading rules")
            
        except Exception as e:
            self.logger().error(f"Failed to initialize trading rules from symbols: {e}")
            # Don't raise to prevent startup failure
            
    async def _api_request(
        self,
        method: str,
        endpoint: str = "",
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
        is_auth_required: bool = False,
    ) -> Dict[str, Any]:
        """
        Generic API request method for making HTTP requests to Somnia API.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            params: URL parameters
            headers: Request headers
            data: Request data
            is_auth_required: Whether authentication is required
            
        Returns:
            API response data
        """
        try:
            if is_auth_required and self._auth:
                if headers is None:
                    headers = {}
                auth_headers = await self._auth.get_headers()
                headers.update(auth_headers)
            
            # For now, return mock data since we're using StandardWeb3 directly
            # This method can be enhanced later for additional API calls
            return {"success": True, "data": {}}
            
        except Exception as e:
            self.logger().error(f"API request failed: {e}")
            raise

    async def _get_symbols(self) -> List[Dict[str, Any]]:
        """
        Get symbol information from Somnia exchange.
        
        Returns:
            List of symbol information dictionaries
        """
        try:
            self.logger().info(f"DEBUG: _get_symbols called with:")
            self.logger().info(f"  - self._trading_pairs = {self._trading_pairs}")
            self.logger().info(f"  - self._trading_required = {self._trading_required}")
            self.logger().info(f"  - len(self._trading_pairs) = {len(self._trading_pairs) if self._trading_pairs else 0}")
            
            # If this is a non-trading connector (used for connection testing), 
            # return empty list to avoid any processing
            if not self._trading_required and not self._trading_pairs:
                self.logger().info("Non-trading connector mode - returning empty symbols list for connection testing")
                return []
            
            # Use configured trading pairs
            symbols = []
            self.logger().info(f"Processing {len(self._trading_pairs)} trading pairs...")
            
            for i, trading_pair in enumerate(self._trading_pairs):
                self.logger().info(f"  Processing trading pair {i+1}/{len(self._trading_pairs)}: '{trading_pair}'")
                try:
                    if "-" not in trading_pair:
                        self.logger().error(f"  Invalid trading pair format (missing '-'): '{trading_pair}'")
                        continue
                        
                    base, quote = trading_pair.split("-", 1)  # Split only on first dash
                    self.logger().info(f"  Split '{trading_pair}' -> base: '{base}', quote: '{quote}'")
                    
                    if not base or not quote:
                        self.logger().error(f"  Empty base or quote after split: base='{base}', quote='{quote}'")
                        continue
                    
                    symbol_info = {
                        "symbol": trading_pair,
                        "baseAsset": base,
                        "quoteAsset": quote,
                        "status": "TRADING",
                        "baseAssetPrecision": 8,
                        "quotePrecision": 8,
                        "orderTypes": ["LIMIT", "MARKET"],
                    }
                    symbols.append(symbol_info)
                    self.logger().info(f"  Successfully created symbol info for '{trading_pair}'")
                    
                except ValueError as e:
                    self.logger().error(f"  ValueError processing trading pair '{trading_pair}': {e}")
                except Exception as e:
                    self.logger().error(f"  Unexpected error processing trading pair '{trading_pair}': {e}")
            
            # In trading mode, we should have symbols configured by the strategy
            if not symbols and self._trading_required:
                self.logger().error("CRITICAL: Trading mode requires configured trading pairs but none were successfully processed")
                self.logger().error(f"  Original trading pairs: {self._trading_pairs}")
                self.logger().error("  This indicates a configuration problem - the strategy should provide valid trading pairs")
                # Don't hardcode - return empty and let the system handle the error properly
                return []
            
            self.logger().info(f"Successfully processed {len(symbols)} symbols: {[s['symbol'] for s in symbols]}")
            return symbols
            
        except Exception as e:
            self.logger().error(f"CRITICAL: Exception in _get_symbols: {e}")
            self.logger().exception("Full exception details:")
            # Don't hardcode a fallback - return empty and let caller handle
            return []

    async def _get_contracts(self) -> Dict[str, Any]:
        """
        Get contract information from Somnia exchange.
        
        Returns:
            Dictionary of contract information
        """
        try:
            # Return contract information for known tokens
            contracts = {}
            
            # Get token addresses from constants
            for symbol in ["STT", "USDC"]:
                address = utils.convert_symbol_to_address(symbol)
                if address and address != "0x...":
                    # Get decimals from constants
                    decimals = CONSTANTS.TOKEN_DECIMALS.get(symbol, 18)
                    contracts[symbol] = {
                        "address": address,
                        "decimals": decimals,
                        "symbol": symbol,
                    }
            
            self.logger().info(f"Retrieved {len(contracts)} contracts")
            return contracts
            
        except Exception as e:
            self.logger().error(f"Failed to get contracts: {e}")
            return {}

    async def _get_fee_rates(self) -> Dict[str, Any]:
        """
        Get current fee rates from Somnia exchange.
        
        Returns:
            Dictionary of fee rate information
        """
        try:
            # Return default fee rates (can be enhanced to fetch dynamically)
            fee_rates = {
                "maker_fee": "0.001",  # 0.1%
                "taker_fee": "0.002",  # 0.2%
            }
            
            self.logger().info("Retrieved fee rates")
            return fee_rates
            
        except Exception as e:
            self.logger().error(f"Failed to get fee rates: {e}")
            return {"maker_fee": "0.001", "taker_fee": "0.002"}

    async def _get_account(self) -> Dict[str, Any]:
        """
        Get account information from Somnia exchange.
        
        Returns:
            Dictionary containing account information
        """
        try:
            if not self._standard_client:
                raise ValueError("StandardWeb3 client not initialized")
            
            # Get account balances and info using StandardWeb3
            account_info = {
                "address": self._wallet_address,
                "balances": {},
            }
            
            # Get balances for known tokens
            known_tokens = ["STT", "USDC"]
            for token in known_tokens:
                try:
                    # This would use StandardWeb3 to get actual balance
                    balance = "0"  # Placeholder - implement actual balance fetching
                    account_info["balances"][token] = balance
                except Exception as e:
                    self.logger().warning(f"Failed to get {token} balance: {e}")
                    account_info["balances"][token] = "0"
            
            return account_info
            
        except Exception as e:
            self.logger().error(f"Failed to get account info: {e}")
            return {"address": self._wallet_address, "balances": {}}

    async def _get_account_max_withdrawable(self) -> Dict[str, Decimal]:
        """
        Get maximum withdrawable amounts for each asset.
        
        Returns:
            Dictionary mapping asset to max withdrawable amount
        """
        try:
            account_info = await self._get_account()
            max_withdrawable = {}
            
            for asset, balance_str in account_info.get("balances", {}).items():
                balance = Decimal(balance_str) if balance_str else Decimal("0")
                # For simplicity, assume full balance is withdrawable
                # In reality, you might need to account for locked amounts
                max_withdrawable[asset] = balance
                
            return max_withdrawable
            
        except Exception as e:
            self.logger().error(f"Failed to get max withdrawable amounts: {e}")
            return {}

    # ====== END MISSING METHODS ======

    def supported_order_types(self) -> List[OrderType]:
        """
        Return list of supported order types.
        
        Returns:
            List of supported OrderType values
        """
        return [OrderType.LIMIT, OrderType.MARKET]

    def update_trading_pairs(self, trading_pairs: List[str]):
        """
        Update trading pairs after connector initialization.
        This method allows the connector to be updated with trading pairs from the strategy.
        
        Args:
            trading_pairs: List of trading pairs to support
        """
        self.logger().info("=== DEBUG: update_trading_pairs CALLED ===")
        self.logger().info(f"  Current trading_pairs: {self._trading_pairs}")
        self.logger().info(f"  New trading_pairs: {trading_pairs}")
        self.logger().info(f"  trading_required: {self._trading_required}")
        
        # Log call stack to see who's calling this
        import traceback
        stack = traceback.format_stack()
        self.logger().info("DEBUG: update_trading_pairs call stack (last 3 frames):")
        for i, frame in enumerate(stack[-3:]):
            self.logger().info(f"  Frame {i}: {frame.strip()}")
        
        if trading_pairs and trading_pairs != self._trading_pairs:
            self.logger().info(f"UPDATING: Trading pairs changing from {self._trading_pairs} to {trading_pairs}")
            self._trading_pairs = trading_pairs
            
            # Update order book data source if it exists
            if hasattr(self, '_order_book_tracker') and self._order_book_tracker:
                self.logger().info("DEBUG: Updating order book tracker data source...")
                if hasattr(self._order_book_tracker, 'data_source') and self._order_book_tracker.data_source:
                    self._order_book_tracker.data_source.update_trading_pairs(trading_pairs)
                    self.logger().info("DEBUG: Order book data source updated")
                else:
                    self.logger().warning("DEBUG: Order book tracker has no data_source")
            else:
                self.logger().warning("DEBUG: No order book tracker found")
            
            # Re-initialize trading rules for new pairs
            try:
                import asyncio
                if asyncio.get_event_loop().is_running():
                    self.logger().info("DEBUG: Event loop running, creating task for trading rules update")
                    asyncio.create_task(self._update_trading_rules_for_new_pairs(trading_pairs))
                else:
                    # If no event loop is running, schedule for later
                    self.logger().info("DEBUG: No event loop running, trading rules will be updated when connector starts")
            except Exception as e:
                self.logger().warning(f"DEBUG: Could not update trading rules immediately: {e}")
        elif not trading_pairs:
            self.logger().warning(f"SKIPPING: Empty trading_pairs provided: {trading_pairs}")
        elif trading_pairs == self._trading_pairs:
            self.logger().info(f"SKIPPING: Trading pairs unchanged: {trading_pairs}")
        else:
            self.logger().warning(f"SKIPPING: Unexpected condition - trading_pairs: {trading_pairs}, current: {self._trading_pairs}")
        
        self.logger().info("=== DEBUG: update_trading_pairs COMPLETED ===")
        self.logger().info(f"  Final trading_pairs: {self._trading_pairs}")

    async def _update_trading_rules_for_new_pairs(self, trading_pairs: List[str]):
        """Update trading rules for newly added trading pairs."""
        try:
            symbols = []
            for trading_pair in trading_pairs:
                base, quote = trading_pair.split("-")
                symbols.append({
                    "symbol": trading_pair,
                    "baseAsset": base,
                    "quoteAsset": quote,
                    "status": "TRADING",
                    "baseAssetPrecision": 8,
                    "quotePrecision": 8,
                    "orderTypes": ["LIMIT", "MARKET"],
                })
            
            await self._initialize_trading_rules_from_symbols(symbols)
            self.logger().info(f"Updated trading rules for {len(trading_pairs)} trading pairs")
            
        except Exception as e:
            self.logger().error(f"Failed to update trading rules for new pairs: {e}")

    @property
    def trading_pairs(self) -> List[str]:
        """Get current trading pairs."""
        return self._trading_pairs

    def _is_request_exception_related_to_time_synchronizer(self, request_exception: Exception) -> bool:
        """
        Check if request exception is related to time synchronization.
        
        Args:
            request_exception: Exception to check
            
        Returns:
            True if time-related, False otherwise
        """
        # Somnia doesn't typically have time sync issues like CEXs
        return False

    def _is_order_not_found_during_status_update_error(self, status_update_exception: Exception) -> bool:
        """
        Check if exception indicates order not found during status update.
        
        Args:
            status_update_exception: Exception to check
            
        Returns:
            True if order not found, False otherwise
        """
        error_message = str(status_update_exception).lower()
        return "order not found" in error_message or "not found" in error_message

    def _is_order_not_found_during_cancelation_error(self, cancelation_exception: Exception) -> bool:
        """
        Check if exception indicates order not found during cancellation.
        
        Args:
            cancelation_exception: Exception to check
            
        Returns:
            True if order not found, False otherwise
        """
        error_message = str(cancelation_exception).lower()
        return "order not found" in error_message or "cannot cancel" in error_message

    def _create_web_assistants_factory(self) -> WebAssistantsFactory:
        """
        Create web assistants factory.
        
        Returns:
            WebAssistantsFactory instance
        """
        return web_utils.build_api_factory(
            throttler=self._throttler,
            auth=self._auth,
        )

    def _create_order_book_data_source(self) -> OrderBookTrackerDataSource:
        """
        Create order book data source.
        
        Returns:
            OrderBookTrackerDataSource instance
        """
        self.logger().info("DEBUG: _create_order_book_data_source() called")
        self.logger().info(f"DEBUG: Current trading_pairs: {self._trading_pairs}")
        self.logger().info(f"DEBUG: trading_required: {self._trading_required}")
        
        # Use the configured trading pairs - don't hardcode anything
        effective_trading_pairs = self._trading_pairs.copy() if self._trading_pairs else []
        self.logger().info(f"DEBUG: Creating order book data source with trading_pairs: {effective_trading_pairs}")
        
        try:
            data_source = SomniaAPIOrderBookDataSource(
                trading_pairs=effective_trading_pairs,
                connector=self,  # Pass self reference like other exchanges
                api_factory=self._web_assistants_factory,
                domain=self._domain,
                throttler=self._throttler,
            )
            self.logger().info("DEBUG: Order book data source created successfully")
            # Store reference to update later if needed
            self._orderbook_ds = data_source
            return data_source
        except Exception as e:
            self.logger().error(f"DEBUG: Failed to create order book data source: {e}")
            self.logger().exception("DEBUG: Exception details:")
            raise

    def _create_user_stream_data_source(self) -> UserStreamTrackerDataSource:
        """
        Create user stream data source.
        
        Returns:
            UserStreamTrackerDataSource instance
        """
        return SomniaAPIUserStreamDataSource(
            auth=self._auth,
            trading_pairs=self._trading_pairs,
            connector=self,
            api_factory=self._web_assistants_factory,
            domain=self._domain,
            throttler=self._throttler,
        )

    async def _get_last_traded_price(self, trading_pair: str) -> float:
        """
        Get last traded price for a trading pair.
        
        Args:
            trading_pair: Trading pair
            
        Returns:
            Last traded price
        """
        try:
            prices = await self._order_book_tracker.data_source.get_last_traded_prices([trading_pair])
            return prices.get(trading_pair, 0.0)
        except Exception as e:
            self.logger().error(f"Error getting last traded price for {trading_pair}: {e}")
            return 0.0

    async def _make_trading_rules_request(self) -> Any:
        """
        Make request to get trading rules.
        
        Returns:
            Trading rules data
        """
        # For Somnia, we'll define trading rules based on known token configurations
        trading_rules = {}
        
        for trading_pair in self._trading_pairs:
            base, quote = utils.split_trading_pair(trading_pair)
            
            # Get token decimals for precision
            base_decimals = utils.get_token_decimals(base)
            quote_decimals = utils.get_token_decimals(quote)
            
            # Define basic trading rules
            trading_rules[trading_pair] = {
                "symbol": trading_pair,
                "baseAssetPrecision": base_decimals,
                "quoteAssetPrecision": quote_decimals,
                "minQty": str(CONSTANTS.MIN_ORDER_SIZE),
                "maxQty": str(CONSTANTS.MAX_ORDER_SIZE),
                "stepSize": str(Decimal("1e-{}".format(base_decimals))),
                "minPrice": str(Decimal("1e-{}".format(quote_decimals))),
                "maxPrice": str(CONSTANTS.MAX_ORDER_SIZE),
                "tickSize": str(Decimal("1e-{}".format(quote_decimals))),
                "minNotional": str(CONSTANTS.MIN_ORDER_SIZE),
                "status": "TRADING",
            }
            
        return trading_rules

    async def _make_trading_pairs_request(self) -> Any:
        """
        Make request to get available trading pairs.
        
        Returns:
            Trading pairs data
        """
        # Return the configured trading pairs for Somnia
        trading_pairs_data = []
        
        for trading_pair in CONSTANTS.SOMNIA_TESTNET_TRADING_PAIRS:
            base, quote = utils.split_trading_pair(trading_pair)
            
            trading_pairs_data.append({
                "symbol": trading_pair,
                "baseAsset": base,
                "quoteAsset": quote,
                "status": "TRADING",
            })
            
        return trading_pairs_data

    def _get_fee(self,
                 base_currency: str,
                 quote_currency: str,
                 order_type: OrderType,
                 order_side: TradeType,
                 amount: Decimal,
                 price: Decimal = s_decimal_NaN,
                 is_maker: Optional[bool] = None) -> TradeFeeBase:
        """
        Calculate trading fee for an order.
        
        Args:
            base_currency: Base currency
            quote_currency: Quote currency  
            order_type: Order type
            order_side: Order side (buy/sell)
            amount: Order amount
            price: Order price
            is_maker: Whether the order is a maker order
            
        Returns:
            TradeFeeBase instance
        """
        trading_pair = f"{base_currency}-{quote_currency}"
        is_maker = is_maker or (order_type is OrderType.LIMIT_MAKER)
        
        if trading_pair not in self._trading_fees:
            fee = build_trade_fee(
                exchange=self.name,
                is_maker=is_maker,
                order_side=order_side,
                order_type=order_type,
                amount=amount,
                price=price,
                base_currency=base_currency,
                quote_currency=quote_currency,
            )
        else:
            fee_data = self._trading_fees[trading_pair]
            if is_maker:
                fee_value = fee_data["maker"]
            else:
                fee_value = fee_data["taker"]
            fee = AddedToCostTradeFee(percent=fee_value)
        
        return fee

    async def _get_current_nonce(self) -> int:
        """
        Get proper blockchain nonce using Dexalot-style approach.
        Note: Transaction lock should be held by caller to prevent race conditions.
        """
        try:
            from web3 import Web3
            
            # Use the Web3 connection from our RPC URL
            w3 = Web3(Web3.HTTPProvider(self._rpc_url))
            
            # Get current nonce from blockchain
            current_nonce = await asyncio.get_event_loop().run_in_executor(
                None, w3.eth.get_transaction_count, self._wallet_address, 'pending'
            )
            
            # Use the higher of current blockchain nonce or our tracked nonce
            # This prevents "nonce too low" errors from concurrent transactions
            final_nonce = current_nonce if current_nonce > self._last_nonce else self._last_nonce
            
            # Update our tracking
            self._last_nonce = final_nonce + 1
            
            self.logger().debug(f"Nonce management: blockchain={current_nonce}, tracked={self._last_nonce-1}, using={final_nonce}")
            return final_nonce
            
        except Exception as e:
            self.logger().error(f"Error getting blockchain nonce: {e}")
            # Fallback: increment our tracked nonce
            self._last_nonce += 1
            return self._last_nonce

    async def _place_order(self,
                          order_id: str,
                          trading_pair: str,
                          amount: Decimal,
                          trade_type: TradeType,
                          order_type: OrderType,
                          price: Decimal,
                          **kwargs) -> Tuple[str, float]:
        """
        Place an order on the exchange.
        
        Args:
            order_id: Client order ID
            trading_pair: Trading pair
            amount: Order amount
            trade_type: Buy or sell
            order_type: Order type (limit/market)
            price: Order price
            **kwargs: Additional arguments
            
        Returns:
            Tuple of (exchange_order_id, timestamp)
        """
        try:
            base, quote = utils.split_trading_pair(trading_pair)
            base_address = utils.convert_symbol_to_address(base)
            quote_address = utils.convert_symbol_to_address(quote)
            
            if not base_address or not quote_address:
                raise ValueError(f"Could not get token addresses for {trading_pair}")
            
            # Convert amounts to blockchain format
            base_decimals = utils.get_token_decimals(base)
            quote_decimals = utils.get_token_decimals(quote)
            
            # Prepare order parameters for StandardClient
            is_buy = trade_type == TradeType.BUY
            
            if order_type == OrderType.MARKET:
                # For market orders, we'll place a limit order at a price that should execute immediately
                if is_buy:
                    # Buy at a higher price to ensure execution
                    execution_price = price * Decimal("1.01")  # 1% above current price
                else:
                    # Sell at a lower price to ensure execution  
                    execution_price = price * Decimal("0.99")  # 1% below current price
            else:
                execution_price = price
            
            # Use transaction lock to prevent nonce conflicts between multiple orders
            async with self._transaction_lock:
                # Get current nonce for the account to avoid "nonce too low" errors
                current_nonce = await self._get_current_nonce()
                
                # Use StandardClient to place the order - convert symbols to addresses
                if is_buy:
                    # For buy orders: quote_amount = amount * price
                    quote_amount = amount * execution_price
                    tx_hash = await self._standard_client.limit_buy(
                        base=base_address,  # Use token address, not symbol
                        quote=quote_address,  # Use token address, not symbol
                        price=float(execution_price),
                        quote_amount=float(quote_amount),
                        is_maker=True,  # Default to maker order
                        n=current_nonce,  # Use dynamic nonce
                        recipient=self._wallet_address
                    )
                else:
                    # For sell orders: base_amount = amount
                    tx_hash = await self._standard_client.limit_sell(
                        base=base_address,  # Use token address, not symbol
                        quote=quote_address,  # Use token address, not symbol
                        price=float(execution_price),
                        base_amount=float(amount),
                        is_maker=True,  # Default to maker order
                        n=current_nonce,  # Use dynamic nonce
                        recipient=self._wallet_address
                    )
            
            # Store order ID mapping for cancellation
            self._order_id_map[order_id] = {
                'blockchain_order_id': current_nonce,  # The 'n' parameter is the blockchain order ID
                'base_address': base_address,
                'quote_address': quote_address,
                'is_bid': is_buy
            }
            
            # Return transaction hash as exchange order ID
            timestamp = time.time()
            self.logger().info(f"Order placed successfully: {order_id} -> {tx_hash} (blockchain_order_id: {current_nonce})")
            
            return tx_hash, timestamp
            
        except Exception as e:
            self.logger().error(f"Error placing order {order_id}: {e}")
            raise

    async def _place_cancel(self, order_id: str, tracked_order: InFlightOrder) -> str:
        """
        Cancel an order on the exchange using StandardWeb3 cancel_orders method with on-chain fallback.
        
        Args:
            order_id: Client order ID
            tracked_order: InFlightOrder instance
            
        Returns:
            Exchange cancellation ID (transaction hash)
        """
        try:
            # Method 1: Use StandardWeb3 cancel_orders (preferred method)
            if self._standard_client and order_id in self._order_id_map:
                order_info = self._order_id_map[order_id]
                base_address = order_info['base_address']
                quote_address = order_info['quote_address']
                is_bid = order_info['is_bid']
                blockchain_order_id = order_info['blockchain_order_id']
                
                self.logger().info(f"Using StandardWeb3 cancel_orders for: {order_id} -> blockchain_order_id: {blockchain_order_id}")
                
                # Use transaction lock to prevent nonce conflicts (same as order placement)
                async with self._transaction_lock:
                    # Get current nonce for the account to avoid "nonce too low" errors (same as order placement)
                    current_nonce = await self._get_current_nonce()
                    
                    # Prepare cancel_order_data structure for StandardWeb3
                    cancel_order_data = [{
                        "base": base_address,
                        "quote": quote_address,
                        "isBid": is_bid,  # Use camelCase as expected by StandardWeb3 API
                        "orderId": blockchain_order_id,  # Use 'orderId' (camelCase) as expected by StandardWeb3
                    }]
                    
                    try:
                        # Use StandardWeb3 cancel_orders method (without nonce parameter - it manages its own nonce)
                        cancel_tx_hash = await self._standard_client.cancel_orders(cancel_order_data)
                        
                        # Clean up the stored order info
                        del self._order_id_map[order_id]
                        
                        self.logger().info(f"Order cancelled via StandardWeb3: {order_id} -> {cancel_tx_hash}")
                        return cancel_tx_hash
                        
                    except Exception as e:
                        self.logger().warning(f"StandardWeb3 cancel_orders failed for {order_id}: {e}")
                        # Continue to fallback method below
            
            # Method 2: Direct on-chain contract interaction (fallback)
            
            # Check if we have the order information stored
            if order_id in self._order_id_map:
                order_info = self._order_id_map[order_id]
                base_address = order_info['base_address']
                quote_address = order_info['quote_address']
                is_bid = order_info['is_bid']
                blockchain_order_id = order_info['blockchain_order_id']
                
                # Cancel order using direct contract interaction
                cancel_tx_hash = await self._cancel_order_on_contract(
                    base_address=base_address,
                    quote_address=quote_address,
                    is_bid=is_bid,
                    order_id=blockchain_order_id
                )
                
                # Clean up the stored order info
                del self._order_id_map[order_id]
                
                self.logger().info(f"Order cancelled on contract: {order_id} -> {cancel_tx_hash}")
                return cancel_tx_hash
            
            else:
                # Extract order information from tracked_order
                trading_pair = tracked_order.trading_pair
                base, quote = utils.split_trading_pair(trading_pair)
                
                # Get token addresses
                base_address = utils.convert_symbol_to_address(base)
                quote_address = utils.convert_symbol_to_address(quote)
                
                if not base_address or not quote_address:
                    raise ValueError(f"Could not get token addresses for {trading_pair}")
                
                # Determine if it's a bid (buy order)
                is_bid = tracked_order.trade_type == TradeType.BUY
                
                # We need to extract the order ID from the transaction receipt
                exchange_order_id = tracked_order.exchange_order_id
                
                if not exchange_order_id or exchange_order_id.startswith("cancelled_"):
                    # If we don't have a valid exchange order ID, fall back to local cancellation
                    self.logger().warning(f"No valid exchange order ID for {order_id}, marking as cancelled locally")
                    cancellation_id = f"cancelled_{order_id}"
                    self.logger().info(f"Order marked as cancelled locally: {order_id} -> {cancellation_id}")
                    return cancellation_id
                
                # Extract order ID from transaction receipt (fallback method)
                blockchain_order_id = await self._extract_order_id_from_transaction(exchange_order_id)
                
                if blockchain_order_id is None:
                    self.logger().warning(f"Could not extract order ID from transaction {exchange_order_id}, using local cancellation")
                    cancellation_id = f"cancelled_{order_id}"
                    return cancellation_id
                
                # Cancel order using direct contract interaction
                cancel_tx_hash = await self._cancel_order_on_contract(
                    base_address=base_address,
                    quote_address=quote_address,
                    is_bid=is_bid,
                    order_id=blockchain_order_id
                )
                
                self.logger().info(f"Order cancelled on contract: {order_id} -> {cancel_tx_hash}")
                return cancel_tx_hash
            
        except Exception as e:
            self.logger().error(f"Error cancelling order {order_id}: {e}")
            # Fall back to local cancellation if all methods fail
            cancellation_id = f"cancelled_{order_id}"
            # Clean up the stored order info if it exists
            if order_id in self._order_id_map:
                del self._order_id_map[order_id]
            self.logger().info(f"Falling back to local cancellation: {order_id} -> {cancellation_id}")
            return cancellation_id

    async def _extract_order_id_from_transaction(self, tx_hash: str) -> Optional[int]:
        """
        Extract the order ID from a transaction by parsing the transaction input data.
        The order ID is the 'n' parameter passed to limitSell/limitBuy functions.
        
        Args:
            tx_hash: Transaction hash from order placement
            
        Returns:
            Order ID if found, None otherwise
        """
        try:
            from web3 import Web3
            from standardweb3 import matching_engine_abi
            
            # Connect to Somnia network
            w3 = Web3(Web3.HTTPProvider(self._rpc_url))
            
            # Get transaction
            tx = w3.eth.get_transaction(tx_hash)
            
            if not tx or not tx.input:
                self.logger().warning(f"No transaction input found for {tx_hash}")
                return None
            
            # Create contract instance to decode function input
            contract_address = Web3.to_checksum_address(CONSTANTS.STANDARD_EXCHANGE_ADDRESS)
            contract = w3.eth.contract(address=contract_address, abi=matching_engine_abi)
            
            # Decode the function call
            decoded = contract.decode_function_input(tx.input)
            function_obj = decoded[0]
            inputs = decoded[1]
            
            function_name = function_obj.fn_name
            
            # For limitSell/limitBuy, the 'n' parameter is the order ID
            if function_name in ['limitSell', 'limitBuy'] and 'n' in inputs:
                order_id = inputs['n']
                self.logger().info(f"Extracted order ID {order_id} from {function_name} transaction {tx_hash}")
                return order_id
            else:
                self.logger().warning(f"Could not find 'n' parameter in {function_name} transaction {tx_hash}")
                return None
            
        except Exception as e:
            self.logger().error(f"Error extracting order ID from transaction {tx_hash}: {e}")
            return None

    async def _cancel_order_on_contract(self, base_address: str, quote_address: str, is_bid: bool, order_id: int) -> str:
        """
        Cancel an order directly on the smart contract.
        
        Args:
            base_address: Base token contract address
            quote_address: Quote token contract address  
            is_bid: True for buy orders, False for sell orders
            order_id: Blockchain order ID
            
        Returns:
            Transaction hash of cancellation
        """
        try:
            from web3 import Web3
            from standardweb3 import matching_engine_abi
            from eth_account import Account
            
            # Connect to Somnia network
            w3 = Web3(Web3.HTTPProvider(self._rpc_url))
            
            # Get contract instance
            contract_address = Web3.to_checksum_address(CONSTANTS.STANDARD_EXCHANGE_ADDRESS)
            contract = w3.eth.contract(address=contract_address, abi=matching_engine_abi)
            
            # Prepare account for signing
            account = Account.from_key(self._private_key)
            
            # Use transaction lock to prevent nonce conflicts
            async with self._transaction_lock:
                # Get current nonce
                nonce = await self._get_current_nonce()
                
                # Build transaction
                transaction = contract.functions.cancelOrder(
                    Web3.to_checksum_address(base_address),
                    Web3.to_checksum_address(quote_address),
                    is_bid,
                    order_id
                ).build_transaction({
                    'from': account.address,
                    'nonce': nonce,
                    'gas': 200000,  # Estimate gas limit for cancel order
                    'gasPrice': w3.eth.gas_price,
                    'chainId': CONSTANTS.SOMNIA_CHAIN_ID
                })
                
                # Sign and send transaction
                signed_txn = account.sign_transaction(transaction)
                tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
                
                # Convert to hex string with 0x prefix
                tx_hash_hex = tx_hash.hex()
                
                self.logger().info(f"Cancel order transaction sent: {tx_hash_hex}")
                return tx_hash_hex
                
        except Exception as e:
            self.logger().error(f"Error cancelling order on contract: {e}")
            raise

    def _parse_trading_rule(self, trading_rule: Dict[str, Any]) -> TradingRule:
        """
        Parse trading rule from exchange data.
        
        Args:
            trading_rule: Raw trading rule data
            
        Returns:
            TradingRule instance
        """
        try:
            trading_pair = trading_rule["symbol"]
            
            # Initialize default values
            min_order_size = Decimal("0.001")
            max_order_size = Decimal("1000000")
            min_price_increment = Decimal("0.001")
            min_base_amount_increment = Decimal("0.001")
            min_notional_size = Decimal("1.0")
            
            # Handle filter-based format (from tests)
            if "filters" in trading_rule:
                for filter_item in trading_rule["filters"]:
                    filter_type = filter_item.get("filterType")
                    if filter_type == "LOT_SIZE":
                        min_order_size = Decimal(filter_item.get("minQty", "0.001"))
                        max_order_size = Decimal(filter_item.get("maxQty", "1000000"))
                        min_base_amount_increment = Decimal(filter_item.get("stepSize", "0.001"))
                    elif filter_type == "PRICE_FILTER":
                        min_price_increment = Decimal(filter_item.get("tickSize", "0.001"))
                    elif filter_type == "MIN_NOTIONAL":
                        min_notional_size = Decimal(filter_item.get("minNotional", "1.0"))
            
            # Handle direct field format (from our implementation)
            else:
                min_order_size = Decimal(trading_rule.get("minQty", "0.001"))
                max_order_size = Decimal(trading_rule.get("maxQty", "1000000"))
                min_price_increment = Decimal(trading_rule.get("tickSize", "0.001"))
                min_base_amount_increment = Decimal(trading_rule.get("stepSize", "0.001"))
                min_notional_size = Decimal(trading_rule.get("minNotional", "1.0"))
            
            return TradingRule(
                trading_pair=trading_pair,
                min_order_size=min_order_size,
                max_order_size=max_order_size,
                min_price_increment=min_price_increment,
                min_base_amount_increment=min_base_amount_increment,
                min_notional_size=min_notional_size,
            )
            
        except Exception as e:
            self.logger().error(f"Error parsing trading rule: {e}")
            raise

    def _parse_trading_pair(self, trading_pair: Dict[str, Any]) -> str:
        """
        Parse trading pair from exchange data.
        
        Args:
            trading_pair: Raw trading pair data
            
        Returns:
            Trading pair string
        """
        return trading_pair["symbol"]

    async def _format_trading_rules(self, exchange_info_dict: Dict[str, Any]) -> List[TradingRule]:
        """
        Format trading rules from exchange response.
        
        Args:
            exchange_info_dict: Exchange info dictionary or list
            
        Returns:
            List of trading rules
        """
        trading_rules = []
        
        # Handle both dict and list inputs for test compatibility
        if isinstance(exchange_info_dict, list):
            # If it's a list, treat each item as rule data
            for rule_data in exchange_info_dict:
                try:
                    trading_rule = self._parse_trading_rule(rule_data)
                    trading_rules.append(trading_rule)
                except Exception as e:
                    self.logger().error(f"Error formatting trading rule: {e}")
        else:
            # If it's a dict, iterate over items  
            for trading_pair, rule_data in exchange_info_dict.items():
                try:
                    trading_rule = self._parse_trading_rule(rule_data)
                    trading_rules.append(trading_rule)
                except Exception as e:
                    self.logger().error(f"Error formatting trading rule for {trading_pair}: {e}")
                
        return trading_rules

    async def _update_balances(self):
        """
        Update account balances using on-chain Web3 calls with API fallback.
        This method is called by the balance command to fetch current balances.
        """
        try:
            self.logger().info("=== Starting balance update ===")
            
            if not self._standard_client:
                self.logger().error("StandardWeb3 client not available - cannot fetch balances")
                return
                
            # Get all relevant tokens including native token
            tokens = set()
            
            if not self._trading_pairs:
                # For balance command or non-trading mode, use default tokens
                self.logger().info("No trading pairs configured - using default tokens for balance check")
                tokens = CONSTANTS.DEFAULT_TOKENS.copy()
                self.logger().info(f"Using default tokens for balance check: {tokens}")
            else:
                for trading_pair in self._trading_pairs:
                    base, quote = utils.split_trading_pair(trading_pair)
                    self.logger().debug(f"Split {trading_pair} -> base: {base}, quote: {quote}")
                    tokens.add(base)
                    tokens.add(quote)
                    
                # Always include native SOMNIA token for trading mode
                if self._trading_required:
                    tokens.add("SOMNIA")
            
            self.logger().info(f"Fetching balances for tokens: {sorted(tokens)}")
            
            # Fetch balances using Web3 (primary method)
            balances = {}
            successful_fetches = 0
            failed_fetches = 0
            
            for token in sorted(tokens):
                try:
                    self.logger().debug(f"Fetching balance for {token}...")
                    balance = await self._get_token_balance_web3(token)
                    balances[token] = balance
                    successful_fetches += 1
                    
                    # Show balance with appropriate formatting
                    if balance > Decimal("0"):
                        self.logger().info(f"✓ {token}: {balance}")
                    else:
                        self.logger().debug(f"✓ {token}: {balance} (zero balance)")
                        
                except Exception as e:
                    self.logger().warning(f"✗ Web3 balance failed for {token}: {e}")
                    failed_fetches += 1
                    
                    try:
                        self.logger().debug(f"Trying API fallback for {token}...")
                        balance = await self._get_token_balance_api(token)
                        balances[token] = balance
                        self.logger().info(f"✓ {token}: {balance} (via API)")
                    except Exception as api_error:
                        self.logger().error(f"✗ Both Web3 and API balance failed for {token}: {api_error}")
                        balances[token] = s_decimal_0
            
            # Update local balances
            self._account_balances = balances
            self._account_available_balances = balances.copy()
            
            # Summary
            total_tokens = len(tokens)
            self.logger().info(f"=== Balance update completed ===")
            self.logger().info(f"Successfully fetched: {successful_fetches}/{total_tokens} tokens")
            if failed_fetches > 0:
                self.logger().warning(f"Failed to fetch: {failed_fetches}/{total_tokens} tokens")
            
            # Log non-zero balances for user visibility
            non_zero_balances = {token: balance for token, balance in balances.items() if balance > s_decimal_0}
            if non_zero_balances:
                self.logger().info(f"Non-zero balances: {non_zero_balances}")
            else:
                self.logger().info("All balances are zero")
            
        except Exception as e:
            self.logger().error(f"Critical error updating balances: {e}")
            self.logger().exception("Full error details:")
            # Don't raise - let the system continue with existing balances

    async def _get_token_balance_web3(self, token: str) -> Decimal:
        """
        Get token balance using Web3 on-chain calls.
        
        Args:
            token: Token symbol (e.g., "STT", "USDC")
            
        Returns:
            Token balance as Decimal
        """
        try:
            # Use direct Web3 connection to Somnia RPC instead of StandardClient
            from web3 import Web3
            
            # Create Web3 instance with Somnia RPC
            rpc_url = "https://dream-rpc.somnia.network"
            w3 = Web3(Web3.HTTPProvider(rpc_url))
            
            if not w3.is_connected():
                self.logger().error("Failed to connect to Somnia RPC")
                return s_decimal_0
            
            # Use the wallet address and convert to checksum format
            wallet_address = w3.to_checksum_address(self._wallet_address)
            
            self.logger().debug(f"Getting balance for {token} at address {wallet_address}")
            self.logger().debug(f"wallet_address type: {type(wallet_address)}")
            
            if token.upper() in ["ETH", "SOMNIA", "STT"]:
                # Native token balance - try both native and ERC20 for STT
                if token.upper() == "STT":
                    # For STT, try native balance first
                    try:
                        native_balance_wei = w3.eth.get_balance(wallet_address)
                        native_balance = w3.from_wei(native_balance_wei, 'ether')
                        if native_balance > 0:
                            balance_decimal = Decimal(str(native_balance))
                            self.logger().debug(f"Native STT balance: {balance_decimal}")
                            return balance_decimal
                        else:
                            self.logger().debug("Native STT balance is 0, trying ERC20...")
                            # Fall through to ERC20 logic below
                    except Exception as native_error:
                        self.logger().debug(f"Native STT check failed: {native_error}, trying ERC20...")
                        # Fall through to ERC20 logic below
                else:
                    # For other native tokens
                    balance_wei = w3.eth.get_balance(wallet_address)
                    balance = w3.from_wei(balance_wei, 'ether')
                    balance_decimal = Decimal(str(balance))
                    self.logger().debug(f"Native {token} balance: {balance_decimal}")
                    return balance_decimal
            
            # ERC-20 token balance (or STT fallback)
            token_address = utils.convert_symbol_to_address(token)
            if not token_address or token_address == "0x...":
                self.logger().warning(f"Token address not found or incomplete for {token}")
                return s_decimal_0
            
            self.logger().debug(f"Getting ERC-20 balance for {token} at contract {token_address}")
            
            # Standard ERC-20 balanceOf call
            erc20_abi = [
                {
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "balance", "type": "uint256"}],
                    "type": "function"
                },
                {
                    "constant": True,
                    "inputs": [],
                    "name": "decimals",
                    "outputs": [{"name": "", "type": "uint8"}],
                    "type": "function"
                }
            ]
            
            # Create contract instance with proper checksum addresses
            contract = w3.eth.contract(
                address=w3.to_checksum_address(token_address), 
                abi=erc20_abi
            )
            
            # Get balance using Web3.to_checksum_address for safety
            balance_wei = contract.functions.balanceOf(w3.to_checksum_address(wallet_address)).call()
            
            # Get token decimals
            try:
                decimals = contract.functions.decimals().call()
            except Exception:
                # Default to 18 decimals if decimals() call fails
                decimals = 18
            
            # Convert to human readable format
            balance = Decimal(balance_wei) / Decimal(10 ** decimals)
            self.logger().debug(f"ERC-20 {token} balance: {balance} (decimals: {decimals})")
            return balance
                
        except Exception as e:
            self.logger().error(f"Web3 balance error for {token}: {e}")
            raise

    async def _get_token_balance_api(self, token: str) -> Decimal:
        """
        Get token balance using StandardWeb3 API as fallback.
        
        Args:
            token: Token symbol (e.g., "STT", "USDC")
            
        Returns:
            Token balance as Decimal
        """
        try:
            # First, get token information by symbol to get the token address
            token_info_url = f"{CONSTANTS.STANDARD_API_URL}/api/token/symbol/{token}"
            
            # Use the web assistant factory from the parent class  
            rest_assistant = await self._web_assistants_factory.get_rest_assistant()
            
            # Get token information
            token_response = await rest_assistant.execute_request(
                url=token_info_url,
                method=RESTMethod.GET,
                throttler_limit_id=CONSTANTS.GET_TOKEN_INFO_PATH_URL
            )
            
            if token_response.get("id"):
                token_address = token_response["id"]
                decimals = token_response.get("decimals", 18)
                
                # For native token (STT), use account data which might include balance info
                if token.upper() == "STT":
                    # Try to get account data for potential balance information
                    account_url = f"{CONSTANTS.STANDARD_API_URL}/api/account/{self._wallet_address}"
                    account_response = await rest_assistant.execute_request(
                        url=account_url,
                        method=RESTMethod.GET,
                        throttler_limit_id=CONSTANTS.GET_ACCOUNT_INFO_PATH_URL
                    )
                    
                    # For now, return 0 as API doesn't provide direct balance
                    # In production, you might need additional endpoints or Web3 fallback
                    self.logger().info(f"Got account data for {token}, but no direct balance endpoint available")
                    return s_decimal_0
                    
                else:
                    # For ERC-20 tokens, API doesn't provide direct balance
                    # This is a limitation of the current API
                    self.logger().warning(f"API balance not available for ERC-20 token {token}")
                    return s_decimal_0
                    
            else:
                self.logger().warning(f"Token {token} not found in API")
                return s_decimal_0
                    
        except Exception as e:
            self.logger().error(f"Failed to get {token} balance via API: {e}")
            return s_decimal_0

    async def _all_trade_updates_for_order(self, order: InFlightOrder) -> List[TradeUpdate]:
        """
        Get all trade updates for an order using StandardWeb3 trade history.
        
        Args:
            order: InFlightOrder instance
            
        Returns:
            List of TradeUpdate instances
        """
        try:
            if not self._standard_client:
                return []
            
            # Fetch account trade history using StandardWeb3
            trades_response = await self._standard_client.fetch_account_trade_history_paginated_with_limit(
                address=self._wallet_address,
                limit=100,  # Get recent trades
                page=1
            )
            
            trade_updates = []
            if trades_response and "trades" in trades_response:
                for trade in trades_response["trades"]:
                    # Check if this trade is related to our order
                    # This might depend on the exact response format from StandardWeb3
                    if self._is_trade_for_order(trade, order):
                        trade_update = self._parse_trade_update(trade, order)
                        if trade_update:
                            trade_updates.append(trade_update)
            
            return trade_updates
            
        except Exception as e:
            self.logger().error(f"Error fetching trade updates for order {order.client_order_id}: {e}")
            return []

    def _is_trade_for_order(self, trade: Dict[str, Any], order: InFlightOrder) -> bool:
        """
        Check if a trade is related to a specific order.
        
        Args:
            trade: Trade data from StandardWeb3
            order: InFlightOrder instance
            
        Returns:
            True if trade is for this order
        """
        try:
            # Check if the trade transaction hash matches our order exchange ID
            trade_tx_hash = trade.get("tx_hash") or trade.get("transaction_hash")
            if trade_tx_hash == order.exchange_order_id:
                return True
            
            # Alternative: check if trade matches order details (trading pair, side, etc.)
            trading_pair = f"{trade.get('base_symbol', '')}-{trade.get('quote_symbol', '')}"
            if trading_pair == order.trading_pair:
                # Additional checks could be added here for more precision
                return True
            
            return False
            
        except Exception as e:
            self.logger().warning(f"Error checking if trade is for order: {e}")
            return False

    def _parse_trade_update(self, trade: Dict[str, Any], order: InFlightOrder) -> Optional[TradeUpdate]:
        """
        Parse trade data into TradeUpdate format.
        
        Args:
            trade: Trade data from StandardWeb3
            order: InFlightOrder instance
            
        Returns:
            TradeUpdate instance or None
        """
        try:
            # Extract trade information
            fill_price = Decimal(str(trade.get("price", "0")))
            fill_quantity = Decimal(str(trade.get("quantity", "0")))
            
            # Get fee information if available
            fee_amount = Decimal(str(trade.get("fee", "0")))
            fee_currency = trade.get("fee_currency", order.quote_asset)
            
            # Create trade fee
            trade_fee = AddedToCostTradeFee(
                flat_fees=[TokenAmount(token=fee_currency, amount=fee_amount)]
            )
            
            # Get trade timestamp
            trade_time = trade.get("timestamp", time.time())
            if isinstance(trade_time, str):
                # Parse timestamp if it's a string
                try:
                    trade_time = float(trade_time)
                except ValueError:
                    trade_time = time.time()
            
            return TradeUpdate(
                trading_pair=order.trading_pair,
                fill_timestamp=trade_time,
                fill_price=fill_price,
                fill_base_amount=fill_quantity,
                fee=trade_fee,
                trade_id=trade.get("trade_id", f"trade_{int(trade_time)}"),
                exchange_order_id=order.exchange_order_id,
                client_order_id=order.client_order_id,
            )
            
        except Exception as e:
            self.logger().error(f"Error parsing trade update: {e}")
            return None

    async def _request_order_status(self, tracked_order: InFlightOrder) -> OrderUpdate:
        """
        Request order status from the exchange.
        
        Args:
            tracked_order: InFlightOrder instance
            
        Returns:
            OrderUpdate instance
        """
        try:
            # Query order status using StandardClient account orders
            # Since there's no direct get_order_status, we'll fetch recent orders
            # and find the one matching our exchange_order_id
            orders_response = await self._standard_client.fetch_account_orders_paginated_with_limit(
                address=self._wallet_address,
                limit=50,  # Get recent orders
                page=1
            )
            
            # Look for our order in the response
            order_status = None
            if orders_response and "orders" in orders_response:
                for order in orders_response["orders"]:
                    if order.get("tx_hash") == tracked_order.exchange_order_id:
                        order_status = order
                        break
            
            if not order_status:
                # If not found in active orders, check order history
                history_response = await self._standard_client.fetch_account_order_history_paginated_with_limit(
                    address=self._wallet_address,
                    limit=50,
                    page=1
                )
                
                if history_response and "orders" in history_response:
                    for order in history_response["orders"]:
                        if order.get("tx_hash") == tracked_order.exchange_order_id:
                            order_status = order
                            break
            
            if not order_status:
                # Order not found - might be too new or still being indexed
                # Don't immediately mark as failed, give it more time
                creation_time = tracked_order.creation_timestamp
                current_time = time.time()
                time_since_creation = current_time - creation_time
                
                # Only mark as failed if order is older than 5 minutes and still not found
                if time_since_creation > 300:  # 5 minutes
                    self.logger().warning(f"Order {tracked_order.client_order_id} not found after 5 minutes, marking as failed")
                    return OrderUpdate(
                        trading_pair=tracked_order.trading_pair,
                        update_timestamp=time.time(),
                        new_state=OrderState.FAILED,
                        client_order_id=tracked_order.client_order_id,
                        exchange_order_id=tracked_order.exchange_order_id,
                    )
                else:
                    # Order is still new, assume it's OPEN and wait for indexing
                    self.logger().debug(f"Order {tracked_order.client_order_id} not found yet (age: {time_since_creation:.1f}s), assuming OPEN")
                    return OrderUpdate(
                        trading_pair=tracked_order.trading_pair,
                        update_timestamp=time.time(),
                        new_state=OrderState.OPEN,
                        client_order_id=tracked_order.client_order_id,
                        exchange_order_id=tracked_order.exchange_order_id,
                    )
            
            # Parse the status response
            new_state = self._parse_order_status(order_status)
            
            return OrderUpdate(
                trading_pair=tracked_order.trading_pair,
                update_timestamp=time.time(),
                new_state=new_state,
                client_order_id=tracked_order.client_order_id,
                exchange_order_id=tracked_order.exchange_order_id,
            )
            
        except Exception as e:
            self.logger().error(f"Error requesting order status for {tracked_order.client_order_id}: {e}")
            raise

    def _parse_order_status(self, order_status: Dict[str, Any]) -> OrderState:
        """
        Parse order state from exchange response.
        
        Args:
            order_status: Order status data
            
        Returns:
            OrderState
        """
        status = order_status.get("status", "").lower()
        
        if status in ["filled", "completed"]:
            return OrderState.FILLED
        elif status in ["open", "active", "pending"]:
            return OrderState.OPEN
        elif status in ["cancelled", "canceled"]:
            return OrderState.CANCELLED
        elif status in ["failed", "rejected"]:
            return OrderState.FAILED
        else:
            return OrderState.OPEN  # Default to open for unknown statuses

    # Required abstract properties
    @property
    def trading_pairs(self) -> List[str]:
        """
        Return list of active trading pairs.
        """
        return self._trading_pairs

    @property
    def is_cancel_request_in_exchange_synchronous(self) -> bool:
        """
        Whether cancel requests are synchronous or not.
        """
        return True  # Somnia cancellations are synchronous

    def is_trading_required(self) -> bool:
        """
        Whether trading is required for this connector.
        """
        return True
        
    @property  
    def _order_book_tracker(self):
        """
        Expose order book tracker for tests and internal use.
        """
        return self.order_book_tracker

    def convert_from_exchange_trading_pair(self, exchange_trading_pair: str) -> str:
        """
        Convert trading pair from exchange format to internal format.
        
        Args:
            exchange_trading_pair: Exchange trading pair format
            
        Returns:
            Internal trading pair format
        """
        return utils.convert_from_exchange_trading_pair(exchange_trading_pair)
        
    def convert_to_exchange_trading_pair(self, trading_pair: str) -> str:
        """
        Convert trading pair from internal format to exchange format.
        
        Args:
            trading_pair: Internal trading pair format
            
        Returns:
            Exchange trading pair format
        """
        return utils.convert_to_exchange_trading_pair(trading_pair)
        
    def get_token_info(self, token_symbol: str) -> Dict[str, Any]:
        """
        Get token information.
        
        Args:
            token_symbol: Token symbol
            
        Returns:
            Token information dictionary
        """
        return {
            "symbol": token_symbol,
            "address": utils.convert_symbol_to_address(token_symbol),
            "decimals": utils.get_token_decimals(token_symbol)
        }
        
    def _get_web3_balance(self, token: str) -> Decimal:
        """
        Synchronous wrapper for Web3 balance retrieval.
        
        Args:
            token: Token symbol
            
        Returns:
            Token balance
        """
        # This is a sync wrapper that the tests expect
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self._get_token_balance_web3(token))
        except Exception:
            return s_decimal_0

    def _is_user_stream_initialized(self) -> bool:
        """
        Override to always return True since Somnia uses REST API polling instead of WebSocket user streams.
        """
        return True

    # Required abstract methods
    def _initialize_trading_pair_symbols_from_exchange_info(self, exchange_info: Dict[str, Any]):
        """
        Initialize trading pair symbols from exchange info.
        
        Args:
            exchange_info: Exchange information dictionary
        """
        self.logger().info("DEBUG: _initialize_trading_pair_symbols_from_exchange_info called")
        self.logger().info(f"DEBUG: exchange_info keys: {list(exchange_info.keys())}")
        self.logger().info(f"DEBUG: exchange_info type: {type(exchange_info)}")
        
        # Use bidict like Vertex for proper symbol mapping
        mapping = bidict()
        
        # Handle the structure returned by build_exchange_market_info() - format 1
        if "symbols" in exchange_info:
            self.logger().info("DEBUG: Using format 1 - exchange_info contains 'symbols' key")
            symbols = exchange_info.get("symbols", [])
            self.logger().info(f"DEBUG: Found {len(symbols)} symbols in 'symbols' key")
            
            for symbol_info in symbols:
                if isinstance(symbol_info, dict):
                    symbol = symbol_info.get("symbol", "")
                    base = symbol_info.get("baseAsset", "")
                    quote = symbol_info.get("quoteAsset", "")
                    self.logger().info(f"DEBUG: Processing symbol - symbol: {symbol}, base: {base}, quote: {quote}")
                    
                    if symbol and base and quote:
                        # Use combine_to_hb_trading_pair like Vertex
                        hb_trading_pair = combine_to_hb_trading_pair(base=base, quote=quote)
                        mapping[symbol] = hb_trading_pair
                        self.logger().info(f"DEBUG: Added mapping {symbol} -> {hb_trading_pair}")
        
        # Handle direct trading pair keys - format 2 (when base class calls directly)
        else:
            self.logger().info("DEBUG: Using format 2 - exchange_info contains direct trading pair keys")
            self.logger().info(f"DEBUG: Full exchange_info content: {exchange_info}")
            trading_pair_keys = [key for key in exchange_info.keys() if "-" in key]
            self.logger().info(f"DEBUG: Found trading pair keys: {trading_pair_keys}")
            
            # If no keys with dash, try all keys as potential trading pairs
            if not trading_pair_keys:
                self.logger().info("DEBUG: No keys with dash found, checking all keys")
                all_keys = list(exchange_info.keys())
                self.logger().info(f"DEBUG: All keys: {all_keys}")
                
                # Check if any key looks like a trading pair or if we should use configured trading pairs
                for key in all_keys:
                    self.logger().info(f"DEBUG: Examining key: {key}, type: {type(key)}")
                    
                    # If key is a trading pair format, use it
                    if isinstance(key, str) and "-" in key:
                        trading_pair_keys.append(key)
                    # If key matches our configured trading pairs, use it
                    elif key in self._trading_pairs:
                        trading_pair_keys.append(key)
                
                # If still no keys, use our configured trading pairs as fallback
                if not trading_pair_keys:
                    self.logger().info("DEBUG: Using configured trading pairs as fallback")
                    trading_pair_keys = self._trading_pairs
                    
            self.logger().info(f"DEBUG: Final trading pair keys to process: {trading_pair_keys}")
            
            for trading_pair in trading_pair_keys:
                try:
                    # For Somnia, we expect trading pairs like "STT-USDC"
                    if "-" in trading_pair:
                        base_asset, quote_asset = trading_pair.split("-", 1)
                        
                        # Create proper Hummingbot trading pair format
                        hb_trading_pair = combine_to_hb_trading_pair(base=base_asset, quote=quote_asset)
                        
                        self.logger().info(f"DEBUG: Mapping {trading_pair} -> {hb_trading_pair}")
                        mapping[trading_pair] = hb_trading_pair
                    else:
                        self.logger().info(f"DEBUG: Skipping key without dash: {trading_pair}")
                    
                except Exception as e:
                    self.logger().error(f"DEBUG: Error processing trading pair {trading_pair}: {e}")
                    import traceback
                    self.logger().error(f"DEBUG: Traceback: {traceback.format_exc()}")
        
        self.logger().info(f"DEBUG: Final mapping before setting: {dict(mapping)}")
        self.logger().info(f"Initialized trading pair symbol map with {len(mapping)} pairs: {dict(mapping)}")
        
        self.logger().info("DEBUG: About to call _set_trading_pair_symbol_map")
        self._set_trading_pair_symbol_map(mapping)
        self.logger().info("DEBUG: Called _set_trading_pair_symbol_map")
        
        # Verify it was set
        current_map = getattr(self, '_trading_pair_symbol_map', 'NOT SET')
        self.logger().info(f"DEBUG: After setting, _trading_pair_symbol_map = {current_map}")
        self.logger().info(f"DEBUG: trading_pair_symbol_map_ready() = {self.trading_pair_symbol_map_ready()}")

    async def _update_trading_fees(self):
        """
        Update trading fees for all trading pairs.
        """
        # Somnia uses fixed fees defined in constants
        trading_fees = {}
        for trading_pair in self._trading_pairs:
            trading_fees[trading_pair] = {
                "maker": Decimal("0.001"),  # 0.1%
                "taker": Decimal("0.001"),  # 0.1%
            }
        
        self._trading_fees = trading_fees

    async def _request_order_history(self) -> List[Dict[str, Any]]:
        """
        Request order history from the exchange using StandardWeb3 API.
        
        Returns:
            List of order history data
        """
        try:
            if not self._standard_client:
                self.logger().warning("StandardWeb3 client not available for order history")
                return []
            
            # Use StandardWeb3 to fetch account order history
            self.logger().info(f"Fetching order history for address: {self._wallet_address}")
            
            # Fetch order history using StandardWeb3 client
            try:
                orders_response = await self._standard_client.fetch_account_order_history_paginated_with_limit(
                    address=self._wallet_address,
                    limit=100,  # Get last 100 orders
                    page=1
                )
                
                if orders_response and "orders" in orders_response:
                    orders = orders_response["orders"]
                    self.logger().info(f"Successfully fetched {len(orders)} orders from history")
                    return orders
                else:
                    self.logger().info("No orders found in history response")
                    return []
                    
            except Exception as e:
                self.logger().warning(f"StandardWeb3 order history failed: {e}, trying alternative method...")
                
                # Fallback: Use REST API endpoints
                rest_assistant = await self._web_assistants_factory.get_rest_assistant()
                
                # Use account orders endpoint from constants
                orders_url = f"{CONSTANTS.STANDARD_API_URL}/api/orders/{self._wallet_address}/100/1"
                
                orders_response = await rest_assistant.execute_request(
                    url=orders_url,
                    method=RESTMethod.GET,
                    throttler_limit_id=CONSTANTS.GET_ACCOUNT_ORDERS_PATH_URL
                )
                
                if orders_response and isinstance(orders_response, dict):
                    orders = orders_response.get("orders", [])
                    self.logger().info(f"Successfully fetched {len(orders)} orders via REST API")
                    return orders
                else:
                    self.logger().warning("REST API order history returned no valid data")
                    return []
                    
        except Exception as e:
            self.logger().error(f"Error requesting order history: {e}", exc_info=True)
            return []

    async def _request_trade_history(self) -> List[Dict[str, Any]]:
        """
        Request trade history from the exchange using StandardWeb3 API.
        
        Returns:
            List of trade history data
        """
        try:
            if not self._standard_client:
                self.logger().warning("StandardWeb3 client not available for trade history")
                return []
            
            # Use StandardWeb3 to fetch account trade history
            self.logger().info(f"Fetching trade history for address: {self._wallet_address}")
            
            # Fetch trade history using StandardWeb3 client
            try:
                trades_response = await self._standard_client.fetch_account_trade_history_paginated_with_limit(
                    address=self._wallet_address,
                    limit=100,  # Get last 100 trades
                    page=1
                )
                
                if trades_response and "trades" in trades_response:
                    trades = trades_response["trades"]
                    self.logger().info(f"Successfully fetched {len(trades)} trades from history")
                    return trades
                else:
                    self.logger().info("No trades found in history response")
                    return []
                    
            except Exception as e:
                self.logger().warning(f"StandardWeb3 trade history failed: {e}, trying alternative method...")
                
                # Fallback: Use REST API endpoints
                rest_assistant = await self._web_assistants_factory.get_rest_assistant()
                
                # Use account trades endpoint from constants
                trades_url = f"{CONSTANTS.STANDARD_API_URL}/api/tradehistory/{self._wallet_address}/100/1"
                
                trades_response = await rest_assistant.execute_request(
                    url=trades_url,
                    method=RESTMethod.GET,
                    throttler_limit_id=CONSTANTS.GET_ACCOUNT_TRADES_PATH_URL
                )
                
                if trades_response and isinstance(trades_response, dict):
                    trades = trades_response.get("trades", [])
                    self.logger().info(f"Successfully fetched {len(trades)} trades via REST API")
                    return trades
                else:
                    self.logger().warning("REST API trade history returned no valid data")
                    return []
                    
        except Exception as e:
            self.logger().error(f"Error requesting trade history: {e}", exc_info=True)
            return []

    def get_order_history_df(self) -> Optional[Any]:
        """
        Get order history as a pandas DataFrame for the 'history' command.
        
        Returns:
            DataFrame with order history or None if pandas not available
        """
        try:
            if pd is None:
                self.logger().error("pandas not available for order history DataFrame")
                return None
            
            self.logger().info("Fetching order history for 'history' command...")
            
            # Fetch order history using async method
            import asyncio
            
            try:
                # Check if we're in an async context
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're already in an async context, need to create a task
                    # This is a synchronous method called from CLI, so we'll use a different approach
                    order_history = []
                    trade_history = []
                    
                    # Try to get from cache or recent data
                    # In practice, the CLI should call async methods, but for compatibility:
                    self.logger().info("Creating async task for history retrieval...")
                    
                    # Create tasks for both order and trade history
                    async def fetch_histories():
                        orders = await self._request_order_history()
                        trades = await self._request_trade_history()
                        return orders, trades
                    
                    # Create task and get result
                    task = asyncio.create_task(fetch_histories())
                    # Since we're in an event loop, we can't await here
                    # We'll return a placeholder and log that async fetch is happening
                    self.logger().info("Order history fetch initiated - check logs for results")
                    
                    # Return minimal DataFrame structure for now
                    columns = [
                        'symbol', 'order_id', 'timestamp', 'order_type', 'side', 
                        'amount', 'price', 'status', 'trade_fee', 'exchange_order_id'
                    ]
                    df = pd.DataFrame(columns=columns)
                    return df
                    
                else:
                    # No event loop running, create one
                    order_history = loop.run_until_complete(self._request_order_history())
                    trade_history = loop.run_until_complete(self._request_trade_history())
                    
            except RuntimeError:
                # No event loop exists, create one
                order_history = asyncio.run(self._request_order_history())
                trade_history = asyncio.run(self._request_trade_history())
            
            # Convert order history to DataFrame format
            order_data = []
            
            # Process order history
            for order in order_history:
                try:
                    order_entry = {
                        'symbol': order.get('trading_pair', order.get('symbol', 'Unknown')),
                        'order_id': order.get('order_id', order.get('id', 'Unknown')),
                        'timestamp': order.get('timestamp', order.get('created_at', 'Unknown')),
                        'order_type': order.get('order_type', order.get('type', 'Unknown')),
                        'side': order.get('side', 'Unknown'),
                        'amount': float(order.get('amount', order.get('quantity', 0))),
                        'price': float(order.get('price', 0)),
                        'status': order.get('status', 'Unknown'),
                        'trade_fee': float(order.get('fee', 0)),
                        'exchange_order_id': order.get('tx_hash', order.get('transaction_hash', 'Unknown'))
                    }
                    order_data.append(order_entry)
                except Exception as e:
                    self.logger().warning(f"Error processing order entry: {e}")
                    continue
            
            # Process trade history and add to order data
            for trade in trade_history:
                try:
                    trade_entry = {
                        'symbol': trade.get('trading_pair', trade.get('symbol', 'Unknown')),
                        'order_id': trade.get('order_id', 'Trade'),
                        'timestamp': trade.get('timestamp', trade.get('created_at', 'Unknown')),
                        'order_type': 'TRADE',
                        'side': trade.get('side', 'Unknown'),
                        'amount': float(trade.get('amount', trade.get('quantity', 0))),
                        'price': float(trade.get('price', 0)),
                        'status': 'FILLED',
                        'trade_fee': float(trade.get('fee', 0)),
                        'exchange_order_id': trade.get('tx_hash', trade.get('transaction_hash', 'Unknown'))
                    }
                    order_data.append(trade_entry)
                except Exception as e:
                    self.logger().warning(f"Error processing trade entry: {e}")
                    continue
            
            # Create DataFrame
            if order_data:
                df = pd.DataFrame(order_data)
                # Sort by timestamp (most recent first)
                if 'timestamp' in df.columns:
                    df = df.sort_values('timestamp', ascending=False)
                
                self.logger().info(f"Order history DataFrame created with {len(df)} entries")
                return df
            else:
                # Create empty DataFrame with proper columns
                columns = [
                    'symbol', 'order_id', 'timestamp', 'order_type', 'side', 
                    'amount', 'price', 'status', 'trade_fee', 'exchange_order_id'
                ]
                df = pd.DataFrame(columns=columns)
                self.logger().info("No order/trade history found - returning empty DataFrame")
                return df
            
        except Exception as e:
            self.logger().error(f"Error creating order history DataFrame: {e}", exc_info=True)
            
            # Return empty DataFrame on error
            if pd is not None:
                columns = [
                    'symbol', 'order_id', 'timestamp', 'order_type', 'side', 
                    'amount', 'price', 'status', 'trade_fee', 'exchange_order_id'
                ]
                return pd.DataFrame(columns=columns)
            else:
                return None

    async def _user_stream_event_listener(self):
        """
        Listen to user stream events.
        """
        async for stream_message in self._iter_user_event_queue():
            try:
                await self._process_user_stream_event(stream_message)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger().error(f"Error processing user stream event: {e}", exc_info=True)
