#!/usr/bin/env python

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from hummingbot.connector.exchange.standard import (
    standard_constants as CONSTANTS,
    standard_utils as utils,
    standard_web_utils as web_utils,
)
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory
from hummingbot.logger import HummingbotLogger

if TYPE_CHECKING:
    from hummingbot.connector.exchange.standard.standard_auth import StandardAuth


class StandardAPIUserStreamDataSource(UserStreamTrackerDataSource):
    """
    User stream data source for Somnia exchange.
    Handles real-time updates for user-specific data like orders, balances, and trades.
    """
    
    _logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(
        self,
        auth: "StandardAuth",
        trading_pairs: List[str],
        connector,
        api_factory: Optional[WebAssistantsFactory] = None,
        domain: str = CONSTANTS.DEFAULT_DOMAIN,
        throttler: Optional[AsyncThrottler] = None,
    ):
        super().__init__()
        self._auth = auth
        self._trading_pairs = trading_pairs
        self._connector = connector
        self._domain = domain
        self._throttler = throttler or web_utils.create_throttler()
        self._api_factory = api_factory or web_utils.build_api_factory(
            throttler=self._throttler,
            auth=self._auth,
        )
        self._last_recv_time: float = 0

    async def listen_for_user_stream(self, output: asyncio.Queue):
        """
        Override to disable WebSocket user stream functionality.
        Somnia currently relies on periodic REST API calls for user data updates.
        """
        self.logger().info("Somnia user stream disabled - using REST API polling for user data updates.")
        # Just return - no WebSocket subscriptions needed for REST-based connector
        return

    async def _connected_websocket_assistant(self):
        """
        Create and maintain WebSocket connection for user stream data.
        
        Returns:
            WebSocket assistant for user stream
        """
        try:
            ws_assistant = await self._api_factory.get_ws_assistant()
            await ws_assistant.connect(
                ws_url=web_utils.get_websocket_url(self._domain),
                message_timeout=CONSTANTS.UPDATE_ORDERBOOK_INTERVAL,
            )
            
            # Authenticate the WebSocket connection
            await self._authenticate_websocket(ws_assistant)
            
            return ws_assistant
            
        except Exception as e:
            self.logger().error(f"Error connecting to user stream WebSocket: {e}")
            raise

    async def _authenticate_websocket(self, ws_assistant) -> None:
        """
        Authenticate WebSocket connection for user stream.
        
        Args:
            ws_assistant: WebSocket assistant
        """
        try:
            # Send authentication message
            auth_message = {
                "type": "auth",
                "wallet_address": self._auth.get_wallet_address(),
                "timestamp": utils.generate_timestamp(),
            }
            
            await ws_assistant.send(auth_message)
            self.logger().info("WebSocket authentication message sent")
            
        except Exception as e:
            self.logger().error(f"Error authenticating WebSocket: {e}")
            raise

    async def _subscribe_channels(self, ws_assistant) -> None:
        """
        Subscribe to user stream channels.
        
        Args:
            ws_assistant: WebSocket assistant
        """
        try:
            # Subscribe to user-specific channels
            subscriptions = [
                {
                    "type": "subscribe",
                    "channel": "orders",
                    "wallet_address": self._auth.get_wallet_address(),
                },
                {
                    "type": "subscribe", 
                    "channel": "balances",
                    "wallet_address": self._auth.get_wallet_address(),
                },
                {
                    "type": "subscribe",
                    "channel": "trades",
                    "wallet_address": self._auth.get_wallet_address(),
                },
            ]
            
            for subscription in subscriptions:
                await ws_assistant.send(subscription)
                await asyncio.sleep(0.1)  # Small delay between subscriptions
                
            self.logger().info("Subscribed to user stream channels")
            
        except Exception as e:
            self.logger().error(f"Error subscribing to channels: {e}")
            raise

    async def _process_websocket_messages(self, websocket_assistant) -> None:
        """
        Process incoming WebSocket messages for user stream.
        
        Args:
            websocket_assistant: WebSocket assistant
        """
        async for ws_response in websocket_assistant.iter_messages():
            try:
                data = ws_response.data
                if isinstance(data, dict):
                    await self._process_user_stream_message(data)
                    self._last_recv_time = utils.generate_timestamp()
                    
            except Exception as e:
                self.logger().error(f"Error processing WebSocket message: {e}")

    async def _process_user_stream_message(self, message: Dict[str, Any]) -> None:
        """
        Process individual user stream message.
        
        Args:
            message: User stream message
        """
        try:
            message_type = message.get("type")
            
            if message_type == "order_update":
                await self._process_order_update(message)
            elif message_type == "balance_update":
                await self._process_balance_update(message)
            elif message_type == "trade_update":
                await self._process_trade_update(message)
            elif message_type == "error":
                self.logger().error(f"WebSocket error: {message.get('message', 'Unknown error')}")
            else:
                self.logger().debug(f"Unknown message type: {message_type}")
                
        except Exception as e:
            self.logger().error(f"Error processing user stream message: {e}")

    async def _process_order_update(self, message: Dict[str, Any]) -> None:
        """
        Process order update message.
        
        Args:
            message: Order update message
        """
        try:
            # Extract order information
            order_data = message.get("data", {})
            order_id = order_data.get("id")
            
            if order_id:
                # Put the message in the queue for the connector to process
                self._message_queue.put_nowait(message)
                self.logger().debug(f"Order update processed for order {order_id}")
                
        except Exception as e:
            self.logger().error(f"Error processing order update: {e}")

    async def _process_balance_update(self, message: Dict[str, Any]) -> None:
        """
        Process balance update message.
        
        Args:
            message: Balance update message
        """
        try:
            # Extract balance information
            balance_data = message.get("data", {})
            
            # Put the message in the queue for the connector to process
            self._message_queue.put_nowait(message)
            self.logger().debug("Balance update processed")
            
        except Exception as e:
            self.logger().error(f"Error processing balance update: {e}")

    async def _process_trade_update(self, message: Dict[str, Any]) -> None:
        """
        Process trade update message.
        
        Args:
            message: Trade update message
        """
        try:
            # Extract trade information
            trade_data = message.get("data", {})
            trade_id = trade_data.get("id")
            
            if trade_id:
                # Put the message in the queue for the connector to process
                self._message_queue.put_nowait(message)
                self.logger().debug(f"Trade update processed for trade {trade_id}")
                
        except Exception as e:
            self.logger().error(f"Error processing trade update: {e}")

    async def _get_listen_key(self) -> Optional[str]:
        """
        Get listen key for user stream (if required by exchange).
        
        Returns:
            Listen key or None if not applicable
        """
        # Somnia might not use traditional listen keys
        # This would be implemented if the exchange requires it
        return None

    async def _ping_listen_key(self, listen_key: str) -> bool:
        """
        Ping listen key to keep it active.
        
        Args:
            listen_key: Listen key to ping
            
        Returns:
            True if successful, False otherwise
        """
        # Implementation if listen key pinging is required
        return True

    @property
    def last_recv_time(self) -> float:
        """
        Get timestamp of last received message.
        
        Returns:
            Timestamp of last received message
        """
        return self._last_recv_time
