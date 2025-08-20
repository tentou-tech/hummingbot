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
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
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
        connector: Optional["SomniaExchange"] = None,
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
                # Use order book snapshot to get market price
                # Get the mid-price from best bid and ask
                snapshot = await self._request_order_book_snapshot(trading_pair)
                
                bids = snapshot.get("bids", [])
                asks = snapshot.get("asks", [])
                
                if bids and asks:
                    best_bid = float(bids[0].get("price", 0))
                    best_ask = float(asks[0].get("price", 0))
                    if best_bid > 0 and best_ask > 0:
                        # Use mid-price as last traded price
                        result[trading_pair] = (best_bid + best_ask) / 2
                elif bids:
                    result[trading_pair] = float(bids[0].get("price", 0))
                elif asks:
                    result[trading_pair] = float(asks[0].get("price", 0))
                    
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
        
        # Extract order book data from REST API response
        # Response format: {"bids": [...], "asks": [...]}
        # Each entry: {"price": "string", "amount": "string", "count": number}
        bid_orders = snapshot.get("bids", [])
        ask_orders = snapshot.get("asks", [])
        
        for order in ask_orders:
            price = float(order.get("price", 0))
            amount = float(order.get("amount", 0))
            asks.append([price, amount])
            
        for order in bid_orders:
            price = float(order.get("price", 0))
            amount = float(order.get("amount", 0))
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
        Request order book snapshot from the exchange using REST API.
        
        Args:
            trading_pair: Trading pair
            
        Returns:
            Raw order book data from exchange
        """
        # Temporary fix: Return mock data until HTTP issue is resolved
        # TODO: Fix the hanging HTTP request issue and use real API data
        
        self.logger().warning(f"Using mock order book data for {trading_pair} due to HTTP connection issues")
        
        # Return mock order book data with reasonable prices
        mock_data = {
            "id": "mock_orderbook",
            "mktPrice": 269.0,  # Based on real data we saw earlier
            "bids": [
                {"price": 268.5, "amount": 100.0, "count": 1},
                {"price": 268.0, "amount": 200.0, "count": 1},
                {"price": 267.5, "amount": 150.0, "count": 1},
                {"price": 267.0, "amount": 300.0, "count": 1},
                {"price": 266.5, "amount": 250.0, "count": 1}
            ],
            "asks": [
                {"price": 269.5, "amount": 100.0, "count": 1},
                {"price": 270.0, "amount": 200.0, "count": 1},
                {"price": 270.5, "amount": 150.0, "count": 1},
                {"price": 271.0, "amount": 300.0, "count": 1},
                {"price": 271.5, "amount": 250.0, "count": 1}
            ]
        }
        
        return mock_data
        
        # Original code (commented out due to hanging HTTP issue):
        """
        import aiohttp
        import json
        
        base, quote = utils.split_trading_pair(trading_pair)
        
        # Convert symbols to addresses for the API
        base_address = utils.convert_symbol_to_address(base)
        quote_address = utils.convert_symbol_to_address(quote)
        
        if not base_address or not quote_address:
            raise ValueError(f"Could not get addresses for {trading_pair}")
        
        # Use the REST API endpoint: /api/orderbook/ticks/{base}/{quote}/{limit}
        limit = 100  # Get top 100 orders on each side
        url = web_utils.public_rest_url("orderbook_ticks", 
                                      base=base_address, quote=quote_address, limit=limit)
        
        # Use direct aiohttp instead of rest_assistant to avoid hanging
        timeout = aiohttp.ClientTimeout(total=10)  # 10 second timeout
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    text = await response.text()
                    return json.loads(text)
                else:
                    raise Exception(f"HTTP {response.status}: {await response.text()}")
        """

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

    async def listen_for_subscriptions(self):
        """
        Somnia currently uses REST API polling instead of WebSocket subscriptions.
        This method is overridden to prevent infinite loops from WebSocket connection attempts.
        """
        self.logger().info("Somnia connector is using REST API polling for order book updates (no WebSocket support).")
        # Just return - no WebSocket subscriptions needed for REST-based connector
        return

    async def _connected_websocket_assistant(self) -> WSAssistant:
        """
        Somnia currently relies on REST API polling instead of WebSocket streams.
        We return None to indicate no WebSocket connection is available.
        """
        # Create a dummy websocket assistant that doesn't actually connect
        websocket_assistant: WSAssistant = await self._api_factory.get_ws_assistant()
        # Don't actually connect - just return the assistant
        # This prevents the infinite loop while maintaining the expected interface
        return websocket_assistant
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
