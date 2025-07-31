#!/usr/bin/env python

import asyncio
import logging
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from standardweb3 import StandardClient

from hummingbot.connector.gateway.gateway_evm_amm import GatewayEVMAMM
from hummingbot.connector.gateway.gateway_order_tracker import GatewayOrderTracker
from hummingbot.core.data_type.cancellation_result import CancellationResult
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.trade_fee import TokenAmount, TradeFeeBase
from hummingbot.core.event.events import (
    MarketEvent,
    OrderFilledEvent,
    TokenApprovalCancelledEvent,
    TokenApprovalEvent,
    TokenApprovalSuccessEvent,
)
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.logger import HummingbotLogger

from .somnia_constants import (
    DEFAULT_GAS_LIMIT_CANCEL,
    DEFAULT_GAS_PRICE,
    SOMNIA_CHAIN_ID,
    SOMNIA_RPC_URL,
    SOMNIA_TESTNET_TRADING_PAIRS,
    UPDATE_BALANCES_INTERVAL,
)
from .somnia_data_source import SomniaOrderBookDataSource
from .somnia_utils import generate_timestamp, split_trading_pair


class SomniaConnector(GatewayEVMAMM):
    """
    Connector for Somnia Exchange using standard.py library
    """

    # Class variables
    _logger = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(
        self,
        client_config_map: Dict[str, Any],
        private_key: str,
        rpc_url: str = SOMNIA_RPC_URL,
        chain_id: int = SOMNIA_CHAIN_ID,
        trading_pairs: Optional[List[str]] = None,
        trading_required: bool = True,
    ):
        """
        Initialize the connector

        Args:
            client_config_map: Client configuration map
            private_key: Private key for signing transactions
            rpc_url: RPC URL for the blockchain
            chain_id: Chain ID
            trading_pairs: List of trading pairs
            trading_required: Whether trading is enabled
        """
        self._name = "somnia"

        # Setup StandardClient
        self._standard_client = StandardClient(
            private_key=private_key,
            http_rpc_url=rpc_url,
            networkName="Somnia Testnet",  # Could be parameterized
            chainId=chain_id
        )

        # Configure connector settings
        self._trading_pairs = trading_pairs or SOMNIA_TESTNET_TRADING_PAIRS
        self._trading_required = trading_required
        self._order_tracker = GatewayOrderTracker(connector=self)
        self._ev_loop = asyncio.get_event_loop()

        # Configure order book data source
        self._data_source = SomniaOrderBookDataSource(
            trading_pairs=self._trading_pairs,
            standard_client=self._standard_client
        )

        # Balance update task
        self._update_balances_task = None

        # Initialize base class (GatewayEVMAMM)
        super().__init__(
            client_config_map=client_config_map,
            connector_name=self._name,
            chain=self._name,  # Using connector name as chain
            network=self._name,  # Using connector name as network
            wallet_address=self._standard_client.address,
            trading_pairs=trading_pairs,
            trading_required=trading_required
        )

    async def start_network(self):
        """Start connector network components"""

        self.logger().info("Starting Somnia connector network...")

        # Start the base connector network
        await super().start_network()

        # Schedule balance updates
        if self._trading_required:
            self._update_balances_task = safe_ensure_future(self._update_balances_loop())

        # Setup event listeners for StandardClient events
        self._setup_standard_client_listeners()

        self.logger().info("Somnia connector network started.")

    async def stop_network(self):
        """Stop connector network components"""

        self.logger().info("Stopping Somnia connector network...")

        # Cancel ongoing tasks
        if self._update_balances_task is not None:
            self._update_balances_task.cancel()
            self._update_balances_task = None

        # Stop the base connector network
        await super().stop_network()

        # Clean up StandardClient resources if needed
        # (StandardClient might have its own cleanup methods)

        self.logger().info("Somnia connector network stopped.")

    def _setup_standard_client_listeners(self):
        """Setup event listeners for StandardClient events"""

        # These are placeholder methods - the actual implementation would depend on
        # what events StandardClient emits and how they are structured

        # Example for order filled events
        self._standard_client.on_order_filled(self._on_order_filled)

        # Example for order created events
        self._standard_client.on_order_created(self._on_order_created)

        # Example for order cancelled events
        self._standard_client.on_order_cancelled(self._on_order_cancelled)

    async def _update_balances_loop(self):
        """Periodically update user balances"""
        while True:
            try:
                await self._update_balances()
                await asyncio.sleep(UPDATE_BALANCES_INTERVAL)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger().error(f"Error updating balances: {e}", exc_info=True)
                await asyncio.sleep(UPDATE_BALANCES_INTERVAL)

    async def _update_balances(self):
        """Update user balances from the exchange"""

        # Get all relevant tokens from trading pairs
        tokens = set()
        for trading_pair in self._trading_pairs:
            base, quote = split_trading_pair(trading_pair)
            tokens.add(base)
            tokens.add(quote)

        # Fetch balances for all tokens
        balances = {}
        for token in tokens:
            try:
                # Use StandardClient to get token balance
                balance = await self._standard_client.get_balance(token)
                balances[token] = Decimal(str(balance))
            except Exception as e:
                self.logger().error(f"Error fetching balance for {token}: {e}", exc_info=True)

        # Update local balances
        self._account_balances = balances
        self._account_available_balances = balances.copy()  # For simplicity, assuming all balance is available

        self.logger().debug(f"Updated balances: {balances}")

    async def get_order_price_quote(
        self, trading_pair: str, is_buy: bool, amount: Decimal, ignore_shim: bool = False
    ) -> Decimal:
        """
        Get price quote for creating an order

        Args:
            trading_pair: Trading pair
            is_buy: True for buy, False for sell
            amount: Amount to trade
            ignore_shim: Whether to ignore price shim

        Returns:
            Quote price
        """
        base, quote = split_trading_pair(trading_pair)

        # Use price shim if available and not ignored
        if not ignore_shim:
            price_shim = self._price_shim
            if price_shim is not None:
                price = await price_shim.get_order_price_quote(trading_pair, is_buy, amount)
                if price is not None:
                    return price

        # Get quote from order book
        orderbook = await self._data_source.get_new_order_book(trading_pair)
        if is_buy:
            # For buys, get the lowest ask price
            price = orderbook.get_price(is_buy=False)
        else:
            # For sells, get the highest bid price
            price = orderbook.get_price(is_buy=True)

        return price

    async def approve_token(self, token_symbol: str, amount: Decimal, **request_args) -> str:
        """
        Approve spending limit for a token

        Args:
            token_symbol: Symbol of the token to approve
            amount: Amount to approve
            request_args: Additional request arguments

        Returns:
            Transaction hash of the approval
        """
        self.logger().info(f"Approving {amount} of {token_symbol}...")

        try:
            # Use StandardClient for token approval
            tx_hash = await self._standard_client.approve_token(
                token_symbol,
                str(amount),  # Convert Decimal to string for StandardClient
                gas_price=DEFAULT_GAS_PRICE
            )

            # Emit approval event
            self.trigger_event(
                TokenApprovalEvent.ApprovalSubmitted,
                TokenApprovalEvent(
                    timestamp=generate_timestamp(),
                    token_symbol=token_symbol,
                    amount=amount,
                    exchange_name=self.name,
                )
            )

            # Wait for the transaction to be confirmed
            # This will depend on how StandardClient handles transaction confirmation
            tx_receipt = await self._standard_client.wait_for_transaction(tx_hash)

            if tx_receipt and tx_receipt.get("status") == 1:
                self.logger().info(f"Token approval for {token_symbol} successful with tx hash: {tx_hash}")
                # Emit success event
                self.trigger_event(
                    TokenApprovalEvent.ApprovalSuccessful,
                    TokenApprovalSuccessEvent(
                        timestamp=generate_timestamp(),
                        token_symbol=token_symbol,
                        amount=amount,
                        exchange_name=self.name,
                    )
                )
            else:
                self.logger().error(f"Token approval for {token_symbol} failed with tx hash: {tx_hash}")
                # Emit cancellation event
                self.trigger_event(
                    TokenApprovalEvent.ApprovalCancelled,
                    TokenApprovalCancelledEvent(
                        timestamp=generate_timestamp(),
                        token_symbol=token_symbol,
                        amount=amount,
                        exchange_name=self.name,
                    )
                )

            return tx_hash

        except Exception as e:
            self.logger().error(f"Error in token approval for {token_symbol}: {e}", exc_info=True)
            # Emit cancellation event
            self.trigger_event(
                TokenApprovalEvent.ApprovalCancelled,
                TokenApprovalCancelledEvent(
                    timestamp=generate_timestamp(),
                    token_symbol=token_symbol,
                    amount=amount,
                    exchange_name=self.name,
                )
            )
            raise

    async def _create_order(
        self,
        trade_type: TradeType,
        order_id: str,
        trading_pair: str,
        amount: Decimal,
        order_type: OrderType,
        price: Optional[Decimal] = None,
        **kwargs
    ) -> Tuple[str, float]:
        """
        Create an order with the exchange

        Args:
            trade_type: TradeType.BUY or TradeType.SELL
            order_id: Client order ID
            trading_pair: Trading pair
            amount: Amount to trade
            order_type: OrderType.LIMIT or OrderType.MARKET
            price: Price for limit orders
            kwargs: Additional arguments

        Returns:
            Tuple of (transaction hash, timestamp)
        """
        is_buy = trade_type is TradeType.BUY
        base, quote = split_trading_pair(trading_pair)

        if order_type is OrderType.LIMIT:
            if price is None:
                raise ValueError("Price is required for limit orders")

            self.logger().info(f"Creating {'buy' if is_buy else 'sell'} limit order for {amount} {base} at {price} {quote}")

            try:
                # Use StandardClient to place order
                if is_buy:
                    # Calculate quote amount (amount * price)
                    quote_amount = amount * price

                    tx_hash = await self._standard_client.limit_buy(
                        base=base,
                        quote=quote,
                        price=str(price),
                        quote_amount=str(quote_amount),
                        is_maker=True,  # Default to maker orders
                        n=0,  # Order nonce or sequence - may need adjustment
                        uid=order_id,  # Use client order ID as UID
                        recipient=self._standard_client.address
                    )
                else:
                    tx_hash = await self._standard_client.limit_sell(
                        base=base,
                        quote=quote,
                        price=str(price),
                        base_amount=str(amount),
                        is_maker=True,  # Default to maker orders
                        n=0,  # Order nonce or sequence - may need adjustment
                        uid=order_id,  # Use client order ID as UID
                        recipient=self._standard_client.address
                    )

                timestamp = time.time()
                return tx_hash, timestamp

            except Exception as e:
                self.logger().error(f"Error creating limit order: {e}", exc_info=True)
                raise

        elif order_type is OrderType.MARKET:
            self.logger().info(f"Creating {'buy' if is_buy else 'sell'} market order for {amount} {base}")

            try:
                # Use StandardClient to place market order
                if is_buy:
                    # For market buy, we need the quote amount
                    # We'll use the current price to estimate
                    current_price = await self.get_order_price_quote(trading_pair, is_buy, amount)
                    quote_amount = amount * current_price

                    tx_hash = await self._standard_client.market_buy(
                        base=base,
                        quote=quote,
                        quote_amount=str(quote_amount),
                        uid=order_id,  # Use client order ID as UID
                        recipient=self._standard_client.address
                    )
                else:
                    tx_hash = await self._standard_client.market_sell(
                        base=base,
                        quote=quote,
                        base_amount=str(amount),
                        uid=order_id,  # Use client order ID as UID
                        recipient=self._standard_client.address
                    )

                timestamp = time.time()
                return tx_hash, timestamp

            except Exception as e:
                self.logger().error(f"Error creating market order: {e}", exc_info=True)
                raise
        else:
            raise ValueError(f"Unsupported order type: {order_type}")

    async def _execute_cancel(self, order_id: str, cancel_age: int) -> CancellationResult:
        """
        Execute order cancellation

        Args:
            order_id: Order ID to cancel
            cancel_age: Age of the order in seconds

        Returns:
            CancellationResult
        """
        in_flight_order = self._order_tracker.fetch_order(client_order_id=order_id)

        if in_flight_order is None:
            self.logger().error(f"Failed to cancel order {order_id}: order not found in tracking")
            return CancellationResult(order_id=order_id, success=False)

        try:
            # Use StandardClient for cancellation
            tx_hash = await self._standard_client.cancel_order(
                order_id=in_flight_order.exchange_order_id,
                gas_price=DEFAULT_GAS_PRICE,
                gas_limit=DEFAULT_GAS_LIMIT_CANCEL
            )

            # Wait for confirmation if needed
            # This depends on how StandardClient handles transaction confirmation

            self.logger().info(f"Order {order_id} cancelled with tx hash: {tx_hash}")

            return CancellationResult(order_id=order_id, success=True)

        except Exception as e:
            self.logger().error(f"Failed to cancel order {order_id}: {e}", exc_info=True)
            return CancellationResult(order_id=order_id, success=False)

    # Order event handlers

    def _on_order_filled(self, event_data: Dict[str, Any]):
        """Handle order filled event from StandardClient"""

        try:
            # Extract relevant data from the event
            # This will depend on StandardClient event structure
            order_id = event_data.get("order_id")
            exchange_order_id = event_data.get("exchange_order_id")
            trade_id = event_data.get("trade_id")
            trading_pair = event_data.get("trading_pair")
            is_buy = event_data.get("side") == "buy"  # Adjust based on StandardClient convention
            fill_amount = Decimal(str(event_data.get("amount")))
            fill_price = Decimal(str(event_data.get("price")))
            timestamp = event_data.get("timestamp", time.time())

            # Fetch the in-flight order
            tracked_order = self._order_tracker.fetch_order(exchange_order_id=exchange_order_id)

            if tracked_order is None:
                tracked_order = self._order_tracker.fetch_order(client_order_id=order_id)

                if tracked_order is None:
                    self.logger().info(f"Order {order_id} ({exchange_order_id}) not found in order tracker.")
                    return

            # Update order status
            tracked_order.update_with_trade_update(
                trade_id=trade_id,
                fill_price=fill_price,
                fill_base_amount=fill_amount,
                fill_quote_amount=fill_amount * fill_price,
                fee=TradeFeeBase.to_json([]),  # Placeholder for fee information
                exchange_trade_id=trade_id
            )

            # Emit order filled event
            self.trigger_event(
                MarketEvent.OrderFilled,
                OrderFilledEvent(
                    timestamp=timestamp,
                    order_id=tracked_order.client_order_id,
                    trading_pair=trading_pair,
                    trade_type=TradeType.BUY if is_buy else TradeType.SELL,
                    order_type=tracked_order.order_type,
                    price=fill_price,
                    amount=fill_amount,
                    trade_fee=TradeFeeBase.to_json([]),  # Placeholder for fee information
                    exchange_trade_id=trade_id,
                    leverage=1,  # Default for spot trading
                    position=None  # Default for spot trading
                )
            )

        except Exception as e:
            self.logger().error(f"Error processing order filled event: {e}", exc_info=True)

    def _on_order_created(self, event_data: Dict[str, Any]):
        """Handle order created event from StandardClient"""

        # Implementation would depend on StandardClient event structure
        # This is a placeholder
        self.logger().info(f"Order created event received: {event_data}")

    def _on_order_cancelled(self, event_data: Dict[str, Any]):
        """Handle order cancelled event from StandardClient"""

        # Implementation would depend on StandardClient event structure
        # This is a placeholder
        self.logger().info(f"Order cancelled event received: {event_data}")

    # Additional required methods to implement from GatewayEVMAMM

    def get_fee(
        self,
        base_currency: str,
        quote_currency: str,
        order_type: OrderType,
        order_side: TradeType,
        amount: Decimal,
        price: Decimal = Decimal("0"),
        is_maker: Optional[bool] = None
    ) -> TradeFeeBase:
        """
        Get the fee for an order

        Args:
            base_currency: Base currency
            quote_currency: Quote currency
            order_type: Order type
            order_side: Order side
            amount: Order amount
            price: Order price
            is_maker: Whether the order is a maker order

        Returns:
            TradeFeeBase
        """
        # This is a placeholder implementation
        # Actual fee calculation would depend on Somnia's fee structure

        # For simplicity, using a fixed percentage fee
        fee_percent = Decimal("0.001")  # 0.1%

        if order_side == TradeType.BUY:
            fee_currency = base_currency
            fee_amount = amount * fee_percent
        else:
            fee_currency = quote_currency
            fee_amount = amount * price * fee_percent

        return TradeFeeBase.new_spot_fee(
            fee_schema=TradeFeeBase.FeeSchema.PERCENT,
            percent=fee_percent,
            percent_token=fee_currency,
            flat_fees=[TokenAmount(token=fee_currency, amount=fee_amount)]
        )
