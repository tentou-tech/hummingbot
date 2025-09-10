#!/usr/bin/env python

import asyncio
import logging
import time
from collections import defaultdict
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from standardweb3 import StandardClient

from hummingbot.connector.exchange.standard import (
    standard_constants as CONSTANTS,
    standard_utils as utils,
    standard_web_utils as web_utils,
)
from hummingbot.connector.exchange.standard.standard_order_book import StandardOrderBook
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.web_assistant.connections.data_types import RESTMethod, WSJSONRequest
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.core.web_assistant.ws_assistant import WSAssistant
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.connector.exchange.standard.standard_exchange import StandardExchange


class StandardAPIOrderBookDataSource(OrderBookTrackerDataSource):
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
        connector: Optional["StandardExchange"] = None,
        api_factory: Optional[WebAssistantsFactory] = None,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
        throttler: Optional[AsyncThrottler] = None,
    ):
        super().__init__(trading_pairs)
        self._connector = connector
        self._domain = domain
        self._api_factory = api_factory
        self._throttler = throttler

        # Cache for latest API prices to fix stale LastTrade price bug
        self._last_api_prices = {}  # {trading_pair: price}

        # Store latest API response to access mktPrice for pricing
        self._latest_api_response = None

        self.logger().info(f"🔄 Initialized API price cache for LastTrade fix: {self._last_api_prices}")
        self.logger().info("🔄 Initialized latest API response storage for mktPrice access")

        self.logger().info(f"StandardAPIOrderBookDataSource initialized with trading_pairs: {trading_pairs}")
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

        # Initialize StandardWeb3 client for API calls
        try:
            # noqa: mock - dummy key for read-only operations
            dummy_key = '0x0000000000000000000000000000000000000000000000000000000000000001'  # noqa: mock
            domain_config = CONSTANTS.DOMAIN_CONFIG[self._domain]
            self._standard_client = StandardClient(
                private_key=dummy_key,
                http_rpc_url=domain_config["rpc_url"],
                matching_engine_address=domain_config["standard_exchange_address"],
                api_url=domain_config["api_url"]
            )
            self.logger().info("✅ StandardWeb3 client initialized successfully")
        except Exception as e:
            self.logger().error(f"❌ Failed to initialize StandardWeb3 client: {e}")
            self._standard_client = None

    def update_trading_pairs(self, trading_pairs: List[str]):
        """
        Update trading pairs after initialization.

        Args:
            trading_pairs: New list of trading pairs to track
        """
        if trading_pairs != self._trading_pairs:
            old_pairs = self._trading_pairs
            new_pairs = trading_pairs
            self.logger().info(
                f"Updating order book data source trading pairs from {old_pairs} to {new_pairs}"
            )
            self._trading_pairs = trading_pairs

            # Initialize message queues for new trading pairs
            for trading_pair in trading_pairs:
                if trading_pair not in self._message_queue:
                    self._message_queue[trading_pair] = asyncio.Queue()
                if trading_pair not in self._last_orderbook_timestamp:
                    self._last_orderbook_timestamp[trading_pair] = 0.0

    async def get_last_traded_prices(
        self,
        trading_pairs: List[str],
        domain: Optional[str] = None
    ) -> Dict[str, float]:
        """
        Get last traded prices for trading pairs.
        For DEX with limited trade history, we use order book mid-price as last trade price.

        Args:
            trading_pairs: List of trading pairs
            domain: Domain (unused for Somnia)

        Returns:
            Dictionary mapping trading pairs to last prices
        """
        self.logger().info(f"🔍 get_last_traded_prices called for: {trading_pairs}")
        result = {}

        for trading_pair in trading_pairs:
            try:
                self.logger().info(f"🔄 Processing {trading_pair} for last traded price...")

                # First try to get actual trade history from the API
                last_trade_price = await self._get_last_trade_from_api(trading_pair)

                if last_trade_price is not None:
                    result[trading_pair] = last_trade_price
                    self.logger().info(f"✅ Got actual last trade price for {trading_pair}: {last_trade_price}")

                    # 🔧 FIX: Cache the fresh API price for LastTrade price type
                    # This prevents the strategy from using stale cached prices
                    self._last_api_prices[trading_pair] = last_trade_price
                    self.logger().info(f"🔄 Cached API price for LastTrade: {trading_pair} -> {last_trade_price}")
                    self.logger().info(f"📊 Current price cache: {self._last_api_prices}")

                    # 🔧 FIX: Update the exchange's order book last_trade_price with fresh API data
                    # This prevents the strategy from using stale cached prices
                    try:
                        if hasattr(self._connector, 'get_order_book'):
                            order_book = self._connector.get_order_book(trading_pair)
                            if order_book is not None:
                                old_price = order_book.last_trade_price
                                order_book.last_trade_price = last_trade_price
                                self.logger().info(
                                    f"🔄 Updated order book last_trade_price for {trading_pair}: "
                                    f"{old_price} -> {last_trade_price}"
                                )
                            else:
                                self.logger().warning(f"⚠️ Order book not found for {trading_pair}")
                        else:
                            self.logger().warning("⚠️ Connector does not have get_order_book method")
                    except Exception as update_error:
                        self.logger().warning(f"Could not update order book last_trade_price: {update_error}")
                else:
                    self.logger().error(f"⚠️ No trade price from API for {trading_pair}, using order book fallback")
                    # throw error
                    raise ValueError(f"No trade price available for {trading_pair}")
            except Exception as e:
                self.logger().error(f"❌ Error getting last traded price for {trading_pair}: {e}")

        self.logger().info(f"🎯 Final get_last_traded_prices result: {result}")
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
        # The _request_order_book_snapshot already returns processed data in format:
        # {"bids": [[price, size], ...], "asks": [[price, size], ...]}
        bids = snapshot.get("bids", [])
        asks = snapshot.get("asks", [])

        # Prepare data for StandardOrderBook
        snapshot_data = {
            "trading_pair": trading_pair,
            "bids": bids,
            "asks": asks,
        }

        # Create order book message using StandardOrderBook
        snapshot_msg = StandardOrderBook.snapshot_message_from_exchange_rest(
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
            # Create a new order book instance using StandardOrderBook
            self.logger().info("DEBUG: Creating StandardOrderBook instance")
            order_book = StandardOrderBook()
            self.logger().info("DEBUG: StandardOrderBook instance created successfully")

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
        Request order book snapshot from the exchange using StandardWeb3 client with REST API fallback.

        Args:
            trading_pair: Trading pair (e.g., 'STT-USDC')

        Returns:
            Raw order book data from exchange
        """
        self.logger().info(f"DEBUG: _request_order_book_snapshot called for {trading_pair}")
        production_msg = f"🔴 PRODUCTION MODE: Fetching REAL order book data for {trading_pair}"
        self.logger().info(production_msg)

        # Extract token addresses from trading pair for API call
        # STT-USDC -> base=STT, quote=USDC
        base_symbol, quote_symbol = trading_pair.split('-')

        # Get token addresses from constants file for the current domain
        from .standard_constants import get_token_addresses

        token_addresses = get_token_addresses(self._domain)
        base_address = token_addresses.get(base_symbol)
        quote_address = token_addresses.get(quote_symbol)

        if not base_address or not quote_address:
            error_msg = (
                f"Unknown token addresses for {trading_pair}. "
                f"Base: {base_symbol} -> {base_address}, Quote: {quote_symbol} -> {quote_address}"
            )
            raise ValueError(error_msg)

        self.logger().info(f"🔍 Token mapping: {base_symbol}({base_address}) / {quote_symbol}({quote_address})")

        # Method 1: Try StandardWeb3 client first
        if self._standard_client:
            try:
                self.logger().info("🥇 PRIMARY: Attempting StandardWeb3 client method")
                return await self._fetch_via_standardweb3(base_address, quote_address, trading_pair)
            except Exception as e:
                self.logger().warning(f"⚠️ StandardWeb3 client failed: {e}")
                self.logger().info("🔄 Falling back to REST API method")
        else:
            self.logger().warning("⚠️ StandardWeb3 client not available, using REST API method")

        # Method 2: Fallback to REST API
        try:
            self.logger().info("🥈 FALLBACK: Using REST API method")
            base_url = CONSTANTS.DOMAIN_CONFIG[self._domain]["api_url"]
            return await self._fetch_via_rest_api(base_address, quote_address, trading_pair, base_url)
        except Exception as e:
            self.logger().error(f"💥 Both StandardWeb3 and REST API methods failed for {trading_pair}")
            self.logger().error(f"StandardWeb3 client available: {self._standard_client is not None}")
            self.logger().error(f"REST API error: {e}")
            raise e

    async def _fetch_via_standardweb3(self, base_address: str, quote_address: str, trading_pair: str) -> Dict[str, Any]:
        """
        Fetch order book data using StandardWeb3 client.

        Args:
            base_address: Base token address
            quote_address: Quote token address
            trading_pair: Trading pair name

        Returns:
            Order book data in standardized format
        """
        # Use StandardWeb3 client to fetch order book ticks
        limit = 20  # Get top 20 levels

        self.logger().info(f"🌐 Calling StandardWeb3 fetch_orderbook_ticks({base_address}, {quote_address}, {limit})")

        # Call the async standardweb3 API method directly
        response = await self._standard_client.fetch_orderbook_ticks(
            base=base_address,
            quote=quote_address,
            limit=limit
        )

        self.logger().info(f"✅ Received response from StandardWeb3 API for {trading_pair}")
        self.logger().debug(f"📋 Raw API response: {response}")

        # 🔧 STORE LATEST API RESPONSE - for get_price_by_type to access mktPrice
        self._latest_api_response = response
        mkt_price = response.get('mktPrice') if response else None
        self.logger().debug(f"🔄 Stored latest API response for pricing: mktPrice = {mkt_price}")

        # Process the response from StandardWeb3 API
        if response and isinstance(response, dict):
            # {
            #     "id": "...",
            #     "mktPrice": 286.68875,
            #     "bids": [{"orderbook": "...", "price": 286.68875, "amount": 2406.3303, "count": 1}, ...],
            #     "asks": [{"orderbook": "...", "price": 286.68906, "amount": 4.6462846, "count": 1}, ...]
            # }

            raw_bids = response.get("bids", [])
            raw_asks = response.get("asks", [])

            if not raw_bids and not raw_asks:
                self.logger().warning(f"⚠️ No order book data returned for {trading_pair}")

            # Process bids and asks directly from the response
            bids = []
            asks = []

            # Process bids
            for bid in raw_bids:
                try:
                    price = float(bid.get("price", 0))
                    amount = float(bid.get("amount", 0))
                    if price > 0 and amount > 0:  # Skip zero amounts
                        bids.append([price, amount])
                except (ValueError, TypeError) as e:
                    self.logger().warning(f"⚠️ Invalid bid data format: {bid}, error: {e}")
                    continue

            # Process asks
            for ask in raw_asks:
                try:
                    price = float(ask.get("price", 0))
                    amount = float(ask.get("amount", 0))
                    if price > 0 and amount > 0:  # Skip zero amounts
                        asks.append([price, amount])
                except (ValueError, TypeError) as e:
                    self.logger().warning(f"⚠️ Invalid ask data format: {ask}, error: {e}")
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
                "timestamp": int(time.time() * 1000),
                "mktPrice": response.get("mktPrice", 0),  # Include market price if available
                "source": "standardweb3"
            }

            success_msg = f"🎯 Successfully fetched REAL order book data for {trading_pair} using StandardWeb3"
            self.logger().info(success_msg)
            return order_book_data

        else:
            raise ValueError(f"Invalid StandardWeb3 response format for {trading_pair}: {response}")

    async def _fetch_via_rest_api(
        self, base_address: str, quote_address: str, trading_pair: str, base_url: str
    ) -> Dict[str, Any]:
        """
        Fetch order book data using direct REST API calls as fallback.

        Args:
            base_address: Base token address
            quote_address: Quote token address
            trading_pair: Trading pair name
            base_url: REST API base URL

        Returns:
            Order book data in standardized format
        """
        # Get REST assistant for making HTTP requests
        rest_assistant = await self._api_factory.get_rest_assistant()

        # Prepare the API endpoint for order book ticks
        # Format: /api/orderbook/ticks/{base}/{quote}/{limit}
        limit = 20  # Get top 20 levels
        endpoint = f"api/orderbook/ticks/{base_address}/{quote_address}/{limit}"
        # Remove trailing slash from base_url if present to avoid double slash
        base_url = base_url.rstrip("/")
        url = f"{base_url}/{endpoint}"

        self.logger().info(f"🌐 Making REST API call to: {url}")

        # Make the API call to Somnia REST endpoint
        response = await rest_assistant.execute_request(
            url=url,
            method=RESTMethod.GET,
            headers={"Content-Type": "application/json"},
            throttler_limit_id=CONSTANTS.GET_ORDERBOOK_PATH_URL
        )

        self.logger().info(f"✅ Received response from REST API for {trading_pair}")
        self.logger().debug(f"📋 Raw API response: {response}")

        # Process the response from REST API
        if response and isinstance(response, dict):
            # Check if it's the same format as StandardWeb3 or a different format
            if "bids" in response and "asks" in response:
                # Same format as StandardWeb3 - process directly
                self.logger().info("📋 REST API returned StandardWeb3-compatible format")
                return await self._process_standardweb3_format(
                    response, trading_pair, "rest_api"
                )
            else:
                # Handle other potential formats here
                # This could be extended to handle different API response formats
                self.logger().warning(f"⚠️ Unknown REST API response format for {trading_pair}")
                raise ValueError(f"Unrecognized REST API response format for {trading_pair}")
        else:
            raise ValueError(f"Invalid REST API response for {trading_pair}: {response}")

    async def _process_standardweb3_format(
        self, response: Dict[str, Any], trading_pair: str, source: str
    ) -> Dict[str, Any]:
        """
        Process response data that follows StandardWeb3 format.

        Args:
            response: API response data
            trading_pair: Trading pair name
            source: Source of the data ("standardweb3" or "rest_api")

        Returns:
            Processed order book data
        """
        raw_bids = response.get("bids", [])
        raw_asks = response.get("asks", [])

        if not raw_bids and not raw_asks:
            self.logger().warning(f"⚠️ No order book data returned for {trading_pair} from {source}")

        # Process bids and asks
        bids = []
        asks = []

        # Process bids
        for bid in raw_bids:
            try:
                price = float(bid.get("price", 0))
                amount = float(bid.get("amount", 0))
                if price > 0 and amount > 0:  # Skip zero amounts
                    bids.append([price, amount])
            except (ValueError, TypeError) as e:
                self.logger().warning(f"⚠️ Invalid bid data format: {bid}, error: {e}")
                continue

        # Process asks
        for ask in raw_asks:
            try:
                price = float(ask.get("price", 0))
                amount = float(ask.get("amount", 0))
                if price > 0 and amount > 0:  # Skip zero amounts
                    asks.append([price, amount])
            except (ValueError, TypeError) as e:
                self.logger().warning(f"⚠️ Invalid ask data format: {ask}, error: {e}")
                continue

        # Sort bids (highest price first) and asks (lowest price first)
        bids.sort(key=lambda x: x[0], reverse=True)
        asks.sort(key=lambda x: x[0])

        self.logger().info(f"📊 Processed order book from {source}: {len(bids)} bids, {len(asks)} asks")
        self.logger().debug(f"📈 Top bids: {bids[:5]}")
        self.logger().debug(f"📉 Top asks: {asks[:5]}")

        # Return in expected format for order book processing
        order_book_data = {
            "symbol": trading_pair,
            "bids": bids,
            "asks": asks,
            "timestamp": int(time.time() * 1000),
            "mktPrice": response.get("mktPrice", 0),  # Include market price if available
            "source": source
        }

        self.logger().info(f"🎯 Successfully fetched REAL order book data for {trading_pair} using {source}")
        return order_book_data

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

    async def _get_last_trade_from_api(self, trading_pair: str) -> Optional[float]:
        """
        Get the last trade price from the API using mktPrice if available.

        Args:
            trading_pair: Trading pair (e.g., SOMI-USDC)

        Returns:
            Last trade price (mktPrice) or None if not available
        """
        try:
            if self._standard_client is None:
                warning_msg = "StandardWeb3 client not initialized, cannot fetch order book"
                self.logger().warning(warning_msg)
                return None

            # Convert trading pair to contract addresses
            base_asset, quote_asset = trading_pair.split('-')

            # Get token addresses from constants
            from .standard_constants import get_token_addresses
            token_addresses = get_token_addresses(self._domain)
            base_address = token_addresses.get(base_asset)
            quote_address = token_addresses.get(quote_asset)

            if not base_address or not quote_address:
                self.logger().warning(f"Token addresses not found for {trading_pair}")
                return None

            fetch_msg = (
                f"🔍 Fetching market price for {trading_pair}: "
                f"{base_asset}({base_address}) / {quote_asset}({quote_address})"
            )
            self.logger().info(fetch_msg)

            # Get market price from API response
            try:
                self.logger().info("🎯 Getting market price from API")
                response = await self._standard_client.fetch_orderbook_ticks(
                    base=base_address,
                    quote=quote_address,
                    limit=10
                )

                if response and isinstance(response, dict):
                    # Get mktPrice if available
                    mkt_price = response.get("mktPrice")

                    if mkt_price and mkt_price > 0:
                        self.logger().info(f"✅ Got market price for {trading_pair}: {mkt_price}")
                        return float(mkt_price)
                    else:
                        self.logger().warning(f"⚠️ No valid mktPrice in response: {mkt_price}")
                else:
                    self.logger().warning(f"⚠️ Invalid response from fetch_orderbook_ticks: {response}")

            except Exception as e:
                self.logger().warning(f"⚠️ Could not get market price: {e}")

            return None  # No price data available

        except Exception as e:
            self.logger().error(f"❌ Error fetching market price for {trading_pair}: {e}")
            return None

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
