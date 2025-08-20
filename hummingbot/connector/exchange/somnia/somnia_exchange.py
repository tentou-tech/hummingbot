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
        trading_pairs: Optional[List[str]] = None,
        trading_required: bool = True,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
    ):
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
        self._private_key = somnia_private_key
        self._wallet_address = somnia_wallet_address.lower()
        self._domain = domain
        self._trading_pairs = trading_pairs or []
        
        # Initialize StandardWeb3 client
        self._standard_client = None
        if StandardClient:
            try:
                client_config = utils.build_standard_web3_config()
                self._standard_client = StandardClient(
                    rpc_url=client_config["rpc_url"],
                    private_key=self._private_key,
                    address=self._wallet_address,
                )
                self.logger().info("StandardWeb3 client initialized successfully")
            except Exception as e:
                self.logger().error(f"Failed to initialize StandardWeb3 client: {e}")
                raise
        else:
            raise ImportError("standardweb3 library is required for Somnia connector")
        
        # Initialize authentication
        self._auth = SomniaAuth(
            private_key=self._private_key,
            wallet_address=self._wallet_address,
        )
        
        # Initialize parent class
        super().__init__(
            client_config_map=client_config_map,
        )
        
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
        return SomniaAPIOrderBookDataSource(
            trading_pairs=self._trading_pairs,
            connector=self,
            api_factory=self._web_assistants_factory,
            domain=self._domain,
            throttler=self._throttler,
        )

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

    async def _format_trading_rules(self, exchange_info_dict: Dict[str, Any]) -> Dict[str, TradingRule]:
        """
        Format trading rules from exchange response.
        
        Args:
            exchange_info_dict: Exchange info dictionary
            
        Returns:
            Dictionary of trading rules
        """
        trading_rules = {}
        
        for trading_pair, rule_data in exchange_info_dict.items():
            try:
                trading_rule = self._parse_trading_rule(rule_data)
                trading_rules[trading_pair] = trading_rule
            except Exception as e:
                self.logger().error(f"Error formatting trading rule for {trading_pair}: {e}")
                
        return trading_rules

    async def _update_balances(self):
        """
        Update account balances.
        """
        try:
            if not self._standard_client:
                return
                
            # Get all relevant tokens
            tokens = set()
            for trading_pair in self._trading_pairs:
                base, quote = utils.split_trading_pair(trading_pair)
                tokens.add(base)
                tokens.add(quote)
            
            # Fetch balances using StandardClient
            balances = {}
            for token in tokens:
                try:
                    balance = await self._standard_client.get_balance(token)
                    balances[token] = Decimal(str(balance))
                except Exception as e:
                    self.logger().error(f"Error getting balance for {token}: {e}")
                    balances[token] = s_decimal_0
            
            # Update local balances
            self._account_balances = balances
            self._account_available_balances = balances.copy()
            
            self.logger().debug(f"Updated balances: {balances}")
            
        except Exception as e:
            self.logger().error(f"Error updating balances: {e}")

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
