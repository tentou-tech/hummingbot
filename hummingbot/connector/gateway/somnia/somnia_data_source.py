#!/usr/bin/env python

import asyncio
import logging
import time
from decimal import Decimal
from typing import Dict, List, Optional

from standardweb3 import StandardClient

from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType
from hummingbot.core.data_type.order_book_row import OrderBookRow
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.logger import HummingbotLogger

from .somnia_constants import API_ENDPOINTS, UPDATE_ORDERBOOK_INTERVAL
from .somnia_utils import execute_graphql_query, split_trading_pair


class SomniaOrderBookDataSource(OrderBookTrackerDataSource):
    _logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(self,
                 trading_pairs: List[str],
                 standard_client: StandardClient):
        """
        Initialize the OrderBookDataSource

        Args:
            trading_pairs: List of trading pairs to track
            standard_client: Instance of StandardClient for API interactions
        """
        super().__init__(trading_pairs)
        self._standard_client = standard_client
        self._order_book_create_function = lambda: OrderBook()
        self._tasks = {}

    async def get_last_traded_prices(self, trading_pairs: List[str]) -> Dict[str, Decimal]:
        """
        Fetch the last traded price for each trading pair

        Args:
            trading_pairs: List of trading pairs

        Returns:
            Dictionary mapping each trading pair to its last traded price
        """
        result = {}

        for trading_pair in trading_pairs:
            base_asset, quote_asset = split_trading_pair(trading_pair)

            variables = {
                "baseCurrency": base_asset,
                "quoteCurrency": quote_asset,
                "skip": 0,
                "first": 1
            }

            try:
                response = await execute_graphql_query(API_ENDPOINTS["recent_trades"], variables)
                trades = response.get("data", {}).get("trades", [])

                if trades:
                    last_trade = trades[0]
                    result[trading_pair] = Decimal(str(last_trade.get("price")))

            except Exception as e:
                self.logger().error(f"Error getting last traded price for {trading_pair}: {e}")

        return result

    async def get_new_order_book(self, trading_pair: str) -> OrderBook:
        """
        Creates a new order book for a trading pair

        Args:
            trading_pair: Trading pair to create order book for

        Returns:
            A new OrderBook instance
        """
        order_book = self._order_book_create_function()

        # Using StandardClient if available
        if self._standard_client:
            base, quote = split_trading_pair(trading_pair)
            try:
                orderbook_data = await self._standard_client.fetch_orderbook(
                    base=base,
                    quote=quote,
                    limit=100  # Or appropriate value
                )

                # Process orderbook data
                asks = []
                bids = []

                for order_data in orderbook_data["asks"]:
                    price = Decimal(str(order_data.get("price")))
                    amount = Decimal(str(order_data.get("amount")))
                    asks.append(OrderBookRow(price, amount, update_id=int(time.time() * 1000)))

                for order_data in orderbook_data["bids"]:
                    price = Decimal(str(order_data.get("price")))
                    amount = Decimal(str(order_data.get("amount")))
                    bids.append(OrderBookRow(price, amount, update_id=int(time.time() * 1000)))

                order_book.apply_snapshot(bids, asks, update_id=int(time.time() * 1000))
                return order_book

            except Exception as e:
                self.logger().error(f"Error fetching order book via StandardClient: {e}")

        # Fallback to GraphQL API if StandardClient fails or isn't available
        try:
            base_asset, quote_asset = split_trading_pair(trading_pair)

            variables = {
                "baseCurrency": base_asset,
                "quoteCurrency": quote_asset,
                "skip": 0,
                "first": 100  # Adjust depth as needed
            }

            response = await execute_graphql_query(API_ENDPOINTS["orderbook"], variables)
            orderbook_data = response.get("data", {})

            asks = []
            bids = []

            # Process sell orders (asks)
            for order_data in orderbook_data.get("sellOrders", []):
                price = Decimal(str(order_data.get("price")))
                amount = Decimal(str(order_data.get("baseAmount")))
                asks.append(OrderBookRow(price, amount, update_id=int(time.time() * 1000)))

            # Process buy orders (bids)
            for order_data in orderbook_data.get("buyOrders", []):
                price = Decimal(str(order_data.get("price")))
                amount = Decimal(str(order_data.get("baseAmount")))
                bids.append(OrderBookRow(price, amount, update_id=int(time.time() * 1000)))

            order_book.apply_snapshot(bids, asks, update_id=int(time.time() * 1000))
            return order_book

        except Exception as e:
            self.logger().error(f"Error getting order book snapshot: {e}", exc_info=True)
            raise

    async def _order_book_snapshot(self, trading_pair: str) -> OrderBookMessage:
        """
        Takes an order book snapshot for a specific trading pair

        Args:
            trading_pair: The trading pair to take snapshot for

        Returns:
            OrderBookMessage containing snapshot data
        """
        order_book = await self.get_new_order_book(trading_pair)
        timestamp = time.time()
        msg = OrderBookMessage(
            OrderBookMessageType.SNAPSHOT,
            {
                "trading_pair": trading_pair,
                "update_id": int(timestamp * 1000),
                "bids": [[float(bid.price), float(bid.amount)] for bid in order_book.bid_entries()],
                "asks": [[float(ask.price), float(ask.amount)] for ask in order_book.ask_entries()],
            },
            timestamp
        )
        return msg

    async def _create_order_book_snapshot_task(self, trading_pair: str):
        """
        Periodically takes order book snapshots

        Args:
            trading_pair: The trading pair to track
        """
        self.logger().debug(f"Starting order book snapshot task for {trading_pair}")

        while True:
            try:
                snapshot_msg = await self._order_book_snapshot(trading_pair)
                await self._order_book_snapshot_stream.put(snapshot_msg)
                self.logger().debug(f"Order book snapshot taken for {trading_pair}")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger().error(f"Error getting order book snapshot for {trading_pair}: {e}", exc_info=True)

            await asyncio.sleep(UPDATE_ORDERBOOK_INTERVAL)

    async def listen_for_trades(self, ev_loop: asyncio.AbstractEventLoop, output: asyncio.Queue):
        """
        Listen for trades from the exchange

        Args:
            ev_loop: Event loop
            output: Output queue for trade messages
        """
        while True:
            try:
                for trading_pair in self._trading_pairs:
                    base_asset, quote_asset = split_trading_pair(trading_pair)

                    variables = {
                        "baseCurrency": base_asset,
                        "quoteCurrency": quote_asset,
                        "skip": 0,
                        "first": 50  # Adjust as needed
                    }

                    response = await execute_graphql_query(API_ENDPOINTS["recent_trades"], variables)
                    trades = response.get("data", {}).get("trades", [])

                    # Process and queue trade messages
                    for trade in trades:
                        msg = {
                            "trading_pair": trading_pair,
                            "trade_type": int(trade["order"]["side"]),  # 0 for BUY, 1 for SELL
                            "trade_id": trade["id"],
                            "update_id": int(trade["timestamp"]),
                            "price": Decimal(str(trade["price"])),
                            "amount": Decimal(str(trade["baseAmount"])),
                            "timestamp": float(trade["timestamp"])
                        }

                        trade_message = OrderBookMessage(OrderBookMessageType.TRADE, msg, msg["timestamp"])
                        await output.put(trade_message)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger().error(f"Error fetching trades: {e}", exc_info=True)

            await asyncio.sleep(30)  # Adjust polling interval as needed

    async def listen_for_order_book_diffs(self, ev_loop: asyncio.AbstractEventLoop, output: asyncio.Queue):
        """
        Listen for order book diffs

        For Somnia, we don't have real-time diff updates, so we'll simulate them with snapshots

        Args:
            ev_loop: Event loop
            output: Output queue for diff messages
        """
        while True:
            try:
                for trading_pair in self._trading_pairs:
                    snapshot_msg = await self._order_book_snapshot(trading_pair)
                    await output.put(snapshot_msg)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger().error(f"Error in order book diff listener: {e}", exc_info=True)

            await asyncio.sleep(UPDATE_ORDERBOOK_INTERVAL)

    async def listen_for_order_book_snapshots(self, ev_loop: asyncio.AbstractEventLoop, output: asyncio.Queue):
        """
        Listen for order book snapshots

        Args:
            ev_loop: Event loop
            output: Output queue for snapshot messages
        """
        self._order_book_snapshot_stream = output

        # Create snapshot tasks for each trading pair
        for trading_pair in self._trading_pairs:
            task = safe_ensure_future(self._create_order_book_snapshot_task(trading_pair))
            self._tasks[f"snapshot_{trading_pair}"] = task
