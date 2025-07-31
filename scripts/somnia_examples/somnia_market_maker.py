#!/usr/bin/env python

"""
Simple market-making strategy for Somnia Exchange.

This script demonstrates a basic market-making strategy on Somnia exchange.
It places buy and sell orders around the mid-price with a configurable spread.
"""

import asyncio
import logging
from decimal import Decimal
from typing import List

from hummingbot.client.config.config_helpers import ClientConfigAdapter
from hummingbot.connector.gateway.somnia.somnia_connector import SomniaConnector
from hummingbot.core.clock import Clock, ClockMode
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.limit_order import LimitOrder
from hummingbot.core.event.events import OrderFilledEvent
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from hummingbot.strategy.strategy_py_base import StrategyPyBase

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SimpleMarketMakerSomnia(StrategyPyBase):
    """
    Simple market-making strategy for Somnia Exchange.
    """

    # Default parameters
    DEFAULT_BID_SPREAD = Decimal("0.01")  # 1% below mid price
    DEFAULT_ASK_SPREAD = Decimal("0.01")  # 1% above mid price
    DEFAULT_ORDER_REFRESH_TIME = 60.0  # 1 minute
    DEFAULT_ORDER_AMOUNT = Decimal("0.1")  # Base asset amount
    DEFAULT_ACTIVE_ORDERS_LIMIT = 2  # Maximum number of active orders

    def __init__(self,
                 market_info: MarketTradingPairTuple,
                 bid_spread: Decimal = DEFAULT_BID_SPREAD,
                 ask_spread: Decimal = DEFAULT_ASK_SPREAD,
                 order_refresh_time: float = DEFAULT_ORDER_REFRESH_TIME,
                 order_amount: Decimal = DEFAULT_ORDER_AMOUNT,
                 active_orders_limit: int = DEFAULT_ACTIVE_ORDERS_LIMIT):
        """
        Initialize strategy parameters.

        Args:
            market_info: Market trading pair info
            bid_spread: Percentage below mid price to place buy orders
            ask_spread: Percentage above mid price to place sell orders
            order_refresh_time: Time in seconds to refresh orders
            order_amount: Order amount in base asset
            active_orders_limit: Maximum number of active orders
        """
        super().__init__()
        self._market_info = market_info
        self._bid_spread = bid_spread
        self._ask_spread = ask_spread
        self._order_refresh_time = order_refresh_time
        self._order_amount = order_amount
        self._active_orders_limit = active_orders_limit

        # State variables
        self._last_timestamp = 0
        self._current_bids = []
        self._current_asks = []

        # Register event listeners
        self.add_markets([market_info.market])

    def active_orders_count(self) -> int:
        """
        Count of active orders placed by the strategy.
        """
        return len(self._current_bids) + len(self._current_asks)

    def active_bids_count(self) -> int:
        """
        Count of active bid orders.
        """
        return len(self._current_bids)

    def active_asks_count(self) -> int:
        """
        Count of active ask orders.
        """
        return len(self._current_asks)

    @property
    def active_limit_orders(self) -> List[LimitOrder]:
        """
        List of active limit orders placed by the strategy.
        """
        return self._sb_order_tracker.active_limit_orders

    def format_status(self) -> str:
        """
        Format strategy status for display.
        """
        if not self._ready_to_trade:
            return "Market connectors are not ready."

        lines = []
        lines.append(f"Exchange: {self._market_info.market.display_name}")
        lines.append(f"Trading Pair: {self._market_info.trading_pair}")
        lines.append("")

        # Get market mid price
        mid_price = self.get_mid_price()
        lines.append(f"Current mid price: {mid_price:.8g}")

        # Display order book info
        best_bid = self._market_info.market.get_price(self._market_info.trading_pair, False)
        best_ask = self._market_info.market.get_price(self._market_info.trading_pair, True)
        lines.append(f"Best bid: {best_bid:.8g}, Best ask: {best_ask:.8g}")

        # Display active orders
        lines.append("")
        lines.append("Active orders:")
        if self.active_orders_count() == 0:
            lines.append("  No active orders")
        else:
            for order in self.active_limit_orders:
                side = "BUY" if order.is_buy else "SELL"
                lines.append(f"  {side} {order.quantity:.8g} @ {order.price:.8g}")

        # Display strategy parameters
        lines.append("")
        lines.append("Strategy parameters:")
        lines.append(f"  Bid spread: {self._bid_spread:.2%}")
        lines.append(f"  Ask spread: {self._ask_spread:.2%}")
        lines.append(f"  Order amount: {self._order_amount}")
        lines.append(f"  Order refresh time: {self._order_refresh_time} seconds")

        return "\n".join(lines)

    def get_mid_price(self) -> Decimal:
        """
        Calculate the mid price from order book.
        """
        market = self._market_info.market
        trading_pair = self._market_info.trading_pair

        # Get the bid and ask prices
        bid_price = market.get_price(trading_pair, True)  # True for buy
        ask_price = market.get_price(trading_pair, False)  # False for sell

        # Calculate mid price
        mid_price = (bid_price + ask_price) / Decimal("2")
        return mid_price

    async def cancel_all_orders(self):
        """
        Cancel all active orders.
        """
        for order in self.active_limit_orders:
            self.cancel_order(self._market_info, order.client_order_id)

    def place_orders(self):
        """
        Place new orders based on the current market conditions.
        """
        # Get the current mid price
        mid_price = self.get_mid_price()
        if mid_price == Decimal("0"):
            logger.warning("Unable to place orders: mid price is 0.")
            return

        # Calculate bid and ask prices
        bid_price = mid_price * (Decimal("1") - self._bid_spread)
        ask_price = mid_price * (Decimal("1") + self._ask_spread)

        # Quantize prices to match exchange requirements
        bid_price = self.quantize_order_price(self._market_info.trading_pair, bid_price)
        ask_price = self.quantize_order_price(self._market_info.trading_pair, ask_price)

        # Quantize order amount
        order_amount = self.quantize_order_amount(self._market_info.trading_pair, self._order_amount)

        # Check if we can place orders
        if self.active_orders_count() >= self._active_orders_limit:
            logger.info("Maximum number of active orders reached. Not placing new orders.")
            return

        # Place the bid order
        if self.active_bids_count() < self._active_orders_limit / 2:
            self.buy_with_specific_market(
                self._market_info,
                order_amount,
                OrderType.LIMIT,
                bid_price
            )
            logger.info(f"Placed buy order: {order_amount} @ {bid_price}")

        # Place the ask order
        if self.active_asks_count() < self._active_orders_limit / 2:
            self.sell_with_specific_market(
                self._market_info,
                order_amount,
                OrderType.LIMIT,
                ask_price
            )
            logger.info(f"Placed sell order: {order_amount} @ {ask_price}")

    def did_fill_order(self, event: OrderFilledEvent):
        """
        Handle order filled event.
        """
        order_id = event.order_id
        price = event.price
        amount = event.amount
        trade_type = "BUY" if event.trade_type is TradeType.BUY else "SELL"

        logger.info(f"Order filled: {trade_type} {amount} @ {price}")

        # Update the current bids/asks lists
        if trade_type == "BUY":
            self._current_bids = [bid for bid in self._current_bids if bid.client_order_id != order_id]
        else:
            self._current_asks = [ask for ask in self._current_asks if ask.client_order_id != order_id]

    def process_order_update(self, event):
        """
        Process order update events.
        """
        client_order_id = event.client_order_id
        order_type = "BUY" if event.trade_type is TradeType.BUY else "SELL"

        logger.info(f"Order update: {order_type} {client_order_id}")

    def tick(self, timestamp: float):
        """
        Called on each clock tick.
        """
        now = timestamp

        # Check if it's time to refresh orders
        if now > self._last_timestamp + self._order_refresh_time:
            # Cancel existing orders
            if self.active_orders_count() > 0:
                logger.info("Refreshing orders - cancelling existing orders")
                asyncio.create_task(self.cancel_all_orders())

            # Place new orders
            self.place_orders()

            # Update the timestamp
            self._last_timestamp = now

# Example usage


async def main():
    # Configuration
    private_key = "your_private_key_here"  # Replace with your private key
    rpc_url = "https://dream-rpc.somnia.network"  # Somnia testnet RPC URL
    trading_pair = "ATOM-USDC"  # Example trading pair

    try:
        # Create an empty config adapter
        client_config_map = ClientConfigAdapter(ClientConfigAdapter.create_empty_config_dict())

        # Initialize the connector
        connector = SomniaConnector(
            client_config_map=client_config_map,
            private_key=private_key,
            rpc_url=rpc_url,
            trading_pairs=[trading_pair],
            trading_required=True
        )

        # Start the connector
        await connector.start_network()
        logger.info("Somnia connector started")

        # Wait for the connector to be ready
        await asyncio.sleep(5)

        # Create market info
        market_info = MarketTradingPairTuple(connector, trading_pair, "ATOM", "USDC")

        # Create strategy
        strategy = SimpleMarketMakerSomnia(
            market_info=market_info,
            bid_spread=Decimal("0.01"),  # 1%
            ask_spread=Decimal("0.01"),  # 1%
            order_refresh_time=60.0,     # 60 seconds
            order_amount=Decimal("0.1")  # 0.1 ATOM
        )

        # Create and start clock
        clock = Clock(ClockMode.REALTIME)
        clock.add_iterator(connector)
        clock.add_iterator(strategy)

        logger.info("Starting market making strategy...")

        # Run the clock for a specified duration
        with clock:
            await asyncio.sleep(3600)  # Run for 1 hour

    except Exception as e:
        logger.error(f"Error in market making strategy: {e}", exc_info=True)
    finally:
        # Stop the connector
        await connector.stop_network()
        logger.info("Somnia connector stopped")

if __name__ == "__main__":
    # Run the market making strategy
    asyncio.run(main())
