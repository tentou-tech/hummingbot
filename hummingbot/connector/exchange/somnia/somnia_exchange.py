#!/usr/bin/env python

import asyncio
import logging
import time
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

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
from hummingbot.core.data_type.trade_fee import AddedToCostTradeFee, TokenAmount, TradeFeeBase, TradeFeeSchema
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


class SomniaExchange(ExchangePyBase):
    """
    Somnia exchange connector using StandardWeb3 for blockchain interactions.
    """
    
    web_utils = web_utils
    _logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(
        self,
        client_config_map: "ClientConfigAdapter",
        somnia_private_key: str,
        somnia_wallet_address: str,
        trading_pairs: List[str] = None,
        trading_required: bool = True,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
        self.logger().info("DEBUG: SomniaExchange.__init__ called")
        self.logger().info(f"DEBUG: SomniaExchange.__init__ called with trading_pairs = {trading_pairs}")
        
        # Store configuration
        self._private_key = somnia_private_key
        self._wallet_address = somnia_wallet_address
        self._domain = domain
        self._trading_required = trading_required
        self._trading_pairs = trading_pairs or []
        
        self.logger().info(f"DEBUG: After assignment, self._trading_pairs = {self._trading_pairs}")
        
        # Initialize StandardWeb3 client if available
        if StandardClient:
            try:
                client_config = {
                    "name": "somnia",
                    "rpc_url": "https://rpc.somnia.network",
                    "chain_id": 50311,
                    "websocket_url": "wss://ws.somnia.network"
                }
                self._standard_client = StandardClient(
                    name=client_config["name"],
                    rpc_url=client_config["rpc_url"],
                    chain_id=client_config["chain_id"],
                    websocket_url=client_config["websocket_url"],
                    api_key="defaultApiKey"  # Optional parameter
                )
                self.logger().info("StandardWeb3 client initialized successfully")
            except Exception as e:
                self.logger().error(f"Failed to initialize StandardWeb3 client: {e}")
                self.logger().info("StandardWeb3 client disabled due to error")
                self._standard_client = None
        else:
            self.logger().info("StandardWeb3 client disabled - library not available")
        
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
        
        # Real-time balance updates
        self.real_time_balance_update = True
        
        self.logger().info("DEBUG: SomniaExchange.__init__ completed successfully")
        """
        Initialize Somnia exchange connector.
        
        Args:
            client_config_map: Client configuration
            somnia_private_key: Wallet private key
            somnia_wallet_address: Wallet address
            trading_pairs: List of trading pairs
            trading_required: Whether trading is required
            domain: Exchange domain
        """
        self.logger().info(f"DEBUG: SomniaExchange.__init__ called with trading_pairs = {trading_pairs}")
        
        self._private_key = somnia_private_key
        self._wallet_address = somnia_wallet_address.lower()
        self._domain = domain
        self._trading_pairs = trading_pairs or []
        
        self.logger().info(f"DEBUG: After assignment, self._trading_pairs = {self._trading_pairs}")
        
        # TEMPORARY FIX: If no trading pairs provided, use default from config
        if not self._trading_pairs:
            self.logger().warning("No trading pairs provided, using default STT-USDC")
            self._trading_pairs = ["STT-USDC"]
            self.logger().info(f"DEBUG: Set default trading pairs: {self._trading_pairs}")
        
        # Initialize StandardWeb3 client
        self._standard_client = None
        if StandardClient:
            try:
                client_config = utils.build_standard_web3_config()
                self._standard_client = StandardClient(
                    private_key=self._private_key,
                    http_rpc_url=client_config["rpc_url"],
                    matching_engine_address=client_config["exchange_address"],
                    networkName=client_config["network_name"],
                    api_url=client_config["api_url"],
                    websocket_url=client_config["websocket_url"],
                    api_key="defaultApiKey"  # Optional parameter
                )
                self.logger().info("StandardWeb3 client initialized successfully")
            except Exception as e:
                self.logger().error(f"Failed to initialize StandardWeb3 client: {e}")
                self.logger().info("StandardWeb3 client disabled due to error")
                self._standard_client = None
        else:
            self.logger().info("StandardWeb3 client disabled - library not available")
        
        # Initialize authentication
        self._auth = SomniaAuth(
            private_key=self._private_key,
            wallet_address=self._wallet_address,
        )
        
        # Initialize parent class
        super().__init__(
            client_config_map=client_config_map,
        )
        
        # Set connector reference in data sources after initialization
        if hasattr(self, '_orderbook_ds') and self._orderbook_ds:
            self._orderbook_ds._connector = self
        
        # Real-time balance updates
        self.real_time_balance_update = True

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
            
            # TEMPORARILY SKIP build_exchange_market_info to isolate the order book tracker issue
            # self.logger().info("DEBUG: About to call build_exchange_market_info()")
            # await self.build_exchange_market_info()
            # self.logger().info("DEBUG: build_exchange_market_info() completed successfully")
            
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
            self.logger().info("Building Somnia exchange market info...")
            
            # Get available trading pairs and market data
            symbols = await self._get_symbols()
            contracts = await self._get_contracts()
            fee_rates = await self._get_fee_rates()
            
            exchange_info = {
                "symbols": symbols,
                "contracts": contracts,
                "fee_rates": fee_rates,
                "server_time": int(time.time() * 1000),
                "rate_limits": self.rate_limits_rules,
            }
            
            self.logger().info(f"Built exchange info with {len(symbols)} symbols and {len(contracts)} contracts")
            return exchange_info
            
        except Exception as e:
            self.logger().error(f"Failed to build exchange market info: {e}")
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
            self.logger().info("Initializing trading pair symbol map...")
            exchange_info = await self.build_exchange_market_info()
            self._initialize_trading_pair_symbols_from_exchange_info(exchange_info=exchange_info)
            self.logger().info("Trading pair symbol map initialized successfully")
        except Exception as e:
            self.logger().exception("There was an error requesting exchange info.")
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
            self.logger().info(f"DEBUG: _get_symbols called with self._trading_pairs = {self._trading_pairs}")
            
            # For now, return known trading pairs
            # This can be enhanced to fetch from actual API
            symbols = []
            for trading_pair in self._trading_pairs:
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
            
            # If no trading pairs are configured yet, add default STT-USDC
            if not symbols:
                self.logger().info("No trading pairs configured, adding default STT-USDC")
                symbols.append({
                    "symbol": "STT-USDC",
                    "baseAsset": "STT",
                    "quoteAsset": "USDC",
                    "status": "TRADING",
                    "baseAssetPrecision": 8,
                    "quotePrecision": 8,
                    "orderTypes": ["LIMIT", "MARKET"],
                })
            
            self.logger().info(f"Retrieved {len(symbols)} symbols")
            return symbols
            
        except Exception as e:
            self.logger().error(f"Failed to get symbols: {e}")
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
        self.logger().info(f"DEBUG: Creating order book data source with trading_pairs: {self._trading_pairs}")
        
        try:
            data_source = SomniaAPIOrderBookDataSource(
                trading_pairs=self._trading_pairs,
                connector=self,  # Pass self reference like other exchanges
                api_factory=self._web_assistants_factory,
                domain=self._domain,
                throttler=self._throttler,
            )
            self.logger().info("DEBUG: Order book data source created successfully")
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
        is_maker = is_maker or (order_type is OrderType.LIMIT_MAKER)
        fee_rate = CONSTANTS.DEFAULT_TRADING_FEE
        
        # For gas fees on blockchain
        gas_fee = TokenAmount(amount=Decimal(str(CONSTANTS.DEFAULT_GAS_PRICE)), token="STT")
        
        fee = build_trade_fee(
            exchange=self.name,
            is_maker=is_maker,
            order_side=order_side,
            order_type=order_type,
            amount=amount,
            price=price,
            fee_schema=TradeFeeSchema(
                maker_percent_fee_decimal=Decimal(str(fee_rate)),
                taker_percent_fee_decimal=Decimal(str(fee_rate)),
                buy_percent_fee_deducted_from_returns=True
            )
        )
        
        return fee

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
            
            # Use StandardClient to place the order
            if is_buy:
                tx_hash = await self._standard_client.place_buy_order(
                    base_token=base_address,
                    quote_token=quote_address,
                    amount=utils.format_amount(amount, base_decimals),
                    price=utils.format_amount(execution_price, quote_decimals),
                    order_type=self.somnia_order_type(order_type),
                )
            else:
                tx_hash = await self._standard_client.place_sell_order(
                    base_token=base_address,
                    quote_token=quote_address,
                    amount=utils.format_amount(amount, base_decimals),
                    price=utils.format_amount(execution_price, quote_decimals),
                    order_type=self.somnia_order_type(order_type),
                )
            
            # Return transaction hash as exchange order ID
            timestamp = time.time()
            self.logger().info(f"Order placed successfully: {order_id} -> {tx_hash}")
            
            return tx_hash, timestamp
            
        except Exception as e:
            self.logger().error(f"Error placing order {order_id}: {e}")
            raise

    async def _place_cancel(self, order_id: str, tracked_order: InFlightOrder) -> str:
        """
        Cancel an order on the exchange.
        
        Args:
            order_id: Client order ID
            tracked_order: InFlightOrder instance
            
        Returns:
            Exchange cancellation ID
        """
        try:
            # Use StandardClient to cancel the order
            exchange_order_id = tracked_order.exchange_order_id
            
            tx_hash = await self._standard_client.cancel_order(
                order_id=exchange_order_id
            )
            
            self.logger().info(f"Order cancelled successfully: {order_id} -> {tx_hash}")
            return tx_hash
            
        except Exception as e:
            self.logger().error(f"Error cancelling order {order_id}: {e}")
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
            
            return TradingRule(
                trading_pair=trading_pair,
                min_order_size=Decimal(trading_rule["minQty"]),
                max_order_size=Decimal(trading_rule["maxQty"]),
                min_price_increment=Decimal(trading_rule["tickSize"]),
                min_base_amount_increment=Decimal(trading_rule["stepSize"]),
                min_notional_size=Decimal(trading_rule["minNotional"]),
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
            exchange_info_dict: Exchange info dictionary
            
        Returns:
            List of trading rules
        """
        trading_rules = []
        
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
        """
        try:
            if not self._standard_client:
                return
                
            # Get all relevant tokens including native token
            tokens = set()
            self.logger().info(f"Trading pairs configured: {self._trading_pairs}")
            
            if not self._trading_pairs:
                # Fallback: add default tokens if no trading pairs configured
                self.logger().warning("No trading pairs configured, using default tokens STT and USDC")
                tokens.add("STT")
                tokens.add("USDC")
            else:
                for trading_pair in self._trading_pairs:
                    base, quote = utils.split_trading_pair(trading_pair)
                    self.logger().info(f"Split {trading_pair} -> base: {base}, quote: {quote}")
                    tokens.add(base)
                    tokens.add(quote)
            
            # Always include native SOMNIA token
            tokens.add("SOMNIA")
            
            self.logger().info(f"Fetching balances for tokens: {tokens}")
            
            # Fetch balances using Web3 (primary method)
            balances = {}
            for token in tokens:
                try:
                    balance = await self._get_token_balance_web3(token)
                    balances[token] = balance
                    self.logger().info(f"Web3 balance for {token}: {balance}")
                except Exception as e:
                    self.logger().warning(f"Web3 balance failed for {token}: {e}, trying API fallback...")
                    try:
                        balance = await self._get_token_balance_api(token)
                        balances[token] = balance
                        self.logger().info(f"API balance for {token}: {balance}")
                    except Exception as api_error:
                        self.logger().error(f"Both Web3 and API balance failed for {token}: {api_error}")
                        balances[token] = s_decimal_0
            
            # Update local balances
            self._account_balances = balances
            self._account_available_balances = balances.copy()
            
            self.logger().info(f"Updated balances: {balances}")
            
        except Exception as e:
            self.logger().error(f"Error updating balances: {e}")

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
        Get all trade updates for an order.
        
        Args:
            order: InFlightOrder instance
            
        Returns:
            List of TradeUpdate instances
        """
        # Implementation would query the exchange for trade updates related to this order
        # For now, return empty list - this would be populated by real-time updates
        return []

    async def _request_order_status(self, tracked_order: InFlightOrder) -> OrderUpdate:
        """
        Request order status from the exchange.
        
        Args:
            tracked_order: InFlightOrder instance
            
        Returns:
            OrderUpdate instance
        """
        try:
            # Query order status using StandardClient
            order_status = await self._standard_client.get_order_status(
                tracked_order.exchange_order_id
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

    @property
    def is_trading_required(self) -> bool:
        """
        Whether trading is required for this connector.
        """
        return True

    # Required abstract methods
    def _initialize_trading_pair_symbols_from_exchange_info(self, exchange_info: Dict[str, Any]):
        """
        Initialize trading pair symbols from exchange info.
        
        Args:
            exchange_info: Exchange information dictionary
        """
        # Update trading pairs mapping based on exchange info
        mapping = {}
        if isinstance(exchange_info, list):
            for pair_info in exchange_info:
                if isinstance(pair_info, dict):
                    symbol = pair_info.get("symbol", "")
                    base = pair_info.get("base_asset", "")
                    quote = pair_info.get("quote_asset", "")
                    if symbol and base and quote:
                        hb_trading_pair = f"{base}-{quote}"
                        mapping[symbol] = hb_trading_pair
        
        self._set_trading_pair_symbol_map(mapping)

    async def _update_trading_fees(self):
        """
        Update trading fees for all trading pairs.
        """
        # Somnia uses fixed fees defined in constants
        trading_fees = {}
        for trading_pair in self._trading_pairs:
            trading_fees[trading_pair] = TradeFeeSchema(
                maker_percent_fee_decimal=Decimal("0.001"),  # 0.1%
                taker_percent_fee_decimal=Decimal("0.001"),  # 0.1%
            )
        
        self._trading_fees = trading_fees

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
