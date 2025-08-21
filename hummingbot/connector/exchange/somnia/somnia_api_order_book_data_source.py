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
from hummingbot.core.data_type.order_book import OrderBook
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
        self._api_factory = api_factory
        self._throttler = throttler
        self.logger().info(f"SomniaAPIOrderBookDataSource initialized with trading_pairs: {trading_pairs}")
        self.logger().info(f"Connector provided: {connector is not None}")
        self.logger().info(f"API factory provided: {api_factory is not None}")
        self.logger().info(f"Domain: {domain}")
        self.logger().info(f"Throttler provided: {throttler is not None}")
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

    async def get_new_order_book(self, trading_pair: str) -> OrderBook:
        """
        Create a new order book for the given trading pair.
        
        Args:
            trading_pair: Trading pair
            
        Returns:
            New OrderBook instance
        """
        self.logger().info(f"DEBUG: get_new_order_book() called for {trading_pair}")
        self.logger().info(f"Creating new order book for {trading_pair}")
        
        try:
            # Create a new order book instance using SomniaOrderBook
            self.logger().info("DEBUG: Creating SomniaOrderBook instance")
            order_book = SomniaOrderBook()
            self.logger().info("DEBUG: SomniaOrderBook instance created successfully")
            
            # Initialize with snapshot data
            self.logger().info("DEBUG: Getting order book snapshot for initialization")
            snapshot_msg = await self._order_book_snapshot(trading_pair)
            self.logger().info("DEBUG: Order book snapshot obtained successfully")
            
            self.logger().info("DEBUG: Applying snapshot to order book")
            order_book.apply_snapshot(snapshot_msg.bids, snapshot_msg.asks, snapshot_msg.update_id)
            self.logger().info(f"Successfully created and initialized order book for {trading_pair}")
            
            return order_book
        except Exception as e:
            self.logger().error(f"DEBUG: Exception in get_new_order_book for {trading_pair}: {e}")
            self.logger().error(f"Error initializing order book for {trading_pair}: {e}")
            self.logger().exception("DEBUG: Full traceback:")
            raise

    async def _request_order_book_snapshot(self, trading_pair: str) -> Dict[str, Any]:
        """
        Request order book snapshot from the exchange using REST API.
        
        Args:
            trading_pair: Trading pair (e.g., 'STT-USDC')
            
        Returns:
            Raw order book data from exchange
        """
        self.logger().info(f"DEBUG: _request_order_book_snapshot called for {trading_pair}")
        self.logger().info(f"🔴 PRODUCTION MODE: Fetching REAL order book data for {trading_pair} from Somnia API")
        
        try:
            # Get REST assistant for making HTTP requests
            rest_assistant = await self._api_factory.get_rest_assistant()
            
            # Extract token addresses from trading pair for API call
            # STT-USDC -> base=STT, quote=USDC
            base_symbol, quote_symbol = trading_pair.split('-')
            
            # Token address mappings
            token_addresses = {
                "STT": "0x4A3BC48C156384f9564Fd65A53a2f3D534D8f2b7",
                "USDC": "0x0ED782B8079529f7385c3eDA9fAf1EaA0DbC6a17"
            }
            
            base_address = token_addresses.get(base_symbol)
            quote_address = token_addresses.get(quote_symbol)
            
            if not base_address or not quote_address:
                raise ValueError(f"Unknown token addresses for {trading_pair}. Base: {base_symbol} -> {base_address}, Quote: {quote_symbol} -> {quote_address}")
            
            self.logger().info(f"🔍 Token mapping: {base_symbol}({base_address}) / {quote_symbol}({quote_address})")
            
            # Prepare the API endpoint for order book ticks
            # Format: /api/orderbook/ticks/{base}/{quote}/{limit}
            limit = 20  # Get top 20 levels
            endpoint = f"/api/orderbook/ticks/{base_address}/{quote_address}/{limit}"
            
            # Use the base URL from constants
            from .somnia_constants import REST_API_BASE_URL
            url = f"{REST_API_BASE_URL}{endpoint}"
            
            self.logger().info(f"🌐 Making API call to: {url}")
            
            # Make the API call to Somnia REST endpoint
            response = await rest_assistant.execute_request(
                url=url,
                method=RESTMethod.GET,
                headers={"Content-Type": "application/json"},
                throttler_limit_id="order_book_snapshot"
            )
            
            self.logger().info(f"✅ Received response from Somnia API for {trading_pair}")
            self.logger().debug(f"📋 Raw API response: {response}")
            
            # Process the response from StandardWeb3 API
            if response and isinstance(response, dict):
                # Expected response format from StandardWeb3:
                # {
                #     "data": [
                #         {
                #             "price": "273.5",
                #             "size": "100.0", 
                #             "side": "buy"  # or "sell"
                #         },
                #         ...
                #     ]
                # }
                
                raw_data = response.get("data", [])
                if not raw_data:
                    self.logger().warning(f"⚠️ No order book data returned for {trading_pair}")
                    raw_data = []
                
                # Process and separate bids/asks
                bids = []
                asks = []
                
                for tick in raw_data:
                    try:
                        price = float(tick.get("price", 0))
                        size = float(tick.get("size", 0))
                        side = tick.get("side", "").lower()
                        
                        if side == "buy":
                            bids.append([price, size])
                        elif side == "sell":
                            asks.append([price, size])
                            
                    except (ValueError, TypeError) as e:
                        self.logger().warning(f"⚠️ Invalid tick data format: {tick}, error: {e}")
                        continue
                
                # Sort bids (highest price first) and asks (lowest price first)
                bids.sort(key=lambda x: x[0], reverse=True)
                asks.sort(key=lambda x: x[0])
                
                self.logger().info(f"📊 Processed order book: {len(bids)} bids, {len(asks)} asks")
                self.logger().debug(f"📈 Top bids: {bids[:5]}")
                self.logger().debug(f"📉 Top asks: {asks[:5]}")
                
                # Return in expected format for order book processing
                order_book_data = {
                    "symbol": trading_pair,
                    "bids": bids,
                    "asks": asks,
                    "timestamp": int(time.time() * 1000)
                }
                
                self.logger().info(f"🎯 Successfully fetched REAL order book data for {trading_pair}")
                return order_book_data
                
            else:
                self.logger().error(f"❌ Invalid response format from Somnia API for {trading_pair}: {response}")
                raise ValueError(f"Invalid order book response for {trading_pair}")
                
        except Exception as e:
            self.logger().error(f"💥 Failed to fetch order book from Somnia API for {trading_pair}: {e}")
            self.logger().exception("Full error details:")
            
            # For production, we should NOT fall back to mock data
            # Instead, raise the exception to signal the issue
            raise e

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

    async def listen_for_order_book_snapshots(self, ev_loop: asyncio.AbstractEventLoop, output: asyncio.Queue):
        """
        Listen for order book snapshots by polling the REST API.
        
        Args:
            ev_loop: Event loop
            output: Queue to put order book messages
        """
        self.logger().info("DEBUG: listen_for_order_book_snapshots() method called!")
        self.logger().info("Starting order book snapshot listener for Somnia")
        self.logger().info(f"Trading pairs to track: {self._trading_pairs}")
        
        while True:
            try:
                self.logger().debug("DEBUG: Polling for order book snapshots...")
                
                for trading_pair in self._trading_pairs:
                    try:
                        self.logger().info(f"DEBUG: Getting order book snapshot for {trading_pair}")
                        # Get order book snapshot
                        snapshot_msg = await self._order_book_snapshot(trading_pair)
                        output.put_nowait(snapshot_msg)
                        self.logger().info(f"DEBUG: Successfully put order book snapshot for {trading_pair} in queue")
                    except Exception as e:
                        self.logger().error(f"DEBUG: Error getting order book snapshot for {trading_pair}: {e}")
                
                # Wait before next poll (5 seconds)
                self.logger().debug("DEBUG: Waiting 5 seconds before next poll...")
                await asyncio.sleep(5.0)
                
            except asyncio.CancelledError:
                self.logger().info("DEBUG: Order book snapshot listener cancelled")
                break
            except Exception as e:
                self.logger().error(f"DEBUG: Error in order book snapshot listener: {e}")
                await asyncio.sleep(5.0)  # Wait before retrying

    async def listen_for_order_book_diffs(self, ev_loop: asyncio.AbstractEventLoop, output: asyncio.Queue):
        """
        Listen for order book differential updates.
        For Somnia (REST-only), we don't have real-time diffs, so this method does nothing.
        """
        self.logger().info("Order book diffs not supported for Somnia (REST-only exchange)")
        # For REST-only exchanges, we rely on snapshots only
        while True:
            await asyncio.sleep(60)  # Sleep indefinitely, we only use snapshots

    async def listen_for_trades(self, ev_loop: asyncio.AbstractEventLoop, output: asyncio.Queue):
        """
        Listen for trade updates.
        For Somnia (REST-only), we don't have real-time trade data, so this method does nothing.
        """
        self.logger().info("Real-time trade updates not supported for Somnia (REST-only exchange)")
        # For REST-only exchanges, we don't have real-time trade data
        while True:
            await asyncio.sleep(60)  # Sleep indefinitely

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
