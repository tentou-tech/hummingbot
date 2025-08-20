#!/usr/bin/env python

import asyncio
import logging
from collections import defaultdict
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from hummingbot.connector.exchange.somnia import (
    somnia_constants as CONSTANTS,
    somnia_utils as utils,
    somnia_web_utils as web_utils,
)
from hummingbot.connector.exchange.somnia.somnia_order_book import SomniaOrderBook
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.connector.exchange.somnia.somnia_exchange import SomniaExchange


class SomniaAPIOrderBookDataSource(OrderBookTrackerDataSource):
    """
    Order book data source for Somnia exchange.
    """
    
    _logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(
        self,
        trading_pairs: List[str],
        connector: "SomniaExchange",
        api_factory: Optional[WebAssistantsFactory] = None,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
        throttler: Optional[AsyncThrottler] = None,
    ):
        super().__init__(trading_pairs)
        self._connector = connector
        self._domain = domain
        self._throttler = throttler or web_utils.create_throttler()
        self._api_factory = api_factory or web_utils.build_api_factory(
            throttler=self._throttler,
        )
        self._message_queue: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self._last_orderbook_timestamp: Dict[str, float] = {}

    async def get_last_traded_prices(
        self, 
        trading_pairs: List[str], 
        domain: Optional[str] = None
    ) -> Dict[str, float]:
        """
        Get last traded prices for trading pairs.
        
        Args:
            trading_pairs: List of trading pairs
            domain: Domain (unused for Somnia)
            
        Returns:
            Dictionary mapping trading pairs to last prices
        """
        result = {}
        
        for trading_pair in trading_pairs:
            try:
                base, quote = utils.split_trading_pair(trading_pair)
                base_address = utils.convert_symbol_to_address(base)
                quote_address = utils.convert_symbol_to_address(quote)
                
                if not base_address or not quote_address:
                    self.logger().warning(f"Could not get addresses for {trading_pair}")
                    continue
                
                # Build GraphQL request for recent trades
                variables = {
                    "baseCurrency": base_address,
                    "quoteCurrency": quote_address,
                    "skip": 0,
                    "first": 1
                }
                
                request_payload = web_utils.build_graphql_request(
                    CONSTANTS.GRAPHQL_QUERIES["recent_trades"],
                    variables
                )
                
                rest_assistant = await self._api_factory.get_rest_assistant()
                response = await rest_assistant.execute_request(
                    url=web_utils.public_rest_url("graphql"),
                    data=request_payload,
                    method=RESTMethod.POST,
                    throttler_limit_id="trades",
                )
                
                trades = response.get("data", {}).get("trades", [])
                if trades:
                    last_trade = trades[0]
                    result[trading_pair] = float(last_trade.get("price", 0))
                    
            except Exception as e:
                self.logger().error(f"Error getting last traded price for {trading_pair}: {e}")
                
        return result

    async def _order_book_snapshot(self, trading_pair: str) -> OrderBookMessage:
        """
        Get order book snapshot for a trading pair.
        
        Args:
            trading_pair: Trading pair
            
        Returns:
            OrderBookMessage with snapshot data
        """
        snapshot = await self._request_order_book_snapshot(trading_pair)
        snapshot_timestamp = utils.generate_timestamp()
        
        # Parse the snapshot data
        asks = []
        bids = []
        
        # Extract order book data from GraphQL response
        sell_orders = snapshot.get("data", {}).get("sellOrders", [])
        buy_orders = snapshot.get("data", {}).get("buyOrders", [])
        
        for order in sell_orders:
            price = float(order.get("price", 0))
            amount = float(order.get("baseAmount", 0))
            asks.append([price, amount])
            
        for order in buy_orders:
            price = float(order.get("price", 0))
            amount = float(order.get("baseAmount", 0))
            bids.append([price, amount])
        
        # Prepare data for SomniaOrderBook
        snapshot_data = {
            "trading_pair": trading_pair,
            "bids": bids,
            "asks": asks,
        }
        
        # Create order book message using SomniaOrderBook
        snapshot_msg = SomniaOrderBook.snapshot_message_from_exchange_rest(
            snapshot_data, snapshot_timestamp
        )
        
        return snapshot_msg

    async def _request_order_book_snapshot(self, trading_pair: str) -> Dict[str, Any]:
        """
        Request order book snapshot from the exchange.
        
        Args:
            trading_pair: Trading pair
            
        Returns:
            Raw order book data from exchange
        """
        base, quote = utils.split_trading_pair(trading_pair)
        base_address = utils.convert_symbol_to_address(base)
        quote_address = utils.convert_symbol_to_address(quote)
        
        if not base_address or not quote_address:
            raise ValueError(f"Could not get addresses for {trading_pair}")
        
        variables = {
            "baseCurrency": base_address,
            "quoteCurrency": quote_address,
            "skip": 0,
            "first": 100  # Get top 100 orders on each side
        }
        
        request_payload = web_utils.build_graphql_request(
            CONSTANTS.GRAPHQL_QUERIES["orderbook"],
            variables
        )
        
        rest_assistant = await self._api_factory.get_rest_assistant()
        
        response = await rest_assistant.execute_request(
            url=web_utils.public_rest_url("graphql"),
            data=request_payload,
            method=RESTMethod.POST,
            throttler_limit_id="orderbook",
        )
        
        return response

    async def _parse_order_book_diff_message(
        self, 
        raw_message: Dict[str, Any], 
        message_queue: asyncio.Queue
    ):
        """
        Parse order book differential update message.
        
        Args:
            raw_message: Raw message from WebSocket
            message_queue: Queue to put parsed message
        """
        # Implementation for WebSocket order book updates
        # This would be called when receiving real-time order book updates
        pass

    async def _parse_trade_message(
        self, 
        raw_message: Dict[str, Any], 
        message_queue: asyncio.Queue
    ):
        """
        Parse trade message from WebSocket.
        
        Args:
            raw_message: Raw trade message
            message_queue: Queue to put parsed message
        """
        # Implementation for WebSocket trade updates
        # This would be called when receiving real-time trade data
        pass

    def _channel_originating_message(self, event_message: Dict[str, Any]) -> str:
        """
        Determine which channel an event message originated from.
        
        Args:
            event_message: Event message
            
        Returns:
            Channel name
        """
        # For Somnia, determine the message type/channel
        if "orderbook" in str(event_message).lower():
            return "orderbook"
        elif "trade" in str(event_message).lower():
            return "trades"
        return "unknown"

    async def _connected_websocket_assistant(self) -> None:
        """
        Create and maintain WebSocket connection for real-time data.
        """
        # Implementation for WebSocket connection
        # This would establish a WebSocket connection to receive real-time updates
        # For now, we'll rely on periodic REST API calls
        pass

    async def _subscribe_channels(self, ws_assistant) -> None:
        """
        Subscribe to WebSocket channels for order book and trade data.
        
        Args:
            ws_assistant: WebSocket assistant
        """
        # Implementation for WebSocket channel subscription
        # This would subscribe to relevant channels for real-time data
        pass

    async def _process_websocket_messages(self, websocket_assistant) -> None:
        """
        Process incoming WebSocket messages.
        
        Args:
            websocket_assistant: WebSocket assistant
        """
        # Implementation for processing WebSocket messages
        # This would handle incoming real-time data
        pass
